"""ANSI styling and terminal wrapping helpers for Motoko."""

from __future__ import annotations

import io
import os
import re
import sys
import unicodedata

from .text import human_duration_words


ANSI_STYLES = {
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "purple": "35",
    "pink": "95",
    "turquoise": "36",
    "magenta": "95",
    "cyan": "36",
    "white": "37",
}
DEFAULT_ASSISTANT_COLOR = "purple"
UI_COLOR_NAMES = {
    "red",
    "green",
    "yellow",
    "blue",
    "purple",
    "pink",
    "turquoise",
    "magenta",
    "cyan",
    "white",
}
UI_COLOR_ALIASES = {
    "aqua": "turquoise",
    "teal": "turquoise",
    "violet": "purple",
    "fuchsia": "pink",
    "bright-magenta": "pink",
    "bright_magenta": "pink",
}


def color_enabled() -> bool:
    if os.environ.get("NO_COLOR") is not None or os.environ.get("TERM", "") == "dumb":
        return False
    if sys.stdout.isatty():
        return True
    real_stdout = getattr(sys, "__stdout__", None)
    return (
        isinstance(sys.stdout, io.StringIO)
        and real_stdout is not None
        and real_stdout is not sys.stdout
        and real_stdout.isatty()
    )


def style(text: str, *names: str) -> str:
    if not color_enabled():
        return text
    codes = [ANSI_STYLES[name] for name in names if name in ANSI_STYLES]
    if not codes:
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"


def command_label(text: str) -> str:
    command, sep, rest = text.partition(" ")
    return style(command, "turquoise", "bold") + (sep + style(rest, "dim") if sep else "")


REPORT_LABEL_RE = re.compile(r"^(\s*)([A-Za-z][A-Za-z0-9 _./_-]{0,48}:)(\s*)(.*)$")
REPORT_ROW_RE = re.compile(r"^(\s*)(\d+\.?)(\s+)(.*)$")


def highlight_report_line(line: str) -> str:
    if not line:
        return line
    stripped = line.lstrip()
    indent = line[: len(line) - len(stripped)]
    lower = stripped.lower()
    if stripped.startswith(("/", "motoko ")):
        return indent + style(stripped, "turquoise", "bold")
    if lower.startswith(("error:", "error ")):
        return indent + style(stripped, "red", "bold")
    if lower.startswith(("warning:", "warning ")):
        return indent + style(stripped, "yellow", "bold")
    row_match = REPORT_ROW_RE.match(line)
    if row_match:
        return (
            row_match.group(1)
            + style(row_match.group(2), "turquoise", "bold")
            + row_match.group(3)
            + row_match.group(4)
        )
    label_match = REPORT_LABEL_RE.match(line)
    if label_match:
        label = label_match.group(2)
        label_key = label[:-1].strip().lower()
        color = "yellow" if label_key in {"warning", "warnings"} else "turquoise"
        if label_key in {"error", "failed", "failure"}:
            color = "red"
        elif label_key in {"reflection", "diagnosis", "action", "guide"}:
            color = "magenta"
        return (
            label_match.group(1)
            + style(label, color, "bold")
            + label_match.group(3)
            + label_match.group(4)
        )
    if stripped.endswith(":") and len(stripped) <= 72:
        return indent + style(stripped, "turquoise", "bold")
    if stripped.startswith(("- ", "* ")):
        return indent + style(stripped[:2], "dim") + stripped[2:]
    return line


def highlight_report_text(text: str) -> str:
    return "\n".join(highlight_report_line(line) for line in text.splitlines())


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)


def cell_width(char: str) -> int:
    if not char:
        return 0
    category = unicodedata.category(char)
    if category in {"Cc", "Cf"} or unicodedata.combining(char):
        return 0
    if unicodedata.east_asian_width(char) in {"F", "W"}:
        return 2
    return 1


def display_width(text: str) -> int:
    return sum(cell_width(char) for char in strip_ansi(text))


def split_cells(text: str, width: int, *, word_wrap: bool = False) -> list[tuple[str, int, int]]:
    width = max(1, width)
    if not text:
        return [("", 0, 0)]
    if word_wrap:
        segments: list[tuple[str, int, int]] = []
        start = 0
        length = len(text)
        while start < length:
            idx = start
            current_width = 0
            last_break = None
            while idx < length:
                char = text[idx]
                char_width = cell_width(char)
                if idx > start and current_width + char_width > width:
                    break
                if idx == start and char_width > width:
                    idx += 1
                    break
                current_width += char_width
                idx += 1
                if char.isspace():
                    last_break = idx
                if current_width >= width:
                    break
            if idx >= length:
                segments.append((text[start:length], start, length))
                break
            if last_break is not None and last_break > start:
                end = last_break
            else:
                end = max(start + 1, idx)
            segments.append((text[start:end], start, end))
            start = end
        return segments or [("", 0, 0)]
    segments: list[tuple[str, int, int]] = []
    start = 0
    current: list[str] = []
    current_width = 0
    for idx, char in enumerate(text):
        char_width = cell_width(char)
        if current and current_width + char_width > width:
            segments.append(("".join(current), start, idx))
            start = idx
            current = []
            current_width = 0
        current.append(char)
        current_width += char_width
    segments.append(("".join(current), start, len(text)))
    return segments


def cursor_segment_index(segments: list[tuple[str, int, int]], cursor: int) -> int:
    if cursor <= 0:
        return 0
    if cursor >= segments[-1][2]:
        return len(segments) - 1
    for idx, (_text, start, end) in enumerate(segments):
        if start <= cursor < end:
            return idx
        if cursor == end and idx + 1 < len(segments) and segments[idx + 1][1] == cursor:
            return idx + 1
    return len(segments) - 1


def ansi_tokens(text: str) -> list[tuple[str, str, int]]:
    tokens = []
    ansi_re = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
    idx = 0
    while idx < len(text):
        match = ansi_re.match(text, idx)
        if match:
            tokens.append(("ansi", match.group(0), 0))
            idx = match.end()
            continue
        char = text[idx]
        tokens.append(("char", char, cell_width(char)))
        idx += 1
    return tokens


def active_sgr_before(tokens: list[tuple[str, str, int]], end: int) -> str:
    active = ""
    for kind, value, _width in tokens[:end]:
        if kind == "ansi" and value.endswith("m"):
            active = "" if value == "\033[0m" else value
    return active


def trim_trailing_space_tokens(tokens: list[tuple[str, str, int]], start: int, end: int) -> int:
    while end > start and tokens[end - 1][0] == "char" and tokens[end - 1][1].isspace():
        end -= 1
    return end


def skip_leading_space_tokens(tokens: list[tuple[str, str, int]], start: int) -> int:
    while start < len(tokens) and tokens[start][0] == "char" and tokens[start][1].isspace():
        start += 1
    return start


def render_ansi_token_segment(tokens: list[tuple[str, str, int]], start: int, end: int) -> str:
    end = trim_trailing_space_tokens(tokens, start, end)
    if start >= end:
        return ""
    active = active_sgr_before(tokens, start)
    line = active
    for _kind, value, _width in tokens[start:end]:
        line += value
    if active and not line.endswith("\033[0m"):
        line += "\033[0m"
    return line


def wrap_display_part(text: str, width: int, *, word_wrap: bool) -> list[str]:
    tokens = ansi_tokens(text)
    if not tokens:
        return [""]
    lines = []
    start = 0
    while start < len(tokens):
        idx = start
        current_width = 0
        last_break = None
        while idx < len(tokens):
            kind, value, char_width = tokens[idx]
            if kind == "ansi":
                idx += 1
                continue
            if idx > start and current_width + char_width > width:
                break
            if idx == start and char_width > width:
                idx += 1
                break
            current_width += char_width
            idx += 1
            if value.isspace():
                last_break = idx
            if current_width >= width:
                break
        if idx >= len(tokens):
            lines.append(render_ansi_token_segment(tokens, start, len(tokens)))
            break
        if word_wrap and last_break is not None and last_break > start:
            end = last_break
            lines.append(render_ansi_token_segment(tokens, start, end))
            start = skip_leading_space_tokens(tokens, end)
        else:
            end = max(start + 1, idx)
            lines.append(render_ansi_token_segment(tokens, start, end))
            start = end
    return lines or [""]


def wrap_display_line(text: str, width: int, *, word_wrap: bool = True) -> list[str]:
    if width <= 4:
        return [strip_ansi(text)[:width]]
    if not text:
        return [""]
    chunks = []
    for part in str(text).splitlines() or [""]:
        chunks.extend(wrap_display_part(part, width, word_wrap=word_wrap))
    return chunks or [""]


def fixed_prompt_input_display(
    input_buffer: str,
    cursor: int,
    width: int,
    *,
    prompt: str = "> ",
    max_rows: int = 4,
) -> tuple[list[str], int, int]:
    prompt_width = display_width(prompt)
    usable = max(10, width - prompt_width)
    cursor = max(0, min(cursor, len(input_buffer)))
    # Tabs have a visible width; hard newlines are layout, never raw terminal
    # controls inside a rendered row. The saved/submitted draft is unchanged.
    cursor += 3 * input_buffer[:cursor].count("\t")
    input_buffer = input_buffer.replace("\t", "    ")
    segments = []
    offset = 0
    for line in input_buffer.split("\n"):
        segments.extend(
            (text, start + offset, end + offset)
            for text, start, end in split_cells(line, usable, word_wrap=True)
        )
        offset += len(line) + 1
    if (
        cursor == len(input_buffer)
        and segments
        and display_width(segments[-1][0]) >= usable
    ):
        segments.append(("", cursor, cursor))

    cursor_row = cursor_segment_index(segments, cursor)
    for index, (_text, start, end) in enumerate(segments):
        if start <= cursor <= end and input_buffer[end:end + 1] == "\n":
            cursor_row = index
            break
    shown_start = min(
        max(0, cursor_row - max_rows + 1),
        max(0, len(segments) - max_rows),
    )
    shown = segments[shown_start : shown_start + max_rows]
    cursor_row_offset = max(0, cursor_row - shown_start)
    _current_line, start, _end = segments[cursor_row]
    cursor_col = prompt_width + display_width(input_buffer[start:cursor]) + 1

    rows = []
    for offset, (line, _start, _end) in enumerate(shown):
        segment_index = shown_start + offset
        prefix = style(prompt, "turquoise", "bold") if segment_index == 0 else " " * prompt_width
        rows.append(prefix + line)
    return rows, cursor_row_offset, cursor_col


def tui_marker(color: str, *, active: bool = False) -> str:
    return style(("●" if active else "›") + " ", color, "bold")


def chat_phase_label(phase: str) -> str:
    phase = str(phase or "").strip().lower()
    if phase.startswith("chat:"):
        phase = phase.split(":", 1)[1].strip()
    return {
        "preparing": "Preparing",
        "thinking": "Thinking",
        "answering": "Answering",
    }.get(phase, "Working")


def compact_working_detail(text: str, *, max_chars: int = 96) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_chars:
        return compact
    return "... " + compact[-max(0, max_chars - 4) :]


def working_text(phase: str, elapsed_seconds: float, detail: str = "") -> str:
    text = chat_phase_label(phase) + " " + style(f"({human_duration_words(int(max(0, elapsed_seconds)))})", "dim")
    detail = compact_working_detail(detail)
    if detail:
        text += " " + style(detail, "dim")
    return text


def worked_line(duration: str, width: int) -> str:
    label = f"Worked for {duration} "
    filler = "─" * max(0, width - display_width(label))
    return style(label, "dim") + style(filler, "dim")
