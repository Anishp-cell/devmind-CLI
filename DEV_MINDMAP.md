# DevMind Codebase Architecture Digest: Cognee Hackahton

## High-Level Architecture Metrics
- **Indexable Files**: 26
- **Classes / Data Models**: 3
- **Functions / Methods**: 50
- **Graph Nodes**: 79
- **Graph Relationships**: 53

## Codebase Symbol  

### 📄 `.env.example`
  - *(No top-level classes/functions extracted)*

### 📄 `.gitignore`
  - *(No top-level classes/functions extracted)*

### 📄 `ARCHITECTURE.md`
  - *(No top-level classes/functions extracted)*

### 📄 `ARCHITECTURE_DEEP_DIVE.md`
  - *(No top-level classes/functions extracted)*

### 📄 `CONTRIBUTING.md`
  - *(No top-level classes/functions extracted)*

### 📄 `GETTING_STARTED.md`
  - *(No top-level classes/functions extracted)*

### 📄 `README.md`
  - *(No top-level classes/functions extracted)*

### 📄 `devmind\__init__.py`
  - *(No top-level classes/functions extracted)*

### 📄 `devmind\cli.py`
  - fn run_async()
  - fn remember_pipeline()
  - fn remember()
  - fn ask()
  - fn chat()
  - fn log()
  - fn refresh()
  - fn forget()
  - fn dashboard()
  - fn mcp()
  - fn graph()
  - fn digest()

### 📄 `devmind\ingestion\ast_parser.py`
  - fn parse_python_ast()
  - fn parse_generic_code_symbols()
  - fn extract_code_symbols()
  - fn build_ast_summary()

### 📄 `devmind\ingestion\comment_extractor.py`
  - fn extract_comments_from_file()
  - fn get_codebase_comments()

### 📄 `devmind\ingestion\file_reader.py`
  - fn scrub_secrets()
  - fn _load_gitignore_spec()
  - fn is_text_file()
  - fn scan_codebase_files()

### 📄 `devmind\ingestion\git_parser.py`
  - fn get_git_history()
  - fn get_changed_files_git_diff()

### 📄 `devmind\integrations\claude_code.py`
  - fn query_codebase_memory()
  - fn log_architectural_decision()

### 📄 `devmind\memory.py`
  - fn _install_litellm_key_rotation()
  - fn get_project_root()
  - fn _get_global_config_path()
  - fn load_api_keys()
  - fn get_random_api_key()
  - fn get_random_gemini_key()
  - fn initialize_cognee()
  - fn remember_content()
  - fn get_all_dataset_names()
  - fn recall_query()
  - fn improve_memory()
  - fn forget_memory()
  - fn forget_file_nodes()

### 📄 `devmind\web\app.py`
  - fn read_index()
  - fn api_ask()
  - fn api_log()
  - fn api_remember()
  - fn build_codebase_graph_data()
  - fn api_graph()
  - fn api_digest()

### 📄 `devmind\web\templates\index.html`
  - *(No top-level classes/functions extracted)*

### 📄 `examples\demo_project\README.md`
  - *(No top-level classes/functions extracted)*

### 📄 `examples\demo_project\main.py`
  - fn calculate_user_tax()
  - fn process_checkout()

### 📄 `examples\demo_project\utils.py`
  - fn sanitize_phone_number()
  - fn debounce_event()

### 📄 `project description.txt`
  - *(No top-level classes/functions extracted)*

### 📄 `pyproject.toml`
  - *(No top-level classes/functions extracted)*

### 📄 `requirements.txt`
  - *(No top-level classes/functions extracted)*

### 📄 `tests\test_ast_parser.py`
  - Class TestAstParser

### 📄 `tests\test_graph_digest.py`
  - Class TestGraphDigest

### 📄 `tests\test_incremental.py`
  - Class TestIncrementalScanner

---
*Generated automatically by DevMind CLI (`devmind digest`)*