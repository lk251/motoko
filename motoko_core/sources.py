"""Source report formatting for Motoko."""

from __future__ import annotations

import json

from motoko_core.text import relative_time

CONTEXT_PLAN_BUDGET_CHARS = 180000
MEMORY_DEFAULT_IMPORTANCE = 3


def format_source_span_detail(span: dict) -> str:
    detail = f"{span.get('kind', '')}:{span.get('label', '')}".strip(":")
    if span.get("evidence_id"):
        detail += f"#{str(span.get('evidence_id'))[-8:]}"
    if span.get("selected_sub_start") is not None and span.get("selected_sub_end") is not None:
        detail += (
            f"@{span.get('selected_sub_start')}-"
            f"{span.get('selected_sub_end')}"
        )
    return detail


def format_sources(sources: list[dict]) -> str:
    if not sources:
        return "No recorded sources for the last answer."
    lines = []
    for idx, source in enumerate(sources, 1):
        kind = source.get("kind", "source")
        if kind == "identity":
            lines.append(
                f"{idx:3d}  identity  {source.get('name', 'Motoko')}  "
                f"realm {source.get('realm', 'personal')}"
            )
            lines.append("     why: assistant identity and account realm")
        elif kind == "memory":
            reasons = []
            if source.get("pinned"):
                reasons.append("pinned")
            if source.get("matched_terms", 0):
                reasons.append(f"matched {source.get('matched_terms')} prompt term(s)")
            reasons.append(f"importance {source.get('importance', MEMORY_DEFAULT_IMPORTANCE)}")
            detail = source.get("source", "unknown")
            if source.get("conversation_id"):
                detail += f"; conversation {source.get('conversation_id')}"
            detail += (
                f"; score {source.get('score', 0)}"
            )
            lines.append(f"{idx:3d}  memory {source.get('id', '')}  {detail}")
            lines.append(f"     why: {', '.join(reasons)}")
        elif kind == "skill":
            matched = ", ".join(source.get("matched_terms", [])[:8]) or "-"
            lines.append(
                f"{idx:3d}  skill  {source.get('name', '')}  "
                f"score {source.get('score', 0)}  {source.get('description', '')}"
            )
            lines.append(f"     why: relevant learned procedure; matched {matched}")
            if source.get("handler"):
                effects = ", ".join(source.get("allowed_effects", [])[:6]) or "-"
                lines.append(
                    f"     handler: {source.get('handler', '')}  "
                    f"kind: {source.get('skill_kind', '')}  effects: {effects}"
                )
            if source.get("path"):
                lines.append(f"     path: {source.get('path', '')}")
        elif kind == "skill-support":
            matched = ", ".join(source.get("matched_terms", [])[:8]) or "-"
            lines.append(
                f"{idx:3d}  skill support  {source.get('name', '')}  "
                f"{source.get('support_file', '')}  score {source.get('score', 0)}"
            )
            lines.append(f"     why: relevant support file for a learned procedure; matched {matched}")
            if source.get("handler"):
                effects = ", ".join(source.get("allowed_effects", [])[:6]) or "-"
                lines.append(
                    f"     handler: {source.get('handler', '')}  "
                    f"kind: {source.get('skill_kind', '')}  effects: {effects}"
                )
            if source.get("path"):
                lines.append(f"     path: {source.get('path', '')}")
        elif kind == "retrieval-plan":
            lines.append(
                f"{idx:3d}  retrieval plan  {source.get('schema', '')}  "
                f"{source.get('status', 'unknown')}"
            )
            lines.append("     why: pre-retrieval skill/handler planning")
            if source.get("activated_skills"):
                lines.append("     skills: " + ", ".join(source.get("activated_skills", [])[:8]))
            if source.get("handlers"):
                lines.append("     handlers: " + ", ".join(source.get("handlers", [])[:8]))
            temporal = source.get("temporal") or {}
            if temporal:
                mentions = ", ".join(temporal.get("path_mentions", [])[:4]) or "-"
                lines.append(
                    f"     temporal: {temporal.get('mode', '')} "
                    f"count={temporal.get('requested_count', 0)} source={mentions}"
                )
            for warning in source.get("warnings", [])[:3]:
                lines.append(f"     warning: {warning}")
        elif kind == "personality":
            lines.append(
                f"{idx:3d}  personality  {source.get('status', 'unknown')}  "
                f"{source.get('path', '')}"
            )
            lines.append("     why: tone and conversational style guidance")
        elif kind == "profile":
            lines.append(
                f"{idx:3d}  profile dossier  updated {relative_time(source.get('updated', ''))}  "
                f"{source.get('memory_count', 0)} memories  "
                f"{source.get('conversation_count', 0)} conversations"
            )
            lines.append("     why: stable long-term profile context")
        elif kind == "conversation-summary":
            lines.append(f"{idx:3d}  compacted conversation summary")
            lines.append("     why: older turns compressed for continuity")
        elif kind == "context-catalog":
            lines.append(f"{idx:3d}  context catalog  updated {relative_time(source.get('updated', ''))}")
            lines.append("     why: inventory of available private context")
        elif kind == "context-warning":
            detail = source.get("path", "") or source.get("id", "")
            lines.append(
                f"{idx:3d}  warning  attached {source.get('context_kind', 'context')} unavailable  {detail}"
            )
            lines.append(f"     why: skipped stale or missing attached context: {source.get('warning', '')}")
        elif kind == "context-plan":
            lines.append(
                f"{idx:3d}  context plan  "
                f"{source.get('total_chars', 0)}/{source.get('budget_chars', CONTEXT_PLAN_BUDGET_CHARS)} chars  "
                f"{source.get('status', 'unknown')}"
            )
            for lane in source.get("lanes", []):
                lines.append(
                    f"     lane: {lane.get('lane')}  {lane.get('chars', 0)} chars  "
                    f"{lane.get('sources', 0)} source(s)  {lane.get('purpose', '')}"
                )
        elif kind == "answer-audit":
            lines.append(
                f"{idx:3d}  answer audit  {source.get('status', 'unknown')}  "
                f"strong {source.get('strong_evidence_sources', 0)}  "
                f"context {source.get('context_sources', 0)}  "
                f"total {source.get('total_sources', 0)}"
            )
            lines.append(f"     reflection: {source.get('reflection', '')}")
            lines.append(f"     action: {source.get('recommended_action', '')}")
            if source.get("warnings"):
                for warning in source.get("warnings", [])[:3]:
                    lines.append(f"     warning: {warning}")
            if source.get("paths"):
                lines.append("     paths: " + ", ".join(source.get("paths", [])[:4]))
        elif kind == "recent-conversation":
            selection = ",".join(source.get("selection", [])) or "-"
            lines.append(
                f"{idx:3d}  recent conversation {source.get('conversation_id', '')}  "
                f"{selection}  "
                f"score {source.get('score', 0)}  "
                f"match {source.get('matched_terms', 0)}  "
                f"updated {relative_time(source.get('updated', ''))}  "
                f"{source.get('title', '')}"
            )
            lines.append(f"     why: selected by {selection} lane")
        elif kind == "file":
            lines.append(f"{idx:3d}  file  {source.get('path', '')}  {source.get('bytes', 0)} bytes")
            lines.append("     why: explicitly attached file")
        elif kind == "repo":
            lines.append(
                f"{idx:3d}  repo {source.get('command', '')}  "
                f"{source.get('root', '')}  {source.get('bytes', 0)} bytes"
            )
            lines.append("     why: explicitly attached read-only repo report")
        elif kind == "index":
            lines.append(
                f"{idx:3d}  index {source.get('id', '')}  "
                f"{source.get('status', 'unknown')}  "
                f"{source.get('retrieval', 'summary')} retrieval  {source.get('name', '')}"
            )
            profile = source.get("corpus_profile_schema", "")
            profile_note = f"; {profile} corpus profile" if profile else ""
            lines.append(f"     why: attached document index summary, retrieval root{profile_note}")
            if source.get("hybrid_candidates") is not None:
                route = source.get("hybrid_rerank_route", "")
                rerank = f"rerank={source.get('hybrid_rerank', False)}"
                if route:
                    rerank += f" via {route}"
                lines.append(f"     hybrid: {source.get('hybrid_candidates', 0)} candidate(s), {rerank}")
            if source.get("evidence_store"):
                lines.append(
                    f"     evidence: {source.get('evidence_rows', 0)} row(s) from {source.get('evidence_store', '')}"
                )
            if source.get("temporal_selected_dates"):
                lines.append("     temporal: selected newest dates present in source: " + ", ".join(source.get("temporal_selected_dates", [])[:8]))
            if source.get("activated_skills"):
                lines.append("     activated skills: " + ", ".join(source.get("activated_skills", [])[:8]))
            for warning in source.get("warnings", [])[:3]:
                lines.append(f"     warning: {warning}")
        elif kind == "topic":
            lines.append(
                f"{idx:3d}  topic {source.get('id', '')}  "
                f"{source.get('name', '')}  query: {source.get('query', '')}"
            )
            lines.append("     why: attached or auto-selected topic dossier")
        elif kind == "topic-evidence":
            lines.append(
                f"{idx:3d}  topic evidence  {source.get('path', '')} "
                f"chunk {source.get('chunk')}  topic {source.get('topic', '')}"
            )
            lines.append("     why: relevant evidence excerpt from topic dossier")
        elif kind == "dossier":
            lines.append(
                f"{idx:3d}  memory dossier {source.get('id', '')}  "
                f"{source.get('name', '')}  query: {source.get('query', '')}"
            )
            lines.append("     why: attached or auto-selected query-focused memory dossier")
        elif kind == "dossier-memory":
            lines.append(
                f"{idx:3d}  dossier memory  {source.get('memory', '')}  "
                f"dossier {source.get('dossier', '')}  {source.get('source', '')}"
            )
            lines.append("     why: memory excerpt selected inside attached dossier")
        elif kind == "dossier-conversation":
            lines.append(
                f"{idx:3d}  dossier conversation {source.get('conversation_id', '')}  "
                f"updated {relative_time(source.get('updated', ''))}  "
                f"{source.get('title', '')}"
            )
            lines.append("     why: prior conversation excerpt selected inside attached dossier")
        elif kind == "file-summary":
            lines.append(
                f"{idx:3d}  file summary  {source.get('path', '')}  "
                f"index {source.get('index', '')}  {source.get('status', 'unknown')}"
            )
            lines.append("     why: relevant file summary from attached index")
        elif kind == "chunk":
            lines.append(
                f"{idx:3d}  chunk  {source.get('path', '')} "
                f"chunk {source.get('chunk')}  index {source.get('index', '')}"
            )
            methods = ",".join(source.get("retrieval_methods", []) or [source.get("retrieval", "")]).strip(",")
            score_bits = []
            if source.get("hybrid_score") is not None:
                score_bits.append(f"hybrid {source.get('hybrid_score')}")
            if source.get("rerank_score") is not None:
                score_bits.append(f"rerank {source.get('rerank_score')}")
            if source.get("lexical_score") is not None:
                score_bits.append(f"lex {source.get('lexical_score')}")
            if source.get("evidence_score") is not None:
                score_bits.append(f"evidence {source.get('evidence_score')}")
            lines.append(
                "     why: relevant chunk retrieved from attached index"
                + (f" via {methods}" if methods else "")
                + (f"; {'; '.join(score_bits)}" if score_bits else "")
            )
            if source.get("excerpt_selection"):
                spans = source.get("excerpt_spans") or []
                span_bits = [
                    format_source_span_detail(span)
                    for span in spans[:6]
                    if isinstance(span, dict)
                ]
                detail = ", ".join(bit for bit in span_bits if bit)
                if len(spans) > 6:
                    more = f"+{len(spans) - 6} more"
                    detail = f"{detail}, {more}" if detail else more
                lines.append(
                    "     span: "
                    + str(source.get("excerpt_selection", ""))
                    + (f" ({detail})" if detail else "")
                )
            if source.get("temporal_selected_dates"):
                lines.append("     temporal: selected newest dates present in source: " + ", ".join(source.get("temporal_selected_dates", [])[:8]))
            for warning in source.get("excerpt_warnings", [])[:2]:
                lines.append(f"     warning: {warning}")
        else:
            lines.append(f"{idx:3d}  {json.dumps(source, ensure_ascii=False)}")
    return "\n".join(lines)
