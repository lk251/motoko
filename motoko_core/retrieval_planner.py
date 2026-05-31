"""Skill-aware retrieval planning for Motoko.

The planner produces inspectable intent records before source retrieval runs.
It does not read private files, execute scripts, or call models.
"""

from __future__ import annotations

import re

from motoko_core.retrieval import (
    query_date_mentions,
    query_path_mentions,
    query_requested_recent_section_count,
)
from motoko_core.skills import (
    BUILTIN_SKILLS,
    ORG_STRUCTURAL_HANDLER,
    ORG_STRUCTURAL_SKILL,
    ORG_TEMPORAL_HANDLER,
    ORG_TEMPORAL_SKILL,
)


RETRIEVAL_PLAN_SCHEMA = "motoko-retrieval-plan-v1"

ORG_QUERY_TAG_STOPWORDS = {
    "tag",
    "tags",
    "tagged",
    "todo",
    "todos",
    "done",
    "task",
    "tasks",
    "heading",
    "headings",
    "element",
    "elements",
    "entry",
    "entries",
    "org",
    "orgmode",
    "org-mode",
    "with",
    "from",
    "that",
    "this",
    "all",
    "any",
    "the",
    "and",
}
ORG_TODO_STATES = {
    "TODO",
    "DONE",
    "NEXT",
    "WAITING",
    "WAIT",
    "HOLD",
    "CANCELLED",
    "CANCELED",
}


def _append_unique(rows: list[str], value: str) -> None:
    value = value.strip(" :#`'\".,;()[]{}").lower()
    if not value or value in ORG_QUERY_TAG_STOPWORDS:
        return
    if value not in rows:
        rows.append(value)


def query_org_tag_mentions(query: str) -> list[str]:
    text = str(query or "")
    rows: list[str] = []
    for pattern in [
        r":([A-Za-z0-9_@#%+-]+):",
        r"\btag\s*[:=]\s*#?:?([A-Za-z0-9_@#%+-]+)",
        r"\b(?:tagged|with\s+(?:the\s+)?tag|under\s+(?:the\s+)?tag)\s+#?:?([A-Za-z0-9_@#%+-]+)",
        r"\b(?:elements?|headings?|tasks?|entries?)\s+(?:with|tagged)\s+#?:?([A-Za-z0-9_@#%+-]+)",
    ]:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            _append_unique(rows, match.group(1))
    return rows[:8]


def query_org_todo_states(query: str) -> list[str]:
    text = str(query or "")
    rows = []
    for state in sorted(ORG_TODO_STATES):
        if re.search(rf"\b{re.escape(state)}\b", text, flags=re.IGNORECASE):
            rows.append("CANCELLED" if state == "CANCELED" else state)
    if re.search(r"\bto[- ]do(?:s)?\b", text, flags=re.IGNORECASE) and "TODO" not in rows:
        rows.append("TODO")
    return rows[:8]


def query_org_priorities(query: str) -> list[str]:
    text = str(query or "")
    rows = []
    for match in re.finditer(r"\[#([A-Za-z0-9])\]|\bpriority\s+([A-Za-z0-9])\b", text, flags=re.IGNORECASE):
        value = (match.group(1) or match.group(2) or "").upper()
        if value and value not in rows:
            rows.append(value)
    return rows[:8]


def query_wants_org_structural_context(query: str) -> bool:
    text = str(query or "").lower()
    if query_org_tag_mentions(query) or query_org_todo_states(query) or query_org_priorities(query):
        return True
    return bool(
        re.search(
            r"\borg(?:-mode|mode)?\b.*\b(headings?|entries|tasks?|deadlines?|scheduled|tags?)\b"
            r"|\b(headings?|entries)\b.*\borg(?:-mode|mode)?\b"
            r"|\b(deadlines?|scheduled)\b",
            text,
        )
    )


def query_org_structural_flags(query: str) -> dict:
    text = str(query or "").lower()
    return {
        "deadline": bool(re.search(r"\bdeadlines?\b", text)),
        "scheduled": bool(re.search(r"\bscheduled\b|\bschedule\b", text)),
        "heading": bool(re.search(r"\bheadings?\b|\belements?\b|\bentries\b", text)),
    }


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
            "org_tags": query_org_tag_mentions(query),
            "org_todo_states": query_org_todo_states(query),
            "org_priorities": query_org_priorities(query),
            "org_structural_flags": query_org_structural_flags(query),
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
    structural_skill = catalog.get(ORG_STRUCTURAL_SKILL)
    tags = query_org_tag_mentions(query)
    todo_states = query_org_todo_states(query)
    priorities = query_org_priorities(query)
    structural_flags = query_org_structural_flags(query)
    if structural_skill and query_wants_org_structural_context(query):
        activation = {
            "name": structural_skill.get("name", ORG_STRUCTURAL_SKILL),
            "slug": structural_skill.get("slug", ORG_STRUCTURAL_SKILL),
            "kind": structural_skill.get("kind", "retrieval"),
            "handler": structural_skill.get("handler", ORG_STRUCTURAL_HANDLER),
            "allowed_effects": structural_skill.get("allowed_effects", []),
            "reason": "query asks for deterministic Org structure, tag, TODO, priority, or date evidence",
        }
        plan["status"] = "active"
        plan["activated_skills"].append(activation)
        plan["handlers"].append(activation["handler"])
        plan["structural"] = {
            "mode": "org_structural_query",
            "tags": tags,
            "todo_states": todo_states,
            "priorities": priorities,
            "flags": structural_flags,
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
        "structural": plan.get("structural", {}),
        "warnings": plan.get("warnings", [])[:8],
    }
