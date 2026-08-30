# pyrefly: ignore [missing-import]
import typer
import sys
import asyncio
import os
import logging
import warnings
import pathlib
from typing import Optional

# Suppress ResourceWarning and DeprecationWarning from aiohttp/asyncio during garbage collection
warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Suppress Windows proactor event loop SSL bugs during shutdown
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from devmind.memory import initialize_cognee, remember_content, recall_query, improve_memory, forget_memory, forget_file_nodes, get_project_root
from devmind.ingestion.file_reader import scan_codebase_files
from devmind.ingestion.git_parser import get_git_history, get_changed_files_git_diff, is_git_repo
from devmind.ingestion.comment_extractor import get_codebase_comments
from devmind.version_checker import show_update_notification
import atexit

# Register background version update checker to notify user upon exit if an update is available
atexit.register(show_update_notification)

# Default to WARNING so stdout stays clean for Rich UI output; `--debug`
# escalates this to DEBUG for full trace visibility.
logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("devmind.cli")

def run_async(coro):
    """
    Custom asyncio runner that:
    1. Cancels pending background tasks (Cognee telemetry fire-and-forget)
    2. Explicitly closes Cognee's singleton aiohttp.ClientSession
    3. Suppresses stderr during cleanup to silence any remaining aiohttp warnings
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    def silence_exceptions(loop, context):
        exc = context.get("exception")
        msg = context.get("message", "")
        # Swallow Win32 10038/not-a-socket/Event loop is closed/telemetry warnings during exit
        if (exc and ("Event loop is closed" in str(exc) or "10038" in str(exc) or "socket" in str(exc))) or "Event loop is closed" in msg or "SSL transport" in msg:
            return
        loop.default_exception_handler(context)
        
    loop.set_exception_handler(silence_exceptions)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            # Cancel all pending background tasks (telemetry, etc.)
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

            # Explicitly close Cognee's singleton telemetry aiohttp session
            # This prevents "Unclosed client session" / "Unclosed connector" stderr dumps
            try:
                from cognee.shared.utils import _telemetry_session
                if _telemetry_session is not None and not _telemetry_session.closed:
                    loop.run_until_complete(_telemetry_session.close())
            except Exception:
                pass

            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass

        # Suppress any remaining stderr output during GC/loop teardown
        import io
        _real_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            loop.close()
        finally:
            sys.stderr = _real_stderr


app = typer.Typer(
    name="devmind",
    help="DevMind – Codebase Memory for Developers. Powered by Cognee.",
    add_completion=False
)

def _version_callback(value: bool):
    if value:
        from devmind import __version__
        typer.echo(f"devmind-cli v{__version__}")
        raise typer.Exit()

@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", "-v",
        callback=_version_callback, is_eager=True,
        help="Show the DevMind CLI version and exit."
    ),
    debug: bool = typer.Option(
        False, "--debug",
        help="Enable verbose debug logging output."
    )
):
    """DevMind – Codebase Memory for Developers. Powered by Cognee."""
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s", force=True)
    logging.getLogger("devmind").setLevel(level)

async def remember_pipeline(directory: str, incremental: bool = False, deep: bool = False):
    """
    Core async pipeline for scanning files, comments, and git logs,
    and loading them into Cognee.

    Args:
        deep: If True, runs cognee.cognify() after add() to build a
              full LLM-extracted knowledge graph. Default is False
              (fast mode: local embeddings only, 0 API calls).
    """
    # Determine a single, unified dataset name based on the target folder
    folder_name = os.path.basename(os.path.abspath(directory)).lower().replace("-", "_").replace(" ", "_")
    dataset_name = f"devmind_{folder_name}"

    mode_label = "deep (LLM graph extraction)" if deep else "fast (local embeddings only)"

    # 1. Scan the codebase files
    files = scan_codebase_files(directory)
    if not files:
        typer.echo("No files found to ingest.")
        return

    if incremental:
        if not is_git_repo(directory):
            typer.echo(
                "[Warning] Incremental mode requires a git repository, but none was found here.\n"
                "Run 'git init' first, or drop --incremental to do a full scan."
            )
            return
        changed_paths = get_changed_files_git_diff(directory)
        if changed_paths:
            files = [f for f in files if f["relative_path"].replace("\\", "/") in changed_paths]
            typer.echo(f"Incremental mode: Filtered to {len(files)} changed file(s).")
        else:
            typer.echo("Incremental mode: No changed files detected via git diff.")
            return

    typer.echo(f"Ingesting {len(files)} files into Cognee memory (Dataset: {dataset_name}) [{mode_label}]...")
    
    # Ingest file contents in a single batch
    contents = []
    for idx, file_data in enumerate(files, start=1):
        rel_path = file_data["relative_path"]
        content = file_data["content"]
        ast_summary = file_data.get("ast_summary", "")
        
        tagged_content = f"File Path: {rel_path}\n{ast_summary}\n---\n{content}"
        contents.append(tagged_content)
        
    logger.info(f"Batched {len(contents)} files. Triggering ingestion pipeline...")
    success = await remember_content(contents, dataset_name=dataset_name, deep=deep)
    if success:
        typer.echo(f"Successfully remembered {len(files)} files.")
    else:
        typer.echo(f"[Warning] Failed to ingest files.")

    # 2. Extract and Ingest Git History
    git_logs = get_git_history(directory, max_commits=20)
    if git_logs:
        typer.echo("Ingesting combined git history into Cognee...")
        combined_git = "\n\n---\n\n".join(git_logs)
        success = await remember_content(combined_git, dataset_name=dataset_name, deep=deep)
        if success:
            typer.echo("Successfully remembered git history.")
        else:
            typer.echo("[Warning] Failed to ingest git history.")

    # 3. Extract and Ingest Inline Comments & Docstrings
    relative_paths = [f["relative_path"] for f in files]
    comments = get_codebase_comments(directory, relative_paths)
    if comments:
        typer.echo("Ingesting combined inline comments into Cognee...")
        combined_comments = "\n\n---\n\n".join(comments)
        success = await remember_content(combined_comments, dataset_name=dataset_name, deep=deep)
        if success:
            typer.echo("Successfully remembered code comments.")
        else:
            typer.echo("[Warning] Failed to ingest code comments.")

@app.command()
def remember(
    directory: str = typer.Option(
        ".", 
        "--dir", "-d", 
        help="The directory of the codebase to ingest."
    ),
    incremental: bool = typer.Option(
        False,
        "--incremental", "-i",
        help="Only scan and ingest files modified or changed in git diff."
    ),
    deep: bool = typer.Option(
        False,
        "--deep",
        help="Run full LLM knowledge-graph extraction (slower, requires API keys). Default: fast local-only mode."
    )
):
    """
    Ingest the codebase files into persistent Cognee memory.

    By default, uses fast local-only mode (0 API calls, instant).
    Use --deep to enable LLM-powered knowledge graph extraction.
    """
    if deep:
        from devmind.config_wizard import ensure_configured
        if not ensure_configured():
            return

    initialize_cognee()
    resolved_dir = get_project_root(directory) if directory == "." else os.path.abspath(directory)
    run_async(remember_pipeline(resolved_dir, incremental=incremental, deep=deep))
    typer.echo("[Success] Codebase memory ingestion completed.")

@app.command()
def init():
    """
    Interactive setup wizard to configure AI model provider (Groq, Gemini, Claude, OpenAI, Ollama, OpenRouter).
    """
    from devmind.config_wizard import run_setup_wizard
    run_setup_wizard()

@app.command()
def config():
    """
    View your active AI model provider, model, and embedding configuration,
    and interactively switch provider, update keys/model, or diff global vs
    local config — without re-entering every setting.
    """
    from devmind.config_wizard import run_config_inspector
    run_config_inspector()

@app.command()
def ask(
    query: str = typer.Argument(..., help="Your natural language question about the codebase.")
):
    """
    Ask a question about the ingested codebase memory in plain English.
    """
    from devmind.config_wizard import ensure_configured
    if not ensure_configured():
        return

    initialize_cognee()
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel

    console = Console()
    with console.status(f"[bold cyan]Searching codebase memory for '[white]{query}[/white]'...[/bold cyan]", spinner="dots"):
        answer = run_async(recall_query(query))
        
    console.print(Panel(
        Markdown(answer),
        title="[bold magenta]DevMind Memory Response[/bold magenta]",
        border_style="cyan",
        padding=(1, 2)
    ))

async def _chat_session_async(console):
    """
    Runs the interactive chat REPL inside a single persistent event loop
    (reused across every query) instead of spinning up a new loop per message.
    """
    from rich.markdown import Markdown
    from rich.prompt import Prompt

    while True:
        try:
            query = Prompt.ask("\n[bold green]You[/bold green]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            return

        if not query.strip():
            continue

        command = query.lower().strip()
        if command in ("exit", "quit", "q"):
            console.print("[dim]Goodbye![/dim]")
            return
        if command == "clear":
            console.clear()
            continue

        try:
            with console.status("[bold cyan]DevMind is thinking...[/bold cyan]", spinner="dots"):
                answer = await recall_query(query)

            console.print("\n[bold magenta]DevMind:[/bold magenta]")
            console.print(Markdown(answer))
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")

@app.command()
def chat():
    """
    Start an interactive DevMind terminal chat session to explore your codebase.
    """
    from devmind.config_wizard import ensure_configured
    if not ensure_configured():
        return

    initialize_cognee()

    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    console.print(Panel.fit(
        "[bold blue]DevMind Codebase Chat[/bold blue]\n"
        "[dim]Type your queries below. Type 'clear' to clear the screen, 'exit'/'quit'/'q' to close.[/dim]",
        border_style="blue"
    ))

    run_async(_chat_session_async(console))

@app.command()
def log(
    decision: str = typer.Argument(..., help="The Architectural Decision Record (ADR) text to log.")
):
    """
    Log an Architectural Decision Record (ADR) into persistent memory.
    """
    initialize_cognee()
    typer.echo(f"Logging decision: '{decision}'...")

    import time
    from devmind.memory import ADR_DATASET_NAME
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    tagged_decision = f"Architectural Decision Record:\nDate: {timestamp}\n{decision}"

    success = run_async(remember_content(tagged_decision, dataset_name=ADR_DATASET_NAME))
    if success:
        typer.echo("[Success] Architectural decision successfully logged.")
    else:
        typer.echo("[Error] Failed to log architectural decision.")

@app.command()
def refresh(
    directory: str = typer.Option(
        ".", 
        "--dir", "-d", 
        help="The directory of the codebase to refresh."
    )
):
    """
    Refresh codebase memory by scanning for changed files and refining relationships.
    """
    initialize_cognee()
    resolved_dir = get_project_root(directory) if directory == "." else os.path.abspath(directory)
    folder_name = os.path.basename(os.path.abspath(resolved_dir)).lower().replace("-", "_").replace(" ", "_")
    dataset_name = f"devmind_{folder_name}"
    
    typer.echo(f"Scanning for codebase changes to refresh memory (Dataset: {dataset_name})...")
    run_async(remember_pipeline(resolved_dir))
    
    typer.echo("Refining the codebase memory graph structure...")
    # Improve memory on the specific folder-based dataset
    success = run_async(improve_memory(dataset_name=dataset_name))
    if success:
        typer.echo("[Success] Memory refresh and relationship refinement completed.")
    else:
        typer.echo("[Warning] File changes re-ingested, but relationship refinement had warnings.")

@app.command()
def forget(
    file_path: str = typer.Option(
        None, 
        "--file", "-f", 
        help="The relative path of the file memory to forget."
    ),
    all_memories: bool = typer.Option(
        False, 
        "--all", "-a", 
        help="Wipe all local memory databases completely."
    )
):
    """
    Surgically forget a specific file's memory, or completely wipe the local databases.
    """
    initialize_cognee()
    
    if all_memories:
        typer.echo("Wiping all local memory databases...")
        import shutil
        from devmind.memory import system_path, data_path
        try:
            if os.path.exists(system_path):
                shutil.rmtree(system_path)
            if os.path.exists(data_path):
                shutil.rmtree(data_path)
            typer.echo("[Success] Local memory databases completely wiped.")
        except Exception as e:
            typer.echo(f"[Error] Failed to wipe memory folders: {e}")
        return
        
    if file_path:
        typer.echo(f"Removing memory nodes for '{file_path}'...")
        success = run_async(forget_file_nodes(file_path))
        if success:
            typer.echo(f"[Success] Memory of '{file_path}' successfully forgotten.")
        else:
            typer.echo(f"[Error] Failed to forget memory of '{file_path}'.")
    else:
        typer.echo("[Warning] Please specify either --file <path> to forget a file, or --all to wipe all databases.")

@app.command()
def dashboard(
    port: int = typer.Option(8000, "--port", "-p", help="Port to run the dashboard server on."),
    directory: str = typer.Option(".", "--dir", "-d", help="The directory of the codebase to target.")
):
    """
    Launch the DevMind Web UI dashboard.
    """
    import uvicorn
    abs_dir = os.path.abspath(directory)
    if not os.path.isdir(abs_dir):
        typer.echo(f"[Error] Directory not found: {abs_dir}")
        raise typer.Exit(code=1)
    os.chdir(abs_dir)
    typer.echo(f"Starting DevMind Web UI Dashboard on http://localhost:{port} targeting '{abs_dir}' ...")
    uvicorn.run("devmind.web.app:app", host="127.0.0.1", port=port, reload=False)

@app.command()
def mcp():
    """
    Start the DevMind MCP server for integration with Claude Code.
    """
    typer.echo("Starting DevMind MCP Server...", err=True)
    initialize_cognee()
    from devmind.integrations.claude_code import mcp as mcp_instance
    mcp_instance.run()

@app.command()
def graph(
    port: int = typer.Option(8000, "--port", "-p", help="Port to run the visual graph dashboard on."),
    directory: str = typer.Option(".", "--dir", "-d", help="The codebase directory to map.")
):
    """
    Launch interactive visual architecture graph in your browser.
    """
    import uvicorn
    import webbrowser
    import socket
    import threading
    import time

    abs_dir = os.path.abspath(directory)
    if not os.path.isdir(abs_dir):
        typer.echo(f"[Error] Directory not found: {abs_dir}")
        raise typer.Exit(code=1)
    os.chdir(abs_dir)
    url = f"http://localhost:{port}/#graph"

    def _open_browser_when_ready():
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    break
            except OSError:
                time.sleep(0.2)
        webbrowser.open(url)

    typer.echo(f"Opening interactive codebase graph at {url} ...")
    threading.Thread(target=_open_browser_when_ready, daemon=True).start()
    uvicorn.run("devmind.web.app:app", host="127.0.0.1", port=port, reload=False)

@app.command()
def digest(
    output: str = typer.Option("DEV_MINDMAP.md", "--output", "-o", help="Output file name for the architecture digest."),
    directory: str = typer.Option(".", "--dir", "-d", help="The directory of the codebase to analyze.")
):
    """
    Generate an instant Markdown architecture mindmap digest of the codebase.
    """
    resolved_dir = get_project_root(directory) if directory == "." else os.path.abspath(directory)
    from devmind.web.app import build_codebase_graph_data
    graph_data = build_codebase_graph_data(resolved_dir)
    stats = graph_data["stats"]
    
    lines = [
        f"# DevMind Codebase Architecture Digest: {os.path.basename(resolved_dir)}",
        "",
        "## High-Level Architecture Metrics",
        f"- **Indexable Files**: {stats['total_files']}",
        f"- **Classes / Data Models**: {stats['total_classes']}",
        f"- **Functions / Methods**: {stats['total_funcs']}",
        f"- **Graph Nodes**: {stats['total_nodes']}",
        f"- **Graph Relationships**: {stats['total_edges']}",
        "",
        "## Codebase Symbol Map",
        ""
    ]
    
    nodes_by_file = {}
    for node in graph_data["nodes"]:
        if node["group"] == "file":
            nodes_by_file[node["path"]] = []
            
    for node in graph_data["nodes"]:
        if node["group"] != "file":
            parts = node["id"].split(":", 2)
            if len(parts) >= 2:
                rel_p = parts[1]
                if rel_p in nodes_by_file:
                    nodes_by_file[rel_p].append(node["label"])
                    
    for file_path, syms in sorted(nodes_by_file.items()):
        lines.append(f"### 📄 `{file_path}`")
        if syms:
            for s in syms:
                lines.append(f"  - {s}")
        else:
            lines.append("  - *(No top-level classes/functions extracted)*")
        lines.append("")
        
    lines.append("---")
    lines.append("*Generated automatically by DevMind CLI (`devmind digest`)*")
    
    out_path = os.path.join(resolved_dir, output)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    typer.echo(f"[Success] Architecture digest generated at '{out_path}'.")

@app.command()
def health(
    directory: str = typer.Option(
        ".",
        "--dir", "-d",
        help="The directory of the codebase to analyse. Defaults to current directory."
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output", "-o",
        help="Write the health report as a Markdown file at this path."
    ),
    threshold: Optional[int] = typer.Option(
        None,
        "--threshold", "-t",
        help="Exit with code 1 if the health score is below this value (useful for CI gates)."
    ),
):
    """
    Scan the codebase and generate a structured health report.

    Analyses cyclomatic complexity, code smells, technical debt tags,
    dead imports, and test coverage gaps — all offline, zero API calls.
    Produces a 0-100 health score with grade (A-F).
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.text import Text
    from rich.columns import Columns
    from devmind.analysis.health import run_health_analysis

    console = Console()

    resolved_dir = get_project_root(directory) if directory == "." else os.path.abspath(directory)

    # ── Run analysis with spinner ─────────────────────────────────────────────
    with console.status(
        "[bold cyan]🔬 Scanning codebase for health issues...[/bold cyan]",
        spinner="dots"
    ):
        report = run_health_analysis(resolved_dir)

    if report.total_files == 0:
        console.print("[bold red]No files found to analyse.[/bold red]")
        raise typer.Exit(code=1)

    # ── Helper: severity colour ───────────────────────────────────────────────
    def sev_icon(count: int, warn_threshold: int = 1, crit_threshold: int = 5) -> str:
        if count == 0:
            return "[bold green]✅[/bold green]"
        if count < crit_threshold:
            return "[bold yellow]⚠️ [/bold yellow]"
        return "[bold red]🔴[/bold red]"

    def grade_colour(grade: str) -> str:
        return {"A": "green", "B": "cyan", "C": "yellow", "D": "orange3", "F": "red"}.get(grade, "white")

    # ── Score bar ─────────────────────────────────────────────────────────────
    score = report.health_score
    grade = report.grade
    bar_filled = int(score / 5)   # 20 blocks total → each = 5 pts
    bar_empty  = 20 - bar_filled
    bar_colour = grade_colour(grade)
    bar_str    = f"[{bar_colour}]{'█' * bar_filled}[/{bar_colour}][dim]{'░' * bar_empty}[/dim]"

    header_text = (
        f"  [bold]Project:[/bold] [cyan]{report.project_name}[/cyan]  "
        f"[dim]│[/dim]  [bold]{report.total_files}[/bold] files  "
        f"[dim]│[/dim]  [bold]{report.total_functions}[/bold] functions  "
        f"[dim]│[/dim]  [bold]{report.total_classes}[/bold] classes  "
        f"[dim]│[/dim]  [bold]{report.total_lines:,}[/bold] lines"
    )

    console.print()
    console.print(Panel(header_text, title="[bold magenta]🧠 DevMind Codebase Health Report[/bold magenta]", border_style="magenta"))
    console.print()
    console.print(
        f"  Health Score   {bar_str}  "
        f"[bold {bar_colour}]{score} / 100[/bold {bar_colour}]   "
        f"Grade: [bold {bar_colour}]{grade}[/bold {bar_colour}]"
    )
    console.print()

    # ── Complexity panel ──────────────────────────────────────────────────────
    hotspots = [fc for fc in report.function_complexities if fc.is_hotspot]
    avg_cc = report.avg_complexity
    cc_icon = sev_icon(len(hotspots), 1, 5)

    comp_table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    comp_table.add_column("Function", style="white", no_wrap=True)
    comp_table.add_column("File", style="dim", no_wrap=True)
    comp_table.add_column("Line", style="dim", justify="right")
    comp_table.add_column("CC", style="bold", justify="right")

    for fc in hotspots[:8]:
        cc_colour = "red" if fc.complexity >= 15 else "yellow"
        comp_table.add_row(
            fc.name,
            fc.file,
            str(fc.line),
            f"[{cc_colour}]{fc.complexity}[/{cc_colour}]",
        )

    top_line = (
        f"{cc_icon} Avg CC: [bold]{avg_cc:.1f}[/bold]   "
        f"Hot spots: [bold]{len(hotspots)}[/bold] / {len(report.function_complexities)} functions"
    )
    if hotspots:
        console.print(Panel(
            Text.from_markup(top_line + "\n") if not hotspots else top_line,
            title="[bold]🔁 Complexity[/bold]",
            border_style="cyan",
        ))
        console.print(comp_table)
        console.print()
    else:
        console.print(Panel(
            top_line,
            title="[bold]🔁 Complexity[/bold]",
            border_style="green",
        ))
        console.print()

    # ── Code smells panel ─────────────────────────────────────────────────────
    smells = report.code_smells
    smell_icon = sev_icon(len(smells), 1, 4)
    god_classes = [s for s in smells if s.kind == "god_class"]
    long_fns    = [s for s in smells if s.kind == "long_function"]
    deep_nests  = [s for s in smells if s.kind == "deep_nesting"]

    smell_table = Table(show_header=False, box=None, padding=(0, 1))
    smell_table.add_column("Icon", width=3)
    smell_table.add_column("Kind", style="yellow")
    smell_table.add_column("Name", style="white")
    smell_table.add_column("Location", style="dim")
    smell_table.add_column("Detail", style="dim")

    for s in smells[:10]:
        kind_label = {"god_class": "God Class", "long_function": "Long Function", "deep_nesting": "Deep Nesting"}.get(s.kind, s.kind)
        smell_table.add_row("⚠️ ", kind_label, s.name, f"{s.file}:L{s.line}", s.detail)

    smell_summary = (
        f"{smell_icon} "
        f"[bold]{len(god_classes)}[/bold] god class{'es' if len(god_classes) != 1 else ''}  •  "
        f"[bold]{len(long_fns)}[/bold] long function{'s' if len(long_fns) != 1 else ''}  •  "
        f"[bold]{len(deep_nests)}[/bold] deep nest{'s' if len(deep_nests) != 1 else ''}"
    )
    border = "yellow" if smells else "green"
    console.print(Panel(smell_summary, title="[bold]🐛 Code Smells[/bold]", border_style=border))
    if smells:
        console.print(smell_table)
    console.print()

    # ── Tech debt tags panel ──────────────────────────────────────────────────
    debt = report.debt_tags
    debt_counts: dict[str, int] = {}
    for d in debt:
        debt_counts[d.tag] = debt_counts.get(d.tag, 0) + 1

    debt_icon = sev_icon(len(debt), 3, 10)
    debt_summary_parts = "  ".join(
        f"[bold]{count}[/bold] {tag}" for tag, count in sorted(debt_counts.items())
    ) or "None found"

    debt_table = Table(show_header=False, box=None, padding=(0, 1))
    debt_table.add_column("Tag", style="bold yellow", width=8)
    debt_table.add_column("Location", style="dim", no_wrap=True)
    debt_table.add_column("Text", style="white")

    # Show BUG first, then FIXME, then others
    priority_order = ["BUG", "FIXME", "HACK", "TODO", "XXX", "DEPRECATED"]
    sorted_debt = sorted(
        debt,
        key=lambda d: (priority_order.index(d.tag) if d.tag in priority_order else 99, d.file, d.line)
    )
    for d in sorted_debt[:12]:
        tag_colour = "red" if d.tag in {"BUG", "FIXME"} else "yellow"
        debt_table.add_row(
            f"[{tag_colour}]{d.tag}[/{tag_colour}]",
            f"{d.file}:L{d.line}",
            d.text[:70] + ("..." if len(d.text) > 70 else ""),
        )
    if len(debt) > 12:
        debt_table.add_row("", "[dim]...[/dim]", f"[dim]and {len(debt) - 12} more[/dim]")

    border = "red" if len(debt) >= 10 else "yellow" if debt else "green"
    console.print(Panel(
        f"{debt_icon} {debt_summary_parts}",
        title="[bold]📋 Technical Debt Tags[/bold]",
        border_style=border,
    ))
    if debt:
        console.print(debt_table)
    console.print()

    # ── Dead imports panel ────────────────────────────────────────────────────
    dead = report.dead_imports
    dead_icon = sev_icon(len(dead), 3, 10)
    dead_table = Table(show_header=False, box=None, padding=(0, 1))
    dead_table.add_column("Icon", width=3)
    dead_table.add_column("Import", style="white")
    dead_table.add_column("Location", style="dim")

    for di in dead[:10]:
        dead_table.add_row("⚠️ ", di.import_name, f"{di.file}:L{di.line}")
    if len(dead) > 10:
        dead_table.add_row("", "[dim]...[/dim]", f"[dim]and {len(dead) - 10} more[/dim]")

    border = "yellow" if dead else "green"
    console.print(Panel(
        f"{dead_icon} [bold]{len(dead)}[/bold] potentially unused import{'s' if len(dead) != 1 else ''} detected  [dim](heuristic — verify before removing)[/dim]",
        title="[bold]🗑️  Dead Imports[/bold]",
        border_style=border,
    ))
    if dead:
        console.print(dead_table)
    console.print()

    # ── Test coverage panel ───────────────────────────────────────────────────
    from devmind.analysis.health import SOURCE_EXTENSIONS
    source_only = [f for f in report.source_files if pathlib.Path(f).suffix.lower() in SOURCE_EXTENSIONS]
    covered_count = len(source_only) - len(report.uncovered_files)
    total_source = max(len(source_only), 1)
    coverage_pct = int(covered_count / total_source * 100)

    cov_icon = "✅" if coverage_pct >= 80 else "⚠️ " if coverage_pct >= 50 else "🔴"
    cov_bar_filled = int(coverage_pct / 5)
    cov_bar = f"[cyan]{'█' * cov_bar_filled}[/cyan][dim]{'░' * (20 - cov_bar_filled)}[/dim]"

    cov_table = Table(show_header=False, box=None, padding=(0, 1))
    cov_table.add_column("Icon", width=3)
    cov_table.add_column("File", style="white")

    for uf in report.uncovered_files[:8]:
        cov_table.add_row("🔴", uf)
    if len(report.uncovered_files) > 8:
        cov_table.add_row("", f"[dim]... and {len(report.uncovered_files) - 8} more[/dim]")

    border = "green" if coverage_pct >= 80 else "yellow" if coverage_pct >= 50 else "red"
    console.print(Panel(
        f"{cov_icon} {cov_bar}  [bold]{covered_count}[/bold] / [bold]{total_source}[/bold] source files covered   [bold]{coverage_pct}%[/bold]",
        title="[bold]🧪 Test Coverage[/bold]",
        border_style=border,
    ))
    if report.uncovered_files:
        console.print(cov_table)
    console.print()

    # ── Final verdict ─────────────────────────────────────────────────────────
    gc = grade_colour(grade)
    if score >= 85:
        verdict = f"[bold green]✅ Score {score}/100 — Excellent codebase health![/bold green]"
    elif score >= 70:
        verdict = f"[bold cyan]✅ Score {score}/100 — Healthy codebase with minor issues.[/bold cyan]"
    elif score >= 55:
        verdict = f"[bold yellow]⚠️  Score {score}/100 — Codebase needs attention.[/bold yellow]"
    elif score >= 40:
        verdict = f"[bold orange3]⚠️  Score {score}/100 — Significant technical debt present.[/bold orange3]"
    else:
        verdict = f"[bold red]🔴 Score {score}/100 — Critical health issues detected.[/bold red]"

    console.print(Panel(verdict, border_style=gc, padding=(0, 2)))

    # ── Optional Markdown output ──────────────────────────────────────────────
    if output:
        import pathlib as _pl
        md_lines = [
            f"# DevMind Codebase Health Report: {report.project_name}",
            "",
            f"**Health Score: {score}/100  |  Grade: {grade}**",
            "",
            f"| Metric | Value |",
            f"|---|---|",
            f"| Total Files | {report.total_files} |",
            f"| Total Functions | {report.total_functions} |",
            f"| Total Classes | {report.total_classes} |",
            f"| Total Lines | {report.total_lines:,} |",
            f"| Avg Complexity (CC) | {report.avg_complexity:.1f} |",
            f"| Complexity Hotspots | {len(hotspots)} |",
            f"| Code Smells | {len(smells)} |",
            f"| Technical Debt Tags | {len(debt)} |",
            f"| Dead Imports | {len(dead)} |",
            f"| Test Coverage | {coverage_pct}% ({covered_count}/{total_source}) |",
            "",
            "## Complexity Hotspots",
            "",
        ]
        if hotspots:
            md_lines.append("| Function | File | Line | CC |")
            md_lines.append("|---|---|---|---|")
            for fc in hotspots[:20]:
                md_lines.append(f"| `{fc.name}` | `{fc.file}` | {fc.line} | {fc.complexity} |")
        else:
            md_lines.append("*No complexity hotspots found.*")

        md_lines += ["", "## Code Smells", ""]
        if smells:
            md_lines.append("| Kind | Name | File | Line | Detail |")
            md_lines.append("|---|---|---|---|---|")
            for s in smells:
                kind_label = {"god_class": "God Class", "long_function": "Long Function", "deep_nesting": "Deep Nesting"}.get(s.kind, s.kind)
                md_lines.append(f"| {kind_label} | `{s.name}` | `{s.file}` | {s.line} | {s.detail} |")
        else:
            md_lines.append("*No code smells found.*")

        md_lines += ["", "## Technical Debt Tags", ""]
        if debt:
            md_lines.append("| Tag | File | Line | Text |")
            md_lines.append("|---|---|---|---|")
            for d in sorted_debt[:50]:
                md_lines.append(f"| `{d.tag}` | `{d.file}` | {d.line} | {d.text} |")
        else:
            md_lines.append("*No debt tags found.*")

        md_lines += ["", "## Uncovered Files (No Tests Found)", ""]
        if report.uncovered_files:
            for uf in report.uncovered_files:
                md_lines.append(f"- `{uf}`")
        else:
            md_lines.append("*All source files have corresponding test files.*")

        md_lines += ["", "---", "*Generated by DevMind CLI (`devmind health`)*"]

        out_path = _pl.Path(output) if _pl.Path(output).is_absolute() else _pl.Path(resolved_dir) / output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
        console.print(f"\n[dim]📄 Report also written to: [cyan]{out_path}[/cyan][/dim]")

    # ── CI threshold gate ─────────────────────────────────────────────────────
    if threshold is not None and score < threshold:
        console.print(f"\n[bold red]❌ Health score {score} is below threshold {threshold}. Exiting with code 1.[/bold red]")
        raise typer.Exit(code=1)

@app.command()
def onboard(
    directory: str = typer.Option(
        ".",
        "--dir", "-d",
        help="The directory of the codebase to analyze."
    ),
    output: str = typer.Option(
        "ONBOARDING.md",
        "--output", "-o",
        help="Output markdown file name for the onboarding guide."
    ),
):
    """
    Generate an instant, structured Codebase Onboarding Guide for new developers.

    Detects tech stack, entry points, setup/test commands, top architectural files,
    git activity, and engineering debt. Outputs ONBOARDING.md and a terminal dashboard.
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from devmind.analysis.onboarding import generate_onboarding_report, format_onboarding_markdown

    console = Console()
    resolved_dir = get_project_root(directory) if directory == "." else os.path.abspath(directory)

    with console.status("[bold cyan]🚀 Analyzing codebase topology for onboarding guide...[/bold cyan]", spinner="dots"):
        report = generate_onboarding_report(resolved_dir)

    console.print()
    banner = (
        f"[bold cyan]🚀 Codebase Onboarding Guide: {report.project_name}[/bold cyan]\n"
        f"[dim]{report.total_files} files • {report.total_lines:,} lines • Auto-detected architecture[/dim]"
    )
    console.print(Panel(banner, border_style="cyan", padding=(0, 2)))
    console.print()

    # 1. Tech Stack Card
    stack_lines = []
    if report.stack.languages:
        stack_lines.append(f"[bold]Languages:[/bold]       {', '.join(report.stack.languages)}")
    if report.stack.frameworks:
        stack_lines.append(f"[bold]Frameworks:[/bold]      {', '.join(report.stack.frameworks)}")
    if report.stack.package_managers:
        stack_lines.append(f"[bold]Tooling:[/bold]         {', '.join(report.stack.package_managers)}")
    if report.stack.databases:
        stack_lines.append(f"[bold]Storage/DB:[/bold]      {', '.join(report.stack.databases)}")
    if report.stack.entry_points:
        stack_lines.append(f"[bold]Entry Points:[/bold]    {', '.join(report.stack.entry_points[:4])}")

    console.print(Panel(
        "\n".join(stack_lines) if stack_lines else "[dim]Standard environment[/dim]",
        title="[bold]🏗️  Technology Stack[/bold]",
        border_style="magenta"
    ))
    console.print()

    # 2. Setup Commands
    cmd_table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    cmd_table.add_column("Action", style="yellow", width=12)
    cmd_table.add_column("Command", style="bold white")

    if report.commands.install:
        for c in report.commands.install:
            cmd_table.add_row("Install", c)
    if report.commands.run:
        for c in report.commands.run:
            cmd_table.add_row("Run", c)
    if report.commands.test:
        for c in report.commands.test:
            cmd_table.add_row("Test", c)
    if report.commands.lint:
        for c in report.commands.lint:
            cmd_table.add_row("Lint", c)

    console.print(Panel(
        cmd_table if (report.commands.install or report.commands.run or report.commands.test) else "[dim]No explicit scripts found.[/dim]",
        title="[bold]⚙️  Quickstart Commands[/bold]",
        border_style="green"
    ))
    console.print()

    # 3. Key Architectural Files
    file_table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    file_table.add_column("File", style="bold white", no_wrap=True)
    file_table.add_column("Role / Summary", style="dim")
    file_table.add_column("Imports", justify="right", style="cyan")

    for kf in report.key_files:
        file_table.add_row(kf.path, kf.role_summary[:65], str(kf.fan_in))

    console.print(Panel(
        file_table,
        title="[bold]🗺️  Core Architectural Files (Start Reading Here)[/bold]",
        border_style="blue"
    ))
    console.print()

    # Export Markdown file
    md_content = format_onboarding_markdown(report)
    out_path = pathlib.Path(output) if pathlib.Path(output).is_absolute() else pathlib.Path(resolved_dir) / output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    console.print(f"[bold green]✨ Onboarding guide generated at:[/bold green] [cyan]{out_path}[/cyan]\n")

@app.command()
def impact(
    target: str = typer.Argument(
        ...,
        help="The function, class, or file path to analyze blast radius for."
    ),
    directory: str = typer.Option(
        ".",
        "--dir", "-d",
        help="The directory of the codebase to analyze."
    ),
    depth: int = typer.Option(
        3,
        "--depth",
        help="Maximum downstream call graph hops to traverse."
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output", "-o",
        help="Optional markdown file path to write the blast radius report to."
    ),
):
    """
    Analyze blast radius and downstream dependency impact before modifying code.

    Traverses AST call graphs and import networks to reveal direct callers,
    transitive ripples, impacted test suites, and calculates a risk severity score.
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.tree import Tree
    from devmind.analysis.impact import run_impact_analysis, format_impact_markdown

    console = Console()
    resolved_dir = get_project_root(directory) if directory == "." else os.path.abspath(directory)

    with console.status(f"[bold cyan]💥 Calculating blast radius for '[white]{target}[/white]'...[/bold cyan]", spinner="dots"):
        report = run_impact_analysis(resolved_dir, target, depth=depth)

    console.print()
    sev_colour = {"CRITICAL": "red", "MODERATE": "yellow", "LOW": "green"}.get(report.severity, "white")
    sev_icon = {"CRITICAL": "🔴", "MODERATE": "⚠️ ", "LOW": "🟢"}.get(report.severity, "")

    loc_str = f" in [cyan]{report.target_file}[/cyan]" if report.target_file else ""
    if report.target_line:
        loc_str += f":L{report.target_line}"

    target_header = (
        f"  [bold]Target:[/bold] [cyan]{report.target_symbol}[/cyan] ({report.target_type}){loc_str}\n"
        f"  [bold]Blast Radius Severity:[/bold] [{sev_colour}]{sev_icon} {report.severity}[/{sev_colour}] (Risk Score: [{sev_colour}]{report.risk_score}/100[/{sev_colour}])\n"
        f"  [bold]Impact:[/bold] [bold]{len(report.direct_callers)}[/bold] direct callers • "
        f"[bold]{len(report.transitive_callers)}[/bold] transitive downstream • "
        f"[bold]{len(report.impacted_files)}[/bold] files • "
        f"[bold]{len(report.impacted_tests)}[/bold] test suites"
    )
    console.print(Panel(target_header, title="[bold magenta]💥 DevMind Blast Radius Analysis[/bold magenta]", border_style=sev_colour))
    console.print()

    # 1. Direct Callers Table
    if report.direct_callers:
        direct_table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
        direct_table.add_column("Location", style="white", no_wrap=True)
        direct_table.add_column("Enclosing Scope", style="yellow")
        direct_table.add_column("Type", style="dim")
        direct_table.add_column("Code Snippet", style="dim")

        for c in report.direct_callers[:10]:
            direct_table.add_row(
                f"{c.file_path}:L{c.line_number}",
                c.enclosing_symbol,
                c.call_type,
                c.snippet[:50] + ("..." if len(c.snippet) > 50 else "")
            )
        console.print(Panel(direct_table, title=f"[bold]🎯 Direct Callers (Depth 1 — {len(report.direct_callers)} sites)[/bold]", border_style="cyan"))
        console.print()
    else:
        console.print(Panel("[dim]No direct internal callers detected in codebase.[/dim]", title="[bold]🎯 Direct Callers[/bold]", border_style="green"))
        console.print()

    # 2. Transitive Tree
    if report.transitive_callers:
        tree = Tree(f"[bold cyan]{report.target_symbol}[/bold cyan] [dim](target)[/dim]")
        for tc in report.transitive_callers[:12]:
            tree.add(f"[dim]Hop {tc.depth} ➔[/dim] [white]{tc.file_path}:L{tc.line_number}[/white] in [yellow]{tc.enclosing_symbol}()[/yellow]")
        console.print(Panel(tree, title=f"[bold]🌊 Downstream Transitive Ripple ({len(report.transitive_callers)} downstream nodes)[/bold]", border_style="yellow"))
        console.print()

    # 3. Impacted Tests Checklist
    if report.impacted_tests:
        test_table = Table(show_header=False, box=None, padding=(0, 1))
        test_table.add_column("Icon", width=3)
        test_table.add_column("Test Suite", style="bold red")
        for t in report.impacted_tests:
            test_table.add_row("🔴", t)
        console.print(Panel(test_table, title="[bold]🧪 Impacted Test Suites (MUST RUN BEFORE COMMITTING)[/bold]", border_style="red"))
        console.print()
    else:
        console.print(Panel("[dim]No direct test suites exercise this symbol.[/dim]", title="[bold]🧪 Impacted Test Suites[/bold]", border_style="dim"))
        console.print()

    # 4. Recommended Actions
    if report.recommended_actions:
        rec_text = "\n".join([f"• {r}" for r in report.recommended_actions])
        console.print(Panel(rec_text, title="[bold]💡 Recommended Actions[/bold]", border_style=sev_colour))
        console.print()

    # Export Markdown if requested
    if output:
        md_content = format_impact_markdown(report)
        out_path = pathlib.Path(output) if pathlib.Path(output).is_absolute() else pathlib.Path(resolved_dir) / output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        console.print(f"[dim]📄 Report written to: [cyan]{out_path}[/cyan][/dim]\n")


@app.command()
def drift(
    directory: str = typer.Option(
        ".",
        "--dir", "-d",
        help="The directory of the codebase to analyze."
    ),
    days: int = typer.Option(
        30,
        "--days",
        help="Number of days of git history to analyze for churn."
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output", "-o",
        help="Optional path to export the report as markdown (e.g. DRIFT.md)."
    )
):
    """
    Detect architecture drift: circular imports, layer violations, and
    churn/complexity hotspots. Runs 100% offline (no API calls).
    """
    from devmind.analysis.drift import run_drift_analysis, render_drift_terminal, format_drift_markdown
    from rich.console import Console

    resolved_dir = get_project_root(directory) if directory == "." else os.path.abspath(directory)
    console = Console()

    with console.status("[bold cyan]Scanning for architecture drift and churn hotspots...[/bold cyan]", spinner="dots"):
        report = run_drift_analysis(resolved_dir, days=days)

    render_drift_terminal(report, console=console)

    if output:
        out_path = pathlib.Path(output) if pathlib.Path(output).is_absolute() else pathlib.Path(resolved_dir) / output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(format_drift_markdown(report))
        console.print(f"\n[dim]📄 Report written to: [cyan]{out_path}[/cyan][/dim]\n")


@app.command()
def blame(
    file_path: str = typer.Argument(..., help="The relative path of the file to analyze."),
    expert: bool = typer.Option(
        False,
        "--expert",
        help="Only show the primary domain expert for this file."
    ),
    func_name: Optional[str] = typer.Option(
        None,
        "--func",
        help="Scope ownership and history to a specific function/method name."
    )
):
    """
    Semantic & architectural git blame: code ownership, key commits,
    collision risk, and related Architecture Decision Records.
    """
    from devmind.analysis.blame import generate_blame_report, render_blame_terminal
    from rich.console import Console

    root_dir = get_project_root(os.path.dirname(os.path.abspath(file_path)) or ".")
    relative_path = os.path.relpath(os.path.abspath(file_path), root_dir)

    if not os.path.exists(os.path.join(root_dir, relative_path)):
        typer.echo(f"[Error] File not found: {file_path}")
        raise typer.Exit(code=1)

    if not is_git_repo(root_dir):
        typer.echo(f"[Error] '{root_dir}' is not a git repository. Semantic blame requires git history.")
        raise typer.Exit(code=1)

    console = Console()
    with console.status(f"[bold cyan]Analyzing semantic blame for '[white]{relative_path}[/white]'...[/bold cyan]", spinner="dots"):
        report = run_async(generate_blame_report(relative_path, root_dir, func_name=func_name))

    render_blame_terminal(report, console=console, expert_only=expert)


@app.command()
def secure(
    directory: str = typer.Option(
        ".",
        "--dir", "-d",
        help="The directory of the codebase to scan for security vulnerabilities."
    ),
    severity: Optional[str] = typer.Option(
        None,
        "--severity", "-s",
        help="Filter findings by minimum severity: 'critical', 'high', 'medium', 'low'."
    ),
    category: Optional[str] = typer.Option(
        None,
        "--category", "-c",
        help="Filter findings by category keyword (e.g. 'secret', 'injection', 'sink')."
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output", "-o",
        help="Optional path to export the report as markdown (e.g. SECURITY.md)."
    )
):
    """
    Offline Security & Penetration Scanner: hardcoded secrets, dangerous sinks (eval/exec/subprocess),
    injection risks (SQLi/SSRF/Path Traversal), cryptographic weaknesses, and CVEs.
    """
    from devmind.analysis.secure import run_security_analysis, format_secure_markdown
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    resolved_dir = get_project_root(directory) if directory == "." else os.path.abspath(directory)
    console = Console()

    with console.status("[bold cyan]Running offline penetration & security audit...[/bold cyan]", spinner="dots"):
        report = run_security_analysis(resolved_dir, severity=severity, category=category)

    # 1. Header Banner
    grade_color = "green" if report.risk_grade in ("A", "B") else ("yellow" if report.risk_grade == "C" else "red")
    summary_text = (
        f"[bold]Project:[/bold] {os.path.basename(resolved_dir)}  │  "
        f"[bold]Files Scanned:[/bold] {report.files_scanned}  │  "
        f"[bold]Security Grade:[/bold] [{grade_color} bold]{report.risk_grade} ({report.risk_score}/100)[/{grade_color} bold]\n"
        f"[bold]Vulnerabilities:[/bold] "
        f"[red bold]🔴 {report.critical_count} Critical[/red bold]  •  "
        f"[yellow bold]🟠 {report.high_count} High[/yellow bold]  •  "
        f"[blue]🟡 {report.medium_count} Medium[/blue]  •  "
        f"[dim]🔵 {report.low_count} Low[/dim]"
    )
    console.print()
    console.print(Panel.fit(summary_text, title="🔒 DevMind Security & Penetration Audit", border_style=grade_color))
    console.print()

    # 2. Findings Table / Cards
    if not report.findings:
        console.print(Panel("✅ [bold green]Clean Audit:[/bold green] No security vulnerabilities or hardcoded secrets detected.", title="🛡️ Status", border_style="green"))
        console.print()
    else:
        table = Table(title=f"🚨 Detected Vulnerabilities ({len(report.findings)} items)", border_style="red", show_lines=True)
        table.add_column("Sev", justify="center", width=8)
        table.add_column("Rule & Title", style="bold white", width=28)
        table.add_column("Location", style="cyan", width=22)
        table.add_column("Risk & Remediation", width=42)

        for f in report.findings[:25]:  # show top 25 findings
            if f.severity == "CRITICAL":
                sev_styled = "[red bold]CRITICAL[/red bold]"
            elif f.severity == "HIGH":
                sev_styled = "[yellow bold]HIGH[/yellow bold]"
            elif f.severity == "MEDIUM":
                sev_styled = "[blue]MEDIUM[/blue]"
            else:
                sev_styled = "[dim]LOW[/dim]"

            loc = f"{f.file_path}:L{f.line_number}"
            details = f"[dim]{f.owasp_category}[/dim]\n[bold]{f.exploit_scenario}[/bold]\n💡 [green]{f.remediation}[/green]"
            table.add_row(sev_styled, f"[bold]{f.title}[/bold]\n[dim]{f.id}[/dim]", loc, details)

        console.print(table)
        console.print()

    # 3. Export Markdown if requested
    if output:
        out_path = pathlib.Path(output) if pathlib.Path(output).is_absolute() else pathlib.Path(resolved_dir) / output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(format_secure_markdown(report))
        console.print(f"[dim]📄 Security audit written to: [cyan]{out_path}[/cyan][/dim]\n")


@app.command()
def doctor():
    """
    Run self-healing system & environment diagnostics: Python version, git,
    AI provider connectivity, local memory/cache integrity, FastEmbed
    readiness, and network/update status.
    """
    from devmind.doctor import run_diagnostics, render_diagnostics
    from rich.console import Console

    console = Console()
    with console.status("[bold cyan]🩺 Running DevMind diagnostics...[/bold cyan]", spinner="dots"):
        results = run_diagnostics()

    console.print()
    render_diagnostics(results, console=console)

    if any(r.status == "fail" for r in results):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

