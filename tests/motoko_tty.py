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
import termios
import tempfile
import time


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
    ui.messages = ui.seed_messages(ui.conv)
    ui.messages.append({"role": "user", "content": "resize redraw probe"})
    ui.messages.append({"role": "assistant", "content": "checking pty dimensions"})
    return ui


def main() -> int:
    old_state = os.environ.get("MOTOKO_STATE_HOME")
    old_config = os.environ.get("MOTOKO_CONFIG_HOME")
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
            assert "\x1b[H" in first
            assert "Motoko" in first
            assert "Suggestions" not in first

            set_winsz(slave_fd, 18, 72)
            assert ui.terminal_size().columns == 72
            ui.render(force=True)
            second = read_available(master_fd)
            assert "\x1b[H" in second
            assert "PTY Resize Probe" in second
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
    print("1 motoko tty render check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
