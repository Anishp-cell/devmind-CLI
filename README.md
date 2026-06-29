# DevMind – Codebase Memory for Developers

> "Your codebase finally has a memory."

DevMind is a developer CLI tool and local web interface that gives your codebase a persistent, queryable memory powered by **Cognee**. It scans source files, git commit history, comments, and architectural decisions, building a hybrid graph-vector knowledge store. This persistent memory allows developers and AI coding assistants (via MCP) to query the codebase in plain English and carry context across infinite sessions.

---

## Features

1. **One-Command Ingestion** (`devmind remember`): Scans the codebase, git logs, and code comments to feed `cognee.remember()`.
2. **Plain-English Q&A** (`devmind ask "..."`): Uses `cognee.recall()` to retrieve grounded, context-aware answers from the memory graph.
3. **Decision Logging** (`devmind log "..."`): Records Architecture Decision Records (ADRs) to capture design reasoning.
4. **Memory Refresh** (`devmind refresh`): Automatically detects modified files, updates the graph, and runs `cognee.improve()`.
5. **Surgical Forget** (`devmind forget --file ...`): Prunes specific file memory from the knowledge graph using `cognee.forget()`.
6. **Claude Code MCP Server** (`devmind mcp`): Seamlessly integrates with Claude Code or Cursor via standard Model Context Protocol (MCP).
7. **Local Dashboard UI** (`devmind dashboard`): Provides a clean visual panel showing memory status, search queries, and recent decisions.
8. **Smart API Key Rotation**: Automatically detects, formats, and rotates between multiple Groq and OpenRouter API keys to balance rate limits on free-tier LLM access.

---

## Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/Anishp-cell/devmind-CLI.git
cd devmind-CLI
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```
To run for **free**, configure your `.env` with a list of rotated API keys:
```env
LLM_PROVIDER="groq"

# Add a comma-separated list of Groq keys (gsk_...) and/or OpenRouter keys (sk-or-v1-...)
# The CLI automatically load-balances and routes requests to the correct endpoints!
GROQ_API_KEYS="gsk_key1,sk-or-v1-key2,gsk_key3"

EMBEDDING_PROVIDER="fastembed"
EMBEDDING_MODEL="BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS="384"
```

### 3. Install DevMind
Install the package in editable mode:
```bash
pip install -e .
```

---

## CLI Command Reference

*   **Ingest Codebase**:
    ```bash
    devmind remember
    ```
*   **Ask a Question**:
    ```bash
    devmind ask "Why did we switch to redis for the queue?"
    ```
*   **Log an Architectural Decision (ADR)**:
    ```bash
    devmind log "Chose FastAPI for the web UI because it supports async routes natively."
    ```
*   **Refresh Changed Memory**:
    ```bash
    devmind refresh
    ```
*   **Forget a Specific File**:
    ```bash
    devmind forget --file devmind/web/app.py
    ```
*   **Wipe Local Database Cache**:
    ```bash
    devmind forget --all
    ```
*   **Launch Web Dashboard**:
    ```bash
    devmind dashboard --port 8000
    ```
*   **Start MCP Server**:
    ```bash
    devmind mcp
    ```

---

## Running the Mock Demo Project

To test DevMind on a smaller project without polluting your main repo:
1. Navigate to the demo directory:
   ```bash
   cd examples/demo_project
   ```
2. Build the memory of the demo:
   ```bash
   devmind remember --dir .
   ```
3. Query its memory:
   ```bash
   devmind ask "What open TODO tasks are left in main.py?"
   devmind ask "Why do we use SQLite according to our architecture decisions?"
   ```

---

## Claude Code MCP Integration

To connect Claude Code to DevMind's memory, add the server to your Claude MCP config:

```bash
claude mcp add devmind "devmind mcp"
```

Alternatively, configure your project-level `.mcp.json` file in your project root:
```json
{
  "mcpServers": {
    "devmind": {
      "command": "devmind",
      "args": ["mcp"]
    }
  }
}
```

---

## AI Assistant Declaration

Per the rules of **The Hangover Part AI Hackathon**, this project declares the use of **Claude** (via the Antigravity IDE agent) as an AI pair programmer.
