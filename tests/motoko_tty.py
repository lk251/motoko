#!/usr/bin/env python3
"""Pseudo-terminal checks for Motoko TUI rendering.

These tests stay stdlib-only but exercise the renderer through a real pty so
terminal-size handling is closer to a tty/tmux session than pure string tests.
"""

from __future__ import annotations

import collections
import contextlib
import fcntl
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import pty
import select
import subprocess
import struct
import sys
import termios
import tempfile
import threading
import time

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


class CountingMessageList(list):
    def __init__(self, rows=()):
        super().__init__(rows)
        self.iterations = 0

    def __iter__(self):
        self.iterations += len(self)
        return super().__iter__()


def latency_percentile_ms(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * (percentile / 100.0)))
    idx = max(0, min(len(ordered) - 1, idx))
    return round(ordered[idx] * 1000.0, 3)


def read_until_visible(fd: int, target: str, *, timeout: float = 2.0) -> str:
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        readable, _writeable, _errors = select.select([fd], [], [], 0.02)
        if not readable:
            continue
        try:
            chunks.append(os.read(fd, 65536))
        except OSError:
            break
        text = b"".join(chunks).decode("utf-8", errors="replace")
        if target in strip_ansi(text):
            return text
    return b"".join(chunks).decode("utf-8", errors="replace")


def wait_for_prefixes(
    fd: int,
    *,
    prefixes: list[str],
    injected_at: list[float],
    timeout: float = 3.0,
) -> tuple[list[float], str]:
    seen: dict[int, float] = {}
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and len(seen) < len(prefixes):
        readable, _writeable, _errors = select.select([fd], [], [], 0.02)
        if not readable:
            continue
        now_value = time.monotonic()
        try:
            chunks.append(os.read(fd, 65536))
        except OSError:
            break
        visible = strip_ansi(b"".join(chunks).decode("utf-8", errors="replace"))
        for idx, prefix in enumerate(prefixes):
            if idx not in seen and prefix in visible:
                seen[idx] = max(0.0, now_value - injected_at[idx])
    output = b"".join(chunks).decode("utf-8", errors="replace")
    latencies = [seen[idx] for idx in range(len(prefixes)) if idx in seen]
    return latencies, output


def write_json(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def build_background_study_fixture(
    m,
    tmp_root: pathlib.Path,
    *,
    file_count: int = 20,
    chunks_per_file: int = 2,
    headings_per_chunk: int = 10,
) -> dict:
    docs = tmp_root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    index_id = "20260621-000000-badfed"
    files = []
    for file_idx in range(file_count):
        chunks = []
        file_parts = []
        source = docs / f"background-{file_idx:04d}.org"
        for chunk_idx in range(chunks_per_file):
            lines = []
            for heading_idx in range(headings_per_chunk):
                ordinal = file_idx * chunks_per_file * headings_per_chunk + chunk_idx * headings_per_chunk + heading_idx
                lines.extend(
                    [
                        f"* [2026-06-{(ordinal % 28) + 1:02d} Mon 10:{ordinal % 60:02d}] Synthetic background day {ordinal}",
                        "** do",
                        f"*** TODO Preserve responsive typing during evidence build {ordinal} :latency:",
                        "** log",
                        (
                            "This deterministic fixture exists only to keep the real background "
                            "evidence-store code busy while the PTY verifier types into Motoko."
                        ),
                    ]
                )
            content = "\n".join(lines) + "\n"
            file_parts.append(content)
            chunks.append(
                {
                    "chunk": chunk_idx + 1,
                    "summary": f"Synthetic background evidence chunk {file_idx}-{chunk_idx}.",
                    "content": content,
                    "content_sha256": m.sha256_hex(content.encode("utf-8")),
                    "content_bytes": len(content.encode("utf-8")),
                }
            )
        source.write_text("".join(file_parts), encoding="utf-8")
        files.append(
            {
                "path": str(source),
                "source_fingerprint": m.source_fingerprint(source),
                "summary": "Synthetic background-study latency fixture.",
                "chunks": chunks,
            }
        )
    index = {
        "id": index_id,
        "name": "background-study-latency",
        "root": str(docs),
        "glob": "*.org",
        "created": m.now(),
        "files": files,
    }
    write_json(m.index_path(index_id), index)
    return index


def read_pty_until(
    fd: int,
    predicate,
    *,
    timeout: float,
) -> tuple[str, bool]:
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        readable, _writeable, _errors = select.select([fd], [], [], 0.02)
        if not readable:
            continue
        try:
            chunks.append(os.read(fd, 65536))
        except OSError:
            break
        text = b"".join(chunks).decode("utf-8", errors="replace")
        if predicate(strip_ansi(text)):
            return text, True
    return b"".join(chunks).decode("utf-8", errors="replace"), False


def observe_child_prompt_latency(
    fd: int,
    *,
    text: str,
    phase_end_markers: tuple[str, ...],
    timeout: float,
) -> dict:
    prefixes = [text[: idx + 1] for idx in range(len(text))]
    injected_at: list[float] = []
    seen: dict[int, float] = {}
    chunks: list[bytes] = []
    phase_end_seen_at: float | None = None
    first_prefix_at: float | None = None
    last_visible_change = time.monotonic()
    longest_stall = 0.0

    for char in text:
        injected_at.append(time.monotonic())
        os.write(fd, char.encode("utf-8"))

    deadline = time.monotonic() + timeout
    last_visible = ""
    while time.monotonic() < deadline and (len(seen) < len(prefixes) or phase_end_seen_at is None):
        readable, _writeable, _errors = select.select([fd], [], [], 0.02)
        now_value = time.monotonic()
        if not readable:
            longest_stall = max(longest_stall, now_value - last_visible_change)
            continue
        try:
            chunks.append(os.read(fd, 65536))
        except OSError:
            break
        visible = strip_ansi(b"".join(chunks).decode("utf-8", errors="replace"))
        if visible != last_visible:
            longest_stall = max(longest_stall, now_value - last_visible_change)
            last_visible_change = now_value
            last_visible = visible
        if phase_end_seen_at is None and any(marker in visible for marker in phase_end_markers):
            phase_end_seen_at = now_value
        for idx, prefix in enumerate(prefixes):
            if idx not in seen and prefix in visible:
                seen[idx] = max(0.0, now_value - injected_at[idx])
                if first_prefix_at is None:
                    first_prefix_at = now_value
    output = b"".join(chunks).decode("utf-8", errors="replace")
    latencies = [seen[idx] for idx in range(len(prefixes)) if idx in seen]
    return {
        "latencies": latencies,
        "output": output,
        "visible_text": strip_ansi(output),
        "phase_end_seen": phase_end_seen_at is not None,
        "visible_before_phase_end": (
            first_prefix_at is not None
            and (phase_end_seen_at is None or first_prefix_at <= phase_end_seen_at)
        ),
        "longest_stall_ms": round(longest_stall * 1000.0, 3),
    }


def wait_for_background_artifact(state_dir: pathlib.Path, fd: int, *, timeout: float = 5.0) -> tuple[bool, str]:
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if list((state_dir / "evidence-stores").glob("*.json")):
            return True, b"".join(chunks).decode("utf-8", errors="replace")
        readable, _writeable, _errors = select.select([fd], [], [], 0.05)
        if not readable:
            continue
        try:
            chunks.append(os.read(fd, 65536))
        except OSError:
            break
    return bool(list((state_dir / "evidence-stores").glob("*.json"))), b"".join(chunks).decode("utf-8", errors="replace")


def run_background_study_latency_probe(
    m,
    *,
    text: str,
    width: int = 140,
) -> dict:
    old_env = {
        "MOTOKO_STATE_HOME": os.environ.get("MOTOKO_STATE_HOME"),
        "MOTOKO_CONFIG_HOME": os.environ.get("MOTOKO_CONFIG_HOME"),
    }
    master_fd = slave_fd = None
    proc: subprocess.Popen | None = None
    errors: list[str] = []
    try:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = pathlib.Path(tmp_name)
            state_dir = tmp / "state"
            config_dir = tmp / "config"
            os.environ["MOTOKO_STATE_HOME"] = str(state_dir)
            os.environ["MOTOKO_CONFIG_HOME"] = str(config_dir)
            build_background_study_fixture(m, tmp)

            env = os.environ.copy()
            env.update(
                {
                    "MOTOKO_STATE_HOME": str(state_dir),
                    "MOTOKO_CONFIG_HOME": str(config_dir),
                    "MOTOKO_TUI": "1",
                    "TERM": "xterm-256color",
                    "MOTOKO_BACKGROUND_STUDY": "1",
                    "MOTOKO_BACKGROUND_STUDY_INTERVAL": "1",
                    "MOTOKO_BACKGROUND_STUDY_IDLE_GRACE": "1",
                    "MOTOKO_BACKGROUND_INDEX_ENRICH": "0",
                    "MOTOKO_BACKGROUND_HEAVY_INDEX": "0",
                    "MOTOKO_BACKGROUND_INDEX_CLEANUP": "0",
                    "MOTOKO_BACKGROUND_INDEX_REPAIR": "0",
                    "MOTOKO_BACKGROUND_VECTOR_REFRESH": "0",
                    "MOTOKO_BACKGROUND_PROFILE": "0",
                    "MOTOKO_BACKGROUND_EVIDENCE_REFRESH": "1",
                    "MOTOKO_BACKGROUND_EVIDENCE_REFRESH_LIMIT": "1",
                    "MOTOKO_TUI_INPUT_BATCH_LIMIT": "64",
                }
            )
            master_fd, slave_fd = pty.openpty()
            set_winsz(slave_fd, 24, width)
            proc = subprocess.Popen(
                [sys.executable, str(REPO_ROOT / "motoko"), "chat", "--title", "Background Study Latency"],
                cwd=str(tmp),
                env=env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
            )
            os.close(slave_fd)
            slave_fd = None

            initial, ready = read_pty_until(master_fd, lambda visible: "Background Study Latency" in visible, timeout=5.0)
            if not ready:
                errors.append("child TUI did not render initial conversation title")
            phase_output, phase_seen = read_pty_until(
                master_fd,
                lambda visible: "study: evidence-store" in visible,
                timeout=12.0,
            )
            cumulative_before_input = strip_ansi(initial + phase_output)
            phase_seen = phase_seen or "study: evidence-store" in cumulative_before_input
            if not phase_seen:
                errors.append("background study evidence-store phase was not observed")

            observed = observe_child_prompt_latency(
                master_fd,
                text=text,
                phase_end_markers=("study: idle", "evidence store(s) refreshed", "catalog fresh"),
                timeout=20.0,
            )
            completed, completion_output = wait_for_background_artifact(state_dir, master_fd, timeout=5.0)
            final_visible = strip_ansi(initial + phase_output + observed["output"] + completion_output)
            if len(observed["latencies"]) != len(text):
                errors.append(f"background latency samples missing: {len(observed['latencies'])}/{len(text)}")
            if text not in final_visible:
                errors.append("background composer final text was not observed")
            if not observed["visible_before_phase_end"]:
                errors.append("typed text was not visible before background phase ended")
            background_completed = completed
            if not background_completed:
                errors.append("background evidence store was not written")

            with contextlib.suppress(OSError):
                os.write(master_fd, b"\x03")
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.terminate()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=2.0)
            latencies = observed["latencies"]
            return {
                "phase": "study: evidence-store",
                "samples": len(latencies),
                "p50_ms": latency_percentile_ms(latencies, 50),
                "p95_ms": latency_percentile_ms(latencies, 95),
                "max_ms": round((max(latencies) if latencies else 0.0) * 1000.0, 3),
                "longest_stall_ms": observed["longest_stall_ms"],
                "visible_before_phase_end": observed["visible_before_phase_end"],
                "input_integrity": text in final_visible,
                "background_completed": background_completed,
                "errors": errors,
            }
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            with contextlib.suppress(Exception):
                proc.wait(timeout=2.0)
        for fd in (master_fd, slave_fd):
            if fd is not None:
                with contextlib.suppress(OSError):
                    os.close(fd)
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def make_latency_tui(
    m,
    slave_fd: int,
    *,
    title: str,
    transcript_pairs: int,
    initial_input: str = "",
    width: int = 80,
    during_streaming: bool = False,
):
    conv = m.new_conversation(title)
    ui = m.MotokoTui(conv)
    ui.stdin_fd = slave_fd
    ui.stdout_fd = slave_fd
    ui.start_study_loop = lambda: None
    ui.start_maintenance = lambda *args, **kwargs: None
    ui.resume_maintenance_on_start = False
    ui.pending_prompts = collections.deque()
    ui.report_running = 0
    ui.foreground_running = 0
    ui.maintaining = False
    ui.study_running = False
    ui.cwd_indexing = False
    ui.index_progress = None
    ui.status = "ready"
    ui.input_buffer = initial_input
    ui.cursor = len(initial_input)
    ui.dropdown_index = 0
    rows = []
    for idx in range(transcript_pairs):
        rows.append({"role": "user", "content": f"transcript user row {idx}"})
        rows.append({"role": "assistant", "content": f"transcript answer row {idx}"})
    if not rows:
        rows = [{"role": "system", "content": "empty transcript probe"}]
    ui.messages = CountingMessageList(rows)
    ui.rendered_message_ids = set()
    ui.bottom_rows_rendered = 0
    ui.bottom_cursor_row_offset = 0
    ui.bottom_frame_key = None
    ui.answer_stream_width = 0
    ui.answer_stream_emitted_lines = 0
    if during_streaming:
        ui.generating = True
        ui.answer_phase = "answering"
        ui.answer_started_monotonic = time.monotonic()
        ui.answer_phase_started_monotonic = ui.answer_started_monotonic
        ui.answer_reasoning = ""
        ui.answer_entry = {"role": "assistant", "content": "streamed answer line held stable"}
        ui.messages.append(ui.answer_entry)
    else:
        ui.generating = False
        ui.answer_phase = ""
        ui.answer_entry = None
    set_winsz(slave_fd, 18, width)
    return ui


def run_tui_latency_probe(
    m,
    *,
    name: str,
    text: str,
    width: int = 80,
    transcript_pairs: int = 2,
    initial_input: str = "",
    burst: bool = False,
    during_streaming: bool = False,
    input_batch_limit: int | None = None,
) -> dict:
    old_env = {
        "MOTOKO_STATE_HOME": os.environ.get("MOTOKO_STATE_HOME"),
        "MOTOKO_CONFIG_HOME": os.environ.get("MOTOKO_CONFIG_HOME"),
        "MOTOKO_BACKGROUND_STUDY": os.environ.get("MOTOKO_BACKGROUND_STUDY"),
        "MOTOKO_TUI_INPUT_BATCH_LIMIT": os.environ.get("MOTOKO_TUI_INPUT_BATCH_LIMIT"),
    }
    old_model_badge = m.model_badge
    old_assistant_color = m.assistant_color
    counters = collections.Counter()
    errors: list[str] = []
    master_fd = slave_fd = None
    ui = None
    thread = None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MOTOKO_STATE_HOME"] = str(pathlib.Path(tmp) / "state")
            os.environ["MOTOKO_CONFIG_HOME"] = str(pathlib.Path(tmp) / "config")
            os.environ["MOTOKO_BACKGROUND_STUDY"] = "0"
            if input_batch_limit is None:
                os.environ.pop("MOTOKO_TUI_INPUT_BATCH_LIMIT", None)
            else:
                os.environ["MOTOKO_TUI_INPUT_BATCH_LIMIT"] = str(input_batch_limit)

            def counted_model_badge():
                counters["model_badge_calls"] += 1
                return old_model_badge()

            def counted_assistant_color():
                counters["assistant_color_calls"] += 1
                return old_assistant_color()

            m.model_badge = counted_model_badge
            m.assistant_color = counted_assistant_color
            master_fd, slave_fd = pty.openpty()
            ui = make_latency_tui(
                m,
                slave_fd,
                title=f"Latency {name}",
                transcript_pairs=transcript_pairs,
                initial_input=initial_input,
                width=width,
                during_streaming=during_streaming,
            )
            original_write = ui.write
            original_render = ui.render
            original_draw = ui.draw_bottom_area

            def counted_write(payload: str) -> None:
                counters["writes"] += 1
                counters["write_bytes"] += len(payload.encode("utf-8", errors="replace"))
                original_write(payload)

            def counted_render(*args, **kwargs):
                counters["renders"] += 1
                return original_render(*args, **kwargs)

            def counted_draw(*args, **kwargs):
                counters["bottom_draw_calls"] += 1
                return original_draw(*args, **kwargs)

            ui.write = counted_write
            ui.render = counted_render
            ui.draw_bottom_area = counted_draw

            result: dict = {}

            def driver() -> None:
                initial_output = read_until_visible(master_fd, f"Latency {name}", timeout=2.0)
                initial_output += read_available(master_fd)
                if f"Latency {name}" not in strip_ansi(initial_output):
                    errors.append("initial render did not become visible")
                counters.clear()
                if isinstance(ui.messages, CountingMessageList):
                    ui.messages.iterations = 0

                injected_at: list[float] = []
                prefixes: list[str] = []
                observed_latencies: list[float] = []
                observed_output = ""
                for idx, char in enumerate(text):
                    injected_at.append(time.monotonic())
                    os.write(master_fd, char.encode("utf-8"))
                    prefixes.append(initial_input + text[: idx + 1])
                    if not burst:
                        current_latencies, current_output = wait_for_prefixes(
                            master_fd,
                            prefixes=[prefixes[-1]],
                            injected_at=[injected_at[-1]],
                        )
                        observed_latencies.extend(current_latencies)
                        observed_output += current_output
                if burst:
                    observed_latencies, observed_output = wait_for_prefixes(
                        master_fd,
                        prefixes=prefixes,
                        injected_at=injected_at,
                    )
                observed_output += read_available(master_fd)
                final_expected = initial_input + text
                final_input = getattr(ui, "input_buffer", "")
                if final_input != final_expected:
                    errors.append(f"input mismatch: expected {final_expected!r}, got {final_input!r}")
                if len(observed_latencies) != len(text):
                    errors.append(f"latency samples missing: {len(observed_latencies)}/{len(text)}")
                transcript_iterations = ui.messages.iterations if isinstance(ui.messages, CountingMessageList) else 0
                char_count = max(1, len(text))
                result.update(
                    {
                        "name": name,
                        "text": text,
                        "final_input": final_input,
                        "expected_input": final_expected,
                        "p50_ms": latency_percentile_ms(observed_latencies, 50),
                        "p95_ms": latency_percentile_ms(observed_latencies, 95),
                        "max_ms": round((max(observed_latencies) if observed_latencies else 0.0) * 1000.0, 3),
                        "samples": len(observed_latencies),
                        "writes": counters["writes"],
                        "write_bytes": counters["write_bytes"],
                        "renders": counters["renders"],
                        "bottom_draw_calls": counters["bottom_draw_calls"],
                        "model_badge_calls": counters["model_badge_calls"],
                        "assistant_color_calls": counters["assistant_color_calls"],
                        "writes_per_char": round(counters["writes"] / char_count, 3),
                        "bytes_per_char": round(counters["write_bytes"] / char_count, 3),
                        "renders_per_char": round(counters["renders"] / char_count, 3),
                        "transcript_iterations": transcript_iterations,
                        "output_contains_final": final_expected in strip_ansi(observed_output),
                        "errors": errors,
                    }
                )
                ui.running = False
                with contextlib.suppress(OSError):
                    os.write(master_fd, b"\x00")

            thread = threading.Thread(target=driver, daemon=True)
            thread.start()
            try:
                ui.run()
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                ui.running = False
            thread.join(timeout=2.0)
            if not result:
                result.update(
                    {
                        "name": name,
                        "text": text,
                        "final_input": getattr(ui, "input_buffer", ""),
                        "expected_input": initial_input + text,
                        "p50_ms": 0.0,
                        "p95_ms": 0.0,
                        "max_ms": 0.0,
                        "samples": 0,
                        "writes": counters["writes"],
                        "write_bytes": counters["write_bytes"],
                        "renders": counters["renders"],
                        "bottom_draw_calls": counters["bottom_draw_calls"],
                        "model_badge_calls": counters["model_badge_calls"],
                        "assistant_color_calls": counters["assistant_color_calls"],
                        "writes_per_char": 0.0,
                        "bytes_per_char": 0.0,
                        "renders_per_char": 0.0,
                        "transcript_iterations": 0,
                        "output_contains_final": False,
                        "errors": errors + ["driver did not finish"],
                    }
                )
            return result
    finally:
        m.model_badge = old_model_badge
        m.assistant_color = old_assistant_color
        if ui is not None:
            ui.running = False
        if master_fd is not None:
            with contextlib.suppress(OSError):
                os.write(master_fd, b"\x00")
        if thread is not None:
            thread.join(timeout=2.0)
        for fd in (master_fd, slave_fd):
            if fd is not None:
                with contextlib.suppress(OSError):
                    os.close(fd)
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_tui_editing_probe(m) -> dict:
    old_state = os.environ.get("MOTOKO_STATE_HOME")
    old_config = os.environ.get("MOTOKO_CONFIG_HOME")
    master_fd = slave_fd = None
    ui = None
    thread = None
    errors: list[str] = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MOTOKO_STATE_HOME"] = str(pathlib.Path(tmp) / "state")
            os.environ["MOTOKO_CONFIG_HOME"] = str(pathlib.Path(tmp) / "config")
            master_fd, slave_fd = pty.openpty()
            ui = make_latency_tui(m, slave_fd, title="Edit Probe", transcript_pairs=1, width=60)
            ui.start_study_loop = lambda: None
            ui.history = ["prior prompt"]
            result: dict = {}

            def driver() -> None:
                read_until_visible(master_fd, "Edit Probe", timeout=2.0)
                read_available(master_fd)
                sequence = b"abc\x1b[D\x1b[D\x1b[3~Z\x05!\x01^\x0b"
                os.write(master_fd, sequence)
                read_until_visible(master_fd, "^", timeout=2.0)
                read_available(master_fd)
                if ui.input_buffer != "^":
                    errors.append(f"editing expected '^', got {ui.input_buffer!r}")
                os.write(master_fd, b"\x15\x1b[A")
                read_until_visible(master_fd, "prior prompt", timeout=2.0)
                read_available(master_fd)
                if ui.input_buffer != "prior prompt":
                    errors.append(f"history expected 'prior prompt', got {ui.input_buffer!r}")
                result.update({"name": "editing", "final_input": ui.input_buffer, "errors": errors})
                ui.running = False
                with contextlib.suppress(OSError):
                    os.write(master_fd, b"\x00")

            thread = threading.Thread(target=driver, daemon=True)
            thread.start()
            try:
                ui.run()
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                ui.running = False
            thread.join(timeout=2.0)
            return result or {"name": "editing", "final_input": getattr(ui, "input_buffer", ""), "errors": errors}
    finally:
        if ui is not None:
            ui.running = False
        if master_fd is not None:
            with contextlib.suppress(OSError):
                os.write(master_fd, b"\x00")
        if thread is not None:
            thread.join(timeout=2.0)
        for fd in (master_fd, slave_fd):
            if fd is not None:
                with contextlib.suppress(OSError):
                    os.close(fd)
        if old_state is None:
            os.environ.pop("MOTOKO_STATE_HOME", None)
        else:
            os.environ["MOTOKO_STATE_HOME"] = old_state
        if old_config is None:
            os.environ.pop("MOTOKO_CONFIG_HOME", None)
        else:
            os.environ["MOTOKO_CONFIG_HOME"] = old_config


def run_tui_latency_suite(m) -> dict:
    scenarios = {
        "short": run_tui_latency_probe(
            m,
            name="short",
            text="latency",
            transcript_pairs=2,
        ),
        "long": run_tui_latency_probe(
            m,
            name="long",
            text="latency",
            transcript_pairs=700,
        ),
        "wrapped": run_tui_latency_probe(
            m,
            name="wrapped",
            text="abcdefghijklmnopqrstuvwxyz0123456789",
            width=24,
            transcript_pairs=2,
        ),
        "slash": run_tui_latency_probe(
            m,
            name="slash",
            text="status",
            initial_input="/",
            transcript_pairs=2,
        ),
        "burst": run_tui_latency_probe(
            m,
            name="burst",
            text="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            transcript_pairs=2,
            burst=True,
        ),
        "unicode": run_tui_latency_probe(
            m,
            name="unicode",
            text="cafe-界-🙂",
            transcript_pairs=2,
            burst=True,
        ),
        "streaming": run_tui_latency_probe(
            m,
            name="streaming",
            text="queued while streaming",
            transcript_pairs=2,
            during_streaming=True,
            burst=True,
        ),
        "regression_single_key_batch": run_tui_latency_probe(
            m,
            name="regression",
            text="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            transcript_pairs=700,
            burst=True,
            input_batch_limit=1,
        ),
        "editing": run_tui_editing_probe(m),
    }
    return {"schema": "motoko-tui-latency-v1", "scenarios": scenarios}


def assert_tui_latency_report(report: dict) -> None:
    scenarios = report["scenarios"]
    for name, scenario in scenarios.items():
        assert not scenario.get("errors"), f"{name}: {scenario.get('errors')}"
    for name in ("short", "long", "wrapped", "slash", "burst", "unicode", "streaming"):
        assert scenarios[name]["samples"] == len(scenarios[name]["text"])
        assert scenarios[name]["output_contains_final"]
        assert scenarios[name]["p95_ms"] <= 250.0, (name, scenarios[name])
    assert scenarios["long"]["transcript_iterations"] == 0, scenarios["long"]
    assert scenarios["burst"]["renders_per_char"] <= 0.35, scenarios["burst"]
    assert scenarios["burst"]["writes_per_char"] <= 0.35, scenarios["burst"]
    regression = scenarios["regression_single_key_batch"]
    assert regression["renders_per_char"] >= 0.75, regression
    assert regression["renders_per_char"] > scenarios["burst"]["renders_per_char"] * 2.0
    assert regression["transcript_iterations"] == 0, regression


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
        realm="mares",
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
    latency_report = run_tui_latency_suite(m)
    if os.environ.get("MOTOKO_TUI_LATENCY_REPORT"):
        print(json.dumps(latency_report, indent=2, sort_keys=True))
    else:
        assert_tui_latency_report(latency_report)
    print("4 motoko tty render/input checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
