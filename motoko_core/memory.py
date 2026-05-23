"""Durable memory row helpers for Motoko."""

from __future__ import annotations

import json
import pathlib
import uuid

from motoko_core.retrieval import score_text, token_counts
from motoko_core.state import atomic_write, read_jsonl


DEFAULT_MEMORY_IMPORTANCE = 3
MAX_MEMORY_IMPORTANCE = 5
MEMORY_CONTEXT_RECENT_MESSAGES = 6
MEMORY_DUPLICATE_THRESHOLD = 0.72


def memory_id() -> str:
    return "mem-" + uuid.uuid4().hex[:10]


def normalize_memory_row(
    row: dict,
    ordinal: int,
    *,
    default_importance: int = DEFAULT_MEMORY_IMPORTANCE,
    max_importance: int = MAX_MEMORY_IMPORTANCE,
) -> dict:
    normalized = dict(row)
    normalized.setdefault("id", f"legacy-{ordinal:04d}")
    normalized.setdefault("created", "")
    normalized.setdefault("source", "unknown")
    normalized.setdefault("text", "")
    normalized.setdefault("importance", default_importance)
    normalized.setdefault("pinned", False)
    normalized.setdefault("tags", [])
    try:
        normalized["importance"] = max(
            1,
            min(max_importance, int(normalized.get("importance", default_importance))),
        )
    except (TypeError, ValueError):
        normalized["importance"] = default_importance
    if not isinstance(normalized.get("tags"), list):
        normalized["tags"] = []
    normalized["pinned"] = bool(normalized.get("pinned"))
    return normalized


def read_memory_rows_file(path: pathlib.Path) -> list[dict]:
    return read_jsonl(path)


def load_memory_rows(
    path: pathlib.Path,
    *,
    limit: int = 80,
    default_importance: int = DEFAULT_MEMORY_IMPORTANCE,
    max_importance: int = MAX_MEMORY_IMPORTANCE,
) -> list[dict]:
    rows = [
        normalize_memory_row(
            row,
            idx,
            default_importance=default_importance,
            max_importance=max_importance,
        )
        for idx, row in enumerate(read_memory_rows_file(path), 1)
    ]
    return rows[-limit:]


def write_memory_rows_file(path: pathlib.Path, rows: list[dict]) -> None:
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    atomic_write(path, text)


def text_similarity(left: str, right: str) -> float:
    left_terms = set(token_counts(left))
    right_terms = set(token_counts(right))
    if not left_terms or not right_terms:
        return 0.0
    overlap = left_terms & right_terms
    return len(overlap) / max(1, min(len(left_terms), len(right_terms)))


def memory_tags(text: str) -> list[str]:
    counts = token_counts(text)
    stop = {
        "about",
        "after",
        "also",
        "because",
        "before",
        "could",
        "from",
        "have",
        "into",
        "javier",
        "motoko",
        "should",
        "that",
        "their",
        "there",
        "this",
        "with",
        "would",
    }
    tags = []
    for word, _count in counts.most_common(20):
        if word in stop:
            continue
        tags.append(word)
        if len(tags) >= 8:
            break
    return tags


def find_similar_memory(
    text: str,
    rows: list[dict],
    *,
    duplicate_threshold: float = MEMORY_DUPLICATE_THRESHOLD,
) -> dict | None:
    best = None
    best_score = 0.0
    for row in rows:
        score = text_similarity(text, row.get("text", ""))
        if score > best_score:
            best = row
            best_score = score
    if best is not None and best_score >= duplicate_threshold:
        return best
    return None


def memory_query_text(
    conv: dict | None,
    query: str = "",
    *,
    recent_message_limit: int = MEMORY_CONTEXT_RECENT_MESSAGES,
) -> str:
    parts = [query, conv.get("title", "") if conv else ""]
    if conv:
        if conv.get("summary"):
            parts.append(conv.get("summary", "")[-4000:])
        for msg in conv.get("messages", [])[-recent_message_limit:]:
            if msg.get("role") == "user":
                parts.append(msg.get("content", ""))
    return "\n".join(part for part in parts if part)


def memory_relevance(
    row: dict,
    query_counts,
    recency_bonus: int,
    conversation_terms=None,
    *,
    default_importance: int = DEFAULT_MEMORY_IMPORTANCE,
) -> int:
    text = "\n".join(
        [
            row.get("text", ""),
            " ".join(str(tag) for tag in row.get("tags", [])),
            row.get("source", ""),
        ]
    )
    lexical = score_text(query_counts, text)
    thread_match = score_text(conversation_terms or {}, text)
    importance = int(row.get("importance", default_importance))
    pinned = 40 if row.get("pinned") else 0
    seen = min(8, int(row.get("seen_count", 1)))
    return lexical * 8 + thread_match * 3 + importance * 4 + recency_bonus + pinned + seen


def rank_memory_rows(
    rows: list[dict],
    *,
    conv: dict | None = None,
    query: str = "",
    limit: int,
    default_importance: int = DEFAULT_MEMORY_IMPORTANCE,
    recent_message_limit: int = MEMORY_CONTEXT_RECENT_MESSAGES,
) -> list[dict]:
    if not rows:
        return []
    combined_query = memory_query_text(conv, query, recent_message_limit=recent_message_limit)
    query_counts = token_counts(combined_query)
    conversation_terms = token_counts(memory_query_text(conv, "", recent_message_limit=recent_message_limit))
    scored = []
    total = len(rows)
    for idx, row in enumerate(rows):
        recency_bonus = 1 + min(10, idx * 10 // max(1, total - 1)) if total > 1 else 10
        score = memory_relevance(
            row,
            query_counts,
            recency_bonus,
            conversation_terms,
            default_importance=default_importance,
        )
        matched = score_text(query_counts, row.get("text", "")) if query_counts else 0
        thread_matched = score_text(conversation_terms, row.get("text", "")) if conversation_terms else 0
        enriched = dict(row)
        enriched["_score"] = score
        enriched["_matched_terms"] = matched
        enriched["_thread_matched_terms"] = thread_matched
        enriched["_recency_bonus"] = recency_bonus
        scored.append(enriched)
    scored.sort(
        key=lambda row: (
            bool(row.get("pinned")),
            row.get("_matched_terms", 0),
            row.get("_score", 0),
            row.get("importance", default_importance),
            row.get("created", ""),
        ),
        reverse=True,
    )

    selected = []
    seen: set[str] = set()
    for row in scored:
        if len(selected) >= limit:
            break
        if (
            not row.get("pinned")
            and row.get("_matched_terms", 0) <= 0
            and row.get("_thread_matched_terms", 0) <= 0
            and query_counts
        ):
            continue
        memory_ref = row.get("id", "")
        if memory_ref in seen:
            continue
        seen.add(memory_ref)
        selected.append(row)

    if len(selected) < min(6, len(rows)):
        for row in reversed(rows):
            memory_ref = row.get("id", "")
            if memory_ref in seen:
                continue
            enriched = dict(row)
            enriched.setdefault("_score", 0)
            enriched.setdefault("_matched_terms", 0)
            selected.append(enriched)
            seen.add(memory_ref)
            if len(selected) >= min(limit, 6):
                break
    return selected[:limit]


def format_memory_rows(
    rows: list[dict],
    *,
    verbose: bool = False,
    default_importance: int = DEFAULT_MEMORY_IMPORTANCE,
) -> str:
    if not rows:
        return "No memories yet."
    lines = []
    for idx, row in enumerate(rows, 1):
        pin = "pin" if row.get("pinned") else "   "
        prefix = (
            f"{idx:3d}  {row.get('id', '')}  "
            f"i{row.get('importance', default_importance)} {pin}  "
            f"{row.get('created', '')}"
        )
        lines.append(f"{prefix}  {row.get('text', '')}")
        if verbose:
            lines.append(f"     source: {row.get('source', 'unknown')}")
            if row.get("conversation_id"):
                lines.append(f"     conversation: {row.get('conversation_id')}")
            if row.get("derived_from"):
                lines.append(f"     derived from: {row.get('derived_from')}")
            if row.get("tags"):
                lines.append(f"     tags: {', '.join(row.get('tags', []))}")
            if row.get("seen_count"):
                lines.append(f"     seen: {row.get('seen_count')} time(s)")
    return "\n".join(lines)


def format_memory_search_rows(
    rows: list[dict],
    *,
    default_importance: int = DEFAULT_MEMORY_IMPORTANCE,
) -> str:
    if not rows:
        return "No matching memories."
    lines = []
    for idx, row in enumerate(rows, 1):
        pin = "pin" if row.get("pinned") else "   "
        lines.append(
            f"{idx:3d}  {row.get('id', '')}  "
            f"score={row.get('_score', 0):3d}  "
            f"match={row.get('_matched_terms', 0):2d}  "
            f"i{row.get('importance', default_importance)} {pin}  "
            f"{row.get('text', '')}"
        )
    return "\n".join(lines)


def render_memories_with_sources_core(
    memories: list[dict],
    *,
    has_any_memory: bool,
    default_importance: int = DEFAULT_MEMORY_IMPORTANCE,
) -> tuple[str, list[dict]]:
    if not memories:
        if has_any_memory:
            return "No saved memories matched this turn strongly.", []
        return "No saved memories yet.", []
    lines = []
    sources = []
    for row in memories:
        memory_ref = row.get("id", "unknown")
        markers = []
        if row.get("pinned"):
            markers.append("pinned")
        markers.append(f"importance={row.get('importance', default_importance)}")
        if row.get("_matched_terms", 0):
            markers.append(f"match={row.get('_matched_terms')}")
        if row.get("_thread_matched_terms", 0):
            markers.append(f"thread={row.get('_thread_matched_terms')}")
        lines.append(f"- [memory:{memory_ref}; {', '.join(markers)}] {row.get('text', '')}")
        sources.append(
            {
                "kind": "memory",
                "id": memory_ref,
                "source": row.get("source", "unknown"),
                "conversation_id": row.get("conversation_id", ""),
                "created": row.get("created", ""),
                "importance": row.get("importance", default_importance),
                "pinned": bool(row.get("pinned")),
                "score": row.get("_score", 0),
                "matched_terms": row.get("_matched_terms", 0),
            }
        )
    return "\n".join(lines), sources
