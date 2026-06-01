"""Profile dossier helpers for Motoko."""

from __future__ import annotations

import textwrap

from motoko_core.text import compact_text


def render_profile_with_sources_core(profile: dict | None) -> tuple[str, list[dict]]:
    if not profile or not profile.get("text", "").strip():
        return "No profile dossier yet. Run /profile-refresh to build one.", []
    return profile.get("text", ""), [
        {
            "kind": "profile",
            "updated": profile.get("updated", ""),
            "memory_count": len(profile.get("memory_ids", [])),
            "conversation_count": len(profile.get("conversation_ids", [])),
        }
    ]


def format_profile_dossier(profile: dict | None) -> str:
    if not profile:
        return "No profile dossier yet. Run 'motoko profile refresh' or /profile-refresh."
    return "\n".join(
        [
            f"updated: {profile.get('updated', '')}",
            f"memories: {len(profile.get('memory_ids', []))}",
            f"conversations: {len(profile.get('conversation_ids', []))}",
            "",
            str(profile.get("text", "")),
        ]
    )


def profile_source_material_core(
    memories: list[dict],
    conversations: list[dict],
    *,
    conversation_text,
    memory_default_importance: int,
    conversation_excerpt_chars: int = 2500,
    check_cancelled=None,
) -> tuple[str, list[str], list[str]]:
    """Build profile source material from already-loaded private rows."""

    def maybe_cancel() -> None:
        if check_cancelled is not None:
            check_cancelled()

    maybe_cancel()
    selected_conversations: list[tuple[dict, str]] = []
    for conv in conversations or []:
        maybe_cancel()
        text = str(conversation_text(conv) or "")
        if text.strip():
            selected_conversations.append((conv, text))

    memory_lines = []
    for row in memories or []:
        maybe_cancel()
        if not isinstance(row, dict):
            continue
        memory_lines.append(
            f"- [{row.get('id', '')}; i{row.get('importance', memory_default_importance)}] {row.get('text', '')}"
        )

    conversation_blocks = []
    for conv, recall_text in selected_conversations:
        maybe_cancel()
        title = conv.get("title") or "Untitled"
        conversation_blocks.append(
            f"--- conversation:{conv.get('id', '')} title:{title} updated:{conv.get('updated', '')} ---\n"
            f"{compact_text(recall_text, conversation_excerpt_chars)}"
        )

    text = textwrap.dedent(
        f"""
        Durable memories:
        {chr(10).join(memory_lines) if memory_lines else "(none)"}

        Recent conversation material:
        {chr(10).join(conversation_blocks) if conversation_blocks else "(none)"}
        """
    ).strip()
    return (
        text,
        [row.get("id", "") for row in memories or [] if isinstance(row, dict) and row.get("id")],
        [conv.get("id", "") for conv, _recall_text in selected_conversations if conv.get("id")],
    )
