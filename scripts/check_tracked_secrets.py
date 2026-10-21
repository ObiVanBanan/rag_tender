#!/usr/bin/env python3
"""Check Git-tracked files for common active credential formats.

Run: python scripts/check_tracked_secrets.py
This is a defensive preflight, NOT comprehensive Git-history/secret scanning.
Never print matched secrets, only path:line and finding type.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024
RAW_TOKENS = (
    ("OpenAI/DeepSeek-compatible key", re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("Google API key", re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("GitLab token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    ("Stripe live key", re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
)
ENV_SECRET = re.compile(
    r"^\s*(?:OPENAI_API_KEY|DEEPSEEK_API_KEY|ANTHROPIC_API_KEY|"
    r"GITHUB_TOKEN|GH_TOKEN|BRAVE_API_KEY|WEB_SEARCH_API_KEY|"
    r"POSTGRES_PASSWORD|PUBLIC_DEMO_PASSWORD|PUBLIC_DEMO_ADMIN_PASSWORD|"
    r"DATABASE_URL|AWS_SECRET_ACCESS_KEY|HF_TOKEN)\s*=\s*(\S.*)?$"
)
UNSAFE_DEFAULT_PASSWORD = re.compile(r"\$\{POSTGRES_PASSWORD:-[^}]*\}")
UNSAFE_DEFAULT_DSN = re.compile(r'database_url:\s*str\s*=\s*["\'](?:postgres(?:ql)?://)[^"\']+["\']')


def scan_content(path: str, content: str) -> list[tuple[int, str]]:
    """Return only categories, never matching secret values."""
    findings = []
    for n, line in enumerate(content.splitlines(), 1):
        for label, pattern in RAW_TOKENS:
            if pattern.search(line):
                findings.append((n, label))
        if path in {".env.example", ".env.sample"}:
            m = ENV_SECRET.match(line)
            if m and (m.group(1) or "").strip() not in {"", "''", '""'}:
                findings.append((n, "nonempty secret in example environment"))
        if (path.startswith("docker-compose") and path.endswith((".yml", ".yaml"))
                and UNSAFE_DEFAULT_PASSWORD.search(line)):
            findings.append((n, "insecure default PostgreSQL password"))
        if path == "src/nomenclature_matcher/settings.py" and UNSAFE_DEFAULT_DSN.search(line):
            findings.append((n, "embedded database credential in Settings default"))
    return findings


def tracked_files() -> list[Path]:
    proc = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True)
    return [Path(p.decode("utf-8", "surrogateescape"))
            for p in proc.stdout.split(b"\0") if p]


def main() -> int:
    files = tracked_files()
    problems = []
    skipped = []
    prohibited = {
        ".env", ".env.local", ".env.production", ".env.development",
        "credentials.json", "service-account.json", ".npmrc", ".pypirc",
        ".netrc",
    }
    for path in files:
        name = path.as_posix()
        if path.name in prohibited or path.suffix.lower() in {
            ".pem", ".p12", ".pfx", ".key", ".kdbx",
        }:
            problems.append((name, 0, "tracked private config/key file"))
            continue
        try:
            size = path.stat().st_size
            if size > MAX_BYTES:
                skipped.append(name)
                continue
            contents = path.read_bytes()
            if b"\0" in contents:
                skipped.append(name)
                continue
            text = contents.decode("utf-8")
        except (OSError, UnicodeError):
            skipped.append(name)
            continue
        for line, label in scan_content(name, text):
            problems.append((name, line, label))
    for name, line, label in problems:
        print(f"SECRET_SCAN: {name}:{line} [{label}]; value hidden")
    if problems:
        print(f"FAIL: {len(problems)} potential secret exposure(s) in tracked files.")
        return 1
    print(f"PASS: scanned {len(files) - len(skipped)} tracked text files; "
          f"skipped {len(skipped)} binary/large/unreadable files.")
    if skipped:
        print("NOTE: scan skipped large/binary files; use gitleaks for full history.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
