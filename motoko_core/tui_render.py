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
from motoko_core.text import human_duration


def study_status_label_core(study_status: str, index_progress: dict | None, *, progress_formatter) -> str:
    if index_progress:
        return progress_formatter(index_progress)
    phase = study_status
    if phase.startswith("bg-heavy:"):
        return phase
    if "profile" in phase:
        return "bg-heavy: profile(model)"
    if "index" in phase:
        return "bg-heavy: indexing(model)"
    if "catalog" in phase:
        return "bg-light: catalog(cpu)"
    if "planning" in phase:
        return "bg-light: planning(cpu)"
    if "scanning" in phase:
        return "bg-light: scanning(cpu)"
    return f"bg: {phase}"


def status_display_lines(
    *,
    title: str,
    model_badge: str,
    width: int,
    idle_status: str,
    generating: bool,
    maintaining: bool,
    report_running: int,
    report_status: str,
    maintenance_elapsed: int,
    maintenance_phase: str,
    pending_count: int,
    study_running: bool,
    study_elapsed: int,
    study_status: str,
    study_status_label: str,
    study_last_note: str,
    attention_notice: str = "",
) -> list[str]:
    text = f"{style(title, 'turquoise', 'bold')}  {style(model_badge, 'dim')}"
    status_parts = []
    if not generating and not maintaining:
        idle_status = str(idle_status or "").strip()
        if idle_status and idle_status != "ready":
            status_parts.append(style(idle_status, "turquoise"))
    if report_running:
        label = report_status or "report"
        count = f" x{report_running}" if report_running > 1 else ""
        status_parts.append(style(f"{label}{count}", "turquoise"))
    if maintaining:
        phase = str(maintenance_phase or "")
        label = "mem: " + phase.removeprefix("memory: ")
        status_parts.append(style(f"{label} {human_duration(maintenance_elapsed)}".rstrip(), "turquoise"))
    if pending_count:
        status_parts.append(style(f"queued:{pending_count}", "yellow"))
    if attention_notice:
        status_parts.append(style(attention_notice, "yellow"))
    if study_running:
        status_parts.append(style(f"{study_status_label} {human_duration(study_elapsed)}".rstrip(), "turquoise"))
    elif study_status == "study: off":
        status_parts.append(style("bg: off", "dim"))
    elif study_last_note:
        status_parts.append(style(f"bg: idle ({study_last_note})", "dim"))
    else:
        status_parts.append(style("bg: idle", "dim"))
    if status_parts:
        text += "  " + "  ".join(status_parts)
    return [style(line, "dim") for line in wrap_display_line(text, width)]


def bottom_area_frame(
    *,
    live_lines: list[str],
    dropdown_lines: list[str],
    input_lines: list[str],
    status_lines: list[str],
    input_cursor_row_offset: int,
    input_cursor_col: int,
    width: int,
    height: int,
    truncation_marker: str,
) -> tuple[list[str], int, int]:
    max_live = max(0, height - len(dropdown_lines) - len(input_lines) - len(status_lines) - 2)
    if max_live and len(live_lines) > max_live:
        clipped_live_lines = live_lines
        tail_count = max(0, max_live - 1)
        live_lines = [style(truncation_marker, "dim")]
        if tail_count:
            live_lines.extend(clipped_live_lines[-tail_count:])
    elif not max_live:
        live_lines = []
    lines = []
    lines.extend(live_lines)
    lines.extend(dropdown_lines)
    input_start = len(lines)
    lines.extend(input_lines)
    lines.extend(status_lines)
    lines = lines or [""]
    cursor_row = input_start + input_cursor_row_offset
    cursor_col = min(width, input_cursor_col)
    return lines, cursor_row, cursor_col


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


def overlay_page_frame(body_lines: list[str], height: int, scroll: int) -> tuple[list[str], int]:
    height = max(1, height)
    max_scroll = max(0, len(body_lines) - height)
    scroll = min(max(0, scroll), max_scroll)
    visible = body_lines[scroll : scroll + height]
    rows = visible + [""] * max(0, height - len(visible))
    return rows[:height], scroll


def overlay_page_sequence(rows: list[str], height: int) -> str:
    height = max(1, height)
    visible_rows = rows[:height] + [""] * max(0, height - len(rows))
    return "\033[H" + "\n".join(f"{row}\033[K" for row in visible_rows[:height]) + "\033[J\033[?25h"


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
    answer_reasoning: str = "",
) -> list[str]:
    lines = []
    code = False
    role = entry.get("role", "?")
    content = entry.get("content", "")
    if active_answer:
        lines.append(
            tui_marker(assistant_color, active=True)
            + working_text(answer_phase, answer_phase_elapsed, answer_reasoning)
        )
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


def live_answer_display_lines(
    entry: dict | None,
    width: int,
    *,
    assistant_color: str,
    answer_phase: str,
    answer_phase_elapsed: float,
    answer_reasoning: str = "",
) -> list[str]:
    if entry is None:
        return []
    return message_display_lines(
        entry,
        width,
        assistant_color=assistant_color,
        active_answer=True,
        answer_phase=answer_phase,
        answer_phase_elapsed=answer_phase_elapsed,
        answer_reasoning=answer_reasoning,
    )


def bottom_clear_sequence(rendered_rows: int, cursor_row_offset: int) -> str:
    if rendered_rows <= 0:
        return ""
    offset = min(rendered_rows - 1, max(0, cursor_row_offset))
    sequence = ""
    if offset > 0:
        sequence += f"\033[{offset}A"
    sequence += "\r\033[J"
    return sequence


def lines_at_cursor_sequence(lines: list[str]) -> str:
    if not lines:
        return ""
    parts = []
    for idx, line in enumerate(lines):
        parts.append(f"\r{line}\033[K")
        if idx + 1 < len(lines):
            parts.append("\n")
    return "".join(parts)


def bottom_area_absolute_sequence(
    lines: list[str],
    *,
    cursor_row: int,
    cursor_col: int,
    height: int,
    previous_rows: int = 0,
) -> str:
    """Render the bottom prompt/status frame without trusting cursor history."""
    if not lines:
        return ""
    height = max(1, height)
    visible_rows = lines[:height]
    rows_to_clear = min(height, max(len(visible_rows), int(previous_rows or 0), 1))
    clear_start = max(1, height - rows_to_clear + 1)
    frame_start = max(1, height - len(visible_rows) + 1)
    target_row = min(height, frame_start + max(0, min(cursor_row, len(visible_rows) - 1)))
    target_col = max(1, int(cursor_col or 1))
    parts = [f"\033[{clear_start};1H\033[J", f"\033[{frame_start};1H"]
    for idx, line in enumerate(visible_rows):
        parts.append(f"\r{line}\033[K")
        if idx + 1 < len(visible_rows):
            parts.append("\n")
    parts.append(f"\033[{target_row};{target_col}H\033[?25h")
    return "".join(parts)
