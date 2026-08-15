"""
tests/test_impact.py

Unit tests for devmind.analysis.impact:
Tests direct call detection, transitive ripple traversal, test regression mapping,
severity scoring, and blast radius reporting.
"""

import pytest
import os
import pathlib

from devmind.analysis.impact import (
    ImpactAnalyzer,
    ImpactedNode,
    ImpactReport,
    format_impact_markdown,
    run_impact_analysis
)


class TestImpactAnalyzer:
    def test_direct_caller_detected(self):
        sample_files = [
            {
                "relative_path": "core/auth.py",
                "content": "def verify_token(token):\n    return True\n",
                "ast_symbols": {"functions": [{"name": "verify_token", "line": 1}], "classes": []}
            },
            {
                "relative_path": "api/routes.py",
                "content": "from core.auth import verify_token\n\ndef login_endpoint(tok):\n    return verify_token(tok)\n",
                "ast_symbols": {"functions": [{"name": "login_endpoint", "line": 3}], "classes": []}
            }
        ]

        analyzer = ImpactAnalyzer(sample_files)
        report = analyzer.analyze_impact("verify_token", max_depth=2)

        assert report.target_symbol == "verify_token"
        assert len(report.direct_callers) >= 1
        assert any(c.file_path == "api/routes.py" for c in report.direct_callers)
        assert "api/routes.py" in report.impacted_files

    def test_transitive_ripple_detected(self):
        # A defines -> B calls A -> C calls B
        sample_files = [
            {
                "relative_path": "db/repo.py",
                "content": "def save_record(data):\n    pass\n",
                "ast_symbols": {"functions": [{"name": "save_record", "line": 1}], "classes": []}
            },
            {
                "relative_path": "services/user.py",
                "content": "from db.repo import save_record\n\ndef create_user(u):\n    save_record(u)\n",
                "ast_symbols": {"functions": [{"name": "create_user", "line": 3}], "classes": []}
            },
            {
                "relative_path": "api/controllers.py",
                "content": "from services.user import create_user\n\ndef register():\n    create_user('alex')\n",
                "ast_symbols": {"functions": [{"name": "register", "line": 3}], "classes": []}
            }
        ]

        analyzer = ImpactAnalyzer(sample_files)
        report = analyzer.analyze_impact("save_record", max_depth=3)

        assert len(report.direct_callers) >= 1
        assert len(report.transitive_callers) >= 1
        assert any(tc.enclosing_symbol == "register" for tc in report.transitive_callers)
        assert "api/controllers.py" in report.impacted_files

    def test_impacted_tests_mapping(self):
        sample_files = [
            {
                "relative_path": "utils/crypto.py",
                "content": "def hash_password(pwd):\n    return pwd\n",
                "ast_symbols": {"functions": [{"name": "hash_password", "line": 1}], "classes": []}
            },
            {
                "relative_path": "tests/test_crypto.py",
                "content": "from utils.crypto import hash_password\n\ndef test_hash():\n    assert hash_password('123') == '123'\n",
                "ast_symbols": {"functions": [{"name": "test_hash", "line": 3}], "classes": []}
            }
        ]

        analyzer = ImpactAnalyzer(sample_files)
        report = analyzer.analyze_impact("hash_password", max_depth=2)

        assert len(report.impacted_tests) >= 1
        assert "tests/test_crypto.py" in report.impacted_tests

    def test_file_target_impact(self):
        sample_files = [
            {
                "relative_path": "core/config.py",
                "content": "def load_config(): pass\nclass AppConfig: pass\n",
                "ast_symbols": {"functions": [{"name": "load_config"}], "classes": [{"name": "AppConfig"}]}
            },
            {
                "relative_path": "main.py",
                "content": "from core.config import load_config, AppConfig\n\ndef start():\n    load_config()\n",
                "ast_symbols": {"functions": [{"name": "start"}], "classes": []}
            }
        ]

        analyzer = ImpactAnalyzer(sample_files)
        report = analyzer.analyze_impact("core/config.py", max_depth=2)

        assert report.target_type == "file"
        assert "main.py" in report.impacted_files

    def test_severity_scoring(self):
        sample_files = [
            {
                "relative_path": "isolated.py",
                "content": "def standalone_func():\n    return 42\n",
                "ast_symbols": {"functions": [{"name": "standalone_func"}], "classes": []}
            }
        ]

        analyzer = ImpactAnalyzer(sample_files)
        report = analyzer.analyze_impact("standalone_func")

        assert report.severity == "LOW"
        assert report.risk_score == 0


class TestFormatImpactMarkdown:
    def test_generates_markdown_output(self):
        report = ImpactReport(
            target_symbol="calc_fee",
            target_file="services/billing.py",
            target_type="function",
            target_line=45,
            direct_callers=[
                ImpactedNode(
                    symbol_name="calc_fee",
                    file_path="api/checkout.py",
                    line_number=12,
                    depth=1,
                    call_type="call",
                    enclosing_symbol="process_order",
                    snippet="fee = calc_fee(item)"
                )
            ],
            transitive_callers=[],
            impacted_files=["api/checkout.py"],
            impacted_tests=["tests/test_billing.py"],
            severity="MODERATE",
            risk_score=35,
            recommended_actions=["Run test suite `tests/test_billing.py`"]
        )

        md = format_impact_markdown(report)
        assert "# 💥 DevMind Blast Radius Report: calc_fee" in md
        assert "services/billing.py:L45" in md
        assert "MODERATE" in md
        assert "api/checkout.py" in md
        assert "pytest tests/test_billing.py" in md


class TestRunImpactAnalysisIntegration:
    def test_runs_on_real_repo_symbol(self, tmp_path):
        f1 = tmp_path / "helper.py"
        f1.write_text("def ping():\n    return 'pong'\n")
        f2 = tmp_path / "app.py"
        f2.write_text("from helper import ping\ndef main():\n    return ping()\n")

        report = run_impact_analysis(str(tmp_path), "ping")
        assert report.target_symbol == "ping"
        assert len(report.direct_callers) >= 1
