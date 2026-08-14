"""
tests/test_onboarding.py

Unit tests for devmind.analysis.onboarding:
Tests stack detection, setup command extraction, architectural file ranking,
and ONBOARDING.md markdown formatting.
"""

import os
import json
import pytest
import pathlib
import tempfile

from devmind.analysis.onboarding import (
    detect_project_stack,
    extract_setup_commands,
    rank_architectural_files,
    format_onboarding_markdown,
    generate_onboarding_report,
    ProjectStack,
    SetupCommands,
    KeyFileRole,
    OnboardingReport
)


class TestOnboardingStackDetection:
    def test_detects_python_and_fastapi(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test-api"\ndependencies = ["fastapi", "uvicorn"]')
        
        sample_files = [
            {"relative_path": "app/main.py", "content": "from fastapi import FastAPI\napp = FastAPI()", "ast_symbols": {"imports": ["fastapi.FastAPI"]}},
            {"relative_path": "app/routes.py", "content": "import sqlite3", "ast_symbols": {"imports": ["sqlite3"]}}
        ]
        
        stack = detect_project_stack(str(tmp_path), sample_files)
        assert "Python" in stack.languages
        assert "FastAPI" in stack.frameworks
        assert "SQLite" in stack.databases
        assert "pyproject.toml (pip/poetry/setuptools)" in stack.package_managers

    def test_detects_node_and_react(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "web-app", "dependencies": {"react": "^18.0.0", "next": "^14.0.0"}}))
        
        sample_files = [
            {"relative_path": "src/index.tsx", "content": "import React from 'react';", "ast_symbols": {"imports": ["react"]}},
            {"relative_path": "src/App.tsx", "content": "", "ast_symbols": {"imports": []}}
        ]
        
        stack = detect_project_stack(str(tmp_path), sample_files)
        assert "TypeScript (React)" in stack.languages or "TypeScript" in stack.languages
        assert "React" in stack.frameworks or "Next.js" in stack.frameworks


class TestSetupCommandExtraction:
    def test_extracts_package_json_scripts(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({
            "name": "app",
            "scripts": {
                "dev": "next dev",
                "test": "jest",
                "lint": "eslint ."
            }
        }))
        
        cmds = extract_setup_commands(str(tmp_path))
        assert "npm install" in cmds.install
        assert "npm run dev" in cmds.run
        assert "npm run test" in cmds.test
        assert "npm run lint" in cmds.lint

    def test_extracts_makefile_targets(self, tmp_path):
        makefile = tmp_path / "Makefile"
        makefile.write_text("build:\n\tgo build .\ntest:\n\tgo test ./...\n")
        
        cmds = extract_setup_commands(str(tmp_path))
        assert "make test" in cmds.test


class TestRankArchitecturalFiles:
    def test_ranks_by_fan_in(self):
        sample_files = [
            {
                "relative_path": "core/auth.py",
                "content": "class AuthManager: pass",
                "ast_symbols": {
                    "classes": [{"name": "AuthManager"}],
                    "functions": [],
                    "imports": [],
                    "module_docstring": "Authentication engine"
                }
            },
            {
                "relative_path": "api/login.py",
                "content": "from core.auth import AuthManager",
                "ast_symbols": {
                    "classes": [],
                    "functions": [{"name": "login"}],
                    "imports": ["core.auth.AuthManager"]
                }
            },
            {
                "relative_path": "api/profile.py",
                "content": "from core.auth import AuthManager",
                "ast_symbols": {
                    "classes": [],
                    "functions": [{"name": "get_profile"}],
                    "imports": ["core.auth.AuthManager"]
                }
            }
        ]
        
        ranked = rank_architectural_files(sample_files, top_n=2)
        assert len(ranked) >= 1
        assert ranked[0].path == "core/auth.py"
        assert ranked[0].fan_in == 2


class TestFormatOnboardingMarkdown:
    def test_generates_markdown_sections(self):
        report = OnboardingReport(
            project_name="DemoApp",
            directory="/tmp/demo",
            total_files=5,
            total_lines=500,
            stack=ProjectStack(
                languages=["Python"],
                frameworks=["FastAPI"],
                package_managers=["pip"],
                entry_points=["main.py"]
            ),
            commands=SetupCommands(
                install=["pip install -r requirements.txt"],
                run=["uvicorn main:app --reload"],
                test=["pytest"]
            ),
            key_files=[
                KeyFileRole(
                    path="main.py",
                    fan_in=3,
                    role_summary="Application entry point",
                    classes=["Server"],
                    functions=["run"]
                )
            ],
            git_activity=None,
            debt_highlights=[{"tag": "TODO", "file": "main.py", "line": 10, "text": "Add rate limiter"}]
        )
        
        md = format_onboarding_markdown(report)
        assert "# 🚀 Onboarding Guide: DemoApp" in md
        assert "FastAPI" in md
        assert "pip install -r requirements.txt" in md
        assert "uvicorn main:app --reload" in md
        assert "main.py" in md
        assert "Add rate limiter" in md


class TestGenerateOnboardingReportIntegration:
    def test_runs_on_real_directory(self, tmp_path):
        src = tmp_path / "app.py"
        src.write_text("def run():\n    # TODO: implement\n    pass\n")
        
        report = generate_onboarding_report(str(tmp_path))
        assert report.project_name == tmp_path.name
        assert report.total_files >= 1
        assert len(report.key_files) >= 1
