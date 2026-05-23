"""Pure retrieval scoring helpers for Motoko."""

from __future__ import annotations

import collections
import pathlib
import re


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
