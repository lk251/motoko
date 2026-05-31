"""Live retrieval service boundary for Motoko."""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass, field
from typing import Callable

from motoko_core.retrieval import (
    add_hybrid_candidate,
    compact_text,
    context_plan_from_lanes_core,
    file_context_text_and_source,
    hybrid_candidate_base_score,
    hybrid_candidate_guard_bonus,
    org_dated_section_spans,
    query_date_mentions,
    query_path_match_boost,
    query_path_mentions,
    query_needs_grounded_sources_core,
    query_requested_recent_section_count,
    repo_context_text_and_source,
    retrieval_haystack_terms,
    score_text,
    selected_evidence_excerpt,
    selected_temporal_evidence_excerpt,
    source_has_strong_evidence_core,
    token_counts,
    unavailable_context_source,
)
from motoko_core.retrieval_planner import (
    build_retrieval_plan,
    plan_has_handler,
    retrieval_plan_source,
)
from motoko_core.skills import ORG_STRUCTURAL_HANDLER, ORG_TEMPORAL_HANDLER


RETRIEVAL_SERVICE_SCHEMA = "retrieval-service-v1"
CONTEXT_PACKAGE_SCHEMA = "context-package-v1"
RETRIEVAL_SUFFICIENCY_SCHEMA = "retrieval-sufficiency-plan-v1"


@dataclass(frozen=True)
class RetrievalServiceResult:
    text: str
    sources: list[dict] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)

    def source_summary(self, *, limit: int = 8) -> list[dict]:
        return summarize_retrieval_sources(self.sources, limit=limit)


@dataclass(frozen=True)
class ContextLane:
    lane: str
    text: str
    sources: list[dict] = field(default_factory=list)
    purpose: str = ""


@dataclass(frozen=True)
class ContextPackage:
    lanes: list[ContextLane]
    sources: list[dict]
    context_plan: dict
    diagnostics: dict = field(default_factory=dict)

    def text_for(self, lane: str) -> str:
        for row in self.lanes:
            if row.lane == lane:
                return row.text
        return ""


@dataclass(frozen=True)
class RetrievalPreviewResult:
    query: str
    audit: dict
    context_plan: dict
    sources: list[dict]
    attached_context: str
    diagnostics: dict = field(default_factory=dict)


@dataclass(frozen=True)
class VectorQueryResult:
    report: dict
    diagnostics: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalSufficiencyExpansion:
    text: str = ""
    sources: list[dict] = field(default_factory=list)
    plan: dict = field(default_factory=dict)
    selected_item: dict | None = None
    diagnostics: dict = field(default_factory=dict)


def plan_retrieval_sufficiency_expansion(
    query: str,
    sources: list[dict],
    candidates: list[dict],
    *,
    grounding_query_words: set[str],
    task_query_words: set[str],
    strong_source_kinds: set[str],
    context_source_kinds: set[str],
    min_score: int = 1,
) -> dict:
    """Choose one bounded extra retrieval pass for thin or stale context.

    This is deliberately a planner, not an agent loop. It only inspects source
    kinds and pre-ranked candidate context items supplied by the caller. The
    caller still owns allowlists, project scoping, and rendering the selected
    item into prompt context.
    """

    def source_stale_or_unavailable(source: dict) -> bool:
        if str(source.get("kind", "")) == "context-warning":
            return True
        status = str(source.get("status", "")).strip().lower()
        if status in {"stale", "missing", "deleted", "ignored", "unavailable"}:
            return True
        warning_text = " ".join(str(warning) for warning in source.get("warnings", []) or []).lower()
        return any(term in warning_text for term in ("stale", "missing", "deleted", "ignored", "unavailable"))

    requested_path_mentions = query_path_mentions(query)

    def source_matches_requested_path(source: dict) -> bool:
        if not requested_path_mentions:
            return False
        for key in ("path", "root", "id", "name"):
            value = str(source.get(key, "")).strip()
            if value and query_path_match_boost(query, value) > 0:
                return True
        return False

    def select_candidate() -> dict | None:
        for candidate in candidates:
            score = int(candidate.get("score", 0) or 0)
            if score < min_score:
                continue
            item = candidate.get("item") if isinstance(candidate.get("item"), dict) else {}
            if not item.get("kind") or not item.get("id"):
                continue
            return {
                "kind": item.get("kind", ""),
                "id": item.get("id", ""),
                "score": score,
                "reason": candidate.get("reason", ""),
            }
        return None

    clean_sources = [source for source in sources if isinstance(source, dict)]
    kinds = [str(source.get("kind", "unknown")) for source in clean_sources]
    strong_count = sum(
        1
        for source in clean_sources
        if source_has_strong_evidence_core(source, strong_source_kinds=strong_source_kinds)
    )
    strong_requested_path_count = sum(
        1
        for source in clean_sources
        if source_has_strong_evidence_core(source, strong_source_kinds=strong_source_kinds)
        and source_matches_requested_path(source)
    )
    nominal_strong_count = sum(1 for kind in kinds if kind in strong_source_kinds)
    context_count = sum(1 for kind in kinds if kind in context_source_kinds)
    stale_or_unavailable_count = sum(1 for source in clean_sources if source_stale_or_unavailable(source))
    needs_grounding = query_needs_grounded_sources_core(
        query,
        grounding_query_words=grounding_query_words,
        task_query_words=task_query_words,
    )
    plan = {
        "schema": RETRIEVAL_SUFFICIENCY_SCHEMA,
        "kind": "retrieval-sufficiency",
        "status": "not-needed",
        "needs_grounding": needs_grounding,
        "strong_source_count": strong_count,
        "strong_requested_path_source_count": strong_requested_path_count,
        "nominal_strong_source_count": nominal_strong_count,
        "context_source_count": context_count,
        "stale_or_unavailable_source_count": stale_or_unavailable_count,
        "requested_path_mentions": requested_path_mentions,
        "candidate_count": len(candidates),
        "selected": None,
        "reason": "question does not appear to require external grounding",
    }
    if not needs_grounding:
        return plan
    if strong_count:
        if requested_path_mentions and not strong_requested_path_count:
            selected = select_candidate()
            if selected is None:
                plan["status"] = "path-warning"
                plan["reason"] = (
                    "selected context has excerpt-level evidence but not from the requested source path; "
                    "no project-scoped recovery candidate was available"
                )
                return plan
            plan.update(
                {
                    "status": "expand",
                    "selected": selected,
                    "reason": (
                        "query named a source path but selected strong evidence did not match it; "
                        "run one bounded source-scoped recovery pass"
                    ),
                }
            )
            return plan
        if stale_or_unavailable_count:
            selected = select_candidate()
            if selected is None:
                plan["status"] = "stale-warning"
                plan["reason"] = (
                    "selected context has excerpt-level evidence but also stale or unavailable source(s); "
                    "no project-scoped recovery candidate was available"
                )
                return plan
            plan.update(
                {
                    "status": "expand",
                    "selected": selected,
                    "reason": (
                        "selected context had excerpt-level evidence but also stale or unavailable source(s); "
                        "run one bounded fresh retrieval pass"
                    ),
                }
            )
            return plan
        plan["status"] = "sufficient"
        plan["reason"] = "selected context already has excerpt-level evidence"
        return plan
    selected = select_candidate()
    if selected is not None:
        plan.update(
            {
                "status": "expand",
                "selected": selected,
                "reason": "grounded query had no excerpt-level evidence; run one bounded extra retrieval pass",
            }
        )
        return plan
    plan["status"] = "no-candidate"
    plan["reason"] = "grounded query had no excerpt-level evidence and no project-scoped stored context candidate"
    return plan


def build_context_package(
    lanes: list[ContextLane],
    *,
    budget_chars: int,
) -> ContextPackage:
    """Aggregate prompt-context lanes and source records.

    The root facade still owns final prompt wording, but source accounting and
    context-plan construction live here so chat, previews, and sources can keep
    using the same structured lane result.
    """

    lane_rows = []
    sources: list[dict] = []
    for lane in lanes:
        lane_sources = [source for source in lane.sources if isinstance(source, dict)]
        sources.extend(lane_sources)
        lane_rows.append(
            {
                "lane": lane.lane,
                "chars": len(lane.text),
                "sources": len(lane_sources),
                "purpose": lane.purpose,
            }
        )
    context_plan = context_plan_from_lanes_core(lane_rows, budget_chars=budget_chars)
    context_plan["context_package_schema"] = CONTEXT_PACKAGE_SCHEMA
    sources.append(context_plan)
    return ContextPackage(
        lanes=list(lanes),
        sources=sources,
        context_plan=context_plan,
        diagnostics={
            "schema": CONTEXT_PACKAGE_SCHEMA,
            "lane_count": len(lanes),
            "source_count": len(sources),
        },
    )


def build_retrieval_preview_result(
    query: str,
    context_package: ContextPackage,
    *,
    audit: dict,
) -> RetrievalPreviewResult:
    """Shape retrieval preview data from the same package used for chat.

    Formatting stays outside the service, but the preview command should not
    reinterpret context lanes or source records differently from chat prompt
    assembly.
    """

    sources = list(context_package.sources)
    return RetrievalPreviewResult(
        query=query,
        audit=dict(audit),
        context_plan=dict(context_package.context_plan),
        sources=sources,
        attached_context=context_package.text_for("attached context"),
        diagnostics={
            "schema": RETRIEVAL_SERVICE_SCHEMA,
            "kind": "retrieval-preview",
            "context_package_schema": context_package.context_plan.get("context_package_schema", ""),
            "source_count": len(sources),
            "lane_count": len(context_package.lanes),
        },
    )


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


def _debug_file_row(
    index: dict,
    query: str,
    query_counts,
    file_item: dict,
    env: HybridRetrievalEnvironment,
) -> dict:
    file_signal_text = env.format_signal_summary(file_item.get("signals") or {}, limit=12)
    haystack = "\n".join([file_item.get("path", ""), file_item.get("summary", ""), file_signal_text])
    status, warnings = env.file_staleness(file_item)
    return {
        "kind": "file",
        "index": index.get("id", ""),
        "path": file_item.get("path", ""),
        "summary": compact_text(file_item.get("summary", ""), 280),
        "freshness": status,
        "warnings": warnings[:4],
        **env.retrieval_score_parts(
            query,
            query_counts,
            haystack,
            path=file_item.get("path", ""),
            file_signals=file_item.get("signals") or {},
        ),
    }


def _debug_chunk_row(
    index: dict,
    query_counts,
    file_item: dict,
    chunk: dict,
    content: str,
    score_parts: dict,
) -> dict:
    return {
        "kind": "chunk",
        "index": index.get("id", ""),
        "path": file_item.get("path", ""),
        "chunk": chunk.get("chunk"),
        "summary": compact_text(chunk.get("summary", ""), 280),
        "content_chars": len(content),
        "content_sha256": chunk.get("content_sha256", ""),
        "summary_matched_terms": retrieval_haystack_terms(
            query_counts,
            "\n".join([file_item.get("summary", ""), chunk.get("summary", "")]),
        )[:12],
        "content_matched_terms": retrieval_haystack_terms(query_counts, content[:4000])[:12],
        **score_parts,
    }


def _temporal_evidence_rows(
    index: dict,
    query: str,
    env: HybridRetrievalEnvironment,
    *,
    retrieval_plan: dict | None = None,
) -> list[dict]:
    exact_dates = set(query_date_mentions(query))
    recent_count = query_requested_recent_section_count(query)
    source_scoped_latest = plan_has_handler(retrieval_plan or {}, ORG_TEMPORAL_HANDLER)
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
        if source_scoped_latest and path_mentions and path_boost <= 0:
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


def _structural_filters(plan: dict) -> dict:
    structural = plan.get("structural") if isinstance(plan.get("structural"), dict) else {}
    return {
        "tags": [str(item).lower() for item in structural.get("tags", []) if str(item).strip()],
        "todo_states": [str(item).upper() for item in structural.get("todo_states", []) if str(item).strip()],
        "priorities": [str(item).upper() for item in structural.get("priorities", []) if str(item).strip()],
        "flags": structural.get("flags", {}) if isinstance(structural.get("flags"), dict) else {},
        "path_mentions": [str(item) for item in structural.get("path_mentions", []) if str(item).strip()],
    }


def _structural_filter_labels(filters: dict) -> list[str]:
    labels = []
    if filters.get("tags"):
        labels.append("tag:" + ",".join(filters["tags"][:8]))
    if filters.get("todo_states"):
        labels.append("todo:" + ",".join(filters["todo_states"][:8]))
    if filters.get("priorities"):
        labels.append("priority:" + ",".join(filters["priorities"][:8]))
    flags = filters.get("flags") or {}
    for key in ("deadline", "scheduled", "heading"):
        if flags.get(key):
            labels.append(key)
    if filters.get("path_mentions"):
        labels.append("source:" + ",".join(filters["path_mentions"][:4]))
    return labels


def _row_org_tags(row: dict) -> set[str]:
    return {str(tag).lower() for tag in row.get("tags", []) or [] if str(tag).strip()}


def _row_matches_structural_filters(row: dict, query: str, filters: dict) -> tuple[bool, int]:
    kind = str(row.get("kind", ""))
    if not kind.startswith("org_"):
        return False, 0
    path_boost = query_path_match_boost(query, row.get("path", ""))
    if filters.get("path_mentions") and path_boost <= 0:
        return False, 0
    score = 6500 + path_boost
    tags = filters.get("tags") or []
    if tags:
        row_tags = _row_org_tags(row)
        if not all(tag in row_tags for tag in tags):
            return False, 0
        score += 1200 * len(tags)
    todo_states = filters.get("todo_states") or []
    if todo_states:
        if str(row.get("todo", "")).upper() not in set(todo_states):
            return False, 0
        score += 900
    priorities = filters.get("priorities") or []
    if priorities:
        if str(row.get("priority", "")).upper() not in set(priorities):
            return False, 0
        score += 700
    flags = filters.get("flags") or {}
    text = str(row.get("text", ""))
    if flags.get("deadline"):
        if "DEADLINE:" not in text:
            return False, 0
        score += 500
    if flags.get("scheduled"):
        if "SCHEDULED:" not in text:
            return False, 0
        score += 500
    if flags.get("heading") and kind not in {"org_heading", "org_day", "org_task"}:
        return False, 0
    if not (tags or todo_states or priorities or any(flags.values()) or filters.get("path_mentions")):
        return False, 0
    return True, score


def _org_structural_evidence_rows(store: dict, query: str, plan: dict, *, limit: int) -> tuple[list[dict], list[str]]:
    filters = _structural_filters(plan)
    query_counts = token_counts(query)
    rows = []
    for row in store.get("rows", []) or []:
        if not isinstance(row, dict):
            continue
        matched, structured = _row_matches_structural_filters(row, query, filters)
        if not matched:
            continue
        haystack = "\n".join(
            [
                row.get("path", ""),
                row.get("kind", ""),
                row.get("title", ""),
                " ".join(row.get("parent_titles", []) or []),
                " ".join(row.get("tags", []) or []),
                row.get("text", ""),
            ]
        )
        lexical = score_text(query_counts, haystack)
        item = dict(row)
        item.update(
            {
                "matched_terms": retrieval_haystack_terms(query_counts, haystack)[:16],
                "lexical": lexical,
                "path_boost": query_path_match_boost(query, row.get("path", "")),
                "structured": structured,
                "total": structured + lexical,
                "structural_filters": _structural_filter_labels(filters),
            }
        )
        rows.append(item)
    rows.sort(
        key=lambda item: (
            float(item.get("total", 0) or 0),
            float(item.get("structured", 0) or 0),
            str(item.get("path", "")),
            -int(item.get("start", 0) or 0),
        ),
        reverse=True,
    )
    return rows[: max(1, int(limit or 1))], _structural_filter_labels(filters)


CODE_FILE_SUFFIXES = {
    ".py",
    ".nix",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".rs",
    ".go",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".hpp",
    ".java",
    ".kt",
    ".swift",
    ".rb",
    ".lua",
    ".el",
    ".vim",
    ".scm",
    ".sql",
    ".toml",
    ".json",
    ".yaml",
    ".yml",
}

CODE_QUERY_HINTS = {
    "code",
    "source",
    "repo",
    "repository",
    "implementation",
    "implemented",
    "implements",
    "handler",
    "handles",
    "handled",
    "function",
    "class",
    "module",
    "method",
    "command",
    "cli",
    "tui",
    "parser",
    "render",
    "renderer",
    "schema",
    "route",
    "endpoint",
    "test",
    "tests",
    "defined",
    "definition",
    "called",
    "calls",
    "import",
    "imports",
}

CODE_STOPWORDS = {
    "about",
    "which",
    "what",
    "where",
    "when",
    "file",
    "files",
    "repo",
    "repository",
    "takes",
    "care",
    "page",
    "thing",
    "this",
    "that",
    "does",
    "with",
    "from",
    "into",
    "there",
    "have",
    "motoko",
}


def query_wants_code_locator(query: str) -> bool:
    lowered = query.lower()
    query_words = set(re.findall(r"\b[a-z][a-z0-9_:-]*\b", lowered))
    if re.search(r"(?<!\S)/[A-Za-z][\w-]*", query):
        return True
    if re.search(r"`[^`]{2,120}`", query):
        return True
    if re.search(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\s*\(", query):
        return True
    if query_words & CODE_QUERY_HINTS:
        return True
    return any(phrase in lowered for phrase in ("which file", "where is", "where does", "takes care of"))


def code_locator_terms(query: str) -> list[str]:
    terms: list[str] = []

    def add(term: str) -> None:
        term = str(term or "").strip()
        if not term or len(term) > 120:
            return
        if term not in terms:
            terms.append(term)

    for match in re.findall(r"(?<!\S)/[A-Za-z][\w-]*", query):
        add(match)
        name = match.lstrip("/")
        add(name)
        if name:
            add(f"format_{name}")
            add(f"command_{name}")
            add(f"handle_{name}")
    for match in re.findall(r"`([^`]{1,120})`", query):
        add(match)
    for left, right in re.findall(r'"([^"]{1,120})"|\'([^\']{1,120})\'', query):
        add(left or right)
    for match in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", query):
        if match.lower() not in CODE_STOPWORDS:
            add(match)
    return terms


def code_like_path_or_content(path: str, content: str) -> bool:
    lower_path = path.lower()
    suffix = ""
    if "." in lower_path.rsplit("/", 1)[-1]:
        suffix = "." + lower_path.rsplit(".", 1)[-1]
    basename = lower_path.rsplit("/", 1)[-1]
    if suffix in CODE_FILE_SUFFIXES or basename in {"motoko", "makefile", "flake.nix"}:
        return True
    sample = content[:4000]
    return bool(
        re.search(r"(?m)^\s*(def|class|import|from)\s+[A-Za-z_]", sample)
        or re.search(r"(?m)^\s*(function|const|let|var|export)\s+[A-Za-z_]", sample)
        or "add_parser(" in sample
        or "SLASH_COMMANDS" in sample
    )


def code_locator_excerpt(content: str, terms: list[str], *, max_chars: int = 1600) -> tuple[str, int]:
    lowered = content.lower()
    positions = [
        lowered.find(term.lower())
        for term in terms
        if term and lowered.find(term.lower()) >= 0
    ]
    if not positions:
        return content[:max_chars], 0
    pos = min(positions)
    start = max(0, pos - max_chars // 3)
    end = min(len(content), start + max_chars)
    return content[start:end].strip(), pos


def code_locator_score(path: str, content: str, summary: str, query: str, terms: list[str]) -> tuple[int, list[str]]:
    lowered_content = content.lower()
    lowered_path = path.lower()
    lowered_summary = summary.lower()
    score = 0
    matched: list[str] = []
    for term in terms:
        lowered = term.lower()
        if not lowered:
            continue
        count = lowered_content.count(lowered)
        if count:
            matched.append(term)
            score += min(count, 8) * (900 if term.startswith("/") else 90)
            if re.search(rf"(?m)^\s*(def|class)\s+{re.escape(term)}\b", content):
                score += 1200
            if re.search(rf"(?m)^\s*{re.escape(term)}\s*=", content):
                score += 350
        if lowered in lowered_path:
            matched.append(term)
            score += 250
        if lowered in lowered_summary:
            score += 25
    for term in terms:
        if term.startswith(("format_", "command_", "handle_")) and term.lower() in lowered_content:
            score += 500
    if any(term.startswith("/") for term in terms) and re.search(r"\(\s*[\"']/[A-Za-z][\w-]*[\"']", content):
        score += 600
    return score, list(dict.fromkeys(matched))[:12]


def code_locator_rows(index: dict, query: str, env: HybridRetrievalEnvironment) -> list[dict]:
    if not query_wants_code_locator(query):
        return []
    terms = code_locator_terms(query)
    if not terms:
        return []
    rows = []
    for file_item in index.get("files", []):
        path = str(file_item.get("path", "") or "")
        summary = str(file_item.get("summary", "") or "")
        for chunk in file_item.get("chunks", []):
            content = env.read_chunk_content(index, chunk)
            if not code_like_path_or_content(path, content):
                continue
            score, matched = code_locator_score(path, content, summary, query, terms)
            if score <= 0:
                continue
            excerpt, start = code_locator_excerpt(content, terms)
            rows.append(
                {
                    "id": f"{path}#{chunk.get('chunk', '')}:code:{start}",
                    "kind": "code_locator",
                    "path": path,
                    "chunk": chunk.get("chunk"),
                    "title": "source-code locator",
                    "start": start,
                    "end": start + len(excerpt),
                    "text": excerpt,
                    "text_chars": len(excerpt),
                    "matched_terms": matched,
                    "path_boost": 2000 if any(term.lower() in path.lower() for term in terms) else 0,
                    "structured": score,
                    "total": score,
                }
            )
    rows.sort(key=lambda row: (int(row.get("total", 0) or 0), int(row.get("path_boost", 0) or 0)), reverse=True)
    return rows[:12]


def _selected_candidates_with_required_keys(
    candidates: list[dict],
    selected: list[dict],
    *,
    required_keys: set[tuple[str, str]],
) -> list[dict]:
    if not required_keys:
        return selected
    selected_keys = {tuple(row.get("key", ())) for row in selected}
    output = list(selected)
    for row in candidates:
        key = tuple(row.get("key", ()))
        if key not in required_keys or key in selected_keys:
            continue
        output.append(row)
        selected_keys.add(key)
        if len([item for item in output if tuple(item.get("key", ())) in required_keys]) >= 3:
            break
    return output


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
    retrieval_plan = build_retrieval_plan(query)
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
    code_candidate_keys: set[tuple[str, str]] = set()
    lexical_candidates = [row for row in chunk_rows[: env.max_rerank_candidates] if row[0] > 0]
    if not lexical_candidates:
        lexical_candidates = chunk_rows[: min(2, len(chunk_rows))]
    for score, file_item, chunk, score_parts in lexical_candidates:
        add_hybrid_candidate(candidates, file_item, chunk, "lexical", score, score_parts)
    env.add_structured_task_candidates(index, query, candidates)
    lookup = _chunk_lookup(index)
    code_rows = code_locator_rows(index, query, env)
    for row in code_rows:
        found = lookup.get((row.get("path", ""), str(row.get("chunk", ""))))
        if not found:
            continue
        file_item, chunk = found
        add_hybrid_candidate(candidates, file_item, chunk, "code", row.get("total", 0), row)
        code_candidate_keys.add((file_item.get("path", ""), str(chunk.get("chunk", ""))))
    temporal_rows = _temporal_evidence_rows(index, query, env, retrieval_plan=retrieval_plan)
    temporal_dates = sorted({str(row.get("date", "")) for row in temporal_rows if row.get("date")}, reverse=True)
    for row in temporal_rows:
        found = lookup.get((row.get("path", ""), str(row.get("chunk", ""))))
        if not found:
            continue
        file_item, chunk = found
        add_hybrid_candidate(candidates, file_item, chunk, "temporal", row.get("total", 0), row)
        temporal_candidate_keys.add((file_item.get("path", ""), str(chunk.get("chunk", ""))))

    evidence_store = None
    structural_rows = []
    structural_filters = []
    structural_warning = ""
    structural_candidate_keys: set[tuple[str, str]] = set()
    if env.evidence_enabled() and plan_has_handler(retrieval_plan, ORG_STRUCTURAL_HANDLER):
        try:
            evidence_store = env.evidence_store_for_retrieval(index)
            structural_rows, structural_filters = _org_structural_evidence_rows(
                evidence_store,
                query,
                retrieval_plan,
                limit=max(top_chunks * 4, env.evidence_context_limit * 3),
            )
        except SystemExit as exc:
            structural_warning = str(exc).splitlines()[0][:240]
        else:
            for row in structural_rows:
                found = lookup.get((row.get("path", ""), str(row.get("chunk", ""))))
                if not found:
                    continue
                file_item, chunk = found
                add_hybrid_candidate(
                    candidates,
                    file_item,
                    chunk,
                    "structural",
                    row.get("total", 0),
                    row,
                    evidence_context_limit=max(env.evidence_context_limit, 24),
                )
                structural_candidate_keys.add((file_item.get("path", ""), str(chunk.get("chunk", ""))))

    evidence_report = None
    evidence_warning = ""
    if env.evidence_enabled():
        try:
            if evidence_store is None:
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
    elif structural_candidate_keys:
        rerank_candidates = {
            key: value
            for key, value in candidates.items()
            if key in structural_candidate_keys
        }
    selected_candidates, hybrid_report = rerank_hybrid_candidates_with_environment(index, query, rerank_candidates, env)
    selected_candidate_rows = _selected_candidates_with_required_temporal_dates(
        selected_candidates,
        limit=top_chunks,
        temporal_dates=temporal_dates,
    )
    selected_candidate_rows = _selected_candidates_with_required_keys(
        selected_candidates,
        selected_candidate_rows,
        required_keys=code_candidate_keys,
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
        activated = ", ".join(
            row.get("slug") or row.get("name", "")
            for row in retrieval_plan.get("activated_skills", [])
            if row.get("slug") or row.get("name")
        )
        if activated:
            parts.append(
                "Retrieval plan:\n"
                f"Activated skill(s): {activated}. "
                "Motoko applied the plan before context packing so source evidence, "
                "not only final-prompt guidance, controls the answer."
            )
        parts.append(
            "Temporal selection:\n"
            "The query asked for recent dated Org sections from this source. "
            "Motoko selected these as the newest dates present in the matching file(s): "
            f"{', '.join(temporal_dates)}. "
            "Do not assume missing intervening calendar dates have entries."
        )
    if structural_rows or structural_warning:
        activated = ", ".join(
            row.get("slug") or row.get("name", "")
            for row in retrieval_plan.get("activated_skills", [])
            if row.get("handler") == ORG_STRUCTURAL_HANDLER and (row.get("slug") or row.get("name"))
        )
        detail = ", ".join(structural_filters) if structural_filters else "Org structure"
        if structural_rows:
            preview_lines = []
            for row in structural_rows[: min(20, len(structural_rows))]:
                labels = []
                if row.get("todo"):
                    labels.append(str(row.get("todo")))
                if row.get("priority"):
                    labels.append(f"[#{row.get('priority')}]")
                if row.get("date"):
                    labels.append(str(row.get("date")))
                if row.get("tags"):
                    labels.append(":" + ":".join(row.get("tags", [])[:6]) + ":")
                title = row.get("title") or row.get("kind", "org")
                preview_lines.append(
                    f"- {row.get('path', '')} chunk {row.get('chunk', '')}: "
                    f"{' '.join(labels)} {title}".strip()
                )
            parts.append(
                "Org structural selection:\n"
                + (f"Activated skill(s): {activated}. " if activated else "")
                + f"Matched {len(structural_rows)} source-linked Org evidence row(s)"
                + (f" for {detail}." if detail else ".")
                + "\n"
                + "\n".join(preview_lines)
            )
        else:
            parts.append(f"Org structural selection:\nwarning: {structural_warning}")
    if code_rows:
        top_code = ", ".join(
            f"{row.get('path', '')} chunk {row.get('chunk', '')}"
            for row in code_rows[:3]
        )
        parts.append(
            "Source code locator:\n"
            "The query appears to ask about implementation or source-code behavior. "
            "Motoko ran deterministic literal/symbol matching over code-like files "
            f"before context packing. Top implementation candidate(s): {top_code}."
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
        "retrieval_plan_schema": retrieval_plan.get("schema", ""),
    }
    if retrieval_plan.get("activated_skills"):
        index_source["activated_skills"] = [
            row.get("slug") or row.get("name", "")
            for row in retrieval_plan.get("activated_skills", [])
            if row.get("slug") or row.get("name")
        ]
        index_source["retrieval_plan_status"] = retrieval_plan.get("status", "")
    if temporal_dates:
        index_source["temporal_selected_dates"] = temporal_dates
    if structural_rows:
        index_source["structural_matches"] = len(structural_rows)
        index_source["structural_filters"] = structural_filters
    if structural_warning:
        index_source["warnings"] = index_source.get("warnings", []) + [f"structural Org retrieval skipped: {structural_warning}"]
    if code_rows:
        index_source["code_locator_hits"] = len(code_rows)
        index_source["code_locator_top_paths"] = [
            row.get("path", "")
            for row in code_rows[:5]
            if row.get("path")
        ]
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
    plan_source = retrieval_plan_source(retrieval_plan)
    if plan_source:
        sources.append(plan_source)
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
                    excerpt_limit = max(env.evidence_context_limit, 24) if "structural" in retrieval_details.get("retrieval_methods", []) else env.evidence_context_limit
                    excerpt, evidence_spans = selected_evidence_excerpt(
                        evidence_rows,
                        max_chars=remaining,
                        evidence_context_limit=excerpt_limit,
                    )
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
                    "structural_filters": structural_filters if "structural" in retrieval_details.get("retrieval_methods", []) else [],
                }
            )
    debug_row_limit = max(50, top_files * 8, top_chunks * 8, env.max_rerank_candidates)
    debug_files = [
        _debug_file_row(index, query, query_counts, file_item, env)
        for _score, file_item in file_rows[:debug_row_limit]
    ]
    debug_chunks = [
        _debug_chunk_row(
            index,
            query_counts,
            file_item,
            chunk,
            env.read_chunk_content(index, chunk),
            score_parts,
        )
        for _score, file_item, chunk, score_parts in chunk_rows[:debug_row_limit]
    ]
    debug_index = {
        "id": index.get("id", ""),
        "name": index.get("name", ""),
        "root": index.get("root", ""),
        "freshness": index_status,
        "production_retrieval": "hybrid lexical+structured+evidence+embedding -> rerank",
        "warnings": index_warnings[:8],
        "files_considered": len(file_rows),
        "chunks_considered": len(chunk_rows),
        "files": debug_files,
        "chunks": debug_chunks,
        "production_sources": summarize_retrieval_sources(sources, limit=debug_row_limit),
        "production_diagnostics": {
            "schema": RETRIEVAL_SERVICE_SCHEMA,
            "source_count": len(sources),
            "hybrid_candidates": hybrid_report.get("candidate_count", 0) if hybrid_report else 0,
            "evidence_rows": len(evidence_report.get("rows", [])) if evidence_report else 0,
            "vector_rows": len(vector_report.get("rows", [])) if vector_report else 0,
            "index_status": index_status,
            "code_locator_rows": len(code_rows),
        },
    }
    if evidence_report:
        debug_index["evidence_store"] = {
            "id": evidence_report.get("store_id", ""),
            "freshness": evidence_report.get("freshness", ""),
        }
        if evidence_report.get("warnings"):
            debug_index["evidence_warnings"] = evidence_report.get("warnings", [])[:4]
        debug_index["evidence_rows"] = evidence_report.get("rows", [])[:debug_row_limit]
    elif evidence_warning:
        debug_index["evidence_error"] = evidence_warning
    if vector_report:
        debug_index["vector_store"] = {
            "id": vector_report.get("store_id", ""),
            "method": vector_report.get("method", ""),
            "rerank": vector_report.get("rerank", False),
            "rerank_fallback": vector_report.get("rerank_fallback", False),
        }
        if vector_report.get("warnings"):
            debug_index["vector_warnings"] = vector_report.get("warnings", [])[:4]
        debug_index["vector_chunks"] = vector_report.get("rows", [])[:debug_row_limit]
    elif vector_warning:
        debug_index["vector_error"] = vector_warning
    diagnostics = {
        "schema": RETRIEVAL_SERVICE_SCHEMA,
        "kind": "index",
        "source_count": len(sources),
        "hybrid_candidates": hybrid_report.get("candidate_count", 0) if hybrid_report else 0,
        "evidence_rows": len(evidence_report.get("rows", [])) if evidence_report else 0,
        "vector_rows": len(vector_report.get("rows", [])) if vector_report else 0,
        "code_locator_rows": len(code_rows),
        "index_status": index_status,
        "retrieval_plan": retrieval_plan,
        "debug_index": debug_index,
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
        load_vector_store: Callable | None = None,
        latest_vector_store: Callable | None = None,
        query_vector_store: Callable | None = None,
        hybrid_environment: HybridRetrievalEnvironment | None = None,
    ) -> None:
        self.load_index = load_index
        self.retrieve_index_query = retrieve_index_query
        self.render_index_overview = render_index_overview
        self.load_topic = load_topic
        self.retrieve_topic = retrieve_topic
        self.load_dossier = load_dossier
        self.retrieve_dossier = retrieve_dossier
        self.load_vector_store = load_vector_store
        self.latest_vector_store = latest_vector_store
        self._query_vector_store = query_vector_store
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

    def build_sufficiency_expansion(
        self,
        query: str,
        sources: list[dict],
        candidates: list[dict],
        *,
        grounding_query_words: set[str],
        task_query_words: set[str],
        strong_source_kinds: set[str],
        context_source_kinds: set[str],
        min_score: int = 1,
    ) -> RetrievalSufficiencyExpansion:
        """Build one bounded retrieval recovery pass when context is thin.

        Candidate discovery is still injected by the facade because it depends
        on realm-local stores and project scope. The service owns the
        planner-selected item lookup, attached-context rendering, source row,
        and user-visible note so chat context, previews, and /sources keep one
        interpretation of the sufficiency pass.
        """

        plan = plan_retrieval_sufficiency_expansion(
            query,
            sources,
            candidates,
            grounding_query_words=grounding_query_words,
            task_query_words=task_query_words,
            strong_source_kinds=strong_source_kinds,
            context_source_kinds=context_source_kinds,
            min_score=min_score,
        )
        selected = plan.get("selected") if isinstance(plan.get("selected"), dict) else None
        if plan.get("status") != "expand" or not selected:
            return RetrievalSufficiencyExpansion(
                plan=plan,
                diagnostics={
                    "schema": RETRIEVAL_SERVICE_SCHEMA,
                    "kind": "retrieval-sufficiency",
                    "status": plan.get("status", ""),
                    "source_count": 0,
                },
            )

        selected_item = None
        for candidate in candidates:
            item = candidate.get("item") if isinstance(candidate.get("item"), dict) else {}
            if item.get("kind") == selected.get("kind") and item.get("id") == selected.get("id"):
                selected_item = item
                break
        if selected_item is None:
            missing_plan = {
                **plan,
                "status": "no-candidate",
                "reason": "selected context item was no longer available",
            }
            return RetrievalSufficiencyExpansion(
                plan=missing_plan,
                diagnostics={
                    "schema": RETRIEVAL_SERVICE_SCHEMA,
                    "kind": "retrieval-sufficiency",
                    "status": "no-candidate",
                    "source_count": 0,
                },
            )

        result = self.render_attached_context([selected_item], query)
        planner_source = {
            "kind": "retrieval-sufficiency",
            "schema": plan.get("schema", ""),
            "status": plan.get("status", ""),
            "reason": plan.get("reason", ""),
            "selected_kind": selected.get("kind", ""),
            "selected_id": selected.get("id", ""),
            "selected_score": selected.get("score", 0),
            "selected_reason": selected.get("reason", ""),
            "strong_source_count": plan.get("strong_source_count", 0),
            "strong_requested_path_source_count": plan.get("strong_requested_path_source_count", 0),
            "nominal_strong_source_count": plan.get("nominal_strong_source_count", 0),
            "context_source_count": plan.get("context_source_count", 0),
            "stale_or_unavailable_source_count": plan.get("stale_or_unavailable_source_count", 0),
            "requested_path_mentions": plan.get("requested_path_mentions", []),
            "candidate_count": plan.get("candidate_count", 0),
        }
        if plan.get("requested_path_mentions") and not plan.get("strong_requested_path_source_count", 0):
            plan_note = "Initial context had excerpt-level evidence, but not from the requested source path."
        elif plan.get("stale_or_unavailable_source_count", 0):
            plan_note = "Initial context included stale or unavailable source evidence."
        else:
            plan_note = "Initial context had no excerpt-level evidence for this grounded query."
        note = textwrap.dedent(
            f"""
            Retrieval sufficiency planner:
            {plan_note}
            Motoko ran one bounded extra retrieval pass over {selected.get('kind', '')} {selected.get('id', '')}.
            This did not attach or mutate the conversation.
            """
        ).strip()
        expansion_text = "\n\n".join(part for part in [note, result.text] if part)
        expansion_sources = [planner_source] + list(result.sources)
        return RetrievalSufficiencyExpansion(
            text=expansion_text,
            sources=expansion_sources,
            plan=plan,
            selected_item=selected_item,
            diagnostics={
                "schema": RETRIEVAL_SERVICE_SCHEMA,
                "kind": "retrieval-sufficiency",
                "status": plan.get("status", ""),
                "source_count": len(expansion_sources),
                "selected_kind": selected.get("kind", ""),
            },
        )

    def query_vector(
        self,
        query: str,
        *,
        store: dict | None = None,
        store_id: str | None = None,
        limit: int | None = None,
        rerank: bool = False,
    ) -> VectorQueryResult:
        if self._query_vector_store is None:
            raise SystemExit("vector query is not configured")
        if store is None:
            if store_id:
                if self.load_vector_store is None:
                    raise SystemExit("vector store loading is not configured")
                store = self.load_vector_store(store_id)
            else:
                if self.latest_vector_store is None:
                    raise SystemExit("latest vector store lookup is not configured")
                store = self.latest_vector_store()
        kwargs = {"rerank": rerank}
        if limit is not None:
            kwargs["limit"] = limit
        report = self._query_vector_store(store, query, **kwargs)
        report = dict(report)
        report["retrieval_service_schema"] = RETRIEVAL_SERVICE_SCHEMA
        report_store = report.get("store") if isinstance(report.get("store"), dict) else {}
        return VectorQueryResult(
            report=report,
            diagnostics={
                "schema": RETRIEVAL_SERVICE_SCHEMA,
                "kind": "vector-query",
                "store_id": report.get("store_id") or report_store.get("id", ""),
                "row_count": len(report.get("rows", []) or []),
                "rerank": bool(report.get("rerank", rerank)),
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
            "structural_matches",
            "structural_filters",
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
