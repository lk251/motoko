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
import json
import os
import pathlib
import pty
import select
import struct
import sys
import termios
import tempfile
import time
import tty

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from motoko_core.commands import (
    COMMAND_KIND_MUTATION,
    CommandRequest,
    command_body,
    command_matches,
    command_matches_any,
    command_menu_text,
    command_names,
    command_primary,
    normalize_command_request,
    slash_command_value,
)
from motoko_core.artifact_lifecycle import (
    source_lifecycle_state,
    superseded_index_cleanup_decision,
)
from motoko_core.feedback import is_feedback_command, parse_feedback_command
from motoko_core.input_edit import (
    delete_word_left,
    move_word_left,
    move_word_right,
    next_history_entry,
    previous_history_entry,
    remember_input_history_entry,
    seed_input_history_from_messages,
)
from motoko_core.jobs import JobSupervisor, format_job_snapshots
from motoko_core.model_manager import ModelRouteManager
from motoko_core.observability import format_observability_report, scrub_observability_row
from motoko_core.retrieval_service import RetrievalService
from motoko_core.runtime import RuntimePaths, make_runtime_context
from motoko_core.terminal import strip_ansi
from motoko_core.tui_render import (
    bottom_area_absolute_sequence,
    bottom_area_frame,
    bottom_clear_sequence,
    dropdown_display_lines,
    lines_at_cursor_sequence,
    live_answer_display_lines,
    message_display_lines,
    overlay_display_lines,
    overlay_page_frame,
    overlay_page_sequence,
    status_display_lines,
    study_status_label_core,
    transcript_append_sequence,
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
    ui.foreground_running = 0
    ui.foreground_status = ""
    ui.maintaining = False
    ui.study_running = False
    ui.cwd_indexing = False
    ui.study_status = "study: idle"
    ui.study_last_note = ""
    ui.study_phase_started = time.monotonic()
    ui.study_phase_updated = ui.study_phase_started
    ui.index_progress = None
    ui.last_input_at = time.monotonic()
    ui.cancel_event = m.threading.Event()
    ui.pending_prompts = collections.deque()
    ui.answer_entry = None
    ui.answer_phase = ""
    ui.answer_started_monotonic = 0.0
    ui.answer_phase_started_monotonic = 0.0
    ui.answer_reasoning = ""
    ui.kv_notice_started_monotonic = 0.0
    ui.kv_notice_until_monotonic = 0.0
    ui.last_render = 0.0
    ui.tui_spinner_frames = m.spinner_frames() or ["*"]
    ui.tui_spinner_index = 0
    ui.overlay_title = None
    ui.overlay_lines = None
    ui.overlay_scroll = 0
    ui.ui_owner_thread_id = None
    ui.ui_owner_thread_error = None
    ui.messages = ui.seed_messages(ui.conv)
    ui.messages.append({"role": "user", "content": "resize redraw probe"})
    ui.messages.append({"role": "assistant", "content": "checking pty dimensions"})
    return ui


def catalog_latency_probe_on_pty(m, master_fd: int, slave_fd: int) -> dict:
    return m.build_tui_catalog_latency_probe(master_fd, slave_fd)


def run_catalog_latency_probe() -> dict:
    old_state = os.environ.get("MOTOKO_STATE_HOME")
    old_config = os.environ.get("MOTOKO_CONFIG_HOME")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MOTOKO_STATE_HOME"] = str(pathlib.Path(tmp) / "state")
            os.environ["MOTOKO_CONFIG_HOME"] = str(pathlib.Path(tmp) / "config")
            m = load_motoko()
            master_fd, slave_fd = pty.openpty()
            try:
                set_winsz(slave_fd, 14, 50)
                return catalog_latency_probe_on_pty(m, master_fd, slave_fd)
            finally:
                os.close(master_fd)
                os.close(slave_fd)
    finally:
        if old_state is None:
            os.environ.pop("MOTOKO_STATE_HOME", None)
        else:
            os.environ["MOTOKO_STATE_HOME"] = old_state
        if old_config is None:
            os.environ.pop("MOTOKO_CONFIG_HOME", None)
        else:
            os.environ["MOTOKO_CONFIG_HOME"] = old_config


def main() -> int:
    if "--catalog-latency-json" in sys.argv:
        result = run_catalog_latency_probe()
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("status") == "pass" else 1

    old_state = os.environ.get("MOTOKO_STATE_HOME")
    old_config = os.environ.get("MOTOKO_CONFIG_HOME")
    assert move_word_left("alpha beta", 10) == 6
    assert move_word_right("alpha beta", 0) == 5
    assert delete_word_left("alpha beta", 10) == ("alpha ", 6, "beta")
    assert previous_history_entry(["one", "two"], None) == (1, "two")
    assert next_history_entry(["one", "two"], 1) == (None, "")
    history = seed_input_history_from_messages(
        [
            {"role": "assistant", "content": "ignore"},
            {"role": "user", "content": " first "},
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
        ]
    )
    assert history == ["first", "second"]
    assert remember_input_history_entry(history, "second") == ["first", "second"]
    assert remember_input_history_entry(history, "third", limit=2) == ["second", "third"]
    commands = [("/help", "show help"), ("/memory search TEXT", "search memories")]
    assert slash_command_value("/memory search TEXT") == "/memory search"
    assert command_primary("/models qwen35-2b-worker") == "/models"
    assert command_body("/models qwen35-2b-worker") == "qwen35-2b-worker"
    assert command_primary("   /status   ") == "/status"
    assert command_body("   /status   ") == ""
    assert command_matches("/status", "/status")
    assert not command_matches("/status extra", "/status", allow_body=False)
    assert command_matches_any("/down missed sources", ("/up", "/down"))
    request = normalize_command_request(("/remember", lambda: "ok"), kind=COMMAND_KIND_MUTATION, mutates_state=True)
    assert isinstance(request, CommandRequest)
    assert request.kind == COMMAND_KIND_MUTATION
    assert request.mutates_state
    label, runner = request
    assert label == "/remember"
    assert runner() == "ok"
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
    live_answer = "\n".join(
        live_answer_display_lines(
            {"role": "assistant", "content": "answer text"},
            60,
            assistant_color="cyan",
            answer_phase="thinking",
            answer_phase_elapsed=12,
            answer_reasoning="checking sources before answering",
        )
    )
    live_answer = strip_ansi(live_answer)
    assert "Thinking (12s)" in live_answer
    assert "checking sources before answering" in live_answer
    assert "answer text" in live_answer
    status = "\n".join(
        status_display_lines(
            title="Chat",
            model_badge="model",
            width=80,
            idle_status="ready",
            generating=False,
            maintaining=False,
            report_running=0,
            report_status="",
            maintenance_elapsed=0,
            maintenance_phase="",
            pending_count=2,
            study_running=False,
            study_elapsed=0,
            study_status="study: idle",
            study_status_label="bg: idle",
            study_last_note="catalog fresh",
            attention_notice="KV not in GPU",
        )
    )
    assert "Chat" in status
    assert "queued:2" in status
    assert "KV not in GPU" in status
    assert "bg: idle (catalog fresh)" in status
    vector_status = strip_ansi(
        "\n".join(
            status_display_lines(
                title="Chat",
                model_badge="model",
                width=120,
                idle_status="ready",
                generating=False,
                maintaining=False,
                report_running=0,
                report_status="",
                maintenance_elapsed=0,
                maintenance_phase="",
                pending_count=0,
                study_running=True,
                study_elapsed=2,
                study_status="bg-heavy: vectorizing(model)",
                study_status_label="bg-heavy: vectorizing(model) resumed checkpoint rows 10/20 elapsed 5m00s eta 1m00s",
                study_last_note="",
            )
        )
    )
    assert "elapsed 5m00s" in vector_status
    assert "elapsed 5m00s eta 1m00s 2s" not in vector_status
    assert study_status_label_core("study: indexing", None, progress_formatter=lambda _row: "unused") == "bg-heavy: indexing(model)"
    frame_lines, frame_cursor_row, frame_cursor_col = bottom_area_frame(
        live_lines=["live1", "live2", "live3"],
        dropdown_lines=["choice"],
        input_lines=["> prompt"],
        status_lines=["status"],
        input_cursor_row_offset=0,
        input_cursor_col=4,
        width=80,
        height=7,
        truncation_marker="...",
    )
    assert "live1" not in frame_lines
    assert "live3" in frame_lines
    assert frame_lines[-2:] == ["> prompt", "status"]
    assert frame_cursor_row == len(frame_lines) - 2
    assert frame_cursor_col == 4
    overlay_rows, overlay_scroll = overlay_page_frame(["one", "two", "three"], 2, 9)
    assert overlay_rows == ["two", "three"]
    assert overlay_scroll == 1
    assert overlay_page_sequence(["one"], 2) == "\033[Hone\033[K\n\033[K\033[J\033[?25h"
    assert bottom_clear_sequence(3, 1) == "\033[1A\r\033[J"
    assert lines_at_cursor_sequence(["one", "two"]) == "\rone\033[K\n\rtwo\033[K"
    assert transcript_append_sequence(["one", "two"], height=10, reserved_rows=3) == (
        "\033[1;7r\033[7;1H\rone\033[K\n\rtwo\033[K\n\033[r"
    )
    anchored = bottom_area_absolute_sequence(
        ["> prompt", "status one", "status two"],
        cursor_row=0,
        cursor_col=4,
        height=10,
        previous_rows=2,
    )
    assert anchored.startswith("\033[8;1H\033[J\033[8;1H")
    assert anchored.endswith("\033[8;4H\033[?25h")
    restored = bottom_area_absolute_sequence(
        ["> prompt", "status"],
        cursor_row=0,
        cursor_col=4,
        height=8,
        previous_rows=5,
        restore_lines=["old one", "old two", "old three"],
    )
    assert "\033[4;1H\033[J\033[4;1H\rold one\033[K\n\rold two\033[K\n\rold three\033[K" in restored
    supervisor = JobSupervisor(clock=lambda: 10.0, id_factory=lambda: "job-1")
    job = supervisor.begin(kind="answer", lane="large-model", label="chat answer")
    supervisor.update(job.job_id, progress={"batch": 1}, checkpoint={"durable": True})
    assert supervisor.request_stop_by_kind("answer") == 1
    snapshot = supervisor.snapshots(include_done=False)[0]
    assert snapshot["status"] == "stop-requested"
    assert snapshot["progress"] == {"batch": 1}
    assert "job-1 answer large-model" in format_job_snapshots([snapshot])
    runtime = make_runtime_context(
        realm="work",
        identity="Motoko",
        app_version="0.1.0",
        revision="test",
        permissions="repo-review",
        paths=RuntimePaths(state_root=pathlib.Path("/state"), config_root=pathlib.Path("/config")),
        routes=[{"route": "chat", "model": "qwen", "endpoint": "unix:///run/motoko.sock", "max_parallel": 1}],
    ).content_free_dict()
    assert runtime["schema"] == "runtime-context-v1"
    assert runtime["routes"][0]["endpoint_kind"] == "unix"
    manager = ModelRouteManager(
        route_provider=lambda _name: {"route": "chat", "endpoint": "unix:///x", "model": "m"},
        status_provider=lambda _route: "socket=active\nproxy=active\nbackend=activating",
        verify_hint_provider=lambda _route: "verify",
        activating_detector=lambda text: "activating" in text,
    )
    readiness = manager.readiness("chat")
    assert readiness.activating
    assert readiness.content_free_dict()["has_verify_hint"]
    service = RetrievalService(
        load_index=lambda _id: {"id": "idx"},
        retrieve_index_query=lambda _index, _query: ("index text", [{"kind": "index"}]),
        render_index_overview=lambda _index: ("overview", [{"kind": "index"}]),
        load_topic=lambda _id: {},
        retrieve_topic=lambda _topic, _query: ("topic", []),
        load_dossier=lambda _id: {},
        retrieve_dossier=lambda _dossier, _query: ("dossier", []),
    )
    retrieval = service.render_attached_context([{"kind": "index", "id": "idx"}], "query")
    assert retrieval.text == "index text"
    assert retrieval.diagnostics["schema"] == "retrieval-service-v1"
    assert retrieval.diagnostics["source_count"] == 1
    decision = superseded_index_cleanup_decision(
        index_id="old",
        latest_id="new",
        stale=True,
        latest_has_missing_artifacts=False,
        bytes_estimate=12,
    ).to_dict()
    assert decision["action"] == "delete"
    assert source_lifecycle_state(path="/private/file", exists=False, ignored=False, fingerprint_changed=False)["status"] == "deleted"
    scrubbed = scrub_observability_row({"event": "status", "prompt": "private", "route": "chat"})
    assert scrubbed["prompt"] == "<redacted>"
    assert "prompt=<redacted>" in format_observability_report([scrubbed])
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

            ui.input_buffer = ""
            ui.cursor = 0
            ui.render(force=True)
            cleared_dropdown = read_available(master_fd)
            assert "checking pty dimensions" in cleared_dropdown

            old_tty = termios.tcgetattr(slave_fd)
            try:
                tty.setcbreak(slave_fd)
                os.write(master_fd, b"a")
                assert ui.handle_ready_input(0.1) is True
                assert ui.input_buffer == "a"
                assert ui.cursor == 1
            finally:
                termios.tcsetattr(slave_fd, termios.TCSADRAIN, old_tty)

            loop_ui = fake_tui(m, slave_fd)
            loop_ui.input_buffer = ""
            loop_ui.cursor = 0
            loop_ui.resume_maintenance_on_start = False
            loop_ui.pending_prompts = collections.deque()
            loop_ui.start_startup_discovery = lambda: None
            pressure_started = False
            input_before_background_events = []
            original_drain_events = loop_ui.drain_events

            def start_background_pressure():
                nonlocal pressure_started
                pressure_started = True
                with loop_ui.events_lock:
                    for idx in range(32):
                        loop_ui.events.append(("system_note", f"background event {idx}"))
                os.write(master_fd, b"z")

            def checked_drain_events():
                if pressure_started:
                    input_before_background_events.append(loop_ui.input_buffer)
                original_drain_events()
                if pressure_started:
                    loop_ui.running = False

            loop_ui.start_study_loop = start_background_pressure
            loop_ui.drain_events = checked_drain_events
            old_tty = termios.tcgetattr(slave_fd)
            try:
                tty.setcbreak(slave_fd)
                loop_ui.run_terminal_owner_loop()
            finally:
                termios.tcsetattr(slave_fd, termios.TCSADRAIN, old_tty)
            assert input_before_background_events
            assert input_before_background_events[0] == "z"
            assert loop_ui.ui_owner_thread_error is None
            read_available(master_fd)

            catalog_probe = catalog_latency_probe_on_pty(m, master_fd, slave_fd)
            assert catalog_probe["status"] == "pass", catalog_probe

            background_preempted = m.threading.Event()

            def preemptible_background(probe_ui):
                step_cancel_event = m.threading.Event()
                probe_ui.study_step_cancel_event = step_cancel_event
                if not step_cancel_event.wait(2.0):
                    raise RuntimeError("typed input did not preempt background work")
                background_preempted.set()

            preemption_probe = m.build_tui_catalog_latency_probe(
                master_fd,
                slave_fd,
                catalog_worker=preemptible_background,
                workload_label="input-preemption",
                stream_seconds=0.4,
                stream_interval=0.02,
            )
            assert preemption_probe["status"] == "pass", preemption_probe
            assert preemption_probe["catalog_worker_status"] == "completed"
            assert background_preempted.is_set()

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
    print("6 motoko tty render/input checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
