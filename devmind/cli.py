# pyrefly: ignore [missing-import]
import typer
import asyncio
import os
import logging
from devmind.memory import initialize_cognee, remember_content, recall_query
from devmind.ingestion.file_reader import scan_codebase_files
from devmind.ingestion.git_parser import get_git_history
from devmind.ingestion.comment_extractor import get_codebase_comments

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("devmind.cli")

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
    asyncio.run(remember_pipeline(directory))
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
    answer = asyncio.run(recall_query(query))
    
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
    
    success = asyncio.run(remember_content(tagged_decision, dataset_name=dataset_name))
    if success:
        typer.echo("[Success] Architectural decision successfully logged.")
    else:
        typer.echo("[Error] Failed to log architectural decision.")

if __name__ == "__main__":
    app()
