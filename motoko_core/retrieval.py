"""Pure retrieval scoring helpers for Motoko."""

from __future__ import annotations

import collections
import pathlib
import re

from motoko_core.text import compact_text_middle


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
