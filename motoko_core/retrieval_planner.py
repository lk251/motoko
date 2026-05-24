"""Skill-aware retrieval planning for Motoko.

The planner produces inspectable intent records before source retrieval runs.
It does not read private files, execute scripts, or call models.
"""

from __future__ import annotations

from motoko_core.retrieval import (
    query_date_mentions,
    query_path_mentions,
    query_requested_recent_section_count,
)
from motoko_core.skills import (
    BUILTIN_SKILLS,
    ORG_TEMPORAL_HANDLER,
    ORG_TEMPORAL_SKILL,
)


RETRIEVAL_PLAN_SCHEMA = "motoko-retrieval-plan-v1"


def _skill_catalog(skills: list[dict] | None = None) -> dict[str, dict]:
    rows = skills if skills is not None else BUILTIN_SKILLS
    catalog = {}
    for row in rows:
        slug = str(row.get("slug") or row.get("name") or "").strip()
        if slug:
            catalog[slug] = dict(row)
    return catalog


def build_retrieval_plan(query: str, *, skills: list[dict] | None = None) -> dict:
    """Return an inspectable plan for retrieval-time skill effects.

    This first planner intentionally recognizes only deterministic built-in
    retrieval handlers. Learned prompt-only skills remain final-prompt context
    until they declare safe handler metadata in a later Motoko version.
    """

    query = str(query or "")
    path_mentions = query_path_mentions(query)
    exact_dates = query_date_mentions(query)
    recent_count = query_requested_recent_section_count(query)
    plan = {
        "schema": RETRIEVAL_PLAN_SCHEMA,
        "kind": "retrieval-plan",
        "status": "default",
        "query_features": {
            "path_mentions": path_mentions,
            "exact_dates": exact_dates,
            "recent_section_count": recent_count,
        },
        "activated_skills": [],
        "handlers": [],
        "warnings": [],
    }
    catalog = _skill_catalog(skills)
    temporal_skill = catalog.get(ORG_TEMPORAL_SKILL)
    if recent_count and path_mentions and temporal_skill:
        activation = {
            "name": temporal_skill.get("name", ORG_TEMPORAL_SKILL),
            "slug": temporal_skill.get("slug", ORG_TEMPORAL_SKILL),
            "kind": temporal_skill.get("kind", "retrieval"),
            "handler": temporal_skill.get("handler", ORG_TEMPORAL_HANDLER),
            "allowed_effects": temporal_skill.get("allowed_effects", []),
            "reason": "query asks for latest/recent dated entries present in an explicitly named source",
        }
        plan["status"] = "active"
        plan["activated_skills"].append(activation)
        plan["handlers"].append(activation["handler"])
        plan["temporal"] = {
            "mode": "latest_present_in_named_source",
            "requested_count": recent_count,
            "path_mentions": path_mentions,
            "handler": activation["handler"],
        }
    return plan


def plan_has_handler(plan: dict, handler: str) -> bool:
    return handler in set(plan.get("handlers") or [])


def retrieval_plan_source(plan: dict) -> dict | None:
    if not plan or not plan.get("activated_skills"):
        return None
    return {
        "kind": "retrieval-plan",
        "schema": plan.get("schema", RETRIEVAL_PLAN_SCHEMA),
        "status": plan.get("status", "unknown"),
        "activated_skills": [
            row.get("slug") or row.get("name", "")
            for row in plan.get("activated_skills", [])
            if row.get("slug") or row.get("name")
        ],
        "handlers": [handler for handler in plan.get("handlers", []) if handler],
        "temporal": plan.get("temporal", {}),
        "warnings": plan.get("warnings", [])[:8],
    }
