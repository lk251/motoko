"""Private response-feedback and eval-fixture helpers for Motoko."""

from __future__ import annotations

import collections
import hashlib

from motoko_core.commands import command_body, command_matches_any, command_primary
from motoko_core.text import compact_text


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_feedback_rating(rating: str) -> str:
    value = str(rating or "").strip().lower()
    aliases = {
        "+": "up",
        "good": "up",
        "yes": "up",
        "thumbsup": "up",
        "thumbs-up": "up",
        "up": "up",
        "-": "down",
        "bad": "down",
        "no": "down",
        "thumbsdown": "down",
        "thumbs-down": "down",
        "down": "down",
        "ok": "ok",
        "neutral": "ok",
    }
    normalized = aliases.get(value)
    if normalized is None:
        raise SystemExit("usage: feedback up|down|ok [note]")
    return normalized


def last_message_content(conv: dict, role: str) -> tuple[int, str]:
    messages = conv.get("messages", []) if isinstance(conv.get("messages"), list) else []
    for index in range(len(messages) - 1, -1, -1):
        msg = messages[index]
        if isinstance(msg, dict) and msg.get("role") == role:
            return index, str(msg.get("content", ""))
    return -1, ""


def compact_feedback_sources(sources: list[dict], *, limit: int = 16) -> list[dict]:
    rows = []
    for source in sources[:limit]:
        if not isinstance(source, dict):
            continue
        rows.append(
            {
                key: source.get(key)
                for key in [
                    "kind",
                    "id",
                    "index",
                    "path",
                    "chunk",
                    "retrieval",
                    "retrieval_methods",
                    "score",
                    "hybrid_score",
                    "rerank_score",
                    "vector_score",
                    "status",
                    "vector_store",
                    "vector_method",
                    "vector_rerank_route",
                    "hybrid_rerank_route",
                    "evidence_rows",
                    "evidence_id",
                    "evidence_kind",
                    "evidence_title",
                    "evidence_date",
                    "evidence_score",
                ]
                if source.get(key) not in (None, "", [])
            }
        )
    return rows


def make_response_feedback_row(
    conv: dict,
    rating: str,
    note: str,
    *,
    schema: str,
    feedback_id: str,
    created: str,
    realm: str,
) -> dict:
    normalized = normalize_feedback_rating(rating)
    assistant_index, assistant_text = last_message_content(conv, "assistant")
    if assistant_index < 0 or not assistant_text.strip():
        raise SystemExit("No assistant answer is available to rate yet.")
    user_index, user_text = last_message_content(conv, "user")
    return {
        "schema": schema,
        "id": feedback_id,
        "created": created,
        "realm": realm,
        "conversation_id": conv.get("id", ""),
        "conversation_title": conv.get("title", ""),
        "rating": normalized,
        "note": compact_text(note, 2000),
        "user_message_index": user_index,
        "assistant_message_index": assistant_index,
        "user_prompt": compact_text(user_text, 4000),
        "assistant_reply": compact_text(assistant_text, 4000),
        "sources": compact_feedback_sources(conv.get("last_sources", []) if isinstance(conv.get("last_sources"), list) else []),
        "use": "retrieval and answer-quality training signal; do not apply automatically without eval gates",
    }


def feedback_eval_focus(row: dict) -> list[str]:
    text = " ".join(
        [
            str(row.get("rating", "")),
            str(row.get("note", "")),
            str(row.get("user_prompt", "")),
        ]
    ).lower()
    focus = []
    for label, words in [
        ("recall", {"missing", "didn't find", "did not find", "not found", "absent", "sources"}),
        ("ranking", {"wrong source", "wrong file", "irrelevant", "ranking", "top result"}),
        ("evidence", {"citation", "source", "excerpt", "ground", "quote"}),
        ("prompt_use", {"ignored", "didn't use", "did not use", "answer"}),
        ("staleness", {"stale", "old", "outdated", "changed"}),
        ("synthesis", {"summary", "prioritize", "todo", "plan"}),
    ]:
        if any(word in text for word in words):
            focus.append(label)
    return list(dict.fromkeys(focus or ["answer_quality"]))


def feedback_eval_source_hints(row: dict) -> list[dict]:
    hints = []
    seen = set()
    for source in row.get("sources", []) if isinstance(row.get("sources"), list) else []:
        if not isinstance(source, dict):
            continue
        key = (
            source.get("kind", ""),
            source.get("index", ""),
            source.get("path", ""),
            str(source.get("chunk", "")),
            source.get("evidence_id", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        hints.append(
            {
                item_key: source.get(item_key)
                for item_key in [
                    "kind",
                    "index",
                    "path",
                    "chunk",
                    "evidence_id",
                    "evidence_kind",
                    "evidence_title",
                    "evidence_date",
                    "score",
                    "hybrid_score",
                    "rerank_score",
                    "vector_score",
                    "evidence_score",
                    "status",
                ]
                if source.get(item_key) not in (None, "", [])
            }
        )
    return hints


def feedback_eval_fixture(row: dict, *, default_realm: str = "") -> dict:
    rating = str(row.get("rating", ""))
    quality_status = {
        "up": "accepted-good",
        "ok": "accepted-mixed",
        "down": "needs-review",
    }.get(rating, "needs-review")
    source_hints = feedback_eval_source_hints(row)
    return {
        "id": row.get("id", ""),
        "created": row.get("created", ""),
        "realm": row.get("realm", default_realm),
        "rating": rating,
        "quality_status": quality_status,
        "focus": feedback_eval_focus(row),
        "conversation_id": row.get("conversation_id", ""),
        "conversation_title": row.get("conversation_title", ""),
        "query": row.get("user_prompt", ""),
        "note": row.get("note", ""),
        "assistant_reply_sha256": sha256_hex(str(row.get("assistant_reply", "")).encode("utf-8")),
        "source_hints": source_hints,
        "source_path_count": len({hint.get("path", "") for hint in source_hints if hint.get("path")}),
        "source_evidence_count": len([hint for hint in source_hints if hint.get("evidence_id")]),
        "use": (
            "Private per-realm eval fixture. Use for retrieval/rerank/prompt "
            "evaluation and audits; do not directly mutate ranking behavior."
        ),
    }


def make_feedback_eval_report(
    rows: list[dict],
    *,
    schema: str,
    report_id: str,
    created: str,
    realm: str,
    source: str,
) -> dict:
    fixtures = [feedback_eval_fixture(row, default_realm=realm) for row in rows]
    ratings = collections.Counter(row.get("rating", "unknown") for row in fixtures)
    focus_counts = collections.Counter(focus for row in fixtures for focus in row.get("focus", []))
    return {
        "schema": schema,
        "id": report_id,
        "created": created,
        "realm": realm,
        "source": source,
        "fixture_count": len(fixtures),
        "ratings": dict(sorted(ratings.items())),
        "focus": dict(sorted(focus_counts.items())),
        "fixtures": fixtures,
        "privacy": "Stored under the current user's Motoko state; no cross-realm sharing.",
    }


def format_feedback_eval_report(report: dict) -> str:
    lines = [
        f"feedback eval: {report.get('fixture_count', 0)} fixture(s)",
        f"id: {report.get('id', '')}",
        f"created: {report.get('created', '')}",
        f"realm: {report.get('realm', '')}",
        f"source: {report.get('source', '')}",
        "ratings: "
        + (
            ", ".join(f"{key}={value}" for key, value in (report.get("ratings") or {}).items())
            or "-"
        ),
        "focus: "
        + (
            ", ".join(f"{key}={value}" for key, value in (report.get("focus") or {}).items())
            or "-"
        ),
    ]
    for row in report.get("fixtures", [])[:12]:
        lines.append(
            f"- {row.get('rating', '')} {row.get('id', '')} "
            f"{row.get('quality_status', '')}: {compact_text(row.get('query', ''), 120)}"
        )
        if row.get("note"):
            lines.append(f"  note: {compact_text(row.get('note', ''), 160)}")
        if row.get("focus"):
            lines.append(f"  focus: {', '.join(row.get('focus', []))}")
        if row.get("source_hints"):
            first = row["source_hints"][0]
            label = first.get("path") or first.get("kind") or "-"
            if first.get("evidence_id"):
                label += f" evidence={first.get('evidence_kind', '')}:{first.get('evidence_id', '')[:12]}"
            lines.append(f"  first source: {label}")
    if report.get("fixture_count", 0) > 12:
        lines.append(f"... {report.get('fixture_count', 0) - 12} more fixture(s)")
    lines.append(f"privacy: {report.get('privacy', '')}")
    return "\n".join(lines)


def is_feedback_command(text: str) -> bool:
    return command_matches_any(text, ("/feedback", "/up", "/down", "feedback"))


def parse_feedback_command(text: str) -> tuple[str, str]:
    primary = command_primary(text)
    body = command_body(text)
    if primary == "/up":
        return "up", body
    if primary == "/down":
        return "down", body
    if primary not in {"/feedback", "feedback"}:
        raise SystemExit("usage: /feedback up|down|ok [note]")
    if not body:
        raise SystemExit("usage: feedback up|down|ok [note]")
    parts = body.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else ""
