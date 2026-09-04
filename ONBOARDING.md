# 🚀 Onboarding Guide: devmind

> *Generated automatically by DevMind CLI (`devmind onboard`)*

---

## 🏗️ 1. Technology Stack & Environment

- **Primary Languages**: Python
- **Frameworks / Libraries**: FastAPI, Typer CLI, Cognee Knowledge Engine, Pytest
- **Package Managers / Manifests**: pyproject.toml (pip/poetry/setuptools), requirements.txt (pip)
- **Databases / Storage**: In-memory / File storage
- **Primary Entry Points**: `devmind/cli.py`, `devmind/analysis/onboarding.py`, `devmind/integrations/claude_code.py`, `devmind/web/app.py`, `examples/demo_project/main.py`, `tests/test_ast_parser.py`, `tests/test_graph_digest.py`, `tests/test_hybrid_engine.py`, `tests/test_incremental.py`

---

## ⚙️ 2. Quickstart & Setup Commands

Run the following commands in your terminal to set up and verify the repository:

```bash
# 1. Install dependencies
pip install -e .

# 3. Execute test suite
pytest

```

---

## 🗺️ 3. Core Architecture & Key Files

The following files are the most central and imported modules in the codebase. Start reading here:

| File | Role / Summary | Key Classes / Functions |
|---|---|---|
| [`devmind/memory.py`](devmind/memory.py) | Exports key functions: mark_key_cooldown, get_active_keys, _install_litellm_key_rotation | `def mark_key_cooldown()`, `def get_active_keys()` |
| [`devmind/analysis/secure_patterns.py`](devmind/analysis/secure_patterns.py) | devmind/analysis/secure_patterns.py | `def calculate_shannon_entropy()` |
| [`devmind/analysis/health.py`](devmind/analysis/health.py) | devmind/analysis/health.py | `class FunctionComplexity`, `class CodeSmell`, `def _compute_cyclomatic_complexity()`, `def analyze_complexity()` |
| [`devmind/analysis/onboarding.py`](devmind/analysis/onboarding.py) | devmind/analysis/onboarding.py | `class ProjectStack`, `class SetupCommands`, `def detect_project_stack()`, `def extract_setup_commands()` |
| [`devmind/analysis/secure.py`](devmind/analysis/secure.py) | devmind/analysis/secure.py | `class SecurityFinding`, `class SecurityReport`, `def format_secure_markdown()`, `def run_security_analysis()` |
| [`devmind/version_checker.py`](devmind/version_checker.py) | devmind/version_checker.py | `def get_cache_file_path()`, `def parse_version_tuple()` |
| [`devmind/analysis/drift.py`](devmind/analysis/drift.py) | Architecture Drift & Churn Detector. | `def _file_to_module()`, `def pathlib_parts()` |
| [`devmind/ingestion/ast_parser.py`](devmind/ingestion/ast_parser.py) | DevMind AST Parser: Deterministic local code symbol extraction. | `def parse_python_ast()`, `def parse_generic_code_symbols()` |

---

## 📋 4. Known Technical Debt & Active TODOs

Keep these areas in mind when contributing or refactoring:

| Type | Location | Notes |
|---|---|---|
| **FIXME** | `ONBOARDING.md:L56` | ...') | |
| **TODO** | `devmind/analysis/health.py:L259` | ...' or '// FIXME ...') |
| **FIXME** | `examples/demo_project/main.py:L16` | Deduplicate cart_items before processing |
| **TODO** | `examples/demo_project/utils.py:L8` | Add international phone format validations |
| **TODO** | `tests/test_health.py:L134` | fix this later\n" |
| **FIXME** | `tests/test_health.py:L139` | broken auth flow\ndef auth(): pass\n" |
| **BUG** | `tests/test_health.py:L144` | off-by-one in loop\nfor i in range(10): pass\n" |
| **TODO** | `tests/test_health.py:L154` | fix line 2\ny = 2\n" |

---

## 🧠 5. Exploring with DevMind Memory

You can explore this codebase using natural language through DevMind:

```bash
# Ingest codebase memory
devmind remember

# Ask anything about architecture or workflows
devmind ask "How does data ingestion and graph indexing work?"

# Check technical debt and code health score
devmind health

# Launch interactive visual dependency graph
devmind graph
```