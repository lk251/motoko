"""Durable memory row helpers for Motoko."""

from __future__ import annotations

import json
import pathlib
import uuid

from motoko_core.state import atomic_write, read_jsonl


DEFAULT_MEMORY_IMPORTANCE = 3
MAX_MEMORY_IMPORTANCE = 5


def memory_id() -> str:
    return "mem-" + uuid.uuid4().hex[:10]


def normalize_memory_row(
    row: dict,
    ordinal: int,
    *,
    default_importance: int = DEFAULT_MEMORY_IMPORTANCE,
    max_importance: int = MAX_MEMORY_IMPORTANCE,
) -> dict:
    normalized = dict(row)
    normalized.setdefault("id", f"legacy-{ordinal:04d}")
    normalized.setdefault("created", "")
    normalized.setdefault("source", "unknown")
    normalized.setdefault("text", "")
    normalized.setdefault("importance", default_importance)
    normalized.setdefault("pinned", False)
    normalized.setdefault("tags", [])
    try:
        normalized["importance"] = max(
            1,
            min(max_importance, int(normalized.get("importance", default_importance))),
        )
    except (TypeError, ValueError):
        normalized["importance"] = default_importance
    if not isinstance(normalized.get("tags"), list):
        normalized["tags"] = []
    normalized["pinned"] = bool(normalized.get("pinned"))
    return normalized


def read_memory_rows_file(path: pathlib.Path) -> list[dict]:
    return read_jsonl(path)


def load_memory_rows(
    path: pathlib.Path,
    *,
    limit: int = 80,
    default_importance: int = DEFAULT_MEMORY_IMPORTANCE,
    max_importance: int = MAX_MEMORY_IMPORTANCE,
) -> list[dict]:
    rows = [
        normalize_memory_row(
            row,
            idx,
            default_importance=default_importance,
            max_importance=max_importance,
        )
        for idx, row in enumerate(read_memory_rows_file(path), 1)
    ]
    return rows[-limit:]


def write_memory_rows_file(path: pathlib.Path, rows: list[dict]) -> None:
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    atomic_write(path, text)
