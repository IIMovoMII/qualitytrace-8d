from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


MAX_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int | None = None


PATTERNS = (
    ("疑似 OpenAI/中转格式密钥", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("疑似 Anthropic 格式密钥", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("疑似 GitHub Token", re.compile(r"\b(?:gh[opusr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("疑似 AWS Access Key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("疑似私有 Windows 绝对路径", re.compile(r"(?i)\b[A-Z]:[\\/](?:Users[\\/][^\\/\s]+|求职)(?:[\\/]|\b)")),
)
STATIC_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|token|secret|password|authorization|base[_-]?url)"
    r"\b\s*[:=]\s*([\"'])([^\"']{5,})\1"
)
SAFE_MARKERS = ("example", "placeholder", "dummy", "test-", "your-", "<", "${", "********")
DENIED_NAMES = {".env", "secrets.toml", "credentials.json", "default-profile.json"}
DENIED_SUFFIXES = {
    ".pem",
    ".p12",
    ".pfx",
    ".key",
    ".dpapi",
    ".har",
    ".trace",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".pyc",
    ".pyo",
}
DENIED_PARTS = {
    ".venv",
    ".git",
    "__pycache__",
    "archive",
    "artifacts",
    ".jinhua",
    ".codex",
    ".claude",
}


def run_git(*args: str) -> bytes:
    completed = subprocess.run(["git", *args], check=False, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError("无法读取 Git 候选；请确认仓库和索引状态。")
    return completed.stdout


def candidate_paths(mode: str) -> tuple[str, ...]:
    if mode == "tracked":
        raw = run_git("ls-files", "-z")
    else:
        raw = run_git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    return tuple(part.decode("utf-8") for part in raw.split(b"\0") if part)


def content_for(path: str, mode: str) -> bytes:
    if mode == "tracked":
        return Path(path).read_bytes()
    return run_git("show", f":{path}")


def safe_assignment(value: str) -> bool:
    normalized = value.strip().casefold()
    return not normalized or any(marker in normalized for marker in SAFE_MARKERS)


def audit(mode: str) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    for path in candidate_paths(mode):
        pure = PurePosixPath(path)
        lowered_parts = {part.casefold() for part in pure.parts}
        if lowered_parts & DENIED_PARTS:
            findings.append(Finding("禁止提交的本地目录", path))
        if pure.name.casefold() in DENIED_NAMES or (
            pure.name.casefold().startswith(".env.") and pure.name.casefold() != ".env.example"
        ):
            findings.append(Finding("禁止提交的凭据配置文件", path))
        if pure.suffix.casefold() in DENIED_SUFFIXES:
            findings.append(Finding("禁止提交的敏感文件类型", path))

        content = content_for(path, mode)
        if len(content) > MAX_BYTES:
            findings.append(Finding("单文件超过 5 MiB", path))
        if b"\0" in content:
            continue
        text = content.decode("utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for rule, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append(Finding(rule, path, line_number))
            for match in STATIC_ASSIGNMENT.finditer(line):
                if not safe_assignment(match.group(2)):
                    findings.append(Finding("疑似静态凭据或私有接口赋值", path, line_number))
    return tuple(findings)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("staged", "tracked"), default="staged")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        paths = candidate_paths(args.mode)
        findings = audit(args.mode)
    except (OSError, RuntimeError, UnicodeError) as error:
        print(f"公开候选审计未完成：{error}", file=sys.stderr)
        return 2
    if not paths:
        print("没有可审计文件。", file=sys.stderr)
        return 2
    if findings:
        print(f"公开候选审计失败：发现 {len(findings)} 个待处理项。")
        for finding in sorted(findings, key=lambda item: (item.path, item.line or 0, item.rule)):
            location = f"{finding.path}:{finding.line}" if finding.line else finding.path
            print(f"- [{finding.rule}] {location}")
        print("审计器不会显示命中的原文。")
        return 1
    print(f"公开候选审计通过：{len(paths)} 个文件，未发现凭据或越界工件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
