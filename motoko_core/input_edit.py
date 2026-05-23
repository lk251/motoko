"""Pure prompt editing helpers for the Motoko TUI."""

from __future__ import annotations


def move_word_left(text: str, cursor: int) -> int:
    idx = max(0, min(cursor, len(text)))
    while idx > 0 and text[idx - 1].isspace():
        idx -= 1
    while idx > 0 and not text[idx - 1].isspace():
        idx -= 1
    return idx


def move_word_right(text: str, cursor: int) -> int:
    idx = max(0, min(cursor, len(text)))
    length = len(text)
    while idx < length and text[idx].isspace():
        idx += 1
    while idx < length and not text[idx].isspace():
        idx += 1
    return idx


def delete_word_left(text: str, cursor: int) -> tuple[str, int, str]:
    cursor = max(0, min(cursor, len(text)))
    if cursor <= 0:
        return text, cursor, ""
    left = text[:cursor].rstrip()
    cut = left.rfind(" ") + 1
    killed = text[cut:cursor]
    return text[:cut] + text[cursor:], cut, killed


def previous_history_entry(history: list[str], history_index: int | None) -> tuple[int | None, str | None]:
    if not history:
        return history_index, None
    if history_index is None:
        history_index = len(history) - 1
    else:
        history_index = max(0, history_index - 1)
    return history_index, history[history_index]


def next_history_entry(history: list[str], history_index: int | None) -> tuple[int | None, str | None]:
    if history_index is None:
        return None, None
    history_index += 1
    if history_index >= len(history):
        return None, ""
    return history_index, history[history_index]
