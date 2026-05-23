"""Slash-command helpers for Motoko."""

from __future__ import annotations


def slash_command_value(command: str) -> str:
    parts = command.split()
    if not parts:
        return command
    if parts[0] == "/memory" and len(parts) > 1:
        return " ".join(parts[:2])
    return parts[0]


def command_primary(text: str) -> str:
    return str(text or "").strip().split(maxsplit=1)[0] if str(text or "").strip() else ""


def command_body(text: str) -> str:
    stripped = str(text or "").strip()
    if not stripped:
        return ""
    parts = stripped.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def command_matches(text: str, command: str, *, allow_body: bool = True) -> bool:
    if command_primary(text) != command:
        return False
    return allow_body or not command_body(text)


def command_matches_any(text: str, commands: set[str] | tuple[str, ...], *, allow_body: bool = True) -> bool:
    return any(command_matches(text, command, allow_body=allow_body) for command in commands)


def command_menu_text(commands: list[tuple[str, str]], *, title: str = "Chat commands:") -> str:
    lines = [title]
    for command, description in commands:
        lines.append(f"  {command:<24} {description}")
    return "\n".join(lines)


def command_names(commands: list[tuple[str, str]]) -> list[str]:
    return sorted({slash_command_value(command) for command, _description in commands})
