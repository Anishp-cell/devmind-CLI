# DevMind Codebase Health Report: Cognee Hackahton

**Health Score: 40/100  |  Grade: D**

| Metric | Value |
|---|---|
| Total Files | 33 |
| Total Functions | 112 |
| Total Classes | 16 |
| Total Lines | 5,999 |
| Avg Complexity (CC) | 5.6 |
| Complexity Hotspots | 16 |
| Code Smells | 27 |
| Technical Debt Tags | 13 |
| Dead Imports | 21 |
| Test Coverage | 11% (2/18) |

## Complexity Hotspots

| Function | File | Line | CC |
|---|---|---|---|
| `health` | `devmind/cli.py` | 436 | 42 |
| `load_api_keys` | `devmind/memory.py` | 149 | 26 |
| `detect_dead_imports` | `devmind/analysis/health.py` | 296 | 25 |
| `get_changed_files_git_diff` | `devmind/ingestion/git_parser.py` | 75 | 23 |
| `parse_python_ast` | `devmind/ingestion/ast_parser.py` | 26 | 21 |
| `extract_comments_from_file` | `devmind/ingestion/comment_extractor.py` | 10 | 21 |
| `recall_query` | `devmind/memory.py` | 506 | 20 |
| `initialize_cognee` | `devmind/memory.py` | 253 | 19 |
| `run_async` | `devmind/cli.py` | 28 | 18 |
| `forget_file_nodes` | `devmind/memory.py` | 617 | 18 |
| `parse_generic_code_symbols` | `devmind/ingestion/ast_parser.py` | 87 | 16 |
| `remember_content` | `devmind/memory.py` | 380 | 15 |
| `scan_codebase_files` | `devmind/ingestion/file_reader.py` | 102 | 15 |
| `remember_pipeline` | `devmind/cli.py` | 87 | 12 |
| `get_git_history` | `devmind/ingestion/git_parser.py` | 7 | 12 |
| `digest` | `devmind/cli.py` | 378 | 11 |

## Code Smells

| Kind | Name | File | Line | Detail |
|---|---|---|---|---|
| Long Function | `run_async` | `devmind/cli.py` | 28 | 51 lines |
| Long Function | `remember_pipeline` | `devmind/cli.py` | 87 | 72 lines |
| Long Function | `digest` | `devmind/cli.py` | 378 | 56 lines |
| Long Function | `health` | `devmind/cli.py` | 436 | 333 lines |
| Long Function | `load_api_keys` | `devmind/memory.py` | 149 | 58 lines |
| Deep Nesting | `load_api_keys` | `devmind/memory.py` | 149 | nesting depth 5 |
| Long Function | `initialize_cognee` | `devmind/memory.py` | 253 | 126 lines |
| Long Function | `remember_content` | `devmind/memory.py` | 380 | 59 lines |
| Long Function | `recall_query` | `devmind/memory.py` | 506 | 75 lines |
| Long Function | `forget_file_nodes` | `devmind/memory.py` | 617 | 77 lines |
| Long Function | `detect_code_smells` | `devmind/analysis/health.py` | 189 | 51 lines |
| Long Function | `detect_dead_imports` | `devmind/analysis/health.py` | 296 | 67 lines |
| Deep Nesting | `detect_dead_imports` | `devmind/analysis/health.py` | 296 | nesting depth 7 |
| Long Function | `map_test_coverage` | `devmind/analysis/health.py` | 368 | 64 lines |
| Long Function | `compute_health_score` | `devmind/analysis/health.py` | 437 | 61 lines |
| Long Function | `run_health_analysis` | `devmind/analysis/health.py` | 503 | 111 lines |
| Long Function | `parse_python_ast` | `devmind/ingestion/ast_parser.py` | 26 | 59 lines |
| Deep Nesting | `parse_python_ast` | `devmind/ingestion/ast_parser.py` | 26 | nesting depth 6 |
| Long Function | `extract_comments_from_file` | `devmind/ingestion/comment_extractor.py` | 10 | 63 lines |
| Deep Nesting | `extract_comments_from_file` | `devmind/ingestion/comment_extractor.py` | 10 | nesting depth 7 |
| Long Function | `scan_codebase_files` | `devmind/ingestion/file_reader.py` | 102 | 74 lines |
| Deep Nesting | `scan_codebase_files` | `devmind/ingestion/file_reader.py` | 102 | nesting depth 5 |
| Long Function | `get_git_history` | `devmind/ingestion/git_parser.py` | 7 | 66 lines |
| Deep Nesting | `get_git_history` | `devmind/ingestion/git_parser.py` | 7 | nesting depth 5 |
| Long Function | `get_changed_files_git_diff` | `devmind/ingestion/git_parser.py` | 75 | 52 lines |
| Deep Nesting | `get_changed_files_git_diff` | `devmind/ingestion/git_parser.py` | 75 | nesting depth 6 |
| Long Function | `build_codebase_graph_data` | `devmind/web/app.py` | 92 | 71 lines |

## Technical Debt Tags

| Tag | File | Line | Text |
|---|---|---|---|
| `BUG` | `devmind/cli.py` | 606 | first, then FIXME, then others |
| `BUG` | `tests/test_health.py` | 144 | off-by-one in loop\nfor i in range(10): pass\n" |
| `FIXME` | `examples/demo_project/main.py` | 16 | Deduplicate cart_items before processing |
| `FIXME` | `tests/test_health.py` | 139 | broken auth flow\ndef auth(): pass\n" |
| `HACK` | `examples/demo_project/main.py` | 17 | Skipping real payment gateway integration and simulating success |
| `HACK` | `tests/test_health.py` | 149 | temporary workaround\nx = 42\n" |
| `TODO` | `examples/demo_project/utils.py` | 8 | Add international phone format validations |
| `TODO` | `tests/test_health.py` | 134 | fix this later\n" |
| `TODO` | `tests/test_health.py` | 154 | fix line 2\ny = 2\n" |
| `TODO` | `tests/test_health.py` | 165 | refactor this module\nfunction foo() {}\n" |
| `TODO` | `tests/test_health.py` | 171 | do something\n" |
| `TODO` | `tests/test_health.py` | 328 | add greeting logic\n" |
| `TODO` | `tests/test_health.py` | 337 | should be captured |

## Uncovered Files (No Tests Found)

- `devmind\cli.py`
- `devmind\memory.py`
- `devmind\__init__.py`
- `devmind\analysis\__init__.py`
- `devmind\ingestion\comment_extractor.py`
- `devmind\ingestion\file_reader.py`
- `devmind\ingestion\git_parser.py`
- `devmind\integrations\claude_code.py`
- `devmind\web\app.py`
- `examples\demo_project\main.py`
- `examples\demo_project\utils.py`
- `tests\test_ast_parser.py`
- `tests\test_graph_digest.py`
- `tests\test_health.py`
- `tests\test_hybrid_engine.py`
- `tests\test_incremental.py`

---
*Generated by DevMind CLI (`devmind health`)*