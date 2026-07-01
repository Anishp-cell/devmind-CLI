# 🚀 DevMind Getting Started Guide

Welcome to DevMind! This guide will help you set up codebase semantic memory and interactive chat for your projects in under 3 minutes.

---

## 📋 Prerequisites
Before you start, make sure you have:
*   **Python 3.10 or higher** installed on your system.
*   An API key from **Groq** (free/fast), **OpenRouter**, or **OpenAI**.

---

## ⚡ 1. Installation

Install DevMind globally or in your active virtual environment using `pip`:

```bash
pip install devmind-cli
```

---

## ⚙️ 2. Environment Configuration

DevMind requires an LLM provider to construct and query your codebase's knowledge graph. Navigate to the root directory of your project and create a `.env` file:

### Option A: Using Groq (Recommended & Free)
Set `LLM_PROVIDER` to `groq` and provide your API keys. We support **API key rotation** (comma-separated keys) to maximize throughput limits:

```ini
LLM_PROVIDER=groq
GROQ_API_KEYS=gsk_key1,gsk_key2,gsk_key3

# Optional: Switch to the high-limit 8B model to prevent Rate Limits during large ingestions
LLM_MODEL_GROQ=groq/llama-3.1-8b-instant
```

### Option B: Using OpenRouter
If you use OpenRouter, paste your key starting with `sk-or-v1-` (we will automatically map it to the OpenRouter endpoint):

```ini
LLM_PROVIDER=groq
GROQ_API_KEY=sk-or-v1-your_openrouter_key
```

### Option C: Using OpenAI
Set `LLM_PROVIDER` to `openai` and provide your standard API key:

```ini
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-proj-your_openai_key
```

---

## 🧠 3. Under the Hood: What about Cognee?

**You don't need to install or configure any databases!** 

On your first run of DevMind, the CLI automatically hooks into the **Cognee** engine to initialize:
1.  **LanceDB**: A local vector database to store code token embeddings.
2.  **Kuzu Graph DB**: A local graph database mapping relationships between functions, comments, and files.
3.  **SQLite**: A relational database to manage dataset partitions.

All data is stored locally inside your project root directory under hidden folders (`.cognee_system/` and `.cognee_data/`). These are automatically added to your project's `.gitignore` rules.

---

## 💻 4. Basic Usage Commands

Now, run the commands from your project root:

### Step 1: Ingest the Codebase
Index your codebase files, git history, and inline tasks into graph memory:
```bash
python -m devmind.cli remember --dir .
```

### Step 2: Open the Interactive Chat
Start a clean, styled terminal chat session to query your codebase:
```bash
python -m devmind.cli chat
```

### Step 3: Run the Web Dashboard UI
If you prefer a visual web interface to explore your codebase memory nodes:
```bash
python -m devmind.cli dashboard --port 8000
```
*(Open http://localhost:8000 in your browser)*

---

## 🧹 How to Reset Memory
If you refactored your code and want to completely clear and rebuild your local databases:
```bash
python -m devmind.cli log --all
```
