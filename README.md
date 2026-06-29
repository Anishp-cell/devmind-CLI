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
6. **Claude Code MCP Server**: Seamlessly integrates with Claude Code or Cursor via standard Model Context Protocol (MCP).
7. **Local Dashboard UI**: Provides a clean visual panel showing memory status, search queries, and recent decisions.

---

## Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/your-username/devmind.git
cd devmind
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```
To run for **free**, configure Groq as the LLM provider and Fastembed as the embedding provider in your `.env`:
```env
LLM_PROVIDER="groq"
GROQ_API_KEY="your_groq_api_key"
LLM_MODEL="groq/llama-3.3-70b-versatile"

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
*   **Log a Decision**:
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

---

## Cognee API Usage

DevMind utilizes the full lifecycle of the Cognee memory layer:
*   `cognee.remember(content, dataset_name)`: Used to ingest source files, git commits, comments, and decision logs into the graph.
*   `cognee.recall(query_text)`: Used to retrieve relevant codebase context when querying memory.
*   `cognee.improve(dataset)`: Used during refresh commands to re-enrich the graph and prune stale nodes.
*   `cognee.forget(dataset_name)`: Used during surgical forget commands to erase memory of specific files/namespaces.

---

## Claude Code MCP Integration

To connect Claude Code to DevMind's memory, add the server to your Claude MCP config:

```bash
claude mcp add devmind "python -m devmind.integrations.claude_code"
```

Alternatively, configure your project-level `.mcp.json` file in your project root:
```json
{
  "mcpServers": {
    "devmind": {
      "command": "python",
      "args": ["-m", "devmind.integrations.claude_code"]
    }
  }
}
```

---

## AI Assistant Declaration

Per the rules of **The Hangover Part AI Hackathon**, this project declares the use of **Claude** (via the Antigravity IDE agent) as an AI pair programmer.
