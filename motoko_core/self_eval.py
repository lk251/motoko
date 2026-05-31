"""Deterministic self-improvement checks for Motoko.

These checks are intentionally model-free. They verify that Motoko can inspect
her own source, activate the built-in self-code skill, and review skill/script
packages before a model is asked to synthesize a refactor plan.
"""

from __future__ import annotations

import datetime as _dt
import pathlib

from motoko_core.code_intel import build_code_map, find_motoko_repo_root, query_code_map
from motoko_core.retrieval_planner import build_retrieval_plan
from motoko_core.skill_scanner import scan_skill_package
from motoko_core.skills import (
    BUILTIN_SKILLS,
    MOTOKO_AGENTIC_BOUNDARY_SKILL,
    MOTOKO_CODEBASE_SKILL,
    MOTOKO_REFACTOR_CRAFT_SKILL,
    MOTOKO_RETRIEVAL_MAINTAINER_SKILL,
    rank_skill_rows,
)


SELF_EVAL_SCHEMA = "motoko-self-improvement-eval-v1"

SELF_IMPROVEMENT_UMBRELLA_SKILLS = {
    MOTOKO_CODEBASE_SKILL: "How should Motoko refactor its codebase command handlers?",
    MOTOKO_RETRIEVAL_MAINTAINER_SKILL: "diagnose retrieval failure with weak sources and wrong span selection",
    MOTOKO_REFACTOR_CRAFT_SKILL: "careful service boundary refactor with validation and craftsmanship",
    MOTOKO_AGENTIC_BOUNDARY_SKILL: "review skill tool action goal loop authority and approvals",
}


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _check(name: str, passed: bool, detail: str, *, required: bool = True, evidence: dict | None = None) -> dict:
    return {
        "name": name,
        "status": "pass" if passed else "fail",
        "required": bool(required),
        "detail": detail,
        "evidence": evidence or {},
    }


def _skill_catalog(skills: list[dict] | None = None) -> dict[str, dict]:
    rows = skills if skills is not None else BUILTIN_SKILLS
    catalog = {}
    for row in rows:
        slug = str(row.get("slug") or row.get("name") or "").strip()
        if slug:
            catalog[slug] = row
    return catalog


def run_self_improvement_eval(root: str | pathlib.Path | None = None, *, skills: list[dict] | None = None) -> dict:
    """Return a deterministic readiness report for Motoko self-improvement."""

    repo_root = find_motoko_repo_root(root)
    code_map = build_code_map(repo_root)
    summary = code_map.get("summary") if isinstance(code_map.get("summary"), dict) else {}
    checks: list[dict] = []

    checks.append(
        _check(
            "code_map_schema",
            code_map.get("schema") == "motoko-code-intel-v1",
            f"schema={code_map.get('schema', '')}",
            evidence={"root": code_map.get("root", "")},
        )
    )
    parse_errors = code_map.get("parse_errors", [])
    checks.append(
        _check(
            "code_map_parse_errors",
            not parse_errors,
            f"parse_errors={len(parse_errors)}",
            evidence={"parse_errors": parse_errors[:3]},
        )
    )
    checks.append(
        _check(
            "code_map_root_facade_present",
            int(summary.get("root_script_lines", 0) or 0) > 0,
            f"root_script_lines={summary.get('root_script_lines', 0)}",
            evidence={"largest_files": summary.get("largest_files", [])[:3]},
        )
    )
    checks.append(
        _check(
            "code_map_command_surface",
            int(summary.get("commands", 0) or 0) >= 20 and int(summary.get("command_handlers", 0) or 0) >= 10,
            f"commands={summary.get('commands', 0)} handlers={summary.get('command_handlers', 0)}",
            evidence={"commands": summary.get("commands", 0), "handlers": summary.get("command_handlers", 0)},
        )
    )

    code_query = query_code_map(code_map, "Motoko skill plan command implementation tests", limit=8)
    checks.append(
        _check(
            "code_query_finds_commands_symbols_tests",
            bool(code_query.get("commands")) and bool(code_query.get("symbols")) and bool(code_query.get("tests")),
            (
                f"commands={len(code_query.get('commands', []))} "
                f"symbols={len(code_query.get('symbols', []))} "
                f"tests={len(code_query.get('tests', []))}"
            ),
            evidence={
                "top_command": (code_query.get("commands") or [{}])[0].get("command", ""),
                "top_symbol": (code_query.get("symbols") or [{}])[0].get("qualname", ""),
                "top_test": (code_query.get("tests") or [{}])[0].get("name", ""),
            },
        )
    )

    catalog = _skill_catalog(skills)
    code_skill = catalog.get(MOTOKO_CODEBASE_SKILL)
    checks.append(
        _check(
            "motoko_codebase_skill_present",
            bool(code_skill),
            f"skill={MOTOKO_CODEBASE_SKILL if code_skill else 'missing'}",
            evidence={"known_builtin_skills": sorted(_skill_catalog(BUILTIN_SKILLS))},
        )
    )
    missing_umbrella = [slug for slug in SELF_IMPROVEMENT_UMBRELLA_SKILLS if slug not in catalog]
    checks.append(
        _check(
            "self_improvement_umbrella_skills_present",
            not missing_umbrella,
            f"missing={','.join(missing_umbrella) or '-'}",
            evidence={
                "required": sorted(SELF_IMPROVEMENT_UMBRELLA_SKILLS),
                "known_builtin_skills": sorted(_skill_catalog(BUILTIN_SKILLS)),
            },
        )
    )
    selected = {}
    missing_selection = []
    skill_rows = list(catalog.values()) if catalog else BUILTIN_SKILLS
    for slug, query in SELF_IMPROVEMENT_UMBRELLA_SKILLS.items():
        ranked = rank_skill_rows(skill_rows, query, limit=4)
        selected[slug] = [row.get("slug", "") for row in ranked]
        if slug not in selected[slug]:
            missing_selection.append(slug)
    checks.append(
        _check(
            "self_improvement_umbrella_skills_select",
            not missing_selection,
            f"missing_selection={','.join(missing_selection) or '-'}",
            evidence={"selected": selected},
        )
    )
    plan = build_retrieval_plan(
        "How should Motoko refactor its codebase command handlers?",
        skills=list(catalog.values()) if catalog else BUILTIN_SKILLS,
    )
    checks.append(
        _check(
            "motoko_codebase_skill_activates",
            "builtin:motoko_codebase_query" in set(plan.get("handlers") or []),
            f"handlers={', '.join(plan.get('handlers') or []) or '-'}",
            evidence={"activated_skills": [row.get("slug", "") for row in plan.get("activated_skills", [])]},
        )
    )

    builtin_scans = [scan_skill_package(row) for row in BUILTIN_SKILLS]
    builtin_bad = [
        scan
        for scan in builtin_scans
        if int(scan.get("severity_counts", {}).get("block", 0) or 0) or int(scan.get("severity_counts", {}).get("warn", 0) or 0)
    ]
    checks.append(
        _check(
            "builtin_skill_scan_clean",
            not builtin_bad,
            f"review_findings={len(builtin_bad)}",
            evidence={"skills": [scan.get("skill", "") for scan in builtin_scans]},
        )
    )

    risky_skill = {
        "name": "synthetic-risky-skill",
        "slug": "synthetic-risky-skill",
        "body": "Use scripts/risky.py only after review.",
        "support_files": ["scripts/risky.py"],
    }

    def read_risky(file_path: str) -> str:
        return "import subprocess\nsubprocess.run(['true'])\n" if file_path == "scripts/risky.py" else ""

    risky_scan = scan_skill_package(risky_skill, read_file=read_risky)
    risky_rules = {row.get("rule", "") for row in risky_scan.get("findings", [])}
    checks.append(
        _check(
            "skill_scanner_detects_risky_script",
            risky_scan.get("status") == "review" and {"subprocess_import", "subprocess_call"} <= risky_rules,
            f"status={risky_scan.get('status', '')} rules={','.join(sorted(risky_rules))}",
            evidence={"severity_counts": risky_scan.get("severity_counts", {})},
        )
    )

    docs = [
        repo_root / "docs" / "project-context.md",
        repo_root / "docs" / "motoko.md",
        repo_root / "docs" / "agentic-capability-design.md",
        repo_root / "docs" / "motoko-self-improvement-playbook.md",
    ]
    missing_docs = [path.name for path in docs if not path.exists()]
    checks.append(
        _check(
            "self_improvement_docs_present",
            not missing_docs,
            f"missing={','.join(missing_docs) or '-'}",
            evidence={"docs": [path.relative_to(repo_root).as_posix() for path in docs if path.exists()]},
        )
    )

    failed_required = [row for row in checks if row.get("required") and row.get("status") != "pass"]
    status = "pass" if not failed_required else "fail"
    return {
        "schema": SELF_EVAL_SCHEMA,
        "created_at": _utc_now(),
        "status": status,
        "root": str(repo_root),
        "checks": checks,
        "summary": {
            "passed": sum(1 for row in checks if row.get("status") == "pass"),
            "failed": sum(1 for row in checks if row.get("status") != "pass"),
            "required_failed": len(failed_required),
        },
    }


def format_self_improvement_eval(report: dict) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        f"self-improvement eval: {report.get('schema', SELF_EVAL_SCHEMA)}",
        f"status: {report.get('status', '')}",
        f"created: {report.get('created_at', '')}",
        f"root: {report.get('root', '')}",
        f"checks: {summary.get('passed', 0)} passed, {summary.get('failed', 0)} failed",
    ]
    for row in report.get("checks", []):
        marker = "pass" if row.get("status") == "pass" else "fail"
        required = "required" if row.get("required") else "optional"
        lines.append(f"- {marker}: {row.get('name', '')} ({required}) - {row.get('detail', '')}")
    if report.get("status") == "pass":
        lines.append("next: use motoko code-query before Motoko refactor work and motoko skill scan before trusting script-backed skills")
    else:
        lines.append("next: fix failed required checks before relying on Motoko self-improvement context")
    return "\n".join(lines)
