# DevMind — Semantic Codebase Memory & Intelligence Engine

> **"Your codebase finally has a persistent memory."**  
> An open-source, local-first Codebase Memory and Static Intelligence Engine powered by **Cognee**, **FastEmbed**, **LanceDB**, and **FastMCP**.

[![PyPI Version](https://img.shields.io/pypi/v/devmind-cli.svg)](https://pypi.org/project/devmind-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastMCP](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)

New here? See [GETTING_STARTED.md](GETTING_STARTED.md) for a full walkthrough, or [CHANGELOG.md](CHANGELOG.md) for recent changes.

---

## ✨ Offline Intelligence Commands (Zero API Calls)

Beyond persistent memory, DevMind ships a full offline static-analysis toolkit — no LLM, no API key, no network required:

| Command | What it does |
|---|---|
| `devmind doctor` | Diagnoses your environment: Python version, git, AI provider connectivity, local memory integrity, FastEmbed readiness |
| `devmind health` | Complexity hotspots, code smells, tech-debt tags, dead imports, test-coverage gaps — 0-100 score with CI gate |
| `devmind onboard` | Instant onboarding guide: tech stack, setup/run/test commands, core architectural files |
| `devmind impact <target>` | Blast-radius analysis: who calls this function/class, transitive ripple, impacted tests, risk score |
| `devmind drift` | Circular imports, layer-boundary violations, churn × complexity fragility hotspots |
| `devmind blame <file>` | True code ownership %, meaningful-commit timeline, collision risk, related ADRs |
| `devmind secure` | Hardcoded secrets, dangerous sinks, injection risks, crypto weaknesses, known CVEs |

---

## ⚡ Quickstart (30 Seconds)

Get up and running in any project with just three commands:

```bash
# 1. Install via PyPI
pip install devmind-cli

# 2. Interactive Setup (Configure free Cloud API or 100% Local Ollama)
devmind init

# 3. Index Codebase & Ask Questions
devmind remember
devmind ask "Where is the authentication flow handled and how are tokens validated?"
```

---

## 🦙 100% Local & Offline Setup with Ollama (Step-by-Step)

If you want **complete data privacy** with zero tokens leaving your machine, you can run DevMind entirely on local models using **Ollama**:

### Step 1: Install Ollama
Download and install Ollama for your operating system:
* **macOS / Windows**: Download from [ollama.com](https://ollama.com/download)
* **Linux**:
  ```bash
  curl -fsSL https://ollama.com/install.sh | sh
  ```

### Step 2: Download a Coding Model
Open your terminal and pull your preferred model:
```bash
# Recommended lightweight model (Fast & works on any laptop):
ollama pull llama3.2

# Recommended for high-accuracy coding tasks:
ollama pull qwen2.5-coder:7b
# or
ollama pull mistral
```

### Step 3: Ensure Ollama Server is Running
On **macOS/Windows**, the Ollama.app/desktop app starts the server automatically once installed — nothing else to do.
On **Linux** (or if you're not running the desktop app), start it manually:
```bash
ollama serve
```
*(By default, Ollama is accessible at `http://localhost:11434`. If you already have Ollama.app running, `ollama serve` will just report the port is in use — that's fine, it means it's already up.)*

### Step 4: Configure DevMind for Ollama
Run the DevMind setup wizard:
```bash
devmind init
```
1. Select option **`[5] 🦙 Ollama`**.
2. Press Enter to accept the default base URL (`http://localhost:11434`).
3. Enter the model name you pulled (e.g. `llama3.2` or `qwen2.5-coder:7b`).
4. DevMind will test the local connection and save your configuration globally.

> 💡 **Zero-Cost Local Embeddings**: DevMind uses local CPU-accelerated `FastEmbed` (`BAAI/bge-small-en-v1.5`) for vector indexing. No embeddings are sent to external APIs!

---

## ⚡ Free Cloud AI Providers (Groq & Google Gemini)

If you prefer cloud models without needing local GPU/RAM:

* **⚡ Groq (Recommended - Ultra Fast & 100% Free)**:
  1. Get a free API key at [console.groq.com/keys](https://console.groq.com/keys).
  2. Run `devmind init` and choose `[1] Groq`.
* **♊ Google Gemini (Generous Free Tier)**:
  1. Get a free API key at [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).
  2. Run `devmind init` and choose `[2] Gemini`.
* **🟣 Anthropic Claude / 🟢 OpenAI / 🌐 OpenRouter**:
  Run `devmind init` to configure Claude (`claude-3-5-sonnet`), OpenAI (`gpt-4o-mini`, `o3-mini`), or OpenRouter keys.

---

## 🛠️ CLI Command Reference

### 🧠 1. Memory & Knowledge Ingestion
* **`devmind remember`**: Scans files, AST symbols, comments, and git history into local graph-vector memory.
  ```bash
  devmind remember                # Fast local mode (0 API calls, instant)
  devmind remember --incremental  # Only scan changed files in git diff
  devmind remember --deep         # Run LLM entity extraction
  ```
* **`devmind ask "<query>"`**: Ask plain-English questions about codebase architecture.
  ```bash
  devmind ask "How does payment retry logic work on webhook timeout?"
  ```
* **`devmind chat`**: Start an interactive terminal REPL session to explore code.
  ```bash
  devmind chat
  ```
* **`devmind log "<decision>"`**: Record an Architectural Decision Record (ADR) into persistent memory.
  ```bash
  devmind log "Chose SQLite/LanceDB locally to ensure zero infrastructure overhead."
  ```

---

### 🔬 2. Code Quality & Health Analysis
* **`devmind health`**: Scans the codebase for technical debt, complexity hotspots, code smells, dead imports, and test coverage gaps (100% offline).
  ```bash
  devmind health                        # Rich terminal dashboard
  devmind health --output report.md     # Export Markdown report
  devmind health --threshold 75         # CI quality gate (exit code 1 if score < 75)
  ```

---

### 🗺️ 3. Visual Graphs & Architecture Digests
* **`devmind graph`**: Launch an interactive browser graph of codebase symbols and relationships.
  ```bash
  devmind graph --port 8000
  ```
* **`devmind digest`**: Generate a structured Markdown architecture map of classes, functions, and files.
  ```bash
  devmind digest --output ARCHITECTURE_MINDMAP.md
  ```
* **`devmind dashboard`**: Open the local web management dashboard.
  ```bash
  devmind dashboard
  ```

---

### ⚙️ 4. Configuration & Maintenance
* **`devmind init`**: Interactive setup wizard — first-time provider configuration.
* **`devmind config`**: View your active provider/model/embedding config, switch provider, update just a key or model, or diff global vs local config.
* **`devmind doctor`**: Diagnose your environment — Python version, git, AI provider connectivity, local memory integrity, FastEmbed readiness, update status.
  ```bash
  devmind doctor
  ```
* **`devmind refresh`**: Re-scan changed files and refine relationship links in graph memory.
* **`devmind forget`**: Surgically remove a file or wipe local memory.
  ```bash
  devmind forget --file auth/middleware.py   # Delete specific file memory
  devmind forget --all                      # Wipe local memory databases
  ```

### 🔧 Environment Variables
* `DEVMIND_NO_UPDATE_CHECK=1` — disable the background PyPI update-check notification (useful for CI).
* `DEVMIND_RECALL_TOP_K` — number of memory chunks returned per query (default `3`, capped at `20`).
* `CI=1` — also disables the update check automatically (most CI runners set this already).

---

## 🤖 Agentic IDE Integration (Claude Code & Cursor via MCP)

Connect DevMind's persistent memory directly to autonomous agents like **Claude Code**, **Cursor Agent**, or **Windsurf** using the Model Context Protocol:

### Claude Code Setup:
```bash
claude mcp add devmind "devmind mcp"
```

### Cursor / Project `.mcp.json` Setup:
Create a `.mcp.json` file in your repository root:
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
DevMind's MCP server exposes two tools to your AI assistant:
* **`query_codebase_memory(query)`** — queries the persistent knowledge graph for architectural context, past decisions, or git history.
* **`log_architectural_decision(decision)`** — logs a new ADR into memory when the assistant makes a major design change.

*Your AI assistant can now call these automatically instead of burning 50,000+ tokens blindly reading random files!*

---

## 📄 License

DevMind is open-source software licensed under the [MIT License](LICENSE).
