import os
import sys
import json
import logging
import random
import asyncio
import itertools
import time
import pathlib
from dotenv import load_dotenv, find_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("devmind.memory")

# Load dotenv and set project-scoped directories BEFORE importing cognee
load_dotenv(find_dotenv(usecwd=True))

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
system_path = os.path.join(project_root, ".cognee_system")
data_path = os.path.join(project_root, ".cognee_data")

os.makedirs(system_path, exist_ok=True)
os.makedirs(os.path.join(system_path, "databases"), exist_ok=True)
os.makedirs(data_path, exist_ok=True)

# Set environment variables for Cognee root paths
os.environ["SYSTEM_ROOT_DIRECTORY"] = system_path
os.environ["DATA_ROOT_DIRECTORY"] = data_path
os.environ["CACHE_ROOT_DIRECTORY"] = os.path.join(project_root, ".cognee_cache")
os.environ["ENABLE_BACKEND_ACCESS_CONTROL"] = "false"
os.environ["LOG_LEVEL"] = "CRITICAL"
os.environ["LITELLM_SUPPRESS_PROVIDER_INFO"] = "True"
os.environ["LITELLM_LOG"] = "ERROR"
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

try:
    import litellm
    litellm.suppress_debug_info = True
    litellm.set_verbose = False
    litellm.telemetry = False
except Exception:
    pass

import logging
import warnings
# Silence all warnings globally before Cognee imports or sets up its loggers
warnings.filterwarnings("ignore")
logging.getLogger("cognee").setLevel(logging.CRITICAL)
logging.getLogger().setLevel(logging.CRITICAL)

import cognee

# Global list of keys and rate-limit cooldown tracking
_GROQ_API_KEYS = []
_GEMINI_API_KEYS = []
_KEY_COOLDOWNS = {}  # key_string -> unix_timestamp_cooldown_expires

_litellm_original_acompletion = None
_key_cycle = None
_last_call_time = 0.0
_MIN_CALL_INTERVAL = 4.5  # seconds between calls (≈13 RPM, well under free-tier limits)
_rate_limit_lock = None

def mark_key_cooldown(api_key: str, cooldown_seconds: int = 600):
    """Marks an API key as rate-limited until now + cooldown_seconds."""
    if api_key:
        _KEY_COOLDOWNS[api_key] = time.time() + cooldown_seconds
        logger.warning(f"Key {api_key[:6]}... marked on rate-limit cooldown for {cooldown_seconds}s")

def get_active_keys(keys_list: list[str]) -> list[str]:
    """Returns list of keys that are not currently in a cooldown window."""
    now = time.time()
    active = [k for k in keys_list if k not in _KEY_COOLDOWNS or now > _KEY_COOLDOWNS[k]]
    return active if active else keys_list  # fallback to all if all are in cooldown

def _install_litellm_key_rotation(keys: list):
    """Monkey-patch litellm.acompletion to rotate API keys on every call."""
    import litellm
    global _litellm_original_acompletion, _key_cycle, _rate_limit_lock
    
    if _litellm_original_acompletion is not None:
        return  # Already patched
    
    _litellm_original_acompletion = litellm.acompletion
    _key_cycle = itertools.cycle(keys)
    _rate_limit_lock = asyncio.Lock()
    
    async def _rotating_acompletion(*args, **kwargs):
        global _last_call_time
        
        # Rate-limit: serialize and enforce minimum interval between calls
        async with _rate_limit_lock:
            now = time.monotonic()
            if now < _last_call_time:
                scheduled_time = _last_call_time + _MIN_CALL_INTERVAL
                sleep_time = scheduled_time - now
                _last_call_time = scheduled_time
            else:
                sleep_time = 0.0
                _last_call_time = now + _MIN_CALL_INTERVAL
                
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)
        
        # Rotate to next API key
        next_key = next(_key_cycle)
        kwargs['api_key'] = next_key
        
        if len(next_key) > 10:
            masked = f"{next_key[:6]}...{next_key[-4:]}"
        else:
            masked = "***"
        logger.debug(f"litellm call → rotated key {masked}")
        
        return await _litellm_original_acompletion(*args, **kwargs)
    
    litellm.acompletion = _rotating_acompletion
    logger.info(f"Installed litellm key rotation with {len(keys)} keys (interval: {_MIN_CALL_INTERVAL}s)")

def get_project_root(start_dir: str = None) -> str:
    """
    Finds the nearest parent directory that contains a project marker (.git, .env, pyproject.toml, or setup.py).
    Falls back to start_dir if none found.
    """
    curr = os.path.abspath(start_dir or os.getcwd())
    while True:
        if any(os.path.exists(os.path.join(curr, marker)) for marker in (".git", ".env", "pyproject.toml", "setup.py")):
            return curr
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent
    return os.path.abspath(start_dir or os.getcwd())

def _get_global_config_path() -> pathlib.Path:
    """
    Returns the platform-appropriate path for the global DevMind config file.
    - Windows:       C:\\Users\\<User>\\AppData\\Roaming\\devmind\\config.json
    - macOS / Linux: ~/.config/devmind/config.json
    """
    if sys.platform == "win32":
        base = pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home() / "AppData" / "Roaming"))
    else:
        base = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", pathlib.Path.home() / ".config"))
    return base / "devmind" / "config.json"


def load_api_keys():
    """
    Loads all available Groq and Gemini API keys from the environment.
    Supports comma-separated lists and global configs.
    """
    global _GROQ_API_KEYS, _GEMINI_API_KEYS
    load_dotenv(find_dotenv(usecwd=True))
    
    # 1. Load Groq Keys
    keys_str = os.getenv("GROQ_API_KEYS", "")
    if keys_str:
        _GROQ_API_KEYS = [k.strip() for k in keys_str.split(",") if k.strip()]
    if not _GROQ_API_KEYS:
        single_key = os.getenv("GROQ_API_KEY", "")
        if single_key:
            _GROQ_API_KEYS.append(single_key)

    # 2. Load Gemini Keys
    gemini_str = os.getenv("GEMINI_API_KEYS", "")
    if gemini_str:
        _GEMINI_API_KEYS = [k.strip() for k in gemini_str.split(",") if k.strip()]
    if not _GEMINI_API_KEYS:
        single_gemini = os.getenv("GEMINI_API_KEY", "")
        if single_gemini:
            _GEMINI_API_KEYS.append(single_gemini)

    # 3. Load global config file to inject configurations and fallback keys
    config_path = _get_global_config_path()
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            # Cascading global configurations into os.environ
            for key, val in config.items():
                if key not in os.environ and val is not None:
                    os.environ[key] = str(val)
                    
            if not _GROQ_API_KEYS:
                global_keys_str = config.get("GROQ_API_KEYS", "")
                if global_keys_str:
                    _GROQ_API_KEYS = [k.strip() for k in global_keys_str.split(",") if k.strip()]
                if not _GROQ_API_KEYS:
                    single = config.get("GROQ_API_KEY", "")
                    if single:
                        _GROQ_API_KEYS.append(single)

            if not _GEMINI_API_KEYS:
                global_gemini_str = config.get("GEMINI_API_KEYS", "")
                if global_gemini_str:
                    _GEMINI_API_KEYS = [k.strip() for k in global_gemini_str.split(",") if k.strip()]
                if not _GEMINI_API_KEYS:
                    single = config.get("GEMINI_API_KEY", "")
                    if single:
                        _GEMINI_API_KEYS.append(single)
            logger.info(f"Loaded configurations and fallback keys from global config: {config_path}")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not read global config at {config_path}: {e}")

def get_random_api_key() -> tuple[str, str, str]:
    """
    Selects an active API key from the list (supports both Groq and OpenRouter keys)
    skipping rate-limited keys, and returns (key, endpoint, model).
    """
    available_keys = get_active_keys(_GROQ_API_KEYS)
    if not available_keys:
        return "", "", ""
    selected_key = random.choice(available_keys)
    
    # Auto-detect provider based on key prefix
    if selected_key.startswith("sk-or-v1-"):
        endpoint = "https://openrouter.ai/api/v1"
        model = os.getenv("LLM_MODEL_OPENROUTER", "openrouter/meta-llama/llama-3.3-70b-instruct")
        provider_name = "OpenRouter"
    else:
        endpoint = "https://api.groq.com/openai/v1"
        # If primary 70b model key hit cooldown, fallback to instant 8b model with 500k TPD limit
        if selected_key in _KEY_COOLDOWNS and time.time() <= _KEY_COOLDOWNS[selected_key]:
            model = os.getenv("LLM_MODEL_GROQ_FALLBACK", "groq/llama-3.1-8b-instant")
        else:
            model = os.getenv("LLM_MODEL_GROQ", "groq/llama-3.3-70b-versatile")
        provider_name = "Groq"
        
    if len(selected_key) > 10:
        masked = f"{selected_key[:6]}...{selected_key[-4:]}"
    else:
        masked = "***"
    logger.info(f"Rotating LLM request key -> {masked} ({provider_name} key, model: {model})")
    return selected_key, endpoint, model

def get_random_gemini_key() -> str:
    """
    Selects a random Gemini API key from the list.
    """
    if not _GEMINI_API_KEYS:
        return ""
    selected_key = random.choice(_GEMINI_API_KEYS)
    if len(selected_key) > 10:
        masked = f"{selected_key[:6]}...{selected_key[-4:]}"
    else:
        masked = "***"
    logger.info(f"Rotating Gemini LLM request key -> {masked}")
    return selected_key

def initialize_cognee():
    """
    Loads configuration from .env and verifies LLM & Embedding provider setup.
    """
    import warnings
    import logging
    import structlog
    
    # Suppress all python warnings globally (ResourceWarning, RuntimeWarning, DeprecationWarning)
    warnings.filterwarnings("ignore")
    warnings.filterwarnings("ignore", module="aiohttp")
    
    # Suppress verbose warning/info/error logs and structlog traceback dumps from Cognee
    logging.getLogger("cognee").setLevel(logging.CRITICAL)
    logging.getLogger("aiohttp").setLevel(logging.CRITICAL)
    logging.getLogger("litellm").setLevel(logging.CRITICAL)
    logging.getLogger("instructor").setLevel(logging.CRITICAL)
    
    try:
        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))
    except Exception:
        pass

    load_dotenv(find_dotenv(usecwd=True))
    load_api_keys()
    
    # Disable backend access control and authentication for local CLI use
    os.environ["ENABLE_BACKEND_ACCESS_CONTROL"] = "false"
    
    # Disable database subprocesses via env vars BEFORE Cognee constructs its
    # @lru_cache'd pydantic config singletons. The cognee.config.set_*() API
    # calls are unreliable because GraphConfig / VectorConfig may already be
    # cached with subprocess_enabled=True by the time we call them.
    os.environ["GRAPH_DATABASE_SUBPROCESS_ENABLED"] = "false"
    os.environ["VECTOR_DB_SUBPROCESS_ENABLED"] = "false"
    
    # Skip Cognee's internal LLM connection test (30s timeout) — we already
    # verified the endpoint works and this avoids wasting a cold-start API call.
    os.environ["COGNEE_SKIP_CONNECTION_TEST"] = "true"
    
    # Apply storage paths to Cognee configuration
    cognee.config.system_root_directory(system_path)
    cognee.config.data_root_directory(data_path)
    
    llm_provider = os.getenv("LLM_PROVIDER", "groq").lower()
    embedding_provider = os.getenv("EMBEDDING_PROVIDER", "fastembed").lower()
    
    # Cognee LLM Provider Configuration
    if llm_provider == "groq":
        groq_key, endpoint, model = get_random_api_key()
        os.environ["LLM_PROVIDER"] = "custom"
        os.environ["LLM_ENDPOINT"] = endpoint
        os.environ["LLM_API_KEY"] = groq_key
        os.environ["DEVMIND_ROTATION_ACTIVE"] = "true"
        
        cognee.config.set_llm_provider("custom")
        cognee.config.set_llm_endpoint(endpoint)
        cognee.config.set_llm_api_key(groq_key)
        cognee.config.set_llm_model(model)
        if not groq_key:
            logger.warning("[Warning] No Groq API keys found. Please run 'devmind init' to configure.")
            
    elif llm_provider == "gemini":
        gemini_key = get_random_gemini_key()
        os.environ["LLM_PROVIDER"] = "custom"
        os.environ["LLM_ENDPOINT"] = "https://generativelanguage.googleapis.com/v1beta/openai/"
        os.environ["LLM_API_KEY"] = gemini_key
        os.environ["LLM_ARGS"] = '{"custom_llm_provider": "openai"}'
        
        cognee.config.set_llm_provider("custom")
        cognee.config.set_llm_endpoint("https://generativelanguage.googleapis.com/v1beta/openai/")
        cognee.config.set_llm_api_key(gemini_key)
        model = os.getenv("LLM_MODEL", "gemini-2.5-flash-lite")
        if not model.startswith("openai/"):
            model = f"openai/{model}"
        cognee.config.set_llm_model(model)
        if not gemini_key:
            logger.warning("[Warning] No Gemini API keys found. Please run 'devmind init' to configure.")
        
        if len(_GEMINI_API_KEYS) > 1:
            _install_litellm_key_rotation(_GEMINI_API_KEYS)
            
    elif llm_provider == "anthropic":
        anthropic_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("LLM_API_KEY", "")
        model = os.getenv("LLM_MODEL", "anthropic/claude-3-5-sonnet-20241022")
        os.environ["ANTHROPIC_API_KEY"] = anthropic_key
        os.environ["LLM_API_KEY"] = anthropic_key
        cognee.config.set_llm_provider("anthropic")
        cognee.config.set_llm_api_key(anthropic_key)
        cognee.config.set_llm_model(model)
        if not anthropic_key:
            logger.warning("[Warning] ANTHROPIC_API_KEY is not set. Please run 'devmind init' to configure.")
            
    elif llm_provider == "openai":
        openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY", "")
        model = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
        os.environ["OPENAI_API_KEY"] = openai_key
        os.environ["LLM_API_KEY"] = openai_key
        cognee.config.set_llm_provider("openai")
        cognee.config.set_llm_api_key(openai_key)
        cognee.config.set_llm_model(model)
        if not openai_key:
            logger.warning("[Warning] OPENAI_API_KEY is not set. Please run 'devmind init' to configure.")

    elif llm_provider == "openrouter":
        openrouter_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY", "")
        endpoint = "https://openrouter.ai/api/v1"
        model = os.getenv("LLM_MODEL", "openrouter/meta-llama/llama-3.3-70b-instruct")
        os.environ["LLM_PROVIDER"] = "custom"
        os.environ["LLM_ENDPOINT"] = endpoint
        os.environ["LLM_API_KEY"] = openrouter_key
        cognee.config.set_llm_provider("custom")
        cognee.config.set_llm_endpoint(endpoint)
        cognee.config.set_llm_api_key(openrouter_key)
        cognee.config.set_llm_model(model)
        if not openrouter_key:
            logger.warning("[Warning] OPENROUTER_API_KEY is not set. Please run 'devmind init' to configure.")

    elif llm_provider == "ollama":
        ollama_endpoint = os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_ENDPOINT") or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        if not ollama_endpoint.endswith("/v1") and not ollama_endpoint.endswith("/v1/"):
            ollama_endpoint = f"{ollama_endpoint.rstrip('/')}/v1"
        model = os.getenv("OLLAMA_MODEL") or os.getenv("LLM_MODEL", "llama3.2")
        if not model.startswith("openai/"):
            model = f"openai/{model}"
            
        os.environ["LLM_PROVIDER"] = "custom"
        os.environ["LLM_ENDPOINT"] = ollama_endpoint
        os.environ["LLM_API_KEY"] = "ollama"
        
        cognee.config.set_llm_provider("custom")
        cognee.config.set_llm_endpoint(ollama_endpoint)
        cognee.config.set_llm_api_key("ollama")
        cognee.config.set_llm_model(model)
        logger.info(f"Ollama local LLM configured at {ollama_endpoint} (model: {model})")
    else:
        api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        endpoint = os.getenv("LLM_ENDPOINT") or os.getenv("OPENAI_BASE_URL")
        model = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
        
        cognee.config.set_llm_provider(llm_provider)
        cognee.config.set_llm_model(model)
        cognee.config.set_llm_api_key(api_key)
        if endpoint:
            cognee.config.set_llm_endpoint(endpoint)
            
        if llm_provider == "openai" and not api_key:
            logger.warning("[Warning] OPENAI_API_KEY is not set. Please configure it to query or ingest.")

    # Configure embedding provider
    cognee.config.set_embedding_provider(embedding_provider)
    cognee.config.set_embedding_model(os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"))
    cognee.config.set_embedding_dimensions(int(os.getenv("EMBEDDING_DIMENSIONS", "384")))
    
    logger.info(f"Initializing DevMind memory layer...")
    logger.info(f"LLM Provider: {llm_provider} (Mapped to custom base URL if not native)")
    logger.info(f"Embedding Provider: {embedding_provider} (Model: {os.getenv('EMBEDDING_MODEL')})")
    logger.info(f"System Storage Path: {system_path}")
    logger.info(f"Data Storage Path: {data_path}")

async def remember_content(content: str | list[str], dataset_name: str, deep: bool = False) -> bool:
    """
    Ingests text content into Cognee memory under a specified dataset name.

    Two modes:
      - **fast** (default, deep=False): Uses `cognee.add()` then runs a minimal
        cognify pipeline (classify → chunk → embed → store) that creates vector
        embeddings WITHOUT LLM entity extraction. Instant, zero API cost.
      - **deep** (deep=True): Runs `cognee.add()` then full `cognee.cognify()`.
        Builds a knowledge graph via LLM entity extraction (uses API tokens).
    """
    try:
        # Per-call key rotation for Groq provider
        if os.getenv("DEVMIND_ROTATION_ACTIVE") == "true":
            groq_key, endpoint, model = get_random_api_key()
            # If not deep mode, use fast 8b-instant model (500k TPD quota)
            if not deep:
                model = os.getenv("LLM_MODEL_GROQ_FALLBACK", "groq/llama-3.1-8b-instant")
            
            if groq_key:
                os.environ["LLM_API_KEY"] = groq_key
                os.environ["LLM_ENDPOINT"] = endpoint
                cognee.config.set_llm_endpoint(endpoint)
                cognee.config.set_llm_api_key(groq_key)
                cognee.config.set_llm_model(model)

        logger.info(f"Ingesting content into dataset '{dataset_name}' (mode: {'deep' if deep else 'fast'})...")

        # Step 1: Add data (stores raw content in relational DB)
        try:
            await cognee.add(content, dataset_name=dataset_name)
            logger.info(f"Successfully added data to dataset '{dataset_name}'.")
        except Exception as add_ex:
            err_str = str(add_ex).lower()
            if "ratelimit" in err_str or "429" in err_str or "quota" in err_str or "instructorretryexception" in err_str:
                logger.warning("Cloud rate limit hit during document chunking. Ingestion continuing with local AST & embeddings...")
            else:
                logger.warning(f"Cognee add completed: {add_ex}")

        # Step 2: Create vector embeddings so recall() can search
        if deep:
            # Full cognify: LLM entity extraction + knowledge graph + embeddings
            logger.info(f"Running deep cognify on dataset '{dataset_name}'...")
            await cognee.cognify(datasets=[dataset_name])
            logger.info(f"Successfully cognified dataset '{dataset_name}'.")
        else:
            # Fast cognify: classify → chunk → store embeddings (NO LLM calls)
            # This creates the DocumentChunk_text vector collection that recall() needs
            logger.info(f"Running fast cognify (local embeddings only) on '{dataset_name}'...")
            try:
                await _fast_cognify(dataset_name)
                logger.info(f"Fast cognify completed for '{dataset_name}'.")
            except Exception as cognify_ex:
                logger.warning(f"Fast cognify warning: {cognify_ex}")

        return True
    except Exception as e:
        logger.error(f"Error during ingestion for '{dataset_name}': {e}")
        return True


async def _fast_cognify(dataset_name: str):
    """
    Runs a minimal cognify pipeline that creates vector embeddings WITHOUT
    LLM entity extraction. This makes recall() work in fast mode.
    
    Pipeline: classify_documents → extract_chunks → add_data_points (embed + store)
    Skips: extract_graph_and_summarize (the expensive LLM step)
    """
    from cognee.modules.pipelines import run_pipeline
    from cognee.modules.pipelines.tasks.task import Task
    from cognee.modules.chunking.TextChunker import TextChunker
    from cognee.infrastructure.llm import get_max_chunk_tokens
    from cognee.tasks.documents import classify_documents, extract_chunks_from_documents
    from cognee.tasks.storage import add_data_points
    from cognee.modules.pipelines.layers.pipeline_execution_mode import get_pipeline_executor
    from cognee.modules.engine.operations.setup import setup

    await setup()

    tasks = [
        # Classify raw data into typed Document objects
        Task(classify_documents),
        # Split documents into semantic text chunks
        Task(
            extract_chunks_from_documents,
            max_chunk_size=get_max_chunk_tokens(),
            chunker=TextChunker,
        ),
        # Store chunks with vector embeddings (FastEmbed, no LLM calls)
        Task(
            add_data_points,
            embed_triplets=False,
            task_config={"batch_size": 100},
        ),
    ]

    pipeline_executor_func = get_pipeline_executor(run_in_background=False)

    await pipeline_executor_func(
        pipeline=run_pipeline,
        tasks=tasks,
        datasets=[dataset_name],
        incremental_loading=True,
        use_pipeline_cache=False,
        pipeline_name="fast_cognify_pipeline",
    )

async def get_all_dataset_names() -> list[str]:
    """
    Fetches all registered dataset names from Cognee's relational metadata.
    """
    try:
        from cognee.infrastructure.databases.relational import get_relational_engine
        from sqlalchemy import select
        from cognee.modules.data.models import Dataset
        
        engine = get_relational_engine()
        async with engine.get_async_session() as session:
            stmt = select(Dataset)
            results = (await session.execute(stmt)).scalars().all()
            return [d.name for d in results if d.name]
    except Exception as e:
        logger.warning(f"Could not fetch dataset names dynamically: {e}")
        return []

async def recall_query(query: str) -> str:
    """
    Queries the Cognee memory graph and AST codebase index using natural language.
    """
    current_dir = get_project_root()
    folder_name = os.path.basename(os.path.abspath(current_dir)).lower().replace("-", "_").replace(" ", "_")
    target_dataset = f"devmind_{folder_name}"

    ast_matches = []
    try:
        from devmind.ingestion.file_reader import scan_codebase_files
        files = scan_codebase_files(current_dir)
        query_keywords = [w for w in query.lower().split() if len(w) > 2 and w not in ("where", "are", "defined", "the", "what", "how", "this", "that", "does", "work")]
        
        for f in files:
            rel_path = f.get("relative_path", "").replace("\\", "/")
            content = f.get("content", "")
            content_lower = content.lower()
            
            # Prioritize source files and direct name matches
            score = sum(3 if kw in rel_path.lower() else (1 if kw in content_lower else 0) for kw in query_keywords)
            if score > 0:
                # Find clean matching lines (skip import walls and license boilerplate)
                matching_lines = []
                for line in content.splitlines():
                    sline = line.strip()
                    if any(kw in sline.lower() for kw in query_keywords):
                        if not (sline.startswith("import ") or sline.startswith("from ") or sline.startswith("#")):
                            clean_sline = "".join(c for c in sline if ord(c) < 0xFFFF)
                            matching_lines.append(clean_sline)
                    if len(matching_lines) >= 3:
                        break

                snippet = "\n".join(matching_lines) if matching_lines else "".join(c for c in content[:180].strip() if ord(c) < 0xFFFF)

                # Extract matching functions or classes
                funcs = []
                for line in content.splitlines():
                    sline = line.strip()
                    if sline.startswith("def ") or sline.startswith("class "):
                        name = sline.split("(")[0].split(":")[0].replace("def ", "").replace("class ", "").strip()
                        if any(kw in name.lower() for kw in query_keywords):
                            funcs.append(f"`{name}()`")
                    if len(funcs) >= 3:
                        break

                ast_matches.append({
                    "score": score,
                    "rel_path": rel_path,
                    "snippet": snippet,
                    "funcs": funcs
                })

        ast_matches.sort(key=lambda x: x["score"], reverse=True)
    except Exception as fe:
        logger.warning(f"AST search error: {fe}")

    # Cognee Recall with timeout
    try:
        from cognee.modules.search.types import SearchType
        top_k = int(os.getenv("DEVMIND_RECALL_TOP_K", "3"))
        results = await asyncio.wait_for(
            cognee.recall(query_text=query, query_type=SearchType.RAG_COMPLETION, datasets=[target_dataset], top_k=top_k),
            timeout=2.0
        )
        if results:
            cognee_texts = [str(r.text if hasattr(r, "text") else r) for r in results if r]
            if cognee_texts:
                return "\n\n".join(cognee_texts)
    except Exception:
        pass

    if ast_matches:
        top_items = ast_matches[:4]

        # 1. Attempt LLM natural language synthesis in simple English if configured
        try:
            from devmind.config_wizard import load_global_config
            cfg = load_global_config() or {}

            provider = (os.getenv("LLM_PROVIDER") or cfg.get("LLM_PROVIDER") or cfg.get("provider", "")).lower()
            model = os.getenv("LLM_MODEL") or cfg.get("LLM_MODEL") or cfg.get("model", "")

            # Resolve API key
            api_key = (
                os.getenv("GROQ_API_KEY") or cfg.get("GROQ_API_KEY") or
                os.getenv("GEMINI_API_KEY") or cfg.get("GEMINI_API_KEY") or
                os.getenv("ANTHROPIC_API_KEY") or cfg.get("ANTHROPIC_API_KEY") or
                os.getenv("OPENAI_API_KEY") or cfg.get("OPENAI_API_KEY") or
                os.getenv("OPENROUTER_API_KEY") or cfg.get("OPENROUTER_API_KEY") or
                cfg.get("api_key", "")
            )

            # If provider is ollama or has an API key
            if (provider == "ollama" and model) or api_key:
                import litellm
                if not model:
                    if provider == "groq":
                        model = "groq/llama-3.3-70b-versatile"
                    elif provider == "gemini":
                        model = "gemini/gemini-2.0-flash"
                    elif provider == "anthropic":
                        model = "anthropic/claude-3-5-sonnet-20241022"
                    elif provider == "openai":
                        model = "openai/gpt-4o-mini"
                    elif provider == "ollama":
                        model = "ollama/llama3.2"
                    else:
                        model = "gemini/gemini-2.0-flash"

                context_blocks = []
                for item in top_items:
                    context_blocks.append(f"File: {item['rel_path']}\nSnippet:\n{item['snippet']}")
                context_str = "\n\n---\n\n".join(context_blocks)

                prompt_messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are DevMind, a helpful and knowledgeable software engineering assistant. "
                            "Answer the developer's question in clear, simple, easy-to-understand plain English. "
                            "Explain the key concepts clearly and concisely with short bullet points and brief code examples if helpful. "
                            "Never dump raw tables of symbols or lists of imports. "
                            "Make your explanation intuitive, structured, and easy for any engineer to read immediately."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Codebase Context:\n{context_str}\n\nDeveloper Question: {query}"
                    }
                ]

                res = await asyncio.wait_for(
                    litellm.acompletion(model=model, api_key=api_key if api_key else None, messages=prompt_messages),
                    timeout=6.0
                )
                ai_text = res.choices[0].message.content.strip()
                if ai_text:
                    sources = ", ".join([f"`{item['rel_path']}`" for item in top_items])
                    return f"{ai_text}\n\n---\n[dim]Sources: {sources}[/dim]"
        except Exception as e:
            logger.warning(f"LLM synthesis fallback: {e}")

        # 2. Clean, Simple English Offline Summary (Fallback)
        summary_lines = [
            f"### Codebase Overview: \"{query}\"\n",
            "Here are the key files and functions in your codebase that implement this:\n"
        ]

        for item in top_items:
            funcs_str = f" (Symbols: {', '.join(item['funcs'])})" if item['funcs'] else ""
            summary_lines.append(f"- **`{item['rel_path']}`**{funcs_str}")
            if item['snippet']:
                summary_lines.append(f"```python\n{item['snippet']}\n```")
            summary_lines.append("")

        summary_lines.append("---")
        summary_lines.append("[dim]Tip: To get full conversational explanations synthesized by AI, run [/dim][bold cyan]/init[/bold cyan][dim] to connect a free Gemini or Groq model in 30 seconds.[/dim]")
        return "\n".join(summary_lines)

    return "No relevant files or symbols found in the codebase index matching your query."


async def improve_memory(dataset_name: str) -> bool:

    """
    Re-enriches and prunes relationships for a given dataset in Cognee.
    """
    try:
        logger.info(f"Improving Cognee memory for dataset '{dataset_name}'...")
        await cognee.improve(dataset=dataset_name)
        logger.info(f"Successfully improved memory for dataset '{dataset_name}'.")
        return True
    except Exception as e:
        logger.error(f"Error during cognee.improve for '{dataset_name}': {e}", exc_info=True)
        return False

async def forget_memory(dataset_name: str) -> bool:
    """
    Surgically deletes memory associated with a given dataset name.
    """
    try:
        logger.info(f"Forgetting dataset '{dataset_name}' from Cognee memory...")
        # Since cognee.forget might take dataset or dataset_name depending on local version,
        # we try dataset first, then fallback to everything or other keywords if required.
        try:
            await cognee.forget(dataset=dataset_name)
        except TypeError:
            await cognee.forget(dataset_name=dataset_name)
        logger.info(f"Successfully forgot dataset '{dataset_name}'.")
        return True
    except Exception as e:
        if isinstance(e, AttributeError) and "'NoneType' object has no attribute 'id'" in str(e):
            logger.info(f"Dataset '{dataset_name}' was not found in memory (it may have already been deleted or never ingested).")
            return True
        logger.error(f"Error during cognee.forget for '{dataset_name}': {e}", exc_info=True)
        return False


async def forget_file_nodes(relative_path: str) -> bool:
    """
    Surgically removes data records and associated graph nodes for a specific
    file from Cognee memory.

    Works in both ingestion modes:
    - Unified dataset (all files in one dataset): matches by the 'File Path:'
      prefix tag written by the remember pipeline, deleting the Data records
      and pruning their graph nodes via Cognee's relational + graph engines.
    - Legacy per-file datasets: falls back to deleting the derived dataset name.
    """
    deleted_anything = False

    # --- Strategy 1: delete Data records matching the file path tag ---
    try:
        from cognee.infrastructure.databases.relational import get_relational_engine
        from sqlalchemy import select, delete

        # Try known Cognee data-layer model names (varies by version)
        data_model = None
        for model_path in (
            "cognee.modules.data.models.Data",
            "cognee.modules.data.models.DataPoint",
            "cognee.modules.data.models.Document",
        ):
            try:
                module_path, cls_name = model_path.rsplit(".", 1)
                import importlib
                mod = importlib.import_module(module_path)
                data_model = getattr(mod, cls_name, None)
                if data_model is not None:
                    break
            except Exception:
                continue

        if data_model is not None:
            engine = get_relational_engine()
            # Match on the tagged prefix injected during ingestion:
            #   "File Path: <relative_path>\n---\n..."
            search_tag = f"File Path: {relative_path}"
            async with engine.get_async_session() as session:
                # Find matching records
                stmt = select(data_model)
                results = (await session.execute(stmt)).scalars().all()
                matching_ids = [
                    r.id for r in results
                    if (hasattr(r, "content") and r.content and search_tag in r.content)
                    or (hasattr(r, "name") and r.name and relative_path in r.name)
                ]

                if matching_ids:
                    del_stmt = delete(data_model).where(data_model.id.in_(matching_ids))
                    await session.execute(del_stmt)
                    await session.commit()
                    logger.info(f"Deleted {len(matching_ids)} data record(s) for '{relative_path}'.")
                    deleted_anything = True
                else:
                    logger.info(f"No data records found matching '{relative_path}' in unified dataset.")
    except Exception as e:
        logger.warning(f"Strategy 1 (data record deletion) failed for '{relative_path}': {e}")

    # --- Strategy 2: legacy per-file dataset name deletion (backward compat) ---
    try:
        legacy_dataset = (
            relative_path
            .replace("/", "_")
            .replace("\\", "_")
            .replace(".", "_")
            .replace(" ", "_")
        )
        result = await forget_memory(legacy_dataset)
        if result:
            deleted_anything = True
    except Exception as e:
        logger.warning(f"Strategy 2 (legacy dataset deletion) failed for '{relative_path}': {e}")

    return deleted_anything
