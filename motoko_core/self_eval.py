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
    traces = code_map.get("command_traces", []) if isinstance(code_map.get("command_traces"), list) else []
    source_lifecycle_trace = next((row for row in traces if row.get("command") == "source-lifecycle"), {})
    checks.append(
        _check(
            "code_map_command_traces_link_tests",
            bool(source_lifecycle_trace.get("handler_found")) and bool(source_lifecycle_trace.get("tests")),
            (
                f"traces={summary.get('command_traces', 0)} "
                f"traced_tests={summary.get('command_traces_with_tests', 0)}"
            ),
            evidence={
                "source_lifecycle_handler": source_lifecycle_trace.get("handler", ""),
                "source_lifecycle_tests": [
                    row.get("name", "") for row in source_lifecycle_trace.get("tests", [])[:3]
                ],
            },
        )
    )
    checks.append(
        _check(
            "code_map_relationships_present",
            int(summary.get("resolved_call_edges", 0) or 0) > 0
            and int(summary.get("service_boundaries", 0) or 0) > 0
            and bool(summary.get("root_hotspots")),
            (
                f"edges={summary.get('resolved_call_edges', 0)} "
                f"services={summary.get('service_boundaries', 0)} "
                f"hotspots={len(summary.get('root_hotspots', []) or [])}"
            ),
            evidence={
                "top_hotspot": (summary.get("root_hotspots") or [{}])[0].get("qualname", ""),
                "top_service": (code_map.get("service_boundaries") or [{}])[0].get("path", ""),
            },
        )
    )
    constants = code_map.get("constants", []) if isinstance(code_map.get("constants"), list) else []
    schema_constants = [row for row in constants if row.get("category") == "schema"]
    checks.append(
        _check(
            "code_map_schema_constants_present",
            bool(schema_constants),
            f"constants={len(constants)} schema_constants={len(schema_constants)}",
            evidence={"schema_constants": [row.get("name", "") for row in schema_constants[:8]]},
        )
    )
    validation_gates = code_map.get("validation_gates", []) if isinstance(code_map.get("validation_gates"), list) else []
    validation_gate_names = {str(row.get("name", "")) for row in validation_gates if isinstance(row, dict)}
    checks.append(
        _check(
            "code_map_validation_gates_present",
            {"regression", "self-eval", "action-eval", "nix-flake"} <= validation_gate_names,
            f"validation_gates={len(validation_gates)}",
            evidence={"validation_gates": sorted(validation_gate_names)},
        )
    )
    cancellation_paths = code_map.get("cancellation_paths", []) if isinstance(code_map.get("cancellation_paths"), list) else []
    checks.append(
        _check(
            "code_map_cancellation_paths_present",
            bool(cancellation_paths),
            f"cancellation_paths={len(cancellation_paths)}",
            evidence={"top_path": (cancellation_paths or [{}])[0].get("qualname", "")},
        )
    )
    model_route_paths = code_map.get("model_route_paths", []) if isinstance(code_map.get("model_route_paths"), list) else []
    checks.append(
        _check(
            "code_map_model_route_paths_present",
            bool(model_route_paths),
            f"model_route_paths={len(model_route_paths)}",
            evidence={"top_path": (model_route_paths or [{}])[0].get("qualname", "")},
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
    schema_query = query_code_map(code_map, "source lifecycle schema artifact version migration", limit=8)
    checks.append(
        _check(
            "code_query_finds_schema_constants",
            bool(schema_query.get("constants")),
            f"constants={len(schema_query.get('constants', []))}",
            evidence={"top_constant": (schema_query.get("constants") or [{}])[0].get("name", "")},
        )
    )
    hotspot_query = query_code_map(code_map, "root facade hotspot extraction target", limit=8)
    checks.append(
        _check(
            "code_query_finds_root_hotspots",
            bool(hotspot_query.get("root_hotspots")),
            f"hotspots={len(hotspot_query.get('root_hotspots', []))}",
            evidence={"top_hotspot": (hotspot_query.get("root_hotspots") or [{}])[0].get("qualname", "")},
        )
    )
    lifecycle_query = query_code_map(code_map, "source lifecycle command handler tests", limit=8)
    checks.append(
        _check(
            "code_query_finds_traces_and_services",
            bool(lifecycle_query.get("command_traces")) and bool(lifecycle_query.get("service_boundaries")),
            (
                f"traces={len(lifecycle_query.get('command_traces', []))} "
                f"services={len(lifecycle_query.get('service_boundaries', []))}"
            ),
            evidence={
                "top_trace": (lifecycle_query.get("command_traces") or [{}])[0].get("command", ""),
                "top_service": (lifecycle_query.get("service_boundaries") or [{}])[0].get("path", ""),
            },
        )
    )
    cancellation_query = query_code_map(code_map, "foreground cancellation vector index cleanup interruption", limit=8)
    checks.append(
        _check(
            "code_query_finds_cancellation_paths",
            bool(cancellation_query.get("cancellation_paths")),
            f"cancellation_paths={len(cancellation_query.get('cancellation_paths', []))}",
            evidence={
                "top_path": (cancellation_query.get("cancellation_paths") or [{}])[0].get("qualname", ""),
                "helpers": (cancellation_query.get("cancellation_paths") or [{}])[0].get("helpers", []),
            },
        )
    )
    model_route_query = query_code_map(code_map, "model route local endpoint call_model open_model_response", limit=8)
    checks.append(
        _check(
            "code_query_finds_model_route_paths",
            bool(model_route_query.get("model_route_paths")),
            f"model_route_paths={len(model_route_query.get('model_route_paths', []))}",
            evidence={
                "top_path": (model_route_query.get("model_route_paths") or [{}])[0].get("qualname", ""),
                "helpers": (model_route_query.get("model_route_paths") or [{}])[0].get("helpers", []),
            },
        )
    )
    curator_query = query_code_map(code_map, "feedback eval curator skill suggestion tests", limit=16)
    curator_symbols = {
        str(row.get("qualname", ""))
        for row in curator_query.get("symbols", [])
        if isinstance(row, dict)
    }
    curator_tests = {
        str(row.get("name", ""))
        for row in curator_query.get("tests", [])
        if isinstance(row, dict)
    }
    checks.append(
        _check(
            "code_query_finds_feedback_eval_curator_path",
            "skill_curator_feedback_eval_matches" in curator_symbols
            and "test_skill_curator_uses_saved_feedback_eval_fixtures" in curator_tests,
            (
                f"symbols={len(curator_query.get('symbols', []))} "
                f"tests={len(curator_query.get('tests', []))}"
            ),
            evidence={
                "top_symbol": (curator_query.get("symbols") or [{}])[0].get("qualname", ""),
                "top_test": (curator_query.get("tests") or [{}])[0].get("name", ""),
                "tests": sorted(curator_tests)[:16],
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
