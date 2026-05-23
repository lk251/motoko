"""Conversation record helpers for Motoko."""

from __future__ import annotations

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
