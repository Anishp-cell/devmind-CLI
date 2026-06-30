import os
import sys
import asyncio
import logging

import warnings

# Suppress ResourceWarning and DeprecationWarning from aiohttp/asyncio during garbage collection
warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Suppress Windows proactor event loop SSL bugs during shutdown
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from devmind.memory import recall_query, remember_content, initialize_cognee
from devmind.cli import remember_pipeline

logger = logging.getLogger("devmind.web")

app = FastAPI(title="DevMind Dashboard")

# Initialize Cognee configurations
initialize_cognee()

# Create templates folder and configuration
current_dir = os.path.dirname(os.path.abspath(__file__))
templates_path = os.path.join(current_dir, "templates")
os.makedirs(templates_path, exist_ok=True)
templates = Jinja2Templates(directory=templates_path)

@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    """
    Renders the DevMind UI dashboard.
    """
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/ask")
async def api_ask(payload: dict):
    """
    Handles natural language queries about the codebase.
    """
    query = payload.get("query", "")
    if not query:
        return JSONResponse({"error": "Query cannot be empty"}, status_code=400)
    
    try:
        answer = await recall_query(query)
        return {"answer": answer}
    except Exception as e:
        logger.error(f"Error querying memory: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/log")
async def api_log(payload: dict):
    """
    Saves an Architectural Decision Record (ADR) into memory.
    """
    decision = payload.get("decision", "")
    if not decision:
        return JSONResponse({"error": "Decision cannot be empty"}, status_code=400)
    
    try:
        import time
        dataset_name = f"adr_decision_{int(time.time())}"
        success = await remember_content(f"Architectural Decision Record:\n{decision}", dataset_name=dataset_name)
        return {"success": success}
    except Exception as e:
        logger.error(f"Error logging decision: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/remember")
async def api_remember(background_tasks: BackgroundTasks):
    """
    Triggers codebase re-ingestion asynchronously in the background.
    """
    try:
        project_dir = os.getcwd()
        background_tasks.add_task(remember_pipeline, project_dir)
        return {"status": "ingested", "message": "Codebase memory re-ingestion started in the background."}
    except Exception as e:
        logger.error(f"Error triggering remember: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
