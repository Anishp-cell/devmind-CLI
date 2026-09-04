"""
devmind/analysis/onboarding.py

Instant Codebase Onboarding Guide Generator for DevMind.
Analyzes project manifests (package.json, pyproject.toml, Makefile, Dockerfile),
AST import topology (fan-in/centrality), git activity, and engineering debt
to produce a comprehensive, structured ONBOARDING.md and Rich terminal walkthrough.
"""

from __future__ import annotations

import os
import re
import pathlib
import json
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger("devmind.analysis.onboarding")

# ─────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────
@dataclass
class ProjectStack:
    languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    package_managers: List[str] = field(default_factory=list)
    entry_points: List[str] = field(default_factory=list)
    databases: List[str] = field(default_factory=list)


@dataclass
class SetupCommands:
    install: List[str] = field(default_factory=list)
    run: List[str] = field(default_factory=list)
    test: List[str] = field(default_factory=list)
    lint: List[str] = field(default_factory=list)


@dataclass
class KeyFileRole:
    path: str
    fan_in: int
    role_summary: str
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)


@dataclass
class GitActivitySummary:
    top_contributors: List[Dict[str, Any]] = field(default_factory=list)
    recent_commits: List[str] = field(default_factory=list)


@dataclass
class OnboardingReport:
    project_name: str
    directory: str
    total_files: int
    total_lines: int
    stack: ProjectStack
    commands: SetupCommands
    key_files: List[KeyFileRole]
    git_activity: GitActivitySummary
    debt_highlights: List[Dict[str, Any]] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# 1. Stack & Framework Detector
# ─────────────────────────────────────────────────────────────
def detect_project_stack(root_dir: str, files_data: List[Dict[str, Any]]) -> ProjectStack:
    """
    Detects primary programming languages, frameworks, package managers,
    and entry points by inspecting project manifests and AST imports.
    """
    root_path = pathlib.Path(root_dir).resolve()
    stack = ProjectStack()
    
    ext_counts: Dict[str, int] = {}
    for f in files_data:
        ext = pathlib.Path(f["relative_path"]).suffix.lower()
        if ext:
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            
    # Languages detection
    lang_map = {
        ".py": "Python",
        ".ts": "TypeScript",
        ".tsx": "TypeScript (React)",
        ".js": "JavaScript",
        ".jsx": "JavaScript (React)",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".cpp": "C++",
        ".c": "C",
        ".rb": "Ruby",
        ".php": "PHP",
    }
    for ext, lang in lang_map.items():
        if ext in ext_counts and lang not in stack.languages:
            stack.languages.append(lang)

    # Package managers & manifests detection
    if (root_path / "pyproject.toml").exists():
        stack.package_managers.append("pyproject.toml (pip/poetry/setuptools)")
    if (root_path / "requirements.txt").exists() and "requirements.txt (pip)" not in stack.package_managers:
        stack.package_managers.append("requirements.txt (pip)")
    if (root_path / "package.json").exists():
        if (root_path / "pnpm-lock.yaml").exists():
            stack.package_managers.append("pnpm")
        elif (root_path / "yarn.lock").exists():
            stack.package_managers.append("yarn")
        elif (root_path / "bun.lockb").exists():
            stack.package_managers.append("bun")
        else:
            stack.package_managers.append("npm")
    if (root_path / "Cargo.toml").exists():
        stack.package_managers.append("cargo (Rust)")
    if (root_path / "go.mod").exists():
        stack.package_managers.append("go mod")

    # Frameworks & Dependencies detection from imports and manifests
    all_imports = set()
    for f in files_data:
        syms = f.get("ast_symbols", {})
        for imp in syms.get("imports", []):
            root_imp = imp.split(".")[0].lower()
            all_imports.add(root_imp)

    # Check manifest contents for known frameworks
    manifest_text = ""
    for fname in ["package.json", "pyproject.toml", "requirements.txt", "Cargo.toml"]:
        p = root_path / fname
        if p.exists():
            try:
                manifest_text += p.read_text(encoding="utf-8", errors="ignore").lower() + "\n"
            except Exception:
                pass

    framework_keywords = {
        "fastapi": "FastAPI",
        "flask": "Flask",
        "django": "Django",
        "express": "Express.js",
        "react": "React",
        "next": "Next.js",
        "vue": "Vue.js",
        "svelte": "Svelte",
        "typer": "Typer CLI",
        "click": "Click CLI",
        "cognee": "Cognee Knowledge Engine",
        "langchain": "LangChain",
        "llamaindex": "LlamaIndex",
        "gin": "Gin (Go)",
        "actix": "Actix-Web (Rust)",
        "axum": "Axum (Rust)",
        "pytest": "Pytest",
        "jest": "Jest",
    }
    for kw, label in framework_keywords.items():
        if kw in all_imports or kw in manifest_text:
            if label not in stack.frameworks:
                stack.frameworks.append(label)

    # Databases detection
    db_keywords = {
        "sqlite": "SQLite",
        "sqlite3": "SQLite",
        "lancedb": "LanceDB (Vector DB)",
        "kuzu": "Kùzu (Graph DB)",
        "postgres": "PostgreSQL",
        "postgresql": "PostgreSQL",
        "psycopg2": "PostgreSQL",
        "asyncpg": "PostgreSQL",
        "mysql": "MySQL",
        "mongodb": "MongoDB",
        "redis": "Redis",
        "duckdb": "DuckDB",
    }
    for kw, label in db_keywords.items():
        if any(kw in imp.lower() for imp in all_imports) or kw in manifest_text:
            if label not in stack.databases:
                stack.databases.append(label)

    # Entry point detection
    code_extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java"}
    for f in files_data:
        rel = f["relative_path"].replace("\\", "/")
        ext = pathlib.Path(rel).suffix.lower()
        if ext not in code_extensions:
            continue

        content = f.get("content", "")
        # Common entry point filename patterns
        if rel in (
            "main.py", "app.py", "cli.py", "server.py", "run.py",
            "index.ts", "index.js", "server.js", "src/index.ts",
            "src/index.js", "src/main.rs", "main.go", "manage.py"
        ) or rel.endswith("/cli.py") or rel.endswith("/app.py") or rel.endswith("/main.py"):
            if rel not in stack.entry_points:
                stack.entry_points.append(rel)
        elif 'if __name__ == "__main__":' in content or "if __name__ == '__main__':" in content:
            if rel not in stack.entry_points:
                stack.entry_points.append(rel)

    return stack


# ─────────────────────────────────────────────────────────────
# 2. Setup & Run Command Extractor
# ─────────────────────────────────────────────────────────────
def extract_setup_commands(root_dir: str) -> SetupCommands:
    """
    Extracts install, run, test, and build commands from manifests,
    Makefiles, package.json, and pyproject.toml.
    """
    root_path = pathlib.Path(root_dir).resolve()
    cmds = SetupCommands()

    # 1. Makefile
    makefile_path = root_path / "Makefile"
    if makefile_path.exists():
        try:
            content = makefile_path.read_text(encoding="utf-8", errors="ignore")
            for target in ["install", "setup", "build", "run", "dev", "start", "test", "lint", "check"]:
                if re.search(rf"^{target}:", content, re.MULTILINE):
                    if target in ("install", "setup"):
                        cmds.install.append(f"make {target}")
                    elif target in ("run", "dev", "start"):
                        cmds.run.append(f"make {target}")
                    elif target in ("test", "check"):
                        cmds.test.append(f"make {target}")
                    elif target == "lint":
                        cmds.lint.append(f"make {target}")
        except Exception:
            pass

    # 2. package.json scripts
    pkg_json_path = root_path / "package.json"
    if pkg_json_path.exists():
        try:
            with open(pkg_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            scripts = data.get("scripts", {})
            if "npm" not in [c.split()[0] for c in cmds.install]:
                cmds.install.append("npm install")
            for s in ["dev", "start", "serve"]:
                if s in scripts:
                    cmds.run.append(f"npm run {s}")
            for s in ["test", "test:watch"]:
                if s in scripts:
                    cmds.test.append(f"npm run {s}")
            for s in ["lint", "typecheck", "format"]:
                if s in scripts:
                    cmds.lint.append(f"npm run {s}")
        except Exception:
            pass

    # 3. Python manifests (pyproject.toml / requirements.txt / setup.py)
    if (root_path / "pyproject.toml").exists() or (root_path / "setup.py").exists():
        if not cmds.install:
            cmds.install.append("pip install -e .")
    elif (root_path / "requirements.txt").exists():
        if not cmds.install:
            cmds.install.append("pip install -r requirements.txt")

    if (root_path / "pytest.ini").exists() or (root_path / "tests").exists():
        if "pytest" not in cmds.test and not any("test" in c for c in cmds.test):
            cmds.test.append("pytest")

    # 4. Cargo / Rust
    if (root_path / "Cargo.toml").exists():
        cmds.install.append("cargo build")
        cmds.run.append("cargo run")
        cmds.test.append("cargo test")

    # 5. Go
    if (root_path / "go.mod").exists():
        cmds.install.append("go mod download")
        cmds.run.append("go run main.go")
        cmds.test.append("go test ./...")

    # 6. Dockerfile / docker-compose
    if (root_path / "docker-compose.yml").exists() or (root_path / "docker-compose.yaml").exists():
        cmds.run.append("docker compose up --build")
    elif (root_path / "Dockerfile").exists():
        cmds.run.append("docker build -t app . && docker run -p 8000:8000 app")

    return cmds


# ─────────────────────────────────────────────────────────────
# 3. Architectural File Ranking (Fan-In Analysis)
# ─────────────────────────────────────────────────────────────
def rank_architectural_files(files_data: List[Dict[str, Any]], top_n: int = 8) -> List[KeyFileRole]:
    """
    Ranks the most critical architectural files by calculating fan-in
    (how many other files import this module or its symbols).
    """
    file_map: Dict[str, Dict[str, Any]] = {}
    fan_in_scores: Dict[str, int] = {}

    for f in files_data:
        rel = f["relative_path"].replace("\\", "/")
        file_map[rel] = f
        fan_in_scores[rel] = 0

    # Build import dependency graph
    for f in files_data:
        rel_source = f["relative_path"].replace("\\", "/")
        syms = f.get("ast_symbols", {})
        imports = syms.get("imports", [])
        
        for imp in imports:
            # Check all prefix permutations of the import: e.g. "core.auth.AuthManager" -> ["core", "core/auth", "core/auth/AuthManager"]
            parts = imp.split(".")
            prefixes = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
            
            for target_rel in file_map.keys():
                stem = target_rel.rsplit(".", 1)[0]
                # Match if stem equals any prefix, or target_rel ends with prefix + ext
                if any(stem == p or stem.endswith(f"/{p}") or target_rel == f"{p}.py" for p in prefixes):
                    if target_rel != rel_source:
                        fan_in_scores[target_rel] = fan_in_scores.get(target_rel, 0) + 1

    # Sort files by fan-in score descending, then by number of classes/functions
    def score_file(rel: str) -> tuple:
        f = file_map[rel]
        syms = f.get("ast_symbols", {})
        classes = len(syms.get("classes", []))
        funcs = len(syms.get("functions", []))
        return (fan_in_scores.get(rel, 0), classes * 2 + funcs, len(f.get("content", "")))

    sorted_files = sorted(file_map.keys(), key=score_file, reverse=True)

    key_roles: List[KeyFileRole] = []
    for rel in sorted_files[:top_n]:
        f = file_map[rel]
        syms = f.get("ast_symbols", {})
        doc = syms.get("module_docstring", "").strip()
        if not doc:
            # Generate summary based on classes / functions
            cls_names = [c["name"] for c in syms.get("classes", [])]
            fn_names = [fn["name"] for fn in syms.get("functions", [])]
            if cls_names:
                doc = f"Defines core classes: {', '.join(cls_names[:3])}"
            elif fn_names:
                doc = f"Exports key functions: {', '.join(fn_names[:3])}"
            else:
                doc = "Core module file"
        else:
            doc = doc.split("\n")[0].strip()

        cls_names = [c["name"] for c in syms.get("classes", [])]
        fn_names = [fn["name"] for fn in syms.get("functions", [])]

        key_roles.append(KeyFileRole(
            path=rel,
            fan_in=fan_in_scores.get(rel, 0),
            role_summary=doc,
            classes=cls_names,
            functions=fn_names
        ))

    return key_roles


# ─────────────────────────────────────────────────────────────
# 4. Git Activity Summary
# ─────────────────────────────────────────────────────────────
def summarize_git_activity(root_dir: str) -> GitActivitySummary:
    """
    Extracts top recent contributors and major commit history.
    """
    summary = GitActivitySummary()
    try:
        from devmind.ingestion.git_parser import get_git_history
        logs = get_git_history(root_dir, max_commits=10)
        summary.recent_commits = logs[:6]
    except Exception as e:
        logger.debug(f"Git history lookup failed: {e}")
    return summary


# ─────────────────────────────────────────────────────────────
# 5. Core Generator Function
# ─────────────────────────────────────────────────────────────
def generate_onboarding_report(root_dir: str) -> OnboardingReport:
    """
    Analyzes the entire codebase directory and generates an OnboardingReport.
    """
    from devmind.ingestion.file_reader import scan_codebase_files
    from devmind.analysis.health import scan_debt_tags

    root_path = pathlib.Path(root_dir).resolve()
    project_name = root_path.name
    files = scan_codebase_files(str(root_path))

    stack = detect_project_stack(str(root_path), files)
    commands = extract_setup_commands(str(root_path))
    key_files = rank_architectural_files(files, top_n=8)
    git_act = summarize_git_activity(str(root_path))

    # Collect prominent debt highlights (TODOs, FIXMEs)
    all_debt = []
    total_lines = 0
    for f in files:
        content = f.get("content", "")
        total_lines += content.count("\n") + 1
        rel = f["relative_path"].replace("\\", "/")
        tags = scan_debt_tags(content, rel)
        for t in tags:
            if t.tag in ("BUG", "FIXME", "TODO"):
                all_debt.append({"tag": t.tag, "file": t.file, "line": t.line, "text": t.text})

    return OnboardingReport(
        project_name=project_name,
        directory=str(root_path),
        total_files=len(files),
        total_lines=total_lines,
        stack=stack,
        commands=commands,
        key_files=key_files,
        git_activity=git_act,
        debt_highlights=all_debt[:8]
    )


def format_onboarding_markdown(report: OnboardingReport) -> str:
    """
    Renders the OnboardingReport into a clean, GitHub-flavored Markdown guide.
    """
    lines = [
        f"# 🚀 Onboarding Guide: {report.project_name}",
        "",
        "> *Generated automatically by DevMind CLI (`devmind onboard`)*",
        "",
        "---",
        "",
        "## 🏗️ 1. Technology Stack & Environment",
        "",
        f"- **Primary Languages**: {', '.join(report.stack.languages) if report.stack.languages else 'Generic'}",
        f"- **Frameworks / Libraries**: {', '.join(report.stack.frameworks) if report.stack.frameworks else 'None detected'}",
        f"- **Package Managers / Manifests**: {', '.join(report.stack.package_managers) if report.stack.package_managers else 'Standard'}",
        f"- **Databases / Storage**: {', '.join(report.stack.databases) if report.stack.databases else 'In-memory / File storage'}",
        f"- **Primary Entry Points**: {', '.join([f'`{e}`' for e in report.stack.entry_points]) if report.stack.entry_points else '`cli.py` or `main.py`'}",
        "",
        "---",
        "",
        "## ⚙️ 2. Quickstart & Setup Commands",
        "",
        "Run the following commands in your terminal to set up and verify the repository:",
        "",
        "```bash",
    ]

    # Install
    if report.commands.install:
        lines.append("# 1. Install dependencies")
        for c in report.commands.install:
            lines.append(c)
        lines.append("")

    # Run
    if report.commands.run:
        lines.append("# 2. Run the application / dev server")
        for c in report.commands.run:
            lines.append(c)
        lines.append("")

    # Test
    if report.commands.test:
        lines.append("# 3. Execute test suite")
        for c in report.commands.test:
            lines.append(c)
        lines.append("")

    # Lint
    if report.commands.lint:
        lines.append("# 4. Lint and code formatting")
        for c in report.commands.lint:
            lines.append(c)
        lines.append("")

    if not (report.commands.install or report.commands.run or report.commands.test):
        lines.append("# No explicit setup scripts detected. Use standard language tooling.")

    lines.extend([
        "```",
        "",
        "---",
        "",
        "## 🗺️ 3. Core Architecture & Key Files",
        "",
        "The following files are the most central and imported modules in the codebase. Start reading here:",
        "",
        "| File | Role / Summary | Key Classes / Functions |",
        "|---|---|---|",
    ])

    for kf in report.key_files:
        symbols = []
        if kf.classes:
            symbols.extend([f"`class {c}`" for c in kf.classes[:2]])
        if kf.functions:
            symbols.extend([f"`def {fn}()`" for fn in kf.functions[:2]])
        sym_str = ", ".join(symbols) if symbols else "-"
        lines.append(f"| [`{kf.path}`]({kf.path}) | {kf.role_summary} | {sym_str} |")

    lines.extend([
        "",
        "---",
        "",
        "## 📋 4. Known Technical Debt & Active TODOs",
        "",
        "Keep these areas in mind when contributing or refactoring:",
        "",
    ])

    if report.debt_highlights:
        lines.append("| Type | Location | Notes |")
        lines.append("|---|---|---|")
        for d in report.debt_highlights:
            lines.append(f"| **{d['tag']}** | `{d['file']}:L{d['line']}` | {d['text']} |")
    else:
        lines.append("*No prominent TODOs or FIXMEs detected.*")

    lines.extend([
        "",
        "---",
        "",
        "## 🧠 5. Exploring with DevMind Memory",
        "",
        "You can explore this codebase using natural language through DevMind:",
        "",
        "```bash",
        "# Ingest codebase memory",
        "devmind remember",
        "",
        "# Ask anything about architecture or workflows",
        'devmind ask "How does the application initialize and handle core workflows?"',
        "",
        "# Check technical debt and code health score",
        "devmind health",
        "",
        "# Launch interactive visual dependency graph",
        "devmind graph",
        "```",
    ])

    return "\n".join(lines)
