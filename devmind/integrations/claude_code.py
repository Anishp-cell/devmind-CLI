import os
import time
import asyncio
from fastmcp import FastMCP
from devmind.memory import recall_query, remember_content, ADR_DATASET_NAME

mcp = FastMCP("DevMind")

@mcp.tool()
async def query_codebase_memory(query: str) -> str:
    """
    Queries the DevMind persistent codebase memory for details about the codebase structure, 
    design choices, git commit history, comments, and architectural decisions.
    """
    try:
        answer = await recall_query(query)
        return answer
    except Exception as e:
        return f"Error querying codebase memory: {e}"

@mcp.tool()
async def log_architectural_decision(decision: str) -> str:
    """
    Logs an Architectural Decision Record (ADR) into the codebase's persistent memory.
    Use this when introducing major design changes, library switches, or design patterns.
    """
    try:
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        tagged_decision = f"Architectural Decision Record:\nDate: {timestamp}\n{decision}"
        success = await remember_content(tagged_decision, dataset_name=ADR_DATASET_NAME)
        if success:
            return "Successfully logged architectural decision to memory."
        else:
            return "Failed to log architectural decision."
    except Exception as e:
        return f"Error logging decision: {e}"

if __name__ == "__main__":
    # Start the MCP server (running over stdin/stdout transport)
    mcp.run()
