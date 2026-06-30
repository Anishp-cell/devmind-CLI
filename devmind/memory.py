import os
import logging
import random
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("devmind.memory")

# Load dotenv and set project-scoped directories BEFORE importing cognee
load_dotenv()

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

import cognee

# Global list of keys for rotation
_GROQ_API_KEYS = []

def load_api_keys():
    """
    Loads all available Groq API keys from the environment.
    Supports a comma-separated list via GROQ_API_KEYS, falling back to GROQ_API_KEY.
    """
    global _GROQ_API_KEYS
    load_dotenv()
    
    # Read GROQ_API_KEYS comma-separated list
    keys_str = os.getenv("GROQ_API_KEYS", "")
    if keys_str:
        _GROQ_API_KEYS = [k.strip() for k in keys_str.split(",") if k.strip()]
    
    # Fallback to single GROQ_API_KEY if not already in the list
    single_key = os.getenv("GROQ_API_KEY", "")
    if single_key and single_key not in _GROQ_API_KEYS:
        _GROQ_API_KEYS.append(single_key)

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
    load_dotenv()
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
            print("[Error] No LLM API keys found. Please set GROQ_API_KEYS or GROQ_API_KEY in your .env file.")
            import sys
            sys.exit(1)
    else:
        openai_key = os.getenv("OPENAI_API_KEY", "")
        cognee.config.set_llm_provider(llm_provider)
        cognee.config.set_llm_model(os.getenv("LLM_MODEL", "openai/gpt-4o-mini"))
        cognee.config.set_llm_api_key(openai_key)
        if llm_provider == "openai" and not openai_key:
            print("[Error] OPENAI_API_KEY is not set in your environment.")
            import sys
            sys.exit(1)

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
            if groq_key:
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
            if groq_key:
                os.environ["LLM_API_KEY"] = groq_key
                os.environ["LLM_ENDPOINT"] = endpoint
                cognee.config.set_llm_endpoint(endpoint)
                cognee.config.set_llm_api_key(groq_key)
                cognee.config.set_llm_model(model)

        logger.info(f"Recalling memory for query: '{query}'...")
        datasets = await get_all_dataset_names()
        if datasets:
            logger.info(f"Searching across datasets individually in parallel: {datasets}")
            # Query each dataset in parallel to bypass Cognee's single-dataset check
            tasks = [cognee.recall(query_text=query, datasets=[d]) for d in datasets]
            results_lists = await asyncio.gather(*tasks, return_exceptions=True)
            
            results = []
            for r_list in results_lists:
                if isinstance(r_list, list):
                    results.extend(r_list)
                elif isinstance(r_list, Exception):
                    logger.warning(f"Error recalling from a dataset partition: {r_list}")
        else:
            results = await cognee.recall(query_text=query)
            
        if not results:
            return "No relevant memories found."
        
        # Cognee returns a list of result objects or dictionaries. 
        # Format the output cleanly for console display.
        formatted_results = []
        for index, result in enumerate(results, start=1):
            if hasattr(result, "text"):
                formatted_results.append(result.text)
            elif isinstance(result, dict) and "text" in result:
                formatted_results.append(result["text"])
            else:
                formatted_results.append(str(result))
                
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
