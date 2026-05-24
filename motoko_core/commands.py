"""Slash-command helpers for Motoko."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


COMMAND_KIND_REPORT = "report"
COMMAND_KIND_MUTATION = "mutation"
COMMAND_KIND_FOREGROUND_JOB = "foreground-job"
COMMAND_KIND_BACKGROUND_JOB = "background-job"
COMMAND_KIND_SESSION_CONTROL = "session-control"


@dataclass(frozen=True)
class CommandRequest:
    label: str
    run: Callable
    kind: str = COMMAND_KIND_REPORT
    mutates_state: bool = False
    blocks: bool = False

    def __iter__(self):
        yield self.label
        yield self.run

    def content_free_dict(self) -> dict:
        return {
            "label": self.label,
            "kind": self.kind,
            "mutates_state": self.mutates_state,
            "blocks": self.blocks,
        }


def command_request(
    label: str,
    run: Callable,
    *,
    kind: str = COMMAND_KIND_REPORT,
    mutates_state: bool = False,
    blocks: bool = False,
) -> CommandRequest:
    return CommandRequest(
        label=str(label),
        run=run,
        kind=str(kind),
        mutates_state=bool(mutates_state),
        blocks=bool(blocks),
    )


def normalize_command_request(
    request,
    *,
    kind: str = COMMAND_KIND_REPORT,
    mutates_state: bool = False,
    blocks: bool = False,
) -> CommandRequest | None:
    if request is None:
        return None
    if isinstance(request, CommandRequest):
        return request
    label, run = request
    return command_request(label, run, kind=kind, mutates_state=mutates_state, blocks=blocks)


def slash_command_value(command: str) -> str:
    parts = command.split()
    if not parts:
        return command
    if parts[0] in {"/memory", "/skill"} and len(parts) > 1:
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
