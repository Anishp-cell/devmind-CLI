"""
devmind/analysis/secure.py

Comprehensive offline Security Penetration & Vulnerability Scanner for DevMind.
Runs 100% locally and offline without external API dependencies or fees.
Scans for hardcoded secrets, dangerous sinks across multiple languages (Python, JS/TS, Go, Rust),
injection vulnerabilities (SQLi, SSRF, Path Traversal, SSTI), cryptographic weaknesses,
security misconfigurations, sensitive files in git, and dependency CVEs.
"""

from __future__ import annotations

import ast
import os
import re
import pathlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Set, Optional, Any, Tuple

from devmind.analysis.secure_patterns import (
    SECRET_PATTERNS,
    calculate_shannon_entropy,
    PYTHON_DANGEROUS_CALLS,
    PYTHON_DANGEROUS_ATTRIBUTES,
    POLYGLOT_DANGEROUS_PATTERNS,
    INJECTION_PATTERNS,
    CRYPTO_WEAKNESS_PATTERNS,
    CONFIG_MISCONFIG_PATTERNS,
    BUNDLED_VULNERABLE_PACKAGES
)

logger = logging.getLogger("devmind.analysis.secure")


@dataclass
class SecurityFinding:
    """Represents an individual security finding/vulnerability."""
    id: str                        # e.g. "SEC-AWS-001"
    severity: str                  # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO"
    category: str                  # "Secret Leak" | "Dangerous Sink" | "Injection" | etc.
    owasp_category: str            # e.g. "A05:2025 - Injection"
    title: str                     # Descriptive title
    file_path: str                 # Relative path to vulnerable file
    line_number: int               # 1-indexed line number
    code_snippet: str              # Offending line of code (sanitized)
    exploit_scenario: str          # What an attacker could achieve
    remediation: str               # Explicit how-to-fix instructions
    cwe_id: str = "CWE-Other"      # e.g. "CWE-798"
    rule_id: str = ""              # Internal rule reference


@dataclass
class SecurityReport:
    """Comprehensive aggregation of all security audit findings."""
    scan_timestamp: str
    target_directory: str
    files_scanned: int
    total_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    findings: List[SecurityFinding] = field(default_factory=list)
    summary_by_category: Dict[str, int] = field(default_factory=dict)
    risk_grade: str = "A"          # "A" | "B" | "C" | "D" | "F"
    risk_score: int = 100          # 0 (worst) to 100 (cleanest)


# ─────────────────────────────────────────────────────────────────────────
# 1. SECRET SCANNER (Regex + Shannon Entropy + Heuristics)
# ─────────────────────────────────────────────────────────────────────────
class SecretScanner:
    """Scans all file contents for hardcoded credentials, tokens, and high-entropy secrets."""
    
    # Exclude common test / mock directories from high-entropy alerting
    IGNORED_PATH_SUBSTRINGS = ["/tests/", "/test/", "/fixtures/", "/mocks/", "/__pycache__/", "/node_modules/", "/.git/", "/dist/", "/build/"]
    PLACEHOLDER_SUBSTRINGS = ["example", "placeholder", "dummy", "fake", "xxxx", "test", "your-", "TODO", "CHANGEME", "INSERT_"]

    def scan_file(self, rel_path: str, content: str) -> List[SecurityFinding]:
        findings: List[SecurityFinding] = []
        normalized_path = rel_path.replace("\\", "/").lower()
        parts = normalized_path.split("/")
        filename = pathlib.Path(rel_path).name.lower()
        # Template/example env files (.env.example, .env.sample, config.example.*) are
        # never real secrets — skip them outright rather than relying on placeholder
        # substring matching, which misses values like "your_key1" (underscore, not "your-").
        if filename in (".env.example", ".env.sample", ".env.template") or filename.endswith((".example", ".sample")):
            return findings
        is_test_file = (
            "tests" in parts
            or "test" in parts
            or "fixtures" in parts
            or "mocks" in parts
            or "node_modules" in parts
            or ".git" in parts
            or pathlib.Path(rel_path).name.startswith("test_")
        )

        lines = content.splitlines()
        for idx, line in enumerate(lines, start=1):
            clean_line = line.strip()
            if not clean_line or clean_line.startswith(("#", "//", "/*", "*")):
                continue

            # 1. Regex Pattern Matching (skipped for test/fixture/mock files —
            # those routinely contain fake keys that match real-looking patterns)
            for rule in SECRET_PATTERNS:
                if is_test_file:
                    break
                pattern = rule.get("pattern", "")
                if not pattern:
                    continue
                match = re.search(pattern, clean_line)
                if match:
                    matched_str = match.group(0)
                    # Check for obvious placeholders
                    if any(ph in matched_str.lower() for ph in self.PLACEHOLDER_SUBSTRINGS):
                        continue

                    # Mask the sensitive secret in snippet output
                    masked_snippet = self._mask_secret(clean_line, matched_str)

                    findings.append(SecurityFinding(
                        id=f"SEC-{rule['id']}",
                        severity=rule["severity"],
                        category="Secret Leak",
                        owasp_category=rule["owasp"],
                        title=rule["name"],
                        file_path=rel_path,
                        line_number=idx,
                        code_snippet=masked_snippet,
                        exploit_scenario=rule["description"],
                        remediation=rule["remediation"],
                        cwe_id=rule["cwe"],
                        rule_id=rule["id"]
                    ))

            # 2. Shannon Entropy Analysis for Assignment Statements
            if not is_test_file:
                entropy_finding = self._check_assignment_entropy(clean_line, rel_path, idx)
                if entropy_finding:
                    # Avoid duplicate if regex already caught it
                    if not any(f.line_number == idx and f.category == "Secret Leak" for f in findings):
                        findings.append(entropy_finding)

        return findings

    def _check_assignment_entropy(self, line: str, rel_path: str, lineno: int) -> Optional[SecurityFinding]:
        """Detects custom high-entropy secrets in variable assignment patterns (e.g. custom_token = '...')."""
        match = re.search(r"(?i)(?:key|token|secret|password|api_key|auth_token|access_key)\s*=\s*['\"]([A-Za-z0-9_\-\.\/\+=]{18,})['\"]", line)
        if match:
            candidate = match.group(1)
            # Filter obvious placeholders or UUIDs
            if any(ph in candidate.lower() for ph in self.PLACEHOLDER_SUBSTRINGS):
                return None
            
            entropy = calculate_shannon_entropy(candidate)
            # High-entropy threshold (typical base64/hex tokens have entropy > 4.2)
            if entropy >= 4.3 and not re.match(r"^[0-9a-fA-F\-]{36}$", candidate):  # not a pure UUID
                masked = self._mask_secret(line, candidate)
                return SecurityFinding(
                    id="SEC-ENTROPY-001",
                    severity="HIGH",
                    category="Secret Leak",
                    owasp_category="A04:2025 - Cryptographic Failures",
                    title="High-Entropy Custom Secret in Variable Assignment",
                    file_path=rel_path,
                    line_number=lineno,
                    code_snippet=masked,
                    exploit_scenario="A high-entropy token was discovered hardcoded in code. If valid, an attacker could authenticate without credentials.",
                    remediation="Move this secret into an environment variable or secrets manager (e.g. AWS Secrets Manager, Vault).",
                    cwe_id="CWE-798",
                    rule_id="ENTROPY-001"
                )
        return None

    def _mask_secret(self, snippet: str, secret: str) -> str:
        if len(secret) <= 6:
            return snippet.replace(secret, "***")
        masked = secret[:3] + "*" * (len(secret) - 6) + secret[-3:]
        return snippet.replace(secret, masked)


# ─────────────────────────────────────────────────────────────────────────
# 2. PYTHON AST DANGEROUS SINK DETECTOR
# ─────────────────────────────────────────────────────────────────────────
class PythonAstSinkVisitor(ast.NodeVisitor):
    """Inspects Python AST nodes for hazardous functions (eval, exec, pickle, subprocess shell=True)."""

    def __init__(self, rel_path: str, lines: List[str]):
        self.rel_path = rel_path
        self.lines = lines
        self.findings: List[SecurityFinding] = []

    def _get_snippet(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.lines):
            return self.lines[lineno - 1].strip()
        return ""

    def visit_Call(self, node: ast.Call):
        lineno = getattr(node, "lineno", 1)
        snippet = self._get_snippet(lineno)

        # 1. Simple Function Calls: eval(), exec(), compile(), etc.
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in PYTHON_DANGEROUS_CALLS:
                info = PYTHON_DANGEROUS_CALLS[func_name]
                self.findings.append(SecurityFinding(
                    id=f"SEC-PY-{func_name.upper()}",
                    severity=info["severity"],
                    category="Dangerous Sink",
                    owasp_category=info["owasp"],
                    title=info["title"],
                    file_path=self.rel_path,
                    line_number=lineno,
                    code_snippet=snippet,
                    exploit_scenario=info["risk"],
                    remediation=info["fix"],
                    cwe_id=info["cwe"],
                    rule_id=f"PY-{func_name.upper()}"
                ))

        # 2. Attribute Calls: pickle.loads(), os.system(), subprocess.run(shell=True)
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                mod_name = node.func.value.id
                attr_name = node.func.attr
                key = (mod_name, attr_name)

                if key in PYTHON_DANGEROUS_ATTRIBUTES:
                    info = PYTHON_DANGEROUS_ATTRIBUTES[key]
                    
                    # Check shell=True kwargs if required
                    if info.get("check_shell"):
                        has_shell_true = False
                        for kw in node.keywords:
                            if kw.arg == "shell":
                                if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                    has_shell_true = True
                                elif isinstance(kw.value, ast.NameConstant) and kw.value.value is True:
                                    has_shell_true = True
                        if has_shell_true:
                            self.findings.append(SecurityFinding(
                                id=f"SEC-PY-{mod_name.upper()}-{attr_name.upper()}",
                                severity=info["severity"],
                                category="Dangerous Sink",
                                owasp_category=info["owasp"],
                                title=info["title"],
                                file_path=self.rel_path,
                                line_number=lineno,
                                code_snippet=snippet,
                                exploit_scenario=info["risk"],
                                remediation=info["fix"],
                                cwe_id=info["cwe"],
                                rule_id=f"PY-{mod_name.upper()}-{attr_name.upper()}"
                            ))
                    else:
                        self.findings.append(SecurityFinding(
                            id=f"SEC-PY-{mod_name.upper()}-{attr_name.upper()}",
                            severity=info["severity"],
                            category="Dangerous Sink",
                            owasp_category=info["owasp"],
                            title=info["title"],
                            file_path=self.rel_path,
                            line_number=lineno,
                            code_snippet=snippet,
                            exploit_scenario=info["risk"],
                            remediation=info["fix"],
                            cwe_id=info["cwe"],
                            rule_id=f"PY-{mod_name.upper()}-{attr_name.upper()}"
                        ))

        self.generic_visit(node)


# ─────────────────────────────────────────────────────────────────────────
# 3. POLYGLOT CODE & INJECTION PATTERN SCANNER
# ─────────────────────────────────────────────────────────────────────────
class PatternEngineScanner:
    """Scans code across all languages for injection, polyglot sinks, crypto issues, and misconfigurations."""

    def scan_file(self, rel_path: str, content: str) -> List[SecurityFinding]:
        findings: List[SecurityFinding] = []
        ext = pathlib.Path(rel_path).suffix.lower()
        lines = content.splitlines()

        for idx, line in enumerate(lines, start=1):
            clean_line = line.strip()
            if not clean_line or clean_line.startswith(("#", "//", "/*", "*")):
                continue

            # 1. Polyglot dangerous patterns (JS/TS, Go, Rust)
            for rule in POLYGLOT_DANGEROUS_PATTERNS:
                if ext in rule["lang"]:
                    if re.search(rule["pattern"], clean_line):
                        findings.append(SecurityFinding(
                            id=f"SEC-{rule['id']}",
                            severity=rule["severity"],
                            category="Dangerous Sink",
                            owasp_category=rule["owasp"],
                            title=rule["name"],
                            file_path=rel_path,
                            line_number=idx,
                            code_snippet=clean_line,
                            exploit_scenario=rule["risk"],
                            remediation=rule["fix"],
                            cwe_id=rule["cwe"],
                            rule_id=rule["id"]
                        ))

            # 2. Injection patterns (SQLi, Path Traversal, SSRF, SSTI)
            for rule in INJECTION_PATTERNS:
                if re.search(rule["pattern"], clean_line):
                    findings.append(SecurityFinding(
                        id=f"SEC-{rule['id']}",
                        severity=rule["severity"],
                        category="Injection Vulnerability",
                        owasp_category=rule["owasp"],
                        title=rule["name"],
                        file_path=rel_path,
                        line_number=idx,
                        code_snippet=clean_line,
                        exploit_scenario=rule["risk"],
                        remediation=rule["fix"],
                        cwe_id=rule["cwe"],
                        rule_id=rule["id"]
                    ))

            # 3. Cryptographic Weaknesses
            for rule in CRYPTO_WEAKNESS_PATTERNS:
                if re.search(rule["pattern"], clean_line):
                    findings.append(SecurityFinding(
                        id=f"SEC-{rule['id']}",
                        severity=rule["severity"],
                        category="Cryptographic Weakness",
                        owasp_category=rule["owasp"],
                        title=rule["name"],
                        file_path=rel_path,
                        line_number=idx,
                        code_snippet=clean_line,
                        exploit_scenario=rule["risk"],
                        remediation=rule["fix"],
                        cwe_id=rule["cwe"],
                        rule_id=rule["id"]
                    ))

            # 4. Configuration Misconfigurations
            for rule in CONFIG_MISCONFIG_PATTERNS:
                if re.search(rule["pattern"], clean_line):
                    findings.append(SecurityFinding(
                        id=f"SEC-{rule['id']}",
                        severity=rule["severity"],
                        category="Security Misconfiguration",
                        owasp_category=rule["owasp"],
                        title=rule["name"],
                        file_path=rel_path,
                        line_number=idx,
                        code_snippet=clean_line,
                        exploit_scenario=rule["risk"],
                        remediation=rule["fix"],
                        cwe_id=rule["cwe"],
                        rule_id=rule["id"]
                    ))

        return findings


# ─────────────────────────────────────────────────────────────────────────
# 4. DEPENDENCY & MANIFEST AUDITOR (Offline CVE Matching)
# ─────────────────────────────────────────────────────────────────────────
class DependencyAuditor:
    """Scans manifest files (requirements.txt, package.json) against known CVE database."""

    def scan_manifests(self, files_data: List[Dict[str, Any]]) -> List[SecurityFinding]:
        findings: List[SecurityFinding] = []

        for f in files_data:
            rel = f["relative_path"].replace("\\", "/")
            base = pathlib.Path(rel).name.lower()
            content = f.get("content", "")

            # Scan requirements.txt
            if base in ("requirements.txt", "requirements-dev.txt", "requirements.in"):
                findings.extend(self._scan_python_requirements(rel, content))
            # Scan package.json
            elif base == "package.json":
                findings.extend(self._scan_package_json(rel, content))

        return findings

    def _scan_python_requirements(self, rel_path: str, content: str) -> List[SecurityFinding]:
        findings: List[SecurityFinding] = []
        for idx, line in enumerate(content.splitlines(), start=1):
            clean = line.strip().split("#")[0].strip()
            if not clean:
                continue
            # Parse package==version or package>=version
            match = re.match(r"^([a-zA-Z0-9_\-]+)\s*(?:==|>=|<=|~=)\s*([0-9a-zA-Z\.\-]+)", clean)
            if match:
                pkg_name = match.group(1).lower()
                version = match.group(2)
                if pkg_name in BUNDLED_VULNERABLE_PACKAGES:
                    for vuln in BUNDLED_VULNERABLE_PACKAGES[pkg_name]:
                        findings.append(SecurityFinding(
                            id=f"SEC-DEP-{pkg_name.upper()}",
                            severity=vuln["severity"],
                            category="Vulnerable Dependency",
                            owasp_category="A03:2025 - Software Supply Chain Failures",
                            title=f"Known Vulnerability in {pkg_name} ({vuln['cve']})",
                            file_path=rel_path,
                            line_number=idx,
                            code_snippet=clean,
                            exploit_scenario=f"{vuln['desc']} (Affects versions {vuln['affected']})",
                            remediation=f"Upgrade {pkg_name} to version >= {vuln['fixed']}.",
                            cwe_id="CWE-1395",
                            rule_id=vuln["cve"]
                        ))
        return findings

    def _scan_package_json(self, rel_path: str, content: str) -> List[SecurityFinding]:
        findings: List[SecurityFinding] = []
        try:
            import json
            data = json.loads(content)
            deps = {}
            deps.update(data.get("dependencies", {}))
            deps.update(data.get("devDependencies", {}))

            for pkg_name, ver_str in deps.items():
                clean_pkg = pkg_name.lower()
                clean_ver = re.sub(r"[^\d\.]", "", ver_str)
                if clean_pkg in BUNDLED_VULNERABLE_PACKAGES:
                    for vuln in BUNDLED_VULNERABLE_PACKAGES[clean_pkg]:
                        findings.append(SecurityFinding(
                            id=f"SEC-DEP-{clean_pkg.upper()}",
                            severity=vuln["severity"],
                            category="Vulnerable Dependency",
                            owasp_category="A03:2025 - Software Supply Chain Failures",
                            title=f"Known Vulnerability in {clean_pkg} ({vuln['cve']})",
                            file_path=rel_path,
                            line_number=1,
                            code_snippet=f'"{pkg_name}": "{ver_str}"',
                            exploit_scenario=f"{vuln['desc']} (Affects versions {vuln['affected']})",
                            remediation=f"Upgrade {clean_pkg} to version >= {vuln['fixed']}.",
                            cwe_id="CWE-1395",
                            rule_id=vuln["cve"]
                        ))
        except Exception:
            pass
        return findings


# ─────────────────────────────────────────────────────────────────────────
# 5. SENSITIVE FILE & PERMISSION AUDITOR
# ─────────────────────────────────────────────────────────────────────────
class SensitiveFileAuditor:
    """Checks for committed .env files, private keys, database dumps, and credentials in git."""

    SENSITIVE_EXTENSIONS = {".key", ".pem", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db", ".sql"}
    SENSITIVE_FILENAMES = {".env", ".env.local", ".env.production", ".env.staging", "id_rsa", "id_ed25519", "credentials.json", "service_account.json"}

    def scan_files(self, files_data: List[Dict[str, Any]]) -> List[SecurityFinding]:
        findings: List[SecurityFinding] = []

        for f in files_data:
            rel = f["relative_path"].replace("\\", "/")
            base = pathlib.Path(rel).name.lower()
            ext = pathlib.Path(rel).suffix.lower()

            if base in self.SENSITIVE_FILENAMES or ext in self.SENSITIVE_EXTENSIONS:
                findings.append(SecurityFinding(
                    id="SEC-FILE-001",
                    severity="CRITICAL",
                    category="Sensitive File Exposure",
                    owasp_category="A02:2025 - Security Misconfiguration",
                    title=f"Sensitive File '{base}' Tracked in Repository",
                    file_path=rel,
                    line_number=1,
                    code_snippet=rel,
                    exploit_scenario="Committing environment secrets, private keys, or database snapshots into source control leaks private credentials.",
                    remediation=f"Add '{base}' to .gitignore and remove it from git history with 'git rm --cached {rel}'.",
                    cwe_id="CWE-538",
                    rule_id="FILE-EXPOSURE"
                ))

        return findings


# ─────────────────────────────────────────────────────────────────────────
# 6. MAIN SECURITY ANALYZER ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────
class SecurityAnalyzer:
    """
    Main orchestrator for running the complete penetration & vulnerability audit suite.
    """

    def __init__(self, files_data: List[Dict[str, Any]], target_dir: str = "."):
        self.files_data = files_data
        self.target_dir = target_dir
        self.secret_scanner = SecretScanner()
        self.pattern_scanner = PatternEngineScanner()
        self.dep_auditor = DependencyAuditor()
        self.file_auditor = SensitiveFileAuditor()

    def run_security_audit(self, severity_filter: Optional[str] = None, category_filter: Optional[str] = None) -> SecurityReport:
        all_findings: List[SecurityFinding] = []
        files_scanned = 0

        # 1. Scan individual code files
        for f in self.files_data:
            rel = f["relative_path"].replace("\\", "/")
            # Do not scan the scanner's own pattern definitions
            if rel.endswith("secure_patterns.py"):
                continue

            # Check if this is a test/fixture file
            normalized_path = rel.lower()
            parts = normalized_path.split("/")
            is_test = (
                "tests" in parts
                or "test" in parts
                or "fixtures" in parts
                or "mocks" in parts
                or pathlib.Path(rel).name.startswith("test_")
            )

            if is_test:
                continue

            content = f.get("content", "")
            lines = content.splitlines()
            files_scanned += 1

            # A. Secret Scanner
            all_findings.extend(self.secret_scanner.scan_file(rel, content))

            # B. Pattern & Injection Scanners
            all_findings.extend(self.pattern_scanner.scan_file(rel, content))

            # C. Python AST Sink Visitor
            if rel.endswith(".py"):
                try:
                    tree = ast.parse(content, filename=rel)
                    visitor = PythonAstSinkVisitor(rel, lines)
                    visitor.visit(tree)
                    all_findings.extend(visitor.findings)
                except SyntaxError:
                    pass

        # 2. Scan manifests for vulnerable dependencies
        all_findings.extend(self.dep_auditor.scan_manifests(self.files_data))

        # 3. Check for sensitive files
        all_findings.extend(self.file_auditor.scan_files(self.files_data))

        # 4. Deduplicate findings on (file_path, line_number, title)
        unique_findings: List[SecurityFinding] = []
        seen = set()
        for f in all_findings:
            key = (f.file_path, f.line_number, f.title)
            if key not in seen:
                seen.add(key)
                unique_findings.append(f)

        # 5. Apply filters if requested
        filtered_findings = unique_findings
        if severity_filter:
            sev_target = severity_filter.upper()
            if sev_target == "CRITICAL":
                filtered_findings = [f for f in filtered_findings if f.severity == "CRITICAL"]
            elif sev_target == "HIGH":
                filtered_findings = [f for f in filtered_findings if f.severity in ("CRITICAL", "HIGH")]
            elif sev_target == "MEDIUM":
                filtered_findings = [f for f in filtered_findings if f.severity in ("CRITICAL", "HIGH", "MEDIUM")]

        if category_filter:
            filtered_findings = [f for f in filtered_findings if category_filter.lower() in f.category.lower()]

        # 6. Compute statistics & Composite Risk Grade
        crit = sum(1 for f in unique_findings if f.severity == "CRITICAL")
        high = sum(1 for f in unique_findings if f.severity == "HIGH")
        med = sum(1 for f in unique_findings if f.severity == "MEDIUM")
        low = sum(1 for f in unique_findings if f.severity in ("LOW", "INFO"))

        # Risk score computation: 100 base, deductions for vulnerabilities
        score = 100 - (crit * 25 + high * 12 + med * 5 + low * 2)
        score = max(0, min(100, score))

        if score >= 90 and crit == 0 and high == 0:
            grade = "A"
        elif score >= 75 and crit == 0:
            grade = "B"
        elif score >= 60:
            grade = "C"
        elif score >= 40:
            grade = "D"
        else:
            grade = "F"

        # Group by category
        categories: Dict[str, int] = {}
        for f in unique_findings:
            categories[f.category] = categories.get(f.category, 0) + 1

        # Sort findings: CRITICAL -> HIGH -> MEDIUM -> LOW
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
        filtered_findings.sort(key=lambda x: (severity_order.get(x.severity, 99), x.file_path, x.line_number))

        return SecurityReport(
            scan_timestamp=datetime.now().isoformat(),
            target_directory=self.target_dir,
            files_scanned=files_scanned,
            total_findings=len(unique_findings),
            critical_count=crit,
            high_count=high,
            medium_count=med,
            low_count=low,
            findings=filtered_findings,
            summary_by_category=categories,
            risk_grade=grade,
            risk_score=score
        )


# ─────────────────────────────────────────────────────────────────────────
# 7. MARKDOWN REPORT FORMATTER
# ─────────────────────────────────────────────────────────────────────────
def format_secure_markdown(report: SecurityReport) -> str:
    """Renders the SecurityReport into an enterprise-grade Markdown security audit document."""
    lines = [
        "# 🔒 DevMind Security & Vulnerability Audit Report",
        "",
        f"- **Project:** `{report.target_directory}`",
        f"- **Timestamp:** {report.scan_timestamp}",
        f"- **Files Scanned:** {report.files_scanned}",
        f"- **Security Grade:** **{report.risk_grade}** (Score: {report.risk_score}/100)",
        f"- **Vulnerabilities Found:** 🔴 {report.critical_count} Critical  •  🟠 {report.high_count} High  •  🟡 {report.medium_count} Medium  •  🔵 {report.low_count} Low",
        "",
        "---",
        "",
        "## 📊 Findings Summary by Category",
        "",
        "| Category | Count |",
        "|---|---|",
    ]

    for cat, count in sorted(report.summary_by_category.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"| {cat} | **{count}** |")

    lines.extend([
        "",
        "---",
        "",
        "## 🚨 Detailed Findings & Remediation Plan",
        ""
    ])

    if not report.findings:
        lines.append("✅ **Clean Audit:** No security vulnerabilities or hardcoded secrets detected in scanned codebase.")
    else:
        for idx, f in enumerate(report.findings, start=1):
            sev_icon = "🔴" if f.severity == "CRITICAL" else ("🟠" if f.severity == "HIGH" else "🟡")
            lines.extend([
                f"### {idx}. {sev_icon} [{f.severity}] {f.title}",
                "",
                f"- **ID:** `{f.id}` | **CWE:** `{f.cwe_id}` | **OWASP:** `{f.owasp_category}`",
                f"- **Location:** `{f.file_path}:L{f.line_number}`",
                f"- **Code Snippet:**",
                "```",
                f"{f.code_snippet}",
                "```",
                f"- **Exploit Scenario:** {f.exploit_scenario}",
                f"- **Remediation:** {f.remediation}",
                "",
                "---",
                ""
            ])

    lines.append("*Generated by DevMind CLI (`devmind secure`) — 100% Offline Penetration Scanner*")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────
# 8. PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────
def run_security_analysis(
    directory: str,
    severity: Optional[str] = None,
    category: Optional[str] = None
) -> SecurityReport:
    """
    Runs the complete offline security audit on the specified directory.
    """
    from devmind.ingestion.file_reader import scan_codebase_files

    root_path = pathlib.Path(directory).resolve()
    files = scan_codebase_files(str(root_path))
    analyzer = SecurityAnalyzer(files, target_dir=str(root_path))
    return analyzer.run_security_audit(severity_filter=severity, category_filter=category)
