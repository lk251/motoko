"""Content-free status and observability helpers for Motoko."""

from __future__ import annotations

import re


def concise_error(text: str) -> str:
    """Keep endpoint bodies and service diagnostics out of ordinary chat."""
    text = str(text)
    first = text.splitlines()[0] if text.splitlines() else "Operation failed."
    status = re.search(r"HTTP\s+(\d{3})", first)
    if status:
        prefix = first[:status.start()].removesuffix("model endpoint returned ").strip()
        prefix = prefix + " " if prefix else ""
        if "exceed_context_size" in text or "exceeds the available context size" in text:
            prompt = re.search(r'(?:"n_prompt_tokens"\s*:\s*|request \()(\d+)', text)
            context = re.search(r'(?:"n_ctx"\s*:\s*|context size \()(\d+)', text)
            counts = f" ({prompt[1]} tokens; limit {context[1]})" if prompt and context else ""
            first = f"{prefix}input exceeds the model context{counts}."
        else:
            first = f"{prefix}model endpoint returned HTTP {status[1]}."
    elif "declared model file" in first:
        first = "Model file is missing or unavailable; check /models."
    first = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", first)
    first = " ".join("".join(char for char in first if char.isprintable()).split())
    summary = first[:237] + "..." if len(first) > 240 else first
    reference = re.search(r"\[error log: errors/[\w-]+\.json\]", text)
    if reference and reference[0] not in summary:
        summary = summary.split(" [error log:")[0] + " " + reference[0]
    return summary


def error_log_detail(text: str) -> str:
    # HTTP error bodies can echo private prompts. Retain status/token counts
    # and helper diagnostics, but never persist the arbitrary response body.
    lines = str(text).splitlines()
    if lines and re.search(r"HTTP\s+\d{3}", lines[0]):
        hint = str(text).partition("\nmotoko-model status:")[2]
        status = re.search(r"HTTP\s+(\d{3})", lines[0])[1]
        return (concise_error(text) + f"\nHTTP status: {status}"
                + ("\nmotoko-model status:" + hint[:16000] if hint else ""))
    return str(text)[:16000]


def background_note_is_error(note: str) -> bool:
    return bool(re.search(r"\b(?:failed|error|errors)\b|\(.*; fail\)", str(note).lower()))


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
