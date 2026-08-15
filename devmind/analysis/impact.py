"""
devmind/analysis/impact.py

Blast Radius & Dependency Impact Analysis Engine for DevMind.
Performs static AST call graph traversal and import dependency tracking to
determine direct callers, transitive ripple effects, affected test suites,
and a calculated risk score before modifying code. Zero API cost.
"""

from __future__ import annotations

import ast
import os
import re
import pathlib
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional, Any

logger = logging.getLogger("devmind.analysis.impact")


@dataclass
class ImpactedNode:
    """Represents a function, class, or module impacted by a change."""
    symbol_name: str
    file_path: str
    line_number: int
    depth: int                    # 1 = Direct caller, 2 = 2nd-degree caller, etc.
    call_type: str                # "call" | "import" | "inheritance"
    enclosing_symbol: str = ""    # Name of function/class where call occurred
    snippet: str = ""             # Code snippet of the call site


@dataclass
class ImpactReport:
    """Complete blast radius report for a target symbol or file."""
    target_symbol: str
    target_file: Optional[str]
    target_type: str              # "function" | "class" | "file" | "symbol"
    target_line: Optional[int]
    direct_callers: List[ImpactedNode] = field(default_factory=list)
    transitive_callers: List[ImpactedNode] = field(default_factory=list)
    impacted_files: List[str] = field(default_factory=list)
    impacted_tests: List[str] = field(default_factory=list)
    severity: str = "LOW"         # "LOW" | "MODERATE" | "CRITICAL"
    risk_score: int = 0           # 0 - 100
    recommended_actions: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# 1. AST Call & Import Site Extractor
# ─────────────────────────────────────────────────────────────
class CallSiteVisitor(ast.NodeVisitor):
    """
    Traverses a Python AST to locate all function calls, imports, and
    class inheritances, tracking the enclosing function/class context.
    """
    def __init__(self, rel_path: str, lines: List[str]):
        self.rel_path = rel_path
        self.lines = lines
        self.scope_stack: List[str] = []
        # List of (called_symbol, line_number, call_type, enclosing_scope, snippet)
        self.references: List[Tuple[str, int, str, str, str]] = []

    def _get_snippet(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.lines):
            return self.lines[lineno - 1].strip()
        return ""

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef):
        # Track inheritance
        for base in node.bases:
            if isinstance(base, ast.Name):
                self.references.append((
                    base.id,
                    node.lineno,
                    "inheritance",
                    self.scope_stack[-1] if self.scope_stack else f"class {node.name}",
                    self._get_snippet(node.lineno)
                ))
            elif isinstance(base, ast.Attribute):
                self.references.append((
                    base.attr,
                    node.lineno,
                    "inheritance",
                    self.scope_stack[-1] if self.scope_stack else f"class {node.name}",
                    self._get_snippet(node.lineno)
                ))
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_Call(self, node: ast.Call):
        enclosing = self.scope_stack[-1] if self.scope_stack else "<module>"
        snippet = self._get_snippet(node.lineno)

        if isinstance(node.func, ast.Name):
            self.references.append((node.func.id, node.lineno, "call", enclosing, snippet))
        elif isinstance(node.func, ast.Attribute):
            self.references.append((node.func.attr, node.lineno, "call", enclosing, snippet))
            if isinstance(node.func.value, ast.Name):
                self.references.append((f"{node.func.value.id}.{node.func.attr}", node.lineno, "call", enclosing, snippet))

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        enclosing = self.scope_stack[-1] if self.scope_stack else "<module>"
        snippet = self._get_snippet(node.lineno)
        mod = node.module or ""
        for alias in node.names:
            sym_name = alias.name
            self.references.append((sym_name, node.lineno, "import", enclosing, snippet))
            if mod:
                self.references.append((f"{mod}.{sym_name}", node.lineno, "import", enclosing, snippet))

    def visit_Import(self, node: ast.Import):
        enclosing = self.scope_stack[-1] if self.scope_stack else "<module>"
        snippet = self._get_snippet(node.lineno)
        for alias in node.names:
            self.references.append((alias.name, node.lineno, "import", enclosing, snippet))


# ─────────────────────────────────────────────────────────────
# 2. Impact Analyzer Engine
# ─────────────────────────────────────────────────────────────
class ImpactAnalyzer:
    """
    Constructs codebase symbol definitions and call graphs to perform
    multi-hop BFS blast radius analysis.
    """
    def __init__(self, files_data: List[Dict[str, Any]]):
        self.files_data = files_data
        # symbol_name -> list of {file, line, type, name}
        self.definitions: Dict[str, List[Dict[str, Any]]] = {}
        # caller_file -> list of (called_sym, line, type, enclosing, snippet)
        self.file_references: Dict[str, List[Tuple[str, int, str, str, str]]] = {}
        # caller_symbol_key -> list of called_symbols
        self.caller_graph: Dict[str, List[Dict[str, Any]]] = {}
        self._build_index()

    def _build_index(self):
        code_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".c", ".cpp"}
        for f in self.files_data:
            rel = f["relative_path"].replace("\\", "/")
            ext = pathlib.Path(rel).suffix.lower()
            if ext not in code_exts:
                continue

            content = f.get("content", "")
            lines = content.splitlines()

            # Record definitions from AST
            syms = f.get("ast_symbols", {})
            for fn in syms.get("functions", []):
                self.definitions.setdefault(fn["name"], []).append({
                    "file": rel,
                    "line": fn.get("line", 1),
                    "type": "function",
                    "name": fn["name"]
                })
            for cls in syms.get("classes", []):
                self.definitions.setdefault(cls["name"], []).append({
                    "file": rel,
                    "line": cls.get("line", 1),
                    "type": "class",
                    "name": cls["name"]
                })
                for m in cls.get("methods", []):
                    self.definitions.setdefault(m["name"], []).append({
                        "file": rel,
                        "line": m.get("line", 1),
                        "type": "method",
                        "name": m["name"],
                        "class": cls["name"]
                    })

            # Parse AST for calls and imports
            if rel.endswith(".py"):
                try:
                    tree = ast.parse(content, filename=rel)
                    visitor = CallSiteVisitor(rel, lines)
                    visitor.visit(tree)
                    self.file_references[rel] = visitor.references
                except SyntaxError:
                    self.file_references[rel] = []
            else:
                # Regex fallback for JS/TS/Go/etc.
                refs = []
                for lineno, line in enumerate(lines, start=1):
                    calls = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", line)
                    for c in calls:
                        refs.append((c, lineno, "call", "<module>", line.strip()))
                self.file_references[rel] = refs

    def analyze_impact(self, target_query: str, max_depth: int = 3) -> ImpactReport:
        """
        Calculates blast radius for a given symbol name or file path.
        """
        target_clean = target_query.strip().replace("\\", "/")
        target_file = None
        target_type = "symbol"
        target_line = None

        # Check if target is a file
        is_file_target = False
        for f in self.files_data:
            rel = f["relative_path"].replace("\\", "/")
            if rel == target_clean or rel.endswith(f"/{target_clean}") or target_clean == pathlib.Path(rel).name:
                target_file = rel
                target_type = "file"
                is_file_target = True
                break

        # Check if target is a known defined symbol
        if not is_file_target and target_clean in self.definitions:
            defs = self.definitions[target_clean]
            if defs:
                target_file = defs[0]["file"]
                target_type = defs[0]["type"]
                target_line = defs[0]["line"]

        # If targeting a file, collect all exported symbols in that file
        target_symbols: Set[str] = set()
        if is_file_target:
            target_symbols.add(target_clean)
            target_symbols.add(pathlib.Path(target_clean).stem)
            for f in self.files_data:
                if f["relative_path"].replace("\\", "/") == target_file:
                    syms = f.get("ast_symbols", {})
                    for fn in syms.get("functions", []):
                        target_symbols.add(fn["name"])
                    for cls in syms.get("classes", []):
                        target_symbols.add(cls["name"])
        else:
            target_symbols.add(target_clean)

        # BFS Multi-Hop Traversal
        visited_call_sites: Set[Tuple[str, str, int]] = set()  # (file, caller_name, line)
        direct_callers: List[ImpactedNode] = []
        transitive_callers: List[ImpactedNode] = []
        impacted_files_set: Set[str] = set()
        impacted_tests_set: Set[str] = set()

        # Queue contains: (symbol_to_find, current_depth)
        queue: List[Tuple[str, int]] = [(sym, 1) for sym in target_symbols]
        searched_symbols: Set[str] = set(target_symbols)

        while queue:
            current_sym, current_depth = queue.pop(0)
            if current_depth > max_depth:
                continue

            # Scan all files for references to current_sym
            for file_path, refs in self.file_references.items():
                for called_name, lineno, call_type, enclosing, snippet in refs:
                    # Match exact symbol name or module attribute
                    if (
                        called_name == current_sym
                        or called_name.endswith(f".{current_sym}")
                        or (is_file_target and current_sym in called_name)
                    ):
                        # Avoid duplicate recordings
                        site_key = (file_path, enclosing, lineno)
                        if site_key in visited_call_sites:
                            continue
                        visited_call_sites.add(site_key)

                        # Skip self-calls inside the target's own definition
                        if target_file and file_path == target_file and enclosing == target_clean:
                            continue

                        node = ImpactedNode(
                            symbol_name=called_name,
                            file_path=file_path,
                            line_number=lineno,
                            depth=current_depth,
                            call_type=call_type,
                            enclosing_symbol=enclosing,
                            snippet=snippet
                        )

                        impacted_files_set.add(file_path)

                        # Detect test files
                        is_test = (
                            "tests" in file_path.lower().split("/")
                            or file_path.lower().startswith("test_")
                            or "test_" in pathlib.Path(file_path).name.lower()
                            or enclosing.startswith("test_")
                        )
                        if is_test:
                            impacted_tests_set.add(file_path)

                        if current_depth == 1:
                            direct_callers.append(node)
                        else:
                            transitive_callers.append(node)

                        # Enqueue enclosing function for next hop if it's a valid named symbol
                        if enclosing and enclosing != "<module>" and enclosing not in searched_symbols:
                            searched_symbols.add(enclosing)
                            queue.append((enclosing, current_depth + 1))

        # Calculate Severity & Risk Score
        risk_score = (
            len(direct_callers) * 8 +
            len(transitive_callers) * 3 +
            len(impacted_files_set) * 5 +
            len(impacted_tests_set) * 12
        )
        risk_score = min(100, risk_score)

        if risk_score >= 50 or len(direct_callers) >= 6 or len(impacted_tests_set) >= 3:
            severity = "CRITICAL"
        elif risk_score >= 20 or len(direct_callers) >= 2 or len(impacted_files_set) >= 2:
            severity = "MODERATE"
        else:
            severity = "LOW"

        # Generate Actionable Recommendations
        recommendations = []
        if severity == "CRITICAL":
            recommendations.append(f"⚠️ High blast radius: Modifying '{target_clean}' affects {len(impacted_files_set)} files across {len(direct_callers) + len(transitive_callers)} call sites.")
        if impacted_tests_set:
            test_list = ", ".join([f"`{t}`" for t in list(impacted_tests_set)[:3]])
            recommendations.append(f"🧪 Must run test suites: {test_list} to prevent regression.")
        else:
            recommendations.append("⚠️ No direct test coverage found for this symbol. Consider adding a unit test before refactoring.")

        if direct_callers:
            recommendations.append(f"🔍 Check signature compatibility with direct caller `{direct_callers[0].file_path}:{direct_callers[0].enclosing_symbol}`.")

        return ImpactReport(
            target_symbol=target_clean,
            target_file=target_file,
            target_type=target_type,
            target_line=target_line,
            direct_callers=direct_callers,
            transitive_callers=transitive_callers,
            impacted_files=sorted(list(impacted_files_set)),
            impacted_tests=sorted(list(impacted_tests_set)),
            severity=severity,
            risk_score=risk_score,
            recommended_actions=recommendations
        )


# ─────────────────────────────────────────────────────────────
# 3. Markdown Report Formatter
# ─────────────────────────────────────────────────────────────
def format_impact_markdown(report: ImpactReport) -> str:
    """
    Renders the ImpactReport into a structured Markdown document.
    """
    target_info = f"`{report.target_symbol}` ({report.target_type})"
    if report.target_file:
        loc = f"`{report.target_file}"
        if report.target_line:
            loc += f":L{report.target_line}"
        loc += "`"
        target_info += f" in {loc}"

    lines = [
        f"# 💥 DevMind Blast Radius Report: {report.target_symbol}",
        "",
        f"**Target:** {target_info}  ",
        f"**Severity:** `{report.severity}` (Risk Score: {report.risk_score}/100)  ",
        f"**Total Impacted Files:** {len(report.impacted_files)}  |  **Direct Callers:** {len(report.direct_callers)}  |  **Transitive Downstream:** {len(report.transitive_callers)}",
        "",
        "---",
        "",
        "## 🎯 1. Direct Call Sites (Depth 1)",
        "",
    ]

    if report.direct_callers:
        lines.append("| File | Line | Enclosing Symbol | Call Type | Code Snippet |")
        lines.append("|---|---|---|---|---|")
        for c in report.direct_callers:
            lines.append(f"| `{c.file_path}` | {c.line_number} | `{c.enclosing_symbol}` | `{c.call_type}` | `{c.snippet[:60]}` |")
    else:
        lines.append("*No direct internal callers detected in codebase.*")

    lines.extend([
        "",
        "---",
        "",
        "## 🌊 2. Transitive Downstream Callers (Depth 2+)",
        "",
    ])

    if report.transitive_callers:
        lines.append("| Depth | File | Enclosing Symbol | Code Snippet |")
        lines.append("|---|---|---|---|")
        for c in report.transitive_callers:
            lines.append(f"| Hop {c.depth} | `{c.file_path}:L{c.line_number}` | `{c.enclosing_symbol}` | `{c.snippet[:60]}` |")
    else:
        lines.append("*No multi-hop transitive ripple detected.*")

    lines.extend([
        "",
        "---",
        "",
        "## 🧪 3. Impacted Test Suites (Regression Checklist)",
        "",
    ])

    if report.impacted_tests:
        lines.append("Run these test suites before committing your changes:")
        lines.append("")
        for t in report.impacted_tests:
            lines.append(f"- [ ] `pytest {t}`")
    else:
        lines.append("⚠️ *No unit test files directly call this symbol.*")

    lines.extend([
        "",
        "---",
        "",
        "## 💡 4. Recommended Actions",
        "",
    ])

    for r in report.recommended_actions:
        lines.append(f"- {r}")

    lines.extend([
        "",
        "---",
        "*Generated by DevMind CLI (`devmind impact`)*"
    ])

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# 4. Main Entry Point
# ─────────────────────────────────────────────────────────────
def run_impact_analysis(directory: str, target: str, depth: int = 3) -> ImpactReport:
    """
    Public entry point for running blast radius impact analysis on a target symbol/file.
    """
    from devmind.ingestion.file_reader import scan_codebase_files

    root_path = pathlib.Path(directory).resolve()
    files = scan_codebase_files(str(root_path))
    analyzer = ImpactAnalyzer(files)
    return analyzer.analyze_impact(target, max_depth=depth)
