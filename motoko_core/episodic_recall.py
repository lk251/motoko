"""Lossless episodic conversation history and bounded adaptive recall for Motoko.

The active conversation transcript is intentionally small.  This module keeps an
append-only, realm-local raw history beside the compact conversation record and
lets a model-directed planner ask bounded, inspectable retrieval questions
against that history.  Summaries and durable memories remain useful indexes;
they are never the sole authoritative copy of turns archived by this module.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Callable, Iterable

from motoko_core.state import (
    append_jsonl,
    conversation_history_path,
    conversation_windows_path,
    exclusive_file_lock,
    read_jsonl,
)

EPISODIC_HISTORY_SCHEMA = "conversation-history-v1"
CONTEXT_WINDOW_SCHEMA = "conversation-window-v1"
ADAPTIVE_RECALL_PLAN_SCHEMA = "adaptive-recall-plan-v1"
ADAPTIVE_RECALL_SOURCE_SCHEMA = "adaptive-recall-source-v1"

DEFAULT_MAX_ROUNDS = 2
DEFAULT_MAX_QUERIES_PER_ROUND = 3
DEFAULT_RESULTS_PER_QUERY = 5
DEFAULT_CONTEXT_RADIUS = 2
DEFAULT_MAX_CONTEXT_CHARS = 24000
DEFAULT_MAX_QUERY_CHARS = 360
_ALLOWED_SCOPES = {"current_conversation", "all_conversations"}
_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)


@dataclass(frozen=True)
class AdaptiveRecallResult:
    text: str = ""
    sources: list[dict] = field(default_factory=list)
    plans: list[dict] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)


def _utc_now() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="seconds")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _message_signature(message: dict) -> tuple[str, str]:
    role = str(message.get("role", "message") or "message")
    content = str(message.get("content", "") or "")
    return role, _sha256_text(content)


def _message_rows(messages: Iterable[dict]) -> list[dict]:
    rows = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = str(message.get("content", "") or "")
        if not content.strip():
            continue
        rows.append(message)
    return rows


def ensure_context_window_state(conv: dict) -> dict:
    """Ensure a small lineage record exists in the conversation metadata."""

    state = conv.get("context_window")
    if not isinstance(state, dict) or state.get("schema") != CONTEXT_WINDOW_SCHEMA:
        window_id = str(uuid.uuid4())
        state = {
            "schema": CONTEXT_WINDOW_SCHEMA,
            "window_number": 0,
            "first_window_id": window_id,
            "previous_window_id": "",
            "current_window_id": window_id,
        }
        conv["context_window"] = state
        return state

    current = str(state.get("current_window_id", "") or "")
    if not current:
        current = str(uuid.uuid4())
        state["current_window_id"] = current
    if not state.get("first_window_id"):
        state["first_window_id"] = current
    try:
        state["window_number"] = max(0, int(state.get("window_number", 0) or 0))
    except (TypeError, ValueError):
        state["window_number"] = 0
    state.setdefault("previous_window_id", "")
    return state


def history_rows(conversation_id: str) -> list[dict]:
    conversation_id = str(conversation_id or "").strip()
    return read_jsonl(conversation_history_path(conversation_id)) if conversation_id else []


def window_rows(conversation_id: str) -> list[dict]:
    conversation_id = str(conversation_id or "").strip()
    return read_jsonl(conversation_windows_path(conversation_id)) if conversation_id else []


def archive_conversation_messages(conv: dict, *, archived_at: str | None = None) -> int:
    """Append conversation messages that are not already present in raw history.

    Compaction leaves a suffix of recent messages in ``conv["messages"]``.  A
    longest-suffix/prefix overlap makes saving that retained suffix idempotent
    while still appending new turns that follow it.
    """

    conversation_id = str(conv.get("id", "") or "").strip()
    if not conversation_id:
        return 0
    messages = _message_rows(conv.get("messages", []))
    if not messages:
        ensure_context_window_state(conv)
        return 0

    state = ensure_context_window_state(conv)
    path = conversation_history_path(conversation_id)
    lock_path = path.with_suffix(".lock")
    appended = 0
    with exclusive_file_lock(lock_path):
        existing = read_jsonl(path)
        existing_signatures = [
            (str(row.get("role", "message")), str(row.get("content_sha256", "")))
            for row in existing
        ]
        current_signatures = [_message_signature(message) for message in messages]

        overlap = 0
        max_overlap = min(len(existing_signatures), len(current_signatures))
        for size in range(max_overlap, 0, -1):
            if existing_signatures[-size:] == current_signatures[:size]:
                overlap = size
                break

        next_ordinal = 0
        if existing:
            try:
                next_ordinal = max(int(row.get("ordinal", -1)) for row in existing) + 1
            except (TypeError, ValueError):
                next_ordinal = len(existing)

        archive_time = archived_at or _utc_now()
        for message in messages[overlap:]:
            role, content_sha256 = _message_signature(message)
            content = str(message.get("content", "") or "")
            ordinal = next_ordinal
            next_ordinal += 1
            message_id = "msg-" + _sha256_text(
                f"{conversation_id}\0{ordinal}\0{role}\0{content_sha256}"
            )[:24]
            row = {
                "schema": EPISODIC_HISTORY_SCHEMA,
                "conversation_id": conversation_id,
                "conversation_title": str(conv.get("title", "") or ""),
                "message_id": message_id,
                "ordinal": ordinal,
                "window_id": str(state.get("current_window_id", "") or ""),
                "role": role,
                "content": content,
                "content_sha256": content_sha256,
                "created": str(message.get("created", "") or ""),
                "archived_at": archive_time,
            }
            append_jsonl(path, row)
            appended += 1
    return appended


def seal_context_window(
    conv: dict,
    *,
    reason: str,
    retained_message_count: int = 0,
    summary_text: str = "",
    closed_at: str | None = None,
) -> dict:
    """Close the current episodic window and advance lineage without losing turns."""

    archive_conversation_messages(conv, archived_at=closed_at)
    conversation_id = str(conv.get("id", "") or "").strip()
    state = ensure_context_window_state(conv)
    current_window_id = str(state.get("current_window_id", "") or "")
    rows = [
        row
        for row in history_rows(conversation_id)
        if str(row.get("window_id", "")) == current_window_id
    ]
    ordinals = []
    for row in rows:
        try:
            ordinals.append(int(row.get("ordinal", -1)))
        except (TypeError, ValueError):
            continue
    record = {
        "schema": CONTEXT_WINDOW_SCHEMA,
        "conversation_id": conversation_id,
        "window_number": int(state.get("window_number", 0) or 0),
        "first_window_id": str(state.get("first_window_id", "") or ""),
        "previous_window_id": str(state.get("previous_window_id", "") or ""),
        "window_id": current_window_id,
        "closed_at": closed_at or _utc_now(),
        "reason": str(reason or "rollover"),
        "archived_message_count": len(rows),
        "first_ordinal": min(ordinals) if ordinals else None,
        "last_ordinal": max(ordinals) if ordinals else None,
        "retained_message_count": max(0, int(retained_message_count or 0)),
        "summary_sha256": _sha256_text(summary_text) if summary_text else "",
    }
    if conversation_id:
        append_jsonl(conversation_windows_path(conversation_id), record)

    next_window_id = str(uuid.uuid4())
    state["window_number"] = int(state.get("window_number", 0) or 0) + 1
    state["previous_window_id"] = current_window_id
    state["current_window_id"] = next_window_id
    conv["context_window"] = state
    return record


def delete_episodic_history(conversation_id: str) -> int:
    """Delete raw-history sidecars owned by a conversation."""

    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return 0
    removed = 0
    paths = [
        conversation_history_path(conversation_id),
        conversation_windows_path(conversation_id),
        conversation_history_path(conversation_id).with_suffix(".lock"),
        conversation_windows_path(conversation_id).with_suffix(".lock"),
    ]
    for path in paths:
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            pass
    return removed


def _query_terms(text: str) -> list[str]:
    seen = set()
    terms = []
    for token in _WORD_RE.findall(str(text or "").casefold()):
        if len(token) <= 1 or token in seen:
            continue
        seen.add(token)
        terms.append(token)
    return terms


def _lexical_score(query: str, text: str) -> tuple[int, int]:
    query = str(query or "").strip()
    text = str(text or "")
    if not query or not text:
        return 0, 0
    query_terms = _query_terms(query)
    haystack = text.casefold()
    matched = sum(1 for term in query_terms if term in haystack)
    score = matched * 5
    if query.casefold() in haystack:
        score += 18
    for term in query_terms:
        if len(term) >= 7 and re.search(rf"\b{re.escape(term)}\b", haystack):
            score += 2
    return score, matched


def _history_container_boost(conv: dict, query: str) -> int:
    title_score, _ = _lexical_score(query, str(conv.get("title", "") or ""))
    summary_score, _ = _lexical_score(query, str(conv.get("summary", "") or ""))
    return min(12, title_score // 2 + summary_score // 4)


def _history_span(
    rows: list[dict],
    *,
    center_index: int,
    radius: int,
    conversation: dict,
    score: int,
    matched_terms: int,
) -> dict:
    start = max(0, center_index - max(0, radius))
    stop = min(len(rows), center_index + max(0, radius) + 1)
    selected = rows[start:stop]
    return {
        "conversation_id": str(conversation.get("id", "") or ""),
        "conversation_title": str(conversation.get("title", "") or ""),
        "conversation_updated": str(conversation.get("updated", conversation.get("created", "")) or ""),
        "rows": selected,
        "score": score,
        "matched_terms": matched_terms,
        "start_ordinal": selected[0].get("ordinal") if selected else None,
        "end_ordinal": selected[-1].get("ordinal") if selected else None,
        "window_ids": list(
            dict.fromkeys(str(row.get("window_id", "")) for row in selected if row.get("window_id"))
        ),
    }


def search_conversation_history(
    conversations: Iterable[dict],
    query: str,
    *,
    current_conversation_id: str,
    scope: str = "current_conversation",
    limit: int = DEFAULT_RESULTS_PER_QUERY,
    context_radius: int = DEFAULT_CONTEXT_RADIUS,
) -> list[dict]:
    """Search lossless raw turns and return bounded adjacent-turn evidence spans."""

    query = str(query or "").strip()
    if not query:
        return []
    scope = scope if scope in _ALLOWED_SCOPES else "current_conversation"
    conversation_rows = []
    for conversation in conversations:
        if not isinstance(conversation, dict):
            continue
        conversation_id = str(conversation.get("id", "") or "")
        if not conversation_id:
            continue
        if scope == "current_conversation" and conversation_id != current_conversation_id:
            continue
        archive_conversation_messages(conversation)
        rows = history_rows(conversation_id)
        if not rows:
            continue
        rows.sort(key=lambda row: int(row.get("ordinal", 0) or 0))
        boost = _history_container_boost(conversation, query)
        for index, row in enumerate(rows):
            score, matched = _lexical_score(query, str(row.get("content", "") or ""))
            if matched <= 0:
                continue
            # Prefer exact raw-message evidence; use summary/title only as a
            # modest container hint, never as evidence itself.
            score += boost
            conversation_rows.append((score, matched, index, conversation, rows))

    conversation_rows.sort(
        key=lambda item: (
            item[0],
            item[1],
            str(item[3].get("updated", item[3].get("created", ""))),
            int(item[4][item[2]].get("ordinal", 0) or 0),
        ),
        reverse=True,
    )

    selected: list[dict] = []
    covered: dict[str, set[int]] = {}
    for score, matched, index, conversation, rows in conversation_rows:
        if len(selected) >= max(0, int(limit or 0)):
            break
        conversation_id = str(conversation.get("id", "") or "")
        center_ordinal = int(rows[index].get("ordinal", index) or index)
        if center_ordinal in covered.setdefault(conversation_id, set()):
            continue
        span = _history_span(
            rows,
            center_index=index,
            radius=context_radius,
            conversation=conversation,
            score=score,
            matched_terms=matched,
        )
        for row in span["rows"]:
            try:
                covered[conversation_id].add(int(row.get("ordinal", -1)))
            except (TypeError, ValueError):
                continue
        selected.append(span)
    return selected


def format_history_hits(hits: Iterable[dict], *, max_chars: int = DEFAULT_MAX_CONTEXT_CHARS) -> str:
    parts = []
    used = 0
    for hit in hits:
        header = (
            f"[conversation:{hit.get('conversation_id', '')} "
            f"messages:{hit.get('start_ordinal')}-{hit.get('end_ordinal')} "
            f"title:{hit.get('conversation_title', '')}]"
        )
        lines = [header]
        for row in hit.get("rows", []):
            role = str(row.get("role", "message") or "message")
            content = str(row.get("content", "") or "").strip()
            if content:
                lines.append(f"{role}: {content}")
        block = "\n".join(lines).strip()
        if not block:
            continue
        remaining = max(0, int(max_chars or 0)) - used
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[: max(0, remaining - 1)].rstrip() + "…"
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def history_hit_source(hit: dict, *, query: str, round_number: int) -> dict:
    """Return content-free provenance for /sources and feedback diagnostics."""

    message_ids = [
        str(row.get("message_id", ""))
        for row in hit.get("rows", [])
        if row.get("message_id")
    ]
    return {
        "kind": "conversation-history",
        "schema": EPISODIC_HISTORY_SCHEMA,
        "conversation_id": hit.get("conversation_id", ""),
        "title": hit.get("conversation_title", ""),
        "updated": hit.get("conversation_updated", ""),
        "start_ordinal": hit.get("start_ordinal"),
        "end_ordinal": hit.get("end_ordinal"),
        "window_ids": hit.get("window_ids", []),
        "message_ids": message_ids,
        "score": hit.get("score", 0),
        "matched_terms": hit.get("matched_terms", 0),
        "selection": ["adaptive-recall"],
        "recall_round": round_number,
        "query_sha256": _sha256_text(str(query or "")),
    }


def adaptive_recall_plan_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "status": {
                "type": "string",
                "enum": ["sufficient", "need_more_context"],
            },
            "queries": {
                "type": "array",
                "maxItems": DEFAULT_MAX_QUERIES_PER_ROUND,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "query": {"type": "string"},
                        "scope": {
                            "type": "string",
                            "enum": sorted(_ALLOWED_SCOPES),
                        },
                        "purpose": {"type": "string"},
                    },
                    "required": ["query", "scope", "purpose"],
                },
            },
        },
        "required": ["status", "queries"],
    }


def _extract_json_object(text: str) -> dict | None:
    value = str(text or "").strip()
    if not value:
        return None
    if "```" in value:
        blocks = re.findall(r"```(?:json)?\s*(.*?)```", value, flags=re.IGNORECASE | re.DOTALL)
        if blocks:
            value = blocks[0].strip()
    else:
        start = value.find("{")
        end = value.rfind("}")
        if start >= 0 and end > start:
            value = value[start : end + 1]
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def normalize_adaptive_recall_plan(
    value,
    *,
    max_queries: int = DEFAULT_MAX_QUERIES_PER_ROUND,
    max_query_chars: int = DEFAULT_MAX_QUERY_CHARS,
) -> dict:
    if isinstance(value, str):
        value = _extract_json_object(value)
    if not isinstance(value, dict):
        return {"status": "sufficient", "queries": [], "invalid": True}

    status = str(value.get("status", "sufficient") or "sufficient")
    if status not in {"sufficient", "need_more_context"}:
        status = "sufficient"

    rows = []
    seen = set()
    for item in value.get("queries", []) if isinstance(value.get("queries"), list) else []:
        if isinstance(item, str):
            item = {"query": item, "scope": "current_conversation", "purpose": ""}
        if not isinstance(item, dict):
            continue
        query = " ".join(str(item.get("query", "") or "").split())[:max_query_chars].strip()
        if not query:
            continue
        key = query.casefold()
        if key in seen:
            continue
        seen.add(key)
        scope = str(item.get("scope", "current_conversation") or "current_conversation")
        if scope not in _ALLOWED_SCOPES:
            scope = "current_conversation"
        purpose = " ".join(str(item.get("purpose", "") or "").split())[:240].strip()
        rows.append({"query": query, "scope": scope, "purpose": purpose})
        if len(rows) >= max(0, int(max_queries or 0)):
            break

    if status == "need_more_context" and not rows:
        status = "sufficient"
    return {"status": status, "queries": rows, "invalid": False}


def adaptive_recall_planner_messages(
    *,
    user_query: str,
    seed_context: str,
    prior_evidence: str,
    prior_queries: Iterable[str],
    round_number: int,
) -> list[dict]:
    prior_query_text = "\n".join(f"- {query}" for query in prior_queries) or "(none)"
    evidence = prior_evidence.strip() or "(none yet)"
    prompt = f"""User question:
{user_query}

Selected current context:
{seed_context or '(none)'}

Queries already tried:
{prior_query_text}

Raw conversation evidence recovered so far:
{evidence}

This is adaptive-recall round {round_number}.
"""
    instruction = """You are Motoko's bounded episodic-recall planner, not the final answerer.
Decide only whether the currently supplied context is sufficient to answer the
user carefully. If an important factual or historical gap remains, formulate up
to three standalone search queries for raw prior conversation history.

Queries should target concrete missing facts, events, previous patterns,
statements, decisions, dates, or comparisons that could materially change the
answer. Prefer current_conversation when the missing evidence should be in this
thread; use all_conversations only when earlier chats may matter. Reformulate a
query if an earlier search returned no useful evidence.

Do not provide an answer to the user and do not provide hidden reasoning.
Return only the structured retrieval decision."""
    return [
        {"role": "system", "content": instruction},
        {"role": "user", "content": prompt},
    ]


def _dedupe_sources(sources: Iterable[dict]) -> list[dict]:
    result = []
    seen = set()
    for source in sources:
        key = (
            source.get("kind"),
            source.get("round"),
            source.get("conversation_id"),
            source.get("start_ordinal"),
            source.get("end_ordinal"),
            tuple(source.get("message_ids", [])),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result


def adaptive_recall_needed(conv: dict) -> bool:
    """Avoid an extra planner call until there is history outside active turns."""

    archive_conversation_messages(conv)
    rows = history_rows(str(conv.get("id", "") or ""))
    active = len(_message_rows(conv.get("messages", [])))
    state = ensure_context_window_state(conv)
    return bool(
        conv.get("summary")
        or int(state.get("window_number", 0) or 0) > 0
        or len(rows) > active
    )


def run_adaptive_recall(
    *,
    conv: dict,
    conversations: Iterable[dict],
    user_query: str,
    seed_context: str,
    planner: Callable[[list[dict], dict, int], str | dict],
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    max_queries_per_round: int = DEFAULT_MAX_QUERIES_PER_ROUND,
    results_per_query: int = DEFAULT_RESULTS_PER_QUERY,
    context_radius: int = DEFAULT_CONTEXT_RADIUS,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
) -> AdaptiveRecallResult:
    """Run a bounded model-directed retrieve/inspect/retrieve loop."""

    if not user_query.strip() or not adaptive_recall_needed(conv):
        return AdaptiveRecallResult(
            diagnostics={
                "schema": ADAPTIVE_RECALL_SOURCE_SCHEMA,
                "status": "not-needed",
                "rounds": 0,
                "hit_count": 0,
            }
        )

    all_conversations = [row for row in conversations if isinstance(row, dict)]
    if not any(str(row.get("id", "")) == str(conv.get("id", "")) for row in all_conversations):
        all_conversations.append(conv)

    accumulated_hits: list[dict] = []
    accumulated_sources: list[dict] = []
    plans: list[dict] = []
    prior_queries: list[str] = []
    prior_evidence = ""
    remaining_chars = max(0, int(max_context_chars or 0))

    for round_number in range(1, max(0, int(max_rounds or 0)) + 1):
        planner_messages = adaptive_recall_planner_messages(
            user_query=user_query,
            seed_context=seed_context,
            prior_evidence=prior_evidence,
            prior_queries=prior_queries,
            round_number=round_number,
        )
        raw_plan = planner(planner_messages, adaptive_recall_plan_schema(), round_number)
        plan = normalize_adaptive_recall_plan(raw_plan, max_queries=max_queries_per_round)
        plans.append(plan)
        planner_source = {
            "kind": "adaptive-recall",
            "schema": ADAPTIVE_RECALL_SOURCE_SCHEMA,
            "round": round_number,
            "status": plan.get("status", ""),
            "query_count": len(plan.get("queries", [])),
            # Keep /sources and saved answer diagnostics content-free.
            # Full structured plans remain in the ephemeral AdaptiveRecallResult.
            "query_scopes": [item.get("scope", "") for item in plan.get("queries", [])],
            "query_hashes": [
                _sha256_text(str(item.get("query", "") or ""))
                for item in plan.get("queries", [])
            ],
            "hit_count": 0,
        }
        accumulated_sources.append(planner_source)
        if plan.get("status") != "need_more_context":
            break

        round_hits = []
        for item in plan.get("queries", []):
            query = item.get("query", "")
            prior_queries.append(query)
            hits = search_conversation_history(
                all_conversations,
                query,
                current_conversation_id=str(conv.get("id", "") or ""),
                scope=item.get("scope", "current_conversation"),
                limit=results_per_query,
                context_radius=context_radius,
            )
            round_hits.extend(hits)
            accumulated_sources.extend(
                history_hit_source(hit, query=query, round_number=round_number)
                for hit in hits
            )
        planner_source["hit_count"] = len(round_hits)
        if not round_hits:
            prior_evidence = (
                prior_evidence
                + ("\n\n" if prior_evidence else "")
                + f"Round {round_number}: no raw history matched the requested searches."
            )
            continue

        round_text = format_history_hits(round_hits, max_chars=remaining_chars)
        if round_text:
            prior_evidence = (
                prior_evidence + ("\n\n" if prior_evidence else "") + round_text
            )
            remaining_chars = max(0, remaining_chars - len(round_text))
        accumulated_hits.extend(round_hits)
        if remaining_chars <= 0:
            break

    evidence_text = format_history_hits(accumulated_hits, max_chars=max_context_chars)
    sources = _dedupe_sources(accumulated_sources)
    return AdaptiveRecallResult(
        text=evidence_text,
        sources=sources,
        plans=plans,
        diagnostics={
            "schema": ADAPTIVE_RECALL_SOURCE_SCHEMA,
            "status": "retrieved" if evidence_text else "no-evidence",
            "rounds": len(plans),
            "hit_count": len(
                [source for source in sources if source.get("kind") == "conversation-history"]
            ),
            "query_count": len(prior_queries),
        },
    )
