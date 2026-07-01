# DevMind: Architecture Deep Dive

DevMind is a powerful, local-first Semantic Codebase Memory tool. It acts exactly like the Gemini CLI, but is deeply integrated into your specific local repository using graph-based memory storage and Model Context Protocol (MCP) tool bindings.

This document outlines how each system component operates, its real-world utility, and our roadmap for future robustness.

---

## 🏗️ 1. Architecture: How Each Part Works

DevMind is composed of three distinct functional layers: **Ingestion**, **Memory (Graph & Vector)**, and **Interfaces**.

### The Ingestion Engine (`devmind.ingestion`)
Before we can query a codebase, we have to prepare and extract meaningful context.
*   **File Parsing**: We scan your directory while explicitly respecting `.gitignore` rules and skipping binary/media files. 
*   **Targeted Comment Extraction (`comment_extractor.py`)**: DevMind doesn't just read code blindly; it runs Regex parsing to extract specific inline engineering comments: `TODO`, `FIXME`, `HACK`, and `NOTE`. It binds these comments to their exact line numbers and file paths.
*   **Git Integration (`git_parser.py`)**: It extracts the `git log` to provide historical context of why changes were made.

### The Memory & Graph Layer (`devmind.memory`)
The core intelligence engine uses the **Cognee** library to orchestrate LanceDB (Vector) and Kuzu (Graph) storage.
*   **Embedding & Storage**: Text chunks and extracted comments are transformed into vector embeddings using `fastembed`. They are then mapped into a local knowledge graph.
*   **Hybrid Query Execution (`RAG_COMPLETION`)**: When a user queries DevMind, we bypass traditional strict vector lookups. We force `SearchType.RAG_COMPLETION`, which executes a hybrid search:
    1.  Finds the most semantically similar code chunks via Vector Similarity.
    2.  Traverses the graph edges connected to those chunks to retrieve surrounding functions, file metadata, and comment context.
    3.  Pipes the combined context into the LLM (Llama 3.3 70B via OpenRouter/Groq) for a synthesized answer.
*   **Parallel Dataset Routing**: To prevent missing data across namespaces, queries are mapped to execute concurrently (`asyncio.gather`) across all dynamically generated `code_comments_*` datasets.

### Interfaces (CLI, Dashboard, MCP)
*   **CLI (`devmind.cli`)**: Built heavily on `typer` and `rich`. It offers a gorgeous, persistent interactive REPL loop (`devmind chat`) with markdown formatting, loading spinners, and graceful shutdown handlers.
*   **Web Dashboard (`devmind.web`)**: A lightweight `FastAPI` application using `Jinja2` templates. It reads the local graph and provides a visual web UI for non-CLI users to explore memory.
*   **Model Context Protocol (`devmind.integrations.claude_code.py`)**: Uses `fastmcp` to expose DevMind as a local server tool. This allows AI assistants like **Claude Desktop** or **Cursor** to autonomously invoke DevMind to fetch exact codebase context without hallucinating.

---

## 🌍 2. Real-World Utility

Why does this tool matter for enterprise codebases?

1.  **Instant Engineer Onboarding**: New hires usually spend weeks understanding "Why was this written this way?" DevMind allows them to ask: *"How does the checkout flow handle failures?"* and instantly receive an answer mapped from hidden `README` files and `HACK` comments.
2.  **Tribal Knowledge Preservation**: Often, critical tech debt is hidden in `FIXME` comments scattered across 500 files. DevMind makes all tech debt semantically searchable from the terminal.
3.  **Agentic AI Context**: Standard AI coding assistants fail on large repositories because they cannot read 10,000 files at once. By hooking DevMind into **MCP**, your AI assistant can query DevMind to fetch the *exact 5 relevant files* needed to fix a bug, drastically reducing token costs and hallucination.

---

## 🚀 3. Future Roadmap: Robustness & Applicability

To scale DevMind from a hackathon prototype to an enterprise-grade production tool, the following areas will be improved:

### A. Incremental Ingestion & File Hashing
*   **Current State**: Running `devmind remember` reparses the entire repository from scratch.
*   **Improvement**: Implement MD5/SHA-256 file hashing. During ingestion, DevMind will only update graph nodes for files whose hash has changed since the last run. This reduces ingestion time from minutes to milliseconds.

### B. Graceful Windows Socket Resilience
*   **Current State**: DevMind relies on a custom `sys.excepthook` and asyncio exception swallowers to hide noisy `10038` and `Event loop is closed` errors thrown by Windows Proactor teardowns during Kuzu/LanceDB shutdown.
*   **Improvement**: Implement explicit connection lifecycle managers that cleanly tear down the graph engines before the `typer` process exits.

### C. True AST (Abstract Syntax Tree) Graph Parsing
*   **Current State**: Code is treated largely as flat text/markdown chunks.
*   **Improvement**: Integrate Python `ast` (or Tree-sitter for multi-language) to explicitly map functions, classes, and variable dependencies as native graph nodes. This will enable structural queries like: *"Which modules import the calculate_tax function?"*

### D. Remote & Distributed Memory Sync
*   **Current State**: Codebase memory is stored entirely locally inside the `.cognee_system` directory.
*   **Improvement**: Add the ability to sync the graph database to a remote server (e.g., S3 buckets, PostgreSQL, or managed Neo4j). This allows an entire engineering team to share the exact same codebase memory state, updated dynamically via CI/CD pipelines upon every git merge.
