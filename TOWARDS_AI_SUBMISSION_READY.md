# Building a Persistent Codebase Memory System: Architecture, Hybrid Graph RAG, and Lessons Learned

*By Anish Pathak & Ambarish Pathak*

*An architectural deep dive into designing a zero-token local codebase intelligence pipeline using deterministic AST parsing, LanceDB, and the Model Context Protocol (MCP).*

---

## 1. The Context Tax in Modern AI Coding Assistants

AI coding assistants have fundamentally transformed developer productivity. They can write boilerplate, debug stack traces, refactor functions, and explain complex algorithmic flows in seconds.

However, existing coding assistants suffer from a major architectural limitation: **statelessness**.

Every time a developer opens a new terminal session or IDE window, the model starts from absolute zero. Developers are forced to repeatedly supply the same architectural overview, re-explain database schemas, and highlight shared utilities.

This creates what we define as the **context tax** — the cumulative engineering time and cognitive load spent re-teaching an assistant information it should already retain.

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

### The Agentic IDE Dilemma: Burning 100k Tokens Before Writing Code

This problem escalates significantly with modern **agentic terminal agents and IDEs** (such as Antigravity, Claude Code, Codex, and Cursor Agent Mode). 

When an autonomous agent is given a high-level task like *"Refactor the authentication middleware"*, the following execution loop occurs:
1. The agent lacks structural awareness of the repository topology.
2. It initiates an exploratory loop, executing recursive file searches, directory listings, and raw file reads across dozens of modules.
3. It ingests 20 to 50 raw source files into its context window merely to identify how modules connect.
4. **The result:** 50,000 to 100,000+ context tokens are consumed on blind exploration before the agent writes a single line of code.
5. By the time the agent attempts the edit, the context window is diluted with raw file dumps, attention degrades ("lost-in-the-middle" phenomenon), and the probability of hallucinating function signatures increases drastically.

To solve this, we engineered an architectural framework that decouples **repository ingestion** from **context querying**.

---

## 2. System Architecture: Decoupling Ingestion from Querying

The core design principle is simple: **Repository ingestion should cost zero LLM tokens, run entirely locally, and construct a persistent graph-vector topology.**

```
┌─────────────────────────────────────────────────────────────┐
│                    1. INGESTION LAYER                       │
│                                                             │
│  Source Files ──→ Deterministic AST Parser (Python/JS/Go/RS)│
│  Git History  ──→ Git Log Extractor (Commits, Diffs)        │
│  Annotations  ──→ Comment Scanner (TODO/FIXME/HACK/ADR)     │
│                                                             │
│  [Local Execution • Zero API Calls • Zero LLM Tokens]       │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    2. MEMORY STORAGE LAYER                  │
│                                                             │
│  FastEmbed (ONNX, CPU)  ──→ Vector Embeddings (LanceDB)     │
│  Relational Entities    ──→ Graph Topology (Kuzu DB)        │
│  Execution Checkpoints  ──→ Relational Store (SQLite)       │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    3. HYBRID RAG QUERY LAYER                │
│                                                             │
│  Query ──→ Hybrid Retrieval ──→ Surgical Context Window     │
│            (Vector Similarity    (Only 2-3 precise chunks   │
│             + Graph Traversal)    sent to LLM for synthesis)│
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Five Critical Engineering Decisions & Tradeoffs

### Decision 1: Deterministic AST Parsing Over LLM Entity Extraction

Initial prototypes attempted to pass source files directly through an LLM to extract structural relationships and summaries. For a modest 30-file codebase, this consumed ~50,000 tokens during ingestion, hit free-tier rate limits within minutes, and took several minutes to process.

We replaced this with **deterministic Abstract Syntax Tree (AST) parsing**:
- **Python**: Utilizes the native `ast` module to extract classes, inheritance bases, method signatures, docstrings, and imports.
- **JavaScript & TypeScript**: Evaluates regular expressions for classes, exported declarations, arrow functions, and ES module imports.
- **Go & Rust**: Identifies struct declarations, traits, method receivers, and async functions.

```python
# Deterministic Python AST extraction without LLM invocation
import ast

def parse_python_ast(content: str) -> dict:
    tree = ast.parse(content)
    symbols = {"classes": [], "functions": [], "imports": []}
    
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            methods = [
                {"name": item.name, "args": [a.arg for a in item.args.args]}
                for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            symbols["classes"].append({"name": node.name, "bases": bases, "methods": methods})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols["functions"].append({"name": node.name, "args": [a.arg for a in node.args.args]})
            
    return symbols
```

**Outcome**: Ingestion time dropped from 4 minutes to **under 2 seconds**, with 100% deterministic symbol indexing and zero API cost.

---

### Decision 2: Engineering the Fast Cognify Embedding Pipeline

In hybrid graph-vector engines like Cognee, standard ingestion workflows typically link embedding generation with full LLM entity extraction (`cognify()`).

Bypassing `cognify()` to avoid LLM costs introduced a silent failure mode: raw files were stored in relational tables, but the vector collection (`DocumentChunk_text`) was never initialized. Queries against the vector index returned empty results.

To solve this, we engineered a dedicated local embedding pipeline (`_fast_cognify`) that executes document classification, semantic chunking, and local vector embedding while bypassing the LLM summarization task:

```python
async def _fast_cognify(dataset_name: str):
    """
    Minimal local embedding pipeline:
    Classify -> Chunk -> Local FastEmbed -> LanceDB Storage
    Bypasses expensive LLM entity extraction.
    """
    tasks = [
        Task(classify_documents),
        Task(
            extract_chunks_from_documents,
            max_chunk_size=get_max_chunk_tokens(),
            chunker=TextChunker,
        ),
        Task(
            add_data_points,
            embed_triplets=False,
            task_config={"batch_size": 100},
        ),
    ]
    
    await pipeline_executor(
        pipeline=run_pipeline,
        tasks=tasks,
        datasets=[dataset_name],
        incremental_loading=True,
    )
```

**Outcome**: Local 384-dimensional dense vector embeddings (`BAAI/bge-small-en-v1.5`) are generated via ONNX Runtime on CPU, populating LanceDB in milliseconds without outbound API calls.

---

### Decision 3: Resilient Multi-Key Rate Limit Management

When developers query the memory layer using cloud LLM providers, free-tier endpoints impose strict rate limits (e.g., Requests Per Minute and Daily Token Limits).

To ensure high availability without requiring paid enterprise tiers, we implemented a cyclic key rotation layer with automated cooldown tracking:

```python
async def _rotating_acompletion(*args, **kwargs):
    global _last_call_time
    
    # Enforce minimum call interval (e.g., 4.5s) to satisfy RPM caps
    async with _rate_limit_lock:
        now = time.monotonic()
        if now < _last_call_time:
            sleep_time = (_last_call_time + MIN_CALL_INTERVAL) - now
            _last_call_time += MIN_CALL_INTERVAL
        else:
            sleep_time = 0.0
            _last_call_time = now + MIN_CALL_INTERVAL
            
    if sleep_time > 0:
        await asyncio.sleep(sleep_time)
        
    # Rotate to next active key (filtering out keys on 429 cooldown)
    kwargs['api_key'] = get_next_active_key()
    return await original_acompletion(*args, **kwargs)
```

When an endpoint returns an HTTP 429 status code, that specific key is placed on a 10-minute cooldown window, and traffic routes seamlessly to alternative active keys.

---

### Decision 4: Resolving the 60-Second SSL Handshake Freeze

During early testing, queries occasionally experienced a 60-second latency spike before generating a response. 

Network tracing revealed that underlying LLM wrapper libraries (such as LiteLLM) attempt an outbound HTTPS request on initialization to fetch remote model pricing files from GitHub Raw. When executed behind corporate firewalls, VPNs, or strict Windows socket filters, the handshake timed out after 60 seconds before falling back to local defaults.

Configuring local cost mapping resolved the bottleneck entirely:

```python
# Force offline bundled model mapping; prevent outbound SSL handshake delays
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ["LITELLM_SUPPRESS_PROVIDER_INFO"] = "True"
```

**Outcome**: Query execution latency dropped from >60 seconds to **under 3 seconds**.

---

### Decision 5: Asyncio Event Loop & Session Lifecycle Teardown

In command-line applications, background tasks and unclosed client sessions frequently dump garbage-collection warnings to `stderr` upon process exit (e.g., `Unclosed client session`, `Task was destroyed but it is pending!`).

Because libraries like `aiohttp` write directly to `sys.stderr` from their `__del__` destructor, standard warning filters (`warnings.filterwarnings`) cannot intercept them.

We resolved this by adding an explicit graceful teardown routine prior to closing the asyncio event loop:

```python
async def cleanup_async_resources(loop):
    # 1. Explicitly close singleton telemetry sessions
    if _telemetry_session and not _telemetry_session.closed:
        await _telemetry_session.close()
        
    # 2. Cancel and gather remaining fire-and-forget tasks
    pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
```

---

## 4. Integration with Autonomous Agents via Model Context Protocol (MCP)

To enable autonomous coding assistants (such as Claude Code or Cursor) to query codebase memory directly, we exposed the memory graph as a **Model Context Protocol (MCP)** server over standard `stdio`.

```python
from fastmcp import FastMCP

mcp = FastMCP("Codebase Memory Server")

@mcp.tool
async def query_codebase_memory(query: str) -> str:
    """
    Query the persistent knowledge graph for architectural context,
    dependency graphs, or historical decision records.
    """
    return await recall_query(query)
```

### Why This Changes Agentic Workflows:
Instead of an AI agent performing 40 recursive filesystem tool calls to explore a project, it invokes `query_codebase_memory()` once. It receives the exact top-3 relevant modules, architectural context, and related symbol definitions in a single 500-token response — cutting exploratory token consumption by over 90%.

---

## 5. Summary & Engineering Takeaways

Building a local-first codebase memory engine highlighted several key software engineering principles:

1. **Decouple Ingestion from Inference**: Generating structural embeddings and AST trees deterministically on the client machine eliminates API costs and eliminates rate-limit vulnerabilities.
2. **Hybrid RAG Outperforms Pure Vector Search**: Combining dense vector similarity (LanceDB) with topological code entity graphs (Kuzu DB) allows models to understand both semantic intent and physical code inheritance.
3. **Clean Teardowns Matter in CLI Tools**: Robust developer tooling requires careful management of event loop lifecycles, connection pool closures, and graceful error handling across different operating systems.
4. **Standardized Tool Protocols (MCP) Bridge the Gap**: Exposing persistent memory over open protocols allows existing autonomous agents to operate with long-term repository context.

---

### Key Technical Tags:
`Python`, `Software Engineering`, `Artificial Intelligence`, `System Design`, `RAG`, `Knowledge Graphs`, `Vector Database`, `Model Context Protocol`
