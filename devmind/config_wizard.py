"""
devmind/config_wizard.py

Interactive onboarding and configuration wizard for DevMind CLI.
Allows developers to configure AI model providers (Groq, Gemini, Anthropic Claude,
OpenAI, Ollama, OpenRouter, Custom Endpoints) with zero manual .env editing.
Saves settings globally or locally, and verifies connections live.
"""

import os
import sys
import json
import pathlib
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

logger = logging.getLogger("devmind.config_wizard")

def get_global_config_path() -> pathlib.Path:
    """
    Returns the platform-appropriate path for the global DevMind config file.
    - Windows:       %APPDATA%\\devmind\\config.json
    - macOS / Linux: ~/.config/devmind/config.json
    """
    if sys.platform == "win32":
        base = pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home() / "AppData" / "Roaming"))
    else:
        base = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", pathlib.Path.home() / ".config"))
    return base / "devmind" / "config.json"


def load_global_config() -> Dict[str, Any]:
    """Reads and returns the global configuration dict, or empty dict if not found."""
    cfg_path = get_global_config_path()
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading global config from {cfg_path}: {e}")
    return {}


def is_any_provider_configured() -> bool:
    """
    Checks if at least one LLM provider (or local model) is configured
    either in environment variables, active .env file, or global config.json.
    """
    # Check env vars
    keys_to_check = [
        "GROQ_API_KEY", "GROQ_API_KEYS",
        "GEMINI_API_KEY", "GEMINI_API_KEYS",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "OLLAMA_MODEL",
    ]
    for k in keys_to_check:
        if os.getenv(k):
            return True

    if os.getenv("LLM_PROVIDER") == "ollama":
        return True

    # Check global config file
    cfg = load_global_config()
    for k in keys_to_check:
        if cfg.get(k):
            return True
    if cfg.get("LLM_PROVIDER") == "ollama":
        return True

    return False


def verify_provider_connection(
    provider_id: str,
    api_key: str = "",
    model: str = "",
    base_url: str = ""
) -> Tuple[bool, str]:
    """
    Sends a lightweight HTTP ping to verify that the provider API key
    or local Ollama daemon is reachable and responding.
    """
    try:
        if provider_id == "groq":
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            with urllib.request.urlopen(req, timeout=7) as resp:
                if resp.status == 200:
                    return True, "Groq API verified successfully."
                return False, f"Unexpected response status: {resp.status}"

        elif provider_id == "openai":
            req = urllib.request.Request(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            with urllib.request.urlopen(req, timeout=7) as resp:
                if resp.status == 200:
                    return True, "OpenAI API verified successfully."
                return False, f"Unexpected response status: {resp.status}"

        elif provider_id == "gemini":
            # Gemini models endpoint
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=7) as resp:
                if resp.status == 200:
                    return True, "Google Gemini API verified successfully."
                return False, f"Unexpected response status: {resp.status}"

        elif provider_id == "anthropic":
            # Test Anthropic key using lightweight version ping
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01"
                }
            )
            with urllib.request.urlopen(req, timeout=7) as resp:
                if resp.status in (200, 400):  # 400 with valid key structure or 200
                    return True, "Anthropic Claude API reachable."
                return False, f"Unexpected response status: {resp.status}"

        elif provider_id == "openrouter":
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            with urllib.request.urlopen(req, timeout=7) as resp:
                if resp.status == 200:
                    return True, "OpenRouter API verified successfully."
                return False, f"Unexpected response status: {resp.status}"

        elif provider_id == "ollama":
            url = f"{base_url.rstrip('/')}/api/tags"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return True, f"Ollama daemon is running at {base_url}."
                return False, f"Ollama responded with status {resp.status}"

        elif provider_id == "custom":
            url = f"{base_url.rstrip('/')}/models"
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.status in (200, 404, 405):
                    return True, f"Custom endpoint reachable at {base_url}."
                return False, f"Endpoint returned status: {resp.status}"

    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, f"Authentication failed (HTTP {e.code}): Invalid API key."
        return False, f"HTTP Error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        if provider_id == "ollama":
            return False, f"Cannot connect to Ollama at {base_url}. Ensure 'ollama serve' is running."
        return False, f"Connection failed: {e.reason}"
    except Exception as e:
        return False, f"Validation error: {str(e)}"

    return True, "Verified."


def save_configuration(config_dict: Dict[str, Any], global_scope: bool = True) -> str:
    """
    Persists configuration settings either to the global config.json or the project .env.
    Returns the file path where configuration was saved.
    """
    if global_scope:
        cfg_path = get_global_config_path()
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        existing = load_global_config()
        existing.update(config_dict)
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
        return str(cfg_path)
    else:
        env_path = pathlib.Path(".env").resolve()
        existing_lines = []
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                existing_lines = f.readlines()

        keys_set = set()
        new_lines = []
        for line in existing_lines:
            stripped = line.strip()
            if "=" in stripped and not stripped.startswith("#"):
                k, _ = stripped.split("=", 1)
                k = k.strip()
                if k in config_dict:
                    new_lines.append(f"{k}={config_dict[k]}\n")
                    keys_set.add(k)
                    continue
            new_lines.append(line)

        for k, v in config_dict.items():
            if k not in keys_set:
                new_lines.append(f"{k}={v}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        return str(env_path)


def run_setup_wizard(console: Optional[Console] = None) -> bool:
    """
    Runs the interactive CLI setup wizard.
    Prompts user for provider, API keys / model names, runs live verification test,
    and saves settings.
    """
    if console is None:
        console = Console()

    console.print()
    banner_text = (
        "[bold cyan]🧠 Welcome to DevMind — Codebase Memory & Intelligence Engine[/bold cyan]\n"
        "[dim]Let's configure your AI provider in 30 seconds. Works with free cloud tiers or 100% offline local models.[/dim]"
    )
    console.print(Panel(banner_text, border_style="magenta", padding=(1, 2)))
    console.print()

    # 1. Provider Menu
    menu_table = Table(show_header=False, box=None, padding=(0, 2))
    menu_table.add_column("Key", style="bold green", width=5)
    menu_table.add_column("Provider", style="white")
    menu_table.add_column("Description", style="dim")

    menu_table.add_row("[1]", "⚡ Groq", "Ultra-fast, 100% free tier available (Recommended)")
    menu_table.add_row("[2]", "♊ Google Gemini", "Generous free tier (Gemini 2.0 Flash)")
    menu_table.add_row("[3]", "🟣 Anthropic Claude", "Claude 3.5 Sonnet, Claude 3.7, Claude Haiku")
    menu_table.add_row("[4]", "🟢 OpenAI", "GPT-4o, GPT-4o-mini, o3-mini")
    menu_table.add_row("[5]", "🦙 Ollama", "100% Local, private, zero internet needed")
    menu_table.add_row("[6]", "🌐 OpenRouter", "Access 100+ models with one API key")
    menu_table.add_row("[7]", "⚙️  Custom Endpoint", "LocalAI, vLLM, LMStudio (OpenAI-compatible)")

    console.print("[bold]Select your AI model provider:[/bold]")
    console.print(menu_table)
    console.print()

    choice = Prompt.ask(
        "[bold cyan]Enter choice[/bold cyan]",
        choices=["1", "2", "3", "4", "5", "6", "7"],
        default="1"
    )

    config_to_save: Dict[str, Any] = {}
    provider_id = "groq"
    api_key = ""
    model = ""
    base_url = ""

    # ── 1. Groq ──────────────────────────────────────────────────────────────
    if choice == "1":
        provider_id = "groq"
        console.print("\n[dim]Get your free Groq API key at: https://console.groq.com/keys[/dim]")
        api_key = Prompt.ask("[bold green]Enter your Groq API Key[/bold green]", password=True).strip()
        model = "groq/llama-3.3-70b-versatile"
        config_to_save = {
            "LLM_PROVIDER": "groq",
            "GROQ_API_KEY": api_key,
            "LLM_MODEL": model
        }

    # ── 2. Google Gemini ──────────────────────────────────────────────────────
    elif choice == "2":
        provider_id = "gemini"
        console.print("\n[dim]Get your free Gemini API key at: https://aistudio.google.com/app/apikey[/dim]")
        api_key = Prompt.ask("[bold green]Enter your Google Gemini API Key[/bold green]", password=True).strip()
        model = "gemini/gemini-2.0-flash"
        config_to_save = {
            "LLM_PROVIDER": "gemini",
            "GEMINI_API_KEY": api_key,
            "LLM_MODEL": model
        }

    # ── 3. Anthropic Claude ───────────────────────────────────────────────────
    elif choice == "3":
        provider_id = "anthropic"
        console.print("\n[dim]Get your Anthropic key at: https://console.anthropic.com/settings/keys[/dim]")
        api_key = Prompt.ask("[bold green]Enter your Anthropic API Key[/bold green]", password=True).strip()
        model_choice = Prompt.ask(
            "Select Claude Model",
            choices=["claude-3-5-sonnet", "claude-3-5-haiku", "claude-3-7-sonnet"],
            default="claude-3-5-sonnet"
        )
        model_mapping = {
            "claude-3-5-sonnet": "anthropic/claude-3-5-sonnet-20241022",
            "claude-3-5-haiku": "anthropic/claude-3-5-haiku-20241022",
            "claude-3-7-sonnet": "anthropic/claude-3-7-sonnet-20250219"
        }
        model = model_mapping[model_choice]
        config_to_save = {
            "LLM_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": api_key,
            "LLM_MODEL": model
        }

    # ── 4. OpenAI ─────────────────────────────────────────────────────────────
    elif choice == "4":
        provider_id = "openai"
        console.print("\n[dim]Get your OpenAI API key at: https://platform.openai.com/api-keys[/dim]")
        api_key = Prompt.ask("[bold green]Enter your OpenAI API Key[/bold green]", password=True).strip()
        model_choice = Prompt.ask(
            "Select OpenAI Model",
            choices=["gpt-4o-mini", "gpt-4o", "o3-mini"],
            default="gpt-4o-mini"
        )
        model = f"openai/{model_choice}"
        config_to_save = {
            "LLM_PROVIDER": "openai",
            "OPENAI_API_KEY": api_key,
            "LLM_MODEL": model
        }

    # ── 5. Ollama ─────────────────────────────────────────────────────────────
    elif choice == "5":
        provider_id = "ollama"
        console.print("\n[dim]Ensure Ollama is running locally ('ollama serve').[/dim]")
        base_url = Prompt.ask("Enter Ollama base URL", default="http://localhost:11434").strip()
        model_name = Prompt.ask("Enter local model name (e.g. llama3.2, qwen2.5-coder, mistral)", default="llama3.2").strip()
        model = f"ollama/{model_name}"
        config_to_save = {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_BASE_URL": base_url,
            "OLLAMA_MODEL": model_name,
            "LLM_MODEL": model
        }

    # ── 6. OpenRouter ─────────────────────────────────────────────────────────
    elif choice == "6":
        provider_id = "openrouter"
        console.print("\n[dim]Get your OpenRouter key at: https://openrouter.ai/keys[/dim]")
        api_key = Prompt.ask("[bold green]Enter your OpenRouter API Key[/bold green]", password=True).strip()
        model = Prompt.ask(
            "Enter OpenRouter model ID",
            default="openrouter/meta-llama/llama-3.3-70b-instruct"
        ).strip()
        config_to_save = {
            "LLM_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": api_key,
            "LLM_MODEL": model
        }

    # ── 7. Custom Endpoint ────────────────────────────────────────────────────
    elif choice == "7":
        provider_id = "custom"
        base_url = Prompt.ask("Enter custom base URL (e.g. http://localhost:8080/v1)").strip()
        api_key = Prompt.ask("Enter API Key (optional, press Enter if none)", password=True, default="").strip()
        model = Prompt.ask("Enter model name (e.g. local-model)", default="local-model").strip()
        config_to_save = {
            "LLM_PROVIDER": "custom",
            "OPENAI_BASE_URL": base_url,
            "OPENAI_API_KEY": api_key or "EMPTY",
            "LLM_MODEL": model
        }

    # 2. Live Verification Ping
    console.print()
    with console.status(f"[bold cyan]Testing connection to {provider_id.upper()}...[/bold cyan]", spinner="dots"):
        success, msg = verify_provider_connection(
            provider_id=provider_id,
            api_key=api_key,
            model=model,
            base_url=base_url
        )

    if success:
        console.print(f"[bold green]✅ Connection verified successfully![/bold green] [dim]({msg})[/dim]")
    else:
        console.print(f"[bold yellow]⚠️  Verification warning:[/bold yellow] {msg}")
        save_anyway = Confirm.ask("Would you like to save this configuration anyway?", default=True)
        if not save_anyway:
            console.print("[dim]Setup cancelled.[/dim]")
            return False

    # 3. Save Scope Selection
    console.print()
    scope_choice = Prompt.ask(
        "Where would you like to save this configuration?",
        choices=["1", "2"],
        default="1"
    )
    global_scope = (scope_choice == "1")

    saved_path = save_configuration(config_to_save, global_scope=global_scope)

    # Cascading into current process env
    for k, v in config_to_save.items():
        os.environ[k] = str(v)

    console.print()
    scope_label = "Globally (applies to all repositories)" if global_scope else "Locally (current repository .env)"
    success_card = (
        f"[bold green]✨ Configuration Saved Successfully![/bold green]\n\n"
        f"  [bold]Provider:[/bold]  {config_to_save.get('LLM_PROVIDER')}\n"
        f"  [bold]Model:[/bold]     {config_to_save.get('LLM_MODEL')}\n"
        f"  [bold]Scope:[/bold]     {scope_label}\n"
        f"  [bold]Saved to:[/bold]  [cyan]{saved_path}[/cyan]\n\n"
        f"[dim]You are ready to use DevMind! Run 'devmind ask \"How does auth work?\"' or 'devmind health'.[/dim]"
    )
    console.print(Panel(success_card, border_style="green", padding=(1, 2)))
    return True


def ensure_configured(console: Optional[Console] = None) -> bool:
    """
    Checks if an LLM provider is configured.
    If not, prompts the user to launch the interactive setup wizard immediately.
    """
    if is_any_provider_configured():
        return True

    if console is None:
        console = Console()

    console.print()
    console.print(
        "[bold yellow]💡 No AI model provider configured yet.[/bold yellow]\n"
        "[dim]DevMind needs an AI provider (Free Groq/Gemini, Claude, OpenAI, or 100% Offline Ollama) to answer queries.[/dim]"
    )
    should_init = Confirm.ask("\nWould you like to set up your provider now? (takes 30 seconds)", default=True)
    if should_init:
        return run_setup_wizard(console=console)
    else:
        console.print("[dim]Skipping setup. Note: Q&A and semantic chat require an active provider.[/dim]")
        return False
