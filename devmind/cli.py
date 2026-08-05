# pyrefly: ignore [missing-import]
import typer
import sys
import asyncio
import os
import logging
import warnings

# Suppress ResourceWarning and DeprecationWarning from aiohttp/asyncio during garbage collection
warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Suppress Windows proactor event loop SSL bugs during shutdown
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from devmind.memory import initialize_cognee, remember_content, recall_query, improve_memory, forget_memory, forget_file_nodes, get_project_root
from devmind.ingestion.file_reader import scan_codebase_files
from devmind.ingestion.git_parser import get_git_history, get_changed_files_git_diff
from devmind.ingestion.comment_extractor import get_codebase_comments

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
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
    initialize_cognee()
    resolved_dir = get_project_root(directory) if directory == "." else os.path.abspath(directory)
    run_async(remember_pipeline(resolved_dir, incremental=incremental, deep=deep))
    typer.echo("[Success] Codebase memory ingestion completed.")

@app.command()
def ask(
    query: str = typer.Argument(..., help="Your natural language question about the codebase.")
):
    """
    Ask a question about the ingested codebase memory in plain English.
    """
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

@app.command()
def chat():
    """
    Start an interactive DevMind terminal chat session to explore your codebase.
    """
    initialize_cognee()
    
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import Prompt

    console = Console()
    console.print(Panel.fit("[bold blue]DevMind Codebase Chat[/bold blue]\n[dim]Type your queries below. Type 'exit' or 'quit' to close.[/dim]", border_style="blue"))
    
    while True:
        try:
            query = Prompt.ask("\n[bold green]You[/bold green]")
            if not query.strip():
                continue
            if query.lower().strip() in ['exit', 'quit', 'clear']:
                console.print("[dim]Goodbye![/dim]")
                break
                
            with console.status("[bold cyan]DevMind is thinking...[/bold cyan]", spinner="dots"):
                answer = run_async(recall_query(query))
                
            console.print("\n[bold magenta]DevMind:[/bold magenta]")
            console.print(Markdown(answer))
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")

@app.command()
def log(
    decision: str = typer.Argument(..., help="The Architectural Decision Record (ADR) text to log.")
):
    """
    Log an Architectural Decision Record (ADR) into persistent memory.
    """
    initialize_cognee()
    typer.echo(f"Logging decision: '{decision}'...")
    
    tagged_decision = f"Architectural Decision Record:\n{decision}"
    import time
    dataset_name = f"adr_decision_{int(time.time())}"
    
    success = run_async(remember_content(tagged_decision, dataset_name=dataset_name))
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
    abs_dir = os.path.abspath(directory)
    os.chdir(abs_dir)
    url = f"http://localhost:{port}/#graph"
    typer.echo(f"Opening interactive codebase graph at {url} ...")
    webbrowser.open(url)
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

if __name__ == "__main__":
    app()
