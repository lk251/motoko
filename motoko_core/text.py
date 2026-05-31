"""Pure text, time, and size formatting helpers for Motoko."""

from __future__ import annotations

import datetime as _dt
import re


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_timestamp(value: str) -> _dt.datetime | None:
    if not value:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def relative_time(value: str) -> str:
    parsed = parse_timestamp(value)
    if parsed is None:
        return "-"
    delta = _dt.datetime.now(_dt.timezone.utc).astimezone() - parsed.astimezone()
    seconds = max(0, int(delta.total_seconds()))
    units = [
        ("y", 365 * 24 * 60 * 60),
        ("mo", 30 * 24 * 60 * 60),
        ("d", 24 * 60 * 60),
        ("h", 60 * 60),
        ("m", 60),
        ("s", 1),
    ]
    for suffix, unit_seconds in units:
        if seconds >= unit_seconds or suffix == "s":
            amount = seconds // unit_seconds
            return "now" if suffix == "s" and amount < 5 else f"{amount}{suffix} ago"
    return "now"


def compact_text(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def compact_text_middle(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= limit:
        return text
    if limit <= 12:
        return text[:limit].rstrip()
    marker = " ... "
    side = max(1, (limit - len(marker)) // 2)
    tail = max(1, limit - len(marker) - side)
    return (text[:side].rstrip() + marker + text[-tail:].lstrip())[:limit]


def compact_source_text_middle(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    if limit <= 12:
        return text[:limit].rstrip()
    marker = "\n...\n"
    side = max(1, (limit - len(marker)) // 2)
    tail = max(1, limit - len(marker) - side)
    return (text[:side].rstrip() + marker + text[-tail:].lstrip())[:limit]


def human_bytes(count: int) -> str:
    value = float(count)
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{count} B"


def human_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "?"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def human_duration_words(seconds: int | float | None) -> str:
    if seconds is None:
        return "?"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def phase_timer_key(phase: str) -> str:
    phase = str(phase or "")
    phase = re.sub(
        r"\s+(?:full|incremental|resumed|reuse-only|rebuild)"
        r"(?:\s+(?!(?:reuse|new|batch|parallel|rows|eta)\b)\S+)?"
        r"(?:\s+reuse\s+\d+)?(?:\s+new\s+\d+)?",
        "",
        phase,
    )
    phase = re.sub(r"\s+retry(?=\s|$)", "", phase)
    phase = re.sub(r"\s+batch\s+\d+/\d+.*$", "", phase)
    phase = re.sub(r"\s+rows\s+\d+/\d+.*$", "", phase)
    phase = re.sub(r"\s+file\s+\d+/\d+.*$", "", phase)
    phase = re.sub(r"\s+chunk\s+\d+/\d+.*$", "", phase)
    phase = re.sub(r"\s+eta\s+\S+.*$", "", phase)
    phase = re.sub(r"\s+call\s+\S+.*$", "", phase)
    return phase.strip()


def parse_byte_count(value: str) -> int:
    text = value.strip().lower().replace("_", "")
    match = re.fullmatch(r"(\d+)([kmgt]?i?b?|)", text)
    if not match:
        raise ValueError(f"invalid byte count: {value}")
    amount = int(match.group(1))
    suffix = match.group(2)
    multipliers = {
        "": 1,
        "b": 1,
        "k": 1024,
        "kb": 1024,
        "kib": 1024,
        "m": 1024**2,
        "mb": 1024**2,
        "mib": 1024**2,
        "g": 1024**3,
        "gb": 1024**3,
        "gib": 1024**3,
        "t": 1024**4,
        "tb": 1024**4,
        "tib": 1024**4,
    }
    return amount * multipliers[suffix]


def slug_title(text: str) -> str:
    words = re.findall(r"[\w'-]+", text.strip(), re.UNICODE)
    if not words:
        return "Untitled"
    title = " ".join(words[:8])
    return title[:80]
