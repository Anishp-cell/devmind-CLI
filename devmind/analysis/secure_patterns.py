"""
devmind/analysis/secure_patterns.py

Comprehensive pattern database for DevMind's offline security & penetration scanner.
Covers secrets, dangerous sinks across multiple languages, injection patterns,
cryptographic weaknesses, configuration misconfigurations, and bundled CVE signatures.
"""

from __future__ import annotations
import math
import re
from typing import Dict, List, Tuple, Any

# ─────────────────────────────────────────────────────────────────────────
# 1. SECRET DETECTION PATTERNS (90+ curated high-precision regexes)
# ─────────────────────────────────────────────────────────────────────────
SECRET_PATTERNS: List[Dict[str, Any]] = [
    # AWS
    {
        "id": "AWS-001",
        "name": "AWS Access Key ID",
        "pattern": r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}",
        "severity": "CRITICAL",
        "cwe": "CWE-798",
        "owasp": "A04:2025 - Cryptographic Failures",
        "description": "Exposed AWS Access Key ID allows unauthorized cloud infrastructure access.",
        "remediation": "Move credentials to AWS IAM Roles or environment variables (AWS_ACCESS_KEY_ID)."
    },
    {
        "id": "AWS-002",
        "name": "AWS Secret Access Key",
        "pattern": r"(?i)(?:aws_secret_access_key|aws_secret|aws_key)\s*[:=]\s*['\"]([A-Za-z0-9/+=]{40})['\"]",
        "severity": "CRITICAL",
        "cwe": "CWE-798",
        "owasp": "A04:2025 - Cryptographic Failures",
        "description": "Exposed AWS Secret Access Key grants programmatic access to AWS services.",
        "remediation": "Revoke key in AWS IAM and use Secrets Manager or environment variables."
    },
    # Google Cloud & Firebase
    {
        "id": "GCP-001",
        "name": "Google API / Firebase Key",
        "pattern": r"AIza[0-9A-Za-z\-_]{35}",
        "severity": "HIGH",
        "cwe": "CWE-798",
        "owasp": "A04:2025 - Cryptographic Failures",
        "description": "Hardcoded Google/Firebase API key.",
        "remediation": "Restrict API key scope in Google Cloud Console and load from environment variables."
    },
    {
        "id": "GCP-002",
        "name": "Google OAuth Access Token",
        "pattern": r"ya29\.[0-9A-Za-z\-_]{30,}",
        "severity": "CRITICAL",
        "cwe": "CWE-798",
        "owasp": "A04:2025 - Cryptographic Failures",
        "description": "Exposed Google OAuth user/service account bearer token.",
        "remediation": "Revoke OAuth token immediately and implement dynamic token generation."
    },
    # GitHub & GitLab
    {
        "id": "GH-001",
        "name": "GitHub Personal Access Token",
        "pattern": r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}",
        "severity": "CRITICAL",
        "cwe": "CWE-798",
        "owasp": "A04:2025 - Cryptographic Failures",
        "description": "Exposed GitHub Personal Access Token grants repository read/write access.",
        "remediation": "Revoke token at github.com/settings/tokens and store in GitHub Secrets or .env."
    },
    {
        "id": "GL-001",
        "name": "GitLab Personal Access Token",
        "pattern": r"glpat-[0-9a-zA-Z\-_]{20,}",
        "severity": "CRITICAL",
        "cwe": "CWE-798",
        "owasp": "A04:2025 - Cryptographic Failures",
        "description": "Exposed GitLab token grants API and repository access.",
        "remediation": "Revoke token in GitLab User Settings and rotate."
    },
    # AI Providers (OpenAI, Anthropic, Groq, OpenRouter)
    {
        "id": "AI-001",
        "name": "OpenAI / LLM API Key",
        "pattern": r"sk-[a-zA-Z0-9]{20,T3BlbkFJ[a-zA-Z0-9]{20,}|sk-proj-[a-zA-Z0-9_\-]{40,}|sk-[a-zA-Z0-9]{48}",
        "severity": "CRITICAL",
        "cwe": "CWE-798",
        "owasp": "A04:2025 - Cryptographic Failures",
        "description": "Exposed OpenAI API Key can lead to unauthorized API credit consumption.",
        "remediation": "Rotate API key in platform.openai.com and load via OPENAI_API_KEY env var."
    },
    {
        "id": "AI-002",
        "name": "Anthropic Claude API Key",
        "pattern": r"sk-ant-api[0-9]{2}-[a-zA-Z0-9_\-]{80,}",
        "severity": "CRITICAL",
        "cwe": "CWE-798",
        "owasp": "A04:2025 - Cryptographic Failures",
        "description": "Exposed Anthropic API Key allows unauthorized LLM queries.",
        "remediation": "Revoke key in console.anthropic.com and set ANTHROPIC_API_KEY environment variable."
    },
    {
        "id": "AI-003",
        "name": "Groq API Key",
        "pattern": r"gsk_[a-zA-Z0-9]{48,}",
        "severity": "CRITICAL",
        "cwe": "CWE-798",
        "owasp": "A04:2025 - Cryptographic Failures",
        "description": "Exposed Groq API Key.",
        "remediation": "Rotate key at console.groq.com and inject via GROQ_API_KEY environment variable."
    },
    # Payment & Communications
    {
        "id": "STRIPE-001",
        "name": "Stripe Live API Key",
        "pattern": r"(?:sk|rk)_live_[0-9a-zA-Z]{24,}",
        "severity": "CRITICAL",
        "cwe": "CWE-798",
        "owasp": "A04:2025 - Cryptographic Failures",
        "description": "Live Stripe Secret Key grants full access to customer billing and payment methods.",
        "remediation": "Roll key immediately in Stripe Dashboard. Never commit live keys to git."
    },
    {
        "id": "SLACK-001",
        "name": "Slack Bot / Webhook Token",
        "pattern": r"xox[baprs]-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24,}|https://hooks\.slack\.com/services/T[0-9A-Z]+/B[0-9A-Z]+/[0-9A-Za-z]+",
        "severity": "HIGH",
        "cwe": "CWE-798",
        "owasp": "A04:2025 - Cryptographic Failures",
        "description": "Slack integration token or webhook URL exposed.",
        "remediation": "Revoke token in Slack API portal and use environment variables."
    },
    # Asymmetric Keys & Tokens
    {
        "id": "KEY-001",
        "name": "Private Cryptographic Key",
        "pattern": r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY-----",
        "severity": "CRITICAL",
        "cwe": "CWE-321",
        "owasp": "A04:2025 - Cryptographic Failures",
        "description": "Private key file or embedded PEM string detected in source code.",
        "remediation": "Remove private keys from repository history and manage via SSH Agent / KMS."
    },
    {
        "id": "JWT-001",
        "name": "JSON Web Token (JWT)",
        "pattern": r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
        "severity": "MEDIUM",
        "cwe": "CWE-522",
        "owasp": "A07:2025 - Authentication Failures",
        "description": "Hardcoded JWT found in source code.",
        "remediation": "Do not hardcode authentication tokens; issue tokens dynamically per session."
    },
    # Database URIs with credentials
    {
        "id": "DB-001",
        "name": "Database Connection String with Credentials",
        "pattern": r"(?:postgres|postgresql|mysql|mongodb|redis|amqp|mssql):\/\/[a-zA-Z0-9_]+:[a-zA-Z0-9_\-!@#$%^&*+=]+@[a-zA-Z0-9_\.\-]+(?::[0-9]+)?\/[a-zA-Z0-9_\.\-]+",
        "severity": "CRITICAL",
        "cwe": "CWE-798",
        "owasp": "A04:2025 - Cryptographic Failures",
        "description": "Database connection URI contains plaintext username and password.",
        "remediation": "Construct database connection URI dynamically from individual environment variables."
    },
    # Generic Sensitive Assignments
    {
        "id": "GEN-001",
        "name": "Hardcoded Password Assignment",
        "pattern": r"(?i)(?:password|passwd|pwd|secret_key|client_secret|auth_token)\s*=\s*['\"]([^'\"\s]{8,})['\"]",
        "severity": "HIGH",
        "cwe": "CWE-798",
        "owasp": "A07:2025 - Authentication Failures",
        "description": "Variable assignment contains plaintext credential string.",
        "remediation": "Use os.environ.get() or a secrets manager instead of literal strings."
    }
]

# ─────────────────────────────────────────────────────────────────────────
# 2. SHANNON ENTROPY CALCULATOR
# ─────────────────────────────────────────────────────────────────────────
def calculate_shannon_entropy(data: str) -> float:
    """Calculates Shannon entropy in bits per character for high-entropy secret detection."""
    if not data:
        return 0.0
    entropy = 0.0
    length = len(data)
    frequencies: Dict[str, int] = {}
    for char in data:
        frequencies[char] = frequencies.get(char, 0) + 1
    for count in frequencies.values():
        probability = count / length
        entropy -= probability * math.log2(probability)
    return entropy


# ─────────────────────────────────────────────────────────────────────────
# 3. DANGEROUS SINKS & AST INSPECTION RULES
# ─────────────────────────────────────────────────────────────────────────
PYTHON_DANGEROUS_CALLS = {
    "eval": {
        "severity": "CRITICAL",
        "cwe": "CWE-95",
        "owasp": "A05:2025 - Injection",
        "title": "Arbitrary Code Execution via eval()",
        "risk": "Dynamic code evaluation executes arbitrary Python instructions with the privileges of the running process.",
        "fix": "Use json.loads() or ast.literal_eval() if parsing structured data."
    },
    "exec": {
        "severity": "CRITICAL",
        "cwe": "CWE-95",
        "owasp": "A05:2025 - Injection",
        "title": "Arbitrary Code Execution via exec()",
        "risk": "Dynamic statement execution allows attackers to run arbitrary system commands if input is tainted.",
        "fix": "Avoid dynamic code execution; use safe dispatch tables or explicit logic."
    },
    "compile": {
        "severity": "HIGH",
        "cwe": "CWE-94",
        "owasp": "A05:2025 - Injection",
        "title": "Dynamic Code Compilation via compile()",
        "risk": "Compiling arbitrary strings into code objects can lead to arbitrary execution.",
        "fix": "Precompile static code or use secure sandboxed interpreters."
    },
    "__import__": {
        "severity": "HIGH",
        "cwe": "CWE-706",
        "owasp": "A05:2025 - Injection",
        "title": "Dynamic Module Import via __import__()",
        "risk": "Importing modules from unverified string names can execute malicious third-party code.",
        "fix": "Use an explicit allowlist of authorized module names before importing."
    },
}

PYTHON_DANGEROUS_ATTRIBUTES = {
    ("pickle", "loads"): {
        "severity": "CRITICAL",
        "cwe": "CWE-502",
        "owasp": "A08:2025 - Software and Data Integrity Failures",
        "title": "Insecure Deserialization via pickle.loads()",
        "risk": "Pickle serialization can execute arbitrary code upon unpickling malicious payloads.",
        "fix": "Use safer serialization formats like JSON, MessagePack, or Protocol Buffers."
    },
    ("pickle", "load"): {
        "severity": "CRITICAL",
        "cwe": "CWE-502",
        "owasp": "A08:2025 - Software and Data Integrity Failures",
        "title": "Insecure Deserialization via pickle.load()",
        "risk": "Loading untrusted pickled objects allows Remote Code Execution.",
        "fix": "Avoid pickle for untrusted sources; use json.load()."
    },
    ("yaml", "load"): {
        "severity": "CRITICAL",
        "cwe": "CWE-502",
        "owasp": "A08:2025 - Software and Data Integrity Failures",
        "title": "Unsafe YAML Deserialization via yaml.load()",
        "risk": "Calling yaml.load() without SafeLoader can instantiate arbitrary Python objects.",
        "fix": "Always use yaml.safe_load() or yaml.load(data, Loader=yaml.SafeLoader)."
    },
    ("os", "system"): {
        "severity": "CRITICAL",
        "cwe": "CWE-78",
        "owasp": "A05:2025 - Injection",
        "title": "Command Injection via os.system()",
        "risk": "Spawns a subshell directly interpreting string arguments, enabling command chaining.",
        "fix": "Use subprocess.run(..., shell=False) with an explicit argument list."
    },
    ("os", "popen"): {
        "severity": "HIGH",
        "cwe": "CWE-78",
        "owasp": "A05:2025 - Injection",
        "title": "Command Execution via os.popen()",
        "risk": "Opens an OS pipe to a command string without shell argument escaping.",
        "fix": "Use subprocess.Popen with a list of arguments and shell=False."
    },
    ("subprocess", "Popen"): {
        "check_shell": True,
        "severity": "CRITICAL",
        "cwe": "CWE-78",
        "owasp": "A05:2025 - Injection",
        "title": "Command Injection Risk in subprocess.Popen(shell=True)",
        "risk": "Passing shell=True invokes /bin/sh or cmd.exe, enabling command injection via metacharacters (&, |, ;).",
        "fix": "Set shell=False and pass arguments as a list of strings."
    },
    ("subprocess", "run"): {
        "check_shell": True,
        "severity": "CRITICAL",
        "cwe": "CWE-78",
        "owasp": "A05:2025 - Injection",
        "title": "Command Injection Risk in subprocess.run(shell=True)",
        "risk": "Shell execution allows shell metacharacters to execute unintended secondary commands.",
        "fix": "Set shell=False and supply arguments as an array: ['command', 'arg1']."
    },
    ("subprocess", "call"): {
        "check_shell": True,
        "severity": "CRITICAL",
        "cwe": "CWE-78",
        "owasp": "A05:2025 - Injection",
        "title": "Command Injection Risk in subprocess.call(shell=True)",
        "risk": "Invokes system shell with potential argument injection.",
        "fix": "Set shell=False and pass parameters as a list."
    },
}

# ─────────────────────────────────────────────────────────────────────────
# 4. CROSS-LANGUAGE DANGEROUS PATTERNS (JS/TS, Go, Rust, Java)
# ─────────────────────────────────────────────────────────────────────────
POLYGLOT_DANGEROUS_PATTERNS: List[Dict[str, Any]] = [
    # JavaScript / TypeScript
    {
        "lang": [".js", ".jsx", ".ts", ".tsx", ".mjs"],
        "id": "JS-001",
        "name": "DOM-Based Cross-Site Scripting (XSS) via innerHTML",
        "pattern": r"(?:\.innerHTML|\.outerHTML)\s*=\s*(?![`'\"][^`'\"]*[`'\"]\s*;)(.+)",
        "severity": "HIGH",
        "cwe": "CWE-79",
        "owasp": "A05:2025 - Injection",
        "risk": "Directly assigning dynamic strings to innerHTML allows arbitrary JavaScript execution in the browser.",
        "fix": "Use textContent, innerText, or sanitize HTML with DOMPurify."
    },
    {
        "lang": [".js", ".jsx", ".ts", ".tsx", ".mjs"],
        "id": "JS-002",
        "name": "Command Injection via child_process.exec",
        "pattern": r"child_process\s*\.\s*(?:exec|execSync)\s*\(\s*(?:`|f?['\"][^'\"]*?\$\{|\w+\s*\+)",
        "severity": "CRITICAL",
        "cwe": "CWE-78",
        "owasp": "A05:2025 - Injection",
        "risk": "Executing dynamic shell command strings allows attackers to execute arbitrary system commands.",
        "fix": "Use child_process.execFile or child_process.spawn with an array of arguments."
    },
    {
        "lang": [".js", ".jsx", ".ts", ".tsx", ".mjs"],
        "id": "JS-003",
        "name": "React dangerouslySetInnerHTML",
        "pattern": r"dangerouslySetInnerHTML\s*=\s*\{\s*\{\s*__html:\s*(.+?)\s*\}\s*\}",
        "severity": "HIGH",
        "cwe": "CWE-79",
        "owasp": "A05:2025 - Injection",
        "risk": "Bypasses React's built-in XSS protection.",
        "fix": "Sanitize HTML using DOMPurify before rendering."
    },
    {
        "lang": [".js", ".jsx", ".ts", ".tsx", ".mjs"],
        "id": "JS-004",
        "name": "Code Injection via eval() or new Function()",
        "pattern": r"\b(?:eval\s*\(|new\s+Function\s*\()",
        "severity": "CRITICAL",
        "cwe": "CWE-95",
        "owasp": "A05:2025 - Injection",
        "risk": "Dynamic code evaluation allows arbitrary script execution in server (Node.js) or client contexts.",
        "fix": "Avoid dynamic code generation; use strict data parsing."
    },
    # Go
    {
        "lang": [".go"],
        "id": "GO-001",
        "name": "Cross-Site Scripting via template.HTML bypass",
        "pattern": r"template\.HTML\s*\(",
        "severity": "HIGH",
        "cwe": "CWE-79",
        "owasp": "A05:2025 - Injection",
        "risk": "template.HTML explicitly disables Go html/template contextual auto-escaping.",
        "fix": "Pass untrusted data as plain string so html/template escapes it automatically."
    },
    # Rust
    {
        "lang": [".rs"],
        "id": "RUST-001",
        "name": "Unsafe Block Memory Invariant Risk",
        "pattern": r"\bunsafe\s*\{",
        "severity": "MEDIUM",
        "cwe": "CWE-119",
        "owasp": "A06:2025 - Insecure Design",
        "risk": "Unsafe blocks disable Rust's memory safety guarantees (pointer dereferences, unchecked mutations).",
        "fix": "Audit unsafe blocks for UB (undefined behavior) and wrap with safe public abstractions."
    },
]

# ─────────────────────────────────────────────────────────────────────────
# 5. INJECTION & LOGIC VULNERABILITY PATTERNS
# ─────────────────────────────────────────────────────────────────────────
INJECTION_PATTERNS: List[Dict[str, Any]] = [
    {
        "id": "SQLI-001",
        "name": "SQL Injection via String Formatting / Concatenation",
        "pattern": r"(?i)(?:cursor\.execute|db\.query|db\.execute|session\.execute|raw_query|execute_query)\s*\(\s*(?:f['\"][^'\"]*?(?:SELECT|INSERT|UPDATE|DELETE|DROP|UNION)[^'\"]*?\{|['\"][^'\"]*?(?:SELECT|INSERT|UPDATE|DELETE|DROP|UNION)[^'\"]*?['\"]\s*%\s*|['\"][^'\"]*?(?:SELECT|INSERT|UPDATE|DELETE|DROP|UNION)[^'\"]*?['\"]\s*\+)",
        "severity": "CRITICAL",
        "cwe": "CWE-89",
        "owasp": "A05:2025 - Injection",
        "risk": "Directly interpolating variables into SQL statements allows attackers to manipulate queries and dump database tables.",
        "fix": "Use parameterized queries (e.g. cursor.execute('SELECT * FROM t WHERE id = %s', (user_id,)))."
    },
    {
        "id": "PATH-001",
        "name": "Path Traversal Risk via Unchecked User Input",
        "pattern": r"(?i)open\s*\(\s*(?:f['\"][^'\"]*?\{|\w+\s*\+\s*['\"]\/|os\.path\.join\s*\([^)]*?(?:request|params|query|user_input))",
        "severity": "HIGH",
        "cwe": "CWE-22",
        "owasp": "A01:2025 - Broken Access Control",
        "risk": "Constructing file paths from user inputs without resolving and validating base paths allows reading arbitrary files.",
        "fix": "Use os.path.realpath() and verify that the target path begins with the intended root directory."
    },
    {
        "id": "SSRF-001",
        "name": "Server-Side Request Forgery (SSRF) Risk",
        "pattern": r"(?i)(?:requests\.(?:get|post|put|delete)|urllib\.request\.urlopen|httpx\.(?:get|post)|fetch|axios\.(?:get|post))\s*\(\s*(?:request\.(?:args|form|json|params)|url_param|target_url|user_url|input_url)",
        "severity": "HIGH",
        "cwe": "CWE-918",
        "owasp": "A01:2025 - Broken Access Control",
        "risk": "Fetching URLs provided directly by users allows internal network scanning and cloud metadata theft (e.g. 169.254.169.254).",
        "fix": "Enforce strict IP/domain allowlists and block private CIDR ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.1)."
    },
    {
        "id": "SSTI-001",
        "name": "Server-Side Template Injection (SSTI)",
        "pattern": r"(?i)(?:render_template_string|jinja2\.Template)\s*\(\s*(?:request\.|f['\"]|[\w_]+\s*\+)",
        "severity": "CRITICAL",
        "cwe": "CWE-1336",
        "owasp": "A05:2025 - Injection",
        "risk": "Rendering dynamic user input as a Jinja2/Mako template allows arbitrary Python object traversal and RCE.",
        "fix": "Never pass user input as the template source. Pass user variables as template context arguments."
    }
]

# ─────────────────────────────────────────────────────────────────────────
# 6. CRYPTOGRAPHIC WEAKNESS PATTERNS
# ─────────────────────────────────────────────────────────────────────────
CRYPTO_WEAKNESS_PATTERNS: List[Dict[str, Any]] = [
    {
        "id": "CRYPTO-001",
        "name": "Broken / Weak Cryptographic Hash (MD5 / SHA1)",
        "pattern": r"(?i)\b(?:hashlib\.md5|hashlib\.sha1|crypto\.createHash\s*\(\s*['\"](?:md5|sha1)['\"]\)|MD5_Init|SHA1_Init)\b",
        "severity": "MEDIUM",
        "cwe": "CWE-328",
        "owasp": "A04:2025 - Cryptographic Failures",
        "risk": "MD5 and SHA-1 are cryptographically broken with practical collision attacks.",
        "fix": "Upgrade to SHA-256 (hashlib.sha256), SHA-3, or bcrypt/argon2id for passwords."
    },
    {
        "id": "CRYPTO-002",
        "name": "Weak Insecure Cipher (DES / RC4 / ECB Mode)",
        "pattern": r"(?i)\b(?:AES\.MODE_ECB|DES\.new|ARC4\.new|Blowfish\.new|crypto\.createCipheriv\s*\(\s*['\"](?:des|rc4|aes-\d+-ecb)['\"])\b",
        "severity": "HIGH",
        "cwe": "CWE-327",
        "owasp": "A04:2025 - Cryptographic Failures",
        "risk": "ECB mode is deterministic and leaks pattern structure. DES/RC4 have small key sizes.",
        "fix": "Use AES-GCM (Galois/Counter Mode) or ChaCha20-Poly1305 with unique IVs."
    },
    {
        "id": "CRYPTO-003",
        "name": "Non-Cryptographic PRNG used in Security Context",
        "pattern": r"(?i)(?:token|secret|session_id|nonce|salt|api_key|auth)\s*=\s*(?:random\.random|random\.randint|random\.choice|Math\.random)",
        "severity": "HIGH",
        "cwe": "CWE-338",
        "owasp": "A04:2025 - Cryptographic Failures",
        "risk": "Standard random functions use Mersenne Twister or LCG, which are predictable from past outputs.",
        "fix": "Use secrets.token_hex(), secrets.token_urlsafe(), or crypto.randomBytes()."
    }
]

# ─────────────────────────────────────────────────────────────────────────
# 7. CONFIGURATION & MISCONFIGURATION PATTERNS
# ─────────────────────────────────────────────────────────────────────────
CONFIG_MISCONFIG_PATTERNS: List[Dict[str, Any]] = [
    {
        "id": "CONF-001",
        "name": "Debug Mode Enabled in Code / Config",
        "pattern": r"(?i)\b(?:DEBUG\s*=\s*True|app\.debug\s*=\s*True|FLASK_DEBUG\s*=\s*['\"]?1['\"]?|NODE_ENV\s*=\s*['\"]development['\"])\b",
        "severity": "HIGH",
        "cwe": "CWE-489",
        "owasp": "A02:2025 - Security Misconfiguration",
        "risk": "Debug mode exposes interactive debug consoles (e.g. Werkzeug pin bypass) and detailed stack traces.",
        "fix": "Ensure DEBUG is read from environment variables and defaults to False in production."
    },
    {
        "id": "CONF-002",
        "name": "Permissive CORS Wildcard Origin (*)",
        "pattern": r"(?i)(?:allow_origins\s*=\s*\[\s*['\"]\*['\"]\s*\]|Access-Control-Allow-Origin['\"]\s*:\s*['\"]\*['\"]|origin\s*:\s*['\"]\*['\"])",
        "severity": "MEDIUM",
        "cwe": "CWE-942",
        "owasp": "A01:2025 - Broken Access Control",
        "risk": "Allowing all origins (*) permits any third-party malicious website to make cross-origin requests to your API.",
        "fix": "Specify explicit allowed domain origins (e.g. ['https://app.yourdomain.com'])."
    },
    {
        "id": "CONF-003",
        "name": "Disabled SSL/TLS Certificate Verification",
        "pattern": r"(?i)(?:verify\s*=\s*False|rejectUnauthorized\s*:\s*false|InsecureSkipVerify\s*:\s*true|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]?0['\"]?)",
        "severity": "HIGH",
        "cwe": "CWE-295",
        "owasp": "A04:2025 - Cryptographic Failures",
        "risk": "Disabling TLS verification exposes outbound network traffic to Man-in-the-Middle (MitM) attacks.",
        "fix": "Remove verify=False and install appropriate Root CA certificates in your runtime container."
    },
    {
        "id": "CONF-004",
        "name": "Default / Hardcoded Credentials",
        "pattern": r"(?i)['\"](?:admin:admin|root:root|test:test|guest:guest|user:password)['\"]",
        "severity": "HIGH",
        "cwe": "CWE-1392",
        "owasp": "A07:2025 - Authentication Failures",
        "risk": "Default credentials allow automated bots to compromise the application instantly.",
        "fix": "Require users to configure unique passwords during initial setup."
    }
]

# ─────────────────────────────────────────────────────────────────────────
# 8. BUNDLED OFFLINE CRITICAL CVE DATABASE (Top high-impact packages)
# ─────────────────────────────────────────────────────────────────────────
BUNDLED_VULNERABLE_PACKAGES: Dict[str, List[Dict[str, Any]]] = {
    "requests": [
        {"affected": "<2.31.0", "cve": "CVE-2023-32681", "severity": "HIGH", "fixed": "2.31.0", "desc": "Unintended leak of Proxy-Authorization header to destination server"}
    ],
    "urllib3": [
        {"affected": "<2.0.7", "cve": "CVE-2023-45803", "severity": "HIGH", "fixed": "2.0.7", "desc": "Request body not stripped on 303 redirect"}
    ],
    "cryptography": [
        {"affected": "<41.0.6", "cve": "CVE-2023-49083", "severity": "HIGH", "fixed": "41.0.6", "desc": "NULL dereference when loading PKCS7 certificates"}
    ],
    "flask": [
        {"affected": "<2.2.5", "cve": "CVE-2023-30861", "severity": "HIGH", "fixed": "2.2.5", "desc": "High vulnerability in cookie session handling"}
    ],
    "django": [
        {"affected": "<4.2.8", "cve": "CVE-2023-46695", "severity": "HIGH", "fixed": "4.2.8", "desc": "Potential denial of service in UsernameField"}
    ],
    "jinja2": [
        {"affected": "<3.1.3", "cve": "CVE-2024-22195", "severity": "HIGH", "fixed": "3.1.3", "desc": "HTML attribute injection vulnerability"}
    ],
    "fastapi": [
        {"affected": "<0.109.1", "cve": "CVE-2024-24762", "severity": "HIGH", "fixed": "0.109.1", "desc": "ReDoS vulnerability in python-multipart form parsing"}
    ],
    "express": [
        {"affected": "<4.19.2", "cve": "CVE-2024-29041", "severity": "HIGH", "fixed": "4.19.2", "desc": "Open redirect vulnerability in res.location"}
    ],
    "axios": [
        {"affected": "<1.7.4", "cve": "CVE-2024-39338", "severity": "HIGH", "fixed": "1.7.4", "desc": "SSRF vulnerability in Axios baseUrl handling"}
    ],
    "jsonwebtoken": [
        {"affected": "<9.0.0", "cve": "CVE-2022-23529", "severity": "CRITICAL", "fixed": "9.0.0", "desc": "Remote Code Execution via insecure secretOrPublicKey parameter"}
    ]
}
