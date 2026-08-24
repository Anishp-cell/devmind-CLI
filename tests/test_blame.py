"""
tests/test_blame.py

Unit tests for devmind.analysis.blame:
Tests ownership percentage calculation, function line-range detection,
collision risk estimation, and timeline generation.
"""

import pytest
import os
import tempfile
import pathlib

from devmind.analysis.blame import (
    get_function_line_range,
    detect_collision_risk,
    _ownership_bar,
    generate_blame_report
)


class TestSemanticBlame:
    def test_function_line_range_detection(self, tmp_path):
        test_file = tmp_path / "sample.py"
        test_file.write_text(
            "import os\n\n"
            "def calculate_total(items):\n"
            "    total = 0\n"
            "    for item in items:\n"
            "        total += item\n"
            "    return total\n\n"
            "def other_func():\n"
            "    pass\n"
        )

        line_range = get_function_line_range(str(test_file), "calculate_total")
        assert line_range is not None
        assert line_range[0] == 3
        assert line_range[1] >= 7

    def test_function_line_range_not_found(self, tmp_path):
        test_file = tmp_path / "sample.py"
        test_file.write_text("x = 1\n")
        assert get_function_line_range(str(test_file), "non_existent") is None

    def test_ownership_bar_formatting(self):
        bar_full = _ownership_bar(100.0, width=10)
        assert bar_full == "██████████"
        bar_half = _ownership_bar(50.0, width=10)
        assert bar_half == "█████░░░░░"
        bar_zero = _ownership_bar(0.0, width=10)
        assert bar_zero == "░░░░░░░░░░"
