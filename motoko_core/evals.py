"""Evaluation helper logic for Motoko."""

from __future__ import annotations

import json
import re
import textwrap

from motoko_core.model_routes import (
    MODEL_ROUTE_INDEX_CHUNK,
    MODEL_ROUTE_INDEX_CORPUS,
    MODEL_ROUTE_INDEX_FILE,
    MODEL_ROUTE_INDEX_LABEL,
)


def worker_model_eval_fixtures() -> list[dict]:
    return [
        {
            "id": "org-priority-chunk",
            "route": MODEL_ROUTE_INDEX_CHUNK,
            "role": "chunk summary",
            "label": "synthetic-corpus/sample-planning.org chunk 1",
            "required_keys": [
                "summary",
                "title",
                "kind",
                "dates",
                "todos",
                "obligations",
                "files_or_paths_mentioned",
                "confidence",
                "escalation_needed",
            ],
            "required_facts": [
                {"name": "todo state", "any": ["TODO"]},
                {"name": "priority", "any": ["#A", "priority A", "A priority"]},
                {"name": "deadline", "any": ["2026-05-22", "May 22"]},
                {"name": "scheduled date", "any": ["2026-05-21", "May 21"]},
                {"name": "person", "any": ["Example Recipient", "Recipient"]},
                {"name": "obligation", "any": ["review packet", "sample packet"]},
                {"name": "path", "any": ["/workspace/synthetic-corpus/reference.org", "reference.org"]},
                {"name": "project", "any": ["fixture lantern"]},
            ],
            "forbidden_facts": [
                {"name": "wrong date", "any": ["2026-05-23"]},
                {"name": "invented person", "any": ["Marina"]},
                {"name": "invented record", "any": ["record TEST-019", "unrelated due date"]},
            ],
            "text": "\n".join(
                [
                    "* TODO [#A] Send review packet :sample:review:",
                    "SCHEDULED: <2026-05-21 Thu 09:00>",
                    "DEADLINE: <2026-05-22 Fri>",
                    "Project: fixture lantern",
                    "File reference: /workspace/synthetic-corpus/reference.org",
                    "Obligation: the user must send the review packet to Example Recipient before noon.",
                ]
            ),
            "max_output_chars": 2200,
            "min_fact_ratio": 0.82,
        },
        {
            "id": "file-purpose-map",
            "route": MODEL_ROUTE_INDEX_FILE,
            "role": "file summary",
            "label": "synthetic-corpus/sample-planning.org file summary",
            "required_keys": [
                "file_summary",
                "file_title",
                "file_role",
                "file_kind",
                "main_projects",
                "main_dates",
                "main_todos",
                "main_obligations",
                "confidence",
                "escalation_needed",
            ],
            "required_facts": [
                {"name": "file role", "any": ["planning", "task"]},
                {"name": "priority task", "any": ["Send review packet", "review packet"]},
                {"name": "deadline", "any": ["2026-05-22", "May 22"]},
                {"name": "project", "any": ["fixture lantern"]},
                {"name": "support task", "any": ["Draft sample note"]},
                {"name": "path", "any": ["/workspace/synthetic-corpus/sample-planning.org", "sample-planning.org"]},
            ],
            "forbidden_facts": [
                {"name": "wrong repo", "any": ["production-config"]},
                {"name": "wrong status", "any": ["DONE Send review packet"]},
            ],
            "text": "\n\n".join(
                [
                    "Path: /workspace/synthetic-corpus/sample-planning.org",
                    "Chunk 1 summary: TODO priority A Send review packet for project fixture lantern. "
                    "Deadline 2026-05-22. Obligation to contact Example Recipient before noon.",
                    "Chunk 2 summary: TODO priority B Draft sample note, scheduled 2026-05-23, "
                    "depends on the review packet being sent.",
                ]
            ),
            "max_output_chars": 2600,
            "min_fact_ratio": 0.82,
        },
        {
            "id": "document-label",
            "route": MODEL_ROUTE_INDEX_LABEL,
            "role": "classification label",
            "label": "synthetic-corpus/sample-intake.org label",
            "required_keys": [
                "label",
                "kind",
                "active",
                "task_bearing",
                "sensitive",
                "confidence",
                "escalation_needed",
            ],
            "required_facts": [
                {"name": "org kind", "any": ["org", "notes", "task"]},
                {"name": "task-bearing", "any": ["task_bearing", "task-bearing", "task bearing", "TODO"]},
                {"name": "active", "any": ["active"]},
                {"name": "review tag", "any": ["review"]},
                {"name": "sample tag", "any": ["sample"]},
            ],
            "forbidden_facts": [
                {"name": "archive", "any": ["archived"]},
                {"name": "code", "any": ["python", "javascript"]},
            ],
            "text": "\n".join(
                [
                    "Path: /workspace/synthetic-corpus/sample-intake.org",
                    "* TODO [#A] Review sample packet :sample:review:",
                    "DEADLINE: <2026-05-22 Fri>",
                    "Short note: active inbox item, current item.",
                ]
            ),
            "max_output_chars": 1400,
            "min_fact_ratio": 0.80,
        },
        {
            "id": "corpus-priority-synthesis",
            "route": MODEL_ROUTE_INDEX_CORPUS,
            "role": "corpus summary",
            "label": "synthetic corpus synthesis",
            "required_keys": [
                "corpus_summary",
                "active_projects",
                "priority_items",
                "deadlines",
                "scheduled_items",
                "obligations",
                "files_by_role",
                "audit_needed",
            ],
            "required_facts": [
                {"name": "top priority", "any": ["Send review packet", "review packet"]},
                {"name": "deadline", "any": ["2026-05-22", "May 22"]},
                {"name": "person", "any": ["Example Recipient", "Recipient"]},
                {"name": "project", "any": ["fixture lantern"]},
                {"name": "repo planning file", "any": ["project-notes.org"]},
                {"name": "morning schedule", "any": ["2026-05-21", "May 21"]},
            ],
            "forbidden_facts": [
                {"name": "wrong person", "any": ["Marina"]},
                {"name": "invented completion", "any": ["already completed", "DONE Send review packet"]},
            ],
            "text": "\n\n".join(
                [
                    "File /workspace/synthetic-corpus/sample-planning.org: active planning file. "
                    "Priority A TODO Send review packet. Deadline 2026-05-22. "
                    "Scheduled 2026-05-21 morning. Obligation: contact Example Recipient.",
                    "File /workspace/synthetic-corpus/project-notes.org: repo planning file. "
                    "Priority B TODO prepare branch review notes after the review packet.",
                    "File /workspace/synthetic-corpus/sample-brainstorm.org: ideas backlog for project fixture lantern.",
                ]
            ),
            "max_output_chars": 3000,
            "min_fact_ratio": 0.82,
        },
    ]


def worker_eval_instruction(fixture: dict) -> str:
    keys = ", ".join(fixture.get("required_keys", []))
    return textwrap.dedent(
        f"""
        You are a Motoko local indexing worker. Build a source-grounded artifact
        for the role: {fixture.get('role', '')}.

        Return only one valid JSON object. Do not use Markdown fences. Do not
        include hidden reasoning or <think> text. Preserve exact names, dates,
        TODO states, obligations, project names, and file paths from the source.
        Do not invent people, dates, statuses, payments, or completed work.

        Required top-level keys: {keys}

        Label: {fixture.get('label', '')}

        Source:
        {fixture.get('text', '')}
        """
    ).strip()


def worker_eval_messages(fixture: dict) -> list[dict]:
    return [
        {
            "role": "system",
            "content": "Create strict JSON indexing artifacts. Be faithful, compact, and source-grounded.",
        },
        {"role": "user", "content": worker_eval_instruction(fixture)},
    ]


def extract_json_object(text: str) -> tuple[dict | None, str]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    candidates = [raw]
    start = raw.find("{")
    end = raw.rfind("}")
    if 0 <= start < end:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed, ""
    return None, "response is not a valid JSON object"


def fact_matches(text: str, fact: dict) -> bool:
    lowered = text.lower()
    for option in fact.get("any", []) or []:
        needle = str(option).strip().lower()
        if needle and needle in lowered:
            return True
    return False


def score_worker_eval_output(fixture: dict, output: str, *, error: str = "") -> dict:
    parsed, json_error = extract_json_object(output) if output else (None, "empty response")
    output_for_scoring = output
    if parsed is not None:
        output_for_scoring = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
    required = fixture.get("required_facts", []) or []
    missing = [fact.get("name", "") for fact in required if not fact_matches(output_for_scoring, fact)]
    forbidden = [fact.get("name", "") for fact in fixture.get("forbidden_facts", []) or [] if fact_matches(output_for_scoring, fact)]
    required_keys = fixture.get("required_keys", []) or []
    missing_keys = [key for key in required_keys if not isinstance(parsed, dict) or key not in parsed]
    fact_ratio = 1.0 if not required else (len(required) - len(missing)) / len(required)
    max_chars = int(fixture.get("max_output_chars", 4000) or 4000)
    length_ok = len(output) <= max_chars
    no_think = "<think" not in output.lower()
    json_valid = parsed is not None
    status = (
        "pass"
        if not error
        and json_valid
        and not missing_keys
        and fact_ratio >= float(fixture.get("min_fact_ratio", 0.8))
        and not forbidden
        and length_ok
        and no_think
        else "fail"
    )
    score = 0.0
    score += 55.0 * fact_ratio
    score += 15.0 if json_valid else 0.0
    score += 10.0 if not missing_keys else max(0.0, 10.0 * (1.0 - len(missing_keys) / max(1, len(required_keys))))
    score += 10.0 if not forbidden else 0.0
    score += 5.0 if length_ok else 0.0
    score += 5.0 if no_think else 0.0
    return {
        "status": status,
        "score": round(score, 1),
        "json_valid": json_valid,
        "json_error": json_error,
        "required_fact_count": len(required),
        "matched_fact_count": len(required) - len(missing),
        "missing_facts": missing,
        "forbidden_hits": forbidden,
        "required_key_count": len(required_keys),
        "missing_keys": missing_keys,
        "length_ok": length_ok,
        "no_think": no_think,
        "error": error,
    }
