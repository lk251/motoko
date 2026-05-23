"""Memory dossier formatting helpers for Motoko."""

from __future__ import annotations

from motoko_core.retrieval import score_text, token_counts


def retrieve_from_dossier_core(dossier: dict, query: str, *, max_chars: int) -> tuple[str, list[dict]]:
    query_counts = token_counts(query or dossier.get("query", ""))
    memory_rows = list(dossier.get("source_memories", []))
    conversation_rows = list(dossier.get("source_conversations", []))
    if query_counts:
        memory_rows.sort(
            key=lambda item: score_text(
                query_counts,
                "\n".join([item.get("excerpt", ""), item.get("id", "")]),
            ),
            reverse=True,
        )
        conversation_rows.sort(
            key=lambda item: score_text(
                query_counts,
                "\n".join([item.get("title", ""), item.get("excerpt", "")]),
            ),
            reverse=True,
        )

    parts = [
        f"=== Memory dossier: {dossier.get('name', dossier.get('id'))} ===",
        f"Dossier query: {dossier.get('query', '')}",
        "Dossier summary:",
        dossier.get("summary", ""),
    ]
    sources = [
        {
            "kind": "dossier",
            "id": dossier.get("id", ""),
            "name": dossier.get("name", ""),
            "query": dossier.get("query", ""),
        }
    ]
    used = 0
    if memory_rows:
        parts.append("Dossier memory excerpts:")
    for item in memory_rows:
        remaining = max_chars - used
        if remaining <= 0:
            break
        excerpt = item.get("excerpt", "")[:remaining]
        used += len(excerpt)
        parts.append(
            f"--- [dossier:{dossier.get('id')} memory:{item.get('id')}] ---\n"
            f"importance={item.get('importance')} score={item.get('score')} "
            f"source={item.get('source')}\n{excerpt}"
        )
        sources.append(
            {
                "kind": "dossier-memory",
                "dossier": dossier.get("id", ""),
                "memory": item.get("id", ""),
                "source": item.get("source", ""),
            }
        )
    if conversation_rows and used < max_chars:
        parts.append("Dossier conversation excerpts:")
    for item in conversation_rows:
        remaining = max_chars - used
        if remaining <= 0:
            break
        excerpt = item.get("excerpt", "")[:remaining]
        used += len(excerpt)
        parts.append(
            f"--- [dossier:{dossier.get('id')} conversation:{item.get('id')}] ---\n"
            f"title={item.get('title')} updated={item.get('updated')} "
            f"selection={','.join(item.get('selection', [])) or '-'}\n{excerpt}"
        )
        sources.append(
            {
                "kind": "dossier-conversation",
                "dossier": dossier.get("id", ""),
                "conversation_id": item.get("id", ""),
                "title": item.get("title", ""),
                "updated": item.get("updated", ""),
            }
        )
    return "\n\n".join(part for part in parts if part), sources


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
