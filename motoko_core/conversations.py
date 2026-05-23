"""Conversation record helpers for Motoko."""

from __future__ import annotations

import contextlib
import json
import pathlib

from motoko_core.state import atomic_write, read_jsonl, safe_load_json
from motoko_core.text import compact_text


def make_conversation_record(
    *,
    conversation_id: str,
    title: str | None,
    created: str,
    branch: str,
    endpoint: str,
    model: str,
) -> dict:
    return {
        "id": conversation_id,
        "title": title or "Untitled",
        "title_kind": "manual" if title else "unset",
        "branch": branch,
        "created": created,
        "updated": created,
        "endpoint": endpoint,
        "model": model,
        "messages": [],
        "context_items": [],
    }


def conversation_has_chat_content(conv: dict) -> bool:
    if str(conv.get("summary", "")).strip():
        return True
    messages = conv.get("messages", [])
    for msg in messages if isinstance(messages, list) else []:
        if isinstance(msg, dict) and str(msg.get("content", "")).strip():
            return True
    return False


def rename_conversation_record(conv: dict, title: str) -> str:
    next_title = str(title or "").strip() or str(conv.get("title", "") or "Untitled")
    conv["title"] = next_title
    conv["title_kind"] = "manual"
    conv.pop("title_generated", None)
    return next_title


def save_conversation_record(conv: dict, path: pathlib.Path, *, updated: str) -> None:
    conv["updated"] = updated
    atomic_write(path, json.dumps(conv, ensure_ascii=False, indent=2) + "\n")


def close_conversation_record(conv: dict, path: pathlib.Path, *, updated: str) -> bool:
    if conversation_has_chat_content(conv):
        save_conversation_record(conv, path, updated=updated)
        return True
    with contextlib.suppress(FileNotFoundError):
        path.unlink()
    return False


def list_conversation_records(directory: pathlib.Path) -> list[dict]:
    rows = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            conv = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.append(conv)
    return rows


def json_references_conversation(value, conversation_id: str) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "conversation_id",
                "owner_conversation_id",
                "created_by_conversation_id",
            } and str(item) == conversation_id:
                return True
            if key in {"conversation_ids", "source_conversation_ids"} and isinstance(item, list):
                if any(str(row) == conversation_id for row in item):
                    return True
            if key == "source_conversations" and isinstance(item, list):
                if any(isinstance(row, dict) and str(row.get("id", "")) == conversation_id for row in item):
                    return True
            if json_references_conversation(item, conversation_id):
                return True
        return False
    if isinstance(value, list):
        return any(json_references_conversation(item, conversation_id) for item in value)
    return False


def rewrite_jsonl_without_conversation(path: pathlib.Path, conversation_id: str) -> int:
    rows = read_jsonl(path)
    if not rows:
        return 0
    kept = [row for row in rows if not json_references_conversation(row, conversation_id)]
    removed = len(rows) - len(kept)
    if not removed:
        return 0
    if kept:
        atomic_write(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in kept))
    else:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
    return removed


def delete_json_artifacts_referencing_conversation(directory: pathlib.Path, conversation_id: str) -> int:
    removed = 0
    for path in sorted(directory.glob("*.json")):
        data = safe_load_json(path)
        if data is not None and json_references_conversation(data, conversation_id):
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
                removed += 1
    return removed


def filter_json_rows_without_conversation(rows: list[dict], conversation_id: str) -> tuple[list[dict], int]:
    kept = [row for row in rows if not json_references_conversation(row, conversation_id)]
    return kept, len(rows) - len(kept)


def format_conversation_delete_report(report: dict) -> str:
    lines = [
        f"deleted conversation: {report.get('conversation_id', '')}",
        f"memories deleted: {report.get('memories_deleted', 0)}",
        f"feedback rows deleted: {report.get('feedback_deleted', 0)}",
        f"study job events deleted: {report.get('study_job_events_deleted', 0)}",
        f"topic dossiers deleted: {report.get('topics_deleted', 0)}",
        f"memory dossiers deleted: {report.get('dossiers_deleted', 0)}",
        f"feedback evals deleted: {report.get('feedback_evals_deleted', 0)}",
    ]
    flags = []
    for key, label in [
        ("profile_deleted", "profile dossier"),
        ("maintenance_deleted", "maintenance state"),
        ("study_state_deleted", "study state"),
        ("context_catalog_deleted", "context catalog"),
    ]:
        if report.get(key):
            flags.append(label)
    if flags:
        lines.append("invalidated: " + ", ".join(flags))
    return "\n".join(lines)


def conversation_recall_text(conv: dict, *, recent_message_limit: int) -> str:
    parts = [conv.get("title", "")]
    if conv.get("summary"):
        parts.append(conv.get("summary", ""))
    for msg in conv.get("messages", [])[-recent_message_limit:]:
        if msg.get("role") in {"user", "assistant"}:
            parts.append(msg.get("content", ""))
    return "\n".join(part for part in parts if part)


def conversation_transcript_for_model(
    conv: dict,
    *,
    limit: int,
    max_chars: int,
) -> str:
    lines = []
    for msg in conv.get("messages", [])[-limit:]:
        role = str(msg.get("role", "message") or "message")
        if role not in {"user", "assistant", "system", "summary", "error", "queued"}:
            role = "message"
        content = str(msg.get("content", "") or "").strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")
    transcript = "\n\n".join(lines).strip()
    return compact_text(transcript, max_chars) if max_chars > 0 else transcript


def rank_recent_conversation_rows(
    rows: list[dict],
    *,
    query_counts,
    recall_text_func,
    score_text_func,
    recency_lane: int,
    relevance_lane: int,
    limit: int,
) -> list[dict]:
    if not rows:
        return []
    scored_by_id = {}
    for idx, row in enumerate(rows):
        recall_text = recall_text_func(row)
        lexical = score_text_func(query_counts, recall_text) if query_counts else 0
        recency_bonus = max(1, 10 - idx)
        enriched = dict(row)
        enriched["_recall_text"] = recall_text
        enriched["_recall_score"] = lexical * 8 + recency_bonus
        enriched["_matched_terms"] = lexical
        enriched["_recency_bonus"] = recency_bonus
        enriched["_selection_reasons"] = []
        scored_by_id[enriched.get("id", "")] = enriched

    selected: list[dict] = []
    seen: set[str] = set()
    for row in rows[:recency_lane]:
        enriched = scored_by_id.get(row.get("id", ""))
        if not enriched:
            continue
        enriched["_selection_reasons"].append("recent")
        selected.append(enriched)
        seen.add(enriched.get("id", ""))

    relevance_ranked = sorted(
        scored_by_id.values(),
        key=lambda row: (
            row.get("_matched_terms", 0),
            row.get("_recall_score", 0),
            row.get("updated", row.get("created", "")),
        ),
        reverse=True,
    )
    for row in relevance_ranked:
        if row.get("_matched_terms", 0) <= 0 and query_counts:
            continue
        if row.get("id", "") in seen:
            if "relevant" not in row["_selection_reasons"] and row.get("_matched_terms", 0) > 0:
                row["_selection_reasons"].append("relevant")
            continue
        row["_selection_reasons"].append("relevant")
        selected.append(row)
        seen.add(row.get("id", ""))
        if len([item for item in selected if "relevant" in item.get("_selection_reasons", [])]) >= relevance_lane:
            break

    selected.sort(
        key=lambda row: (
            "recent" in row.get("_selection_reasons", []),
            row.get("_matched_terms", 0),
            row.get("_recall_score", 0),
        ),
        reverse=True,
    )
    return selected[:limit]


def render_recent_conversations_with_sources_core(
    conversations: list[dict],
    *,
    relative_time_func,
    max_chars: int,
    snippet_chars: int,
    recent_message_limit: int,
) -> tuple[str, list[dict]]:
    if not conversations:
        return "No other recent conversations yet.", []
    lines = []
    sources = []
    used = 0
    for row in conversations:
        title = row.get("title") or "Untitled"
        updated = relative_time_func(row.get("updated", row.get("created", "")))
        branch = row.get("branch") or "-"
        header = f"- [conversation:{row.get('id', '')}; updated={updated}; branch={branch}] {title}"
        body_parts = []
        if row.get("summary"):
            body_parts.append("summary: " + compact_text(row.get("summary", ""), snippet_chars))
        recent_lines = []
        for msg in row.get("messages", [])[-recent_message_limit:]:
            role = msg.get("role", "")
            if role not in {"user", "assistant"}:
                continue
            label = "Javier" if role == "user" else "Motoko"
            recent_lines.append(f"{label}: {compact_text(msg.get('content', ''), snippet_chars)}")
        if recent_lines:
            body_parts.append("recent turns:\n  " + "\n  ".join(recent_lines))
        text = header + ("\n  " + "\n  ".join(body_parts) if body_parts else "")
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(text) > remaining:
            text = text[: max(0, remaining - 1)].rstrip() + "…"
        lines.append(text)
        used += len(text)
        sources.append(
            {
                "kind": "recent-conversation",
                "conversation_id": row.get("id", ""),
                "title": title,
                "updated": row.get("updated", row.get("created", "")),
                "branch": branch,
                "score": row.get("_recall_score", 0),
                "matched_terms": row.get("_matched_terms", 0),
                "selection": row.get("_selection_reasons", []),
            }
        )
    return "\n\n".join(lines), sources
