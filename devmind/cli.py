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
from devmind.ingestion.git_parser import get_git_history
from devmind.ingestion.comment_extractor import get_codebase_comments

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("devmind.cli")

def run_async(coro):
    """
    Custom asyncio runner that sets an exception handler to swallow 
    noisy Win32 socket teardown/closed event loop warnings on shutdown.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    def silence_exceptions(loop, context):
        exc = context.get("exception")
        msg = context.get("message", "")
        # Swallows Win32 10038/not-a-socket/Event loop is closed warnings during exit
        if (exc and ("Event loop is closed" in str(exc) or "10038" in str(exc) or "socket" in str(exc))) or "Event loop is closed" in msg or "SSL transport" in msg:
            return
        loop.default_exception_handler(context)
        
    loop.set_exception_handler(silence_exceptions)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()

app = typer.Typer(
    name="devmind",
    help="DevMind – Codebase Memory for Developers. Powered by Cognee.",
    add_completion=False
)

async def remember_pipeline(directory: str):
    """
    Core async pipeline for scanning files, comments, and git logs,
    and loading them into Cognee.
    """
    # Determine a single, unified dataset name based on the target folder
    folder_name = os.path.basename(os.path.abspath(directory)).lower().replace("-", "_").replace(" ", "_")
    dataset_name = f"devmind_{folder_name}"

    # 1. Scan the codebase files
    files = scan_codebase_files(directory)
    if not files:
        typer.echo("No files found to ingest.")
        return
        
    typer.echo(f"Ingesting {len(files)} files into Cognee memory (Dataset: {dataset_name})...")
    
    # Ingest file contents in a single batch
    contents = []
    for idx, file_data in enumerate(files, start=1):
        rel_path = file_data["relative_path"]
        content = file_data["content"]
        
        tagged_content = f"File Path: {rel_path}\n---\n{content}"
        contents.append(tagged_content)
        
    logger.info(f"Batched {len(contents)} files. Triggering ingestion pipeline...")
    success = await remember_content(contents, dataset_name=dataset_name)
    if success:
        typer.echo(f"Successfully remembered {len(files)} files.")
    else:
        typer.echo(f"[Warning] Failed to ingest files.")

    # 2. Extract and Ingest Git History
    git_logs = get_git_history(directory, max_commits=20)
    if git_logs:
        typer.echo("Ingesting combined git history into Cognee...")
        combined_git = "\n\n---\n\n".join(git_logs)
        success = await remember_content(combined_git, dataset_name=dataset_name)
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
        success = await remember_content(combined_comments, dataset_name=dataset_name)
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
    )
):
    """
    Ingest the codebase files into persistent Cognee memory.
    """
    initialize_cognee()
    resolved_dir = get_project_root(directory) if directory == "." else os.path.abspath(directory)
    run_async(remember_pipeline(resolved_dir))
    typer.echo("[Success] Codebase memory ingestion completed.")

@app.command()
def ask(
    query: str = typer.Argument(..., help="Your natural language question about the codebase.")
):
    """
    Ask a question about the ingested codebase memory in plain English.
    """
    initialize_cognee()
    
    typer.echo(f"Querying codebase memory for: '{query}'...")
    answer = run_async(recall_query(query))
    
    typer.echo("\n--- Response ---")
    typer.echo(answer)
    typer.echo("----------------")

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
    output: str = typer.Option(
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
    with console.status("[bold cyan]Analyzing architecture drift...[/bold cyan]", spinner="dots"):
        report = run_drift_analysis(resolved_dir, days=days)

    render_drift_terminal(report, console=console)

    if output:
        markdown = format_drift_markdown(report)
        with open(output, "w", encoding="utf-8") as f:
            f.write(markdown)
        typer.echo(f"\n[Success] Drift report exported to '{output}'.")

@app.command()
def mcp():
    """
    Start the DevMind MCP server for integration with Claude Code.
    """
    typer.echo("Starting DevMind MCP Server...")
    from devmind.integrations.claude_code import mcp as mcp_instance
    mcp_instance.run()

if __name__ == "__main__":
    app()
