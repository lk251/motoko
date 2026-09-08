"""Incremental terminal decoding and conservative unmarked-paste detection.

No terminal reads or sleeps live here: incomplete input yields to the UI loop.
Bracketed paste is authoritative; timing is only a fallback for plain tmux
paste-buffer/older terminals, where a paste and fast typing are indistinguishable.
"""

from __future__ import annotations

from dataclasses import dataclass


# Match openai/codex's LARGE_PASTE_CHAR_THRESHOLD (verified 2026-09-08):
# https://github.com/openai/codex/blob/main/codex-rs/tui/src/bottom_pane/chat_composer.rs
LARGE_PASTE_CHAR_THRESHOLD = 1000
PASTE_CHAR_INTERVAL = 0.008
PASTE_ENTER_GUARD = 0.120
ESCAPE_TIMEOUT = 0.030
BRACKETED_PASTE_ENABLE = "\x1b[?2004h"
BRACKETED_PASTE_DISABLE = "\x1b[?2004l"


@dataclass(frozen=True)
class Paste:
    text: str
    replace_previous: int = 0


KEYS = {
    b"\x1b[A": "up", b"\x1b[B": "down", b"\x1b[C": "right", b"\x1b[D": "left",
    b"\x1b[H": "home", b"\x1b[F": "end", b"\x1b[1~": "home", b"\x1b[4~": "end",
    b"\x1b[3~": "delete", b"\x1bb": "word-left", b"\x1bf": "word-right",
    b"\x1bB": "word-left", b"\x1bF": "word-right", b"\x1b\x7f": "word-backspace",
    b"\x1b\b": "word-backspace", b"\x1b\r": "newline", b"\x1b\n": "newline",
}


class TerminalInput:
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.updated_at = 0.0
        self.in_paste = False
        self.paste_chunks: list[bytes] = []

    def feed(self, data: bytes, now: float) -> None:
        self.buffer.extend(data)
        self.updated_at = now

    def pop(self, now: float) -> str | Paste | None:
        if self.in_paste:
            marker = b"\x1b[201~"
            end = self.buffer.find(marker)
            if end < 0:
                # Keep only a possible split terminator in the parsing buffer.
                take = max(0, len(self.buffer) - len(marker) + 1)
                if take:
                    self.paste_chunks.append(bytes(self.buffer[:take]))
                    del self.buffer[:take]
                return None
            self.paste_chunks.append(bytes(self.buffer[:end]))
            del self.buffer[:end + len(marker)]
            text = b"".join(self.paste_chunks).decode("utf-8", errors="replace")
            self.paste_chunks.clear()
            self.in_paste = False
            return Paste(text)
        if not self.buffer:
            return None
        if self.buffer[0] == 0x1b:
            if self.buffer.startswith(b"\x1b[200~"):
                del self.buffer[:6]
                self.in_paste = True
                return "paste-start"
            if len(self.buffer) >= 2 and self.buffer[1] not in (ord("["), ord("O")):
                size = 2
            else:
                size = next((i + 1 for i in range(2, len(self.buffer))
                             if 0x40 <= self.buffer[i] <= 0x7e), 0)
            if not size:
                if len(self.buffer) > 1 and b"\x1b[200~".startswith(self.buffer):
                    return None
                if now - self.updated_at < ESCAPE_TIMEOUT:
                    return None
                self.buffer.clear()
                return "escape"
            sequence = bytes(self.buffer[:size])
            del self.buffer[:size]
            if sequence.startswith((b"\x1b[5;", b"\x1b[6;")) or sequence in (b"\x1b[5~", b"\x1b[6~"):
                return "pageup" if sequence[2:3] == b"5" else "pagedown"
            return KEYS.get(sequence, "escape")
        first = self.buffer[0]
        size = 1 if first < 0xc2 else 2 if first < 0xe0 else 3 if first < 0xf0 else 4 if first <= 0xf4 else 1
        if len(self.buffer) < size:
            return None
        # Consume only valid continuation bytes; don't swallow a following key.
        for i in range(1, size):
            if not 0x80 <= self.buffer[i] <= 0xbf:
                size = i
                break
        data = bytes(self.buffer[:size])
        del self.buffer[:size]
        return data.decode("utf-8", errors="replace")


class PasteBurst:
    """Echo initial characters immediately, then capture a rapid text burst.

Only the first two echoed characters may need replacing when the burst flushes.
Enter is briefly held to catch even a one-character first line of an unmarked
paste. Non-text keys flush first, so editing never reorders or loses input.
"""

    def __init__(self) -> None:
        self.prefix = ""
        self.parts: list[str] = []
        self.replace_previous = 0
        self.last_at = -1.0
        self.guard_until = -1.0
        self.pending_enter: str | None = None

    @property
    def pending(self) -> bool:
        return bool(self.parts or self.pending_enter)

    def flush(self, now: float, *, force: bool = False) -> list[str | Paste]:
        if not force and now - self.last_at < PASTE_CHAR_INTERVAL:
            return []
        events: list[str | Paste] = []
        if self.parts:
            events.append(Paste("".join(self.parts), self.replace_previous))
            self.guard_until = now + PASTE_ENTER_GUARD
        elif self.pending_enter:
            events.append(self.pending_enter)
        self.parts = []
        self.replace_previous = 0
        self.pending_enter = None
        self.prefix = ""
        return events

    def feed(self, key: str | Paste, now: float) -> list[str | Paste]:
        events = self.flush(now)
        text_key = isinstance(key, str) and len(key) == 1 and (
            key in "\r\n\t" or (key >= " " and not "\x7f" <= key <= "\x9f")
        )
        if not text_key:
            events.extend(self.flush(now, force=True))
            self.guard_until = -1.0
            self.last_at = -1.0
            events.append(key)
            return events
        rapid = now - self.last_at < PASTE_CHAR_INTERVAL
        if self.parts:
            self.parts.append(key)
        elif self.pending_enter:
            self.parts = [self.pending_enter, key]
            self.pending_enter = None
        elif key in "\r\n\t" and (rapid and self.prefix or now < self.guard_until):
            self.parts = [self.prefix, key]
            self.replace_previous = len(self.prefix)
            self.prefix = ""
        elif key in "\r\n\t":
            self.pending_enter = key
            self.prefix = ""
        elif rapid and len(self.prefix) >= 2:
            self.parts = [self.prefix, key]
            self.replace_previous = len(self.prefix)
            self.prefix = ""
        else:
            self.prefix = self.prefix + key if rapid else key
            events.append(key)
        self.last_at = now
        return events


def normalize_paste(text: str) -> str:
    # Preserve line breaks and indentation, but never emit terminal controls.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(char for char in text if char in "\n\t" or (char >= " " and not "\x7f" <= char <= "\x9f"))


def folded_paste_display(text: str, cursor: int, spans: list[tuple[int, int]]) -> tuple[str, int]:
    parts = []
    offset = 0
    shown_cursor = cursor
    for start, end in spans:
        label = f"[Pasted {end - start} characters]"
        parts.extend((text[offset:start], label))
        if cursor >= end:
            shown_cursor += len(label) - (end - start)
        elif cursor > start:
            shown_cursor -= cursor - start
        offset = end
    parts.append(text[offset:])
    return "".join(parts), shown_cursor
