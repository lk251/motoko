"""Live retrieval service boundary for Motoko."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from motoko_core.retrieval import (
    add_hybrid_candidate,
    score_text,
    selected_evidence_excerpt,
    token_counts,
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
    rerank_hybrid_candidates: Callable[[dict, str, dict], tuple[list[dict], dict]]
    wants_deep_context: Callable[[str], bool]
    file_staleness: Callable[[dict], tuple[str, list[str]]]
    span_model_chunk_limit: Callable[[], int]
    query_aware_content_selection: Callable[..., dict]
    max_rerank_candidates: int
    evidence_query_limit: int
    evidence_context_limit: int
    vector_query_limit: int
    embedding_vector_method: str


def _chunk_lookup(index: dict) -> dict[tuple[str, str], tuple[dict, dict]]:
    lookup: dict[tuple[str, str], tuple[dict, dict]] = {}
    for file_item in index.get("files", []):
        for chunk in file_item.get("chunks", []):
            lookup[(file_item.get("path", ""), str(chunk.get("chunk", "")))] = (file_item, chunk)
    return lookup


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
    lexical_candidates = [row for row in chunk_rows[: env.max_rerank_candidates] if row[0] > 0]
    if not lexical_candidates:
        lexical_candidates = chunk_rows[: min(2, len(chunk_rows))]
    for score, file_item, chunk, score_parts in lexical_candidates:
        add_hybrid_candidate(candidates, file_item, chunk, "lexical", score, score_parts)
    env.add_structured_task_candidates(index, query, candidates)

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
            lookup = _chunk_lookup(index)
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
                lookup = _chunk_lookup(index)
                for row in vector_report.get("rows", [])[: env.max_rerank_candidates]:
                    found = lookup.get((row.get("path", ""), str(row.get("chunk", ""))))
                    if not found:
                        continue
                    file_item, chunk = found
                    add_hybrid_candidate(candidates, file_item, chunk, "vector", row.get("score", 0), row)
    selected_candidates, hybrid_report = env.rerank_hybrid_candidates(index, query, candidates)
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
        for candidate in selected_candidates[:top_chunks]
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
        text, sources = self.render_context_items(
            items,
            query,
            load_index=self.load_index,
            render_index_query=self.retrieve_index_query,
            render_index_overview=self.render_index_overview,
            load_topic=self.load_topic,
            render_topic=self.retrieve_topic,
            load_dossier=self.load_dossier,
            render_dossier=self.retrieve_dossier,
        )
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
