"""
tests/test_health.py

Unit tests for devmind.analysis.health — the zero-API codebase health engine.
Tests cover complexity computation, smell detection, debt tag scanning,
dead import detection, coverage mapping, and the scoring formula.
"""
import pytest
import os
import pathlib
import tempfile

from devmind.analysis.health import (
    analyze_complexity,
    detect_code_smells,
    detect_dead_imports,
    scan_debt_tags,
    map_test_coverage,
    compute_health_score,
    run_health_analysis,
    HealthReport,
    COMPLEXITY_HOTSPOT_THRESHOLD,
)


# ─────────────────────────────────────────────────────────────
# Complexity Analyzer Tests
# ─────────────────────────────────────────────────────────────
class TestAnalyzeComplexity:
    def test_simple_function_has_base_complexity_1(self):
        code = "def foo():\n    return 42\n"
        results = analyze_complexity(code, "foo.py")
        assert len(results) == 1
        assert results[0].name == "foo"
        assert results[0].complexity == 1

    def test_if_adds_1(self):
        code = "def foo(x):\n    if x:\n        return 1\n    return 0\n"
        results = analyze_complexity(code, "foo.py")
        assert results[0].complexity == 2

    def test_elif_adds_1_each(self):
        code = (
            "def foo(x):\n"
            "    if x == 1:\n        return 1\n"
            "    elif x == 2:\n        return 2\n"
            "    elif x == 3:\n        return 3\n"
            "    return 0\n"
        )
        results = analyze_complexity(code, "foo.py")
        # base=1 + if + elif + elif = 4
        assert results[0].complexity == 4

    def test_for_loop_adds_1(self):
        code = "def foo(items):\n    for i in items:\n        print(i)\n"
        results = analyze_complexity(code, "foo.py")
        assert results[0].complexity == 2

    def test_bool_op_adds_paths(self):
        code = "def foo(a, b, c):\n    if a and b and c:\n        return True\n"
        results = analyze_complexity(code, "foo.py")
        # base=1 + if=1 + BoolOp(2 'and' operators = +2) = 4
        assert results[0].complexity == 4

    def test_hotspot_flagged_correctly(self):
        # Build a function complex enough to hit the threshold
        branches = "\n".join(f"    if x == {i}:\n        return {i}" for i in range(COMPLEXITY_HOTSPOT_THRESHOLD))
        code = f"def complex_fn(x):\n{branches}\n    return -1\n"
        results = analyze_complexity(code, "foo.py")
        assert results[0].is_hotspot is True

    def test_multiple_functions_sorted_by_complexity_desc(self):
        code = (
            "def simple():\n    return 1\n\n"
            "def branchy(x):\n    if x:\n        return 1\n    return 0\n"
        )
        results = analyze_complexity(code, "foo.py")
        assert results[0].complexity >= results[1].complexity

    def test_syntax_error_returns_empty(self):
        results = analyze_complexity("def broken(:", "broken.py")
        assert results == []

    def test_async_function_detected(self):
        code = "async def bar():\n    return await something()\n"
        results = analyze_complexity(code, "foo.py")
        assert len(results) == 1
        assert results[0].name == "bar"


# ─────────────────────────────────────────────────────────────
# Code Smell Detector Tests
# ─────────────────────────────────────────────────────────────
class TestDetectCodeSmells:
    def test_no_smells_clean_code(self):
        code = "def foo():\n    return 1\n"
        smells = detect_code_smells(code, "foo.py")
        assert smells == []

    def test_god_class_detected(self):
        # Build a class with 310 lines
        body = "\n".join(f"    x_{i} = {i}" for i in range(310))
        code = f"class Huge:\n{body}\n"
        smells = detect_code_smells(code, "big.py")
        god = [s for s in smells if s.kind == "god_class"]
        assert len(god) >= 1
        assert god[0].name == "Huge"

    def test_long_function_detected(self):
        # Build a function with 60 lines
        body = "\n".join(f"    x_{i} = {i}" for i in range(60))
        code = f"def long_fn():\n{body}\n    return 0\n"
        smells = detect_code_smells(code, "long.py")
        long_fns = [s for s in smells if s.kind == "long_function"]
        assert len(long_fns) >= 1
        assert long_fns[0].name == "long_fn"

    def test_clean_short_class_not_flagged(self):
        code = "class Small:\n    def __init__(self):\n        pass\n"
        smells = detect_code_smells(code, "small.py")
        god = [s for s in smells if s.kind == "god_class"]
        assert god == []

    def test_syntax_error_returns_empty(self):
        smells = detect_code_smells("class Broken(:", "bad.py")
        assert smells == []


# ─────────────────────────────────────────────────────────────
# Debt Tag Scanner Tests
# ─────────────────────────────────────────────────────────────
class TestScanDebtTags:
    def test_todo_detected(self):
        code = "x = 1  # TODO: fix this later\n"
        tags = scan_debt_tags(code, "foo.py")
        assert any(t.tag == "TODO" for t in tags)

    def test_fixme_detected(self):
        code = "# FIXME: broken auth flow\ndef auth(): pass\n"
        tags = scan_debt_tags(code, "foo.py")
        assert any(t.tag == "FIXME" for t in tags)

    def test_bug_detected(self):
        code = "# BUG: off-by-one in loop\nfor i in range(10): pass\n"
        tags = scan_debt_tags(code, "foo.py")
        assert any(t.tag == "BUG" for t in tags)

    def test_hack_detected(self):
        code = "# HACK: temporary workaround\nx = 42\n"
        tags = scan_debt_tags(code, "foo.py")
        assert any(t.tag == "HACK" for t in tags)

    def test_line_number_correct(self):
        code = "x = 1\n# TODO: fix line 2\ny = 2\n"
        tags = scan_debt_tags(code, "foo.py")
        todo = [t for t in tags if t.tag == "TODO"]
        assert todo[0].line == 2

    def test_no_false_positives_in_clean_code(self):
        code = "def add(a, b):\n    return a + b\n"
        tags = scan_debt_tags(code, "foo.py")
        assert tags == []

    def test_js_style_comment(self):
        code = "// TODO: refactor this module\nfunction foo() {}\n"
        tags = scan_debt_tags(code, "foo.js")
        assert any(t.tag == "TODO" for t in tags)

    def test_deduplication(self):
        # Same tag on same line should appear only once
        code = "# TODO: do something\n"
        tags = scan_debt_tags(code, "foo.py")
        assert len([t for t in tags if t.line == 1]) == 1


# ─────────────────────────────────────────────────────────────
# Dead Import Detector Tests
# ─────────────────────────────────────────────────────────────
class TestDetectDeadImports:
    def test_used_import_not_flagged(self):
        code = "import os\npath = os.path.join('a', 'b')\n"
        dead = detect_dead_imports(code, "foo.py")
        names = [d.import_name for d in dead]
        assert "os" not in names

    def test_unused_import_flagged(self):
        code = "import sys\nimport os\npath = os.getcwd()\n"
        dead = detect_dead_imports(code, "foo.py")
        names = [d.import_name for d in dead]
        assert "sys" in names

    def test_from_import_used(self):
        code = "from pathlib import Path\np = Path('.')\n"
        dead = detect_dead_imports(code, "foo.py")
        names = [d.import_name for d in dead]
        assert "Path" not in names

    def test_from_import_unused(self):
        code = "from pathlib import Path\nx = 1\n"
        dead = detect_dead_imports(code, "foo.py")
        names = [d.import_name for d in dead]
        assert "Path" in names

    def test_star_import_ignored(self):
        # star imports can't be tracked — should not crash
        code = "from os.path import *\nx = join('a', 'b')\n"
        dead = detect_dead_imports(code, "foo.py")
        # No crash; star import is skipped
        assert isinstance(dead, list)

    def test_dunder_all_reexport_not_flagged(self):
        code = (
            "from mymodule import MyClass\n"
            "__all__ = ['MyClass']\n"
        )
        dead = detect_dead_imports(code, "foo.py")
        names = [d.import_name for d in dead]
        assert "MyClass" not in names

    def test_syntax_error_returns_empty(self):
        dead = detect_dead_imports("import (", "bad.py")
        assert dead == []


# ─────────────────────────────────────────────────────────────
# Test Coverage Mapper Tests
# ─────────────────────────────────────────────────────────────
class TestMapTestCoverage:
    def test_covered_file_detected(self, tmp_path):
        # Create source + test file
        src = tmp_path / "mymodule.py"
        src.write_text("def foo(): pass")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_f = tests_dir / "test_mymodule.py"
        test_f.write_text("def test_foo(): pass")

        covered, uncovered = map_test_coverage(["mymodule.py"], str(tmp_path))
        assert "mymodule.py" in covered
        assert "mymodule.py" not in uncovered

    def test_uncovered_file_detected(self, tmp_path):
        src = tmp_path / "lonely.py"
        src.write_text("def bar(): pass")
        covered, uncovered = map_test_coverage(["lonely.py"], str(tmp_path))
        assert "lonely.py" in uncovered

    def test_non_source_files_excluded(self, tmp_path):
        # .md and .json files should not appear in uncovered
        covered, uncovered = map_test_coverage(["README.md", "config.json"], str(tmp_path))
        assert "README.md" not in uncovered
        assert "config.json" not in uncovered


# ─────────────────────────────────────────────────────────────
# Health Score Tests
# ─────────────────────────────────────────────────────────────
class TestComputeHealthScore:
    def _clean_report(self) -> HealthReport:
        return HealthReport(
            project_name="test",
            directory="/tmp",
            total_files=10,
            total_py_files=10,
            total_functions=20,
            total_classes=3,
            total_lines=500,
            source_files=["a.py", "b.py"],
        )

    def test_perfect_score_is_100(self):
        report = self._clean_report()
        score, grade = compute_health_score(report)
        assert score == 100
        assert grade == "A"

    def test_grade_a_for_85_plus(self):
        report = self._clean_report()
        score, grade = compute_health_score(report)
        if score >= 85:
            assert grade == "A"

    def test_grade_f_for_low_score(self):
        from devmind.analysis.health import (
            FunctionComplexity, CodeSmell, DebtTag, DeadImport
        )
        report = self._clean_report()
        # Simulate terrible codebase
        report.function_complexities = [
            FunctionComplexity("f", "a.py", 1, 20, True) for _ in range(20)
        ]
        report.code_smells = [
            CodeSmell("god_class", "G", "a.py", 1, "500 lines") for _ in range(10)
        ]
        report.debt_tags = [
            DebtTag("BUG", "a.py", i, "broken") for i in range(50)
        ]
        report.dead_imports = [
            DeadImport("unused", "a.py", i) for i in range(30)
        ]
        report.uncovered_files = ["a.py", "b.py"]
        score, grade = compute_health_score(report)
        assert score < 55
        assert grade in {"C", "D", "F"}

    def test_score_bounded_0_to_100(self):
        from devmind.analysis.health import (
            FunctionComplexity, CodeSmell, DebtTag, DeadImport
        )
        report = self._clean_report()
        report.function_complexities = [FunctionComplexity("f", "a.py", 1, 30, True) for _ in range(100)]
        report.code_smells = [CodeSmell("god_class", "G", "a.py", 1, "1000 lines") for _ in range(100)]
        report.debt_tags = [DebtTag("BUG", "a.py", i, "x") for i in range(200)]
        score, _ = compute_health_score(report)
        assert 0 <= score <= 100


# ─────────────────────────────────────────────────────────────
# Integration Test: run_health_analysis on DevMind itself
# ─────────────────────────────────────────────────────────────
class TestRunHealthAnalysis:
    def test_runs_on_real_project(self, tmp_path):
        """Smoke test: health analysis runs without crashing on a minimal project."""
        src = tmp_path / "myapp.py"
        src.write_text(
            "import os\nimport sys\n\n"
            "def hello(name):\n"
            "    # TODO: add greeting logic\n"
            "    if name:\n        return f'Hello {name}'\n"
            "    return 'Hello'\n"
        )
        report = run_health_analysis(str(tmp_path))
        assert report.total_files >= 1
        assert report.total_functions >= 1
        assert 0 <= report.health_score <= 100
        assert report.grade in {"A", "B", "C", "D", "F"}
        # The TODO should be captured
        assert any(t.tag == "TODO" for t in report.debt_tags)

    def test_empty_directory_returns_zero_file_report(self, tmp_path):
        report = run_health_analysis(str(tmp_path))
        assert report.total_files == 0
