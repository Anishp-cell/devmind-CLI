# DevMind: Master Architecture, System Design & Interview Guide

> **"Your codebase finally has a persistent memory."**  
> An open-source, local-first Codebase Memory and Agentic Search engine built on top of **Cognee**, **LanceDB**, **Kuzu Graph DB**, and **FastMCP**.

---

## 📑 Table of Contents
1. [Executive Summary: What is DevMind?](#1-executive-summary-what-is-devmind)
2. [The Core Problem: The "AI Hangover" & The Context Tax](#2-the-core-problem-the-ai-hangover--the-context-tax)
3. [System Architecture & Data Flow (with Diagrams)](#3-system-architecture--data-flow)
4. [Step-by-Step Pipeline Execution Flow](#4-step-by-step-pipeline-execution-flow)
5. [Storage Layer Deep Dive: Hybrid Graph-Vector Topology](#5-storage-layer-deep-dive-hybrid-graph-vector-topology)
6. [How DevMind RAG Works (Retrieval-Augmented Generation)](#6-how-devmind-rag-works)
7. [Why Cognee? (Technical Rationale & Tradeoffs)](#7-why-cognee-technical-rationale--tradeoffs)
8. [Daily Developer Workflow & Real-World Integration](#8-daily-developer-workflow--real-world-integration)
9. [50 Technical Interview Questions & Deep Answers](#9-50-technical-interview-questions--deep-answers)
   - [Domain 1: System Design & Architecture (Q1–Q7)](#domain-1-system-design--architecture)
   - [Domain 2: Local Ingestion, AST & Multi-Language Parsing (Q8–Q14)](#domain-2-local-ingestion-ast--multi-language-parsing)
   - [Domain 3: Vector Embeddings, FastEmbed & Storage Engines (Q15–Q21)](#domain-3-vector-embeddings-fastembed--storage-engines)
   - [Domain 4: Graph Databases, Kuzu & Knowledge Representation (Q22–Q28)](#domain-4-graph-databases-kuzu--knowledge-representation)
   - [Domain 5: Hybrid RAG, Retrieval & Context Synthesis (Q29–Q35)](#domain-5-hybrid-rag-retrieval--context-synthesis)
   - [Domain 6: Multi-Provider LLM Routing & Key Rotation (Q36–Q40)](#domain-6-multi-provider-llm-routing--key-rotation)
   - [Domain 7: Asyncio, Event Loops & Process Lifecycle (Q41–Q45)](#domain-7-asyncio-event-loops--process-lifecycle)
   - [Domain 8: Model Context Protocol (MCP) & Agent Integration (Q46–Q50)](#domain-8-model-context-protocol-mcp--agent-integration)

---

## 1. Executive Summary: What is DevMind?

**DevMind** is a local-first, developer-centric CLI and Model Context Protocol (MCP) service that builds and maintains a **persistent, queryable memory graph of any codebase**. 

Instead of treating code as dumb flat text or re-uploading thousands of files to external LLM context windows on every prompt, DevMind extracts:
1. **Structural AST Semantics** (Classes, methods, function signatures, module imports, inheritance).
2. **Temporal Git Context** (Commit history, diff summaries, authorship, evolutionary rationale).
3. **Developer Intent & Annotations** (Inline comments: `TODO`, `FIXME`, `BUG`, `HACK`, `NOTE`, `ADR`).
4. **Architectural Decision Records (ADRs)** (Logged human reasoning and design constraints).

It indexes these inputs into a **hybrid knowledge store** combining a **Graph Database (Kuzu)** with a **Vector Database (LanceDB)**. At query time, DevMind uses **Hybrid Graph-Vector RAG** to retrieve surgically accurate context and synthesize grounded answers in milliseconds—without burning API tokens during ingestion.

---

## 2. The Core Problem: The "AI Hangover" & The Context Tax

Modern AI coding assistants (Claude Code, Cursor, Copilot, ChatGPT) suffer from **ephemeral statelessness**:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        The "AI Hangover" Loop                          │
│                                                                        │
│   New Session ──> "What is this repo?" ──> Dump 50 Files (Slow/OOM)    │
│        ▲                                             │                 │
│        │                                             ▼                 │
│   Close Terminal <── High Token Cost <── Hallucinated Schema / Diffs   │
└────────────────────────────────────────────────────────────────────────┘
```

### The 5 Major Pain Points:
1. **The Context Tax**: Developers spend 5–15 minutes every session re-explaining architectures, pointing out utility files, and copying schemas.
2. **The Agentic IDE Token Drain (Antigravity, Claude Code, Codex, Cursor Agent)**:
   - When you prompt an autonomous terminal agent with a task like *"Refactor payment retries"*, the agent blindly runs recursive `grep_search`, `list_dir`, and `view_file` calls across dozens of files just to understand where dependencies live.
   - This burns **50,000 to 100,000+ context tokens** in exploratory loops before a single line of code is written!
   - By the time the agent attempts the fix, the context window is diluted with raw file dumps, attention degrades ("lost in the middle"), and the agent hallucinates function signatures.
3. **Context Window Exhaustion & Hallucination**: Dumping 100+ files into an LLM window degrades attention, increases latency, and risks code hallucination.
4. **Loss of Tribal Knowledge & Intent**: Flat code search (grep/ripgrep) cannot tell you *why* an edge case was handled or *what* commit changed a critical database invariant.
5. **Ingestion Cost & Rate Limiting**: Naive RAG tools send entire codebases to cloud LLMs for summarization, exhausting free-tier API rate limits (HTTP 429) within minutes.

### The DevMind Solution:
DevMind decouples **Ingestion** (zero API tokens, deterministic AST + local CPU embeddings) from **Querying** (hybrid graph traversal + minimal surgical LLM context).

---

## 3. System Architecture & Data Flow

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                                    DEVMIND ARCHITECTURE                                  │
└──────────────────────────────────────────────────────────────────────────────────────────┘

       DEVELOPER INTERFACES
  ┌───────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
  │ Typer CLI     │   │ Claude Code / Cursor   │   │ FastAPI Web Dashboard  │
  │ (devmind ...) │   │ (via FastMCP Server)   │   │ (localhost:8000)       │
  └───────┬───────┘   └───────────┬────────────┘   └───────────┬────────────┘
          │                       │                            │
          └───────────────────────┼────────────────────────────┘
                                  │
                                  ▼
 ┌─────────────────────────────────────────────────────────────────────────────────────────┐
 │                               1. INGESTION ENGINE                                       │
 │                                                                                         │
 │  ┌───────────────────────┐  ┌────────────────────────┐  ┌────────────────────────────┐  │
 │  │ File Reader           │  │ Deterministic AST      │  │ Comment & Tag Extractor    │  │
 │  │ (.gitignore compliant,│  │ (Python ast, JS/TS,    │  │ (TODO, FIXME, BUG, HACK,   │  │
 │  │  binary auto-skip)    │  │  Go, Rust parsers)     │  │  docstrings, ADRs)         │  │
 │  └───────────┬───────────┘  └───────────┬────────────┘  └─────────────┬──────────────┘  │
 │              │                          │                             │                 │
 │              └──────────────────────────┼─────────────────────────────┘                 │
 │                                         ▼                                               │
 │                           ┌───────────────────────────┐                                 │
 │                           │ Git History Parser        │                                 │
 │                           │ (Commit diffs, author logs│                                 │
 │                           └─────────────┬─────────────┘                                 │
 └─────────────────────────────────────────┼───────────────────────────────────────────────┘
                                           │
                                           ▼
 ┌─────────────────────────────────────────────────────────────────────────────────────────┐
 │                               2. MEMORY WRAPPER (Cognee)                                │
 │                                                                                         │
 │  ┌───────────────────────────────────────────────────────────────────────────────────┐  │
 │  │ Fast Cognify Pipeline (Local Embeddings - FastEmbed ONNX BAAI/bge-small-en-v1.5)  │  │
 │  │ -> 0 Cloud LLM Calls during Ingestion -> Runs 100% on CPU                         │  │
 │  └──────────────────────────────┬────────────────────────────────────────────────────┘  │
 │                                 │                                                       │
 │         ┌───────────────────────┴────────────────────────┐                              │
 │         ▼                                                ▼                              │
 │  ┌───────────────────────────────┐            ┌──────────────────────────────────────┐  │
 │  │ Relational & Vector Layer     │            │ Knowledge Graph Layer                │  │
 │  │ LanceDB (Dense Vectors: 384d) │            │ Kuzu Graph DB (Nodes & Relational    │  │
 │  │ SQLite (Document Chunks)      │            │ Code Entities, Commits, Tags)        │  │
 │  └──────────────┬────────────────┘            └──────────────────┬───────────────────┘  │
 └─────────────────┼────────────────────────────────────────────────┼──────────────────────┘
                   │                                                │
                   └───────────────────────┬────────────────────────┘
                                           │
                                           ▼
 ┌─────────────────────────────────────────────────────────────────────────────────────────┐
 │                               3. QUERY & RECALL ENGINE                                  │
 │                                                                                         │
 │  ┌───────────────────────────────────────────────────────────────────────────────────┐  │
 │  │ Hybrid Search (Vector Cosine Match + Graph Neighborhood Traversal)                │  │
 │  └──────────────────────────────────────┬────────────────────────────────────────────┘  │
 │                                         ▼                                               │
 │  ┌───────────────────────────────────────────────────────────────────────────────────┐  │
 │  │ Smart Multi-Key LLM Router (Groq Llama-3.3-70B / Gemini-Flash / Ollama Local)     │  │
 │  │ + Rate-Limit Cooldown Tracker + 4.5s Request Throttling Lock                      │  │
 │  └──────────────────────────────────────┬────────────────────────────────────────────┘  │
 │                                         ▼                                               │
 │                         ┌─────────────────────────────┐                                 │
 │                         │ Rich Terminal Response UI   │                                 │
 │                         │ Grounded, Context-Rich Code │                                 │
 │                         └─────────────────────────────┘                                 │
 └─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Step-by-Step Pipeline Execution Flow

### Phase 1: Ingestion (`devmind remember`)
1. **Workspace Discovery**: `file_reader.py` crawls project directory starting from root, respecting `.gitignore` rules and discarding binaries/virtualenvs.
2. **AST Extraction**: `ast_parser.py` parses source files into structural symbol dictionaries (classes, functions, arguments, docstrings, imports).
3. **Temporal Ingestion**: `git_parser.py` extracts recent commit messages, authors, timestamps, and file diff summaries.
4. **Intent Extraction**: `comment_extractor.py` scans lines for `TODO`, `FIXME`, `HACK`, and `ADR` comments.
5. **Raw Persistence**: Content is passed to `cognee.add()`, registering datasets in relational SQLite.
6. **Local Vector Ingestion (`_fast_cognify`)**:
   - `classify_documents`: Maps raw text items into typed document entities.
   - `extract_chunks_from_documents`: Splits text into semantically coherent tokens.
   - `add_data_points`: Generates 384-dimensional vector embeddings locally using FastEmbed (ONNX runtime on CPU) and stores them in LanceDB without any cloud API requests.

### Phase 2: Querying (`devmind ask "<query>"`)
1. **Dynamic Key Resolution**: `memory.py` selects an active API key from rotation pool (`_GROQ_API_KEYS`, `_GEMINI_API_KEYS`), bypassing keys currently in cooldown.
2. **Dataset Resolution**: Identifies project root and maps query to project dataset (`devmind_<folder_name>`).
3. **Hybrid RAG Recall (`cognee.recall`)**:
   - **Vector Search**: Computes query embedding and performs Approximate Nearest Neighbor (ANN) search over LanceDB chunks.
   - **Graph Traversal**: Explores connected AST symbol nodes and comment metadata in Kuzu.
   - **Fallback Mechanism**: If full RAG search returns empty, falls back to raw vector chunk retrieval (`SearchType.CHUNKS`).
4. **Context Synthesis**: Feeds retrieved graph-vector context into LLM (Llama 3.3 70B / Gemini 2.5 Flash) with strict prompt boundaries.
5. **Output Presentation**: Formats response in a stylized Rich cyan box.

---

## 5. Storage Layer Deep Dive: Hybrid Graph-Vector Topology

DevMind utilizes three specialized storage engines in tandem:

| Engine | Storage Type | Role in DevMind |
|---|---|---|
| **LanceDB** | Embedded Vector DB (Serverless, disk-backed) | Stores 384-dimensional FastEmbed embeddings for dense semantic similarity search. |
| **Kuzu DB** | Embedded Graph DB (Columnar, Cypher-compatible) | Stores relational code entities (Classes $\to$ Methods $\to$ Imports $\to$ Commits) as graph nodes and directed edges. |
| **SQLite** | Embedded Relational DB | Manages pipeline run ledgers, dataset namespaces, file metadata, and pipeline execution checkpoints. |

### Graph Schema Structure:
```
(FileNode) ──[:CONTAINS]──> (ClassNode) ──[:DECLARES]──> (MethodNode)
    │                                                          │
    ├──[:IMPORTS]──> (ModuleNode)                              ├──[:HAS_TAG]──> (CommentNode: TODO/BUG)
    │                                                          │
    └──[:MODIFIED_BY]──> (CommitNode) ──[:AUTHORED_BY]──> (AuthorNode)
```

---

## 6. How DevMind RAG Works

DevMind implements **Hybrid Graph-Vector RAG (SearchType.RAG_COMPLETION)**:

```
 User Query: "Why did we switch to Redis for caching?"
                     │
                     ├──────────────────────────────────────────────┐
                     ▼                                              ▼
          [ 1. Dense Vector Search ]                     [ 2. Graph Traversal ]
      Query Embed (bge-small-en-v1.5)               Entity Match: "Redis", "Cache"
                     ▼                                              ▼
        Top-K LanceDB Code Chunks                     Kuzu Graph Neighborhood
      - redis_client.py (0.89 similarity)           - Commit: "feat: replace memcached"
      - cache_manager.py (0.84 similarity)          - ADR: "ADR-004: Redis Cluster Decision"
                     │                                              │
                     └──────────────────────┬───────────────────────┘
                                            ▼
                          [ 3. Context Aggregator & Reranker ]
                             Deduplicated Context Window
                                            ▼
                          [ 4. LLM Response Synthesis ]
                             Llama 3.3 70B / Gemini Flash
                                            ▼
                          [ 5. Grounded Markdown Answer ]
```

---

## 7. Why Cognee? (Technical Rationale & Tradeoffs)

We selected **Cognee** as our core memory layer framework after evaluating LangChain, LlamaIndex, and custom graph pipelines.

### Why Cognee Won:
1. **Native Hybrid Data Model**: Cognee unifies relational tables, vector spaces, and graph topologies into a single pipeline abstraction (`add()`, `cognify()`, `recall()`, `improve()`, `forget()`).
2. **Self-Contained Embedded Footprint**: Rather than requiring external infrastructure (Dockerized Neo4j, Milvus, Redis), Cognee runs embedded via Kuzu and LanceDB, keeping DevMind a zero-dependency CLI.
3. **Modular Task Pipeline Engine**: Cognee's task graph allows custom task insertion (`_fast_cognify`), letting us bypass heavy LLM entity extraction and replace it with deterministic AST parsing.
4. **Surgical Memory Management (`forget`)**: Supports dataset namespace pruning, allowing developers to wipe or re-index specific files on `git diff` changes without re-indexing the whole repo.

---

## 8. Daily Developer Workflow & Real-World Integration

### Workflow 1: Onboarding to an Unfamiliar Codebase
```bash
git clone https://github.com/org/large-legacy-repo.git
cd large-legacy-repo
devmind remember
devmind ask "Explain the authentication flow from middleware to database"
devmind ask "Are there any open BUG or FIXME comments in the billing module?"
```

### Workflow 2: Autonomous Claude Code / Cursor Assistance
Configure `.mcp.json`:
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
*Now, when you ask Claude Code: "Fix the webhook retry bug", Claude invokes DevMind's MCP tool in the background, fetches exact graph relationships, and edits the code without hallucinations.*

### Workflow 3: Capturing Architecture Decisions
```bash
devmind log "ADR-012: Migrated queue workers from Celery to ARQ to support native asyncio loop."
```

---

## 9. 50 Technical Interview Questions & Deep Answers

---

### Domain 1: System Design & Architecture

#### Q1: How does DevMind architecturally solve the context limitation problem of LLM coding assistants?
**Answer:** DevMind decouples knowledge ingestion from LLM inference. Instead of dumping raw file trees into an LLM context window, DevMind parses files into deterministic AST symbols, git diffs, and developer tags, embedding them into local LanceDB (vector) and Kuzu (graph) databases. At query time, DevMind executes a hybrid RAG lookup to retrieve only the exact top-$k$ graph nodes and text chunks relevant to the user query, compressing a 100,000-line codebase into a ~1,000-token prompt.

#### Q2: What is the high-level architecture of DevMind, and what are its core functional layers?
**Answer:** DevMind consists of five layers:
1. **CLI / Interface Layer**: Typer CLI, FastMCP server, and FastAPI local dashboard.
2. **Ingestion Layer**: Deterministic AST parser (`ast`), regex tag extractors, and GitPython log parsers.
3. **Memory Wrapper Layer**: Cognee lifecycle controller orchestrating `remember`, `recall`, and `forget`.
4. **Hybrid Storage Layer**: LanceDB for vector search, Kuzu for graph traversals, and SQLite for relational run-state.
5. **LLM Routing Layer**: Multi-provider API rotation engine with rate-limit cooldown tracking.

#### Q3: Why is local-first architecture superior for developer memory tools compared to cloud SaaS indexing?
**Answer:**
1. **Privacy & Security**: Proprietary enterprise code never leaves the developer's laptop during ingestion.
2. **Zero Ingestion Cost**: Local AST parsing and FastEmbed CPU embeddings cost \$0.00.
3. **Offline Resilience**: Memory ingestion and local graph exploration function without internet access.
4. **Sub-second Latency**: Querying embedded LanceDB and Kuzu databases eliminates network hops.

#### Q4: How does DevMind handle incremental repository updates instead of re-indexing everything from scratch?
**Answer:** DevMind tracks file modification timestamps and git diffs (`get_changed_files_git_diff()`). In incremental mode (`devmind remember --incremental`), DevMind filters the workspace down to only modified or unstaged files, surgically deletes stale dataset chunks via `cognee.forget()`, and ingests only the modified delta into the graph.

#### Q5: How would you scale DevMind from a local CLI tool to an enterprise-wide shared team memory?
**Answer:**
1. **Storage Decoupling**: Transition LanceDB from embedded files to a remote vector store (e.g., LanceDB Cloud / Qdrant) and Kuzu to a shared Neo4j/Amazon Neptune cluster.
2. **CI/CD Integration**: Run `devmind remember` inside GitHub Actions upon every pull request merge to `main`, publishing updated graph snapshots to a shared object store (S3/GCS).
3. **Authentication & Multi-tenancy**: Use Cognee's tenant isolation to partition code memories by organization, repository, and branch.

#### Q6: How does DevMind prevent race conditions when multiple CLI commands or MCP tools query memory simultaneously?
**Answer:** Memory read operations in LanceDB and Kuzu support concurrent multi-reader access. For LLM API calls, DevMind maintains an asynchronous mutex lock (`_rate_limit_lock = asyncio.Lock()`) and monotonic timestamp tracker (`_last_call_time`) to serialize outbound requests and prevent API throttling.

#### Q7: What design patterns are used in DevMind's codebase?
**Answer:**
- **Adapter Pattern**: Wrapping Cognee's generic engine with specialized CLI commands and MCP tool bindings.
- **Strategy Pattern**: Selectable LLM providers (Groq, Gemini, Ollama, OpenRouter) and embedding backends.
- **Singleton Pattern**: Managed telemetry sessions, database engines, and rate-limit locks.
- **Pipeline Pattern**: Sequential task execution graph (`classify_documents` $\to$ `extract_chunks` $\to$ `add_data_points`).

---

### Domain 2: Local Ingestion, AST & Multi-Language Parsing

#### Q8: Why did DevMind replace LLM-based entity extraction during ingestion with deterministic AST parsing?
**Answer:** LLM-based entity extraction (e.g., asking GPT-4 to extract entities from 50 source files) causes:
1. High token costs (\$2–\$10 per scan).
2. Extreme latency (minutes to hours).
3. Cloud rate limit crashes (HTTP 429).
4. Non-deterministic graph schemas.  
Deterministic AST parsing runs locally in $< 2$ seconds, costs \$0.00, and produces 100% accurate symbol hierarchies.

#### Q9: How does Python's native `ast` module work inside DevMind?
**Answer:** In `ast_parser.py`, `ast.parse(content)` converts Python code into an Abstract Syntax Tree. DevMind traverses `tree.body` using visitor inspection:
- `ast.ClassDef`: Extracts class name, base inheritance classes (`node.bases`), docstrings, and nested methods (`FunctionDef`, `AsyncFunctionDef`).
- `ast.FunctionDef`: Extracts arguments, default values, decorators, and docstrings.
- `ast.Import` / `ast.ImportFrom`: Resolves dependency imports.

#### Q10: How does DevMind parse non-Python languages without requiring heavy language runtime compilers?
**Answer:** DevMind uses compiled regular expression patterns targeting canonical language syntax:
- **JavaScript/TypeScript**: Matches `class Name extends Base`, `export function name()`, `const name = () => {}`, and `import ... from '...'`.
- **Go**: Matches `type Name struct` and receiver functions `func (r *Receiver) Name()`.
- **Rust**: Matches `struct Name`, `enum Name`, `trait Name`, `fn name()`, and `async fn name()`.

#### Q11: How does DevMind extract developer intent from comments?
**Answer:** `comment_extractor.py` scans lines using regular expression patterns against standard engineering tags (`TODO`, `FIXME`, `BUG`, `HACK`, `NOTE`, `ADR`, `WARNING`). It extracts the comment text, associates it with the exact line number and relative file path, and formats it as a structured metadata chunk for vector and graph indexing.

#### Q12: How does DevMind respect `.gitignore` rules during recursive scanning?
**Answer:** DevMind integrates the `pathspec` library (`pathspec.PathSpec.from_lines('gitwildmatch', ...)`). When walking directories via `os.walk()`, it reads the root `.gitignore` and ignores files or directories matching ignore patterns, plus hardcoded safeguards (`.git`, `node_modules`, `__pycache__`, `.venv`, `.cognee_cache`).

#### Q13: How does DevMind sanitize source files to prevent leaking secrets into vector embeddings?
**Answer:** In `file_reader.py`, content is passed through regex sanitizers (`_SECRET_PATTERNS`) that redact API keys (OpenAI `sk-...`, Groq `gsk_...`, GitHub PATs `ghp_...`, Google `AIzaSy...`) prior to embedding generation.

#### Q14: What are the performance characteristics of DevMind's file scanner on large repositories?
**Answer:** By utilizing non-blocking disk I/O, binary file extension filtering, and deterministic in-memory AST extraction, DevMind scans and extracts symbols from ~500 files in under 2.5 seconds on standard consumer CPUs.

---

### Domain 3: Vector Embeddings, FastEmbed & Storage Engines

#### Q15: What embedding model does DevMind use and why?
**Answer:** DevMind uses `BAAI/bge-small-en-v1.5` running on **FastEmbed** (by Qdrant). It outputs 384-dimensional dense vectors. It was chosen because:
1. Runs via ONNX Runtime on local CPU with low RAM footprint (~150MB).
2. Outperforms older 1536d models on the MTEB Retrieval benchmark for code and text.
3. Completely local: zero API keys and zero network latency.

#### Q16: What is FastEmbed and how does it differ from HuggingFace PyTorch models?
**Answer:** FastEmbed executes quantized embedding models using ONNX Runtime directly in C++, bypassing heavy PyTorch and CUDA dependencies. This allows DevMind to run locally on lightweight laptops without requiring GPUs or gigabytes of PyTorch wheel dependencies.

#### Q17: Why did DevMind select LanceDB as its vector database?
**Answer:** LanceDB is an embedded, serverless vector database built on the Lance columnar format. Key benefits:
1. **Zero Server Setup**: Runs in-process within the Python application.
2. **Disk-Backed ANN Search**: Fast IVF-PQ (Inverted File with Product Quantization) index search without holding all vectors in memory.
3. **Multi-Modal & Schema Integration**: Integrates directly with PyArrow and SQLite metadata tables.

#### Q18: What is the mathematical metric used for vector similarity in DevMind?
**Answer:** DevMind uses **Cosine Similarity** over normalized dense vectors:
$$\text{Cosine Similarity}(A, B) = \frac{A \cdot B}{\|A\| \|B\|} = \frac{\sum_{i=1}^n A_i B_i}{\sqrt{\sum_{i=1}^n A_i^2} \sqrt{\sum_{i=1}^n B_i^2}}$$
For normalized embeddings, this reduces to the dot product ($A \cdot B$), enabling ultra-fast vector dot-product ranking in LanceDB.

#### Q19: What chunking strategy is used before embedding code documents?
**Answer:** DevMind uses `TextChunker` with token limits derived from `get_max_chunk_tokens()` (typically 512 tokens with 10% overlap). Chunks are split on semantic code boundaries (functions, classes, paragraphs) rather than arbitrary byte offsets to preserve syntax completeness.

#### Q20: What was the bug where `devmind remember` succeeded but `devmind ask` returned "No relevant memories found"?
**Answer:** `cognee.add()` only ingested raw file text into SQLite relational tables. In fast mode, full `cognee.cognify()` was bypassed to avoid LLM API costs. However, vector embedding generation was inside `cognify()`, meaning LanceDB's `DocumentChunk_text` table was never populated. We solved this by engineering `_fast_cognify()`, which executes document classification, chunking, and FastEmbed vector indexing without invoking LLM summarization.

#### Q21: What is the dimensionality and disk overhead of DevMind's vector index?
**Answer:** Vectors are 384-dimensional float32 arrays (1.5 KB per chunk). For a standard repository of 1,000 code chunks, the total vector index size is under 2 MB.

---

### Domain 4: Graph Databases, Kuzu & Knowledge Representation

#### Q22: What is Kuzu DB and why is it used in DevMind?
**Answer:** Kuzu is an embedded, disk-based, columnar Graph Database Management System (GDBMS) designed for query speed and Cypher compatibility. DevMind uses Kuzu to store structured relationships between files, classes, methods, imports, and git commits that cannot be modeled by vector similarity alone.

#### Q23: Why is a Vector Database alone insufficient for codebase intelligence?
**Answer:** Vector search finds semantic text similarity but fails at topological code relationships. For example, vector search cannot answer:
- *"Which classes inherit from BaseService?"*
- *"What functions break if I change the signature of `execute_query`?"*  
Graph databases excel at recursive traversal over dependency edges.

#### Q24: How does DevMind represent code structures as graph nodes and edges?
**Answer:**
- **Nodes**: `FileNode`, `ClassNode`, `FunctionNode`, `ImportNode`, `CommitNode`, `CommentNode`.
- **Edges**: `(:File)-[:CONTAINS]->(:Class)`, `(:Class)-[:DECLARES]->(:Function)`, `(:File)-[:IMPORTS]->(:Module)`, `(:Commit)-[:MODIFIES]->(:File)`.

#### Q25: How does Cognee construct graph triplets from data points?
**Answer:** During graph processing, `_create_triplets_from_graph()` maps node pairs and directed edge attributes into `Triplet(id, from_node_id, to_node_id, text)`. The concatenated triplet string (`SourceNode -> Relationship -> TargetNode`) is indexed for relational discovery.

#### Q26: What is the difference between Graph RAG and Vector RAG?
**Answer:**
- **Vector RAG**: Embeds text chunks and retrieves top-$k$ closest matches via vector distance. Isolated chunks may lack wider system context.
- **Graph RAG**: Identifies key entities in the query, locates them in a graph index, and traverses $n$-hop relationships to retrieve connected structural context.
- **DevMind Hybrid RAG**: Combines both—locates entry nodes via vector similarity, then expands context via graph neighborhood traversal.

#### Q27: How does DevMind isolate memory across different code repositories?
**Answer:** DevMind namespaces datasets based on the project root folder name (`devmind_<folder_name>`). Each repository gets dedicated table partitions in LanceDB and isolated entity subgraphs in Kuzu.

#### Q28: How does `devmind forget --file <path>` work under the hood?
**Answer:** DevMind resolves the file's dedicated dataset identifier and invokes `cognee.forget(dataset_name)`. This executes a cascading deletion: removing vectors from LanceDB, dropping entity nodes and edges from Kuzu, and pruning relational records from SQLite.

---

### Domain 5: Hybrid RAG, Retrieval & Context Synthesis

#### Q29: What is `SearchType.RAG_COMPLETION` in DevMind?
**Answer:** `SearchType.RAG_COMPLETION` is Cognee's hybrid retrieval pipeline. It:
1. Encodes the user's natural language question into a vector.
2. Performs ANN vector retrieval in LanceDB for relevant chunks.
3. Traverses Kuzu graph edges linked to those chunks.
4. Synthesizes a structured markdown answer using the configured LLM.

#### Q30: What fallback mechanism exists if primary hybrid RAG fails?
**Answer:** In `memory.py` (`recall_query`), if `cognee.recall(query_type=SearchType.RAG_COMPLETION)` fails or throws an exception, DevMind catches the error and executes a fallback retrieval using `SearchType.CHUNKS` directly against the raw vector index.

#### Q31: How does DevMind eliminate duplicate context chunks before LLM synthesis?
**Answer:** DevMind normalizes retrieved text chunks (lowercasing, whitespace stripping) and applies a deduplication filter (`seen_texts = set()`) to prevent repetitive context from inflating LLM token usage.

#### Q32: How are Architecture Decision Records (ADRs) integrated into RAG?
**Answer:** When a developer runs `devmind log "<decision>"`, DevMind persists the text into an architectural dataset tagged as an ADR entity. During recall, queries regarding design decisions ("Why did we choose X?") match these high-importance ADR nodes.

#### Q33: How does DevMind optimize context window usage for LLM prompts?
**Answer:** By setting `DEVMIND_RECALL_TOP_K` (default: 3), DevMind restricts retrieval to the top 3 most relevant context blocks, keeping the prompt under 1,500 tokens. This ensures fast response times (< 2 seconds) and avoids hitting token-per-minute (TPM) limits.

#### Q34: What is Reciprocal Rank Fusion (RRF) and how could it improve DevMind's retrieval?
**Answer:** RRF combines search results from multiple ranking algorithms (e.g., BM25 keyword search + LanceDB dense vector search) without requiring score normalization:
$$RRF\_Score(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}$$
where $r_m(d)$ is the rank of document $d$ in system $m$, and $k$ is a constant (~60). This ensures keyword-exact matches (e.g., exact variable names) and semantic matches both rank highly.

#### Q35: How does DevMind ensure answers are strictly grounded in codebase memory?
**Answer:** The LLM synthesis prompt is constrained with strict context boundary directives: answers must be synthesized solely from retrieved AST nodes, commit history, and code chunks, and must state "No relevant memories found" if the query is out of domain.

---

### Domain 6: Multi-Provider LLM Routing & Key Rotation

#### Q36: Why does DevMind implement an API key rotation mechanism?
**Answer:** Cloud LLM providers on free tiers enforce strict Daily Token Limits (e.g., Groq's 500k TPD on Llama 70B, Gemini's 30 RPM). DevMind accepts comma-separated lists of keys (`GROQ_API_KEYS`, `GEMINI_API_KEYS`) and automatically load-balances requests across them.

#### Q37: How does DevMind's rate-limit cooldown system work?
**Answer:** When an API key encounters an HTTP 429 or rate-limit exception, `mark_key_cooldown(api_key, cooldown_seconds=600)` records an expiration timestamp in `_KEY_COOLDOWNS`. `get_active_keys()` filters out cooled-down keys for 10 minutes, allowing requests to route seamlessly to remaining operational keys.

#### Q38: How does the monkey-patched `_rotating_acompletion` in LiteLLM work?
**Answer:** In `_install_litellm_key_rotation()`, DevMind wraps `litellm.acompletion` with an asynchronous generator (`itertools.cycle(keys)`). On each call:
1. Enforces a minimum interval (`_MIN_CALL_INTERVAL = 4.5s`) via an async lock to stay under RPM limits.
2. Injects the next active API key into `kwargs['api_key']`.
3. Calls the underlying original `litellm.acompletion`.

#### Q39: What was the root cause of the 60-second CLI freeze during `devmind ask` and how was it solved?
**Answer:** On startup, LiteLLM attempted an outbound HTTPS request to `raw.githubusercontent.com` to download an updated JSON cost map. On corporate networks or Windows with strict firewall rules, the SSL handshake timed out after 60 seconds. We solved it by setting `os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"`, forcing LiteLLM to use its offline bundled pricing database immediately.

#### Q40: How does DevMind support 100% offline local LLMs with Ollama?
**Answer:** If `LLM_PROVIDER=ollama`, DevMind configures Cognee to route LLM requests to `http://localhost:11434/v1` using local models (e.g., `llama3.2`, `qwen2.5-coder`). No internet connection or cloud API keys are required.

---

### Domain 7: Asyncio, Event Loops & Process Lifecycle

#### Q41: Why was `aiohttp` dumping `Unclosed client session` warnings to stderr on CLI exit?
**Answer:** Cognee initializes a singleton `_telemetry_session` (`aiohttp.ClientSession`) for telemetry analytics. In short-lived CLI processes, the event loop terminated before the session was closed. When Python's garbage collector destroyed the session during process teardown, `aiohttp`'s `__del__` method printed unclosed session warnings directly to `sys.stderr`, bypassing standard `warnings.filterwarnings()` filters.

#### Q42: How did DevMind resolve the `Task was destroyed but it is pending!` warning?
**Answer:** Cognee's telemetry spawned background tasks via `loop.create_task()` without awaiting them. During CLI shutdown in `run_async()`, DevMind now:
1. Explicitly closes `_telemetry_session`.
2. Gathers all remaining uncompleted tasks: `pending = [t for t in asyncio.all_tasks(loop) if not t.done()]`.
3. Cancels each task: `t.cancel()`.
4. Runs `await asyncio.gather(*pending, return_exceptions=True)`.

#### Q43: How does DevMind bridge synchronous CLI commands (Typer) with asynchronous Cognee pipelines?
**Answer:** DevMind implements a robust `run_async(coro)` runner in `cli.py`. It initializes a dedicated asyncio event loop, executes the coroutine to completion, performs async resource teardown (session closing, task cancellation), and cleanly shuts down the loop with stderr redirection to prevent Proactor event loop noise on Windows.

#### Q44: What Windows-specific asyncio challenges exist and how does DevMind handle them?
**Answer:** Windows uses `ProactorEventLoop`, which can throw `RuntimeError: Event loop is closed` or socket `10038` errors during garbage collection if async transports are destroyed out of order. DevMind suppresses loop teardown stderr during `loop.close()` to ensure clean CLI exits.

#### Q45: How does DevMind handle logging and telemetry suppression?
**Answer:** To prevent noisy structlog traces and LiteLLM provider notifications from polluting clean CLI output:
- `os.environ["LOG_LEVEL"] = "CRITICAL"`
- `os.environ["LITELLM_SUPPRESS_PROVIDER_INFO"] = "True"`
- `logging.getLogger("cognee").setLevel(logging.CRITICAL)`
- `structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))`

---

### Domain 8: Model Context Protocol (MCP) & Agent Integration

#### Q46: What is the Model Context Protocol (MCP) and how does DevMind implement it?
**Answer:** MCP is an open standard created by Anthropic that allows AI agents (like Claude Desktop, Claude Code, Cursor) to securely connect to external data sources and tools via standard JSON-RPC over `stdio`. DevMind implements an MCP server (`devmind/integrations/claude_code.py`) using `fastmcp.FastMCP`.

#### Q47: What MCP tools does DevMind expose to AI coding agents?
**Answer:**
1. `query_codebase_memory(query: str) -> str`: Enables the agent to query the codebase memory graph for architectural context, schemas, and historical bugs.
2. `log_decision_record(decision: str) -> str`: Enables the agent to record architectural decisions directly into memory during coding sessions.

#### Q48: How does an AI agent benefit from DevMind's MCP server compared to standard file-reading tools?
**Answer:** Standard file-reading tools require the agent to know file paths in advance and read whole files. DevMind's MCP tool allows the agent to ask high-level conceptual questions ("How is session validation implemented?") and receive surgical, cross-file hybrid context in a single tool invocation, saving context tokens and eliminating guesswork.

#### Q49: How do you configure Claude Code to use DevMind's MCP server?
**Answer:** Run:
```bash
claude mcp add devmind "devmind mcp"
```
or add to `.mcp.json` in the project root:
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

#### Q50: What is the vision for the future of DevMind and autonomous agentic coding?
**Answer:** DevMind aims to become the universal **hippocampus** for autonomous coding agents. By combining continuous incremental AST parsing, distributed graph synchronization via CI/CD, and bidirectional MCP tool bindings, any AI agent joining a repository can instantly acquire years of codebase context, architecture history, and team conventions.

---

### 💡 Quick Interview Cheat Sheet

```
┌───────────────────────────┬─────────────────────────────────────────────────────────────┐
│ Question Topic            │ Key Buzzwords to Use                                        │
├───────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Architecture              │ Hybrid Graph-Vector RAG, Ingestion/Query Decoupling, FastMCP│
│ Ingestion                 │ Deterministic AST Parsing, Zero-Token Ingestion, FastEmbed  │
│ Vector Storage            │ LanceDB, 384d BAAI/bge-small-en-v1.5, Cosine Dot Product    │
│ Graph Storage             │ Kuzu DB, Cypher Triplet Traversal, Relational Code Edges    │
│ Rate Limiting             │ Cyclic Multi-Key Rotation, Cooldown Tracker, Async Lock     │
│ Asyncio Lifecycle         │ Singleton Session Teardown, Task Cancellation, Clean GC     │
│ Agent Integration         │ Model Context Protocol (MCP), stdio transport, FastMCP      │
└───────────────────────────┴─────────────────────────────────────────────────────────────┘
```
