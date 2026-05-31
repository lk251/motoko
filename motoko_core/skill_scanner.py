"""Static scanner for Motoko skill and script packages.

The scanner is deliberately conservative and report-first. It does not try to
prove that a script is safe. It surfaces risk signals that should be reviewed
before external skills, community skills, or broader script tools are trusted.
"""

from __future__ import annotations

import ast
import pathlib
import re


SKILL_SCAN_SCHEMA = "motoko-skill-scan-v1"


TEXT_PATTERNS = [
    ("block", "prompt_injection", re.compile(r"ignore (all )?(previous|above) instructions|system prompt|developer message", re.I)),
    ("block", "destructive_shell", re.compile(r"\brm\s+-rf\b|\bshutil\.rmtree\b|\.unlink\(", re.I)),
    ("warn", "network_reference", re.compile(r"\b(socket|urllib|httpx|requests|aiohttp|curl|wget)\b", re.I)),
    ("warn", "subprocess_reference", re.compile(r"\b(subprocess|os\.system|Popen|pty\.spawn)\b", re.I)),
    ("warn", "ambient_secret_reference", re.compile(r"\b(os\.environ|getenv|SSH_|TOKEN|API[_-]?KEY|PASSWORD|SECRET)\b", re.I)),
    ("warn", "broad_path_reference", re.compile(r"(/home/|/etc/|/var/|~\/|Path\.home\()", re.I)),
    ("info", "shell_snippet", re.compile(r"```(?:bash|sh|shell)|\bpython\s+-c\b", re.I)),
]

RISKY_IMPORTS = {
    "subprocess": "subprocess_import",
    "socket": "network_import",
    "urllib": "network_import",
    "http": "network_import",
    "requests": "network_import",
    "aiohttp": "network_import",
    "shutil": "filesystem_mutation_import",
    "pty": "terminal_import",
}
RISKY_CALLS = {
    "os.system": "subprocess_call",
    "subprocess.Popen": "subprocess_call",
    "subprocess.run": "subprocess_call",
    "subprocess.call": "subprocess_call",
    "shutil.rmtree": "destructive_call",
    "Path.home": "broad_path_call",
}


def _line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, int(offset))) + 1


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def scan_text(text: str, *, path: str, kind: str) -> list[dict]:
    findings = []
    for severity, rule, pattern in TEXT_PATTERNS:
        for match in pattern.finditer(text or ""):
            findings.append(
                {
                    "severity": severity,
                    "rule": rule,
                    "kind": kind,
                    "path": path,
                    "line": _line_for_offset(text, match.start()),
                    "message": f"{rule.replace('_', ' ')} signal",
                }
            )
    return findings


def scan_python_script(text: str, *, path: str) -> list[dict]:
    findings = scan_text(text, path=path, kind="script")
    try:
        tree = ast.parse(text or "", filename=path)
    except SyntaxError as exc:
        findings.append(
            {
                "severity": "block",
                "rule": "python_syntax_error",
                "kind": "script",
                "path": path,
                "line": getattr(exc, "lineno", 1) or 1,
                "message": str(exc),
            }
        )
        return findings
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in RISKY_IMPORTS:
                    findings.append(
                        {
                            "severity": "warn",
                            "rule": RISKY_IMPORTS[root],
                            "kind": "script",
                            "path": path,
                            "line": node.lineno,
                            "message": f"imports {alias.name}",
                        }
                    )
        elif isinstance(node, ast.ImportFrom):
            root = str(node.module or "").split(".", 1)[0]
            if root in RISKY_IMPORTS:
                findings.append(
                    {
                        "severity": "warn",
                        "rule": RISKY_IMPORTS[root],
                        "kind": "script",
                        "path": path,
                        "line": node.lineno,
                        "message": f"imports from {node.module}",
                    }
                )
        elif isinstance(node, ast.Call):
            call = _call_name(node.func)
            if call in RISKY_CALLS:
                findings.append(
                    {
                        "severity": "block" if "destructive" in RISKY_CALLS[call] else "warn",
                        "rule": RISKY_CALLS[call],
                        "kind": "script",
                        "path": path,
                        "line": getattr(node, "lineno", 1),
                        "message": f"calls {call}",
                    }
                )
    return findings


def _safe_support_path(root: pathlib.Path, path_text: str) -> pathlib.Path | None:
    try:
        candidate = (root / path_text).resolve()
        candidate.relative_to(root.resolve())
        return candidate
    except (OSError, ValueError):
        return None


def scan_skill_package(skill: dict, *, skill_root: pathlib.Path | None = None, read_file=None) -> dict:
    slug = str(skill.get("slug") or skill.get("name") or "")
    root = pathlib.Path(skill.get("path", "")).parent if skill_root is None and skill.get("path") else skill_root
    findings = scan_text(str(skill.get("body", "")), path=f"{slug}:SKILL.md", kind="skill")
    support_files = []
    for relpath in skill.get("support_files", []) or []:
        relpath = str(relpath or "").strip()
        if not relpath:
            continue
        support_files.append(relpath)
        content = ""
        if read_file is not None:
            try:
                content = str(read_file(relpath) or "")
            except Exception as exc:  # pragma: no cover - defensive external reader.
                findings.append(
                    {
                        "severity": "warn",
                        "rule": "support_file_read_failed",
                        "kind": "support",
                        "path": relpath,
                        "line": 1,
                        "message": str(exc),
                    }
                )
                continue
        elif root is not None:
            path = _safe_support_path(pathlib.Path(root), relpath)
            if path and path.exists() and path.is_file():
                content = path.read_text(encoding="utf-8", errors="replace")
        if relpath.startswith("scripts/") and relpath.endswith(".py"):
            findings.extend(scan_python_script(content, path=relpath))
        else:
            findings.extend(scan_text(content, path=relpath, kind="support"))
    severity_counts = {
        "block": sum(1 for row in findings if row.get("severity") == "block"),
        "warn": sum(1 for row in findings if row.get("severity") == "warn"),
        "info": sum(1 for row in findings if row.get("severity") == "info"),
    }
    status = "blocked" if severity_counts["block"] else ("review" if severity_counts["warn"] else "pass")
    return {
        "schema": SKILL_SCAN_SCHEMA,
        "skill": slug,
        "builtin": bool(skill.get("builtin")),
        "status": status,
        "support_files": support_files,
        "severity_counts": severity_counts,
        "findings": findings,
    }


def format_skill_scan_report(report: dict) -> str:
    counts = report.get("severity_counts") if isinstance(report.get("severity_counts"), dict) else {}
    lines = [
        f"skill scan: {report.get('skill', '')}",
        f"schema: {report.get('schema', '')}",
        f"status: {report.get('status', '')}",
        f"findings: block={counts.get('block', 0)} warn={counts.get('warn', 0)} info={counts.get('info', 0)}",
    ]
    if report.get("builtin"):
        lines.append("note: built-in skill; script execution is not used")
    if not report.get("findings"):
        lines.append("findings: none")
        return "\n".join(lines)
    for row in report.get("findings", [])[:40]:
        lines.append(
            f"- {row.get('severity', '')} {row.get('rule', '')} "
            f"{row.get('path', '')}:{row.get('line', '')} {row.get('message', '')}".rstrip()
        )
    return "\n".join(lines)
