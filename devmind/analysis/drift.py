"""
Architecture Drift & Churn Detector.

Runs 100% offline (no LLM/API calls) against the local filesystem and git
history to detect circular imports, layer-boundary violations, churn/complexity
hotspots, and coupling issues.
"""
import ast
import os
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from git import Repo, InvalidGitRepositoryError

logger = logging.getLogger("devmind.analysis.drift")

# ── Layer boundary rules ─────────────────────────────────────────────────
# Each rule: (source_module_prefix, [forbidden_target_prefixes], reason)
# A violation occurs when a file whose dotted module name starts with the
# source prefix imports a module starting with one of the forbidden prefixes.
LAYER_RULES = [
    (
        "devmind.memory",
        ["devmind.cli", "devmind.web"],
        "Core memory layer must not depend on presentation layers (CLI/Web).",
    ),
    (
        "devmind.ingestion",
        ["devmind.cli", "devmind.web", "devmind.integrations"],
        "Ingestion layer must remain independent of interface/integration layers.",
    ),
    (
        "devmind.analysis",
        ["devmind.cli", "devmind.web"],
        "Analysis layer must remain independent of presentation layers (CLI/Web).",
    ),
]

DEFAULT_CC_THRESHOLD = 15
DEFAULT_CHURN_THRESHOLD = 10
DEFAULT_FAN_OUT_THRESHOLD = 10

_DECISION_NODE_TYPES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.Assert,
    ast.BoolOp,
    ast.IfExp,
    ast.comprehension,
)


# ─────────────────────────────────────────────────────────────────────────
# Import graph construction
# ─────────────────────────────────────────────────────────────────────────

def _file_to_module(relative_path: str) -> str:
    """Converts a relative file path (posix or native separators) to a dotted module name."""
    parts = pathlib_parts(relative_path)
    if parts and parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][: -len(".py")]
    return ".".join(parts)


def pathlib_parts(relative_path: str) -> list:
    normalized = relative_path.replace("\\", "/")
    return [p for p in normalized.split("/") if p]


def _extract_imports(content: str):
    """Yields (module_str, level) tuples for every import statement in a Python file."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, 0, []
        elif isinstance(node, ast.ImportFrom):
            yield (node.module or ""), (node.level or 0), [alias.name for alias in node.names]


def _resolve_relative_import(current_module: str, is_package: bool, level: int, module: str) -> str:
    parts = current_module.split(".") if current_module else []
    base = parts[:] if is_package else parts[:-1]
    if level > 1:
        trim = level - 1
        base = base[: len(base) - trim] if trim <= len(base) else []
    if module:
        base = base + module.split(".")
    return ".".join(p for p in base if p)


def build_import_graph(files_data: list) -> dict:
    """
    Builds an adjacency list of internal (in-repo) imports.

    files_data: list of {"relative_path": str, "content": str} for .py files only.

    Returns a dict with:
        "graph": {relative_path: set(relative_path, ...)}  edges = "imports"
        "module_to_path": {dotted_module: relative_path}
        "path_to_module": {relative_path: dotted_module}
    """
    module_to_path = {}
    path_to_module = {}
    for f in files_data:
        rel = f["relative_path"]
        mod = _file_to_module(rel)
        module_to_path[mod] = rel
        path_to_module[rel] = mod

    graph = defaultdict(set)
    for f in files_data:
        rel = f["relative_path"]
        current_module = path_to_module[rel]
        is_package = pathlib_parts(rel)[-1] == "__init__.py"

        for module, level, imported_names in _extract_imports(f["content"]):
            if level > 0:
                resolved = _resolve_relative_import(current_module, is_package, level, module)
            else:
                resolved = module

            targets = set()

            # For "from X import name1, name2", each name may itself be a submodule
            # of X (e.g. "from pkg import b" importing pkg/b.py) rather than an
            # attribute defined in X's __init__.py — try the submodule form first.
            for name in imported_names:
                candidate_module = f"{resolved}.{name}" if resolved else name
                if candidate_module in module_to_path:
                    targets.add(module_to_path[candidate_module])

            if not targets:
                target_path = module_to_path.get(resolved)
                if target_path is None:
                    # Try matching the longest known module prefix (e.g. "devmind.memory.foo" -> "devmind.memory")
                    candidate_parts = resolved.split(".")
                    while candidate_parts:
                        candidate = ".".join(candidate_parts)
                        if candidate in module_to_path:
                            target_path = module_to_path[candidate]
                            break
                        candidate_parts.pop()
                if target_path:
                    targets.add(target_path)

            for target_path in targets:
                if target_path != rel:
                    graph[rel].add(target_path)

    # Ensure every file has an entry, even with no outgoing edges
    for f in files_data:
        graph.setdefault(f["relative_path"], set())

    return {"graph": dict(graph), "module_to_path": module_to_path, "path_to_module": path_to_module}


# ─────────────────────────────────────────────────────────────────────────
# Circular dependency detection (DFS with recursion-stack coloring)
# ─────────────────────────────────────────────────────────────────────────

def detect_circular_dependencies(graph: dict) -> list:
    """
    Detects import cycles in the internal dependency graph using DFS.
    Returns a list of cycles, each a list of relative file paths forming the loop
    (first and last entries are the same node, e.g. [a, b, a]).
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}
    stack_path = []
    cycles = []
    seen_cycle_keys = set()

    def dfs(node):
        color[node] = GRAY
        stack_path.append(node)
        for neighbor in sorted(graph.get(node, ())):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                # Found a back-edge; extract the cycle from the stack
                idx = stack_path.index(neighbor)
                cycle = stack_path[idx:] + [neighbor]
                key = tuple(sorted(set(cycle)))
                if key not in seen_cycle_keys:
                    seen_cycle_keys.add(key)
                    cycles.append(cycle)
            elif color[neighbor] == WHITE:
                dfs(neighbor)
        stack_path.pop()
        color[node] = BLACK

    for node in sorted(graph):
        if color[node] == WHITE:
            dfs(node)

    return cycles


# ─────────────────────────────────────────────────────────────────────────
# Cyclomatic complexity
# ─────────────────────────────────────────────────────────────────────────

def calculate_cyclomatic_complexity(content: str) -> int:
    """
    Computes an approximate cyclomatic complexity score for a Python file by
    counting decision points (if/for/while/except/with/assert/bool-ops/
    comprehensions) across the whole module, plus a base complexity of 1.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return 0

    score = 1
    for node in ast.walk(tree):
        if isinstance(node, _DECISION_NODE_TYPES):
            if isinstance(node, ast.BoolOp):
                # Each additional operand after the first adds a branch
                score += max(len(node.values) - 1, 1)
            else:
                score += 1
    return score


def calculate_codebase_complexity(files_data: list) -> dict:
    """Returns {relative_path: cyclomatic_complexity_score} for all python files."""
    return {f["relative_path"]: calculate_cyclomatic_complexity(f["content"]) for f in files_data}


# ─────────────────────────────────────────────────────────────────────────
# Git churn analysis
# ─────────────────────────────────────────────────────────────────────────

def calculate_file_churn(root_dir: str, days: int = 30) -> dict:
    """
    Runs `git log --since=<days> --name-only` (via GitPython) and returns
    {relative_path: commit_count} for files touched within the window.
    """
    churn = defaultdict(int)
    try:
        repo = Repo(root_dir, search_parent_directories=True)
    except InvalidGitRepositoryError:
        logger.warning(f"No git repository found at '{root_dir}'. Churn data unavailable.")
        return dict(churn)

    since_date = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        commits = list(repo.iter_commits(since=since_date.isoformat()))
    except Exception as e:
        logger.warning(f"Could not read git history for churn analysis: {e}")
        return dict(churn)

    for commit in commits:
        try:
            for file_path in commit.stats.files.keys():
                churn[file_path] += 1
        except Exception:
            continue

    return dict(churn)


# ─────────────────────────────────────────────────────────────────────────
# Hotspot matrix (churn x complexity)
# ─────────────────────────────────────────────────────────────────────────

def compute_hotspot_matrix(
    complexities: dict,
    churn_data: dict,
    cc_threshold: int = DEFAULT_CC_THRESHOLD,
    churn_threshold: int = DEFAULT_CHURN_THRESHOLD,
) -> list:
    """
    Cross-references complexity and churn. Returns a list of hotspot dicts,
    sorted by risk (churn * complexity) descending, flagging files that exceed
    BOTH thresholds as "Critical Fragility Zones".
    """
    hotspots = []
    for rel_path, cc in complexities.items():
        churn = churn_data.get(rel_path, 0)
        if churn == 0 and cc < cc_threshold:
            continue
        is_critical = cc > cc_threshold and churn > churn_threshold
        hotspots.append({
            "file": rel_path,
            "complexity": cc,
            "churn": churn,
            "critical": is_critical,
            "risk_score": cc * churn,
        })

    hotspots.sort(key=lambda h: h["risk_score"], reverse=True)
    return hotspots


# ─────────────────────────────────────────────────────────────────────────
# Coupling & fan-out metrics
# ─────────────────────────────────────────────────────────────────────────

def compute_coupling_metrics(graph: dict, fan_out_threshold: int = DEFAULT_FAN_OUT_THRESHOLD) -> list:
    """
    Computes fan-out (files this file imports) and fan-in (files that import
    this file) for every node. Returns a list of {file, fan_out, fan_in} dicts
    for files whose fan-out exceeds the threshold, sorted by fan-out descending.
    """
    fan_in = defaultdict(int)
    for node, targets in graph.items():
        for target in targets:
            fan_in[target] += 1

    results = []
    for node, targets in graph.items():
        fan_out = len(targets)
        results.append({"file": node, "fan_out": fan_out, "fan_in": fan_in.get(node, 0)})

    results.sort(key=lambda r: r["fan_out"], reverse=True)
    return [r for r in results if r["fan_out"] > fan_out_threshold]


# ─────────────────────────────────────────────────────────────────────────
# Layer boundary violations
# ─────────────────────────────────────────────────────────────────────────

def check_layer_violations(graph: dict, path_to_module: dict) -> list:
    """
    Checks every internal import edge against LAYER_RULES.
    Returns a list of {source, target, reason} violation dicts.
    """
    violations = []
    for source_path, targets in graph.items():
        source_module = path_to_module.get(source_path, "")
        for target_path in targets:
            target_module = path_to_module.get(target_path, "")
            for src_prefix, forbidden_prefixes, reason in LAYER_RULES:
                if not source_module.startswith(src_prefix):
                    continue
                for forbidden in forbidden_prefixes:
                    if target_module.startswith(forbidden):
                        violations.append({
                            "source": source_path,
                            "target": target_path,
                            "reason": reason,
                        })
    return violations


# ─────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────

def run_drift_analysis(root_dir: str, days: int = 30) -> dict:
    """
    Runs the full offline drift analysis pipeline and returns a structured report.
    """
    from devmind.ingestion.file_reader import scan_codebase_files

    all_files = scan_codebase_files(root_dir)
    py_files = [f for f in all_files if f["relative_path"].endswith(".py")]

    graph_data = build_import_graph(py_files)
    graph = graph_data["graph"]
    path_to_module = graph_data["path_to_module"]

    cycles = detect_circular_dependencies(graph)
    complexities = calculate_codebase_complexity(py_files)
    churn_data = calculate_file_churn(root_dir, days=days)
    hotspots = compute_hotspot_matrix(complexities, churn_data)
    coupling = compute_coupling_metrics(graph)
    violations = check_layer_violations(graph, path_to_module)

    return {
        "root_dir": root_dir,
        "files_analyzed": len(py_files),
        "days": days,
        "cycles": cycles,
        "hotspots": hotspots,
        "coupling": coupling,
        "layer_violations": violations,
    }


# ─────────────────────────────────────────────────────────────────────────
# Rendering: terminal (rich)
# ─────────────────────────────────────────────────────────────────────────

def render_drift_terminal(report: dict, console=None):
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    console = console or Console()
    project_name = os.path.basename(os.path.abspath(report["root_dir"]))

    header = (
        f"[bold]Project:[/bold] {project_name}  │  "
        f"[bold]Analyzed:[/bold] {report['files_analyzed']} files  │  "
        f"[bold]Git window:[/bold] Last {report['days']} days"
    )
    console.print(Panel.fit(header, title="🌪️  DevMind Architecture Drift Report", border_style="magenta"))

    # Circular imports
    cycles = report["cycles"]
    if cycles:
        body = Text()
        body.append(f"🔴 {len(cycles)} cyclic dependency detected\n", style="bold red")
        for cycle in cycles:
            body.append(" ➔ ".join(cycle) + "\n")
        console.print(Panel(body, title="🔄 Circular Import Loops", border_style="red"))
    else:
        console.print(Panel("✅ No circular import loops detected.", title="🔄 Circular Import Loops", border_style="green"))

    # Hotspots
    hotspots = report["hotspots"]
    critical = [h for h in hotspots if h["critical"]]
    if hotspots:
        body = Text()
        shown = hotspots[:10]
        for h in shown:
            icon = "🔴" if h["critical"] else "⚠️ "
            body.append(f"{icon} {h['file']}\n", style="bold red" if h["critical"] else "bold yellow")
            body.append(f"   • {h['churn']} commits in {report['days']} days"
                        f"{' (High Churn)' if h['churn'] > DEFAULT_CHURN_THRESHOLD else ''}\n")
            body.append(f"   • CC Score: {h['complexity']}"
                        f"{' (High Complexity)' if h['complexity'] > DEFAULT_CC_THRESHOLD else ''}\n")
            if h["critical"]:
                body.append("   • Risk: High likelihood of regression bugs\n", style="red")
        console.print(Panel(body, title="🔥 Churn vs. Complexity Hotspots", border_style="red" if critical else "yellow"))
    else:
        console.print(Panel("✅ No churn/complexity hotspots detected.", title="🔥 Churn vs. Complexity Hotspots", border_style="green"))

    # Coupling
    coupling = report["coupling"]
    if coupling:
        body = Text()
        for c in coupling[:10]:
            body.append(f"⚠️  {c['file']} has high afferent coupling\n", style="bold yellow")
            body.append(f"   (Imports {c['fan_out']} distinct internal modules, imported by {c['fan_in']})\n")
        console.print(Panel(body, title="📐 Coupling & Fan-Out Metrics", border_style="yellow"))
    else:
        console.print(Panel("✅ No excessive coupling detected.", title="📐 Coupling & Fan-Out Metrics", border_style="green"))

    # Layer violations
    violations = report["layer_violations"]
    if violations:
        body = Text()
        for v in violations:
            body.append(f"🔴 {v['source']} ➔ {v['target']}\n", style="bold red")
            body.append(f"   {v['reason']}\n")
        console.print(Panel(body, title="📏 Layer Boundary Violations", border_style="red"))


# ─────────────────────────────────────────────────────────────────────────
# Rendering: markdown export
# ─────────────────────────────────────────────────────────────────────────

def format_drift_markdown(report: dict) -> str:
    project_name = os.path.basename(os.path.abspath(report["root_dir"]))
    lines = [
        "# 🌪️ DevMind Architecture Drift Report",
        "",
        f"- **Project:** {project_name}",
        f"- **Files analyzed:** {report['files_analyzed']}",
        f"- **Git window:** Last {report['days']} days",
        "",
        "## 🔄 Circular Import Loops",
        "",
    ]

    cycles = report["cycles"]
    if cycles:
        lines.append(f"🔴 **{len(cycles)} cyclic dependency detected**")
        lines.append("")
        for cycle in cycles:
            lines.append(f"- `{' → '.join(cycle)}`")
    else:
        lines.append("✅ No circular import loops detected.")

    lines += ["", "## 🔥 Churn vs. Complexity Hotspots", ""]
    hotspots = report["hotspots"]
    if hotspots:
        lines.append("| File | Commits (window) | Complexity | Status |")
        lines.append("|---|---|---|---|")
        for h in hotspots:
            status = "🔴 Critical Fragility Zone" if h["critical"] else "⚠️ Watch"
            lines.append(f"| `{h['file']}` | {h['churn']} | {h['complexity']} | {status} |")
    else:
        lines.append("✅ No churn/complexity hotspots detected.")

    lines += ["", "## 📐 Coupling & Fan-Out Metrics", ""]
    coupling = report["coupling"]
    if coupling:
        lines.append("| File | Fan-Out (imports) | Fan-In (imported by) |")
        lines.append("|---|---|---|")
        for c in coupling:
            lines.append(f"| `{c['file']}` | {c['fan_out']} | {c['fan_in']} |")
    else:
        lines.append("✅ No excessive coupling detected.")

    lines += ["", "## 📏 Layer Boundary Violations", ""]
    violations = report["layer_violations"]
    if violations:
        lines.append("| Source | Target | Reason |")
        lines.append("|---|---|---|")
        for v in violations:
            lines.append(f"| `{v['source']}` | `{v['target']}` | {v['reason']} |")
    else:
        lines.append("✅ No layer boundary violations detected.")

    lines.append("")
    return "\n".join(lines)
