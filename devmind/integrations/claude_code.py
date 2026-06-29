import os
import time
import asyncio
from fastmcp import FastMCP
from devmind.memory import recall_query, remember_content

# Initialize FastMCP Server
mcp = FastMCP(
    "DevMind",
    dependencies=["cognee", "fastmcp"]
)

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
        dataset_name = f"adr_decision_{int(time.time())}"
        tagged_decision = f"Architectural Decision Record:\n{decision}"
        success = await remember_content(tagged_decision, dataset_name=dataset_name)
        if success:
            return "Successfully logged architectural decision to memory."
        else:
            return "Failed to log architectural decision."
    except Exception as e:
        return f"Error logging decision: {e}"

if __name__ == "__main__":
    # Start the MCP server (running over stdin/stdout transport)
    mcp.run()
