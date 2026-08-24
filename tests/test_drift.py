"""
tests/test_drift.py

Unit tests for devmind.analysis.drift:
Tests circular dependency detection, churn/complexity hotspot matrix,
layer boundary violations, and coupling metrics.
"""

import pytest
import os

from devmind.analysis.drift import (
    detect_circular_dependencies,
    compute_hotspot_matrix,
    check_layer_violations,
    compute_coupling_metrics,
    format_drift_markdown,
    run_drift_analysis
)


class TestDriftAnalysis:
    def test_detects_circular_dependencies(self):
        # A -> B -> C -> A
        graph = {
            "module_a": {"module_b"},
            "module_b": {"module_c"},
            "module_c": {"module_a"},
            "module_d": set(),
        }

        cycles = detect_circular_dependencies(graph)
        assert len(cycles) >= 1
        assert any("module_a" in c and "module_b" in c for c in cycles)

    def test_no_cycle_in_acyclic_graph(self):
        graph = {
            "module_a": {"module_b", "module_c"},
            "module_b": {"module_c"},
            "module_c": set(),
        }
        cycles = detect_circular_dependencies(graph)
        assert len(cycles) == 0

    def test_compute_hotspot_matrix(self):
        complexities = {
            "core/engine.py": 25,   # High CC
            "utils/helpers.py": 4,  # Low CC
        }
        churn_data = {
            "core/engine.py": 18,   # High Churn
            "utils/helpers.py": 2,  # Low Churn
        }

        hotspots = compute_hotspot_matrix(complexities, churn_data, cc_threshold=15, churn_threshold=10)
        assert len(hotspots) == 2
        # First hotspot should be the critical one
        assert hotspots[0]["file"] == "core/engine.py"
        assert hotspots[0]["critical"] is True
        assert hotspots[1]["critical"] is False

    def test_check_layer_violations(self):
        graph = {
            "devmind/memory.py": {"devmind/cli.py", "devmind/web/app.py"},
            "devmind/cli.py": {"devmind/memory.py"},
        }
        path_to_mod = {
            "devmind/memory.py": "devmind.memory",
            "devmind/cli.py": "devmind.cli",
            "devmind/web/app.py": "devmind.web.app",
        }

        violations = check_layer_violations(graph, path_to_mod)
        assert len(violations) >= 1
        assert any("memory.py" in v["source"] for v in violations)

    def test_compute_coupling_metrics(self):
        graph = {
            "a": {"b", "c", "d"},
            "b": {"c"},
            "c": set(),
            "d": set(),
        }
        coupling = compute_coupling_metrics(graph, fan_out_threshold=2)
        assert len(coupling) >= 1
        assert coupling[0]["file"] == "a"
        assert coupling[0]["fan_out"] == 3


class TestDriftMarkdownExport:
    def test_generates_markdown(self):
        report = {
            "root_dir": "/mock/project",
            "files_analyzed": 10,
            "days": 30,
            "cycles": [["mod_a", "mod_b", "mod_a"]],
            "hotspots": [{"file": "app.py", "churn": 12, "complexity": 20, "critical": True}],
            "coupling": [{"file": "main.py", "fan_out": 5, "fan_in": 1}],
            "layer_violations": [{"source": "core.py", "target": "cli.py", "reason": "Layer violation"}],
        }

        md = format_drift_markdown(report)
        assert "# 🌪️ DevMind Architecture Drift Report" in md
        assert "mod_a → mod_b → mod_a" in md
        assert "Critical Fragility Zone" in md
        assert "main.py" in md
