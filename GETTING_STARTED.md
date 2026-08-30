# 🚀 DevMind Getting Started Guide

Welcome to DevMind! This guide will help you set up codebase semantic memory and interactive chat for your projects in under 3 minutes.

---

## 📋 Prerequisites
Before you start, make sure you have:
*   **Python 3.10 or higher** installed on your system (`python --version` to check).
*   **git** installed and on your PATH.
*   An API key from **Groq**, **Gemini**, **Anthropic**, **OpenAI**, or **OpenRouter** — or a local **Ollama** install if you'd rather run 100% offline.

> ⚠️ Installing pulls in `cognee[fastembed]`, which brings a fairly heavy
> dependency tree (onnxruntime, transformers, etc.). Expect the install to
> take a few minutes on a normal connection, and note that on Apple Silicon
> or 32-bit Python, some of those transitive wheels may not be prebuilt for
> your platform.

---

## ⚡ 1. Installation

Install DevMind globally or in your active virtual environment using `pip`:

```bash
pip install devmind-cli
```

*(Note: the PyPI package is `devmind-cli`, but the command you run is `devmind`.)*

---

## ⚙️ 2. Environment Configuration

DevMind requires an LLM provider to construct and query your codebase's knowledge graph.
The easiest way to configure one is the interactive wizard — run it from your project root:

```bash
devmind init
```

It walks you through Groq, Gemini, Anthropic, OpenAI, Ollama, or OpenRouter, verifies the
connection live, and saves the config either globally (`~/.config/devmind/config.json`,
applies to every project) or locally (`.env` in the current project only).

If you'd rather configure it by hand, create a `.env` in your project root:

```ini
# Groq (fast, generous free tier) — supports comma-separated key rotation
LLM_PROVIDER=groq
GROQ_API_KEYS=gsk_key1,gsk_key2,gsk_key3

# or Gemini
LLM_PROVIDER=gemini
GEMINI_API_KEYS=AIza_key1,AIza_key2

# or OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-proj-your_openai_key
```

See [`.env.example`](.env.example) for the full list of supported variables.

---

## 🧠 3. Under the Hood: What about Cognee?

**You don't need to install or configure any databases!** 

On your first run of DevMind, the CLI automatically hooks into the **Cognee** engine to initialize:
1.  **LanceDB**: A local vector database to store code token embeddings.
2.  **Kuzu Graph DB**: A local graph database mapping relationships between functions, comments, and files.
3.  **SQLite**: A relational database to manage dataset partitions.

All data is stored locally inside your project root directory under hidden folders (`.cognee_system/`, `.cognee_data/`, `.cognee_cache/`). If your project already has a `.gitignore`, DevMind automatically appends entries for these folders the first time it initializes — so they're never accidentally committed.

---

## 💻 4. Basic Usage Commands

Now, run the commands from your project root:

### Step 0 (optional): Check your setup
```bash
devmind doctor
```
Verifies Python version, git, your AI provider's connectivity, local memory integrity, and FastEmbed readiness — good to run first if anything looks off.

### Step 1: Ingest the Codebase
Index your codebase files, git history, and inline tasks into graph memory:
```bash
devmind remember
```
This runs in fast, local-only mode by default (0 API calls). On a **large monorepo**,
this scans and holds every matched file in memory before ingesting — for very large
repos, prefer `devmind remember --incremental` after the first full run to only
re-index changed files.

### Step 2: Open the Interactive Chat
Start a clean, styled terminal chat session to query your codebase:
```bash
devmind chat
```

### Step 3: Run the Web Dashboard UI
If you prefer a visual web interface to explore your codebase memory nodes:
```bash
devmind dashboard --port 8000
```
*(Open http://localhost:8000 in your browser)*

---

## 🧹 How to Reset Memory
If you refactored your code and want to completely clear and rebuild your local databases:
```bash
devmind forget --all
devmind remember
```

---

## 🩹 Known Limitations & Tips
* **Shallow git clones** (e.g. `git clone --depth 1`, common in CI/CD) give `devmind blame`
  and `devmind drift` very little history to work with — ownership/churn data will be
  sparse. Use a full clone (or `git fetch --unshallow`) for accurate results.
* **Corporate proxies**: DevMind's network calls (version checks, provider verification)
  respect the standard `HTTPS_PROXY`/`HTTP_PROXY` environment variables.
* **Non-Python codebases**: file ingestion, secret scanning, and drift/blame all work
  across languages, but `devmind health`'s complexity/dead-import analysis is currently
  Python-AST-only — other languages will show 0 for those specific metrics.
