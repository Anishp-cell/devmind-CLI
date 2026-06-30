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

from devmind.memory import initialize_cognee, remember_content, recall_query, improve_memory, forget_memory
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
    # 1. Scan the codebase files
    files = scan_codebase_files(directory)
    if not files:
        typer.echo("No files found to ingest.")
        return
        
    typer.echo(f"Ingesting {len(files)} files into Cognee memory...")
    
    # Ingest file contents
    file_success = 0
    for idx, file_data in enumerate(files, start=1):
        rel_path = file_data["relative_path"]
        content = file_data["content"]
        
        tagged_content = f"File Path: {rel_path}\n---\n{content}"
        dataset_name = rel_path.replace("/", "_").replace("\\", "_").replace(".", "_").replace(" ", "_")
        
        logger.info(f"[{idx}/{len(files)}] Processing {rel_path}...")
        success = await remember_content(tagged_content, dataset_name=dataset_name)
        if success:
            file_success += 1
            
    typer.echo(f"Successfully remembered {file_success}/{len(files)} files.")

    # 2. Extract and Ingest Git History
    git_logs = get_git_history(directory, max_commits=20)
    if git_logs:
        typer.echo(f"Ingesting git history ({len(git_logs)} commits) into Cognee...")
        git_success = 0
        for idx, commit_log in enumerate(git_logs, start=1):
            dataset_name = f"git_commit_{idx}"
            success = await remember_content(commit_log, dataset_name=dataset_name)
            if success:
                git_success += 1
        typer.echo(f"Successfully remembered {git_success}/{len(git_logs)} commits.")

    # 3. Extract and Ingest Inline Comments & Docstrings
    relative_paths = [f["relative_path"] for f in files]
    comments = get_codebase_comments(directory, relative_paths)
    if comments:
        typer.echo(f"Ingesting inline comments ({len(comments)} files containing comments)...")
        comment_success = 0
        for idx, comment_block in enumerate(comments, start=1):
            dataset_name = f"code_comments_{idx}"
            success = await remember_content(comment_block, dataset_name=dataset_name)
            if success:
                comment_success += 1
        typer.echo(f"Successfully remembered {comment_success}/{len(comments)} comment segments.")

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
    run_async(remember_pipeline(directory))
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
    typer.echo("----------------\n")

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
    typer.echo("Scanning for codebase changes to refresh memory...")
    run_async(remember_pipeline(directory))
    
    typer.echo("Refining the codebase memory graph structure...")
    # Improve memory on all dataset partitions
    success = run_async(improve_memory(dataset_name="codebase_memory"))
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
        dataset_name = file_path.replace("/", "_").replace("\\", "_").replace(".", "_").replace(" ", "_")
        typer.echo(f"Removing memory dataset '{dataset_name}'...")
        success = run_async(forget_memory(dataset_name))
        if success:
            typer.echo(f"[Success] Memory of '{file_path}' successfully forgotten.")
        else:
            typer.echo(f"[Error] Failed to forget memory of '{file_path}'.")
    else:
        typer.echo("[Warning] Please specify either --file <path> to forget a file, or --all to wipe all databases.")

@app.command()
def dashboard(
    port: int = typer.Option(8000, "--port", "-p", help="Port to run the dashboard server on.")
):
    """
    Launch the DevMind Web UI dashboard.
    """
    import uvicorn
    typer.echo(f"Starting DevMind Web UI Dashboard on http://localhost:{port} ...")
    uvicorn.run("devmind.web.app:app", host="127.0.0.1", port=port, reload=False)

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
