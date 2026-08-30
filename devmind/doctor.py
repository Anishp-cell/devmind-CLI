"""
devmind/doctor.py

Self-healing system & environment diagnostics for DevMind CLI.
Verifies Python version, git availability, active AI provider connectivity,
local memory/cache integrity, FastEmbed readiness, and network/update status —
so problems surface with a clear fix instead of a raw stack trace mid-command.
"""

import os
import sys
import shutil
import sqlite3
import tempfile
import platform
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CheckResult:
    name: str
    status: str  # "ok" | "warn" | "fail"
    detail: str
    fix_hint: Optional[str] = None


MIN_PYTHON = (3, 10)


def check_python_version() -> CheckResult:
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    if (version.major, version.minor) < MIN_PYTHON:
        return CheckResult(
            "Python Version", "fail",
            f"{version_str} (requires >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]})",
            fix_hint="Install Python 3.10 or newer.",
        )

    import importlib

    missing_extensions = []
    for module_name in ("sqlite3", "ssl", "ctypes"):
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing_extensions.append(module_name)

    if missing_extensions:
        return CheckResult(
            "Python Version", "warn",
            f"{version_str} — missing C-extensions: {', '.join(missing_extensions)}",
            fix_hint="Reinstall Python with full standard library support.",
        )

    return CheckResult("Python Version", "ok", f"{version_str} (Compatible >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]})")


def check_git() -> CheckResult:
    git_path = shutil.which("git")
    if not git_path:
        return CheckResult(
            "Git Binary", "fail", "git not found on PATH",
            fix_hint="Install git and ensure it's on your PATH.",
        )

    try:
        import subprocess
        result = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
        version_str = result.stdout.strip() or "git (version unknown)"
    except Exception:
        version_str = "git (version unknown)"

    try:
        from devmind.memory import get_project_root
        root = get_project_root(os.getcwd())
        is_repo = os.path.exists(os.path.join(root, ".git"))
    except Exception:
        is_repo = os.path.exists(os.path.join(os.getcwd(), ".git"))

    if is_repo:
        return CheckResult("Git Binary", "ok", f"{version_str} (Repository initialized)")
    return CheckResult(
        "Git Binary", "warn", f"{version_str} (No git repository found in current directory)",
        fix_hint="Run 'git init' or navigate to your project's repository.",
    )


def check_provider_health() -> CheckResult:
    from devmind.memory import load_api_keys
    from devmind.config_wizard import verify_provider_connection, PROVIDER_KEY_ENV

    load_api_keys()
    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        try:
            req = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                import json
                payload = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name") for m in payload.get("models", [])]
                if models:
                    return CheckResult("Ollama Health", "ok", f"Reachable at {base_url} — models: {', '.join(models[:5])}")
                return CheckResult(
                    "Ollama Health", "warn", f"Reachable at {base_url} but no models pulled",
                    fix_hint="Run 'ollama pull <model>' to download a local model.",
                )
        except Exception as e:
            return CheckResult(
                "Ollama Health", "fail", f"Cannot reach Ollama at {base_url}: {e}",
                fix_hint="Start the Ollama daemon with 'ollama serve'.",
            )

    key_env, keys_env = PROVIDER_KEY_ENV.get(provider, (None, None))
    api_key = ""
    if keys_env and os.getenv(keys_env):
        api_key = os.getenv(keys_env).split(",")[0].strip()
    elif key_env and os.getenv(key_env):
        api_key = os.getenv(key_env)

    if not api_key:
        return CheckResult(
            f"{provider.title()} Provider", "fail", "No API key configured",
            fix_hint="Run 'devmind init' to configure a provider.",
        )

    model = os.getenv("LLM_MODEL", "(default)")
    masked = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "***"

    import time
    start = time.monotonic()
    success, msg = verify_provider_connection(provider_id=provider, api_key=api_key, model=model)
    latency_ms = int((time.monotonic() - start) * 1000)

    if success:
        return CheckResult(
            f"{provider.title()} Provider", "ok",
            f"{masked} • Model: {model} • {latency_ms}ms latency",
        )
    return CheckResult(
        f"{provider.title()} Provider", "fail", msg,
        fix_hint="Run 'devmind config' to update your API key.",
    )


def check_memory_integrity() -> CheckResult:
    from devmind.memory import system_path, data_path

    if not os.path.exists(system_path) and not os.path.exists(data_path):
        return CheckResult(
            "Local Memory Graph", "warn", "No memory index found for this project",
            fix_hint="Run 'devmind remember' to build the codebase memory index.",
        )

    db_path = os.path.join(system_path, "databases", "cache.db")
    connectivity_ok = True
    connectivity_detail = ""
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path, timeout=3)
            conn.execute("SELECT name FROM sqlite_master LIMIT 1;")
            conn.close()
        except Exception as e:
            connectivity_ok = False
            connectivity_detail = f" (SQLite connectivity issue: {e})"

    def _dir_size(path: str) -> int:
        total = 0
        for dirpath, _, filenames in os.walk(path):
            for fn in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, fn))
                except OSError:
                    pass
        return total

    total_bytes = _dir_size(system_path) + _dir_size(data_path)
    size_mb = total_bytes / (1024 * 1024)

    if not connectivity_ok:
        return CheckResult("Local Memory Graph", "fail", f"{size_mb:.1f} MB indexed{connectivity_detail}")

    # Warn if the index was built by a different DevMind minor version — the
    # underlying Cognee schema can change between releases, which sometimes
    # surfaces as cryptic SQLAlchemy errors on an old index.
    from devmind import __version__ as current_version
    version_stamp_path = os.path.join(system_path, ".devmind_version")
    if os.path.exists(version_stamp_path):
        try:
            with open(version_stamp_path, "r", encoding="utf-8") as f:
                indexed_version = f.read().strip()
            if indexed_version and indexed_version.split(".")[:2] != current_version.split(".")[:2]:
                return CheckResult(
                    "Local Memory Graph", "warn",
                    f"{size_mb:.1f} MB indexed by v{indexed_version}, but DevMind is now v{current_version}",
                    fix_hint="If queries behave oddly, run 'devmind forget --all' then 'devmind remember' to rebuild the index.",
                )
        except OSError:
            pass

    return CheckResult("Local Memory Graph", "ok", f"{size_mb:.1f} MB indexed in .cognee_system/.cognee_data")


def check_fastembed() -> CheckResult:
    embedding_provider = os.getenv("EMBEDDING_PROVIDER", "fastembed").lower()
    if embedding_provider != "fastembed":
        return CheckResult("Local Embeddings", "ok", f"Using '{embedding_provider}' embedding provider")

    try:
        import fastembed  # noqa: F401
    except ImportError:
        return CheckResult(
            "Local Embeddings", "fail", "fastembed package not installed",
            fix_hint="Run 'pip install -e .' to install dependencies.",
        )

    from devmind.memory import system_path
    try:
        os.makedirs(system_path, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=system_path, delete=True):
            pass
    except OSError as e:
        return CheckResult(
            "Local Embeddings", "fail", f"No write permission at {system_path}: {e}",
            fix_hint="Check filesystem permissions for your project directory.",
        )

    model = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    return CheckResult("Local Embeddings", "ok", f"FastEmbed {model} (Ready)")


def check_network_and_update() -> CheckResult:
    from devmind.version_checker import fetch_latest_version_from_pypi, is_version_newer
    from devmind import __version__ as current_version

    latest = fetch_latest_version_from_pypi(timeout=2.0)
    if latest is None:
        return CheckResult(
            "Network & Update", "warn", "Could not reach PyPI (offline or timeout)",
            fix_hint="Check your internet connection if you need update checks.",
        )

    if is_version_newer(latest, current_version):
        return CheckResult(
            "Network & Update", "warn", f"Update available: {current_version} → {latest}",
            fix_hint="Run 'pip install -U devmind-cli' to upgrade.",
        )
    return CheckResult("Network & Update", "ok", f"Up to date (v{current_version})")


def run_diagnostics() -> list:
    """Runs every diagnostic check and returns a list of CheckResult, in display order."""
    checks = [
        check_python_version,
        check_git,
        check_provider_health,
        check_memory_integrity,
        check_fastembed,
        check_network_and_update,
    ]
    results = []
    for check in checks:
        try:
            results.append(check())
        except Exception as e:
            results.append(CheckResult(check.__name__, "fail", f"Check crashed: {e}"))
    return results


_STATUS_ICON = {"ok": "✅", "warn": "⚠️ ", "fail": "🔴"}


def render_diagnostics(results: list, console=None):
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from devmind.memory import get_project_root

    console = console or Console()
    project_name = os.path.basename(get_project_root(os.getcwd()))

    header = (
        f"[bold]Project:[/bold] {project_name}  │  "
        f"[bold]Python:[/bold] {platform.python_version()}  │  "
        f"[bold]Platform:[/bold] {platform.system()}"
    )
    console.print(Panel.fit(header, title="🩺 DevMind System Diagnostics", border_style="cyan"))

    body = Text()
    has_fail = False
    has_warn = False
    for r in results:
        icon = _STATUS_ICON.get(r.status, "•")
        body.append(f"  {icon} {r.name}:", style="bold")
        body.append(f" {r.detail}\n")
        if r.status == "fail":
            has_fail = True
            if r.fix_hint:
                body.append(f"      💡 Fix: {r.fix_hint}\n", style="dim red")
        elif r.status == "warn":
            has_warn = True
            if r.fix_hint:
                body.append(f"      💡 Suggestion: {r.fix_hint}\n", style="dim yellow")

    console.print(body)

    if has_fail:
        console.print("[bold red]🔴 One or more critical issues detected. See fixes above.[/bold red]")
    elif has_warn:
        console.print("[bold yellow]⚠️  DevMind is functional, but some checks need attention.[/bold yellow]")
    else:
        console.print("[bold green]🎉 Everything looks great! DevMind is operating at peak health.[/bold green]")
