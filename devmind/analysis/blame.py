"""
Semantic & Architectural Git Blame.

Goes beyond `git blame`'s line-level authorship to compute code ownership
percentages, a filtered "meaningful commits" timeline, merge-collision risk,
and cross-references to Architecture Decision Records (ADRs) logged via
`devmind log`.
"""
import ast
import logging
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from git import Repo, InvalidGitRepositoryError

logger = logging.getLogger("devmind.analysis.blame")

DEFAULT_ACTIVE_WINDOW_DAYS = 90
DEFAULT_COLLISION_WINDOW_DAYS = 30
DEFAULT_COLLISION_AUTHOR_THRESHOLD = 5
DEFAULT_TIMELINE_LIMIT = 5

_TRIVIAL_MESSAGE_PATTERNS = [
    re.compile(r"^merge\b", re.IGNORECASE),
    re.compile(r"\btypo\b", re.IGNORECASE),
    re.compile(r"\bformatting\b", re.IGNORECASE),
    re.compile(r"\bwhitespace\b", re.IGNORECASE),
    re.compile(r"^style:", re.IGNORECASE),
    re.compile(r"^chore:\s*bump version", re.IGNORECASE),
    re.compile(r"^wip\b", re.IGNORECASE),
]


def _is_trivial_message(message: str) -> bool:
    first_line = message.strip().splitlines()[0] if message.strip() else ""
    return any(p.search(first_line) for p in _TRIVIAL_MESSAGE_PATTERNS)


def _open_repo(root_dir: str) -> Repo:
    return Repo(root_dir, search_parent_directories=True)


# ─────────────────────────────────────────────────────────────────────────
# Ownership
# ─────────────────────────────────────────────────────────────────────────

def _get_blame_hunks(repo: Repo, relative_path: str):
    """Returns a list of {"commit", "start", "end", "count"} 1-indexed line hunks."""
    hunks = repo.blame("HEAD", relative_path)
    results = []
    line_no = 1
    for commit, lines in hunks:
        count = len(lines)
        results.append({"commit": commit, "start": line_no, "end": line_no + count - 1, "count": count})
        line_no += count
    return results


def calculate_file_ownership(
    file_path: str,
    root_dir: str,
    line_range: tuple = None,
    active_window_days: int = DEFAULT_ACTIVE_WINDOW_DAYS,
) -> dict:
    """
    Computes per-author code ownership percentages for a file (or a specific
    line range within it) using `git blame` on the current HEAD.

    Returns:
        {
            "total_lines": int,
            "authors": [{"name", "email", "lines", "percent", "active", "last_commit"}, ...],
            "primary_expert": str | None,
        }
    """
    repo = _open_repo(root_dir)
    hunks = _get_blame_hunks(repo, file_path)

    now = datetime.now(timezone.utc)
    active_cutoff = now - timedelta(days=active_window_days)

    stats = defaultdict(lambda: {"lines": 0, "email": None, "last_commit": None})
    total_lines = 0

    for hunk in hunks:
        count = hunk["count"]
        if line_range:
            overlap_start = max(hunk["start"], line_range[0])
            overlap_end = min(hunk["end"], line_range[1])
            if overlap_start > overlap_end:
                continue
            count = overlap_end - overlap_start + 1

        commit = hunk["commit"]
        name = commit.author.name or "Unknown"
        entry = stats[name]
        entry["lines"] += count
        entry["email"] = commit.author.email
        commit_dt = commit.authored_datetime
        if entry["last_commit"] is None or commit_dt > entry["last_commit"]:
            entry["last_commit"] = commit_dt
        total_lines += count

    authors = []
    for name, entry in stats.items():
        percent = (entry["lines"] / total_lines * 100) if total_lines else 0
        authors.append({
            "name": name,
            "email": entry["email"],
            "lines": entry["lines"],
            "percent": round(percent, 1),
            "active": entry["last_commit"] is not None and entry["last_commit"] >= active_cutoff,
            "last_commit": entry["last_commit"].isoformat() if entry["last_commit"] else None,
        })

    authors.sort(key=lambda a: a["lines"], reverse=True)
    primary_expert = authors[0]["name"] if authors else None

    return {"total_lines": total_lines, "authors": authors, "primary_expert": primary_expert}


# ─────────────────────────────────────────────────────────────────────────
# Evolution timeline
# ─────────────────────────────────────────────────────────────────────────

def get_file_evolution_timeline(file_path: str, root_dir: str, limit: int = DEFAULT_TIMELINE_LIMIT) -> list:
    """
    Returns the most recent `limit` non-trivial commits that touched this file,
    filtering out merges, typo/formatting/whitespace-only, and version bumps.
    """
    repo = _open_repo(root_dir)
    timeline = []
    try:
        for commit in repo.iter_commits(paths=file_path):
            if _is_trivial_message(commit.message):
                continue
            timeline.append({
                "hash": commit.hexsha[:7],
                "message": commit.message.strip().splitlines()[0],
                "author": commit.author.name,
                "date": commit.authored_datetime.date().isoformat(),
            })
            if len(timeline) >= limit:
                break
    except Exception as e:
        logger.warning(f"Could not read commit history for '{file_path}': {e}")

    return timeline


def get_total_commit_count(file_path: str, root_dir: str) -> int:
    repo = _open_repo(root_dir)
    try:
        return sum(1 for _ in repo.iter_commits(paths=file_path))
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────
# Collision risk
# ─────────────────────────────────────────────────────────────────────────

def detect_collision_risk(
    file_path: str,
    root_dir: str,
    days: int = DEFAULT_COLLISION_WINDOW_DAYS,
    author_threshold: int = DEFAULT_COLLISION_AUTHOR_THRESHOLD,
) -> dict:
    """
    Flags a file as high merge-conflict/collision risk if it has been touched
    by `author_threshold`+ distinct authors within the last `days` days.
    """
    repo = _open_repo(root_dir)
    since_date = datetime.now(timezone.utc) - timedelta(days=days)
    authors = set()
    try:
        for commit in repo.iter_commits(paths=file_path, since=since_date.isoformat()):
            authors.add(commit.author.name)
    except Exception as e:
        logger.warning(f"Could not compute collision risk for '{file_path}': {e}")

    return {
        "distinct_authors": len(authors),
        "authors": sorted(authors),
        "days": days,
        "high_risk": len(authors) >= author_threshold,
    }


# ─────────────────────────────────────────────────────────────────────────
# Function-level blame (--func)
# ─────────────────────────────────────────────────────────────────────────

def get_function_line_range(file_path_abs: str, func_name: str):
    """Locates a top-level or nested function/method by name via AST and returns (start, end) lines."""
    try:
        with open(file_path_abs, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        tree = ast.parse(content)
    except (OSError, SyntaxError):
        return None

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            end_line = getattr(node, "end_lineno", node.lineno)
            return (node.lineno, end_line)
    return None


def get_function_history(file_path: str, func_name: str, root_dir: str, limit: int = 10) -> list:
    """
    Uses `git log -L :func_name:file_path` to retrieve the commit history
    of a specific function's body.
    """
    try:
        result = subprocess.run(
            ["git", "-C", root_dir, "log", f"-L:{func_name}:{file_path}", "--oneline", "-n", str(limit)],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning(f"Could not run function-level git log for '{func_name}' in '{file_path}': {e}")
        return []

    if result.returncode != 0:
        logger.warning(f"git log -L failed for function '{func_name}': {result.stderr.strip()}")
        return []

    commits = []
    for line in result.stdout.splitlines():
        if re.match(r"^[0-9a-f]{7,40}\s", line):
            parts = line.split(" ", 1)
            commits.append({"hash": parts[0], "message": parts[1] if len(parts) > 1 else ""})
    return commits


# ─────────────────────────────────────────────────────────────────────────
# ADR cross-referencing (offline text match against local Cognee memory)
# ─────────────────────────────────────────────────────────────────────────

async def link_related_adrs(file_path: str) -> list:
    """
    Searches locally ingested Architecture Decision Records (logged via
    `devmind log`) for mentions of this file's path or basename.
    Performs a plain text match against Cognee's relational store — no LLM calls.
    """
    import os
    import importlib

    matches = []
    try:
        from cognee.infrastructure.databases.relational import get_relational_engine
        from sqlalchemy import select

        data_model = None
        for model_path in (
            "cognee.modules.data.models.Data",
            "cognee.modules.data.models.DataPoint",
            "cognee.modules.data.models.Document",
        ):
            try:
                module_path, cls_name = model_path.rsplit(".", 1)
                mod = importlib.import_module(module_path)
                data_model = getattr(mod, cls_name, None)
                if data_model is not None:
                    break
            except Exception:
                continue

        if data_model is None:
            return matches

        basename = os.path.basename(file_path)
        engine = get_relational_engine()
        async with engine.get_async_session() as session:
            stmt = select(data_model)
            results = (await session.execute(stmt)).scalars().all()
            for r in results:
                content = getattr(r, "content", None)
                if not content or "Architectural Decision Record:" not in content:
                    continue
                if file_path in content or basename in content:
                    created = getattr(r, "created_at", None)
                    matches.append({
                        "date": created.date().isoformat() if created else "unknown",
                        "content": content.replace("Architectural Decision Record:\n", "").strip(),
                    })
    except Exception as e:
        logger.warning(f"Could not search ADR memory for '{file_path}': {e}")

    return matches


# ─────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────

async def generate_blame_report(file_path: str, root_dir: str, func_name: str = None) -> dict:
    """
    Assembles the full semantic blame report: ownership, evolution timeline,
    collision risk, and related ADRs. If func_name is given, ownership is
    scoped to that function's line range and function-level history is added.
    """
    import os

    line_range = None
    func_history = []
    if func_name:
        abs_path = os.path.join(root_dir, file_path)
        line_range = get_function_line_range(abs_path, func_name)
        func_history = get_function_history(file_path, func_name, root_dir)

    ownership = calculate_file_ownership(file_path, root_dir, line_range=line_range)
    timeline = get_file_evolution_timeline(file_path, root_dir)
    total_commits = get_total_commit_count(file_path, root_dir)
    collision = detect_collision_risk(file_path, root_dir)
    adrs = await link_related_adrs(file_path)

    return {
        "file_path": file_path,
        "func_name": func_name,
        "line_range": line_range,
        "func_history": func_history,
        "ownership": ownership,
        "timeline": timeline,
        "total_commits": total_commits,
        "collision": collision,
        "adrs": adrs,
    }


# ─────────────────────────────────────────────────────────────────────────
# Rendering: terminal (rich)
# ─────────────────────────────────────────────────────────────────────────

def _ownership_bar(percent: float, width: int = 20) -> str:
    filled = round(percent / 100 * width)
    return "█" * filled + "░" * (width - filled)


def render_blame_terminal(report: dict, console=None, expert_only: bool = False):
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    console = console or Console()
    ownership = report["ownership"]
    file_label = report["file_path"] + (f" (function: {report['func_name']})" if report["func_name"] else "")

    header = (
        f"[bold]{ownership['total_lines']} lines[/bold]  │  "
        f"[bold]{report['total_commits']} commits[/bold]  │  "
        f"[bold]{len(ownership['authors'])} contributor(s)[/bold]"
    )
    console.print(Panel.fit(header, title=f"👤 DevMind Semantic Blame: {file_label}", border_style="blue"))

    if expert_only:
        expert = ownership["primary_expert"] or "Unknown"
        pct = ownership["authors"][0]["percent"] if ownership["authors"] else 0
        console.print(Panel(f"💡 Primary Domain Expert: [bold]{expert}[/bold] ({pct}% ownership)",
                             title="👥 Expert Lookup", border_style="green"))
        return

    # Ownership distribution
    body = Text()
    for a in ownership["authors"]:
        status = "Active" if a["active"] else "Inactive"
        body.append(f"{a['name']:<18} {_ownership_bar(a['percent'])}  {a['percent']}% ({status})\n")
    if ownership["primary_expert"]:
        body.append(f"\n💡 Primary Domain Expert: {ownership['primary_expert']}", style="bold green")
    console.print(Panel(body, title="👥 Knowledge & Ownership Distribution", border_style="cyan"))

    # Function-level history
    if report["func_name"]:
        body = Text()
        if report["line_range"]:
            body.append(f"Lines {report['line_range'][0]}-{report['line_range'][1]}\n\n")
        else:
            body.append(f"⚠️  Function '{report['func_name']}' not found via AST; showing whole-file ownership.\n\n")
        for c in report["func_history"]:
            body.append(f"• {c['hash']} - {c['message']}\n")
        if not report["func_history"]:
            body.append("No function-level history found.\n")
        console.print(Panel(body, title=f"🔎 Function History: {report['func_name']}", border_style="magenta"))

    # Evolution timeline
    body = Text()
    for c in report["timeline"]:
        body.append(f"• {c['hash']} - {c['message']}\n")
    if not report["timeline"]:
        body.append("No significant commits found.\n")
    console.print(Panel(body, title="📜 Architectural Evolution & Key Commits", border_style="blue"))

    # Collision risk
    collision = report["collision"]
    if collision["high_risk"]:
        body = Text()
        body.append(
            f"⚠️  {collision['distinct_authors']} different authors touched this file "
            f"in the last {collision['days']} days.\n", style="bold yellow"
        )
        body.append("High collision/merge-conflict risk when editing.\n")
        console.print(Panel(body, title="⚡ Risk-on-Edit Warning", border_style="yellow"))

    # ADRs
    adrs = report["adrs"]
    if adrs:
        body = Text()
        for adr in adrs:
            body.append(f"• [{adr['date']}] \"{adr['content'][:120]}\"\n")
        console.print(Panel(body, title="📝 Related Architectural Decisions (ADRs)", border_style="green"))
