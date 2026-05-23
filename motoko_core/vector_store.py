"""Pure vector-store helpers for Motoko."""

from __future__ import annotations

import hashlib
import re

from motoko_core.retrieval import token_counts
from motoko_core.text import compact_text, compact_text_middle

DEFAULT_LEXICAL_VECTOR_DIMS = 256
VECTOR_METHOD_AUTO = "auto"
LEXICAL_VECTOR_METHOD = "lexical-hash-v1"
EMBEDDING_VECTOR_METHOD = "embedding-v1"


def dense_normalize(values) -> list[float]:
    vector = []
    for value in values if isinstance(values, list) else []:
        try:
            vector.append(float(value))
        except (TypeError, ValueError):
            continue
    norm = sum(value * value for value in vector) ** 0.5
    if norm <= 0:
        return []
    return [round(value / norm, 6) for value in vector]


def parse_embedding_response(payload: dict, expected_count: int) -> list[list[float]]:
    if isinstance(payload.get("embedding"), list):
        embeddings = [dense_normalize(payload.get("embedding"))]
    else:
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise RuntimeError("embedding response did not contain data")
        indexed = []
        for ordinal, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            embedding = dense_normalize(row.get("embedding"))
            if not embedding:
                continue
            try:
                index = int(row.get("index", ordinal))
            except (TypeError, ValueError):
                index = ordinal
            indexed.append((index, embedding))
        indexed.sort(key=lambda item: item[0])
        embeddings = [embedding for _index, embedding in indexed]
    if len(embeddings) != expected_count:
        raise RuntimeError(f"embedding response count mismatch: expected {expected_count}, got {len(embeddings)}")
    return embeddings


def parse_rerank_response(payload, expected_count: int) -> list[float]:
    if isinstance(payload, dict) and isinstance(payload.get("scores"), list):
        scores = []
        for value in payload.get("scores", [])[:expected_count]:
            try:
                scores.append(float(value))
            except (TypeError, ValueError):
                scores.append(0.0)
        if len(scores) == expected_count:
            return scores
    rows = []
    if isinstance(payload, dict):
        raw_rows = payload.get("results")
        if raw_rows is None:
            raw_rows = payload.get("data")
    else:
        raw_rows = payload
    if not isinstance(raw_rows, list):
        raise RuntimeError("rerank response did not contain results")
    scores_by_index: dict[int, float] = {}
    for ordinal, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("index", row.get("document_index", ordinal)))
        except (TypeError, ValueError):
            index = ordinal
        value = (
            row.get("relevance_score")
            if "relevance_score" in row
            else row.get("score", row.get("rank_score", row.get("logit")))
        )
        try:
            score = float(value)
        except (TypeError, ValueError):
            score = 0.0
        if 0 <= index < expected_count:
            scores_by_index[index] = score
    if not scores_by_index:
        raise RuntimeError("rerank response did not contain scores")
    for index in range(expected_count):
        rows.append(scores_by_index.get(index, 0.0))
    return rows


def sparse_dot(left: dict, right: dict) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    total = 0.0
    for key, value in left.items():
        try:
            total += float(value) * float(right.get(key, 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
    return total


def lexical_sparse_vector(text: str, *, dims: int = DEFAULT_LEXICAL_VECTOR_DIMS) -> dict[str, float]:
    dims = max(8, int(dims or DEFAULT_LEXICAL_VECTOR_DIMS))
    counts = token_counts(text)
    buckets: dict[int, float] = {}
    for term, count in counts.items():
        if not term:
            continue
        digest = hashlib.sha256(term.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dims
        weight = (1.0 + min(4, count) ** 0.5) * (1.2 if len(term) >= 7 else 1.0)
        buckets[bucket] = buckets.get(bucket, 0.0) + weight
    norm = sum(value * value for value in buckets.values()) ** 0.5
    if norm <= 0:
        return {}
    return {
        str(bucket): round(value / norm, 6)
        for bucket, value in sorted(buckets.items())
        if value
    }


def vector_similarity(left, right) -> float:
    if isinstance(left, dict) and isinstance(right, dict):
        return sparse_dot(left, right)
    if isinstance(left, list) and isinstance(right, list):
        total = 0.0
        for lval, rval in zip(left, right):
            try:
                total += float(lval) * float(rval)
            except (TypeError, ValueError):
                continue
        return total
    return 0.0


def split_embedding_content_parts(content: str, budget: int, max_parts: int) -> list[str]:
    text = re.sub(r"\s+", " ", content.strip())
    if not text:
        return []
    budget = max(120, int(budget or 0))
    max_parts = max(1, int(max_parts or 1))
    if len(text) <= budget:
        return [text]
    step = max(1, int(budget * 0.85))
    parts = []
    start = 0
    while start < len(text) and len(parts) < max_parts:
        end = min(len(text), start + budget)
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start += step
    if start < len(text) and len(parts) >= max_parts:
        parts[-1] = text[-budget:].strip()
    return [part for part in parts if part]


def bounded_vector_embedding_text(header: str, body: str, *, limit: int) -> str:
    if len(header) >= limit and body.strip():
        header = compact_text(header, max(120, int(limit * 0.45)))
    elif len(header) >= limit:
        return compact_text(header, limit)
    remaining = max(0, limit - len(header) - len("\ncontent: "))
    if body.strip() and remaining:
        return f"{header}\ncontent: {compact_text_middle(body, remaining)}"
    return header


def parse_vector_query_input(text: str) -> tuple[str, bool]:
    pieces = str(text or "").split()
    rerank = "--rerank" in pieces
    if rerank:
        pieces = [piece for piece in pieces if piece != "--rerank"]
    return " ".join(pieces).strip(), rerank
