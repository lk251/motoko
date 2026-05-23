"""Pure retrieval scoring helpers for Motoko."""

from __future__ import annotations

import collections
import hashlib
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
