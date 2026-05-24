"""Pure retrieval scoring helpers for Motoko."""

from __future__ import annotations

import collections
import hashlib
import json
import pathlib
import re

from motoko_core.text import compact_source_text_middle, compact_text, compact_text_middle


SPAN_SELECTION_MAX_CANDIDATES = 32


def token_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_'-]{3,}", text.lower())


def token_counts(text: str) -> collections.Counter:
    return collections.Counter(token_words(text))


def score_text(query_counts: collections.Counter, text: str) -> int:
    if not query_counts:
        return 0
    counts = token_counts(text)
    if not counts:
        return 0
    doc_len = max(1, sum(counts.values()))
    avg_len = 400
    k1 = 1.2
    b = 0.75
    score = 0.0
    for word, query_count in query_counts.items():
        tf = counts.get(word, 0)
        if not tf:
            continue
        saturation = (tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b + b * doc_len / avg_len))
        weight = 1.15 if len(word) >= 7 else 1.0
        score += weight * saturation * min(query_count, 2)
    query_terms = list(query_counts)
    if len(query_terms) >= 2:
        lowered = " ".join(token_words(text))
        for left, right in zip(query_terms, query_terms[1:]):
            if f"{left} {right}" in lowered:
                score += 0.5
    return int(round(score * 10))


def retrieval_haystack_terms(query_counts: collections.Counter, text: str) -> list[str]:
    if not query_counts:
        return []
    counts = token_counts(text)
    return [term for term in query_counts if counts.get(term)]


def unavailable_context_source(kind: str, item: dict, exc: BaseException) -> dict:
    return {
        "kind": "context-warning",
        "context_kind": kind,
        "id": item.get("id", ""),
        "path": item.get("path", ""),
        "warning": str(exc),
    }


def repo_context_text_and_source(item: dict) -> tuple[str, dict]:
    label = f"{item.get('command', 'repo')} {item.get('root', '')}".strip()
    content = item.get("content", "")
    return (
        f"--- [repo:{label}] ---\n{content}",
        {
            "kind": "repo",
            "command": item.get("command", ""),
            "root": item.get("root", ""),
            "bytes": item.get("bytes", 0),
            "created": item.get("created", ""),
        },
    )


def file_context_text_and_source(item: dict) -> tuple[str, dict]:
    label = item.get("path", "context")
    content = item.get("content", "")
    return (
        f"--- [file:{label}] {label} ---\n{content}",
        {
            "kind": "file",
            "path": label,
            "bytes": item.get("bytes", 0),
        },
    )


def render_context_items_with_sources(
    items: list[dict],
    query: str = "",
    *,
    load_index,
    render_index_query,
    render_index_overview,
    load_topic,
    render_topic,
    load_dossier,
    render_dossier,
) -> tuple[str, list[dict]]:
    if not items:
        return "No explicit documents are attached.", []
    parts = []
    sources = []
    warning_exceptions = (KeyError, SystemExit, OSError, json.JSONDecodeError)
    for item in items:
        kind = item.get("kind")
        if kind == "index":
            try:
                index = load_index(item["id"])
            except warning_exceptions as exc:
                sources.append(unavailable_context_source("index", item, exc))
                continue
            text, index_sources = render_index_query(index, query) if query else render_index_overview(index)
            parts.append(text)
            sources.extend(index_sources)
            continue
        if kind == "topic":
            try:
                topic = load_topic(item["id"])
            except warning_exceptions as exc:
                sources.append(unavailable_context_source("topic", item, exc))
                continue
            text, topic_sources = render_topic(topic, query)
            parts.append(text)
            sources.extend(topic_sources)
            continue
        if kind == "dossier":
            try:
                dossier = load_dossier(item["id"])
            except warning_exceptions as exc:
                sources.append(unavailable_context_source("dossier", item, exc))
                continue
            text, dossier_sources = render_dossier(dossier, query)
            parts.append(text)
            sources.extend(dossier_sources)
            continue
        if kind == "repo":
            text, source = repo_context_text_and_source(item)
        else:
            text, source = file_context_text_and_source(item)
        parts.append(text)
        sources.append(source)
    return "\n\n".join(parts), sources


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def query_needs_grounded_sources_core(
    query: str,
    *,
    grounding_query_words: set[str],
    task_query_words: set[str],
) -> bool:
    terms = set(token_counts(query))
    return bool(query_path_mentions(query) or (terms & grounding_query_words) or (terms & task_query_words))


def answer_grounding_audit_core(
    query: str,
    reply: str,
    sources: list[dict],
    *,
    schema_version: str,
    created: str,
    grounding_query_words: set[str],
    task_query_words: set[str],
    strong_source_kinds: set[str],
    context_source_kinds: set[str],
) -> dict:
    clean_sources = [source for source in sources if source.get("kind") != "answer-audit"]
    kinds = collections.Counter(source.get("kind", "unknown") for source in clean_sources)
    strong_count = sum(kinds.get(kind, 0) for kind in strong_source_kinds)
    context_count = sum(kinds.get(kind, 0) for kind in context_source_kinds)
    needs_grounding = query_needs_grounded_sources_core(
        query,
        grounding_query_words=grounding_query_words,
        task_query_words=task_query_words,
    )
    freshness_warnings = []
    for source in clean_sources:
        status = str(source.get("status", ""))
        if status == "stale":
            label = source.get("path") or source.get("root") or source.get("id") or source.get("kind", "source")
            freshness_warnings.append(f"{label}: stale")
        for warning in source.get("warnings", []) or []:
            freshness_warnings.append(str(warning))
    paths = []
    seen_paths = set()
    for source in clean_sources:
        path = str(source.get("path") or source.get("root") or "").strip()
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        paths.append(path)
    if strong_count:
        status = "warn" if freshness_warnings else "pass"
        reflection = "answer had retrieved source excerpts or explicit attached evidence available"
        action = "check cited paths if the answer is high impact" if freshness_warnings else "no immediate action"
    elif context_count:
        status = "partial"
        reflection = "answer had summaries, memories, or dossier context but no retrieved excerpt-level evidence"
        action = "run /study for precise source excerpts if details matter"
    elif needs_grounding:
        status = "fail"
        reflection = "question appeared to need document or task grounding, but no usable source context was selected"
        action = "attach or study the relevant corpus before trusting the answer"
    else:
        status = "thin"
        reflection = "answer was mostly conversational and did not use retrieved external evidence"
        action = "no action unless the answer should have used private context"
    return {
        "kind": "answer-audit",
        "artifact_schema": schema_version,
        "created": created,
        "status": status,
        "strong_evidence_sources": strong_count,
        "context_sources": context_count,
        "total_sources": len(clean_sources),
        "source_kinds": dict(sorted(kinds.items())),
        "needs_grounding": needs_grounding,
        "freshness_warning_count": len(freshness_warnings),
        "warnings": freshness_warnings[:8],
        "paths": paths[:12],
        "query_sha256": sha256_text(query),
        "answer_sha256": sha256_text(reply),
        "reflection": reflection,
        "recommended_action": action,
    }


def sources_with_answer_audit_core(
    query: str,
    reply: str,
    sources: list[dict],
    **audit_kwargs,
) -> list[dict]:
    clean_sources = [source for source in sources if source.get("kind") != "answer-audit"]
    return clean_sources + [
        answer_grounding_audit_core(query, reply, clean_sources, **audit_kwargs)
    ]


def context_plan_from_lanes_core(lanes: list[dict], *, budget_chars: int) -> dict:
    total_chars = sum(int(lane.get("chars", 0) or 0) for lane in lanes)
    return {
        "kind": "context-plan",
        "budget_chars": budget_chars,
        "total_chars": total_chars,
        "status": "over-budget" if total_chars > budget_chars else "ok",
        "lanes": lanes,
    }


def format_context_plan_core(plan: dict, *, default_budget_chars: int) -> str:
    lines = [
        (
            "Context plan: "
            f"{plan.get('total_chars', 0)}/{plan.get('budget_chars', default_budget_chars)} "
            f"chars ({plan.get('status', 'unknown')})"
        )
    ]
    for lane in plan.get("lanes", []):
        lines.append(
            f"- {lane.get('lane')}: {lane.get('chars', 0)} chars, "
            f"{lane.get('sources', 0)} source(s), {lane.get('purpose', '')}"
        )
    return "\n".join(lines)


def context_sufficiency_note_core(
    sources: list[dict],
    *,
    has_conversation_summary: bool,
    ranked_topics: list[dict],
    ranked_dossiers: list[dict],
    best_index: dict | None,
    attached_topic_ids: set[str],
    attached_dossier_ids: set[str],
    study_reuse_min_score: int,
) -> str:
    kinds = collections.Counter(source.get("kind", "unknown") for source in sources)
    has_deep_context = any(
        kind in kinds
        for kind in (
            "dossier",
            "dossier-memory",
            "dossier-conversation",
            "topic",
            "topic-evidence",
            "chunk",
            "index",
        )
    )
    if has_deep_context:
        status = "likely enough for a grounded answer if the selected sources match the question"
    elif kinds.get("memory", 0) or kinds.get("recent-conversation", 0) or has_conversation_summary:
        status = "partial; answer from available memory, but suggest /study if details matter"
    else:
        status = "thin; say what is missing and suggest /study or attaching/indexing documents"

    reusable = []
    topic = next((row for row in ranked_topics if row.get("_score", 0) >= study_reuse_min_score), None)
    dossier = next((row for row in ranked_dossiers if row.get("_score", 0) >= study_reuse_min_score), None)
    if topic and topic.get("id") not in attached_topic_ids:
        reusable.append(f"existing topic dossier {topic.get('id')}")
    if dossier and dossier.get("id") not in attached_dossier_ids:
        reusable.append(f"existing memory dossier {dossier.get('id')}")
    if best_index:
        reusable.append(f"document index {best_index.get('id')}")
    action = "; relevant stored context: " + ", ".join(reusable) if reusable else ""
    return f"Context sufficiency: {status}.{action}"


def extract_prompt_section_core(prompt: str, heading: str, stop_headings: list[str]) -> str:
    start_marker = f"{heading}:\n"
    start = prompt.find(start_marker)
    if start < 0:
        return ""
    start += len(start_marker)
    stop = len(prompt)
    for stop_heading in stop_headings:
        marker = f"\n\n{stop_heading}:"
        found = prompt.find(marker, start)
        if found >= 0:
            stop = min(stop, found)
    return prompt[start:stop].strip()


def format_source_kind_counts_core(source_kinds: dict) -> str:
    if not source_kinds:
        return "-"
    return ", ".join(f"{kind}={count}" for kind, count in sorted(source_kinds.items()))


def bounded_retrieval_preview_text(text: str, max_chars: int) -> str:
    text = text.rstrip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + f"\n... truncated after {max_chars} characters ..."


def format_retrieval_preview_core(
    query: str,
    *,
    audit: dict,
    context_plan: dict | None,
    formatted_context_plan: str,
    formatted_sources: str,
    attached_context: str,
    max_chars: int,
) -> str:
    lines = [
        f"retrieval preview: {compact_text(query, 180)}",
        (
            f"source audit: {audit.get('status', 'unknown')}  "
            f"strong {audit.get('strong_evidence_sources', 0)}  "
            f"context {audit.get('context_sources', 0)}  "
            f"total {audit.get('total_sources', 0)}"
        ),
        f"source kinds: {format_source_kind_counts_core(audit.get('source_kinds', {}))}",
    ]
    if audit.get("warnings"):
        for warning in audit.get("warnings", [])[:4]:
            lines.append(f"warning: {warning}")
    if context_plan:
        lines.extend(["", formatted_context_plan])
    lines.extend(
        [
            "",
            "sources:",
            formatted_sources,
            "",
            "attached context excerpt:",
            bounded_retrieval_preview_text(
                attached_context or "No explicit documents, indexes, topics, or dossiers were selected.",
                max_chars,
            ),
            "",
            "diagnosis guide: if the right excerpt is absent, investigate recall/ranking/staleness with /retrieval-debug. If it is present but the answer was weak, investigate prompt/final synthesis.",
        ]
    )
    return "\n".join(lines)


def format_retrieval_eval_report_core(report: dict) -> str:
    lines = [
        f"retrieval eval: {report.get('status', 'unknown')} "
        f"({report.get('passed', 0)}/{report.get('total', 0)})",
        f"id: {report.get('id', '')}",
    ]
    if report.get("saved_path"):
        lines.append(f"saved: {report.get('saved_path')}")
    for row in report.get("fixtures", []):
        lines.append(
            f"- {row.get('status', 'unknown')}: {row.get('id', '')} "
            f"chunks {row.get('chunk_source_count', 0)} "
            f"audit {row.get('answer_audit_status', '')}"
        )
        lines.append("  selected: " + (", ".join(row.get("selected_paths", [])[:4]) or "-"))
        details = []
        if row.get("missing_paths"):
            details.append("missing paths " + ", ".join(row.get("missing_paths", [])[:6]))
        if row.get("missing_terms"):
            details.append("missing terms " + ", ".join(row.get("missing_terms", [])[:6]))
        if details:
            lines.append("  " + "; ".join(details))
    return "\n".join(lines)


def format_retrieval_debug_report_core(report: dict) -> str:
    lines = [
        f"retrieval debug: {report.get('query', '')}",
        f"id: {report.get('id', '')}",
        "query terms: " + (", ".join(report.get("query_terms", [])) or "-"),
    ]
    if report.get("path_mentions"):
        lines.append("path mentions: " + ", ".join(report.get("path_mentions", [])))
    if report.get("saved_path"):
        lines.append(f"saved: {report.get('saved_path')}")
    if not report.get("indexes"):
        lines.append("no indexes available; attach or build an index first")
        return "\n".join(lines)
    lines.append(
        "guide: no relevant file means recall; wrong top chunk means ranking; warnings mean stale data; "
        "right chunk but bad answer means prompt/final synthesis"
    )
    for index in report.get("indexes", []):
        lines.append(
            f"\nindex {index.get('id', '')}  {index.get('freshness', 'unknown')}  "
            f"{index.get('files_considered', 0)} file(s)  {index.get('chunks_considered', 0)} chunk(s)  "
            f"{index.get('name', '')}  {index.get('root', '')}"
        )
        lines.append(f"  production: {index.get('production_retrieval', 'hybrid retrieval')}")
        for warning in index.get("warnings", [])[:3]:
            lines.append(f"  warning: {warning}")
        for note in index.get("diagnosis", []):
            lines.append(f"  diagnosis: {note}")
        lines.append("  top files:")
        for idx, row in enumerate(index.get("files", [])[:5], 1):
            lines.append(
                f"    {idx}. total={row.get('total', 0)} lex={row.get('lexical', 0)} "
                f"path={row.get('path_boost', 0)} task={row.get('file_task_boost', 0)} "
                f"{row.get('freshness', 'unknown')}  {row.get('path', '')}"
            )
            if row.get("matched_terms"):
                lines.append("       matched: " + ", ".join(row.get("matched_terms", [])[:12]))
            if row.get("summary_matched_terms") or row.get("content_matched_terms"):
                lines.append(
                    "       matched by: "
                    f"summary={','.join(row.get('summary_matched_terms', [])[:8]) or '-'} "
                    f"content={','.join(row.get('content_matched_terms', [])[:8]) or '-'}"
                )
            if row.get("summary"):
                lines.append("       summary: " + row.get("summary", ""))
        lines.append("  top chunks:")
        for idx, row in enumerate(index.get("chunks", [])[:8], 1):
            lines.append(
                f"    {idx}. total={row.get('total', 0)} lex={row.get('lexical', 0)} "
                f"path={row.get('path_boost', 0)} file_task={row.get('file_task_boost', 0)} "
                f"chunk_task={row.get('chunk_task_boost', 0)} chars={row.get('content_chars', 0)}  "
                f"{row.get('path', '')} chunk {row.get('chunk', '')}"
            )
            if row.get("matched_terms"):
                lines.append("       matched: " + ", ".join(row.get("matched_terms", [])[:12]))
            if row.get("summary"):
                lines.append("       summary: " + row.get("summary", ""))
        if index.get("evidence_store"):
            store = index.get("evidence_store", {})
            lines.append(f"  evidence store: {store.get('id', '')} freshness={store.get('freshness', '')}")
        for warning in index.get("evidence_warnings", [])[:3]:
            lines.append(f"  evidence warning: {warning}")
        if index.get("evidence_error"):
            lines.append(f"  evidence error: {index.get('evidence_error')}")
        if index.get("evidence_rows"):
            lines.append("  top evidence rows:")
            for idx, row in enumerate(index.get("evidence_rows", [])[:8], 1):
                lines.append(
                    f"    {idx}. total={row.get('total', 0)} lex={row.get('lexical', 0)} "
                    f"path={row.get('path_boost', 0)} structured={row.get('structured', 0)} "
                    f"{row.get('kind', '')}  {row.get('path', '')} chunk {row.get('chunk', '')}"
                )
                labels = []
                if row.get("date"):
                    labels.append(f"date={row.get('date')}")
                if row.get("todo"):
                    labels.append(f"todo={row.get('todo')}")
                if row.get("priority"):
                    labels.append(f"priority={row.get('priority')}")
                if row.get("title"):
                    labels.append(f"title={row.get('title')}")
                if labels:
                    lines.append("       " + "  ".join(labels))
                if row.get("matched_terms"):
                    lines.append("       matched: " + ", ".join(row.get("matched_terms", [])[:12]))
                if row.get("text"):
                    lines.append("       text: " + compact_text(row.get("text", ""), 220))
        if index.get("vector_store"):
            store = index.get("vector_store", {})
            lines.append(
                f"  vector store: {store.get('id', '')} method={store.get('method', '')} "
                f"rerank={store.get('rerank', False)} fallback={store.get('rerank_fallback', False)}"
            )
        for warning in index.get("vector_warnings", [])[:3]:
            lines.append(f"  vector warning: {warning}")
        if index.get("vector_error"):
            lines.append(f"  vector error: {index.get('vector_error')}")
        if index.get("vector_chunks"):
            lines.append("  top vector chunks:")
            for idx, row in enumerate(index.get("vector_chunks", [])[:8], 1):
                lines.append(
                    f"    {idx}. score={row.get('score', 0)} vec={row.get('vector_score', 0)} "
                    f"lex={row.get('lexical', 0)} path={row.get('path_boost', 0)}  "
                    f"{row.get('path', '')} chunk {row.get('chunk', '')}"
                )
                if "rerank_score" in row:
                    lines.append(f"       rerank_score: {row.get('rerank_score', 0)}")
                if row.get("summary"):
                    lines.append("       summary: " + row.get("summary", ""))
    return "\n".join(lines)


def retrieval_score_parts(
    query: str,
    query_counts: collections.Counter,
    haystack: str,
    *,
    path: str = "",
    file_signals: dict | None = None,
    chunk_signals: dict | None = None,
    task_boost_fn=None,
) -> dict:
    lexical = score_text(query_counts, haystack)
    path_boost = query_path_match_boost(query, path)
    file_task_boost = task_boost_fn(query, file_signals or {}) if task_boost_fn else 0
    chunk_task_boost = task_boost_fn(query, chunk_signals or {}) if task_boost_fn else 0
    total = lexical + path_boost + file_task_boost + chunk_task_boost
    return {
        "total": total,
        "lexical": lexical,
        "path_boost": path_boost,
        "file_task_boost": file_task_boost,
        "chunk_task_boost": chunk_task_boost,
        "matched_terms": retrieval_haystack_terms(query_counts, haystack)[:24],
    }


def query_path_mentions(query: str) -> list[str]:
    mentions = []
    seen = set()
    for raw in re.findall(r"[A-Za-z0-9_./~+-]+\.[A-Za-z0-9][A-Za-z0-9._+-]*", query):
        value = raw.strip(".,;:()[]{}<>\"'").lower()
        if not value:
            continue
        name = pathlib.PurePosixPath(value).name
        if "." not in name:
            continue
        if value in seen:
            continue
        seen.add(value)
        mentions.append(value)
    return mentions


def query_path_match_boost(query: str, path: str) -> int:
    mentions = query_path_mentions(query)
    if not mentions or not path:
        return 0
    path_lower = path.lower()
    path_name = pathlib.PurePosixPath(path_lower).name
    boost = 0
    for mention in mentions:
        mention_name = pathlib.PurePosixPath(mention).name
        if path_lower == mention or path_lower.endswith("/" + mention):
            boost += 2500
        elif path_name == mention_name:
            boost += 2000
        elif mention in path_lower:
            boost += 1200
        elif mention_name and mention_name in path_name:
            boost += 800
    return boost


def query_date_mentions(query: str) -> list[str]:
    seen = set()
    dates = []
    for match in re.finditer(r"\b(\d{4}-\d{2}-\d{2})\b", query):
        value = match.group(1)
        if value not in seen:
            seen.add(value)
            dates.append(value)
    return dates


def query_requested_recent_section_count(query: str) -> int:
    lowered = query.lower()
    numbers = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
    }
    match = re.search(
        r"\blast\s+(\d+|one|two|three|four|five)\s+(?:day|days|entry|entries|date|dates)\b",
        lowered,
    )
    if match:
        raw = match.group(1)
        try:
            return max(1, min(int(raw), 7))
        except ValueError:
            return numbers.get(raw, 2)
    terms = set(token_counts(query))
    if {"today", "yesterday"} & terms:
        return 2
    if terms & {"latest", "recent", "newest"}:
        return 2
    return 0


def org_date_from_line(line: str) -> str:
    match = re.search(r"[<\[](\d{4}-\d{2}-\d{2})\b", line)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", line)
    return match.group(1) if match else ""


def org_dated_section_spans(content: str) -> list[dict]:
    headings = []
    offset = 0
    for line in content.splitlines(keepends=True):
        match = re.match(r"^(\*+)\s+(.*)$", line.rstrip())
        if match:
            headings.append(
                {
                    "start": offset,
                    "level": len(match.group(1)),
                    "date": org_date_from_line(line),
                }
            )
        offset += len(line)
    spans = []
    for idx, heading in enumerate(headings):
        if not heading.get("date"):
            continue
        end = len(content)
        for next_heading in headings[idx + 1 :]:
            if int(next_heading.get("level", 1) or 1) <= int(heading.get("level", 1) or 1):
                end = int(next_heading.get("start", end))
                break
        if end > int(heading.get("start", 0)):
            spans.append({**heading, "end": end})
    return spans


def prune_nested_same_date_spans(spans: list[dict]) -> list[dict]:
    rows = sorted(
        [dict(span) for span in spans if span.get("date")],
        key=lambda span: (
            str(span.get("date", "")),
            int(span.get("start", 0) or 0),
            -(int(span.get("end", 0) or 0) - int(span.get("start", 0) or 0)),
        ),
    )
    kept = []
    for span in rows:
        date = str(span.get("date", ""))
        start = int(span.get("start", 0) or 0)
        end = int(span.get("end", 0) or 0)
        nested = False
        for existing in kept:
            if str(existing.get("date", "")) != date:
                continue
            existing_start = int(existing.get("start", 0) or 0)
            existing_end = int(existing.get("end", 0) or 0)
            if start >= existing_start and end <= existing_end:
                nested = True
                break
        if not nested:
            kept.append(span)
    return sorted(kept, key=lambda span: int(span.get("start", 0) or 0))


def org_dated_sections_excerpt(content: str, dates: list[str], *, max_chars: int) -> str:
    if not dates:
        return ""
    wanted = set(dates)
    spans = [
        span
        for span in prune_nested_same_date_spans(org_dated_section_spans(content))
        if span.get("date") in wanted
    ]
    if not spans:
        return ""
    spans.sort(key=lambda span: (str(span.get("date", "")), int(span.get("start", 0))))
    blocks = [content[int(span["start"]) : int(span["end"])].strip() for span in spans]
    blocks = [block for block in blocks if block]
    if not blocks:
        return ""
    joined = "\n\n".join(blocks)
    if len(joined) <= max_chars:
        return joined
    per_block = max(240, max_chars // max(1, len(blocks)))
    return "\n\n".join(compact_text_middle(block, per_block) for block in blocks)[:max_chars].strip()


def recent_org_dated_sections_excerpt(content: str, count: int, *, max_chars: int) -> str:
    spans = org_dated_section_spans(content)
    if not spans:
        return ""
    dates = sorted({str(span.get("date", "")) for span in spans if span.get("date")})
    selected = dates[-max(1, min(count, len(dates))) :]
    return org_dated_sections_excerpt(content, selected, max_chars=max_chars)


def make_evidence_span(
    *,
    kind: str,
    label: str,
    start: int,
    end: int,
    text: str,
    base_score: float = 0,
) -> dict:
    text = text.strip()
    if not text:
        return {}
    return {
        "kind": kind,
        "label": label,
        "start": max(0, int(start or 0)),
        "end": max(0, int(end or 0)),
        "text": text,
        "base_score": float(base_score or 0),
    }


def mandatory_date_evidence_spans(query: str, content: str) -> list[dict]:
    dated_spans = prune_nested_same_date_spans(org_dated_section_spans(content))
    if not dated_spans:
        return []
    exact_dates = query_date_mentions(query)
    rows = []
    if exact_dates:
        wanted = set(exact_dates)
        for span in dated_spans:
            date = str(span.get("date", ""))
            if date not in wanted:
                continue
            text = content[int(span["start"]) : int(span["end"])].strip()
            item = make_evidence_span(
                kind="org-date-exact",
                label=date,
                start=int(span["start"]),
                end=int(span["end"]),
                text=text,
                base_score=4000,
            )
            if item:
                rows.append(item)
        return sorted(rows, key=lambda row: int(row.get("start", 0) or 0))
    recent_count = query_requested_recent_section_count(query)
    if not recent_count:
        return []
    dates_in_content = sorted({str(span.get("date", "")) for span in dated_spans if span.get("date")})
    recent_dates = set(dates_in_content[-max(1, min(recent_count, len(dates_in_content))) :])
    for span in dated_spans:
        date = str(span.get("date", ""))
        if date not in recent_dates:
            continue
        text = content[int(span["start"]) : int(span["end"])].strip()
        item = make_evidence_span(
            kind="org-date-recent",
            label=date,
            start=int(span["start"]),
            end=int(span["end"]),
            text=text,
            base_score=3500,
        )
        if item:
            rows.append(item)
    return sorted(rows, key=lambda row: int(row.get("start", 0) or 0))


def query_term_window_excerpt(query: str, content: str, *, max_chars: int) -> str:
    if len(content) <= max_chars:
        return content.strip()
    lower_content = content.lower()
    terms = [term for term in token_counts(query) if len(term) >= 4 and "." not in term]
    positions = [lower_content.find(term.lower()) for term in terms]
    positions = [pos for pos in positions if pos >= 0]
    if not positions:
        return content[:max_chars].strip()
    anchor = min(positions)
    start = max(0, anchor - max_chars // 3)
    end = min(len(content), start + max_chars)
    if end - start < max_chars:
        start = max(0, end - max_chars)
    return content[start:end].strip()


def heading_section_spans(content: str, *, style: str, max_level: int = 4) -> list[dict]:
    headings = []
    offset = 0
    for line in content.splitlines(keepends=True):
        stripped = line.rstrip()
        if style == "org":
            match = re.match(r"^(\*+)\s+(.*)$", stripped)
            if match:
                headings.append(
                    {
                        "start": offset,
                        "level": len(match.group(1)),
                        "label": compact_text(match.group(2).strip(), 120),
                    }
                )
        elif style == "markdown":
            match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if match:
                headings.append(
                    {
                        "start": offset,
                        "level": len(match.group(1)),
                        "label": compact_text(match.group(2).strip(), 120),
                    }
                )
        offset += len(line)
    spans = []
    for idx, heading in enumerate(headings):
        level = int(heading.get("level", 1) or 1)
        if level > max_level:
            continue
        end = len(content)
        for next_heading in headings[idx + 1 :]:
            if int(next_heading.get("level", 1) or 1) <= level:
                end = int(next_heading.get("start", end))
                break
        text = content[int(heading["start"]) : end].strip()
        span = make_evidence_span(
            kind=f"{style}-heading",
            label=str(heading.get("label", "")),
            start=int(heading["start"]),
            end=end,
            text=text,
            base_score=80 - (level * 4),
        )
        if span:
            spans.append(span)
    return spans


def window_evidence_spans(content: str, *, max_chars: int) -> list[dict]:
    text = content.strip()
    if not text:
        return []
    max_chars = max(240, int(max_chars or 240))
    if len(text) <= max_chars:
        span = make_evidence_span(
            kind="whole-chunk",
            label="whole chunk",
            start=0,
            end=len(content),
            text=text,
            base_score=10,
        )
        return [span] if span else []
    spans = []
    step = max(1, int(max_chars * 0.75))
    start = 0
    while start < len(content) and len(spans) < SPAN_SELECTION_MAX_CANDIDATES:
        end = min(len(content), start + max_chars)
        boundary = content.rfind("\n\n", start, end)
        if boundary > start + max_chars // 2:
            end = boundary
        text = content[start:end].strip()
        span = make_evidence_span(
            kind="text-window",
            label=f"chars {start}-{end}",
            start=start,
            end=end,
            text=text,
            base_score=5,
        )
        if span:
            spans.append(span)
        if end >= len(content):
            break
        start = max(start + step, end - max_chars // 4)
    if spans and spans[-1].get("end", 0) < len(content):
        tail_start = max(0, len(content) - max_chars)
        span = make_evidence_span(
            kind="text-window",
            label=f"tail chars {tail_start}-{len(content)}",
            start=tail_start,
            end=len(content),
            text=content[tail_start:].strip(),
            base_score=8,
        )
        if span:
            spans.append(span)
    return spans


def base_evidence_spans(query: str, content: str, *, max_chars: int) -> list[dict]:
    spans = []
    dates = query_date_mentions(query)
    for span in org_dated_section_spans(content):
        date = str(span.get("date", ""))
        if dates and date not in dates:
            continue
        if dates:
            text = content[int(span["start"]) : int(span["end"])].strip()
            item = make_evidence_span(
                kind="org-date-exact",
                label=date,
                start=int(span["start"]),
                end=int(span["end"]),
                text=text,
                base_score=4000,
            )
            if item:
                spans.append(item)
    recent_count = query_requested_recent_section_count(query)
    if recent_count:
        dated_spans = org_dated_section_spans(content)
        dates_in_content = sorted({str(span.get("date", "")) for span in dated_spans if span.get("date")})
        recent_dates = set(dates_in_content[-max(1, min(recent_count, len(dates_in_content))) :])
        for span in dated_spans:
            if span.get("date") not in recent_dates:
                continue
            text = content[int(span["start"]) : int(span["end"])].strip()
            item = make_evidence_span(
                kind="org-date-recent",
                label=str(span.get("date", "")),
                start=int(span["start"]),
                end=int(span["end"]),
                text=text,
                base_score=3500,
            )
            if item:
                spans.append(item)
    spans.extend(heading_section_spans(content, style="org"))
    spans.extend(heading_section_spans(content, style="markdown"))
    term_window = query_term_window_excerpt(query, content, max_chars=max_chars)
    if term_window:
        start = max(0, content.find(term_window[: min(len(term_window), 80)]))
        item = make_evidence_span(
            kind="term-window",
            label="query term window",
            start=start,
            end=start + len(term_window),
            text=term_window,
            base_score=60,
        )
        if item:
            spans.append(item)
    spans.extend(window_evidence_spans(content, max_chars=max_chars))
    deduped = []
    seen = set()
    for span in spans:
        text = str(span.get("text", "")).strip()
        digest = hashlib.sha256(text[:240].encode("utf-8")).hexdigest()
        key = (int(span.get("start", 0)), int(span.get("end", 0)), digest)
        if not text or key in seen:
            continue
        seen.add(key)
        deduped.append(span)
    return deduped


def score_evidence_spans(query: str, spans: list[dict]) -> list[dict]:
    query_counts = token_counts(query)
    rows = []
    for span in spans:
        row = dict(span)
        lexical = score_text(query_counts, str(span.get("text", "")))
        row["lexical_score"] = lexical
        row["score"] = float(span.get("base_score", 0) or 0) + lexical
        rows.append(row)
    rows.sort(key=lambda row: (float(row.get("score", 0) or 0), -int(row.get("start", 0) or 0)), reverse=True)
    return rows


def fit_evidence_spans_to_budget(spans: list[dict], *, max_chars: int) -> list[dict]:
    rows = [dict(span) for span in spans if str(span.get("text", "")).strip()]
    rows.sort(key=lambda row: int(row.get("start", 0) or 0))
    if not rows:
        return []
    max_chars = max(1, int(max_chars or 1))
    separator_chars = 2 * max(0, len(rows) - 1)
    total_chars = separator_chars + sum(len(str(row.get("text", "")).strip()) for row in rows)
    if total_chars <= max_chars:
        return rows
    per_span = max(180, (max_chars - separator_chars) // max(1, len(rows)))
    fitted = []
    for row in rows:
        text = str(row.get("text", "")).strip()
        item = dict(row)
        item["text"] = compact_source_text_middle(text, per_span)
        fitted.append(item)
    return fitted


def effective_evidence_span(span: dict) -> dict:
    row = dict(span)
    selected_text = str(row.get("selected_subspan_text", "") or "").strip()
    if selected_text:
        row["text"] = selected_text
        if row.get("selected_sub_start") is not None:
            row["start"] = int(row.get("selected_sub_start", row.get("start", 0)) or 0)
        if row.get("selected_sub_end") is not None:
            row["end"] = int(row.get("selected_sub_end", row.get("end", 0)) or 0)
    return row


def select_non_overlapping_spans(spans: list[dict], *, max_chars: int) -> list[dict]:
    selected = []
    used = 0
    for span in spans:
        row = effective_evidence_span(span)
        start = int(row.get("start", 0) or 0)
        end = int(row.get("end", 0) or 0)
        overlaps = any(start < int(row.get("end", 0) or 0) and end > int(row.get("start", 0) or 0) for row in selected)
        if overlaps:
            continue
        text = str(row.get("text", "")).strip()
        if not text:
            continue
        separator = 2 if selected else 0
        if selected and used + len(text) + separator > max_chars:
            continue
        if not selected and len(text) > max_chars:
            row["text"] = compact_source_text_middle(text, max_chars)
            return [row]
        selected.append(row)
        used += len(text) + separator
        if used >= max_chars or len(selected) >= 4:
            break
    if selected:
        return sorted(selected, key=lambda row: int(row.get("start", 0) or 0))
    return []


def query_aware_content_selection(
    query: str,
    content: str,
    max_chars: int,
    *,
    use_models: bool = False,
    model_scorer=None,
) -> dict:
    content = content.strip()
    if not content:
        return {"excerpt": "", "spans": [], "warnings": [], "method": "empty"}
    max_chars = max(1, int(max_chars or 1))
    mandatory_spans = mandatory_date_evidence_spans(query, content)
    if mandatory_spans:
        selected = fit_evidence_spans_to_budget(mandatory_spans, max_chars=max_chars)
        excerpt = "\n\n".join(str(span.get("text", "")).strip() for span in selected if span.get("text"))
        return {
            "excerpt": excerpt[:max_chars].strip(),
            "spans": [
                {
                    key: row.get(key)
                    for key in ["kind", "label", "start", "end", "score", "lexical_score"]
                    if row.get(key) is not None
                }
                for row in selected
            ],
            "warnings": [],
            "method": "date-span",
        }
    spans = score_evidence_spans(query, base_evidence_spans(query, content, max_chars=max_chars))
    warnings = []
    if use_models and model_scorer is not None:
        spans, warnings = model_scorer(query, spans)
    selected = select_non_overlapping_spans(spans, max_chars=max_chars)
    if not selected:
        fallback = query_term_window_excerpt(query, content, max_chars=max_chars)
        span = make_evidence_span(
            kind="term-window",
            label="fallback",
            start=max(0, content.find(fallback[: min(len(fallback), 80)])),
            end=max(0, content.find(fallback[: min(len(fallback), 80)])) + len(fallback),
            text=fallback,
            base_score=0,
        )
        selected = [span] if span else []
    excerpt = "\n\n".join(str(span.get("text", "")).strip() for span in selected if span.get("text"))
    return {
        "excerpt": excerpt[:max_chars].strip(),
        "spans": [
            {
                key: row.get(key)
                for key in [
                    "kind",
                    "label",
                    "start",
                    "end",
                    "score",
                    "lexical_score",
                    "span_vector_score",
                    "span_embedding_route",
                    "span_rerank_score",
                    "span_rerank_route",
                    "selected_sub_start",
                    "selected_sub_end",
                ]
                if row.get(key) is not None
            }
            for row in selected
        ],
        "warnings": warnings,
        "method": "model-span"
        if use_models and any(row.get("span_rerank_score") or row.get("span_vector_score") for row in selected)
        else "deterministic-span",
    }


def retrieval_chunk_key(file_item: dict, chunk: dict) -> tuple[str, str]:
    return file_item.get("path", ""), str(chunk.get("chunk", ""))


def add_hybrid_candidate(
    candidates: dict[tuple[str, str], dict],
    file_item: dict,
    chunk: dict,
    method: str,
    score: int | float,
    details: dict | None = None,
    *,
    evidence_context_limit: int = 8,
) -> dict:
    key = retrieval_chunk_key(file_item, chunk)
    row = candidates.get(key)
    if row is None:
        row = {
            "key": key,
            "file_item": file_item,
            "chunk": chunk,
            "methods": set(),
            "lexical_score": 0,
            "vector_score": None,
            "vector_rank_score": 0,
            "structured_score": 0,
            "path_boost": 0,
            "task_boost": 0,
            "evidence_score": 0,
            "evidence_rows": [],
            "score": 0,
        }
        candidates[key] = row
    row["methods"].add(method)
    details = details or {}
    numeric_score = float(score or 0)
    if method == "lexical":
        row["lexical_score"] = max(float(row.get("lexical_score", 0) or 0), numeric_score)
        row["path_boost"] = max(float(row.get("path_boost", 0) or 0), float(details.get("path_boost", 0) or 0))
        task_boost = float(details.get("file_task_boost", 0) or 0) + float(details.get("chunk_task_boost", 0) or 0)
        row["task_boost"] = max(float(row.get("task_boost", 0) or 0), task_boost)
    elif method == "vector":
        row["vector_rank_score"] = max(float(row.get("vector_rank_score", 0) or 0), numeric_score)
        if details.get("vector_score") is not None:
            row["vector_score"] = max(float(row.get("vector_score") or 0), float(details.get("vector_score") or 0))
        row["path_boost"] = max(float(row.get("path_boost", 0) or 0), float(details.get("path_boost", 0) or 0))
    elif method == "structured":
        row["structured_score"] = max(float(row.get("structured_score", 0) or 0), numeric_score)
        row["task_boost"] = max(float(row.get("task_boost", 0) or 0), numeric_score)
        if details.get("task"):
            row["structured_task"] = details.get("task")
    elif method in {"evidence", "temporal"}:
        row["evidence_score"] = max(float(row.get("evidence_score", 0) or 0), numeric_score)
        row["structured_score"] = max(float(row.get("structured_score", 0) or 0), float(details.get("structured", 0) or 0))
        row["path_boost"] = max(float(row.get("path_boost", 0) or 0), float(details.get("path_boost", 0) or 0))
        if details:
            current = list(row.get("evidence_rows", []) or [])
            current.append(details)
            current.sort(key=lambda item: float(item.get("total", 0) or 0), reverse=True)
            row["evidence_rows"] = current[: max(1, int(evidence_context_limit or 1))]
    row["score"] = max(float(row.get("score", 0) or 0), hybrid_candidate_base_score(row))
    return row


def hybrid_candidate_base_score(candidate: dict) -> float:
    return max(
        float(candidate.get("lexical_score", 0) or 0),
        float(candidate.get("vector_rank_score", 0) or 0),
        float(candidate.get("structured_score", 0) or 0),
        float(candidate.get("evidence_score", 0) or 0),
    )


def hybrid_candidate_guard_bonus(candidate: dict) -> float:
    path_boost = min(float(candidate.get("path_boost", 0) or 0), 2000.0)
    task_boost = min(float(candidate.get("task_boost", 0) or 0), 120.0)
    return path_boost + task_boost


def selected_evidence_excerpt(
    rows: list[dict],
    *,
    max_chars: int,
    evidence_context_limit: int = 8,
) -> tuple[str, list[dict]]:
    selected = []
    used = 0
    seen = set()
    for row in rows:
        text = str(row.get("text", "")).strip()
        if not text:
            continue
        key = (row.get("id"), row.get("start"), row.get("end"))
        if key in seen:
            continue
        seen.add(key)
        separator = 2 if selected else 0
        if selected and used + len(text) + separator > max_chars:
            continue
        item = dict(row)
        if not selected and len(text) > max_chars:
            item["text"] = compact_source_text_middle(text, max_chars)
            selected.append(item)
            break
        selected.append(item)
        used += len(text) + separator
        if len(selected) >= max(1, int(evidence_context_limit or 1)) or used >= max_chars:
            break
    excerpt = "\n\n".join(str(row.get("text", "")).strip() for row in selected)
    spans = [
        {
            "kind": row.get("kind", "evidence"),
            "label": row.get("title") or row.get("date") or row.get("id", ""),
            "start": row.get("start"),
            "end": row.get("end"),
            "evidence_id": row.get("id"),
            "date": row.get("date", ""),
            "todo": row.get("todo", ""),
            "priority": row.get("priority", ""),
        }
        for row in selected
    ]
    return excerpt[:max_chars].strip(), spans


def diagnose_retrieval_debug(index_report: dict, query: str) -> list[str]:
    notes = []
    chunks = index_report.get("chunks", [])
    files = index_report.get("files", [])
    positive_chunks = [row for row in chunks if int(row.get("total", 0) or 0) > 0]
    if index_report.get("freshness") == "stale":
        notes.append("stale data: refresh or rebuild this index before trusting source answers")
    if not chunks:
        notes.append("chunking failure: this index has no chunks to retrieve")
    elif not positive_chunks:
        notes.append("recall failure: no chunk had a positive score for this query")
    else:
        notes.append(f"recall ok: {len(positive_chunks)} positive chunk(s) before limit")
    if index_report.get("vector_chunks"):
        notes.append(f"vector recall available: {len(index_report.get('vector_chunks', []))} vector-ranked chunk(s)")
    elif index_report.get("vector_error"):
        notes.append(f"vector recall issue: {index_report.get('vector_error')}")
    mentions = query_path_mentions(query)
    if mentions:
        top_paths = [row.get("path", "").lower() for row in chunks[:3] + files[:3]]
        for mention in mentions:
            mention_name = pathlib.PurePosixPath(mention.lower()).name
            if not any(
                path.endswith("/" + mention.lower()) or pathlib.PurePosixPath(path).name == mention_name
                for path in top_paths
            ):
                notes.append(f"ranking/path issue: mentioned {mention} was not in the top displayed rows")
    if chunks and int(chunks[0].get("content_chars", 0) or 0) <= 0:
        notes.append("chunk content issue: top chunk has no stored text available")
    if chunks and int(chunks[0].get("content_chars", 0) or 0) > 0 and not chunks[0].get("summary"):
        notes.append("summary issue: top chunk has source text but no chunk summary")
    notes.append("prompt-use check: if /sources shows the right chunk but the answer ignores it, the issue is final synthesis/prompt use")
    return notes


def span_model_text(span: dict, *, input_chars_limit: int) -> str:
    kind = str(span.get("kind", "") or "").strip()
    label = str(span.get("label", "") or "").strip()
    text = str(span.get("text", "") or "").strip()
    limit = max(1, int(input_chars_limit or 1))
    prefix = ": ".join(part for part in [kind, label] if part)
    if not prefix:
        return compact_text_middle(text, limit)
    budget = max(120, limit - len(prefix) - 1)
    return (prefix + "\n" + compact_text_middle(text, budget))[:limit].strip()


def span_model_subspans(
    span: dict,
    *,
    input_chars_limit: int,
    max_subspans_per_parent: int,
) -> list[dict]:
    text = str(span.get("text", "") or "").strip()
    if not text:
        return []
    limit = max(1, int(input_chars_limit or 1))
    prefix = ": ".join(
        part
        for part in [
            str(span.get("kind", "") or "").strip(),
            str(span.get("label", "") or "").strip(),
        ]
        if part
    )
    budget = max(180, limit - len(prefix) - 20)
    start_offset = int(span.get("start", 0) or 0)
    if len(text) <= budget:
        row = dict(span)
        row["model_text"] = span_model_text(span, input_chars_limit=limit)
        row["parent_start"] = start_offset
        row["parent_end"] = int(span.get("end", 0) or 0)
        row["sub_start"] = start_offset
        row["sub_end"] = start_offset + len(text)
        return [row]
    rows = []
    step = max(1, int(budget * 0.75))
    local_start = 0
    max_rows = max(1, int(max_subspans_per_parent or 1))
    loop_limit = max(1, max_rows - 1)
    while local_start < len(text) and len(rows) < loop_limit:
        local_end = min(len(text), local_start + budget)
        boundary = text.rfind("\n\n", local_start, local_end)
        if boundary > local_start + budget // 2:
            local_end = boundary
        fragment = text[local_start:local_end].strip()
        if fragment:
            row = dict(span)
            row["kind"] = f"{span.get('kind', '')}-subspan".strip("-")
            row["parent_kind"] = span.get("kind")
            row["parent_label"] = span.get("label")
            row["parent_start"] = int(span.get("start", 0) or 0)
            row["parent_end"] = int(span.get("end", 0) or 0)
            row["label"] = str(span.get("label", "") or "")
            row["text"] = fragment
            row["sub_start"] = start_offset + local_start
            row["sub_end"] = start_offset + local_end
            row["model_text"] = span_model_text(row, input_chars_limit=limit)
            rows.append(row)
        if local_end >= len(text):
            break
        local_start = max(local_start + step, local_end - budget // 4)
    if rows and int(rows[-1].get("sub_end", 0) or 0) < start_offset + len(text) and len(rows) < max_rows:
        tail_start = max(0, len(text) - budget)
        row = dict(span)
        row["kind"] = f"{span.get('kind', '')}-subspan".strip("-")
        row["parent_kind"] = span.get("kind")
        row["parent_label"] = span.get("label")
        row["parent_start"] = int(span.get("start", 0) or 0)
        row["parent_end"] = int(span.get("end", 0) or 0)
        row["label"] = str(span.get("label", "") or "")
        row["text"] = text[tail_start:].strip()
        row["sub_start"] = start_offset + tail_start
        row["sub_end"] = start_offset + len(text)
        row["model_text"] = span_model_text(row, input_chars_limit=limit)
        rows.append(row)
    return rows


def model_span_rows_for_candidates(
    spans: list[dict],
    *,
    limit: int,
    max_subspans: int,
    input_chars_limit: int,
    max_subspans_per_parent: int,
) -> list[dict]:
    rows = []
    for span in spans[: max(0, int(limit or 0))]:
        for row in span_model_subspans(
            span,
            input_chars_limit=input_chars_limit,
            max_subspans_per_parent=max_subspans_per_parent,
        ):
            if len(rows) >= max(0, int(max_subspans or 0)):
                return rows
            rows.append(row)
    return rows
