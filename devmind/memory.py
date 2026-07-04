import os
import sys
import json
import logging
import random
import asyncio
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
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["LITELLM_SUPPRESS_PROVIDER_INFO"] = "True"

import cognee

# Global list of keys for rotation
_GROQ_API_KEYS = []

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
    Loads all available Groq API keys from the environment.
    Supports a comma-separated list via GROQ_API_KEYS, falling back to GROQ_API_KEY.
    If neither is present in the local .env, checks the global config file:
      - macOS/Linux: ~/.config/devmind/config.json
      - Windows:     %APPDATA%\\devmind\\config.json
    """
    global _GROQ_API_KEYS
    load_dotenv(find_dotenv(usecwd=True))
    # 1. Try local .env — comma-separated list
    keys_str = os.getenv("GROQ_API_KEYS", "")
    if keys_str:
        _GROQ_API_KEYS = [k.strip() for k in keys_str.split(",") if k.strip()]

    # 2. Try local .env — single key fallback
    if not _GROQ_API_KEYS:
        single_key = os.getenv("GROQ_API_KEY", "")
        if single_key:
            _GROQ_API_KEYS.append(single_key)

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
            logger.info(f"Loaded configurations and fallback keys from global config: {config_path}")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not read global config at {config_path}: {e}")

def get_random_api_key() -> tuple[str, str, str]:
    """
    Selects a random API key from the list (supports both Groq and OpenRouter keys)
    and returns (key, endpoint, model) appropriate for that provider.
    """
    if not _GROQ_API_KEYS:
        return "", "", ""
    selected_key = random.choice(_GROQ_API_KEYS)
    
    # Auto-detect provider based on key prefix
    if selected_key.startswith("sk-or-v1-"):
        endpoint = "https://openrouter.ai/api/v1"
        model = os.getenv("LLM_MODEL_OPENROUTER", "openrouter/meta-llama/llama-3.3-70b-instruct")
        provider_name = "OpenRouter"
    else:
        endpoint = "https://api.groq.com/openai/v1"
        model = os.getenv("LLM_MODEL_GROQ", "groq/llama-3.3-70b-versatile")
        provider_name = "Groq"
        
    if len(selected_key) > 10:
        masked = f"{selected_key[:6]}...{selected_key[-4:]}"
    else:
        masked = "***"
    logger.info(f"Rotating LLM request key -> {masked} ({provider_name} key, model: {model})")
    return selected_key, endpoint, model

def initialize_cognee():
    """
    Loads configuration from .env and verifies LLM & Embedding provider setup.
    """
    load_dotenv(find_dotenv(usecwd=True))
    load_api_keys()
    
    # Disable backend access control and authentication for local CLI use
    os.environ["ENABLE_BACKEND_ACCESS_CONTROL"] = "false"
    
    # Apply storage paths to Cognee configuration
    cognee.config.system_root_directory(system_path)
    cognee.config.data_root_directory(data_path)
    
    llm_provider = os.getenv("LLM_PROVIDER", "groq").lower()
    embedding_provider = os.getenv("EMBEDDING_PROVIDER", "fastembed").lower()
    
    # Cognee does not natively support "groq" in its LLMProvider enum.
    # We map "groq" to the "custom" provider utilizing Groq's OpenAI-compatible endpoint.
    if llm_provider == "groq":
        groq_key, endpoint, model = get_random_api_key()
        os.environ["LLM_PROVIDER"] = "custom"
        os.environ["LLM_ENDPOINT"] = endpoint
        os.environ["LLM_API_KEY"] = groq_key
        
        cognee.config.set_llm_provider("custom")
        cognee.config.set_llm_endpoint(endpoint)
        cognee.config.set_llm_api_key(groq_key)
        cognee.config.set_llm_model(model)
        if not groq_key:
            logger.warning("[Warning] No Groq API keys found. Please set GROQ_API_KEYS or GROQ_API_KEY to query or ingest.")
    else:
        openai_key = os.getenv("OPENAI_API_KEY", "")
        cognee.config.set_llm_provider(llm_provider)
        cognee.config.set_llm_model(os.getenv("LLM_MODEL", "openai/gpt-4o-mini"))
        cognee.config.set_llm_api_key(openai_key)
        if llm_provider == "openai" and not openai_key:
            logger.warning("[Warning] OPENAI_API_KEY is not set. Please configure it to query or ingest.")

    # Configure embedding provider
    cognee.config.set_embedding_provider(embedding_provider)
    cognee.config.set_embedding_model(os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"))
    cognee.config.set_embedding_dimensions(int(os.getenv("EMBEDDING_DIMENSIONS", "384")))
    
    logger.info(f"Initializing DevMind memory layer...")
    logger.info(f"LLM Provider: {llm_provider} (Mapped to custom OpenAI-compatible endpoint if groq)")
    logger.info(f"Embedding Provider: {embedding_provider} (Model: {os.getenv('EMBEDDING_MODEL')})")
    logger.info(f"System Storage Path: {system_path}")
    logger.info(f"Data Storage Path: {data_path}")

async def remember_content(content: str, dataset_name: str) -> bool:
    """
    Ingests text content into Cognee memory under a specified dataset name.
    """
    try:
        # Rotate API key if we are on custom/groq rotation
        llm_provider = os.getenv("LLM_PROVIDER", "groq").lower()
        if llm_provider == "groq" or os.environ.get("LLM_PROVIDER") == "custom":
            groq_key, endpoint, model = get_random_api_key()
            if not groq_key:
                logger.error("No API keys available. Aborting memory ingestion.")
                return False
            
            os.environ["LLM_API_KEY"] = groq_key
            os.environ["LLM_ENDPOINT"] = endpoint
            cognee.config.set_llm_endpoint(endpoint)
            cognee.config.set_llm_api_key(groq_key)
            cognee.config.set_llm_model(model)

        logger.info(f"Remembering content in dataset '{dataset_name}'...")
        await cognee.remember(content, dataset_name=dataset_name)
        logger.info(f"Successfully remembered dataset '{dataset_name}'.")
        return True
    except Exception as e:
        logger.error(f"Error during cognee.remember for '{dataset_name}': {e}", exc_info=True)
        return False

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
    Queries the Cognee memory graph using natural language.
    """
    try:
        # Rotate API key if we are on custom/groq rotation
        llm_provider = os.getenv("LLM_PROVIDER", "groq").lower()
        if llm_provider == "groq" or os.environ.get("LLM_PROVIDER") == "custom":
            groq_key, endpoint, model = get_random_api_key()
            if not groq_key:
                return "Error: No API keys found. Please set GROQ_API_KEYS or GROQ_API_KEY before querying."
            
            os.environ["LLM_API_KEY"] = groq_key
            os.environ["LLM_ENDPOINT"] = endpoint
            cognee.config.set_llm_endpoint(endpoint)
            cognee.config.set_llm_api_key(groq_key)
            cognee.config.set_llm_model(model)

        logger.info(f"Recalling memory for query: '{query}'...")
        
        # Target only the active project directory's unified dataset
        current_dir = get_project_root()
        folder_name = os.path.basename(os.path.abspath(current_dir)).lower().replace("-", "_").replace(" ", "_")
        target_dataset = f"devmind_{folder_name}"
        
        from cognee.modules.search.types import SearchType
        query_type = SearchType.RAG_COMPLETION
        top_k = int(os.getenv("DEVMIND_RECALL_TOP_K", "3"))
        
        logger.info(f"Searching memory dataset '{target_dataset}' (top_k={top_k})...")
        try:
            results = await cognee.recall(query_text=query, query_type=query_type, datasets=[target_dataset], top_k=top_k)
        except Exception as ex:
            logger.warning(f"Dataset partition '{target_dataset}' query failed: {ex}. Falling back to default recall.")
            results = await cognee.recall(query_text=query, query_type=query_type, top_k=top_k)
            
        if not results:
            return "No relevant memories found."
        
        # Cognee returns a list of result objects or dictionaries. 
        # Format the output cleanly for console display by deduplicating identical or fallback responses.
        formatted_results = []
        seen_texts = set()
        for index, result in enumerate(results, start=1):
            if hasattr(result, "text"):
                val = result.text
            elif isinstance(result, dict) and "text" in result:
                val = result["text"]
            else:
                val = str(result)
            
            # Normalize whitespace and casing for reliable duplication checks
            normalized = " ".join(val.strip().lower().split())
            if normalized and normalized != "got it." and normalized not in seen_texts:
                seen_texts.add(normalized)
                formatted_results.append(val)
                
        if not formatted_results:
            return "No relevant memories found."
            
        return "\n\n".join(formatted_results)
    except Exception as e:
        logger.error(f"Error during cognee.recall for query '{query}': {e}", exc_info=True)
        return f"Error recalling memory: {e}"

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
