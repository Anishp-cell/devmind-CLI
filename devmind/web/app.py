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
    try:
        return templates.TemplateResponse(request=request, name="index.html")
    except TypeError:
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


def build_codebase_graph_data(project_dir: str) -> dict:
    """
    Scans codebase and constructs Vis-network compatible nodes and edges graph payload.
    """
    from devmind.ingestion.file_reader import scan_codebase_files
    files = scan_codebase_files(project_dir)
    
    nodes = []
    edges = []
    node_ids = set()

    total_classes = 0
    total_funcs = 0

    for file_data in files:
        rel_path = file_data["relative_path"]
        file_id = f"file:{rel_path}"
        if file_id not in node_ids:
            node_ids.add(file_id)
            nodes.append({
                "id": file_id,
                "label": os.path.basename(rel_path),
                "group": "file",
                "title": f"File: {rel_path}",
                "path": rel_path,
                "shape": "dot",
                "size": 22
            })
            
        symbols = file_data.get("ast_symbols", {})
        classes = symbols.get("classes", [])
        total_classes += len(classes)
        for cls in classes:
            cls_id = f"class:{rel_path}:{cls['name']}"
            if cls_id not in node_ids:
                node_ids.add(cls_id)
                nodes.append({
                    "id": cls_id,
                    "label": f"Class {cls['name']}",
                    "group": "class",
                    "title": f"Class {cls['name']} in {rel_path}",
                    "shape": "diamond",
                    "size": 16
                })
                edges.append({"from": file_id, "to": cls_id, "label": "defines"})
                
        functions = symbols.get("functions", [])
        total_funcs += len(functions)
        for fn in functions:
            fn_id = f"func:{rel_path}:{fn['name']}"
            if fn_id not in node_ids:
                node_ids.add(fn_id)
                nodes.append({
                    "id": fn_id,
                    "label": f"fn {fn['name']}()",
                    "group": "func",
                    "title": f"Function {fn['name']} in {rel_path}",
                    "shape": "triangle",
                    "size": 12
                })
                edges.append({"from": file_id, "to": fn_id, "label": "defines"})

    return {
        "nodes": nodes, 
        "edges": edges, 
        "stats": {
            "total_files": len(files),
            "total_classes": total_classes,
            "total_funcs": total_funcs,
            "total_nodes": len(nodes),
            "total_edges": len(edges)
        }
    }


@app.get("/api/graph")
async def api_graph():
    """
    Returns visual architecture node graph JSON.
    """
    try:
        project_dir = os.getcwd()
        graph_data = build_codebase_graph_data(project_dir)
        return graph_data
    except Exception as e:
        logger.error(f"Error building graph data: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/digest")
async def api_digest():
    """
    Returns high-level codebase metrics summary digest.
    """
    try:
        project_dir = os.getcwd()
        graph_data = build_codebase_graph_data(project_dir)
        return {
            "project": os.path.basename(os.path.abspath(project_dir)),
            "stats": graph_data["stats"]
        }
    except Exception as e:
        logger.error(f"Error building digest data: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

