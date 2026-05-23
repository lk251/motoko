"""Pure TUI display helpers for Motoko."""

from __future__ import annotations

from motoko_core.terminal import highlight_report_line, strip_ansi, style, wrap_display_line


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
