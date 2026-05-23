"""Memory dossier formatting helpers for Motoko."""

from __future__ import annotations


def format_dossiers_list(rows: list[dict]) -> str:
    if not rows:
        return "No memory dossiers yet."
    lines = []
    for dossier in rows:
        lines.append(
            f"{dossier.get('created', '')}  {dossier.get('id')}  "
            f"{dossier.get('source_memory_count', 0)} memories  "
            f"{dossier.get('source_conversation_count', 0)} conversations  "
            f"{dossier.get('name', '')}  {dossier.get('query', '')}"
        )
    return "\n".join(lines)


def format_dossier_report(dossier: dict, *, evidence: bool = False) -> str:
    lines = [
        f"{dossier.get('name', 'Untitled')} [{dossier.get('id')}]",
        "",
        f"query> {dossier.get('query', '')}",
        "",
        str(dossier.get("summary", "")),
    ]
    if evidence:
        lines.extend(["", "Memory Evidence:"])
        for item in dossier.get("source_memories", []):
            lines.extend(
                [
                    "",
                    f"--- memory:{item.get('id')} importance:{item.get('importance')} "
                    f"score:{item.get('score')} ---",
                    str(item.get("excerpt", "")),
                ]
            )
        lines.extend(["", "Conversation Evidence:"])
        for item in dossier.get("source_conversations", []):
            lines.extend(
                [
                    "",
                    f"--- conversation:{item.get('id')} title:{item.get('title')} "
                    f"updated:{item.get('updated')} ---",
                    str(item.get("excerpt", "")),
                ]
            )
    return "\n".join(lines)
