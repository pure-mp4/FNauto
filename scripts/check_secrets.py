from __future__ import annotations

import argparse
import re
from pathlib import Path

TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".bat", ".spec", ".toml", ".yml", ".yaml"}
SKIP_DIRS = {".git", ".venv", "__pycache__", "build", "dist", "_qa"}
PATTERNS = (
    ("discord bot token", re.compile(r"\b[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "Discord webhook",
        re.compile(r"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9._-]+"),
    ),
    (
        "assigned secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|password|passwd|access[_-]?token|bot[_-]?token)"
            r'\s*[:=]\s*[\'"][^\'"]{8,}[\'"]'
        ),
    ),
)
PLACEHOLDERS = (
    "unit-test-token",
    "qa-token",
    "123456789012345678",
    "abcdef",
    "your_webhook",
    "your-webhook",
    "example",
    "<",
)


def _is_placeholder(line: str) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in PLACEHOLDERS) or "..." in line


def scan(root: Path) -> list[tuple[str, int, str]]:
    findings = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        for number, line in enumerate(lines, 1):
            if _is_placeholder(line):
                continue
            for name, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append((str(path.relative_to(root)), number, name))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    findings = scan(root)
    for path, number, name in findings:
        print(f"{path}:{number}: possible {name}")
    if findings:
        print(f"{len(findings)} possible secret(s) found")
        return 1
    print("No secrets found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
