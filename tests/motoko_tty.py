#!/usr/bin/env python3
"""Pseudo-terminal checks for Motoko TUI rendering.

These tests stay stdlib-only but exercise the renderer through a real pty so
terminal-size handling is closer to a tty/tmux session than pure string tests.
"""

from __future__ import annotations

import collections
import fcntl
import importlib.machinery
import importlib.util
import os
import pathlib
import pty
import select
import struct
import sys
import termios
import tempfile
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from motoko_core.commands import (
    command_body,
    command_matches,
    command_matches_any,
    command_menu_text,
    command_names,
    command_primary,
    slash_command_value,
)
from motoko_core.feedback import is_feedback_command, parse_feedback_command
from motoko_core.input_edit import (
    delete_word_left,
    move_word_left,
    move_word_right,
    next_history_entry,
    previous_history_entry,
)
from motoko_core.tui_render import (
    bottom_clear_sequence,
    dropdown_display_lines,
    lines_at_cursor_sequence,
    message_display_lines,
    overlay_display_lines,
)


SOURCE = pathlib.Path(os.environ.get("MOTOKO_SOURCE", "motoko"))


def load_motoko():
    loader = importlib.machinery.SourceFileLoader("motoko", str(SOURCE))
    spec = importlib.util.spec_from_loader("motoko", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def set_winsz(fd: int, rows: int, cols: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def read_available(fd: int) -> str:
    chunks = []
    deadline = time.monotonic() + 0.25
    while time.monotonic() < deadline:
        readable, _writeable, _errors = select.select([fd], [], [], 0.02)
        if not readable:
            continue
        try:
            chunks.append(os.read(fd, 65536))
        except OSError:
            break
    return b"".join(chunks).decode("utf-8", errors="replace")


def fake_tui(m, slave_fd: int):
    ui = object.__new__(m.MotokoTui)
    ui.conv = m.new_conversation("PTY Resize Probe")
    ui.stdin_fd = slave_fd
    ui.stdout_fd = slave_fd
    ui.running = True
    ui.dirty = True
    ui.status = "ready"
    ui.maintenance_status = ""
    ui.maintenance_phase_started = time.monotonic()
    ui.input_buffer = "/"
    ui.cursor = 1
    ui.kill_ring = ""
    ui.history = []
    ui.history_index = None
    ui.scroll = 0
    ui.dropdown_index = 9
    ui.events = collections.deque()
    ui.events_lock = m.threading.Lock()
    ui.generating = False
    ui.report_running = 0
    ui.report_status = ""
    ui.maintaining = False
    ui.study_running = False
    ui.study_status = "study: idle"
    ui.study_last_note = ""
    ui.study_phase_started = time.monotonic()
    ui.last_input_at = time.monotonic()
    ui.cancel_event = m.threading.Event()
    ui.pending_prompts = collections.deque()
    ui.answer_entry = None
    ui.last_render = 0.0
    ui.tui_spinner_frames = m.spinner_frames() or ["*"]
    ui.tui_spinner_index = 0
    ui.overlay_title = None
    ui.overlay_lines = None
    ui.overlay_scroll = 0
    ui.messages = ui.seed_messages(ui.conv)
    ui.messages.append({"role": "user", "content": "resize redraw probe"})
    ui.messages.append({"role": "assistant", "content": "checking pty dimensions"})
    return ui


def main() -> int:
    old_state = os.environ.get("MOTOKO_STATE_HOME")
    old_config = os.environ.get("MOTOKO_CONFIG_HOME")
    assert move_word_left("alpha beta", 10) == 6
    assert move_word_right("alpha beta", 0) == 5
    assert delete_word_left("alpha beta", 10) == ("alpha ", 6, "beta")
    assert previous_history_entry(["one", "two"], None) == (1, "two")
    assert next_history_entry(["one", "two"], 1) == (None, "")
    commands = [("/help", "show help"), ("/memory search TEXT", "search memories")]
    assert slash_command_value("/memory search TEXT") == "/memory search"
    assert command_primary("/models qwen35-2b-worker") == "/models"
    assert command_body("/models qwen35-2b-worker") == "qwen35-2b-worker"
    assert command_primary("   /status   ") == "/status"
    assert command_body("   /status   ") == ""
    assert command_matches("/status", "/status")
    assert not command_matches("/status extra", "/status", allow_body=False)
    assert command_matches_any("/down missed sources", ("/up", "/down"))
    assert is_feedback_command("/up helpful")
    assert not is_feedback_command("/upward helpful")
    assert parse_feedback_command("/down missed sources") == ("down", "missed sources")
    assert command_names(commands) == ["/help", "/memory search"]
    assert "search memories" in command_menu_text(commands)
    overlay = "\n".join(overlay_display_lines("status", ["routes:", "  /status  show state"], 60))
    assert "status" in overlay
    assert "routes:" in overlay
    dropdown = dropdown_display_lines(
        [
            {"label": "/status", "description": "show state"},
            {"label": "/sources", "description": "show evidence"},
        ],
        1,
        60,
    )
    assert len(dropdown) == 2
    assert "/sources" in dropdown[1]
    message = "\n".join(
        message_display_lines(
            {"role": "assistant", "content": "```text\ncopy this\n```"},
            60,
            assistant_color="cyan",
        )
    )
    assert "copy this" in message
    assert bottom_clear_sequence(3, 1) == "\033[1A\r\033[J"
    assert lines_at_cursor_sequence(["one", "two"]) == "\rone\033[K\n\rtwo\033[K"
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["MOTOKO_STATE_HOME"] = str(pathlib.Path(tmp) / "state")
        os.environ["MOTOKO_CONFIG_HOME"] = str(pathlib.Path(tmp) / "config")
        m = load_motoko()
        master_fd, slave_fd = pty.openpty()
        try:
            ui = fake_tui(m, slave_fd)
            set_winsz(slave_fd, 14, 50)
            assert ui.terminal_size().columns == 50
            ui.render(force=True)
            first = read_available(master_fd)
            assert "\x1b[H" not in first
            assert "PTY Resize Probe" in first
            assert "resize redraw probe" in first
            assert "checking pty dimensions" in first
            assert "─" not in first

            set_winsz(slave_fd, 18, 72)
            assert ui.terminal_size().columns == 72
            ui.render(force=True)
            second = read_available(master_fd)
            assert "\x1b[H" not in second
            assert "PTY Resize Probe" in second
            assert "resize redraw probe" not in second
            assert first != second
        finally:
            os.close(master_fd)
            os.close(slave_fd)
            if old_state is None:
                os.environ.pop("MOTOKO_STATE_HOME", None)
            else:
                os.environ["MOTOKO_STATE_HOME"] = old_state
            if old_config is None:
                os.environ.pop("MOTOKO_CONFIG_HOME", None)
            else:
                os.environ["MOTOKO_CONFIG_HOME"] = old_config
    print("3 motoko tty render/input checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
