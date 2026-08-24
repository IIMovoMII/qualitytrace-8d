from __future__ import annotations

import json
import re
from pathlib import Path


PATTERNS = (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), re.compile(r"(?i)(?:api[_-]?key|auth[_-]?token)\s*[=:]\s*['\"]?[A-Za-z0-9_-]{20,}"))


def audit(root: Path) -> dict:
    findings: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or ".venv" in path.parts or "__pycache__" in path.parts or path.name in {".env", ".env.local"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(pattern.search(text) for pattern in PATTERNS):
            findings.append(str(path.relative_to(root)))
    return {"clean": not findings, "findings": sorted(findings)}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(audit(root), ensure_ascii=False, indent=2))
