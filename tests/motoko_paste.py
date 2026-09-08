#!/usr/bin/env python3
"""Paste checks using synthetic text, isolated state, PTYs, and a private tmux."""

from __future__ import annotations

import json
import os
import pathlib
import pty
import shutil
import subprocess
import sys
import tempfile
import termios
import time
import tty
import uuid

from motoko_tty import fake_tui, load_motoko, read_available
from motoko_core.paste import Paste, PasteBurst, TerminalInput, folded_paste_display


def draft_ui(m, fd=0):
    ui = fake_tui(m, fd)
    ui.input_buffer = ""
    ui.cursor = 0
    ui.dropdown_index = 0
    ui.cwd_index_offer = None
    ui.study_running = True
    ui.study_status = "bg-heavy: synthetic learning"
    ui.start_generation = lambda _text: (_ for _ in ()).throw(AssertionError("model call during paste test"))
    return ui


def decoder_checks():
    wire = "\x1b[200~one\r\n\t日本語🙂\r/stop\n\x03\x1b[31mred\x1b[201~"
    # Exercise every possible packet boundary, including UTF-8 and markers.
    for split in range(1, len(wire.encode())):
        decoder = TerminalInput()
        events = []
        for chunk in (wire.encode()[:split], wire.encode()[split:]):
            decoder.feed(chunk, 1.0)
            while (event := decoder.pop(1.0)) is not None:
                events.append(event)
        assert events == ["paste-start", Paste("one\r\n\t日本語🙂\r/stop\n\x03\x1b[31mred")], (split, events)
    decoder = TerminalInput()
    for octet in "\x1b[200~α\nβ\x1b[201~".encode():
        decoder.feed(bytes([octet]), 2.0)
        event = decoder.pop(2.0)
    assert event == Paste("α\nβ")
    decoder.feed(b"\x1b", 3.0)
    assert decoder.pop(3.01) is None
    assert decoder.pop(3.04) == "escape"
    decoder.feed(b"\x1b[1;5D\x1b[6;2~\x1bf", 4.0)
    assert [decoder.pop(4.0) for _ in range(3)] == ["escape", "pagedown", "word-right"]
    decoder.feed(b"\x1b[20", 5.0)
    assert decoder.pop(5.2) is None
    decoder.feed(b"0~delayed\nbody\x1b[201~", 5.3)
    assert decoder.pop(5.3) == "paste-start"
    assert decoder.pop(5.3) == Paste("delayed\nbody")


def burst_checks():
    for pasted in ("a\rb\r", "\n\nx\n", "ab\r\ncd\n", "🙂\n日本語\n", "a\tb\n", "\t\tline\n"):
        burst = PasteBurst()
        draft = ""
        sent = []

        def consume(events):
            nonlocal draft
            for event in events:
                if isinstance(event, Paste):
                    if event.replace_previous:
                        draft = draft[:-event.replace_previous]
                    draft += event.text
                elif event in "\r\n":
                    sent.append(draft)
                else:
                    draft += event

        now = 1.0
        for key in pasted:
            consume(burst.feed(key, now))
            now += 0.001
        consume(burst.flush(now + 0.01))
        assert not sent, (pasted, sent)
        assert draft == pasted
        consume(burst.feed("\r", now + 0.3))
        consume(burst.flush(now + 0.32))
        assert sent == [pasted]
    # Ordinary typing echoes immediately and one deliberate Enter submits.
    burst = PasteBurst()
    assert burst.feed("a", 1.0) == ["a"]
    assert burst.feed("b", 1.1) == ["b"]
    assert burst.feed("\r", 1.2) == []
    assert burst.flush(1.22) == ["\r"]
    # Arrow/edit keys flush a burst before moving the cursor.
    burst = PasteBurst()
    for i, key in enumerate("abc"):
        burst.feed(key, 1.0 + i * 0.001)
    assert burst.feed("left", 1.003) == [Paste("abc", 2), "left"]
    burst = PasteBurst()
    for i, key in enumerate("abc"):
        burst.feed(key, 1.0 + i * .001)
    assert burst.feed("\x7f", 1.003) == [Paste("abc", 2), "\x7f"]


def composer_checks(m):
    for count in (1000, 1001, 4302):
        ui = draft_ui(m)
        pasted = "界" * count
        ui.handle_paste(Paste(pasted))
        assert ui.input_buffer == pasted
        shown, cursor = folded_paste_display(ui.input_buffer, ui.cursor, ui.pasted_spans)
        assert shown == (pasted if count == 1000 else f"[Pasted {count} characters]")
        assert cursor == len(shown)
        ui.handle_enter()
        assert list(ui.pending_prompts) == [pasted]
        assert ui.history[-1] == pasted
        saved = json.loads(m.conversation_path(ui.conv["id"]).read_text())
        assert saved["queued_prompts"][0]["content"] == pasted
        assert ui.study_running
        ui.history_up()
        assert ui.input_buffer == pasted
        assert not ui.pasted_spans

    ui = draft_ui(m)
    ui.input_buffer = "before  after"
    ui.cursor = 7
    first, second = "x" * 1001, "y" * 1001
    ui.handle_paste(Paste(first))
    ui.handle_paste(Paste(second))
    assert ui.input_buffer == "before " + first + second + " after"
    assert len(ui.pasted_spans) == 2
    ui.handle_key("left")
    assert ui.cursor == 1008
    ui.handle_key("delete")
    assert ui.input_buffer == "before " + first + " after"
    ui.handle_key("\x7f")
    assert ui.input_buffer == "before  after"
    assert not ui.pasted_spans
    ui.handle_paste(Paste(first))
    ui.handle_key("\x0f")
    assert not ui.pasted_spans
    ui.handle_key("\x7f")
    assert ui.input_buffer == "before " + first[:-1] + " after"
    ui.handle_paste(Paste(second))
    ui.handle_key("\x01")
    ui.handle_key("\x0b")
    assert not ui.input_buffer
    ui.handle_key("\x19")
    assert ui.input_buffer == "before " + first[:-1] + second + " after"
    assert ui.pasted_spans

    ui = draft_ui(m)
    ui.handle_paste(Paste("/stop\r\n\tline two\r\n\nlast\n"))
    assert not ui.dropdown_options()
    assert ui.input_buffer == "/stop\n\tline two\n\nlast\n"
    rows, _row, _col = ui.input_display(50)
    assert all("\n" not in row and "\t" not in row for row in rows)
    ui.handle_enter()
    assert list(ui.pending_prompts) == ["/stop\n\tline two\n\nlast"]
    assert ui.study_running
    ui.handle_paste(Paste("safe\x03\x04\x1b[31m\x00text"))
    assert ui.input_buffer == "safe[31mtext"
    assert ui.running
    ui.input_buffer = "one\n\ntwo\n"
    for cursor, expected in ((0, (0, 3)), (3, (0, 6)), (4, (1, 3)), (5, (2, 3)), (8, (2, 6)), (9, (3, 3))):
        ui.cursor = cursor
        _rows, row, col = ui.input_display(50)
        assert (row, col) == expected, (cursor, row, col)
    ui.input_buffer = "x" * 48
    ui.cursor = 48
    _rows, row, col = ui.input_display(50)
    assert (row, col) == (1, 3)

    ui = draft_ui(m)
    ui.input_buffer = "keep:"
    ui.cursor = 5
    ui.overlay_lines = ["report"]
    burst = PasteBurst()
    for i, key in enumerate("abc"):
        for event in burst.feed(key, 1.0 + i * .001):
            ui.dispatch_terminal_input(event)
    for event in burst.flush(1.1):
        ui.dispatch_terminal_input(event)
    assert ui.input_buffer == "keep:abc"

    ui = draft_ui(m)
    ui.study_running = False
    sent = []
    ui.start_generation = sent.append
    ui.handle_paste(Paste("one\ntwo\nthree"))
    assert not sent
    ui.handle_enter()
    assert sent == ["one\ntwo\nthree"]
    ui.handle_paste(Paste("/stop\n\n"))
    ui.handle_enter()
    assert sent == ["one\ntwo\nthree", "/stop"]


def pty_checks(m):
    master, slave = pty.openpty()
    try:
        tty.setcbreak(slave)
        ui = draft_ui(m, slave)
        ui.input_batch_limit = 2  # Cross many input/render batches.
        wire = b"\x1b[200~first\n\n/stop\nlast\n\x1b[201~"
        for chunk in (wire[:3], wire[3:13], wire[13:-3], wire[-3:]):
            os.write(master, chunk)
            for _ in range(30):
                ui.handle_ready_input(0)
        assert ui.input_buffer == "first\n\n/stop\nlast\n"
        assert not ui.pending_prompts
        time.sleep(0.15)
        os.write(master, b"\r")
        deadline = time.monotonic() + 1
        while not ui.pending_prompts and time.monotonic() < deadline:
            ui.handle_ready_input(0.02)
        assert list(ui.pending_prompts) == ["first\n\n/stop\nlast"]
    finally:
        os.close(master)
        os.close(slave)

    # A failing renderer must still restore terminal paste and signal modes.
    master, slave = pty.openpty()
    try:
        ui = draft_ui(m, slave)
        before = termios.tcgetattr(slave)
        ui.old_termios = None
        ui.clear_bottom_area = lambda: None
        ui.render = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("synthetic render failure"))
        try:
            ui.run()
            raise AssertionError("expected the synthetic render error")
        except RuntimeError as exc:
            assert str(exc) == "synthetic render failure"
        assert before == termios.tcgetattr(slave)
        assert "\x1b[?2004l" in read_available(master)
    finally:
        os.close(master)
        os.close(slave)


def tmux_child(report_dir):
    m = load_motoko()
    ui = draft_ui(m, sys.stdin.fileno())
    ui.old_termios = None
    before = termios.tcgetattr(ui.stdin_fd)
    writes = []
    bracketed_events = []
    original_handle = ui.handle_terminal_key

    def handle(key):
        if isinstance(key, Paste):
            bracketed_events.append(key)
        original_handle(key)

    ui.handle_terminal_key = handle
    ui.write = lambda text: (writes.append(text), os.write(ui.stdout_fd, text.encode()))
    ui.clear_bottom_area = lambda: None
    ui.stop_startup_discovery = lambda: None

    def owner_loop():
        (report_dir / "ready").touch()
        deadline = time.monotonic() + 10
        while ui.running and time.monotonic() < deadline and not ui.pending_prompts:
            ui.handle_ready_input(0.01)
            m.atomic_write(report_dir / "draft", json.dumps({"text": ui.input_buffer, "queued": len(ui.pending_prompts)}))
        ui.running = False

    ui.run_terminal_owner_loop = owner_loop
    ui.run()
    m.atomic_write(report_dir / "result", json.dumps({
        "queued": list(ui.pending_prompts), "studying": ui.study_running,
        "restored": before == termios.tcgetattr(ui.stdin_fd),
        "enabled": "\x1b[?2004h" in "".join(writes),
        "disabled": "\x1b[?2004l" in "".join(writes),
        "bracketed_events": len(bracketed_events),
    }))


def wait_until(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("timed out waiting for isolated tmux paste probe")


def tmux_checks():
    assert shutil.which("tmux"), "tmux is required for the paste integration check"
    for bracketed in (True, False):
        with tempfile.TemporaryDirectory(prefix="motoko-paste-tmux-") as tmp:
            root = pathlib.Path(tmp)
            prefix = ["tmux", "-L", "motoko-paste-" + uuid.uuid4().hex, "-f", "/dev/null"]

            def tmux(*args, check=True):
                return subprocess.run(prefix + list(args), check=check, capture_output=True, text=True, timeout=5)

            try:
                tmux("new-session", "-d", "-s", "paste", "-x", "80", "-y", "24",
                     sys.executable, str(pathlib.Path(__file__).resolve()), "--tmux-child", str(root))
                wait_until(lambda: (root / "ready").exists())
                text = "x\n\n" + "  error: 日本語\n" * 340
                (root / "paste.txt").write_text(text)
                tmux("load-buffer", "-b", "probe", str(root / "paste.txt"))
                flags = ["-p"] if bracketed else []
                tmux("paste-buffer", *flags, "-b", "probe", "-t", "paste:0.0")

                def received():
                    draft = root / "draft"
                    return draft.exists() and json.loads(draft.read_text())["text"] == text

                wait_until(received)
                time.sleep(0.2)
                assert json.loads((root / "draft").read_text())["queued"] == 0
                tmux("send-keys", "-t", "paste:0.0", "Enter")
                wait_until(lambda: (root / "result").exists())
                result = json.loads((root / "result").read_text())
                assert result == {"queued": [text.strip()], "studying": True, "restored": True,
                                  "enabled": True, "disabled": True,
                                  "bracketed_events": int(bracketed)}, result
            finally:
                tmux("kill-server", check=False)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--tmux-child":
        tmux_child(pathlib.Path(sys.argv[2]))
        return
    with tempfile.TemporaryDirectory(prefix="motoko-paste-state-") as tmp:
        os.environ["MOTOKO_STATE_HOME"] = str(pathlib.Path(tmp) / "state")
        os.environ["MOTOKO_CONFIG_HOME"] = str(pathlib.Path(tmp) / "config")
        m = load_motoko()
        for check in (decoder_checks, burst_checks, lambda: composer_checks(m), lambda: pty_checks(m), tmux_checks):
            check()
        print("5 motoko paste checks passed (decoder, burst, composer, PTY, tmux)")


if __name__ == "__main__":
    main()
