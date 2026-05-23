"""Slash-command helpers for Motoko."""

from __future__ import annotations


def slash_command_value(command: str) -> str:
    parts = command.split()
    if not parts:
        return command
    if parts[0] == "/memory" and len(parts) > 1:
        return " ".join(parts[:2])
    return parts[0]


def command_menu_text(commands: list[tuple[str, str]], *, title: str = "Chat commands:") -> str:
    lines = [title]
    for command, description in commands:
        lines.append(f"  {command:<24} {description}")
    return "\n".join(lines)


def command_names(commands: list[tuple[str, str]]) -> list[str]:
    return sorted({slash_command_value(command) for command, _description in commands})
