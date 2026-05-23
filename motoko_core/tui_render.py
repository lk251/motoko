"""Pure TUI display helpers for Motoko."""

from __future__ import annotations

from motoko_core.terminal import (
    highlight_report_line,
    strip_ansi,
    style,
    tui_marker,
    worked_line,
    working_text,
    wrap_display_line,
)


def overlay_display_lines(title: str, body_lines: list[str], width: int) -> list[str]:
    rows = []
    rows.extend(wrap_display_line(style(title or "help", "purple", "bold") + style("  Enter/Esc closes", "dim"), width))
    rows.append("")
    for raw in body_lines or []:
        if raw.startswith("error "):
            text = style(raw, "red")
        elif raw.endswith(":") and not raw.startswith(" "):
            text = style(raw, "turquoise", "bold")
        elif raw.startswith("  /") or raw.startswith("  motoko"):
            command, sep, rest = raw.strip().partition("  ")
            text = "  " + style(command, "turquoise", "bold") + (sep + style(rest, "dim") if sep else "")
        else:
            text = highlight_report_line(raw)
        rows.extend(wrap_display_line(text, width))
    return rows or [""]


def dropdown_display_lines(
    options: list[dict],
    selected_index: int,
    width: int,
    *,
    max_rows: int = 8,
) -> list[str]:
    if not options:
        return []
    max_rows = min(max_rows, len(options))
    start = min(
        max(0, selected_index - max_rows + 1),
        max(0, len(options) - max_rows),
    )
    visible_options = options[start : start + max_rows]
    rows = []
    for offset, option in enumerate(visible_options):
        idx = start + offset
        marker = ">" if idx == selected_index else " "
        label = strip_ansi(str(option.get("label", "")))
        description = strip_ansi(str(option.get("description", "")))
        text = f" {marker} {label}"
        if description:
            remaining = max(0, width - len(strip_ansi(text)) - 3)
            text += "  " + description[:remaining]
        if idx == selected_index:
            rows.append(style(text[:width], "bold", "purple"))
        else:
            rows.append(text[:width])
    return rows


def message_display_lines(
    entry: dict,
    width: int,
    *,
    assistant_color: str,
    active_answer: bool = False,
    answer_phase: str = "",
    answer_phase_elapsed: float = 0.0,
) -> list[str]:
    lines = []
    code = False
    role = entry.get("role", "?")
    content = entry.get("content", "")
    if active_answer:
        lines.append(tui_marker(assistant_color, active=True) + working_text(answer_phase, answer_phase_elapsed))
        lines.append("")
    if role == "worked":
        return [worked_line(str(content), width), ""]
    if active_answer and not content:
        return lines
    if role == "user":
        prefix = style("> ", "turquoise", "bold")
    elif role == "assistant":
        prefix = tui_marker(assistant_color)
    elif role == "queued":
        prefix = style("queued ", "yellow", "bold")
    elif role == "error":
        prefix = style("error ", "red", "bold")
    elif role == "summary":
        prefix = style("summary ", "magenta", "bold")
    else:
        prefix = tui_marker("yellow")
    body_width = width - len(strip_ansi(prefix))
    wrapped = []
    for raw_line in content.splitlines() or [""]:
        if raw_line.startswith("```"):
            code = not code
            wrapped.extend(wrap_display_line(style(raw_line, "magenta"), body_width, word_wrap=False))
            continue
        if code:
            wrapped.extend(wrap_display_line(style(raw_line, "green"), body_width, word_wrap=False))
        elif role == "system":
            wrapped.extend(wrap_display_line(highlight_report_line(raw_line), body_width))
        elif raw_line.startswith(("/", "motoko ")):
            wrapped.extend(wrap_display_line(style(raw_line, "turquoise"), body_width))
        elif raw_line.startswith(("- ", "* ", "  /", "  motoko")):
            wrapped.extend(wrap_display_line(style(raw_line, "dim"), body_width))
        else:
            wrapped.extend(wrap_display_line(raw_line, body_width))
    for idx, line in enumerate(wrapped):
        lines.append((prefix if idx == 0 else " " * len(strip_ansi(prefix))) + line)
    lines.append("")
    return lines or [""]
