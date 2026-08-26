"""
devmind/version_checker.py

Ultra-fast, non-blocking PyPI update checker for DevMind CLI.
Caches version checks locally for 24 hours so it never slows down terminal commands.
Fails silently when offline or on timeouts.
"""

from __future__ import annotations

import os
import json
import time
import urllib.request
import pathlib
import logging
from typing import Optional, Tuple
from devmind import __version__ as CURRENT_VERSION

logger = logging.getLogger("devmind.version_checker")

CACHE_TTL_SECONDS = 86400  # 24 hours
PYPI_URL = "https://pypi.org/pypi/devmind-cli/json"


def get_cache_file_path() -> pathlib.Path:
    """Returns the platform-appropriate path for the version cache file."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(pathlib.Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(pathlib.Path.home() / ".config")
    
    config_dir = pathlib.Path(base) / "devmind"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "version_cache.json"


def parse_version_tuple(v_str: str) -> Tuple[int, ...]:
    """Converts version string (e.g. '0.3.7' or '1.0.0b1') into comparable integer tuple."""
    import re
    parts = re.findall(r"\d+", v_str)
    return tuple(int(p) for p in parts) if parts else (0,)


def is_version_newer(latest: str, current: str) -> bool:
    """Returns True if latest version is strictly greater than current version."""
    try:
        return parse_version_tuple(latest) > parse_version_tuple(current)
    except Exception:
        return False


def get_cached_latest_version() -> Optional[str]:
    """Reads cached latest version if cache is valid (<24h old)."""
    cache_path = get_cache_file_path()
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            last_checked = data.get("last_checked", 0)
            if time.time() - last_checked < CACHE_TTL_SECONDS:
                return data.get("latest_version")
    except Exception:
        pass
    return None


def fetch_latest_version_from_pypi(timeout: float = 0.8) -> Optional[str]:
    """Queries PyPI API with a strict short timeout and updates local cache."""
    try:
        req = urllib.request.Request(
            PYPI_URL,
            headers={"User-Agent": f"devmind-cli/{CURRENT_VERSION}"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                payload = json.loads(response.read().decode("utf-8"))
                latest_ver = payload.get("info", {}).get("version")
                if latest_ver:
                    cache_path = get_cache_file_path()
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump({
                            "last_checked": time.time(),
                            "latest_version": latest_ver
                        }, f)
                    return latest_ver
    except Exception:
        # Fail silently if offline or timeout
        pass
    return None


def check_for_updates() -> Optional[str]:
    """
    Checks if a newer DevMind release is available on PyPI.
    Returns the new version string if an update is available, else None.
    """
    # Allow users and CI/CD pipelines to disable update checks
    if os.environ.get("DEVMIND_NO_UPDATE_CHECK", "").lower() in ("1", "true", "yes"):
        return None
    if os.environ.get("CI", "").lower() in ("1", "true", "yes"):
        return None

    # 1. Check local cache first
    latest = get_cached_latest_version()

    # 2. If cache expired or missing, query PyPI
    if not latest:
        latest = fetch_latest_version_from_pypi(timeout=0.8)

    if latest and is_version_newer(latest, CURRENT_VERSION):
        return latest
    return None


def show_update_notification(console=None):
    """Renders a non-intrusive update alert banner if a new release is available."""
    try:
        new_version = check_for_updates()
        if not new_version:
            return

        if console is None:
            from rich.console import Console
            console = Console()

        from rich.panel import Panel
        from rich.text import Text

        content = Text()
        content.append("🚀 Update available! ", style="bold yellow")
        content.append(f"{CURRENT_VERSION}", style="dim")
        content.append(" → ", style="bold")
        content.append(f"{new_version}\n", style="bold green")
        content.append("Run ", style="dim")
        content.append("pip install -U devmind-cli", style="bold cyan")
        content.append(" to get the latest features & improvements.", style="dim")

        console.print()
        console.print(Panel(content, border_style="yellow", expand=False))
        console.print()
    except Exception:
        # Never crash or interrupt the user's workflow
        pass
