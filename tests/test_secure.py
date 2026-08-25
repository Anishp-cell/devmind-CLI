"""
tests/test_secure.py

Unit tests for devmind.analysis.secure:
Tests secret scanning (regex + entropy), dangerous sink detection across languages,
injection pattern matching, crypto weaknesses, config misconfigurations, and CVE auditing.
"""

import pytest
import os
import pathlib

from devmind.analysis.secure import (
    SecretScanner,
    PatternEngineScanner,
    PythonAstSinkVisitor,
    DependencyAuditor,
    SensitiveFileAuditor,
    SecurityAnalyzer,
    format_secure_markdown,
    run_security_analysis
)
from devmind.analysis.secure_patterns import calculate_shannon_entropy


class TestSecretScanner:
    def test_detects_aws_key(self):
        scanner = SecretScanner()
        test_key = "AKIA" + "IOSFODNN7B72G9KJ"
        content = f'AWS_ACCESS_KEY_ID = "{test_key}"\n'
        findings = scanner.scan_file("config/aws.py", content)
        assert len(findings) >= 1
        assert any("AWS Access Key" in f.title for f in findings)
        assert findings[0].severity == "CRITICAL"

    def test_detects_openai_key(self):
        scanner = SecretScanner()
        test_key = "sk-proj-" + "1234567890abcdef1234567890abcdef1234567890"
        content = f'api_key = "{test_key}"\n'
        findings = scanner.scan_file("services/ai.py", content)
        assert len(findings) >= 1
        assert any("OpenAI" in f.title for f in findings)

    def test_detects_high_entropy_assignment(self):
        scanner = SecretScanner()
        # High entropy 32-char token
        content = 'custom_secret_key = "a8f9b2c3d4e5f60718293a4b5c6d7e8f"\n'
        findings = scanner.scan_file("app/auth.py", content)
        assert len(findings) >= 1
        assert any("Entropy" in f.title or "Secret" in f.category for f in findings)

    def test_ignores_placeholders(self):
        scanner = SecretScanner()
        content = 'api_key = "your-api-key-here-placeholder"\n'
        findings = scanner.scan_file("app/config.py", content)
        assert len(findings) == 0

    def test_masks_secret_in_snippet(self):
        scanner = SecretScanner()
        test_key = "sk_" + "live_" + "1234567890abcdef12345678"
        content = f'stripe_key = "{test_key}"\n'
        findings = scanner.scan_file("billing.py", content)
        assert len(findings) >= 1
        assert test_key not in findings[0].code_snippet
        assert "***" in findings[0].code_snippet


class TestDangerousSinkDetector:
    def test_detects_eval_and_exec(self):
        content = "def run_code(user_input):\n    eval(user_input)\n    exec(user_input)\n"
        import ast
        tree = ast.parse(content)
        visitor = PythonAstSinkVisitor("handlers/script.py", content.splitlines())
        visitor.visit(tree)

        assert len(visitor.findings) == 2
        assert any("eval()" in f.title for f in visitor.findings)
        assert any("exec()" in f.title for f in visitor.findings)
        assert all(f.severity == "CRITICAL" for f in visitor.findings)

    def test_detects_subprocess_shell_true(self):
        content = "import subprocess\ndef ping(ip):\n    subprocess.run(f'ping {ip}', shell=True)\n"
        import ast
        tree = ast.parse(content)
        visitor = PythonAstSinkVisitor("utils/net.py", content.splitlines())
        visitor.visit(tree)

        assert len(visitor.findings) >= 1
        assert any("shell=True" in f.title for f in visitor.findings)

    def test_detects_pickle_loads(self):
        content = "import pickle\ndef unpack(raw):\n    return pickle.loads(raw)\n"
        import ast
        tree = ast.parse(content)
        visitor = PythonAstSinkVisitor("cache/store.py", content.splitlines())
        visitor.visit(tree)

        assert len(visitor.findings) >= 1
        assert any("pickle" in f.title.lower() for f in visitor.findings)


class TestPolyglotPatternScanner:
    def test_detects_js_innerhtml_and_child_process(self):
        scanner = PatternEngineScanner()
        js_code = (
            "document.getElementById('root').innerHTML = dynamicUserContent;\n"
            "child_process.exec(`cat ${filename}`, cb);\n"
        )
        findings = scanner.scan_file("frontend/render.js", js_code)
        assert len(findings) >= 2
        assert any("innerHTML" in f.title for f in findings)
        assert any("child_process" in f.title for f in findings)

    def test_detects_go_template_html_bypass(self):
        scanner = PatternEngineScanner()
        go_code = "func render(w http.ResponseWriter, data string) { template.HTML(data) }\n"
        findings = scanner.scan_file("server.go", go_code)
        assert len(findings) >= 1
        assert any("template.HTML" in f.title for f in findings)

    def test_detects_rust_unsafe_block(self):
        scanner = PatternEngineScanner()
        rust_code = "fn deref_ptr(ptr: *const i32) -> i32 { unsafe { *ptr } }\n"
        findings = scanner.scan_file("lib.rs", rust_code)
        assert len(findings) >= 1
        assert any("Unsafe" in f.title for f in findings)


class TestInjectionAndCryptoScanners:
    def test_detects_sqli_string_interpolation(self):
        scanner = PatternEngineScanner()
        py_code = "cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')\n"
        findings = scanner.scan_file("db/repo.py", py_code)
        assert len(findings) >= 1
        assert any("SQL Injection" in f.title for f in findings)
        assert findings[0].severity == "CRITICAL"

    def test_detects_weak_crypto_md5(self):
        scanner = PatternEngineScanner()
        py_code = "hashed_pass = hashlib.md5(password.encode()).hexdigest()\n"
        findings = scanner.scan_file("auth.py", py_code)
        assert len(findings) >= 1
        assert any("MD5" in f.title for f in findings)

    def test_detects_debug_mode_and_cors_wildcard(self):
        scanner = PatternEngineScanner()
        py_code = "DEBUG = True\nallow_origins = ['*']\nverify = False\n"
        findings = scanner.scan_file("settings.py", py_code)
        assert len(findings) >= 3
        assert any("Debug Mode" in f.title for f in findings)
        assert any("CORS Wildcard" in f.title for f in findings)
        assert any("SSL/TLS" in f.title for f in findings)


class TestDependencyAndFileAuditors:
    def test_detects_vulnerable_python_dependency(self):
        auditor = DependencyAuditor()
        files = [{
            "relative_path": "requirements.txt",
            "content": "requests==2.28.0\nfastapi==0.100.0\n"
        }]
        findings = auditor.scan_manifests(files)
        assert len(findings) >= 2
        assert any("requests" in f.title.lower() for f in findings)
        assert any("fastapi" in f.title.lower() for f in findings)

    def test_detects_sensitive_files(self):
        auditor = SensitiveFileAuditor()
        files = [
            {"relative_path": ".env", "content": "SECRET=123"},
            {"relative_path": "certs/server.key", "content": "KEY"},
            {"relative_path": "db_dump.sqlite", "content": "SQLITE"}
        ]
        findings = auditor.scan_files(files)
        assert len(findings) == 3
        assert all(f.category == "Sensitive File Exposure" for f in findings)


class TestSecurityAnalyzerIntegration:
    def test_runs_clean_on_clean_project(self, tmp_path):
        clean_file = tmp_path / "app.py"
        clean_file.write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

        report = run_security_analysis(str(tmp_path))
        assert report.risk_grade == "A"
        assert report.critical_count == 0
        assert report.risk_score == 100

    def test_formats_markdown_report(self):
        analyzer = SecurityAnalyzer([
            {
                "relative_path": "api/views.py",
                "content": "eval(req.body)\n"
            }
        ])
        report = analyzer.run_security_audit()
        md = format_secure_markdown(report)
        assert "# 🔒 DevMind Security & Vulnerability Audit Report" in md
        assert "Arbitrary Code Execution via eval()" in md
        assert "CRITICAL" in md
