"""Content-free status and observability helpers for Motoko."""

from __future__ import annotations


OBSERVABILITY_SCHEMA = "observability-v1"

PRIVATE_FIELD_HINTS = (
    "prompt",
    "response",
    "content",
    "summary",
    "excerpt",
    "memory",
    "filename",
    "path",
    "source",
)


def scrub_observability_row(row: dict) -> dict:
    safe = {"schema": OBSERVABILITY_SCHEMA}
    for key, value in row.items():
        lowered = str(key).lower()
        if any(hint in lowered for hint in PRIVATE_FIELD_HINTS):
            safe[key] = "<redacted>"
        else:
            safe[key] = value
    return safe


def format_observability_report(rows: list[dict]) -> str:
    lines = [f"observability: {OBSERVABILITY_SCHEMA}"]
    if not rows:
        lines.append("events: none")
        return "\n".join(lines)
    for row in rows:
        safe = scrub_observability_row(row)
        fields = [
            f"{key}={value}"
            for key, value in safe.items()
            if key != "schema"
        ]
        lines.append("- " + " ".join(fields))
    return "\n".join(lines)
