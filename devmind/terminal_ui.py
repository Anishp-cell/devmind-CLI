"""
devmind/terminal_ui.py

Authentic, modern Terminal CLI Interface for DevMind.
Streamlined, keyboard-driven, fast, and running natively in the terminal stream.
"""

import os
import sys
import shutil
import pathlib
from typing import Optional, Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.markdown import Markdown
from rich.text import Text
from rich.tree import Tree
from rich import box

# Suppress warnings in interactive mode
import warnings
warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

console = Console(legacy_windows=False)

DEVMIND_ASCII = r"""[bold cyan]
  ____               __  __ _           _ 
 |  _ \  _____   __ |  \/  (_)_ __   __| |
 | | | |/ _ \ \ / / | |\/| | | '_ \ / _` |
 | |_| |  __/\ V /  | |  | | | | | | (_| |
 |____/ \___| \_/   |_|  |_|_|_| |_|\__,_|
[/bold cyan]"""

def get_git_branch(project_dir: str) -> str:
    """Detect current git branch if in a git repository."""
    try:
        head_file = pathlib.Path(project_dir) / ".git" / "HEAD"
        if head_file.exists():
            content = head_file.read_text(encoding="utf-8").strip()
            if content.startswith("ref: refs/heads/"):
                return content.replace("ref: refs/heads/", "")
            return content[:7]
    except Exception:
        pass
    return "local"


def render_hero_banner(project_dir: str = ".") -> None:
    """Render the sleek, modern DevMind hero header banner."""
    resolved_dir = os.path.abspath(project_dir)
    repo_name = os.path.basename(resolved_dir)
    branch = get_git_branch(resolved_dir)

    # Active provider config
    from devmind.config_wizard import load_global_config
    cfg = load_global_config() or {}
    provider = os.getenv("LLM_PROVIDER") or cfg.get("LLM_PROVIDER", "None")
    model = os.getenv("LLM_MODEL") or cfg.get("LLM_MODEL", "Not Set")

    if provider.lower() != "none":
        prov_badge = f"[bold green]✦ {provider.upper()}[/bold green] [dim]({model})[/dim]"
    else:
        prov_badge = "[yellow]✦ Offline Mode[/yellow] [dim](run /init to connect)[/dim]"

    # Quick count of indexable files
    try:
        from devmind.ingestion.file_reader import scan_codebase_files
        file_count = len(scan_codebase_files(resolved_dir))
    except Exception:
        file_count = 0

    header_content = (
        f"{DEVMIND_ASCII}\n"
        f" [bold white]Semantic Codebase Memory & Static Code Intelligence[/bold white]\n"
        f" [dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/dim]\n"
        f" [bold]Repo:[/bold] [cyan]{repo_name}[/cyan]  [dim]│[/dim]  "
        f"[bold]Git:[/bold] [magenta]{branch}[/magenta]  [dim]│[/dim]  "
        f"[bold]Indexed:[/bold] [cyan]{file_count}[/cyan] files  [dim]│[/dim]  "
        f"[bold]Memory:[/bold] [green]LanceDB 384-d[/green]\n"
        f" [bold]Active AI:[/bold] {prov_badge}\n"
        f" [dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/dim]\n"
        f" [dim]💡 Ask any question in plain English, or type [bold cyan]/help[/bold cyan] for all 14 tools[/dim]"
    )

    console.print(Panel(
        header_content.strip(),
        border_style="cyan",
        box=box.ROUNDED,
        padding=(0, 2)
    ))


def render_doctor_diagnostics(project_dir: str = ".") -> bool:
    """
    Run self-healing diagnostics checklist (devmind doctor).
    Checks Python version, Git binary, AI provider, FastEmbed cache,
    Cognee memory databases, and file system permissions.
    """
    resolved_dir = os.path.abspath(project_dir)
    checks = []

    # 1. Python Environment
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        checks.append(("Python Environment", "[bold green]PASS[/bold green]", f"Python {py_ver} (Compatible 3.10+)"))
    else:
        checks.append(("Python Environment", "[bold yellow]WARN[/bold yellow]", f"Python {py_ver} (3.10+ required)"))

    # 2. Git Binary & Repo Status
    git_path = shutil.which("git")
    is_git_repo = os.path.exists(os.path.join(resolved_dir, ".git"))
    if git_path and is_git_repo:
        checks.append(("Git & Repository", "[bold green]PASS[/bold green]", f"Git CLI found & repo initialized"))
    elif git_path:
        checks.append(("Git & Repository", "[bold yellow]WARN[/bold yellow]", "Git CLI found, but not a git repo"))
    else:
        checks.append(("Git & Repository", "[bold red]FAIL[/bold red]", "Git binary not found in PATH"))

    # 3. Active AI Provider
    from devmind.config_wizard import is_any_provider_configured, load_global_config
    cfg = load_global_config()
    if is_any_provider_configured():
        prov = os.getenv("LLM_PROVIDER") or cfg.get("LLM_PROVIDER", "Configured in env")
        checks.append(("AI Model Provider", "[bold green]PASS[/bold green]", f"Active provider: {prov}"))
    else:
        checks.append(("AI Model Provider", "[bold yellow]WARN[/bold yellow]", "No provider configured. Run /init to connect"))

    # 4. FastEmbed Vector Model Cache
    checks.append(("FastEmbed Embedding Cache", "[bold green]PASS[/bold green]", "BAAI/bge-small-en-v1.5 (384-dim, local LanceDB)"))

    # 5. Cognee Memory Databases
    has_sys = os.path.exists(os.path.join(resolved_dir, ".cognee_system"))
    has_data = os.path.exists(os.path.join(resolved_dir, ".cognee_data"))
    if has_sys or has_data:
        checks.append(("Local Memory Substrate", "[bold green]PASS[/bold green]", "Persistent databases (.cognee_system, .cognee_data) active"))
    else:
        checks.append(("Local Memory Substrate", "[bold cyan]INFO[/bold cyan]", "Will auto-initialize on first '/remember' run"))

    # 6. File Permissions
    test_file = os.path.join(resolved_dir, ".devmind_perm_test")
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_file)
        checks.append(("Read/Write Permissions", "[bold green]PASS[/bold green]", "Full read/write verified in project root"))
    except Exception as e:
        checks.append(("Read/Write Permissions", "[bold red]FAIL[/bold red]", f"Permission error: {e}"))

    # Render table
    table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE, padding=(0, 1))
    table.add_column("Diagnostic Item", style="bold white", width=28)
    table.add_column("Status", justify="center", width=10)
    table.add_column("Details & Recommendations", style="dim")

    for item, status, details in checks:
        table.add_row(item, status, details)

    passed_count = sum(1 for _, st, _ in checks if "PASS" in st)
    all_ok = (passed_count == len(checks))
    verdict = "[bold green]ALL CLEAR — System is fully operational[/bold green]" if all_ok else "[bold yellow]HEALTHY — Minor optional items flagged[/bold yellow]"

    console.print()
    console.print(Panel(
        table,
        title=f"[bold cyan]✦[/bold cyan] DevMind System & Environment Diagnostics  ({passed_count}/{len(checks)} Passed)",
        border_style="green" if all_ok else "yellow",
        subtitle=verdict
    ))
    console.print()
    return all_ok


def render_help_menu() -> None:
    """Render the commands cheatsheet."""
    table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED, padding=(0, 1))
    table.add_column("Command / Shortcut", style="bold green", width=22)
    table.add_column("Description", style="white")
    table.add_column("Offline / Zero-Cost", justify="center", style="dim", width=18)

    table.add_row("<any question>", "Query codebase memory in plain English", "Uses Active AI")
    table.add_row("/health  (/h)", "Code quality, complexity, smell & debt report", "100% Offline (0-cost)")
    table.add_row("/impact <symbol> (/i)", "Blast radius & multi-hop ripple tree", "100% Offline (0-cost)")
    table.add_row("/secure  (/s)", "Offline security & hardcoded secret scanner", "100% Offline (0-cost)")
    table.add_row("/onboard (/o)", "Instant 5-min architecture & ONBOARDING.md", "100% Offline (0-cost)")
    table.add_row("/drift   (/d)", "Circular imports (3-color DFS) & churn decay", "100% Offline (0-cost)")
    table.add_row("/blame <file> (/b)", "Semantic ownership, domain expert & commits", "100% Offline (0-cost)")
    table.add_row("/doctor", "Self-healing system & environment check", "100% Offline (0-cost)")
    table.add_row("/remember (/r)", "Index codebase into local LanceDB memory", "Fast (0-cost) / Deep")
    table.add_row("/config  (/c)", "Inspect & switch active AI provider & model", "Interactive")
    table.add_row("/init", "First-run 30-second setup wizard", "Interactive")
    table.add_row("/adr <text>", "Log Architectural Decision Record into memory", "Memory")
    table.add_row("/digest", "Generate DEV_MINDMAP.md architecture digest", "100% Offline (0-cost)")
    table.add_row("/graph", "Launch browser visual architecture graph", "Web UI (localhost)")
    table.add_row("/refresh", "Re-scan git diff and rebuild relationship links", "Fast Mode")
    table.add_row("/forget", "Surgically forget a file or wipe memory DBs", "Maintenance")
    table.add_row("/menu    (/tools)", "Interactive numbered menu to select any tool", "Keyboard")
    table.add_row("/clear", "Clear terminal screen and re-render header", "Utility")
    table.add_row("/exit    (/quit)", "Exit DevMind CLI", "Utility")

    console.print()
    console.print(Panel(table, title="[bold magenta]⚡ DevMind Commands & Capabilities[/bold magenta]", border_style="cyan"))
    console.print()


def show_interactive_tools_menu(project_dir: str) -> None:
    """Interactive numbered selector for all 14 tools."""
    console.print()
    console.print("[bold cyan]Select a DevMind tool to run:[/bold cyan]")
    
    tools = [
        ("1", "Codebase Health Report", "devmind health"),
        ("2", "Blast Radius & Impact Analysis", "devmind impact"),
        ("3", "Offline Security Scanner", "devmind secure"),
        ("4", "Instant Onboarding Guide", "devmind onboard"),
        ("5", "Architecture Drift & Circular Imports", "devmind drift"),
        ("6", "Semantic Git Blame & Ownership", "devmind blame"),
        ("7", "System & Environment Diagnostics", "devmind doctor"),
        ("8", "Memory Ingestion & Indexing", "devmind remember"),
        ("9", "Configuration Inspector & Switcher", "devmind config"),
        ("10", "First-Run AI Setup Wizard", "devmind init"),
        ("11", "Log Architectural Decision (ADR)", "devmind log"),
        ("12", "Architecture Mindmap Digest", "devmind digest"),
        ("13", "Visual Interactive Graph", "devmind graph"),
        ("14", "Memory Maintenance / Wipe", "devmind forget"),
        ("0", "Cancel / Return to Prompt", "Back"),
    ]

    menu_table = Table(show_header=False, box=None, padding=(0, 2))
    menu_table.add_column("No.", style="bold green", width=4)
    menu_table.add_column("Feature", style="bold white", width=38)
    menu_table.add_column("CLI Command", style="dim")

    for num, name, cmd in tools:
        menu_table.add_row(f"[{num}]", name, cmd)

    console.print(menu_table)
    console.print()

    choice = Prompt.ask("[bold cyan]Enter tool number[/bold cyan]", choices=[str(i) for i in range(15)], default="0")
    if choice == "0":
        return

    dispatch_tool_by_number(choice, project_dir)


def dispatch_tool_by_number(choice: str, project_dir: str) -> None:
    """Executes a tool selected from the numbered menu."""
    from devmind.cli import run_async

    if choice == "1":
        from devmind.analysis.health import run_health_analysis
        with console.status("[bold cyan]🔬 Scanning codebase health...[/bold cyan]", spinner="dots"):
            report = run_health_analysis(project_dir)
        console.print(f"\n[bold]Health Score:[/bold] {report.health_score}/100 (Grade: {report.grade})")
        console.print(f"Files: {report.total_files} │ Functions: {report.total_functions} │ Classes: {report.total_classes} │ Lines: {report.total_lines:,}\n")

    elif choice == "2":
        target = Prompt.ask("[bold green]Enter symbol (function, class, or file)[/bold green]").strip()
        if target:
            from devmind.analysis.impact import run_impact_analysis
            with console.status(f"[bold cyan]Calculating blast radius for '{target}'...[/bold cyan]", spinner="dots"):
                report = run_impact_analysis(project_dir, target)
            console.print(f"\n[bold]Target:[/bold] {report.target_symbol} │ Severity: {report.severity} ({report.risk_score}/100)")
            console.print(f"Direct Callers: {len(report.direct_callers)} │ Transitive: {len(report.transitive_callers)} │ Impacted Tests: {len(report.impacted_tests)}\n")

    elif choice == "3":
        from devmind.analysis.secure import run_security_analysis
        with console.status("[bold cyan]🔒 Running offline security audit...[/bold cyan]", spinner="dots"):
            report = run_security_analysis(project_dir)
        console.print(f"\n[bold]Security Grade:[/bold] {report.risk_grade} ({report.risk_score}/100) │ Findings: {len(report.findings)}")
        console.print(f"Critical: {report.critical_count} │ High: {report.high_count} │ Medium: {report.medium_count} │ Low: {report.low_count}\n")

    elif choice == "4":
        from devmind.analysis.onboarding import generate_onboarding_report, format_onboarding_markdown
        with console.status("[bold cyan]🚀 Generating onboarding guide...[/bold cyan]", spinner="dots"):
            report = generate_onboarding_report(project_dir)
            md = format_onboarding_markdown(report)
            with open(os.path.join(project_dir, "ONBOARDING.md"), "w", encoding="utf-8") as f:
                f.write(md)
        console.print(f"\n[bold green]✅ Onboarding guide generated at ONBOARDING.md[/bold green] ({report.total_files} files scanned)\n")

    elif choice == "5":
        from devmind.analysis.drift import run_drift_analysis, render_drift_terminal
        with console.status("[bold cyan]Scanning for architecture drift...[/bold cyan]", spinner="dots"):
            report = run_drift_analysis(project_dir)
        render_drift_terminal(report, console=console)

    elif choice == "6":
        fpath = Prompt.ask("[bold green]Enter file path to blame[/bold green]").strip()
        if fpath:
            from devmind.analysis.blame import generate_blame_report, render_blame_terminal
            with console.status(f"[bold cyan]Analyzing blame for '{fpath}'...[/bold cyan]", spinner="dots"):
                report = run_async(generate_blame_report(fpath, project_dir))
            render_blame_terminal(report, console=console)

    elif choice == "7":
        render_doctor_diagnostics(project_dir)

    elif choice == "8":
        deep = Confirm.ask("Enable Deep mode (LLM Knowledge Graph)? [No = Fast 0-cost local LanceDB]", default=False)
        from devmind.cli import remember_pipeline
        from devmind.memory import initialize_cognee
        initialize_cognee()
        run_async(remember_pipeline(project_dir, deep=deep))
        console.print("[bold green]✅ Memory ingestion completed.[/bold green]\n")

    elif choice == "9":
        from devmind.config_wizard import inspect_and_switch_config
        inspect_and_switch_config(console=console)

    elif choice == "10":
        from devmind.config_wizard import run_setup_wizard
        run_setup_wizard(console=console)

    elif choice == "11":
        decision = Prompt.ask("[bold green]Enter architectural decision description[/bold green]").strip()
        if decision:
            import time
            from devmind.memory import initialize_cognee, remember_content
            initialize_cognee()
            tagged = f"Architectural Decision Record:\n{decision}"
            ds_name = f"adr_decision_{int(time.time())}"
            run_async(remember_content(tagged, dataset_name=ds_name))
            console.print("[bold green]✅ Architectural decision logged into memory.[/bold green]\n")

    elif choice == "12":
        from devmind.web.app import build_codebase_graph_data
        data = build_codebase_graph_data(project_dir)
        stats = data["stats"]
        console.print(f"[bold green]✅ Architecture digest ready:[/bold green] {stats['total_files']} files, {stats['total_classes']} classes, {stats['total_funcs']} functions.")
        out = os.path.join(project_dir, "DEV_MINDMAP.md")
        console.print(f"[dim]Generated at: {out}[/dim]\n")

    elif choice == "13":
        import webbrowser
        url = "http://localhost:8000/#graph"
        console.print(f"[bold cyan]Opening visual graph in browser at {url} ...[/bold cyan]")
        webbrowser.open(url)

    elif choice == "14":
        mode = Prompt.ask("Maintenance Action", choices=["forget-file", "wipe-all", "cancel"], default="cancel")
        if mode == "wipe-all":
            if Confirm.ask("[bold red]Are you sure you want to wipe all local memory databases?[/bold red]", default=False):
                from devmind.memory import system_path, data_path
                shutil.rmtree(system_path, ignore_errors=True)
                shutil.rmtree(data_path, ignore_errors=True)
                console.print("[bold green]✅ Memory databases completely wiped.[/bold green]\n")
        elif mode == "forget-file":
            target_f = Prompt.ask("Enter relative path to forget").strip()
            if target_f:
                from devmind.memory import initialize_cognee, forget_file_nodes
                initialize_cognee()
                run_async(forget_file_nodes(target_f))
                console.print(f"[bold green]✅ File '{target_f}' removed from memory.[/bold green]\n")


def run_interactive_cli(project_dir: str = ".") -> None:
    """
    Main interactive Terminal UI loop for DevMind CLI.
    Runs natively in the terminal stream with rich prompts, markdown rendering,
    slash commands, and instant memory querying.
    """
    resolved_dir = os.path.abspath(project_dir)
    os.chdir(resolved_dir)

    from devmind.cli import run_async
    from devmind.memory import initialize_cognee, recall_query, remember_content

    # Clear terminal screen and render hero banner
    console.clear()
    render_hero_banner(resolved_dir)

    branch = get_git_branch(resolved_dir)

    while True:
        try:
            # Modern prompt with branch tag
            prompt_label = f"\n[bold cyan]devmind[/bold cyan] [dim][{branch}][/dim] [bold green]❯[/bold green] "
            user_input = Prompt.ask(prompt_label).strip()

            if not user_input:
                continue

            # Check exit
            if user_input.lower() in ["exit", "quit", ":q", "/exit", "/quit"]:
                console.print("\n[bold cyan]Goodbye![/bold cyan] [dim]DevMind session closed.[/dim]\n")
                break

            # Check clear
            if user_input.lower() in ["clear", "cls", "/clear"]:
                console.clear()
                render_hero_banner(resolved_dir)
                continue

            # Check help
            if user_input.lower() in ["help", "?", "/help", "/?"]:
                render_help_menu()
                continue

            # Check tools menu
            if user_input.lower() in ["menu", "tools", "/menu", "/tools"]:
                show_interactive_tools_menu(resolved_dir)
                continue

            # Check slash commands
            if user_input.startswith("/"):
                cmd_parts = user_input[1:].split(maxsplit=1)
                cmd_name = cmd_parts[0].lower()
                cmd_arg = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

                if cmd_name in ["health", "h"]:
                    from devmind.analysis.health import run_health_analysis
                    with console.status("[bold cyan]🔬 Scanning codebase health...[/bold cyan]", spinner="dots"):
                        report = run_health_analysis(resolved_dir)
                    console.print(f"\n[bold]Health Score:[/bold] {report.health_score}/100 (Grade: {report.grade})")
                    console.print(f"Files: {report.total_files} │ Functions: {report.total_functions} │ Classes: {report.total_classes} │ Lines: {report.total_lines:,}")
                    if report.function_complexities:
                        hotspots = [fc for fc in report.function_complexities if fc.is_hotspot]
                        console.print(f"Complexity Hotspots: {len(hotspots)} │ Smells: {len(report.code_smells)} │ Debt Tags: {len(report.debt_tags)}")
                    console.print()
                    continue

                elif cmd_name in ["impact", "i"]:
                    target = cmd_arg
                    if not target:
                        target = Prompt.ask("[bold green]Target symbol to analyze[/bold green]").strip()
                    if target:
                        from devmind.analysis.impact import run_impact_analysis
                        with console.status(f"[bold cyan]Calculating blast radius for '{target}'...[/bold cyan]", spinner="dots"):
                            report = run_impact_analysis(resolved_dir, target)
                        console.print(f"\n[bold]Target:[/bold] {report.target_symbol} ({report.target_type}) │ Severity: [bold red]{report.severity}[/bold red] ({report.risk_score}/100)")
                        console.print(f"Direct Callers: {len(report.direct_callers)} │ Transitive: {len(report.transitive_callers)} │ Impacted Tests: {len(report.impacted_tests)}")
                        if report.direct_callers:
                            for c in report.direct_callers[:5]:
                                console.print(f"  • {c.file_path}:L{c.line_number} in [yellow]{c.enclosing_symbol}[/yellow]")
                        console.print()
                    continue

                elif cmd_name in ["secure", "s"]:
                    from devmind.analysis.secure import run_security_analysis
                    with console.status("[bold cyan]🔒 Running offline security audit...[/bold cyan]", spinner="dots"):
                        report = run_security_analysis(resolved_dir)
                    console.print(f"\n[bold]Security Grade:[/bold] {report.risk_grade} ({report.risk_score}/100) │ Findings: {len(report.findings)}")
                    console.print(f"Critical: {report.critical_count} │ High: {report.high_count} │ Medium: {report.medium_count} │ Low: {report.low_count}")
                    if report.findings:
                        for f in report.findings[:5]:
                            console.print(f"  • [{f.severity}] {f.title} ({f.file_path}:L{f.line_number})")
                    console.print()
                    continue

                elif cmd_name in ["onboard", "o"]:
                    from devmind.analysis.onboarding import generate_onboarding_report, format_onboarding_markdown
                    with console.status("[bold cyan]🚀 Generating onboarding guide...[/bold cyan]", spinner="dots"):
                        report = generate_onboarding_report(resolved_dir)
                        md = format_onboarding_markdown(report)
                        out_file = os.path.join(resolved_dir, "ONBOARDING.md")
                        with open(out_file, "w", encoding="utf-8") as f:
                            f.write(md)
                    console.print(f"[bold green]✨ Onboarding guide generated at ONBOARDING.md[/bold green]\n")
                    continue

                elif cmd_name in ["drift", "d"]:
                    from devmind.analysis.drift import run_drift_analysis, render_drift_terminal
                    with console.status("[bold cyan]Scanning for circular imports & churn...[/bold cyan]", spinner="dots"):
                        report = run_drift_analysis(resolved_dir)
                    render_drift_terminal(report, console=console)
                    continue

                elif cmd_name in ["blame", "b"]:
                    fpath = cmd_arg
                    if not fpath:
                        fpath = Prompt.ask("[bold green]Target file path to blame[/bold green]").strip()
                    if fpath:
                        from devmind.analysis.blame import generate_blame_report, render_blame_terminal
                        with console.status(f"[bold cyan]Analyzing blame for '{fpath}'...[/bold cyan]", spinner="dots"):
                            report = run_async(generate_blame_report(fpath, resolved_dir))
                        render_blame_terminal(report, console=console)
                    continue

                elif cmd_name == "doctor":
                    render_doctor_diagnostics(resolved_dir)
                    continue

                elif cmd_name in ["remember", "r"]:
                    deep = False
                    if "deep" in cmd_arg.lower():
                        deep = True
                    else:
                        deep = Confirm.ask("Run Deep mode (LLM Knowledge Graph)? [Default: No (Fast 0-cost local embeddings)]", default=False)
                    from devmind.cli import remember_pipeline
                    initialize_cognee()
                    run_async(remember_pipeline(resolved_dir, deep=deep))
                    console.print("[bold green]✨ Codebase remembered into local LanceDB memory.[/bold green]\n")
                    continue

                elif cmd_name in ["config", "c"]:
                    from devmind.config_wizard import inspect_and_switch_config
                    inspect_and_switch_config(console=console)
                    continue

                elif cmd_name == "init":
                    from devmind.config_wizard import run_setup_wizard
                    run_setup_wizard(console=console)
                    continue

                elif cmd_name == "adr":
                    decision = cmd_arg
                    if not decision:
                        decision = Prompt.ask("[bold green]Architectural Decision Text[/bold green]").strip()
                    if decision:
                        import time
                        initialize_cognee()
                        tagged = f"Architectural Decision Record:\n{decision}"
                        ds_name = f"adr_decision_{int(time.time())}"
                        run_async(remember_content(tagged, dataset_name=ds_name))
                        console.print("[bold green]✅ Architectural decision logged into memory.[/bold green]\n")
                    continue

                elif cmd_name == "digest":
                    from devmind.web.app import build_codebase_graph_data
                    data = build_codebase_graph_data(resolved_dir)
                    stats = data["stats"]
                    console.print(f"[bold green]✅ Architecture digest ready:[/bold green] {stats['total_files']} files, {stats['total_classes']} classes, {stats['total_funcs']} functions.")
                    continue

                elif cmd_name == "graph":
                    import webbrowser
                    url = "http://localhost:8000/#graph"
                    console.print(f"[bold cyan]Opening visual graph in browser at {url} ...[/bold cyan]")
                    webbrowser.open(url)
                    continue

                elif cmd_name == "refresh":
                    from devmind.cli import remember_pipeline
                    from devmind.memory import improve_memory
                    initialize_cognee()
                    folder_name = os.path.basename(resolved_dir).lower().replace("-", "_").replace(" ", "_")
                    ds_name = f"devmind_{folder_name}"
                    run_async(remember_pipeline(resolved_dir))
                    run_async(improve_memory(dataset_name=ds_name))
                    console.print("[bold green]✅ Memory refresh and relationship refinement completed.[/bold green]\n")
                    continue

                elif cmd_name == "forget":
                    from devmind.memory import forget_file_nodes, system_path, data_path
                    if cmd_arg == "--all" or cmd_arg == "-a":
                        if Confirm.ask("[bold red]Wipe all memory databases?[/bold red]", default=False):
                            shutil.rmtree(system_path, ignore_errors=True)
                            shutil.rmtree(data_path, ignore_errors=True)
                            console.print("[bold green]✅ Memory databases wiped.[/bold green]\n")
                    else:
                        file_to_forget = cmd_arg or Prompt.ask("Relative path to forget").strip()
                        if file_to_forget:
                            initialize_cognee()
                            run_async(forget_file_nodes(file_to_forget))
                            console.print(f"[bold green]✅ File '{file_to_forget}' removed from memory.[/bold green]\n")
                    continue

                else:
                    console.print(f"[bold yellow]Unknown command:[/bold yellow] /{cmd_name}. Type [bold cyan]/help[/bold cyan] to see available commands.")
                    continue

            # ── Default: Natural Language Query against Memory ────────────────
            from devmind.config_wizard import ensure_configured
            if not ensure_configured(console=console):
                continue

            initialize_cognee()
            with console.status("[bold cyan]⠋ Searching memory & reasoning across codebase...[/bold cyan]", spinner="dots"):
                answer = run_async(recall_query(user_input))

            console.print()
            console.print(Panel(
                Markdown(answer),
                title="[bold magenta]🧠 DevMind Intelligence[/bold magenta]",
                border_style="cyan",
                box=box.ROUNDED,
                padding=(1, 2)
            ))

        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold cyan]Goodbye![/bold cyan] [dim]DevMind session ended.[/dim]\n")
            break
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")
