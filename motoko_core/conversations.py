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
