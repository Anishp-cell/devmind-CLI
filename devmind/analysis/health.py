"""
devmind/analysis/health.py

Zero-API-call codebase health analysis engine for DevMind.
Computes cyclomatic complexity, detects dead imports, code smells,
technical debt tags, and test coverage gaps using only Python stdlib
(ast, re, pathlib) — no LLM, no internet, no cost.
"""

from __future__ import annotations

import ast
import os
import re
import pathlib
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("devmind.analysis.health")

# ─────────────────────────────────────────────────────────────
# Configuration Thresholds
# ─────────────────────────────────────────────────────────────
COMPLEXITY_HOTSPOT_THRESHOLD = 10  # CC >= this → hotspot
GOD_CLASS_LINE_THRESHOLD = 300     # class > this many lines → god class
LONG_FUNCTION_LINE_THRESHOLD = 50  # function > this many lines → long function
DEEP_NESTING_THRESHOLD = 4         # nesting depth > this → flagged

# Tags that count as engineering debt
DEBT_TAGS = {"TODO", "FIXME", "BUG", "HACK", "XXX", "DEPRECATED"}

# Source file extensions to include in coverage analysis
SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs"}

# ─────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────
@dataclass
class FunctionComplexity:
    """Cyclomatic complexity record for a single function/method."""
    name: str
    file: str
    line: int
    complexity: int
    is_hotspot: bool


@dataclass
class CodeSmell:
    """A single code smell finding."""
    kind: str        # "god_class" | "long_function" | "deep_nesting"
    name: str
    file: str
    line: int
    detail: str      # Human-readable explanation e.g. "312 lines"


@dataclass
class DebtTag:
    """A single TODO/FIXME/BUG/HACK comment located in the codebase."""
    tag: str
    file: str
    line: int
    text: str


@dataclass
class DeadImport:
    """An import statement whose name appears unused in the file."""
    import_name: str
    file: str
    line: int


@dataclass
class HealthReport:
    """Complete health report for a codebase directory."""
    project_name: str
    directory: str
    total_files: int
    total_py_files: int
    total_functions: int
    total_classes: int
    total_lines: int
    # Complexity
    function_complexities: list[FunctionComplexity] = field(default_factory=list)
    avg_complexity: float = 0.0
    # Smells
    code_smells: list[CodeSmell] = field(default_factory=list)
    # Debt
    debt_tags: list[DebtTag] = field(default_factory=list)
    # Dead code
    dead_imports: list[DeadImport] = field(default_factory=list)
    # Test coverage
    source_files: list[str] = field(default_factory=list)
    uncovered_files: list[str] = field(default_factory=list)
    # Score
    health_score: int = 100
    grade: str = "A"


# ─────────────────────────────────────────────────────────────
# Complexity Analyzer
# ─────────────────────────────────────────────────────────────
# AST node types that each contribute +1 to cyclomatic complexity
_COMPLEXITY_NODES = (
    ast.If, ast.For, ast.While, ast.Try, ast.With,
    ast.ExceptHandler, ast.Assert, ast.comprehension,
)


def _compute_cyclomatic_complexity(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """
    Compute McCabe cyclomatic complexity for a single function.
    Starts at 1 (one linear path) and adds 1 for every branching point.
    Also adds 1 for each boolean operator (and/or) in conditions.
    """
    complexity = 1
    for node in ast.walk(func_node):
        if isinstance(node, _COMPLEXITY_NODES):
            complexity += 1
        # Each 'and' / 'or' in a BoolOp adds extra paths
        elif isinstance(node, ast.BoolOp):
            complexity += len(node.values) - 1
    return complexity


def analyze_complexity(content: str, rel_path: str) -> list[FunctionComplexity]:
    """
    Parse Python source, walk all function/method definitions, and return
    a list of FunctionComplexity records sorted by complexity descending.
    """
    results = []
    try:
        tree = ast.parse(content, filename=rel_path)
    except SyntaxError:
        return results

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cc = _compute_cyclomatic_complexity(node)
            results.append(FunctionComplexity(
                name=node.name,
                file=rel_path,
                line=node.lineno,
                complexity=cc,
                is_hotspot=(cc >= COMPLEXITY_HOTSPOT_THRESHOLD),
            ))

    results.sort(key=lambda x: x.complexity, reverse=True)
    return results


# ─────────────────────────────────────────────────────────────
# Smell Detector
# ─────────────────────────────────────────────────────────────
def _get_function_end_line(func_node: ast.FunctionDef | ast.AsyncFunctionDef, total_lines: int) -> int:
    """Estimate the end line of a function using the last child node's line."""
    last_line = func_node.lineno
    for child in ast.walk(func_node):
        if hasattr(child, "lineno"):
            last_line = max(last_line, child.lineno)
    return last_line


def _get_class_end_line(class_node: ast.ClassDef, total_lines: int) -> int:
    """Estimate the end line of a class using the last child node's line."""
    last_line = class_node.lineno
    for child in ast.walk(class_node):
        if hasattr(child, "lineno"):
            last_line = max(last_line, child.lineno)
    return last_line


def _max_nesting_depth(node: ast.AST, current_depth: int = 0) -> int:
    """Recursively find the maximum nesting depth of control flow nodes."""
    _NESTING_NODES = (ast.If, ast.For, ast.While, ast.With, ast.Try)
    max_depth = current_depth
    if isinstance(node, _NESTING_NODES):
        current_depth += 1
        max_depth = current_depth
    for child in ast.iter_child_nodes(node):
        child_depth = _max_nesting_depth(child, current_depth)
        max_depth = max(max_depth, child_depth)
    return max_depth


def detect_code_smells(content: str, rel_path: str) -> list[CodeSmell]:
    """
    Detect god classes, long functions, and deeply nested code in Python files.
    """
    smells = []
    try:
        tree = ast.parse(content, filename=rel_path)
    except SyntaxError:
        return smells

    total_lines = content.count("\n") + 1

    for node in ast.walk(tree):
        # God Class detection
        if isinstance(node, ast.ClassDef):
            end_line = _get_class_end_line(node, total_lines)
            class_lines = end_line - node.lineno + 1
            if class_lines > GOD_CLASS_LINE_THRESHOLD:
                smells.append(CodeSmell(
                    kind="god_class",
                    name=node.name,
                    file=rel_path,
                    line=node.lineno,
                    detail=f"{class_lines} lines",
                ))

        # Long function / method detection
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_line = _get_function_end_line(node, total_lines)
            fn_lines = end_line - node.lineno + 1
            if fn_lines > LONG_FUNCTION_LINE_THRESHOLD:
                smells.append(CodeSmell(
                    kind="long_function",
                    name=node.name,
                    file=rel_path,
                    line=node.lineno,
                    detail=f"{fn_lines} lines",
                ))

            # Deep nesting within this function
            depth = _max_nesting_depth(node)
            if depth > DEEP_NESTING_THRESHOLD:
                smells.append(CodeSmell(
                    kind="deep_nesting",
                    name=node.name,
                    file=rel_path,
                    line=node.lineno,
                    detail=f"nesting depth {depth}",
                ))

    return smells


# ─────────────────────────────────────────────────────────────
# Debt Tag Scanner
# ─────────────────────────────────────────────────────────────
# Tags that count as engineering debt (must start comment or be followed by delimiter like ':')
_TAG_RE = re.compile(
    r"^\s*(?:[\*\-\#\/]*\s*)?(" + "|".join(DEBT_TAGS) + r")(?:\s*[:\(\[\-]\s*|\s+)(.*)",
    re.IGNORECASE
)
# Comment starters for various languages
_COMMENT_RE = re.compile(r"(?:#|//)\s*(.*)")
_BLOCK_COMMENT_OPEN = re.compile(r"/\*")


def scan_debt_tags(content: str, rel_path: str) -> list[DebtTag]:
    """
    Scan source file content line-by-line for engineering debt tags.
    Only matches tags that appear inside actual comments (# or //) and
    are formatted as tags (e.g. '# TODO: ...' or '// FIXME ...')
    to avoid false positives from regular sentences mentioning words like 'bug'.
    """
    tags = []
    lines = content.splitlines()

    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        comment_match = _COMMENT_RE.search(line)
        if comment_match:
            comment_text = comment_match.group(1).strip()
            tag_match = _TAG_RE.match(comment_text)
            if tag_match:
                tag_word = tag_match.group(1).upper()
                tag_text = tag_match.group(2).strip()
                tags.append(DebtTag(
                    tag=tag_word,
                    file=rel_path,
                    line=lineno,
                    text=(tag_text[:80] + "...") if len(tag_text) > 80 else tag_text,
                ))

    seen = set()
    unique_tags = []
    for t in tags:
        key = (t.file, t.line, t.tag)
        if key not in seen:
            seen.add(key)
            unique_tags.append(t)

    return unique_tags


# ─────────────────────────────────────────────────────────────
# Dead Import Detector (Python only)
# ─────────────────────────────────────────────────────────────
def detect_dead_imports(content: str, rel_path: str) -> list[DeadImport]:
    """
    Detect potentially unused imports in Python files by:
    1. Extracting all imported names
    2. Collecting all Name/Attribute usages in the AST
    3. Flagging imports whose names never appear as usages
    
    Note: This is a heuristic — it may produce false positives for
    __all__ re-exports, type annotations only, or dynamic usages.
    """
    dead = []
    try:
        tree = ast.parse(content, filename=rel_path)
    except SyntaxError:
        return dead

    # Collect (name, alias, lineno) for all imports
    imported: list[tuple[str, str, int]] = []  # (original, local_name, line)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname if alias.asname else alias.name.split(".")[0]
                imported.append((alias.name, local_name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue  # Can't track star imports
                local_name = alias.asname if alias.asname else alias.name
                imported.append((alias.name, local_name, node.lineno))

    if not imported:
        return dead

    # Collect all Name and Attribute usages (excluding the import nodes themselves)
    used_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Store):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            # Handle `module.attr` — track the root `module` name
            if isinstance(node.value, ast.Name):
                used_names.add(node.value.id)

    # Also check __all__ list for re-exports
    all_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, ast.List):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant):
                                all_names.add(str(elt.value))

    effectively_used = used_names | all_names

    # Flag imports whose local name never appears
    for original, local_name, lineno in imported:
        if local_name not in effectively_used:
            dead.append(DeadImport(
                import_name=original,
                file=rel_path,
                line=lineno,
            ))

    return dead


# ─────────────────────────────────────────────────────────────
# Test Coverage Mapper
# ─────────────────────────────────────────────────────────────
def map_test_coverage(
    source_files: list[str],
    root_dir: str
) -> tuple[list[str], list[str]]:
    """
    For each source file, check if a corresponding test file exists anywhere
    in the project. Returns (covered_files, uncovered_files).
    
    Excludes test files themselves (e.g. tests/* or test_*.py) from needing tests.
    """
    root = pathlib.Path(root_dir)
    covered: list[str] = []
    uncovered: list[str] = []

    # Pre-build a set of all files in the project for fast lookup
    all_project_files: set[str] = set()
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            full = pathlib.Path(dirpath) / fname
            try:
                rel = str(full.relative_to(root))
                all_project_files.add(rel.lower().replace("\\", "/"))
            except ValueError:
                pass

    for src_file in source_files:
        p = pathlib.Path(src_file)
        ext = p.suffix.lower()

        # Only check coverage for actual source code files (not docs/configs)
        if ext not in SOURCE_EXTENSIONS:
            continue

        # Skip test files and examples themselves from requiring unit tests
        parts_lower = [part.lower() for part in p.parts]
        if "tests" in parts_lower or "test" in parts_lower or p.name.startswith("test_") or p.name.endswith("_test.py"):
            continue

        stem = p.stem  # filename without extension
        parent = p.parent  # directory of the file

        # Candidate test file patterns to search for
        candidates = [
            f"tests/test_{stem}{ext}",
            f"tests/{parent}/test_{stem}{ext}",
            f"test_{stem}{ext}",
            f"{parent}/test_{stem}{ext}",
            f"{parent}/tests/test_{stem}{ext}",
            # Also accept spec files (JS ecosystem)
            f"tests/{stem}.test{ext}",
            f"{parent}/{stem}.test{ext}",
            f"{parent}/{stem}.spec{ext}",
        ]

        found = any(
            c.lower().replace("\\", "/") in all_project_files
            for c in candidates
        )

        if found:
            covered.append(src_file)
        else:
            uncovered.append(src_file)

    return covered, uncovered


# ─────────────────────────────────────────────────────────────
# Health Scorer
# ─────────────────────────────────────────────────────────────
def compute_health_score(report: HealthReport) -> tuple[int, str]:
    """
    Compute a weighted 0-100 health score from the analysis results.
    
    Penalty breakdown (max total = 100 deductions):
      - Complexity hotspots  : up to 25 pts
      - Code smells          : up to 20 pts
      - Debt tags            : up to 15 pts
      - Dead imports         : up to 10 pts
      - Test coverage gaps   : up to 30 pts
    """
    score = 100.0

    total_fns = max(report.total_functions, 1)
    total_files = max(report.total_files, 1)
    total_py = max(report.total_py_files, 1)
    total_lines = max(report.total_lines, 100)

    # 1. Complexity penalty
    hotspot_count = sum(1 for fc in report.function_complexities if fc.is_hotspot)
    hotspot_ratio = hotspot_count / total_fns
    score -= min(hotspot_ratio * 25, 25)

    # 2. Smell penalty
    smell_count = len(report.code_smells)
    smell_ratio = smell_count / total_files
    score -= min(smell_ratio * 20, 20)

    # 3. Debt tag penalty
    debt_count = len(report.debt_tags)
    # Normalise: penalise proportional to 1 tag per 100 lines being "bad"
    debt_density = debt_count / (total_lines / 100)
    score -= min(debt_density * 15, 15)

    # 4. Dead import penalty (minor — heuristic may have false positives)
    dead_ratio = len(report.dead_imports) / total_py
    score -= min(dead_ratio * 10, 10)

    # 5. Test coverage penalty
    coverage_source_files = [
        f for f in report.source_files
        if pathlib.Path(f).suffix.lower() in SOURCE_EXTENSIONS
    ]
    coverage_total = max(len(coverage_source_files), 1)
    uncovered_ratio = len(report.uncovered_files) / coverage_total
    score -= min(uncovered_ratio * 30, 30)

    final_score = max(0, int(score))

    if final_score >= 85:
        grade = "A"
    elif final_score >= 70:
        grade = "B"
    elif final_score >= 55:
        grade = "C"
    elif final_score >= 40:
        grade = "D"
    else:
        grade = "F"

    return final_score, grade


# ─────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────
def run_health_analysis(directory: str) -> HealthReport:
    """
    Run the full health analysis pipeline on a codebase directory.
    
    This is the single public function that cli.py calls.
    No LLM calls, no API calls — 100% local static analysis.
    
    Returns a fully populated HealthReport dataclass.
    """
    from devmind.ingestion.file_reader import scan_codebase_files

    root_path = pathlib.Path(directory).resolve()
    project_name = root_path.name
    logger.info(f"Starting health analysis for: {root_path}")

    # Scan all codebase files (reuses existing file_reader pipeline)
    files = scan_codebase_files(str(root_path))
    if not files:
        logger.warning("No files found for health analysis.")
        return HealthReport(
            project_name=project_name,
            directory=str(root_path),
            total_files=0,
            total_py_files=0,
            total_functions=0,
            total_classes=0,
            total_lines=0,
        )

    # Build initial report scaffolding
    report = HealthReport(
        project_name=project_name,
        directory=str(root_path),
        total_files=len(files),
        total_py_files=0,
        total_functions=0,
        total_classes=0,
        total_lines=0,
        source_files=[f["relative_path"] for f in files],
    )

    all_complexities: list[FunctionComplexity] = []
    all_smells: list[CodeSmell] = []
    all_debt: list[DebtTag] = []
    all_dead: list[DeadImport] = []
    total_complexity_sum = 0
    complexity_fn_count = 0

    for file_data in files:
        rel_path = file_data["relative_path"].replace("\\", "/")
        content = file_data["content"]
        ext = pathlib.Path(rel_path).suffix.lower()

        lines_in_file = content.count("\n") + 1
        report.total_lines += lines_in_file

        # Count AST symbols from pre-parsed data
        ast_syms = file_data.get("ast_symbols", {})
        report.total_functions += len(ast_syms.get("functions", []))
        for cls in ast_syms.get("classes", []):
            report.total_functions += len(cls.get("methods", []))
        report.total_classes += len(ast_syms.get("classes", []))

        # Deep Python analysis
        if ext == ".py":
            report.total_py_files += 1

            # Complexity
            complexities = analyze_complexity(content, rel_path)
            all_complexities.extend(complexities)
            for fc in complexities:
                total_complexity_sum += fc.complexity
                complexity_fn_count += 1

            # Code smells
            smells = detect_code_smells(content, rel_path)
            all_smells.extend(smells)

            # Dead imports
            dead = detect_dead_imports(content, rel_path)
            all_dead.extend(dead)

        # Debt tags for all supported files
        if ext in {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java"}:
            debt = scan_debt_tags(content, rel_path)
            all_debt.extend(debt)

    # Sort and assign
    all_complexities.sort(key=lambda x: x.complexity, reverse=True)
    report.function_complexities = all_complexities
    report.avg_complexity = (
        total_complexity_sum / complexity_fn_count
        if complexity_fn_count > 0 else 0.0
    )
    report.code_smells = all_smells
    report.debt_tags = all_debt
    report.dead_imports = all_dead

    # Test coverage mapping
    covered, uncovered = map_test_coverage(report.source_files, str(root_path))
    report.uncovered_files = uncovered

    # Score
    report.health_score, report.grade = compute_health_score(report)

    logger.info(
        f"Health analysis complete. Score: {report.health_score}/100 "
        f"({report.grade}) | {len(all_complexities)} fns | "
        f"{len(all_smells)} smells | {len(all_debt)} debt tags"
    )
    return report
