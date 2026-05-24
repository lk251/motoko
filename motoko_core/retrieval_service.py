"""Live retrieval service boundary for Motoko."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from motoko_core.retrieval import (
    add_hybrid_candidate,
    file_context_text_and_source,
    hybrid_candidate_base_score,
    hybrid_candidate_guard_bonus,
    org_dated_section_spans,
    query_date_mentions,
    query_path_match_boost,
    query_path_mentions,
    query_requested_recent_section_count,
    repo_context_text_and_source,
    score_text,
    selected_evidence_excerpt,
    selected_temporal_evidence_excerpt,
    token_counts,
    unavailable_context_source,
)


RETRIEVAL_SERVICE_SCHEMA = "retrieval-service-v1"


@dataclass(frozen=True)
class RetrievalServiceResult:
    text: str
    sources: list[dict] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)


@dataclass(frozen=True)
class HybridRetrievalEnvironment:
    retrieval_limits: Callable[[str], tuple[int, int, int]]
    index_staleness: Callable[[dict], tuple[str, list[str]]]
    corpus_profile_text: Callable[[dict], str]
    format_signal_summary: Callable[..., str]
    read_chunk_content: Callable[[dict, dict], str]
    retrieval_score_parts: Callable[..., dict]
    retrieval_chunk_haystack: Callable[..., str]
    query_wants_task_context: Callable[[str], bool]
    task_signal_boost: Callable[[str, dict], int]
    format_ranked_task_items: Callable[[dict, str], str]
    add_structured_task_candidates: Callable[[dict, str, dict], None]
    evidence_enabled: Callable[[], bool]
    evidence_store_for_retrieval: Callable[[dict], dict]
    query_evidence_store: Callable[..., dict]
    vector_enabled: Callable[[], bool]
    latest_vector_store_for_index: Callable[..., dict | None]
    query_vector_store_for_retrieval: Callable[..., dict]
    hybrid_rerank_enabled: Callable[[], bool]
    hybrid_rerank_available: Callable[[], bool]
    rerank_documents: Callable[[str, list[str]], tuple[list[float], dict]]
    hybrid_candidate_document: Callable[[dict, dict, str], str]
    wants_deep_context: Callable[[str], bool]
    file_staleness: Callable[[dict], tuple[str, list[str]]]
    span_model_chunk_limit: Callable[[], int]
    query_aware_content_selection: Callable[..., dict]
    max_rerank_candidates: int
    evidence_query_limit: int
    evidence_context_limit: int
    vector_query_limit: int
    embedding_vector_method: str


def rerank_hybrid_candidates_with_environment(
    index: dict,
    query: str,
    candidates: dict[tuple[str, str], dict],
    env: HybridRetrievalEnvironment,
) -> tuple[list[dict], dict]:
    rows = list(candidates.values())
    for row in rows:
        row["hybrid_score"] = round(hybrid_candidate_base_score(row), 6)
    rows.sort(key=lambda row: (row.get("hybrid_score", 0), hybrid_candidate_guard_bonus(row)), reverse=True)
    report = {
        "mode": "hybrid",
        "candidate_count": len(rows),
        "rerank": False,
        "rerank_fallback": False,
        "warnings": [],
    }
    if not rows or not env.hybrid_rerank_enabled():
        return rows, report
    if not env.hybrid_rerank_available():
        report["rerank_fallback"] = True
        report["warnings"].append("hybrid rerank fallback: no configured /v1/rerank route")
        return rows, report
    rerank_rows = rows[: min(len(rows), env.max_rerank_candidates)]
    documents = [env.hybrid_candidate_document(index, row, query) for row in rerank_rows]
    try:
        scores, route_info = env.rerank_documents(query, documents)
    except SystemExit as exc:
        report["rerank_fallback"] = True
        report["warnings"].append(f"hybrid rerank fallback: {str(exc).splitlines()[0][:220]}")
        return rows, report
    report["rerank"] = True
    report["rerank_route"] = {
        "catalog_route": route_info.get("catalog_route") or route_info.get("route", ""),
        "model": route_info.get("model", ""),
    }
    for row, score in zip(rerank_rows, scores):
        row["rerank_score"] = round(float(score), 6)
        row["hybrid_score"] = round(
            (hybrid_candidate_base_score(row) * 0.2)
            + (float(score) * 1000)
            + hybrid_candidate_guard_bonus(row),
            6,
        )
    rerank_rows.sort(key=lambda row: (row.get("hybrid_score", 0), hybrid_candidate_base_score(row)), reverse=True)
    return rerank_rows + rows[len(rerank_rows) :], report


def _chunk_lookup(index: dict) -> dict[tuple[str, str], tuple[dict, dict]]:
    lookup: dict[tuple[str, str], tuple[dict, dict]] = {}
    for file_item in index.get("files", []):
        for chunk in file_item.get("chunks", []):
            lookup[(file_item.get("path", ""), str(chunk.get("chunk", "")))] = (file_item, chunk)
    return lookup


def _temporal_evidence_rows(index: dict, query: str, env: HybridRetrievalEnvironment) -> list[dict]:
    exact_dates = set(query_date_mentions(query))
    recent_count = query_requested_recent_section_count(query)
    if not exact_dates and not recent_count:
        return []
    rows = []
    query_counts = token_counts(query)
    path_mentions = query_path_mentions(query)
    for file_item in index.get("files", []):
        path = file_item.get("path", "")
        path_boost = query_path_match_boost(query, path)
        if path_mentions and path_boost <= 0:
            continue
        file_match = path_boost > 0 or score_text(query_counts, "\n".join([path, file_item.get("summary", "")])) > 0
        if not file_match and not exact_dates:
            continue
        for chunk in file_item.get("chunks", []):
            content = env.read_chunk_content(index, chunk)
            for span in org_dated_section_spans(content):
                date = str(span.get("date", ""))
                if not date:
                    continue
                text = content[int(span.get("start", 0) or 0) : int(span.get("end", 0) or 0)].strip()
                if not text:
                    continue
                rows.append(
                    {
                        "id": f"{path}#{chunk.get('chunk', '')}:date:{date}:{span.get('start', 0)}",
                        "kind": "org_date_exact" if exact_dates else "org_date_recent",
                        "path": path,
                        "chunk": chunk.get("chunk"),
                        "date": date,
                        "title": date,
                        "start": int(span.get("start", 0) or 0),
                        "end": int(span.get("end", 0) or 0),
                        "text": text,
                        "text_chars": len(text),
                        "path_boost": path_boost,
                        "structured": 7000 if exact_dates else 6000,
                        "total": (9000 if exact_dates else 8000) + path_boost,
                        "matched_terms": [term for term in query_counts if term in text.lower()][:16],
                    }
                )
    if exact_dates:
        wanted = exact_dates
    else:
        selected_dates = sorted({row.get("date", "") for row in rows if row.get("date")})
        wanted = set(selected_dates[-max(1, min(recent_count, len(selected_dates))) :])
    selected = [row for row in rows if row.get("date") in wanted]
    selected.sort(key=lambda row: (str(row.get("date", "")), int(row.get("start", 0) or 0)), reverse=True)
    return selected


def _candidate_temporal_dates(candidate: dict) -> set[str]:
    dates = set()
    for row in candidate.get("evidence_rows", []) or []:
        date = str(row.get("date", "")).strip()
        if date:
            dates.add(date)
    return dates


def _selected_candidates_with_required_temporal_dates(
    candidates: list[dict],
    *,
    limit: int,
    temporal_dates: list[str],
) -> list[dict]:
    selected = list(candidates[: max(0, int(limit or 0))])
    if not temporal_dates:
        return selected
    selected_keys = {tuple(row.get("key", ())) for row in selected}
    for date in temporal_dates:
        if any(date in _candidate_temporal_dates(row) for row in selected):
            continue
        for row in candidates:
            key = tuple(row.get("key", ()))
            if key in selected_keys:
                continue
            if date not in _candidate_temporal_dates(row):
                continue
            selected.append(row)
            selected_keys.add(key)
            break
    return selected


def retrieve_index_hybrid(index: dict, query: str, env: HybridRetrievalEnvironment) -> RetrievalServiceResult:
    """Run Motoko's hybrid document retrieval for one index.

    The root facade supplies live stores and model-route callbacks through
    ``env``. This service owns the retrieval algorithm and returns in-memory
    source records; it does not write observability or admin-owned logs.
    """

    query_counts = token_counts(query)
    top_files, top_chunks, max_retrieval_chars = env.retrieval_limits(query)
    index_status, index_warnings = env.index_staleness(index)
    profile_text = env.corpus_profile_text(index)
    file_rows = []
    chunk_rows = []
    for file_item in index.get("files", []):
        file_signal_text = env.format_signal_summary(file_item.get("signals") or {}, limit=12)
        file_score = score_text(
            query_counts,
            "\n".join([file_item.get("path", ""), file_item.get("summary", ""), file_signal_text]),
        )
        file_score += env.task_signal_boost(query, file_item.get("signals") or {})
        chunk_path_boost = 0
        for chunk in file_item.get("chunks", []):
            content = env.read_chunk_content(index, chunk)
            score_parts = env.retrieval_score_parts(
                query,
                query_counts,
                env.retrieval_chunk_haystack(file_item, chunk, content, query=query),
                path=file_item.get("path", ""),
                file_signals=file_item.get("signals") or {},
                chunk_signals=chunk.get("signals") or {},
            )
            chunk_path_boost = max(chunk_path_boost, int(score_parts.get("path_boost", 0) or 0))
            chunk_rows.append((score_parts.get("total", 0), file_item, chunk, score_parts))
        file_score += chunk_path_boost
        file_rows.append((file_score, file_item))

    file_rows.sort(key=lambda row: row[0], reverse=True)
    chunk_rows.sort(key=lambda row: row[0], reverse=True)
    selected_files = [row[1] for row in file_rows[:top_files] if row[0] > 0]
    candidates: dict[tuple[str, str], dict] = {}
    temporal_candidate_keys: set[tuple[str, str]] = set()
    lexical_candidates = [row for row in chunk_rows[: env.max_rerank_candidates] if row[0] > 0]
    if not lexical_candidates:
        lexical_candidates = chunk_rows[: min(2, len(chunk_rows))]
    for score, file_item, chunk, score_parts in lexical_candidates:
        add_hybrid_candidate(candidates, file_item, chunk, "lexical", score, score_parts)
    env.add_structured_task_candidates(index, query, candidates)
    lookup = _chunk_lookup(index)
    temporal_rows = _temporal_evidence_rows(index, query, env)
    temporal_dates = sorted({str(row.get("date", "")) for row in temporal_rows if row.get("date")}, reverse=True)
    for row in temporal_rows:
        found = lookup.get((row.get("path", ""), str(row.get("chunk", ""))))
        if not found:
            continue
        file_item, chunk = found
        add_hybrid_candidate(candidates, file_item, chunk, "temporal", row.get("total", 0), row)
        temporal_candidate_keys.add((file_item.get("path", ""), str(chunk.get("chunk", ""))))

    evidence_report = None
    evidence_warning = ""
    if env.evidence_enabled():
        try:
            evidence_store = env.evidence_store_for_retrieval(index)
            evidence_report = env.query_evidence_store(
                evidence_store,
                query,
                limit=max(top_chunks * 3, env.evidence_query_limit),
            )
        except SystemExit as exc:
            evidence_warning = str(exc).splitlines()[0][:240]
        else:
            for row in evidence_report.get("rows", [])[: max(top_chunks * 2, env.evidence_context_limit)]:
                found = lookup.get((row.get("path", ""), str(row.get("chunk", ""))))
                if not found:
                    continue
                file_item, chunk = found
                add_hybrid_candidate(candidates, file_item, chunk, "evidence", row.get("total", 0), row)

    vector_report = None
    vector_warning = ""
    if env.vector_enabled():
        vector_store = env.latest_vector_store_for_index(index, method=env.embedding_vector_method, fresh_only=True)
        if vector_store is not None:
            try:
                vector_report = env.query_vector_store_for_retrieval(
                    vector_store,
                    query,
                    limit=max(top_chunks, env.vector_query_limit, env.max_rerank_candidates),
                    check_freshness=False,
                    rerank=False,
                )
            except SystemExit as exc:
                vector_warning = str(exc).splitlines()[0][:240]
            else:
                for row in vector_report.get("rows", [])[: env.max_rerank_candidates]:
                    found = lookup.get((row.get("path", ""), str(row.get("chunk", ""))))
                    if not found:
                        continue
                    file_item, chunk = found
                    add_hybrid_candidate(candidates, file_item, chunk, "vector", row.get("score", 0), row)
    rerank_candidates = candidates
    if temporal_candidate_keys:
        rerank_candidates = {
            key: value
            for key, value in candidates.items()
            if key in temporal_candidate_keys
        }
    selected_candidates, hybrid_report = rerank_hybrid_candidates_with_environment(index, query, rerank_candidates, env)
    selected_candidate_rows = _selected_candidates_with_required_temporal_dates(
        selected_candidates,
        limit=top_chunks,
        temporal_dates=temporal_dates,
    )
    selected_chunks = [
        (
            candidate.get("hybrid_score", candidate.get("score", 0)),
            candidate.get("file_item", {}),
            candidate.get("chunk", {}),
            "hybrid",
            {
                "score": candidate.get("hybrid_score", candidate.get("score", 0)),
                "retrieval_methods": sorted(candidate.get("methods", [])),
                "lexical_score": candidate.get("lexical_score", 0),
                "structured_score": candidate.get("structured_score", 0),
                "evidence_score": candidate.get("evidence_score", 0),
                "evidence_rows": candidate.get("evidence_rows", []),
                "vector_score": candidate.get("vector_score"),
                "vector_rank_score": candidate.get("vector_rank_score", 0),
                "rerank_score": candidate.get("rerank_score"),
                "structured_task": candidate.get("structured_task", ""),
            },
        )
        for candidate in selected_candidate_rows
    ]

    parts = [
        f"=== Document index: {index.get('name', index.get('id'))} ===",
        f"Root: {index.get('root', '')}",
        f"Freshness: {index_status}",
        "Corpus summary:",
        index.get("corpus_summary", ""),
    ]
    if profile_text:
        parts.extend(["Corpus profile:", profile_text])
    signal_summary = index.get("signal_summary") or env.format_signal_summary(index.get("signals") or {}, limit=30)
    if signal_summary and env.query_wants_task_context(query):
        ranked_tasks = env.format_ranked_task_items(index, query)
        if ranked_tasks:
            parts.extend(["Ranked task candidates:", ranked_tasks])
        parts.extend(["Structured task signals:", signal_summary])
    if index_warnings:
        parts.append("Freshness warnings:\n" + "\n".join(f"- {warning}" for warning in index_warnings[:8]))
    if temporal_dates:
        parts.append(
            "Temporal selection:\n"
            "The query asked for recent dated Org sections from this source. "
            "Motoko selected these as the newest dates present in the matching file(s): "
            f"{', '.join(temporal_dates)}. "
            "Do not assume missing intervening calendar dates have entries."
        )
    index_source = {
        "kind": "index",
        "id": index.get("id", ""),
        "name": index.get("name", ""),
        "root": index.get("root", ""),
        "status": index_status,
        "warnings": index_warnings[:8],
        "retrieval": "deep" if env.wants_deep_context(query) else "normal",
        "corpus_profile_schema": index.get("corpus_profile_schema", ""),
        "retrieval_service_schema": RETRIEVAL_SERVICE_SCHEMA,
    }
    if temporal_dates:
        index_source["temporal_selected_dates"] = temporal_dates
    if hybrid_report:
        index_source["retrieval"] = "hybrid-deep" if env.wants_deep_context(query) else "hybrid"
        index_source["hybrid_candidates"] = hybrid_report.get("candidate_count", 0)
        index_source["hybrid_rerank"] = bool(hybrid_report.get("rerank"))
        if hybrid_report.get("rerank_fallback"):
            index_source["hybrid_rerank_fallback"] = True
        rerank_route = hybrid_report.get("rerank_route")
        if isinstance(rerank_route, dict) and rerank_route:
            index_source["hybrid_rerank_route"] = rerank_route.get("catalog_route", "")
        if hybrid_report.get("warnings"):
            index_source["warnings"] = index_source.get("warnings", []) + hybrid_report.get("warnings", [])[:4]
    if evidence_report:
        index_source["evidence_store"] = evidence_report.get("store_id", "")
        index_source["evidence_rows"] = len(evidence_report.get("rows", []))
        if evidence_report.get("warnings"):
            index_source["warnings"] = index_source.get("warnings", []) + evidence_report.get("warnings", [])[:4]
    elif evidence_warning:
        index_source["warnings"] = index_source.get("warnings", []) + [f"evidence retrieval skipped: {evidence_warning}"]
    if vector_report:
        index_source["vector_store"] = vector_report.get("store_id", "")
        index_source["vector_method"] = vector_report.get("method", "")
        index_source["vector_rows"] = len(vector_report.get("rows", []))
        if vector_report.get("warnings"):
            index_source["warnings"] = index_source.get("warnings", []) + vector_report.get("warnings", [])[:4]
        parts.append(
            "Hybrid retrieval:\n"
            f"- candidates {hybrid_report.get('candidate_count', 0) if hybrid_report else 0} "
            f"rerank {bool(hybrid_report.get('rerank')) if hybrid_report else False}\n"
            f"- evidence {evidence_report.get('store_id', '') if evidence_report else ''} "
            f"rows {len(evidence_report.get('rows', [])) if evidence_report else 0}\n"
            f"- store {vector_report.get('store_id', '')} "
            f"method {vector_report.get('method', '')} "
            f"rows {len(vector_report.get('rows', []))}"
        )
    elif vector_warning:
        index_source["warnings"] = index_source.get("warnings", []) + [f"vector retrieval skipped: {vector_warning}"]
    elif hybrid_report:
        parts.append(
            "Hybrid retrieval:\n"
            f"- candidates {hybrid_report.get('candidate_count', 0)} "
            f"rerank {bool(hybrid_report.get('rerank'))}\n"
            f"- evidence {evidence_report.get('store_id', '') if evidence_report else ''} "
            f"rows {len(evidence_report.get('rows', [])) if evidence_report else 0}"
        )
    sources = [index_source]
    if selected_files:
        parts.append("Relevant file summaries:")
        for file_item in selected_files:
            file_signal_text = env.format_signal_summary(file_item.get("signals") or {}, limit=12)
            signal_block = f"\nStructured signals:\n{file_signal_text}" if file_signal_text else ""
            parts.append(
                f"- [file:{file_item.get('path')}] {file_item.get('path')}:\n"
                f"{file_item.get('summary', '')}{signal_block}"
            )
            sources.append(
                {
                    "kind": "file-summary",
                    "index": index.get("id", ""),
                    "path": file_item.get("path", ""),
                    "status": env.file_staleness(file_item)[0],
                }
            )
    if selected_chunks:
        parts.append("Retrieved excerpts:")
        used = 0
        span_model_uses = 0
        span_model_limit = env.span_model_chunk_limit()
        for _score, file_item, chunk, retrieval_method, retrieval_details in selected_chunks:
            content = env.read_chunk_content(index, chunk)
            remaining = max_retrieval_chars - used
            if remaining <= 0:
                break
            use_span_models = span_model_uses < span_model_limit and len(content) > 4000
            if use_span_models:
                span_model_uses += 1
            evidence_rows = retrieval_details.get("evidence_rows", []) if isinstance(retrieval_details, dict) else []
            evidence_spans = []
            if evidence_rows:
                if "temporal" in retrieval_details.get("retrieval_methods", []):
                    excerpt, evidence_spans = selected_temporal_evidence_excerpt(
                        evidence_rows,
                        max_chars=remaining,
                        dates=temporal_dates,
                    )
                else:
                    excerpt, evidence_spans = selected_evidence_excerpt(evidence_rows, max_chars=remaining)
                excerpt_selection = {
                    "excerpt": excerpt,
                    "spans": evidence_spans,
                    "warnings": [],
                    "method": "evidence-store",
                }
            else:
                excerpt_selection = env.query_aware_content_selection(
                    query,
                    content,
                    remaining,
                    use_models=use_span_models,
                )
            excerpt = excerpt_selection.get("excerpt", "")
            used += len(excerpt)
            chunk_signal_text = env.format_signal_summary(chunk.get("signals") or {}, limit=12)
            signal_block = f"\n\nStructured signals:\n{chunk_signal_text}" if chunk_signal_text else ""
            parts.append(
                f"--- [index:{index.get('id')} file:{file_item.get('path')} chunk:{chunk.get('chunk')}] ---\n"
                f"Chunk summary:\n{chunk.get('summary', '')}\n\n"
                f"Excerpt:\n{excerpt}{signal_block}"
            )
            sources.append(
                {
                    "kind": "chunk",
                    "index": index.get("id", ""),
                    "path": file_item.get("path", ""),
                    "chunk": chunk.get("chunk"),
                    "retrieval": retrieval_method,
                    "score": retrieval_details.get("score", _score) if isinstance(retrieval_details, dict) else _score,
                    "hybrid_score": retrieval_details.get("score") if isinstance(retrieval_details, dict) else None,
                    "retrieval_methods": retrieval_details.get("retrieval_methods", []) if isinstance(retrieval_details, dict) else [],
                    "lexical_score": retrieval_details.get("lexical_score") if isinstance(retrieval_details, dict) else None,
                    "structured_score": retrieval_details.get("structured_score") if isinstance(retrieval_details, dict) else None,
                    "evidence_score": retrieval_details.get("evidence_score") if isinstance(retrieval_details, dict) else None,
                    "rerank_score": retrieval_details.get("rerank_score") if isinstance(retrieval_details, dict) else None,
                    "vector_score": retrieval_details.get("vector_score") if isinstance(retrieval_details, dict) else None,
                    "excerpt_selection": excerpt_selection.get("method", ""),
                    "excerpt_spans": excerpt_selection.get("spans", [])[:4],
                    "excerpt_warnings": excerpt_selection.get("warnings", [])[:4],
                    "evidence_rows": len(evidence_rows),
                    "evidence_id": evidence_spans[0].get("evidence_id", "") if evidence_rows and evidence_spans else "",
                    "evidence_kind": evidence_spans[0].get("kind", "") if evidence_rows and evidence_spans else "",
                    "evidence_title": evidence_spans[0].get("label", "") if evidence_rows and evidence_spans else "",
                    "evidence_date": evidence_spans[0].get("date", "") if evidence_rows and evidence_spans else "",
                    "temporal_selected_dates": temporal_dates if "temporal" in retrieval_details.get("retrieval_methods", []) else [],
                }
            )
    diagnostics = {
        "schema": RETRIEVAL_SERVICE_SCHEMA,
        "kind": "index",
        "source_count": len(sources),
        "hybrid_candidates": hybrid_report.get("candidate_count", 0) if hybrid_report else 0,
        "evidence_rows": len(evidence_report.get("rows", [])) if evidence_report else 0,
        "vector_rows": len(vector_report.get("rows", [])) if vector_report else 0,
        "index_status": index_status,
    }
    return RetrievalServiceResult(
        text="\n\n".join(part for part in parts if part),
        sources=sources,
        diagnostics=diagnostics,
    )


class RetrievalService:
    """Callback-backed service for live hybrid retrieval orchestration.

    The root facade still owns the concrete stores and model calls. This
    boundary makes that ownership explicit while giving tests a narrow place
    to exercise query-to-context behavior with fake callbacks.
    """

    def __init__(
        self,
        *,
        load_index: Callable,
        retrieve_index_query: Callable,
        render_index_overview: Callable,
        load_topic: Callable,
        retrieve_topic: Callable,
        load_dossier: Callable,
        retrieve_dossier: Callable,
        render_context_items: Callable,
        hybrid_environment: HybridRetrievalEnvironment | None = None,
    ) -> None:
        self.load_index = load_index
        self.retrieve_index_query = retrieve_index_query
        self.render_index_overview = render_index_overview
        self.load_topic = load_topic
        self.retrieve_topic = retrieve_topic
        self.load_dossier = load_dossier
        self.retrieve_dossier = retrieve_dossier
        self.render_context_items = render_context_items
        self.hybrid_environment = hybrid_environment

    def retrieve_index(self, index: dict, query: str) -> RetrievalServiceResult:
        if self.hybrid_environment is not None:
            return retrieve_index_hybrid(index, query, self.hybrid_environment)
        text, sources = self.retrieve_index_query(index, query)
        return RetrievalServiceResult(
            text=text,
            sources=list(sources),
            diagnostics={"schema": RETRIEVAL_SERVICE_SCHEMA, "kind": "index", "source_count": len(sources)},
        )

    def render_attached_context(self, items: list[dict], query: str) -> RetrievalServiceResult:
        if not items:
            return RetrievalServiceResult(
                text="No explicit documents are attached.",
                sources=[],
                diagnostics={
                    "schema": RETRIEVAL_SERVICE_SCHEMA,
                    "kind": "attached-context",
                    "item_count": 0,
                    "source_count": 0,
                },
            )
        parts = []
        sources = []
        warning_exceptions = (KeyError, SystemExit, OSError, json.JSONDecodeError)
        for item in items:
            kind = item.get("kind")
            if kind == "index":
                try:
                    index = self.load_index(item["id"])
                except warning_exceptions as exc:
                    sources.append(unavailable_context_source("index", item, exc))
                    continue
                if query:
                    result = self.retrieve_index(index, query)
                else:
                    text, index_sources = self.render_index_overview(index)
                    result = RetrievalServiceResult(text=text, sources=list(index_sources))
                parts.append(result.text)
                sources.extend(result.sources)
                continue
            if kind == "topic":
                try:
                    topic = self.load_topic(item["id"])
                except warning_exceptions as exc:
                    sources.append(unavailable_context_source("topic", item, exc))
                    continue
                text, topic_sources = self.retrieve_topic(topic, query)
                parts.append(text)
                sources.extend(topic_sources)
                continue
            if kind == "dossier":
                try:
                    dossier = self.load_dossier(item["id"])
                except warning_exceptions as exc:
                    sources.append(unavailable_context_source("dossier", item, exc))
                    continue
                text, dossier_sources = self.retrieve_dossier(dossier, query)
                parts.append(text)
                sources.extend(dossier_sources)
                continue
            if kind == "repo":
                text, source = repo_context_text_and_source(item)
            else:
                text, source = file_context_text_and_source(item)
            parts.append(text)
            sources.append(source)
        text = "\n\n".join(part for part in parts if part)
        return RetrievalServiceResult(
            text=text,
            sources=list(sources),
            diagnostics={
                "schema": RETRIEVAL_SERVICE_SCHEMA,
                "kind": "attached-context",
                "item_count": len(items),
                "source_count": len(sources),
            },
        )


def summarize_retrieval_sources(sources: list[dict], *, limit: int = 8) -> list[dict]:
    rows = []
    for order, source in enumerate(sources):
        if not isinstance(source, dict):
            continue
        kind = str(source.get("kind", ""))
        if kind not in {"index", "file-summary", "chunk", "context-warning"}:
            continue
        row = {
            "kind": kind,
            "index": source.get("index") or source.get("id", ""),
            "path": source.get("path", ""),
            "chunk": source.get("chunk", ""),
            "status": source.get("status", ""),
        }
        for key in (
            "retrieval",
            "retrieval_methods",
            "hybrid_score",
            "lexical_score",
            "structured_score",
            "evidence_score",
            "vector_score",
            "rerank_score",
            "excerpt_selection",
            "evidence_id",
            "evidence_kind",
            "evidence_date",
            "temporal_selected_dates",
            "warning",
        ):
            if source.get(key) not in (None, "", []):
                row[key] = source.get(key)
        row["_order"] = order
        rows.append(row)
    priority = {
        "index": 0,
        "context-warning": 1,
        "chunk": 2,
        "file-summary": 3,
    }
    rows.sort(key=lambda row: (priority.get(str(row.get("kind", "")), 9), int(row.get("_order", 0))))
    summarized = []
    for row in rows[: max(0, int(limit or 0))]:
        row = dict(row)
        row.pop("_order", None)
        summarized.append(row)
    return summarized
