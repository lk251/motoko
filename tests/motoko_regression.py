#!/usr/bin/env python3
"""Stdlib-only Motoko regression tests."""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import socketserver
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


SOURCE = pathlib.Path(os.environ.get("MOTOKO_SOURCE", "motoko"))


def load_motoko():
    loader = importlib.machinery.SourceFileLoader("motoko", str(SOURCE))
    spec = importlib.util.spec_from_loader("motoko", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@contextlib.contextmanager
def isolated_state():
    old_state = os.environ.get("MOTOKO_STATE_HOME")
    old_config = os.environ.get("MOTOKO_CONFIG_HOME")
    old_alias_color = os.environ.get("MOTOKO_ALIAS_COLOR")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["MOTOKO_STATE_HOME"] = str(pathlib.Path(tmp) / "state")
        os.environ["MOTOKO_CONFIG_HOME"] = str(pathlib.Path(tmp) / "config")
        os.environ.pop("MOTOKO_ALIAS_COLOR", None)
        try:
            yield pathlib.Path(tmp)
        finally:
            if old_state is None:
                os.environ.pop("MOTOKO_STATE_HOME", None)
            else:
                os.environ["MOTOKO_STATE_HOME"] = old_state
            if old_config is None:
                os.environ.pop("MOTOKO_CONFIG_HOME", None)
            else:
                os.environ["MOTOKO_CONFIG_HOME"] = old_config
            if old_alias_color is None:
                os.environ.pop("MOTOKO_ALIAS_COLOR", None)
            else:
                os.environ["MOTOKO_ALIAS_COLOR"] = old_alias_color


def write_conversation(m, conv):
    m.atomic_write(m.conversation_path(conv["id"]), json.dumps(conv, ensure_ascii=False) + "\n")


def test_recent_conversation_lanes(m):
    with isolated_state():
        current = m.new_conversation("Current")
        current["id"] = "current"
        current["updated"] = "2026-05-17T10:00:00+00:00"
        current["messages"] = [{"role": "user", "content": "What did I say about violet harbor?"}]
        write_conversation(m, current)

        recent = m.new_conversation("Recent unrelated")
        recent["id"] = "recent"
        recent["updated"] = "2026-05-17T09:59:00+00:00"
        recent["messages"] = [{"role": "user", "content": "I bought coffee."}]
        write_conversation(m, recent)

        relevant = m.new_conversation("Older relevant")
        relevant["id"] = "relevant"
        relevant["updated"] = "2026-05-17T08:00:00+00:00"
        relevant["messages"] = [{"role": "user", "content": "The codename is violet harbor."}]
        write_conversation(m, relevant)

        selected = m.ranked_recent_conversations(current, "violet harbor")
        by_id = {row["id"]: row for row in selected}
        assert "recent" in by_id
        assert "recent" in by_id["recent"]["_selection_reasons"]
        assert "relevant" in by_id
        assert "relevant" in by_id["relevant"]["_selection_reasons"]

        text, sources = m.render_recent_conversations_with_sources(current, "violet harbor")
        assert "violet harbor" in text
        assert any("relevant" in source.get("selection", []) for source in sources)


def test_maintenance_state_and_phases(m):
    with isolated_state():
        conv = m.new_conversation("Maintenance")
        conv["id"] = "maint"
        conv["messages"] = [
            {"role": "user", "content": "I prefer concise terminal output."},
            {"role": "assistant", "content": "Understood."},
            {"role": "user", "content": "I use Motoko for private memory."},
            {"role": "assistant", "content": "I will keep that in mind."},
        ]
        write_conversation(m, conv)

        old_propose = m.propose_memories_bounded
        try:
            m.propose_memories_bounded = lambda _conv, timeout=m.MODEL_TIMEOUT_SECONDS: [
                "Javier prefers concise terminal output."
            ]
            state = m.begin_maintenance_state(conv)
            phases = []
            notes = m.auto_maintain_conversation(conv, phase_callback=phases.append, state=state)
            assert "memory: checking" in phases
            assert "memory: proposing" in phases
            assert "memory: saving" in phases
            assert phases[-1] == "memory: done"
            assert notes == ["saved 1 durable memory"]
            assert m.read_maintenance_state()["phase"] == "memory: done"
            m.clear_maintenance_state(state["job_id"])
            assert m.read_maintenance_state() is None
        finally:
            m.propose_memories_bounded = old_propose


def test_memory_proposal_sends_transcript_not_assistant_prefill(m):
    with isolated_state():
        conv = m.new_conversation("Memory proposal")
        conv["id"] = "memory-prefill"
        conv["messages"] = [
            {"role": "user", "content": "I prefer concise terminal output."},
            {"role": "assistant", "content": "Understood."},
            {"role": "user", "content": "Motoko should preserve privacy boundaries."},
            {"role": "assistant", "content": "I will keep that in mind."},
        ]

        calls = []
        old_call_model = m.call_model
        try:
            def fake_call_model(messages, **kwargs):
                calls.append((messages, kwargs))
                return "MEMORY: Javier prefers concise terminal output."

            m.call_model = fake_call_model
            proposals = m.propose_memories(conv)
        finally:
            m.call_model = old_call_model

        assert proposals == ["Javier prefers concise terminal output."]
        messages, kwargs = calls[0]
        assert [item["role"] for item in messages] == ["system", "user"]
        assert "Conversation transcript:" in messages[-1]["content"]
        assert "assistant: I will keep that in mind." in messages[-1]["content"]
        assert messages[-1]["role"] != "assistant"
        assert kwargs["route"] == m.MODEL_ROUTE_MEMORY


def test_interrupted_maintenance_resume(m):
    with isolated_state():
        conv = m.new_conversation("Resume")
        conv["id"] = "resume"
        write_conversation(m, conv)
        state = m.begin_maintenance_state(conv)
        update = dict(state)
        update["retry_count"] = 0
        m.write_maintenance_state(update)
        should_resume, note = m.resume_interrupted_maintenance(conv)
        assert should_resume
        assert "resuming" in note
        assert m.read_maintenance_state()["retry_count"] == 1


def test_other_conversation_maintenance_is_quietly_abandoned(m):
    with isolated_state():
        conv = m.new_conversation("Current")
        conv["id"] = "current"
        other = m.new_conversation("Other")
        other["id"] = "other"
        state = m.begin_maintenance_state(other)
        m.write_maintenance_state(state)

        should_resume, note = m.resume_interrupted_maintenance(conv)
        assert not should_resume
        assert note is None
        abandoned = m.read_maintenance_state()
        assert abandoned["status"] == "abandoned"
        assert abandoned["conversation_id"] == "other"
        assert abandoned["abandoned_reason"] == "opened different conversation"


def test_profile_dossier(m):
    with isolated_state():
        conv = m.new_conversation("Profile source")
        conv["id"] = "profile-conv"
        conv["messages"] = [{"role": "user", "content": "I care about craftsmanship."}]
        write_conversation(m, conv)
        m.add_memory("Javier values craftsmanship.", source="test", conversation_id=conv["id"])

        old_quiet = m.quiet_model
        try:
            m.quiet_model = lambda *args, **kwargs: "Stable preferences\n- Javier values craftsmanship."
            profile = m.refresh_profile_dossier()
            assert "craftsmanship" in profile["text"]
            text, sources = m.render_profile_with_sources()
            assert "craftsmanship" in text
            assert sources[0]["kind"] == "profile"
        finally:
            m.quiet_model = old_quiet


def test_memory_dossier(m):
    with isolated_state():
        conv = m.new_conversation("Dossier source")
        conv["id"] = "dossier-conv"
        conv["messages"] = [{"role": "user", "content": "I want careful craftsmanship in Motoko."}]
        write_conversation(m, conv)
        m.add_memory("Javier values careful craftsmanship.", source="test", conversation_id=conv["id"])

        old_summarize = m.summarize_blocks
        try:
            m.summarize_blocks = lambda _label, blocks, _instruction, **_kwargs: "Dossier summary\n" + "\n".join(blocks)[:200]
            dossier = m.build_memory_dossier("craftsmanship")
            assert dossier["source_memory_count"] >= 1
            assert dossier["source_conversation_count"] >= 1
            assert "craftsmanship" in dossier["summary"]
            item = m.context_item_from_dossier(dossier)
            text, sources = m.render_context_with_sources([item], "craftsmanship")
            assert "Memory dossier" in text
            assert any(source.get("kind") == "dossier" for source in sources)
        finally:
            m.summarize_blocks = old_summarize


def test_spinner_and_input_wrapping(m):
    old_term = os.environ.get("TERM")
    old_spinner = os.environ.get("MOTOKO_SPINNER")
    try:
        os.environ["TERM"] = "xterm-256color"
        os.environ.pop("MOTOKO_SPINNER", None)
        assert m.spinner_frames() == []
        os.environ["MOTOKO_SPINNER"] = "auto"
        assert m.spinner_frames() == ["/", "|", "\\", "-"]
        os.environ["MOTOKO_SPINNER"] = "braille"
        assert m.spinner_frames()[0] == "⠋"
    finally:
        if old_term is None:
            os.environ.pop("TERM", None)
        else:
            os.environ["TERM"] = old_term
        if old_spinner is None:
            os.environ.pop("MOTOKO_SPINNER", None)
        else:
            os.environ["MOTOKO_SPINNER"] = old_spinner

    rows, row_offset, col = m.fixed_prompt_input_display("abcdefghij", 10, 12)
    assert [m.strip_ansi(row) for row in rows] == ["> abcdefghij", "  "]
    assert row_offset == 1
    assert col == 3

    rows, row_offset, col = m.fixed_prompt_input_display("abcdefghijklmnopqrstuvwxyz", 5, 12)
    assert [m.strip_ansi(row) for row in rows] == [
        "> abcdefghij",
        "  klmnopqrst",
        "  uvwxyz",
    ]
    assert row_offset == 0
    assert col == 8

    rows, row_offset, col = m.fixed_prompt_input_display("ab界cdefghi", 3, 12)
    assert [m.strip_ansi(row) for row in rows] == ["> ab界cdefgh", "  i"]
    assert row_offset == 0
    assert col == 7

    rows, row_offset, col = m.fixed_prompt_input_display("alpha beta gamma", 16, 14)
    assert [m.strip_ansi(row).rstrip() for row in rows] == ["> alpha beta", "  gamma"]
    assert row_offset == 1
    assert col == 8


def test_phase_timer_key_ignores_progress_counters(m):
    left = "bg-heavy: vectorizing(model) orgfiles batch 29/129 parallel 32 rows 2700/10525 eta 1m50s"
    right = "bg-heavy: vectorizing(model) orgfiles batch 30/129 parallel 32 rows 2780/10525 eta 1m45s"
    assert m.phase_timer_key(left) == m.phase_timer_key(right)
    assert m.phase_timer_key(left) == "bg-heavy: vectorizing(model) orgfiles"
    assert m.phase_timer_key("study: planning") != m.phase_timer_key(left)


def test_generated_title(m):
    with isolated_state():
        conv = m.new_conversation()
        conv["id"] = "title-test"
        conv["messages"] = [
            {"role": "user", "content": "I want Motoko to improve her memory UI."},
            {"role": "assistant", "content": "We can refine the terminal interface."},
            {"role": "user", "content": "Please focus on dossiers and better titles."},
            {"role": "assistant", "content": "I will add a generated title pass."},
        ]
        write_conversation(m, conv)
        old_quiet = m.quiet_model
        try:
            m.quiet_model = lambda *args, **kwargs: 'Title: "Motoko memory title craft."'
            title = m.maybe_generate_conversation_title(conv, timeout=1)
            assert title == "Motoko memory title craft"
            assert conv["title"] == "Motoko memory title craft"
            assert conv["title_kind"] == "model"
            assert conv.get("title_generated")
        finally:
            m.quiet_model = old_quiet

        manual = m.new_conversation("Manual title")
        manual["messages"] = conv["messages"]
        assert not m.should_generate_conversation_title(manual)


def test_dropdown_scrolls_without_header(m):
    ui = object.__new__(m.MotokoTui)
    ui.dropdown_index = 9
    options = [
        {"label": f"/cmd-{idx}", "description": f"description {idx}", "value": f"/cmd-{idx}"}
        for idx in range(12)
    ]
    rows = [m.strip_ansi(row) for row in ui.dropdown_display(80, options)]
    assert len(rows) == 8
    assert not any("Suggestions" in row for row in rows)
    assert any("> /cmd-9" in row for row in rows)
    assert not any("/cmd-0" in row for row in rows)


def test_wall_timeout(m):
    start = time.monotonic()
    try:
        m.run_with_wall_timeout("slow task", 0.02, lambda: time.sleep(0.2))
    except TimeoutError as exc:
        assert "slow task timed out" in str(exc)
    else:
        raise AssertionError("slow task did not time out")
    assert time.monotonic() - start < 0.2


def test_help_about_and_explicit_memory(m):
    with isolated_state():
        help_text = m.format_help()
        assert "Session:" in help_text
        assert "Memory:" in help_text
        assert "Enter or Esc" in help_text
        about = m.format_about()
        assert "Motoko" in about
        assert "model badge:" in about
        assert "values: intelligence, competence, craft" in about
        assert "$$$$$_" in about
        assert about.index("$$$$$_") < about.index("version:")
        assert "Model routes:" not in about
        assert "assistant color:" not in about
        assert "spinner:" not in about
        assert m.explicit_memory_candidates("Please remember that I prefer small terminal UIs.") == [
            "I prefer small terminal UIs."
        ]
        conv = m.new_conversation("Memory request")
        saved = m.save_explicit_user_memories(
            "remember: I like Motoko to be careful with memories.",
            conv["id"],
        )
        assert saved == 1
        assert "careful with memories" in m.read_memory_rows()[0]["text"]


def test_help_overlay_closes(m):
    ui = object.__new__(m.MotokoTui)
    ui.dirty = False
    ui.open_overlay("help", "Motoko help\n\nSession:")
    assert ui.overlay_lines is not None
    ui.handle_key("q")
    assert ui.overlay_lines is None
    assert ui.dirty
    ui.open_overlay("about", "Motoko\n\nversion: 0.1.0")
    ui.handle_key("\n")
    assert ui.overlay_lines is None


def test_tui_about_opens_overlay(m):
    with isolated_state():
        conv = m.new_conversation("About overlay")
        ui = object.__new__(m.MotokoTui)
        ui.conv = conv
        ui.messages = []
        ui.scroll = 0
        ui.dirty = False
        ui.status = "ready"
        ui.generating = False
        ui.maintaining = False
        ui.report_running = 0
        ui.report_status = ""
        ui.report_token = 0
        ui.active_report_token = 0
        ui.events = m.collections.deque()
        ui.events_lock = threading.Lock()

        ui.handle_command("/about")
        deadline = time.monotonic() + 2
        while ui.report_running and time.monotonic() < deadline:
            ui.drain_events()
            time.sleep(0.01)
        ui.drain_events()

        assert ui.overlay_title == "/about"
        assert any("Motoko" in line for line in ui.overlay_lines or [])
        assert any("values: intelligence, competence, craft" in line for line in ui.overlay_lines or [])
        assert ui.messages == []


def test_tui_overlay_highlights_report_labels(m):
    class FakeTty:
        def isatty(self):
            return True

    old_stdout = m.sys.stdout
    old_real_stdout = m.sys.__stdout__
    old_term = os.environ.get("TERM")
    old_no_color = os.environ.get("NO_COLOR")
    try:
        os.environ["TERM"] = "xterm-256color"
        os.environ.pop("NO_COLOR", None)
        m.sys.stdout = m.io.StringIO()
        m.sys.__stdout__ = FakeTty()
        ui = object.__new__(m.MotokoTui)
        ui.open_overlay("status", "identity: Motoko\nBackground lanes:\n  /status  show status")
        rows = ui.overlay_display(80)
        assert any("\033[" in row and "identity:" in row for row in rows)
        assert any("\033[" in row and "Background lanes:" in row for row in rows)
        assert any("\033[" in row and "/status" in row for row in rows)
    finally:
        m.sys.stdout = old_stdout
        m.sys.__stdout__ = old_real_stdout
        if old_term is None:
            os.environ.pop("TERM", None)
        else:
            os.environ["TERM"] = old_term
        if old_no_color is None:
            os.environ.pop("NO_COLOR", None)
        else:
            os.environ["NO_COLOR"] = old_no_color


class FakeHandler(BaseHTTPRequestHandler):
    payloads = []

    def do_POST(self):  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            self.__class__.payloads.append(json.loads(body.decode("utf-8")))
        except json.JSONDecodeError:
            self.__class__.payloads.append({})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for token in ("hel", "lo"):
            event = {"choices": [{"delta": {"content": token}}]}
            self.wfile.write(f"data: {json.dumps(event)}\n\n".encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *_args):
        return


class LoadingThenOkHandler(BaseHTTPRequestHandler):
    calls = 0

    def do_POST(self):  # noqa: N802 - stdlib handler API
        self.__class__.calls += 1
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        if self.__class__.calls == 1:
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"Loading model","type":"unavailable_error","code":503}}')
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        event = {"choices": [{"delta": {"content": "OK"}}]}
        self.wfile.write(f"data: {json.dumps(event)}\n\n".encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *_args):
        return


class ResetThenOkHandler(BaseHTTPRequestHandler):
    calls = 0

    def do_POST(self):  # noqa: N802 - stdlib handler API
        self.__class__.calls += 1
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        if self.__class__.calls == 1:
            self.connection.close()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        event = {"choices": [{"delta": {"content": "OK"}}]}
        self.wfile.write(f"data: {json.dumps(event)}\n\n".encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *_args):
        return


class EmbeddingHandler(BaseHTTPRequestHandler):
    payloads = []
    paths = []

    def do_POST(self):  # noqa: N802 - stdlib handler API
        self.__class__.paths.append(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {}
        self.__class__.payloads.append(payload)
        inputs = payload.get("input", [])
        if isinstance(inputs, str):
            inputs = [inputs]
        data = []
        for idx, text in enumerate(inputs):
            text = str(text).lower()
            vector = [
                1.0 if "vector" in text else 0.0,
                1.0 if "deadline" in text else 0.0,
                1.0 if "task" in text else 0.0,
                0.25,
            ]
            data.append({"object": "embedding", "index": idx, "embedding": vector})
        response = {"object": "list", "data": data, "model": payload.get("model", "embedding-test")}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, *_args):
        return


class SlowEmbeddingHandler(BaseHTTPRequestHandler):
    payloads = []
    paths = []
    active = 0
    max_active = 0
    lock = threading.Lock()

    def do_POST(self):  # noqa: N802 - stdlib handler API
        self.__class__.paths.append(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {}
        self.__class__.payloads.append(payload)
        with self.__class__.lock:
            self.__class__.active += 1
            self.__class__.max_active = max(self.__class__.max_active, self.__class__.active)
        try:
            time.sleep(0.05)
            inputs = payload.get("input", [])
            if isinstance(inputs, str):
                inputs = [inputs]
            data = []
            for idx, text in enumerate(inputs):
                text = str(text).lower()
                vector = [
                    1.0 if "alpha" in text else 0.0,
                    1.0 if "beta" in text else 0.0,
                    1.0 if "gamma" in text else 0.0,
                    0.25,
                ]
                data.append({"object": "embedding", "index": idx, "embedding": vector})
            response = {"object": "list", "data": data, "model": payload.get("model", "embedding-test")}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
        finally:
            with self.__class__.lock:
                self.__class__.active -= 1

    def log_message(self, *_args):
        return


class ThrottledEmbeddingHandler(BaseHTTPRequestHandler):
    payloads = []
    paths = []
    active = 0
    failures = 0
    max_active = 0
    max_supported = 2
    lock = threading.Lock()

    def do_POST(self):  # noqa: N802 - stdlib handler API
        self.__class__.paths.append(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {}
        self.__class__.payloads.append(payload)
        with self.__class__.lock:
            self.__class__.active += 1
            active = self.__class__.active
            self.__class__.max_active = max(self.__class__.max_active, active)
        try:
            time.sleep(0.05)
            if active > self.__class__.max_supported:
                with self.__class__.lock:
                    self.__class__.failures += 1
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":{"message":"too much parallelism"}}')
                return
            inputs = payload.get("input", [])
            if isinstance(inputs, str):
                inputs = [inputs]
            data = []
            for idx, text in enumerate(inputs):
                text = str(text).lower()
                vector = [
                    1.0 if "vector" in text else 0.0,
                    1.0 if "task" in text else 0.0,
                    1.0 if "fallback" in text else 0.0,
                    0.25,
                ]
                data.append({"object": "embedding", "index": idx, "embedding": vector})
            response = {"object": "list", "data": data, "model": payload.get("model", "embedding-test")}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
        finally:
            with self.__class__.lock:
                self.__class__.active -= 1

    def log_message(self, *_args):
        return


class RerankHandler(BaseHTTPRequestHandler):
    payloads = []
    paths = []

    def do_POST(self):  # noqa: N802 - stdlib handler API
        self.__class__.paths.append(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {}
        self.__class__.payloads.append(payload)
        documents = payload.get("documents", [])
        if not isinstance(documents, list):
            documents = []
        results = []
        for idx, document in enumerate(documents):
            text = str(document).lower()
            score = 0.95 if "deadline" in text and "priority" in text else 0.15
            results.append({"index": idx, "relevance_score": score})
        response = {"object": "list", "results": results, "model": payload.get("model", "rerank-test")}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, *_args):
        return


class UnixHTTPServer(socketserver.UnixStreamServer):
    allow_reuse_address = True


def test_fake_openai_stream(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    FakeHandler.payloads = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        os.environ["MOTOKO_ENDPOINT"] = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
        tokens = []
        text = m.call_model_with_callback(
            [{"role": "user", "content": "hello"}],
            on_token=tokens.append,
            timeout=2,
        )
        assert text == "hello"
        assert tokens == ["hel", "lo"]
        buf = m.io.StringIO()
        with contextlib.redirect_stdout(buf):
            quiet = m.quiet_model([{"role": "user", "content": "hello"}], timeout=2)
        assert quiet == "hello"
        assert buf.getvalue() == ""
        assert FakeHandler.payloads[-1]["model"] == m.model_name()
    finally:
        server.shutdown()
        server.server_close()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint


def test_unix_socket_model_loading_retries(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    old_retry = m.MODEL_LOADING_RETRY_SECONDS
    socket_path = None
    LoadingThenOkHandler.calls = 0
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        m.MODEL_LOADING_RETRY_SECONDS = 0.01
        with isolated_state() as tmp:
            socket_path = tmp / "chat.sock"
            server = UnixHTTPServer(str(socket_path), LoadingThenOkHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "chat": {
                        "endpoint": f"unix://{socket_path}",
                        "model": "qwen-loading-test",
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            assert m.quiet_model([{"role": "user", "content": "hello"}], timeout=2) == "OK"
            assert LoadingThenOkHandler.calls == 2
            server.shutdown()
            server.server_close()
    finally:
        m.MODEL_LOADING_RETRY_SECONDS = old_retry
        if socket_path is not None:
            with contextlib.suppress(OSError):
                pathlib.Path(socket_path).unlink()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model


def assert_unix_socket_connection_reset_retries(m, status_text):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    old_retry = m.MODEL_LOADING_RETRY_SECONDS
    socket_path = None
    ResetThenOkHandler.calls = 0
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        m.MODEL_LOADING_RETRY_SECONDS = 0.01
        with isolated_state() as tmp:
            socket_path = tmp / "chat-reset.sock"
            server = UnixHTTPServer(str(socket_path), ResetThenOkHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "chat": {
                        "endpoint": f"unix://{socket_path}",
                        "model": "qwen-reset-test",
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            old_status = m.local_model_status_text
            try:
                m.local_model_status_text = lambda _route_info: status_text
                assert m.quiet_model([{"role": "user", "content": "hello"}], timeout=2) == "OK"
            finally:
                m.local_model_status_text = old_status
            assert ResetThenOkHandler.calls == 2
            server.shutdown()
            server.server_close()
    finally:
        m.MODEL_LOADING_RETRY_SECONDS = old_retry
        if socket_path is not None:
            with contextlib.suppress(OSError):
                pathlib.Path(socket_path).unlink()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model


def test_unix_socket_connection_reset_retries_while_activating(m):
    assert_unix_socket_connection_reset_retries(m, "realm=mares\nroute=chat\nbackend=activating\n")


def test_unix_socket_connection_reset_retries_while_active(m):
    assert_unix_socket_connection_reset_retries(m, "realm=mares\nroute=chat\nbackend=active\n")


def test_model_route_config_and_summary_cache(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_cache = os.environ.get("MOTOKO_MODEL_CACHE")
    FakeHandler.payloads = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        os.environ["MOTOKO_ENDPOINT"] = "http://127.0.0.1:9/v1/chat/completions"
        os.environ.pop("MOTOKO_MODEL_CACHE", None)
        with isolated_state():
            config = m.load_config()
            config["model_routes"]["index_chunk"] = {
                "endpoint": f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                "model": "tiny-index-worker",
            }
            m.save_config(config)

            first = m.summarize_text(
                "cache-test",
                "alpha beta",
                "Summarize this test.",
                timeout=2,
                route=m.MODEL_ROUTE_INDEX_CHUNK,
                prompt_version="test-summary-v1",
            )
            second = m.summarize_text(
                "cache-test",
                "alpha beta",
                "Summarize this test.",
                timeout=2,
                route=m.MODEL_ROUTE_INDEX_CHUNK,
                prompt_version="test-summary-v1",
            )
            assert first == "hello"
            assert second == "hello"
            assert len(FakeHandler.payloads) == 1
            assert FakeHandler.payloads[0]["model"] == "tiny-index-worker"
            assert "index_chunk: tiny-index-worker" in m.format_model_routes(include_defaults=True)
            assert list(m.model_cache_dir().glob("*/*.json"))
    finally:
        server.shutdown()
        server.server_close()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_cache is None:
            os.environ.pop("MOTOKO_MODEL_CACHE", None)
        else:
            os.environ["MOTOKO_MODEL_CACHE"] = old_cache


def test_local_model_catalog_unix_socket_route(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    socket_path = None
    FakeHandler.payloads = []
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        with isolated_state() as tmp:
            socket_path = tmp / "chat.sock"
            server = UnixHTTPServer(str(socket_path), FakeHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "chat": {
                        "endpoint": f"unix://{socket_path}",
                        "model": "qwen-test-chat",
                        "download_url": "https://example.invalid/model.gguf",
                        "sha256": "sha256-test",
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")

            assert m.endpoint() == f"unix://{socket_path}"
            assert m.model_name() == "qwen-test-chat"
            assert m.model_route_badge() == "qwen:chat"
            text = m.call_model_with_callback(
                [{"role": "user", "content": "hello"}],
                on_token=lambda _token: None,
                timeout=2,
            )
            assert text == "hello"
            assert FakeHandler.payloads[-1]["model"] == "qwen-test-chat"
            routes = m.format_model_routes(include_defaults=True)
            assert "manager=systemd-socket-worker" in routes
            assert f"endpoint=unix://{socket_path}" in routes
            server.shutdown()
            server.server_close()
    finally:
        if socket_path is not None:
            with contextlib.suppress(OSError):
                pathlib.Path(socket_path).unlink()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model


def test_local_model_catalog_task_routes(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        with isolated_state():
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen35-2b-worker": {
                        "endpoint": "unix:///run/motoko-llm/mares/qwen35-2b-worker.sock",
                        "modelId": "qwen3.5-2b-q4-k-m",
                        "tasks": ["index_chunk", "index_label", "memory_maintenance"],
                        "cache": {
                            "prompt": True,
                            "reuseMinTokens": 256,
                            "cacheRamMiB": 512,
                            "slotPromptSimilarity": 0.5,
                            "metrics": True,
                            "persistentSlotCache": False,
                        },
                        "metrics_endpoint": "unix:///run/motoko-llm/mares/qwen35-2b-worker.sock",
                        "metrics_path": "/metrics",
                    },
                    "ministral-3b-worker": {
                        "endpoint": "unix:///run/motoko-llm/mares/ministral-3b-worker.sock",
                        "modelId": "ministral-3-3b-instruct-2512-q4-k-m",
                        "tasks": ["index_chunk", "index_label", "index_file"],
                    },
                    "qwen3-4b-instruct-worker": {
                        "endpoint": "unix:///run/motoko-llm/mares/qwen3-4b-instruct-worker.sock",
                        "modelId": "qwen3-4b-instruct-2507-q4-k-m",
                        "tasks": ["index_file", "index_corpus", "audit"],
                    },
                    "qwen35-9b-worker": {
                        "endpoint": "unix:///run/motoko-llm/mares/qwen35-9b-worker.sock",
                        "modelId": "qwen3.5-9b-q4-k-m",
                        "tasks": ["index_corpus", "synthesis", "audit"],
                    },
                    "qwen36-chat": {
                        "endpoint": "unix:///run/motoko-llm/mares/qwen36-chat.sock",
                        "modelId": "qwen3.6-27b-mtp-ud-q5-k-xl",
                        "tasks": ["chat", "deep_synthesis"],
                    },
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")

            chat = m.model_route(m.MODEL_ROUTE_CHAT)
            chunk = m.model_route(m.MODEL_ROUTE_INDEX_CHUNK)
            label = m.model_route(m.MODEL_ROUTE_INDEX_LABEL)
            file_route = m.model_route(m.MODEL_ROUTE_INDEX_FILE)
            corpus = m.model_route(m.MODEL_ROUTE_INDEX_CORPUS)
            memory = m.model_route(m.MODEL_ROUTE_MEMORY)
            assert chat["catalog_route"] == "qwen36-chat"
            assert chunk["catalog_route"] == "qwen35-2b-worker"
            assert label["catalog_route"] == "ministral-3b-worker"
            assert file_route["catalog_route"] == "qwen3-4b-instruct-worker"
            assert corpus["catalog_route"] == "qwen35-9b-worker"
            assert memory["catalog_route"] == "qwen35-2b-worker"
            assert chunk["cache"]["prompt"] is True
            assert chunk["cache"]["reuseMinTokens"] == 256
            text = m.format_model_routes(include_defaults=True)
            assert "index_chunk: qwen3.5-2b-q4-k-m" in text
            assert "catalog=qwen35-2b-worker" in text
            assert "prompt-cache=on" in text
            assert "metrics-endpoint=unix:///run/motoko-llm/mares/qwen35-2b-worker.sock path=/metrics" in text
    finally:
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model


def test_embedding_route_fails_fast_when_model_file_missing(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        with isolated_state() as tmp:
            missing = tmp / "missing-embedding.gguf"
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen3-embedding-0b6": {
                        "kind": "embedding",
                        "endpoint": f"unix://{tmp / 'embed.sock'}",
                        "modelId": "qwen3-embedding-0.6b-q8-0",
                        "model_path": str(missing),
                        "tasks": ["embedding", "vector_index", "vector_query"],
                        "endpoint_paths": ["/v1/embeddings"],
                        "embedding_dimensions": 1024,
                        "maxParallel": 32,
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            try:
                m.embedding_route_info()
                raise AssertionError("expected missing embedding model file to fail fast")
            except SystemExit as exc:
                text = str(exc)
            assert "embedding route qwen3-embedding-0b6 declared model file is missing" in text
            assert str(missing) in text
            assert "verify declared model files" in text or "motoko-model helper is not on PATH" in text
    finally:
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model


def test_local_model_status_diagnostic_uses_catalog_route_without_hashing(m):
    with isolated_state() as tmp:
        socket_dir = tmp / "sockets"
        socket_dir.mkdir()
        route_info = {
            "route": m.MODEL_ROUTE_TOPIC,
            "catalog_route": "qwen35-9b-worker",
            "endpoint": f"unix://{socket_dir / 'qwen35-9b-worker.sock'}",
            "model_path": str(tmp / "missing.gguf"),
            "download_url": "https://example.invalid/model.gguf",
            "download_hash": "sha256-test",
        }
        old_run_helper = m.run_local_model_helper
        old_which = m.shutil.which
        calls = []

        def fake_run_helper(command, info, *, timeout=m.LOCAL_MODEL_HELPER_TIMEOUT_SECONDS):
            calls.append((command, m.local_model_helper_route(info), timeout))
            if command == "status":
                return "\n".join(
                    [
                        "realm=mares",
                        "route=qwen35-9b-worker",
                        "socket=active",
                        "proxy=activating",
                        "backend=activating",
                    ]
                )
            raise AssertionError(f"unexpected helper command: {command}")

        try:
            m.run_local_model_helper = fake_run_helper
            m.shutil.which = lambda name: "/run/current-system/sw/bin/motoko-model" if name == "motoko-model" else old_which(name)
            hint = m.local_model_verify_hint(route_info)
            assert "route=qwen35-9b-worker" in hint
            assert "proxy=activating" in hint
            assert "declared model file is missing" in hint
            assert "motoko-model verify qwen35-9b-worker" in hint
            assert calls == [("status", "qwen35-9b-worker", m.LOCAL_MODEL_HELPER_TIMEOUT_SECONDS)]
            compact = m.compact_local_model_status(fake_run_helper("status", route_info))
            assert compact == "route=qwen35-9b-worker socket=active proxy=activating backend=activating"
        finally:
            m.run_local_model_helper = old_run_helper
            m.shutil.which = old_which


def test_model_service_status_and_stop_use_motoko_model_helper(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        with isolated_state():
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen36-chat": {
                        "endpoint": "unix:///run/motoko-llm/mares/qwen36-chat.sock",
                        "modelId": "qwen3.6-27b-mtp-ud-q5-k-xl",
                        "tasks": ["chat", "deep_synthesis"],
                        "maxParallel": 1,
                    },
                    "qwen35-2b-worker": {
                        "endpoint": "unix:///run/motoko-llm/mares/qwen35-2b-worker.sock",
                        "modelId": "qwen3.5-2b-q4-k-m",
                        "tasks": ["index_chunk", "memory_maintenance"],
                        "maxParallel": 8,
                    },
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            calls = []
            old_run_helper = m.run_local_model_helper

            def fake_run_helper(command, info, *, timeout=m.LOCAL_MODEL_HELPER_TIMEOUT_SECONDS):
                route = m.local_model_helper_route(info)
                calls.append((command, route))
                if command == "status":
                    backend = "inactive" if calls and calls[-2:] == [("stop", route), ("status", route)] else "active"
                    return "\n".join(
                        [
                            "realm=mares",
                            f"route={route}",
                            "socket=active",
                            "proxy=active",
                            f"backend={backend}",
                            "cache=prompt:1 reuse_min_tokens:1024",
                        ]
                    )
                if command == "stop":
                    return f"stopped {route}"
                raise AssertionError(f"unexpected helper command: {command}")

            try:
                m.run_local_model_helper = fake_run_helper
                report = m.format_model_services("chat")
                assert "status source: motoko-model status ROUTE" in report
                assert "- qwen36-chat: qwen3.6-27b-mtp-ud-q5-k-xl" in report
                assert "logical routes: chat" in report
                assert "state: socket=active proxy=active backend=active" in report
                assert "backend=active is service/process state" in report

                stopped = m.stop_model_service("qwen36-chat")
                assert "model stop requested: qwen36-chat" in stopped
                assert "control source: motoko-model stop qwen36-chat" in stopped
                assert "helper: stopped qwen36-chat" in stopped
                assert ("stop", "qwen36-chat") in calls
            finally:
                m.run_local_model_helper = old_run_helper
    finally:
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model


def test_summary_reductions_fan_out_across_worker_routes(m):
    old_summary_input = m.SUMMARY_INPUT_CHARS
    old_summarize_text = m.summarize_text
    old_model_route = m.model_route
    old_parallel = os.environ.get("MOTOKO_SUMMARY_PARALLEL")
    old_max_parallel = os.environ.get("MOTOKO_SUMMARY_MAX_PARALLEL")
    lock = threading.Lock()
    active = 0
    max_active = 0
    routes = []

    def fake_model_route(route=m.MODEL_ROUTE_CHAT):
        route = m.normalize_model_route(route)
        return {
            "route": route,
            "endpoint": f"unix:///tmp/{route}.sock",
            "model": route,
            "request_path": "/v1/chat/completions",
            "manager_kind": "systemd-socket-worker",
            "catalog_route": route,
            "model_path": "",
            "max_parallel": 1,
            "download_url": "",
            "download_hash": "",
            "description": m.MODEL_ROUTE_DESCRIPTIONS.get(route, ""),
        }

    def fake_summarize_text(label, text, instruction, *, timeout=m.MODEL_TIMEOUT_SECONDS, route=m.MODEL_ROUTE_CHAT, prompt_version="summary-v1"):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            routes.append(route)
            active -= 1
        return f"{route}:{label}:{len(text)}"

    try:
        os.environ["MOTOKO_SUMMARY_PARALLEL"] = "1"
        os.environ["MOTOKO_SUMMARY_MAX_PARALLEL"] = "2"
        m.SUMMARY_INPUT_CHARS = 20
        m.model_route = fake_model_route
        m.summarize_text = fake_summarize_text
        result = m.summarize_blocks(
            "topic dossier: test",
            ["a" * 40, "b" * 40, "c" * 40, "d" * 40],
            "Final summary.",
            route=m.MODEL_ROUTE_TOPIC,
        )
        assert result.startswith(f"{m.MODEL_ROUTE_TOPIC}:")
        assert max_active >= 2
        assert m.MODEL_ROUTE_INDEX_FILE in routes
        assert m.MODEL_ROUTE_INDEX_CHUNK in routes
        assert routes[-1] == m.MODEL_ROUTE_TOPIC
    finally:
        m.SUMMARY_INPUT_CHARS = old_summary_input
        m.summarize_text = old_summarize_text
        m.model_route = old_model_route
        if old_parallel is None:
            os.environ.pop("MOTOKO_SUMMARY_PARALLEL", None)
        else:
            os.environ["MOTOKO_SUMMARY_PARALLEL"] = old_parallel
        if old_max_parallel is None:
            os.environ.pop("MOTOKO_SUMMARY_MAX_PARALLEL", None)
        else:
            os.environ["MOTOKO_SUMMARY_MAX_PARALLEL"] = old_max_parallel


def test_sources_fallback_lists_attached_topic_context(m):
    with isolated_state():
        topic = {
            "id": "topic-test",
            "name": "Yesterday Tasks",
            "query": "unfinished tasks",
            "summary": "Summary",
            "evidence": [
                {
                    "index": "idx",
                    "path": "/tmp/work/logbook.org",
                    "chunk": 3,
                }
            ],
        }
        m.atomic_write(m.topic_path(topic["id"]), json.dumps(topic, ensure_ascii=False) + "\n")
        conv = m.new_conversation("Topic attached")
        conv["context_items"] = [m.context_item_from_topic(topic)]
        text = m.format_conversation_sources(conv)
        assert "No recorded sources for the last answer yet" in text
        assert "topic topic-test" in text
        assert "/tmp/work/logbook.org" in text


def test_stale_attached_topic_is_skipped_in_chat_context(m):
    with isolated_state():
        conv = m.new_conversation("Stale topic")
        conv["context_items"] = [{"kind": "topic", "id": "missing-topic"}]

        context_text, sources = m.render_context_with_sources(conv["context_items"], "custom symbology")

        assert context_text == ""
        assert sources
        assert sources[0]["kind"] == "context-warning"
        assert sources[0]["context_kind"] == "topic"
        assert "matched 0" in sources[0]["warning"]
        formatted = m.format_sources(sources)
        assert "attached topic unavailable" in formatted


def test_answer_grounding_audit_sources(m):
    sources = [
        {
            "kind": "chunk",
            "index": "idx",
            "path": "/tmp/logbook.org",
            "chunk": 1,
        },
        {
            "kind": "context-plan",
            "total_chars": 1200,
            "budget_chars": 10000,
            "status": "ok",
            "lanes": [],
        },
    ]
    audited = m.sources_with_answer_audit(
        "summarize today according to logbook.org",
        "The logbook says the retrieval audit passed.",
        sources,
    )
    audit = audited[-1]
    assert audit["kind"] == "answer-audit"
    assert audit["status"] == "pass"
    assert audit["strong_evidence_sources"] == 1
    text = m.format_sources(audited)
    assert "answer audit" in text
    assert "paths: /tmp/logbook.org" in text

    thin = m.answer_grounding_audit("summarize according to logbook.org", "No documents are attached.", [])
    assert thin["status"] == "fail"
    assert "attach or study" in thin["recommended_action"]


def test_core_answer_grounding_audit_is_injectable(m):
    audit = m.answer_grounding_audit_core(
        "according to plan.org",
        "answer",
        [{"kind": "index", "root": "/tmp/docs", "status": "stale", "warnings": ["old"]}],
        schema_version="audit-test",
        created="2026-05-23T00:00:00+00:00",
        grounding_query_words={"according"},
        task_query_words={"task"},
        strong_source_kinds={"chunk"},
        context_source_kinds={"index"},
    )

    assert audit["artifact_schema"] == "audit-test"
    assert audit["status"] == "partial"
    assert audit["context_sources"] == 1
    assert audit["needs_grounding"]
    assert "/tmp/docs: stale" in audit["warnings"]
    assert audit["paths"] == ["/tmp/docs"]


def test_core_context_plan_is_injectable(m):
    lanes = [
        {"lane": "identity", "chars": 10, "sources": 1, "purpose": "realm"},
        {"lane": "attached context", "chars": 45, "sources": 3, "purpose": "evidence"},
    ]

    plan = m.context_plan_from_lanes_core(lanes, budget_chars=40)
    text = m.format_context_plan_core(plan, default_budget_chars=100)

    assert plan["kind"] == "context-plan"
    assert plan["total_chars"] == 55
    assert plan["status"] == "over-budget"
    assert "55/40 chars (over-budget)" in text
    assert "- attached context: 45 chars, 3 source(s), evidence" in text


def test_core_context_sufficiency_note_is_injectable(m):
    note = m.context_sufficiency_note_core(
        [{"kind": "recent-conversation"}],
        has_conversation_summary=False,
        ranked_topics=[{"id": "topic-1", "_score": 50}],
        ranked_dossiers=[{"id": "dossier-1", "_score": 10}],
        best_index={"id": "idx-1"},
        attached_topic_ids=set(),
        attached_dossier_ids={"dossier-1"},
        study_reuse_min_score=20,
    )

    assert "partial; answer from available memory" in note
    assert "existing topic dossier topic-1" in note
    assert "document index idx-1" in note
    assert "dossier-1" not in note


def test_core_retrieval_preview_formatting_is_injectable(m):
    prompt = "Intro\n\nAttached documents and dossiers:\nEvidence block\n\nAvailable private context catalog:\nCatalog"
    attached = m.extract_prompt_section_core(
        prompt,
        "Attached documents and dossiers",
        ["Available private context catalog"],
    )
    report = m.format_retrieval_preview_core(
        "what does plan.org say?",
        audit={
            "status": "pass",
            "strong_evidence_sources": 1,
            "context_sources": 0,
            "total_sources": 2,
            "source_kinds": {"chunk": 1, "context-plan": 1},
            "warnings": ["stale source"],
        },
        context_plan={"kind": "context-plan"},
        formatted_context_plan="Context plan: 10/100 chars (ok)",
        formatted_sources="1  chunk  /tmp/plan.org",
        attached_context=attached,
        max_chars=100,
    )

    assert attached == "Evidence block"
    assert "source audit: pass  strong 1  context 0  total 2" in report
    assert "source kinds: chunk=1, context-plan=1" in report
    assert "warning: stale source" in report
    assert "Context plan: 10/100 chars (ok)" in report
    assert "1  chunk  /tmp/plan.org" in report
    assert "Evidence block" in report


def test_named_file_query_boosts_matching_path(m):
    with isolated_state():
        index = {
            "id": "idx",
            "name": "orgfiles",
            "root": "/tmp/orgfiles",
            "files": [
                {
                    "path": "/tmp/orgfiles/organization/plan.org",
                    "summary": "High priority TODO planning notes with many active tasks.",
                    "signals": {"active_task_count": 10, "priorities": {"A": 2}},
                    "chunks": [
                        {
                            "chunk": 1,
                            "summary": "TODO planning backlog and tomorrow tasks.",
                            "content": "TODO many planning tasks for today and tomorrow.",
                        }
                    ],
                },
                {
                    "path": "/tmp/orgfiles/logbook.org",
                    "summary": "Daily logbook entries for yesterday and today.",
                    "signals": {},
                    "chunks": [
                        {
                            "chunk": 1,
                            "summary": "Yesterday and today logbook notes.",
                            "content": "Yesterday unfinished work and today's notes.",
                        }
                    ],
                },
            ],
        }
        rows = m.ranked_index_chunks(index, "summarize yesterday and today according to logbook.org")
        assert rows[0][1]["path"].endswith("/logbook.org")
        text, sources = m.retrieve_from_index(index, "summarize yesterday and today according to logbook.org")
        assert "/tmp/orgfiles/logbook.org" in text
        assert any(source.get("path", "").endswith("/logbook.org") for source in sources)


def test_retrieval_debug_explains_scores(m):
    with isolated_state():
        index = {
            "id": "debug-index",
            "name": "orgfiles",
            "root": "/tmp/orgfiles",
            "created": "2026-05-21T00:00:00+00:00",
            "corpus_summary": "Daily logbook and planning notes.",
            "files": [
                {
                    "path": "/tmp/orgfiles/notes.org",
                    "summary": "General planning notes with many unrelated TODOs.",
                    "signals": {"active_task_count": 8, "priorities": {"A": 1}},
                    "chunks": [
                        {
                            "chunk": 1,
                            "summary": "Planning backlog.",
                            "content": "* TODO Backlog item\n",
                            "signals": {"active_task_count": 1},
                        }
                    ],
                },
                {
                    "path": "/tmp/orgfiles/logbook.org",
                    "summary": "Daily logbook entries for yesterday and today.",
                    "signals": {},
                    "chunks": [
                        {
                            "chunk": 1,
                            "summary": "Yesterday and today logbook notes.",
                            "content": "* 2026-05-20\n** TODO Confirm retrieval debug\n",
                            "signals": {},
                        }
                    ],
                },
            ],
        }
        m.atomic_write(m.index_path(index["id"]), json.dumps(index, ensure_ascii=False, indent=2) + "\n")
        report = m.run_retrieval_debug(
            "summarize yesterday and today according to logbook.org",
            index_ids=[index["id"]],
            limit=4,
        )
        rows = report["indexes"][0]["chunks"]
        assert rows[0]["path"].endswith("/logbook.org")
        assert rows[0]["path_boost"] >= 2000
        text = m.format_retrieval_debug_report(report)
        assert "retrieval debug:" in text
        assert "path=2500" in text
        assert "diagnosis:" in text
        assert "prompt-use check" in text


def test_named_logbook_recent_query_uses_latest_org_sections(m):
    with isolated_state() as tmp:
        docs = tmp / "orgfiles"
        docs.mkdir()
        old_body = "Old setup note.\n" + ("older filler line\n" * 3600)
        recent_body = (
            "* [2026-05-18 Mon 11:14]\n"
            "** do\n"
            "*** TODO Renew vector diagnostics\n"
            "** log\n"
            "Motoko retrieved the right file but not the newest dated section.\n\n"
            "* [2026-05-19 Tue 12:34]\n"
            "** do\n"
            "*** TODO Check logbook synthesis\n"
            "** log\n"
            "Confirmed the last day should be selected from the tail.\n"
        )
        content = f"* [2026-04-09 Thu 12:39]\n** do\n{old_body}\n{recent_body}"
        path = docs / "logbook.org"
        path.write_text(content, encoding="utf-8")
        index = {
            "id": "recent-logbook-index",
            "name": "orgfiles",
            "root": str(docs),
            "created": "2026-05-21T10:00:00+00:00",
            "files": [
                {
                    "path": str(path),
                    "source_fingerprint": m.source_fingerprint(path),
                    "summary": "Daily logbook entries.",
                    "chunks": [
                        {
                            "chunk": 1,
                            "summary": "Chronological logbook chunk.",
                            "content": content,
                            "content_sha256": m.sha256_hex(content.encode("utf-8")),
                            "content_bytes": len(content.encode("utf-8")),
                        }
                    ],
                }
            ],
        }
        query = "summarize the last two days present in logbook.org"
        selection = m.query_aware_content_selection(query, content, 1200, use_models=True)
        excerpt = selection["excerpt"]
        assert "2026-05-18" in excerpt
        assert "2026-05-19" in excerpt
        assert "2026-04-09" not in excerpt
        assert "** do" in excerpt
        assert "** log" in excerpt
        assert selection["method"] == "date-span"
        labels = {span.get("label") for span in selection["spans"]}
        assert {"2026-05-18", "2026-05-19"} <= labels

        text, sources = m.retrieve_from_index(index, query)
        assert "2026-05-18" in text
        assert "2026-05-19" in text
        assert "2026-04-09" not in text
        chunk_sources = [source for source in sources if source.get("kind") == "chunk"]
        assert chunk_sources and chunk_sources[0]["path"].endswith("logbook.org")


def test_hierarchical_evidence_store_retrieves_org_day_and_terms(m):
    with isolated_state() as tmp:
        docs = tmp / "orgfiles"
        docs.mkdir()
        path = docs / "logbook.org"
        content = (
            "* [2026-05-18 Mon 11:14]\n"
            "** do\n"
            "*** TODO Review repaste plan\n"
            "** log\n"
            "Repasting was discussed as part of the Personal LLM Architecture work.\n\n"
            "* [2026-05-19 Tue 12:34]\n"
            "** do\n"
            "*** TODO Continue Personal LLM Architecture\n"
            "** log\n"
            "The word repaste appeared again with the model-service plan.\n"
        )
        path.write_text(content, encoding="utf-8")
        index = {
            "id": "evidence-index",
            "name": "orgfiles",
            "root": str(docs),
            "created": "2026-05-21T10:00:00+00:00",
            "files": [
                {
                    "path": str(path),
                    "source_fingerprint": m.source_fingerprint(path),
                    "summary": "Daily logbook entries.",
                    "chunks": [
                        {
                            "chunk": 1,
                            "summary": "Recent logbook notes.",
                            "content": content,
                            "content_sha256": m.sha256_hex(content.encode("utf-8")),
                            "content_bytes": len(content.encode("utf-8")),
                        }
                    ],
                }
            ],
        }
        m.atomic_write(m.index_path(index["id"]), json.dumps(index, ensure_ascii=False, indent=2) + "\n")

        store = m.build_evidence_store_from_index(index, write=False)
        kinds = {row.get("kind") for row in store["rows"]}
        assert "org_day" in kinds
        assert "org_task" in kinds
        report = m.query_evidence_store(store, "repaste Personal LLM Architecture logbook.org")
        assert report["rows"]
        assert report["rows"][0]["path"].endswith("logbook.org")
        assert "Personal LLM Architecture" in report["rows"][0]["text"]

        text, sources = m.retrieve_from_index(index, "repaste Personal LLM Architecture logbook.org")
        assert "Personal LLM Architecture" in text
        assert "repaste" in text.lower()
        chunk_sources = [source for source in sources if source.get("kind") == "chunk"]
        assert chunk_sources
        assert "evidence" in chunk_sources[0].get("retrieval_methods", [])
        assert chunk_sources[0].get("excerpt_selection") == "evidence-store"
        assert chunk_sources[0].get("evidence_id")
        assert "evidence" in m.format_retrieval_debug_report(
            m.run_retrieval_debug(
                "repaste Personal LLM Architecture logbook.org",
                index_ids=[index["id"]],
            )
        )


def test_span_selection_uses_embedding_and_rerank_routes(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    old_span_embedding = os.environ.get("MOTOKO_SPAN_EMBEDDING")
    old_span_rerank = os.environ.get("MOTOKO_SPAN_RERANK")
    old_span_model_input = os.environ.get("MOTOKO_SPAN_MODEL_INPUT_CHARS")
    embed_socket = None
    rerank_socket = None
    embed_server = None
    rerank_server = None
    EmbeddingHandler.payloads = []
    EmbeddingHandler.paths = []
    RerankHandler.payloads = []
    RerankHandler.paths = []
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        os.environ["MOTOKO_SPAN_EMBEDDING"] = "1"
        os.environ["MOTOKO_SPAN_RERANK"] = "1"
        os.environ["MOTOKO_SPAN_MODEL_INPUT_CHARS"] = "500"
        with isolated_state() as tmp:
            embed_socket = tmp / "embed.sock"
            embed_server = UnixHTTPServer(str(embed_socket), EmbeddingHandler)
            embed_thread = threading.Thread(target=embed_server.serve_forever, daemon=True)
            embed_thread.start()
            rerank_socket = tmp / "rerank.sock"
            rerank_server = UnixHTTPServer(str(rerank_socket), RerankHandler)
            rerank_thread = threading.Thread(target=rerank_server.serve_forever, daemon=True)
            rerank_thread.start()
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen3-embedding-0b6": {
                        "kind": "embedding",
                        "endpoint": f"unix://{embed_socket}",
                        "modelId": "qwen3-embedding-0.6b-q8-0",
                        "tasks": ["embedding", "vector_index", "vector_query"],
                        "endpoint_paths": ["/v1/embeddings"],
                        "embedding_dimensions": 4,
                        "maxParallel": 4,
                        "openai_compatible": True,
                    },
                    "qwen3-reranker-0b6": {
                        "kind": "reranker",
                        "endpoint": f"unix://{rerank_socket}",
                        "modelId": "qwen3-reranker-0.6b-q6-k",
                        "tasks": ["reranker", "rerank", "vector_rerank"],
                        "endpoint_paths": ["/v1/rerank"],
                        "maxParallel": 4,
                        "openai_compatible": True,
                    },
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            content = (
                "# General notes\n"
                + ("alpha errands and setup notes without the needed action. " * 80)
                + "\n\n# Action section\n"
                "Priority deadline task: prepare the Motoko retrieval span fix.\n"
            )
            selection = m.query_aware_content_selection(
                "priority deadline task",
                content,
                900,
                use_models=True,
            )
            assert "Priority deadline task" in selection["excerpt"]
            assert selection["method"] == "model-span"
            assert EmbeddingHandler.payloads
            assert RerankHandler.payloads
            assert any(span.get("span_rerank_score") == 0.95 for span in selection["spans"])
            long_text = (
                "* Large heading\n"
                + ("background planning filler without the target words.\n" * 80)
                + "Priority deadline task: preserve the local source passage.\n"
                + ("more filler after the target.\n" * 80)
            )
            long_span = m.make_evidence_span(
                kind="org-heading",
                label="Large heading",
                start=0,
                end=len(long_text),
                text=long_text,
                base_score=1,
            )
            scored, warnings = m.model_score_evidence_spans("priority deadline task", [long_span])
            assert not warnings
            selected = m.select_non_overlapping_spans(scored, max_chars=600)
            assert selected
            assert "Priority deadline task" in selected[0]["text"]
            assert selected[0].get("selected_sub_start") is not None
            for payload in EmbeddingHandler.payloads:
                inputs = payload.get("input", [])
                if isinstance(inputs, str):
                    inputs = [inputs]
                assert inputs
                assert max(len(str(item)) for item in inputs) <= 500
            for payload in RerankHandler.payloads:
                assert len(str(payload.get("query", ""))) <= 500
                assert max(len(str(item)) for item in payload.get("documents", [])) <= 500
    finally:
        if embed_server is not None:
            embed_server.shutdown()
            embed_server.server_close()
        if rerank_server is not None:
            rerank_server.shutdown()
            rerank_server.server_close()
        for socket_path in (embed_socket, rerank_socket):
            if socket_path is not None:
                with contextlib.suppress(OSError):
                    pathlib.Path(socket_path).unlink()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model
        if old_span_embedding is None:
            os.environ.pop("MOTOKO_SPAN_EMBEDDING", None)
        else:
            os.environ["MOTOKO_SPAN_EMBEDDING"] = old_span_embedding
        if old_span_rerank is None:
            os.environ.pop("MOTOKO_SPAN_RERANK", None)
        else:
            os.environ["MOTOKO_SPAN_RERANK"] = old_span_rerank
        if old_span_model_input is None:
            os.environ.pop("MOTOKO_SPAN_MODEL_INPUT_CHARS", None)
        else:
            os.environ["MOTOKO_SPAN_MODEL_INPUT_CHARS"] = old_span_model_input


def test_study_focus_recent_is_parsed_and_bounded(m):
    query, focus = m.parse_study_directive("summarize yesterday and today according to logbook.org --focus recent")
    assert query == "summarize yesterday and today according to logbook.org"
    assert focus == "recent"
    assert "--focus" not in m.study_retrieval_query(query, focus)
    assert "yesterday" in m.study_retrieval_query(query, focus)

    with isolated_state():
        conv = m.new_conversation("Study focus")
        conv["context_items"] = [{"kind": "index", "id": "idx"}]
        calls = []
        old_build_topic = m.build_topic_dossier
        try:
            def fake_build_topic(index_ids, topic_query, **kwargs):
                calls.append((index_ids, topic_query, kwargs))
                return {
                    "id": "topic1",
                    "name": "topic",
                    "query": topic_query,
                    "summary": "summary",
                    "evidence": [],
                }

            m.build_topic_dossier = fake_build_topic
            result = m.study_query(conv, query, focus=focus)
        finally:
            m.build_topic_dossier = old_build_topic
        assert result == "built topic dossier from attached index(es): topic1"
        assert calls[0][1] == query
        assert calls[0][2]["focus"] == "recent"
        assert calls[0][2]["max_chunks"] == 8
        assert "--focus" not in calls[0][2]["retrieval_query"]


def test_index_plan(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "a.txt").write_text("alpha\n", encoding="utf-8")
        (docs / "b.bin").write_bytes(b"\x00\x01")
        m.add_allowed_dir(str(docs))
        plan = m.plan_document_index(str(docs))
        assert plan["files"] == 1
        assert plan["bytes"] == 6
        assert plan["estimated_chunks"] == 1
        assert plan["estimated_model_calls"] == 3


def test_motokoignore_filters_index_candidates_and_plan(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "keep.org").write_text("* TODO Keep\n", encoding="utf-8")
        (docs / "secret.org").write_text("* Archive\n", encoding="utf-8")
        (docs / "legacy.bak").write_text("old text\n", encoding="utf-8")
        archive = docs / "archive"
        archive.mkdir()
        (archive / "old.org").write_text("* Old\n", encoding="utf-8")
        (docs / ".motokoignore").write_text(
            "# Motoko corpus exclusions\narchive/\n*.bak\n/secret.org\n",
            encoding="utf-8",
        )
        m.add_allowed_dir(str(docs))

        candidates = m.iter_index_candidates(docs, m.AUTO_INDEX_GLOB)
        assert [path.name for path in candidates] == ["keep.org"]

        plan = m.plan_document_index(str(docs))
        assert plan["files"] == 1
        assert plan["ignored_count"] == 3
        assert plan["ignored_file_count"] == 2
        assert plan["ignored_dir_count"] == 1
        assert len(plan["selection_policy"]["motokoignore"]["rules"]) == 3
        ignored = {item["relative_path"] for item in plan["ignored_examples"]}
        assert {"archive", "legacy.bak", "secret.org"} <= ignored


def test_motokoignore_marks_existing_index_stale(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        current = docs / "current.org"
        legacy = docs / "legacy.org"
        current.write_text("* Current\n", encoding="utf-8")
        legacy.write_text("* Legacy\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        index = {
            "id": "ignore-stale-index",
            "name": "docs",
            "root": str(docs.resolve()),
            "glob": m.AUTO_INDEX_GLOB,
            "selection_policy": m.document_selection_policy(docs, m.AUTO_INDEX_GLOB),
            "created": m.now(),
            "corpus_summary": "test corpus",
            "files": [
                {
                    "path": str(current.resolve()),
                    "source_fingerprint": m.source_fingerprint(current),
                    "chunks": [],
                },
                {
                    "path": str(legacy.resolve()),
                    "source_fingerprint": m.source_fingerprint(legacy),
                    "chunks": [],
                },
            ],
        }
        status, warnings = m.index_staleness(index)
        assert status == "fresh"
        assert warnings == []

        (docs / ".motokoignore").write_text("legacy.org\n", encoding="utf-8")
        status, warnings = m.index_staleness(index)
        assert status == "stale"
        assert any("source selection policy changed" in warning for warning in warnings)


def test_motokoignore_rejects_unsupported_negation(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "keep.org").write_text("* Keep\n", encoding="utf-8")
        (docs / ".motokoignore").write_text("!keep.org\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))
        try:
            m.plan_document_index(str(docs))
        except SystemExit as exc:
            assert "negation patterns are not supported" in str(exc)
        else:
            raise AssertionError("unsupported negation should fail closed")


def test_nix_managed_allowdirs_message(m):
    with isolated_state() as tmp:
        config = tmp / "config"
        config.mkdir()
        allowdirs = config / "allowdirs"
        allowdirs.symlink_to("/nix/store/motoko-test-allowdirs")

        message = m.nix_managed_config_message(allowdirs, "document allowlist")
        assert message is not None
        assert "Nix-managed" in message
        assert "NixOS/Home Manager" in message
        assert str(allowdirs) in message


def test_cwd_learning_plan_and_existing_index(m):
    old_cwd = os.getcwd()
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "plan.org").write_text("* TODO Plan tomorrow\n", encoding="utf-8")
        (docs / "notes.md").write_text("# Notes\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))
        os.chdir(docs)
        try:
            plan = m.cwd_learning_plan()
            assert plan is not None
            assert plan["root"] == docs.resolve()
            assert plan["files"] == 2
            assert "readable text files" in m.cwd_learning_offer_text(plan)
            assert "HRAG model call" in m.cwd_learning_offer_text(plan)

            index = {
                "id": "corpus-index",
                "name": "docs",
                "root": str(docs.resolve()),
                "glob": m.AUTO_INDEX_GLOB,
                "created": m.now(),
                "corpus_summary": "test corpus",
                "files": [
                    {
                        "path": str((docs / "plan.org").resolve()),
                        "source_fingerprint": m.source_fingerprint(docs / "plan.org"),
                        "chunks": [],
                    },
                    {
                        "path": str((docs / "notes.md").resolve()),
                        "source_fingerprint": m.source_fingerprint(docs / "notes.md"),
                        "chunks": [],
                    },
                ],
            }
            write_conversation(m, m.new_conversation("placeholder"))
            m.atomic_write(
                m.index_path(index["id"]),
                json.dumps(index, ensure_ascii=False, indent=2) + "\n",
            )
            refreshed = m.cwd_learning_plan()
            conv = m.new_conversation("Cwd attach")
            attached = m.attach_best_cwd_index(conv, refreshed)
            assert attached["id"] == "corpus-index"
            assert conv["context_items"][0]["id"] == "corpus-index"
            ui = object.__new__(m.MotokoTui)
            ui.conv = m.new_conversation("Quiet Cwd Attach")
            ui.messages = []
            ui.scroll = 0
            ui.dirty = False
            ui.cwd_index_offer = None
            ui.maybe_offer_cwd_learning()
            assert ui.conv["context_items"][0]["id"] == "corpus-index"
            assert not any("attached corpus index" in row.get("content", "") for row in ui.messages)
        finally:
            os.chdir(old_cwd)


def test_permissions_config(m):
    old_permissions = os.environ.get("MOTOKO_PERMISSIONS")
    try:
        os.environ.pop("MOTOKO_PERMISSIONS", None)
        with isolated_state():
            assert m.permission_mode() == "repo-read"
            m.set_permission_mode("chat-only")
            assert m.permission_mode() == "chat-only"
            try:
                m.require_permission("file-read")
            except SystemExit as exc:
                assert "does not allow file-read" in str(exc)
            else:
                raise AssertionError("chat-only should block file reads")
            m.set_permission_mode("repo-review")
            assert "repo-read" in m.PERMISSION_MODE_CAPABILITIES[m.permission_mode()]
            assert "repo-review" in m.format_permissions()
    finally:
        if old_permissions is None:
            os.environ.pop("MOTOKO_PERMISSIONS", None)
        else:
            os.environ["MOTOKO_PERMISSIONS"] = old_permissions


def test_identity_config(m):
    with isolated_state():
        assert m.identity_name() == "Motoko"
        assert m.identity_realm() == "personal"
        config = m.load_config()
        config["identity"] = {
            "name": "Motoko",
            "realm": "admin",
            "description": "Admin review assistant.",
        }
        m.save_config(config)
        assert m.identity_realm() == "admin"
        assert "Admin review assistant" in m.format_identity()
        conv = m.new_conversation("Identity")
        prompt, sources = m.build_system_prompt_and_sources(conv, "")
        assert "running in the admin realm" in prompt
        assert any(source.get("kind") == "identity" for source in sources)


def test_assistant_color_config(m):
    with isolated_state():
        assert m.assistant_color() == "purple"
        config = m.load_config()
        config["ui"] = {"assistant_color": "pink"}
        m.save_config(config)
        assert m.assistant_color() == "pink"
        assert "assistant color: pink" in m.format_identity()
        assert "assistant color: pink" in m.format_status()

        config = m.load_config()
        config["ui"] = {"assistant_color": "\033[31mred"}
        m.save_config(config)
        assert m.assistant_color() == "purple"
        assert "assistant_color" in m.load_config()["ui"]

        config = m.load_config()
        config["ui"] = {"assistant_color": "pink"}
        m.save_config(config)
        os.environ["MOTOKO_ALIAS_COLOR"] = "cyan"
        assert m.assistant_color() == "cyan"
        assert "assistant color: cyan" in m.format_identity()

        os.environ["MOTOKO_ALIAS_COLOR"] = "not-a-color"
        assert m.assistant_color() == "purple"


def test_report_highlighting_is_render_only(m):
    class FakeTty:
        def isatty(self):
            return True

    with isolated_state():
        old_stdout = m.sys.stdout
        old_real_stdout = m.sys.__stdout__
        old_term = os.environ.get("TERM")
        old_no_color = os.environ.get("NO_COLOR")
        try:
            os.environ["TERM"] = "xterm-256color"
            os.environ.pop("NO_COLOR", None)
            m.sys.stdout = m.io.StringIO()
            m.sys.__stdout__ = FakeTty()
            plain = "identity: Motoko\n  warning: stale index\n     why: attached index\n    1. total=10 path=notes.org"
            highlighted = m.highlight_report_text(plain)
            assert "\033[" in highlighted
            assert m.strip_ansi(highlighted) == plain
            assert "\033[" not in m.format_status()

            ui = object.__new__(m.MotokoTui)
            ui.messages = [{"role": "system", "content": "identity: Motoko"}]
            ui.answer_entry = None
            ui.generating = False
            rows = ui.body_display(80)
            assert "\033[" in rows[0]
            assert m.strip_ansi(rows[0]).startswith("› identity: Motoko")
        finally:
            m.sys.stdout = old_stdout
            m.sys.__stdout__ = old_real_stdout
            if old_term is None:
                os.environ.pop("TERM", None)
            else:
                os.environ["TERM"] = old_term
            if old_no_color is None:
                os.environ.pop("NO_COLOR", None)
            else:
                os.environ["NO_COLOR"] = old_no_color


def test_tui_role_markers_working_and_worked_line(m):
    with isolated_state():
        ui = object.__new__(m.MotokoTui)
        active = {"role": "assistant", "content": ""}
        ui.messages = [
            {"role": "system", "content": "identity: Motoko"},
            {"role": "assistant", "content": "Done answer."},
            active,
            {"role": "worked", "content": "6m 32s"},
        ]
        ui.answer_entry = active
        ui.generating = True
        ui.answer_started_monotonic = time.monotonic() - 173
        ui.answer_phase_started_monotonic = time.monotonic() - 32
        ui.answer_phase = "answering"

        rows = [m.strip_ansi(row) for row in ui.body_display(60) if row.strip()]
        assert rows[0].startswith("› identity: Motoko")
        assert rows[1].startswith("› Done answer.")
        assert rows[2].startswith("● Answering (32s)")
        assert rows[3].startswith("Worked for 6m 32s ")
        assert "─" in rows[3]


def test_tui_alt_backspace_deletes_previous_word(m):
    ui = object.__new__(m.MotokoTui)
    ui.input_buffer = "alpha beta  gamma"
    ui.cursor = len(ui.input_buffer)
    ui.kill_ring = ""
    ui.dropdown_index = 0
    ui.overlay_lines = None
    ui.dirty = False

    ui.handle_key("word-backspace")

    assert ui.input_buffer == "alpha beta  "
    assert ui.cursor == len("alpha beta  ")
    assert ui.kill_ring == "gamma"
    assert ui.dropdown_index == 0
    assert ui.dirty


def test_tui_bottom_status_omits_chat_phase_and_spinner(m):
    with isolated_state():
        ui = object.__new__(m.MotokoTui)
        ui.conv = {"title": "Status Test"}
        ui.generating = True
        ui.maintaining = False
        ui.report_running = 0
        ui.report_status = ""
        ui.pending_prompts = m.collections.deque()
        ui.study_running = False
        ui.study_status = "study: idle"
        ui.study_last_note = ""
        ui.status = "ready"
        ui.index_progress = None

        status = m.strip_ansi(" ".join(ui.status_display(80)))
        assert "Motoko" not in status
        assert "Status Test" in status
        assert "chat:" not in status
        assert "/ chat" not in status
        assert "ready" not in status
        assert "bg: idle" in status


def test_tui_bottom_renderer_skips_identical_frames(m):
    with isolated_state():
        captured = []
        ui = object.__new__(m.MotokoTui)
        ui.conv = {"title": "Stable Bottom"}
        ui.input_buffer = ""
        ui.cursor = 0
        ui.dropdown_index = 0
        ui.generating = False
        ui.maintaining = False
        ui.report_running = 0
        ui.report_status = ""
        ui.pending_prompts = m.collections.deque()
        ui.study_running = False
        ui.study_status = "study: idle"
        ui.study_last_note = ""
        ui.status = "ready"
        ui.index_progress = None
        ui.answer_entry = None
        ui.bottom_rows_rendered = 0
        ui.bottom_cursor_row_offset = 0
        ui.bottom_frame_key = None
        ui.write = captured.append

        ui.draw_bottom_area(80, 12)
        writes_after_first_draw = len(captured)
        assert writes_after_first_draw == 1

        ui.draw_bottom_area(80, 12)
        assert len(captured) == writes_after_first_draw

        ui.input_buffer = "draft"
        ui.cursor = len("draft")
        ui.draw_bottom_area(80, 12)
        assert len(captured) == writes_after_first_draw + 1
        assert captured[-1].count("\033[J") == 1
        assert "draft" in m.strip_ansi(captured[-1])


def test_tui_append_renderer_keeps_transcript_in_scrollback(m):
    with isolated_state():
        captured = []
        ui = object.__new__(m.MotokoTui)
        ui.conv = {"title": "Scrollback Test"}
        ui.messages = [
            {"role": "user", "content": "first prompt"},
            {"role": "assistant", "content": "first answer"},
        ]
        ui.rendered_message_ids = set()
        ui.bottom_rows_rendered = 0
        ui.bottom_cursor_row_offset = 0
        ui.overlay_screen_active = False
        ui.overlay_lines = None
        ui.input_buffer = ""
        ui.cursor = 0
        ui.dropdown_index = 0
        ui.generating = False
        ui.maintaining = False
        ui.report_running = 0
        ui.report_status = ""
        ui.pending_prompts = m.collections.deque()
        ui.study_running = False
        ui.study_status = "study: idle"
        ui.study_last_note = ""
        ui.status = "ready"
        ui.index_progress = None
        ui.answer_entry = None
        ui.scroll = 0
        ui.last_render = 0.0
        ui.dirty = True
        ui.drain_events = lambda: None
        ui.terminal_size = lambda: os.terminal_size((80, 12))
        ui.write = captured.append

        ui.render()
        first = m.strip_ansi("".join(captured))
        assert "\x1b[H" not in "".join(captured)
        assert "first prompt" in first
        assert "first answer" in first
        assert "Scrollback Test" in first

        captured.clear()
        ui.input_buffer = "draft"
        ui.cursor = len("draft")
        ui.dirty = True
        ui.render()
        second = m.strip_ansi("".join(captured))
        assert "first prompt" not in second
        assert "first answer" not in second
        assert "draft" in second


def test_tui_seed_messages_renders_full_saved_history_without_redundant_banner(m):
    conv = {
        "id": "history-test",
        "title": "History Test",
        "messages": [
            {"role": "user", "content": f"user turn {idx}"}
            for idx in range(m.MAX_RECENT_MESSAGES + 3)
        ],
    }
    ui = object.__new__(m.MotokoTui)
    rows = ui.seed_messages(conv)
    contents = [row.get("content", "") for row in rows]
    assert not any("Motoko conversation:" in content for content in contents)
    assert not any("Type / for commands" in content for content in contents)
    assert any(content == "user turn 0" for content in contents)
    assert any(content == f"user turn {m.MAX_RECENT_MESSAGES + 2}" for content in contents)


def test_tui_prompt_history_is_seeded_from_saved_user_turns(m):
    conv = {
        "id": "prompt-history-test",
        "title": "Prompt History Test",
        "messages": [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "first answer"},
            {"role": "user", "content": "second question"},
        ],
    }
    ui = object.__new__(m.MotokoTui)
    ui.history = ui.seed_input_history(conv)
    ui.history_index = None
    ui.input_buffer = ""
    ui.cursor = 0

    ui.history_up()
    assert ui.input_buffer == "second question"
    assert ui.cursor == len("second question")

    ui.history_up()
    assert ui.input_buffer == "first question"
    assert ui.cursor == len("first question")


def test_tui_resume_without_id_uses_dropdown_instead_of_terminal_prompt(m):
    with isolated_state():
        conv = m.new_conversation("Current")
        ui = object.__new__(m.MotokoTui)
        ui.conv = conv
        ui.input_buffer = ""
        ui.cursor = 0
        ui.dropdown_index = 0
        ui.status = "ready"
        ui.dirty = False

        old_load = m.load_conversation
        try:
            def fail_load(_selector=None):
                raise AssertionError("/resume without id should not invoke terminal selection in the TUI")

            m.load_conversation = fail_load
            ui.handle_command("/resume")
        finally:
            m.load_conversation = old_load

        assert ui.input_buffer == "/resume "
        assert ui.cursor == len("/resume ")
        assert ui.status == "choose a conversation"
        assert ui.dirty


def test_conversation_delete_removes_owned_derived_artifacts(m):
    with isolated_state():
        conv = m.new_conversation("Delete Me")
        conv["id"] = "delete-me"
        conv["messages"] = [{"role": "user", "content": "remember this"}]
        write_conversation(m, conv)
        other = m.new_conversation("Keep Me")
        other["id"] = "keep-me"
        write_conversation(m, other)

        m.write_memory_rows(
            [
                {"id": "mem-delete", "text": "delete", "conversation_id": "delete-me"},
                {"id": "mem-keep", "text": "keep", "conversation_id": "keep-me"},
            ]
        )
        m.append_jsonl(m.response_feedback_path(), {"schema": m.RESPONSE_FEEDBACK_SCHEMA_VERSION, "conversation_id": "delete-me"})
        m.append_jsonl(m.response_feedback_path(), {"schema": m.RESPONSE_FEEDBACK_SCHEMA_VERSION, "conversation_id": "keep-me"})
        m.append_jsonl(m.study_jobs_path(), {"job_id": "job-delete", "conversation_id": "delete-me"})
        m.append_jsonl(m.study_jobs_path(), {"job_id": "job-keep", "conversation_id": "keep-me"})
        m.atomic_write(m.topic_path("topic-delete"), json.dumps({"id": "topic-delete", "owner_conversation_id": "delete-me"}) + "\n")
        m.atomic_write(m.topic_path("topic-keep"), json.dumps({"id": "topic-keep", "owner_conversation_id": "keep-me"}) + "\n")
        m.atomic_write(m.dossier_path("dossier-delete"), json.dumps({"id": "dossier-delete", "source_conversations": [{"id": "delete-me"}]}) + "\n")
        m.atomic_write(m.dossier_path("dossier-keep"), json.dumps({"id": "dossier-keep", "source_conversations": [{"id": "keep-me"}]}) + "\n")
        m.atomic_write(m.feedback_eval_path("eval-delete"), json.dumps({"fixtures": [{"conversation_id": "delete-me"}]}) + "\n")
        m.atomic_write(m.feedback_eval_path("eval-keep"), json.dumps({"fixtures": [{"conversation_id": "keep-me"}]}) + "\n")
        m.atomic_write(m.profile_path(), json.dumps({"conversation_ids": ["delete-me"]}) + "\n")
        m.write_maintenance_state({"job_id": "maint-delete", "conversation_id": "delete-me", "status": "running"})
        m.write_study_state({"conversation_id": "delete-me", "status": "running"})
        m.atomic_write(m.context_catalog_path(), "{}\n")

        report = m.delete_conversation_and_artifacts(conv)

        assert report["conversation_deleted"]
        assert report["memories_deleted"] == 1
        assert report["feedback_deleted"] == 1
        assert report["study_job_events_deleted"] == 1
        assert report["topics_deleted"] == 1
        assert report["dossiers_deleted"] == 1
        assert report["feedback_evals_deleted"] == 1
        assert not m.conversation_path("delete-me").exists()
        assert m.conversation_path("keep-me").exists()
        assert [row["id"] for row in m.read_memory_rows()] == ["mem-keep"]
        assert [row["conversation_id"] for row in m.read_response_feedback_rows()] == ["keep-me"]
        assert [row["conversation_id"] for row in m.read_jsonl(m.study_jobs_path())] == ["keep-me"]
        assert not m.topic_path("topic-delete").exists()
        assert m.topic_path("topic-keep").exists()
        assert not m.dossier_path("dossier-delete").exists()
        assert m.dossier_path("dossier-keep").exists()
        assert not m.feedback_eval_path("eval-delete").exists()
        assert m.feedback_eval_path("eval-keep").exists()
        assert not m.profile_path().exists()
        assert m.read_maintenance_state() is None
        assert m.read_study_state() is None
        assert not m.context_catalog_path().exists()


def test_close_conversation_prunes_empty_chats(m):
    with isolated_state():
        empty = m.new_conversation()
        empty["id"] = "empty-chat"
        m.save_conversation(empty)
        assert m.conversation_path("empty-chat").exists()

        assert not m.close_conversation(empty)
        assert not m.conversation_path("empty-chat").exists()

        kept = m.new_conversation()
        kept["id"] = "kept-chat"
        kept["messages"] = [{"role": "user", "content": "keep this"}]
        assert m.close_conversation(kept)
        assert m.conversation_path("kept-chat").exists()


def test_tui_report_commands_do_not_persist_system_output(m):
    with isolated_state():
        conv = m.new_conversation("Reports")
        conv["id"] = "reports"
        conv["messages"] = [
            {"role": "user", "content": "What did sources use?"},
            {"role": "assistant", "content": "A short answer."},
        ]
        conv["last_sources"] = [
            {
                "kind": "answer-audit",
                "status": "grounded",
                "reflection": "Used excerpt evidence.",
                "recommended_action": "none",
            }
        ]
        write_conversation(m, conv)
        saved_before = json.loads(m.conversation_path(conv["id"]).read_text(encoding="utf-8"))

        ui = object.__new__(m.MotokoTui)
        ui.conv = conv
        ui.messages = []
        ui.scroll = 0
        ui.dirty = False
        ui.status = "ready"
        ui.generating = False
        ui.maintaining = False
        ui.report_running = 0
        ui.report_status = ""
        ui.report_token = 0
        ui.active_report_token = 0
        ui.overlay_title = None
        ui.overlay_lines = None
        ui.overlay_scroll = 0
        ui.events = m.collections.deque()
        ui.events_lock = threading.Lock()

        ui.handle_command("/status")
        deadline = time.monotonic() + 2
        while ui.report_running and time.monotonic() < deadline:
            ui.drain_events()
            time.sleep(0.01)
        ui.drain_events()
        assert ui.overlay_title == "/status"
        assert any("identity:" in line for line in ui.overlay_lines or [])

        ui.handle_command("/sources")
        deadline = time.monotonic() + 2
        while ui.report_running and time.monotonic() < deadline:
            ui.drain_events()
            time.sleep(0.01)
        ui.drain_events()

        assert ui.overlay_title == "/sources"
        assert any("answer audit" in line for line in ui.overlay_lines or [])

        ui.handle_command("/indexes")
        deadline = time.monotonic() + 2
        while ui.report_running and time.monotonic() < deadline:
            ui.drain_events()
            time.sleep(0.01)
        ui.drain_events()
        assert ui.overlay_title == "/indexes"
        assert ui.overlay_lines == ["No document indexes yet."]

        ui.handle_command("/topics")
        deadline = time.monotonic() + 2
        while ui.report_running and time.monotonic() < deadline:
            ui.drain_events()
            time.sleep(0.01)
        ui.drain_events()
        assert ui.overlay_title == "/topics"
        assert ui.overlay_lines == ["No topic dossiers yet."]

        ui.handle_command("/dossiers")
        deadline = time.monotonic() + 2
        while ui.report_running and time.monotonic() < deadline:
            ui.drain_events()
            time.sleep(0.01)
        ui.drain_events()
        assert ui.overlay_title == "/dossiers"
        assert ui.overlay_lines == ["No memory dossiers yet."]

        ui.handle_command("/memories")
        deadline = time.monotonic() + 2
        while ui.report_running and time.monotonic() < deadline:
            ui.drain_events()
            time.sleep(0.01)
        ui.drain_events()
        assert ui.overlay_title == "/memories"
        assert ui.overlay_lines == ["No memories yet."]

        ui.handle_command("/profile")
        deadline = time.monotonic() + 2
        while ui.report_running and time.monotonic() < deadline:
            ui.drain_events()
            time.sleep(0.01)
        ui.drain_events()
        assert ui.overlay_title == "/profile"
        assert ui.overlay_lines == ["No profile dossier yet. Run 'motoko profile refresh' or /profile-refresh."]

        ui.handle_command("/remember durable preference")
        deadline = time.monotonic() + 2
        while ui.report_running and time.monotonic() < deadline:
            ui.drain_events()
            time.sleep(0.01)
        ui.drain_events()
        assert ui.overlay_title == "/remember"
        assert ui.overlay_lines == ["memory saved"]
        assert m.read_memory_rows()[-1]["text"] == "durable preference"

        ui.handle_command("/memory pin 1")
        deadline = time.monotonic() + 2
        while ui.report_running and time.monotonic() < deadline:
            ui.drain_events()
            time.sleep(0.01)
        ui.drain_events()
        assert ui.overlay_title == "/memory pin"
        assert ui.overlay_lines[0].startswith("memory pinned:")
        assert m.read_memory_rows()[0]["pinned"] is True

        old_context_item_from_file = m.context_item_from_file
        try:
            m.context_item_from_file = lambda path: {"kind": "file", "path": path, "content": "stub"}
            ui.handle_command("/read /tmp/context.txt")
            deadline = time.monotonic() + 2
            while ui.report_running and time.monotonic() < deadline:
                ui.drain_events()
                time.sleep(0.01)
            ui.drain_events()
        finally:
            m.context_item_from_file = old_context_item_from_file

        assert ui.overlay_title == "/read"
        assert ui.overlay_lines == ["attached: /tmp/context.txt"]
        assert conv["context_items"][-1]["path"] == "/tmp/context.txt"

        old_latest_evidence_store = m.latest_evidence_store
        old_query_evidence_store = m.query_evidence_store
        old_format_evidence_query_report = m.format_evidence_query_report
        try:
            m.latest_evidence_store = lambda: {"id": "store"}
            m.query_evidence_store = lambda store, query: {"store": store, "query": query}
            m.format_evidence_query_report = lambda report: f"evidence query: {report['query']}"
            ui.handle_command("/evidence-query texere")
            deadline = time.monotonic() + 2
            while ui.report_running and time.monotonic() < deadline:
                ui.drain_events()
                time.sleep(0.01)
            ui.drain_events()
        finally:
            m.latest_evidence_store = old_latest_evidence_store
            m.query_evidence_store = old_query_evidence_store
            m.format_evidence_query_report = old_format_evidence_query_report

        assert ui.overlay_title == "/evidence-query"
        assert ui.overlay_lines == ["evidence query: texere"]

        old_latest_vector_store = m.latest_vector_store
        old_query_vector_store = m.query_vector_store
        old_format_vector_query_report = m.format_vector_query_report
        try:
            m.latest_vector_store = lambda: {"id": "vector-store"}
            m.query_vector_store = lambda store, query, rerank=False: {
                "store": store,
                "query": query,
                "rerank": rerank,
            }
            m.format_vector_query_report = lambda report: f"vector query: {report['query']} rerank={report['rerank']}"
            ui.handle_command("/vector-query --rerank texere")
            deadline = time.monotonic() + 2
            while ui.report_running and time.monotonic() < deadline:
                ui.drain_events()
                time.sleep(0.01)
            ui.drain_events()
        finally:
            m.latest_vector_store = old_latest_vector_store
            m.query_vector_store = old_query_vector_store
            m.format_vector_query_report = old_format_vector_query_report

        assert ui.overlay_title == "/vector-query"
        assert ui.overlay_lines == ["vector query: texere rerank=True"]

        old_stop_model_service = m.stop_model_service
        try:
            m.stop_model_service = lambda selector: f"stopped model route: {selector}"
            ui.handle_command("/model-stop qwen35-2b-worker")
            deadline = time.monotonic() + 2
            while ui.report_running and time.monotonic() < deadline:
                ui.drain_events()
                time.sleep(0.01)
            ui.drain_events()
        finally:
            m.stop_model_service = old_stop_model_service

        assert ui.overlay_title == "/model-stop"
        assert ui.overlay_lines == ["stopped model route: qwen35-2b-worker"]

        old_format_task_candidates = m.format_task_candidates_from_chat
        try:
            m.format_task_candidates_from_chat = lambda conv_arg, query="": f"tasks query: {query.strip()}"
            ui.handle_command("/tasks tomorrow")
            deadline = time.monotonic() + 2
            while ui.report_running and time.monotonic() < deadline:
                ui.drain_events()
                time.sleep(0.01)
            ui.drain_events()
        finally:
            m.format_task_candidates_from_chat = old_format_task_candidates

        assert ui.overlay_title == "/tasks"
        assert ui.overlay_lines == ["tasks query: tomorrow"]
        assert ui.messages == []
        assert conv["messages"] == saved_before["messages"]
        saved_after = json.loads(m.conversation_path(conv["id"]).read_text(encoding="utf-8"))
        assert saved_after["messages"] == saved_before["messages"]


def test_tui_report_command_does_not_block_render_thread(m):
    with isolated_state():
        conv = m.new_conversation("Async report")
        conv["id"] = "async-report"
        write_conversation(m, conv)

        ui = object.__new__(m.MotokoTui)
        ui.conv = conv
        ui.messages = []
        ui.scroll = 0
        ui.dirty = False
        ui.status = "ready"
        ui.generating = False
        ui.maintaining = False
        ui.report_running = 0
        ui.report_status = ""
        ui.report_token = 0
        ui.active_report_token = 0
        ui.overlay_title = None
        ui.overlay_lines = None
        ui.overlay_scroll = 0
        ui.events = m.collections.deque()
        ui.events_lock = threading.Lock()

        started = threading.Event()
        release = threading.Event()
        old_format_status = m.format_status
        try:
            def slow_status(_conv=None):
                started.set()
                assert release.wait(2)
                return "identity: Motoko\nmodel status source: test"

            m.format_status = slow_status
            ui.handle_command("/status")

            assert ui.report_running == 1
            assert ui.overlay_title == "/status"
            assert ui.overlay_lines == ["/status: running..."]
            assert started.wait(1)

            release.set()
            deadline = time.monotonic() + 2
            while ui.report_running and time.monotonic() < deadline:
                ui.drain_events()
                time.sleep(0.01)
            ui.drain_events()
            assert ui.report_running == 0
            assert ui.overlay_lines == ["identity: Motoko", "model status source: test"]
        finally:
            release.set()
            m.format_status = old_format_status


def test_tui_prompt_is_saved_before_context_preparation(m):
    with isolated_state():
        conv = m.new_conversation("Immediate prompt")
        conv["id"] = "immediate-prompt"
        write_conversation(m, conv)

        ui = object.__new__(m.MotokoTui)
        ui.conv = conv
        ui.messages = []
        ui.scroll = 0
        ui.dirty = False
        ui.status = "ready"
        ui.generating = False
        ui.answer_phase = ""
        ui.answer_entry = None
        ui.events = m.collections.deque()
        ui.events_lock = threading.Lock()
        ui.pending_prompts = m.collections.deque()
        ui.start_maintenance = lambda *args, **kwargs: None

        build_started = threading.Event()
        release_build = threading.Event()
        old_build_messages = m.build_messages
        old_call_model = m.call_model_with_callback
        try:
            def slow_build_messages(conv_arg, query=""):
                build_started.set()
                assert release_build.wait(2)
                return [{"role": "system", "content": "prompt"}] + conv_arg.get("messages", []), []

            def fake_call_model(messages, *, temperature=0.7, on_token=None, route=None, cancel_event=None, **_kwargs):
                if on_token:
                    on_token("ok")
                return "ok"

            m.build_messages = slow_build_messages
            m.call_model_with_callback = fake_call_model

            ui.start_generation("slow context setup")

            assert any(
                row.get("role") == "user" and row.get("content") == "slow context setup"
                for row in ui.messages
            )
            saved = json.loads(m.conversation_path(conv["id"]).read_text(encoding="utf-8"))
            assert saved["messages"] == [{"role": "user", "content": "slow context setup"}]
            assert ui.generating
            assert ui.answer_phase == "preparing"
            assert build_started.wait(1)

            release_build.set()
            deadline = time.monotonic() + 2
            while ui.generating and time.monotonic() < deadline:
                ui.drain_events()
                time.sleep(0.01)
            ui.drain_events()
            assert not ui.generating
            assert conv["messages"][-1] == {"role": "assistant", "content": "ok"}
        finally:
            release_build.set()
            m.build_messages = old_build_messages
            m.call_model_with_callback = old_call_model


def test_tui_stop_during_preparing_cancels_before_model_call(m):
    with isolated_state():
        conv = m.new_conversation("Stop preparing")
        conv["id"] = "stop-preparing"
        write_conversation(m, conv)

        ui = object.__new__(m.MotokoTui)
        ui.conv = conv
        ui.messages = []
        ui.scroll = 0
        ui.dirty = False
        ui.status = "ready"
        ui.generating = False
        ui.answer_phase = ""
        ui.answer_entry = None
        ui.events = m.collections.deque()
        ui.events_lock = threading.Lock()
        ui.pending_prompts = m.collections.deque(["queued two", "queued three"])
        ui.start_maintenance = lambda *args, **kwargs: None

        build_started = threading.Event()
        release_build = threading.Event()
        model_called = threading.Event()
        old_build_messages = m.build_messages
        old_call_model = m.call_model_with_callback
        try:
            def slow_build_messages(conv_arg, query=""):
                build_started.set()
                assert release_build.wait(2)
                return [{"role": "system", "content": "prompt"}] + conv_arg.get("messages", []), []

            def fail_call_model(*args, **kwargs):
                model_called.set()
                raise AssertionError("model should not be called after /stop during preparation")

            m.build_messages = slow_build_messages
            m.call_model_with_callback = fail_call_model

            ui.start_generation("stop while preparing")
            assert build_started.wait(1)
            ui.handle_command("/stop")
            assert ui.cancel_event.is_set()
            assert not ui.pending_prompts
            assert any("discarded 2 queued prompt" in row.get("content", "") for row in ui.messages)

            release_build.set()
            deadline = time.monotonic() + 2
            while ui.generating and time.monotonic() < deadline:
                ui.drain_events()
                time.sleep(0.01)
            ui.drain_events()
            assert not ui.generating
            assert not model_called.is_set()
        finally:
            release_build.set()
            m.build_messages = old_build_messages
            m.call_model_with_callback = old_call_model


def test_tui_clear_queue_discards_pending_prompts(m):
    ui = object.__new__(m.MotokoTui)
    ui.messages = []
    ui.scroll = 0
    ui.dirty = False
    ui.status = "ready"
    ui.generating = False
    ui.pending_prompts = m.collections.deque(["one", "two"])

    ui.handle_command("/clear-queue")

    assert not ui.pending_prompts
    assert ui.status == "discarded 2 queued prompt(s)"
    assert ui.messages[-1]["content"] == "discarded 2 queued prompt(s)"


def test_tui_stop_closes_active_model_request(m):
    class Closeable:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    response = Closeable()
    connection = Closeable()
    ui = object.__new__(m.MotokoTui)
    ui.messages = []
    ui.scroll = 0
    ui.dirty = False
    ui.status = "ready"
    ui.generating = True
    ui.pending_prompts = m.collections.deque()
    ui.cancel_event = threading.Event()
    ui.active_model_lock = threading.Lock()
    ui.active_model_response = response
    ui.active_model_connection = connection

    ui.handle_command("/stop")

    assert ui.cancel_event.is_set()
    assert response.closed
    assert connection.closed
    assert ui.messages[-1]["content"] == "stopping current answer"


def test_response_feedback_is_private_and_does_not_pollute_conversation(m):
    with isolated_state():
        conv = m.new_conversation("Feedback")
        conv["id"] = "feedback"
        conv["messages"] = [
            {"role": "user", "content": "What should I do tomorrow?"},
            {"role": "assistant", "content": "You should review the logbook."},
        ]
        conv["last_sources"] = [
            {
                "kind": "chunk",
                "index": "idx",
                "path": "/tmp/logbook.org",
                "chunk": 1,
                "retrieval": "hybrid",
                "retrieval_methods": ["lexical", "vector"],
                "hybrid_score": 123,
                "rerank_score": 0.8,
            }
        ]
        write_conversation(m, conv)
        saved_before = json.loads(m.conversation_path(conv["id"]).read_text(encoding="utf-8"))

        row = m.record_response_feedback(conv, "down", "It missed the scheduled item.")

        assert row["schema"] == m.RESPONSE_FEEDBACK_SCHEMA_VERSION
        assert row["rating"] == "down"
        assert row["realm"] == m.identity_realm()
        assert "scheduled item" in row["note"]
        assert row["sources"][0]["retrieval_methods"] == ["lexical", "vector"]
        saved_after = json.loads(m.conversation_path(conv["id"]).read_text(encoding="utf-8"))
        assert saved_after["messages"] == saved_before["messages"]
        feedback_rows = [
            json.loads(line)
            for line in m.response_feedback_path().read_text(encoding="utf-8").splitlines()
        ]
        assert feedback_rows[-1]["id"] == row["id"]


def test_feedback_eval_exports_private_retrieval_fixtures(m):
    with isolated_state():
        conv = m.new_conversation("Feedback eval")
        conv["id"] = "feedback-eval-conv"
        conv["messages"] = [
            {"role": "user", "content": "summarize logbook.org"},
            {"role": "assistant", "content": "A weak answer."},
        ]
        conv["last_sources"] = [
            {
                "kind": "chunk",
                "index": "idx",
                "path": "/tmp/logbook.org",
                "chunk": 1,
                "evidence_id": "ev-abc",
                "evidence_kind": "org_day",
                "evidence_date": "2026-05-19",
                "evidence_score": 4000,
            }
        ]
        row = m.record_response_feedback(conv, "down", "Wrong source and stale summary.")
        report = m.run_feedback_eval()
        assert report["schema"] == m.FEEDBACK_EVAL_SCHEMA_VERSION
        assert report["fixture_count"] == 1
        fixture = report["fixtures"][0]
        assert fixture["id"] == row["id"]
        assert fixture["quality_status"] == "needs-review"
        assert "ranking" in fixture["focus"] or "staleness" in fixture["focus"]
        assert fixture["source_evidence_count"] == 1
        text = m.format_feedback_eval_report(report)
        assert "feedback eval:" in text
        assert "Wrong source" in text
        path = m.save_feedback_eval_report(report)
        assert path.exists()


def test_retrieval_preview_shows_context_without_model_call(m):
    with isolated_state():
        conv = m.new_conversation("Preview")
        conv["context_items"] = [
            {
                "kind": "file",
                "path": "/tmp/tasks.org",
                "content": "* TODO Prepare tomorrow plan\nDEADLINE: <2026-05-22 Fri>\n",
                "bytes": 60,
            }
        ]
        report = m.format_retrieval_preview(conv, "tomorrow plan")
        assert "retrieval preview:" in report
        assert "source audit:" in report
        assert "attached context excerpt:" in report
        assert "Prepare tomorrow plan" in report
        assert "/tmp/tasks.org" in report
        assert "\033[" not in report

        ui = object.__new__(m.MotokoTui)
        ui.conv = conv
        ui.messages = []
        ui.scroll = 0
        ui.dirty = False
        ui.status = "ready"
        ui.generating = False
        ui.maintaining = False
        ui.report_running = 0
        ui.report_status = ""
        ui.report_token = 0
        ui.active_report_token = 0
        ui.overlay_title = None
        ui.overlay_lines = None
        ui.overlay_scroll = 0
        ui.events = m.collections.deque()
        ui.events_lock = threading.Lock()
        ui.handle_command("/retrieval-preview tomorrow plan")

        deadline = time.monotonic() + 2
        while ui.report_running and time.monotonic() < deadline:
            ui.drain_events()
            time.sleep(0.01)
        ui.drain_events()

        assert any("Prepare tomorrow plan" in line for line in ui.overlay_lines or [])
        assert conv["messages"] == []


def test_index_storage_audit_reports_duplicates_and_cleanup_plan(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        content = "same chunk body\n"
        digest = m.sha256_hex(content.encode("utf-8"))
        relpath = m.chunk_content_relpath("old-index", 1, 1)
        chunk_path = m.indexes_dir() / relpath
        m.ensure_private_dir(chunk_path.parent)
        m.atomic_write(chunk_path, content)
        m.atomic_write(chunk_path.parent / "999999-999999.txt", "orphan\n")
        old_index = {
            "id": "old-index",
            "name": "docs",
            "root": str(docs),
            "glob": m.AUTO_INDEX_GLOB,
            "created": "2026-05-21T10:00:00+00:00",
            "files": [
                {
                    "path": str(docs / "a.org"),
                    "chunks": [
                        {
                            "id": "1.1",
                            "chunk": 1,
                            "content_path": relpath,
                            "content_sha256": digest,
                            "content_bytes": len(content.encode("utf-8")),
                            "stored_content_bytes": len(content.encode("utf-8")),
                        }
                    ],
                }
            ],
        }
        new_index = {
            "id": "new-index",
            "name": "docs",
            "root": str(docs),
            "glob": m.AUTO_INDEX_GLOB,
            "created": "2026-05-21T11:00:00+00:00",
            "files": [
                {
                    "path": str(docs / "b.org"),
                    "chunks": [
                        {
                            "id": "1.1",
                            "chunk": 1,
                            "duplicate_of_existing_index": True,
                            "content_sha256": digest,
                            "content_bytes": len(content.encode("utf-8")),
                            "stored_content_bytes": 0,
                        }
                    ],
                }
            ],
        }
        partial = {
            "id": "partial-old",
            "name": "docs",
            "root": str(docs),
            "glob": m.AUTO_INDEX_GLOB,
            "created": "2026-05-21T09:00:00+00:00",
            "status": "failed",
            "files": [],
        }
        m.atomic_write(m.index_path("old-index"), json.dumps(old_index, ensure_ascii=False) + "\n")
        m.atomic_write(m.index_path("new-index"), json.dumps(new_index, ensure_ascii=False) + "\n")
        m.atomic_write(m.index_partial_path("partial-old"), json.dumps(partial, ensure_ascii=False) + "\n")

        audit = m.index_storage_audit()
        assert audit["index_count"] == 2
        assert audit["older_complete_indexes"] == 1
        assert audit["superseded_partial_count"] == 1
        assert audit["duplicate_reference_chunks"] == 1
        assert audit["missing_duplicate_target_count"] == 0
        assert audit["estimated_dedup_saved_bytes"] == len(content.encode("utf-8"))
        assert audit["orphan_chunk_file_count"] == 1
        assert any(item["kind"] == "superseded-partials" for item in audit["safe_cleanup"])
        assert any(item["kind"] == "orphan-chunk-files" for item in audit["safe_cleanup"])
        assert any(item["kind"] == "older-complete-indexes" for item in audit["blocked_cleanup"])
        text = m.format_index_storage_audit(audit)
        assert "index storage audit:" in text
        assert "duplicate reference(s)" in text
        assert "safe cleanup plan:" in text


def test_index_cleanup_removes_stale_superseded_snapshots_after_materializing_latest(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        a_path = docs / "a.org"
        b_path = docs / "b.org"
        a_path.write_text("* TODO Old project\n", encoding="utf-8")
        b_path.write_text("* TODO Shared stable note\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        try:
            m.quiet_model = lambda *args, **kwargs: "summary"
            first = m.build_document_index(str(docs), name="docs")
            first["created"] = "2026-05-22T00:00:00+00:00"
            m.atomic_write(m.index_path(first["id"]), json.dumps(first, ensure_ascii=False, indent=2) + "\n")

            a_path.write_text("* TODO New project\n", encoding="utf-8")
            second = m.build_document_index(str(docs), name="docs")
            second["created"] = "2026-05-22T00:01:00+00:00"
            m.atomic_write(m.index_path(second["id"]), json.dumps(second, ensure_ascii=False, indent=2) + "\n")
        finally:
            m.quiet_model = old_quiet_model

        latest_before = m.load_index_exact(second["id"])
        assert any(
            chunk.get("duplicate_of_existing_index")
            for file_item in latest_before.get("files", [])
            for chunk in file_item.get("chunks", [])
        )
        m.atomic_write(
            m.vector_store_path("vec-old"),
            json.dumps({"id": "vec-old", "source_index": {"id": first["id"]}}, ensure_ascii=False) + "\n",
        )
        m.atomic_write(
            m.evidence_store_path("ev-old"),
            json.dumps({"id": "ev-old", "source_index": {"id": first["id"]}}, ensure_ascii=False) + "\n",
        )

        dry_run = m.cleanup_superseded_stale_indexes(limit=1, dry_run=True)
        assert dry_run["candidate_count"] == 1
        assert dry_run["deleted"][0]["status"] == "candidate"
        assert m.index_path(first["id"]).exists()

        report = m.cleanup_superseded_stale_indexes(limit=1)

        assert report["deleted"][0]["index"] == first["id"]
        assert report["deleted"][0]["vector_stores_deleted"] == 1
        assert report["deleted"][0]["evidence_stores_deleted"] == 1
        assert not m.index_path(first["id"]).exists()
        assert not (m.indexes_dir() / f"{first['id']}.chunks").exists()
        assert not m.vector_store_path("vec-old").exists()
        assert not m.evidence_store_path("ev-old").exists()
        latest_after = m.load_index_exact(second["id"])
        assert not m.index_artifact_warnings(latest_after)
        assert not any(
            chunk.get("duplicate_of_existing_index")
            for file_item in latest_after.get("files", [])
            for chunk in file_item.get("chunks", [])
        )


def test_vector_plan_reports_storage_and_readiness_gates(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        content = "* TODO [#A] Finish vector readiness plan\nDEADLINE: <2026-05-22 Fri>\n"
        (docs / "tasks.org").write_text(content, encoding="utf-8")
        digest = m.sha256_hex(content.encode("utf-8"))
        index = {
            "id": "vector-index",
            "name": "docs",
            "root": str(docs),
            "glob": m.AUTO_INDEX_GLOB,
            "created": "2026-05-21T10:00:00+00:00",
            "corpus_summary": "Vector readiness test corpus.",
            "files": [
                {
                    "path": str(docs / "tasks.org"),
                    "source_fingerprint": m.source_fingerprint(docs / "tasks.org"),
                    "summary": "Task file with current priorities.",
                    "chunks": [
                        {
                            "chunk": 1,
                            "summary": "Task to finish the vector readiness plan.",
                            "content": content,
                            "content_bytes": len(content.encode("utf-8")),
                            "content_sha256": digest,
                        }
                    ],
                }
            ],
        }
        catalog = {
            "realm": "mares",
            "manager": {"kind": "systemd-socket-worker"},
            "routes": {
                "embed-worker": {
                    "endpoint": "unix:///run/motoko-llm/mares/embed-worker.sock",
                    "modelId": "embedding-test",
                    "tasks": ["embedding"],
                },
                "rerank-worker": {
                    "endpoint": "unix:///run/motoko-llm/mares/rerank-worker.sock",
                    "modelId": "reranker-test",
                    "tasks": ["reranker"],
                },
            },
        }
        m.ensure_private_dir(m.config_root())
        m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
        m.atomic_write(m.index_path("vector-index"), json.dumps(index, ensure_ascii=False) + "\n")
        m.atomic_write(
            m.memories_path(),
            json.dumps({"id": "mem-1", "text": "Remember vector readiness.", "created": "2026-05-21T10:01:00+00:00"}, ensure_ascii=False)
            + "\n",
        )
        conv = m.new_conversation("Vector plan")
        conv["id"] = "conv-vector"
        write_conversation(m, conv)

        plan = m.vector_plan(dims=8)
        assert plan["schema"] == m.VECTOR_PLAN_SCHEMA_VERSION
        assert plan["target_vector_schema"] == m.VECTOR_STORE_SCHEMA_VERSION
        assert plan["production_enabled"] is False
        assert plan["source_stats"]["chunk_count"] == 1
        assert plan["estimated_total_bytes"] > 0
        gate_status = {gate["name"]: gate["status"] for gate in plan["gates"]}
        assert gate_status["retrieval_eval"] == "pass"
        assert gate_status["embedding_route"] == "available"
        assert gate_status["reranker_route"] == "available"
        text = m.format_vector_plan(plan)
        assert "vector plan:" in text
        assert "planned stores:" in text
        assert "raw_chunk_embedding" in text
        assert "readiness gates:" in text


def test_vector_build_and_query_lexical_baseline(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        content = "* TODO [#A] Finish vector readiness plan\nDEADLINE: <2026-05-22 Fri>\n"
        (docs / "tasks.org").write_text(content, encoding="utf-8")
        digest = m.sha256_hex(content.encode("utf-8"))
        index = {
            "id": "vector-index",
            "name": "docs",
            "root": str(docs),
            "glob": m.AUTO_INDEX_GLOB,
            "created": "2026-05-21T10:00:00+00:00",
            "corpus_summary": "Vector readiness test corpus.",
            "files": [
                {
                    "path": str(docs / "tasks.org"),
                    "source_fingerprint": m.source_fingerprint(docs / "tasks.org"),
                    "summary": "Task file with current priorities.",
                    "chunks": [
                        {
                            "chunk": 1,
                            "summary": "Task to finish the vector readiness plan.",
                            "content": content,
                            "content_bytes": len(content.encode("utf-8")),
                            "content_sha256": digest,
                        }
                    ],
                }
            ],
        }
        m.atomic_write(m.index_path("vector-index"), json.dumps(index, ensure_ascii=False) + "\n")

        store = m.build_vector_store("vector-index", dims=16)
        assert store["schema"] == m.VECTOR_STORE_SCHEMA_VERSION
        assert store["method"] == m.LEXICAL_VECTOR_METHOD
        assert store["production_embedding"] is False
        assert store["row_count"] >= 2
        assert any(row.get("kind") == "evidence_embedding" for row in store["rows"])
        assert pathlib.Path(store["path"]).exists()
        assert m.vector_store_freshness(store)[0] == "fresh"
        report = m.query_vector_store(store, "finish vector readiness deadline", limit=3)
        assert report["rows"]
        assert report["rows"][0]["path"].endswith("tasks.org")
        assert report["freshness"] == "fresh"
        text = m.format_vector_query_report(report)
        assert "vector query:" in text
        assert "tasks.org" in text
        vector_eval = m.run_vector_eval(dims=64)
        assert vector_eval["schema"] == m.VECTOR_EVAL_SCHEMA_VERSION
        assert vector_eval["status"] == "pass"
        assert "vector eval:" in m.format_vector_eval_report(vector_eval)


def test_embedding_vector_store_uses_catalog_route(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    socket_path = None
    EmbeddingHandler.payloads = []
    EmbeddingHandler.paths = []
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        with isolated_state() as tmp:
            docs = tmp / "docs"
            docs.mkdir()
            content = "* TODO [#A] Finish vector deadline task\nDEADLINE: <2026-05-22 Fri>\n"
            (docs / "tasks.org").write_text(content, encoding="utf-8")
            digest = m.sha256_hex(content.encode("utf-8"))
            index = {
                "id": "embedding-index",
                "name": "docs",
                "root": str(docs),
                "glob": m.AUTO_INDEX_GLOB,
                "created": "2026-05-21T10:00:00+00:00",
                "corpus_summary": "Embedding route test corpus.",
                "files": [
                    {
                        "path": str(docs / "tasks.org"),
                        "source_fingerprint": m.source_fingerprint(docs / "tasks.org"),
                        "summary": "Task file with current priorities.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "Task to finish the vector deadline work.",
                                "content": content,
                                "content_bytes": len(content.encode("utf-8")),
                                "content_sha256": digest,
                            }
                        ],
                    }
                ],
            }
            socket_path = tmp / "embed.sock"
            server = UnixHTTPServer(str(socket_path), EmbeddingHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen3-embedding-0b6": {
                        "kind": "embedding",
                        "endpoint": f"unix://{socket_path}",
                        "modelId": "qwen3-embedding-0.6b-q8-0",
                        "tasks": ["embedding", "vector_index", "vector_query"],
                        "endpoint_paths": ["/v1/embeddings"],
                        "embedding_dimensions": 4,
                        "maxParallel": 4,
                        "openai_compatible": True,
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            m.atomic_write(m.index_path("embedding-index"), json.dumps(index, ensure_ascii=False) + "\n")

            routes = m.local_model_routes_for_capability(
                kind="embedding",
                tasks=m.EMBEDDING_TASKS,
                endpoint_path="/v1/embeddings",
            )
            assert routes[0]["route"] == "qwen3-embedding-0b6"
            assert routes[0]["embedding_dimensions"] == 4
            store = m.build_vector_store("embedding-index", method=m.EMBEDDING_VECTOR_METHOD)
            assert store["method"] == m.EMBEDDING_VECTOR_METHOD
            assert store["production_embedding"] is True
            assert store["dims"] == 4
            assert store["embedding_route"]["catalog_route"] == "qwen3-embedding-0b6"
            assert store["rows"][0]["vector"]
            report = m.query_vector_store(store, "vector deadline task", limit=3)
            assert report["rows"]
            text, sources = m.retrieve_from_index(index, "vector deadline task")
            assert "Hybrid retrieval:" in text
            assert any(source.get("vector_store") == store["id"] for source in sources)
            refresh = m.refresh_vector_stores(
                index_id="embedding-index",
                force=True,
                limit=1,
                method=m.EMBEDDING_VECTOR_METHOD,
            )
            assert refresh["built"] == 1
            assert refresh["items"][0]["store_id"]
            assert EmbeddingHandler.paths
            assert set(EmbeddingHandler.paths) == {"/v1/embeddings"}
            assert EmbeddingHandler.payloads[0]["model"] == "qwen3-embedding-0.6b-q8-0"
            server.shutdown()
            server.server_close()
    finally:
        if socket_path is not None:
            with contextlib.suppress(OSError):
                pathlib.Path(socket_path).unlink()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model


def test_embedding_vector_store_splits_long_chunks_with_parent_mapping(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    old_input_chars = os.environ.get("MOTOKO_EMBEDDING_INPUT_CHARS")
    old_max_parts = os.environ.get("MOTOKO_EMBEDDING_MAX_PARTS_PER_CHUNK")
    old_batch = os.environ.get("MOTOKO_EMBEDDING_BATCH_SIZE")
    EmbeddingHandler.payloads = []
    EmbeddingHandler.paths = []
    server = None
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        os.environ["MOTOKO_EMBEDDING_INPUT_CHARS"] = "700"
        os.environ["MOTOKO_EMBEDDING_MAX_PARTS_PER_CHUNK"] = "6"
        os.environ["MOTOKO_EMBEDDING_BATCH_SIZE"] = "2"
        with isolated_state() as tmp:
            docs = tmp / "docs"
            docs.mkdir()
            content = "alpha start " + ("middle planning context " * 120) + " omega tail deadline"
            path = docs / "long.org"
            path.write_text(content, encoding="utf-8")
            index = {
                "id": "long-embedding-index",
                "name": "docs",
                "root": str(docs),
                "glob": m.AUTO_INDEX_GLOB,
                "created": "2026-05-21T10:00:00+00:00",
                "files": [
                    {
                        "path": str(path),
                        "source_fingerprint": m.source_fingerprint(path),
                        "summary": "Long planning note with a deadline near the tail.",
                        "chunks": [
                            {
                                "chunk": 7,
                                "summary": "Long chunk that must preserve head and tail retrieval evidence.",
                                "content": content,
                                "content_bytes": len(content.encode("utf-8")),
                                "content_sha256": m.sha256_hex(content.encode("utf-8")),
                            }
                        ],
                    }
                ],
            }
            server = ThreadingHTTPServer(("127.0.0.1", 0), EmbeddingHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen3-embedding-0b6": {
                        "kind": "embedding",
                        "endpoint": f"http://127.0.0.1:{server.server_port}/v1/embeddings",
                        "modelId": "qwen3-embedding-0.6b-q8-0",
                        "tasks": ["embedding", "vector_index", "vector_query"],
                        "endpoint_paths": ["/v1/embeddings"],
                        "embedding_dimensions": 4,
                        "maxParallel": 2,
                        "openai_compatible": True,
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            m.atomic_write(m.index_path("long-embedding-index"), json.dumps(index, ensure_ascii=False) + "\n")

            store = m.build_vector_store("long-embedding-index", method=m.EMBEDDING_VECTOR_METHOD)

            payload_inputs = []
            for payload in EmbeddingHandler.payloads:
                inputs = payload.get("input", [])
                payload_inputs.extend(inputs if isinstance(inputs, list) else [inputs])
            assert store["row_count"] > 1
            assert store["embedding_input_schema"] == m.EMBEDDING_INPUT_SCHEMA_VERSION
            assert all(len(str(text)) <= 700 for text in payload_inputs)
            assert any("alpha start" in str(text).lower() for text in payload_inputs)
            assert any("omega tail deadline" in str(text).lower() for text in payload_inputs)
            assert all(row["path"] == str(path) and row["chunk"] == 7 for row in store["rows"])
            raw_rows = [row for row in store["rows"] if row["kind"] == "raw_chunk_embedding"]
            assert raw_rows
            assert all(row["embedding_kind"] == "chunk_content" for row in raw_rows)
            assert max(row["embedding_part"] for row in raw_rows) == len(raw_rows)
            assert any(row["kind"] == "evidence_embedding" for row in store["rows"])
            assert m.vector_store_freshness(store)[0] == "fresh"
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model
        if old_input_chars is None:
            os.environ.pop("MOTOKO_EMBEDDING_INPUT_CHARS", None)
        else:
            os.environ["MOTOKO_EMBEDDING_INPUT_CHARS"] = old_input_chars
        if old_max_parts is None:
            os.environ.pop("MOTOKO_EMBEDDING_MAX_PARTS_PER_CHUNK", None)
        else:
            os.environ["MOTOKO_EMBEDDING_MAX_PARTS_PER_CHUNK"] = old_max_parts
        if old_batch is None:
            os.environ.pop("MOTOKO_EMBEDDING_BATCH_SIZE", None)
        else:
            os.environ["MOTOKO_EMBEDDING_BATCH_SIZE"] = old_batch


def test_embedding_vector_store_parallelizes_batches(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    old_batch = os.environ.get("MOTOKO_EMBEDDING_BATCH_SIZE")
    old_parallel = os.environ.get("MOTOKO_EMBEDDING_PARALLEL")
    SlowEmbeddingHandler.payloads = []
    SlowEmbeddingHandler.paths = []
    SlowEmbeddingHandler.active = 0
    SlowEmbeddingHandler.max_active = 0
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        os.environ["MOTOKO_EMBEDDING_BATCH_SIZE"] = "2"
        os.environ.pop("MOTOKO_EMBEDDING_PARALLEL", None)
        with isolated_state() as tmp:
            docs = tmp / "docs"
            docs.mkdir()
            files = []
            for idx in range(12):
                path = docs / f"note-{idx}.org"
                content = f"* Alpha {idx}\nBeta gamma note {idx}.\n"
                path.write_text(content, encoding="utf-8")
                files.append(
                    {
                        "path": str(path),
                        "source_fingerprint": m.source_fingerprint(path),
                        "summary": f"Alpha note {idx}.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": f"Alpha beta gamma chunk {idx}.",
                                "content": content,
                                "content_sha256": m.sha256_hex(content.encode("utf-8")),
                            }
                        ],
                    }
                )
            index = {
                "id": "parallel-embedding-index",
                "name": "docs",
                "root": str(docs),
                "glob": m.AUTO_INDEX_GLOB,
                "created": "2026-05-21T10:00:00+00:00",
                "corpus_summary": "Parallel embedding route test corpus.",
                "files": files,
            }
            server = ThreadingHTTPServer(("127.0.0.1", 0), SlowEmbeddingHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen3-embedding-0b6": {
                        "kind": "embedding",
                        "endpoint": f"http://127.0.0.1:{server.server_port}/v1/embeddings",
                        "modelId": "qwen3-embedding-0.6b-q8-0",
                        "tasks": ["embedding", "vector_index", "vector_query"],
                        "endpoint_paths": ["/v1/embeddings"],
                        "embedding_dimensions": 4,
                        "maxParallel": 3,
                        "openai_compatible": True,
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            m.atomic_write(m.index_path("parallel-embedding-index"), json.dumps(index, ensure_ascii=False) + "\n")

            store = m.build_vector_store("parallel-embedding-index", method=m.EMBEDDING_VECTOR_METHOD)

            raw_rows = [row for row in store["rows"] if row["kind"] == "raw_chunk_embedding"]
            assert len(raw_rows) == 12
            assert store["row_count"] >= 12
            assert store["embedding_batch_count"] >= 6
            assert store["embedding_parallelism"] == 3
            assert SlowEmbeddingHandler.max_active >= 2
            assert len(SlowEmbeddingHandler.payloads) >= 6
            server.shutdown()
            server.server_close()
    finally:
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model
        if old_batch is None:
            os.environ.pop("MOTOKO_EMBEDDING_BATCH_SIZE", None)
        else:
            os.environ["MOTOKO_EMBEDDING_BATCH_SIZE"] = old_batch
        if old_parallel is None:
            os.environ.pop("MOTOKO_EMBEDDING_PARALLEL", None)
        else:
            os.environ["MOTOKO_EMBEDDING_PARALLEL"] = old_parallel


def test_embedding_parallelism_allows_32_cap(m):
    old_parallel = os.environ.get("MOTOKO_EMBEDDING_PARALLEL")
    old_batch = os.environ.get("MOTOKO_EMBEDDING_BATCH_SIZE")
    old_batches_per_worker = os.environ.get("MOTOKO_EMBEDDING_BATCHES_PER_WORKER")
    try:
        os.environ.pop("MOTOKO_EMBEDDING_PARALLEL", None)
        os.environ.pop("MOTOKO_EMBEDDING_BATCH_SIZE", None)
        os.environ.pop("MOTOKO_EMBEDDING_BATCHES_PER_WORKER", None)
        assert m.embedding_parallelism({"max_parallel": 32}, 64) == 32
        assert m.embedding_parallelism({"max_parallel": 64}, 64) == 32
        assert m.embedding_parallelism({"max_parallel": 32}, 8) == 8
        assert m.embedding_batch_size({"max_parallel": 32}, 138) == 1
        assert m.embedding_batch_size({"max_parallel": 32}, 1000) == 7
        os.environ["MOTOKO_EMBEDDING_PARALLEL"] = "40"
        assert m.embedding_parallelism({"max_parallel": 32}, 64) == 32
        os.environ["MOTOKO_EMBEDDING_PARALLEL"] = "6"
        assert m.embedding_parallelism({"max_parallel": 32}, 64) == 6
        assert m.embedding_batch_size({"max_parallel": 32}, 1000) == 41
        os.environ["MOTOKO_EMBEDDING_PARALLEL"] = "32"
        os.environ["MOTOKO_EMBEDDING_BATCHES_PER_WORKER"] = "2"
        assert m.embedding_batch_size({"max_parallel": 32}, 138) == 2
        os.environ["MOTOKO_EMBEDDING_BATCH_SIZE"] = "9"
        assert m.embedding_batch_size({"max_parallel": 32}, 138) == 9
    finally:
        if old_parallel is None:
            os.environ.pop("MOTOKO_EMBEDDING_PARALLEL", None)
        else:
            os.environ["MOTOKO_EMBEDDING_PARALLEL"] = old_parallel
        if old_batch is None:
            os.environ.pop("MOTOKO_EMBEDDING_BATCH_SIZE", None)
        else:
            os.environ["MOTOKO_EMBEDDING_BATCH_SIZE"] = old_batch
        if old_batches_per_worker is None:
            os.environ.pop("MOTOKO_EMBEDDING_BATCHES_PER_WORKER", None)
        else:
            os.environ["MOTOKO_EMBEDDING_BATCHES_PER_WORKER"] = old_batches_per_worker


def test_embedding_vector_store_stale_when_route_model_changes(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    EmbeddingHandler.payloads = []
    EmbeddingHandler.paths = []
    server = None
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        with isolated_state() as tmp:
            docs = tmp / "docs"
            docs.mkdir()
            content = "* TODO Refresh vectors\n"
            path = docs / "tasks.org"
            path.write_text(content, encoding="utf-8")
            index = {
                "id": "embedding-stale-index",
                "name": "docs",
                "root": str(docs),
                "glob": m.AUTO_INDEX_GLOB,
                "created": "2026-05-21T10:00:00+00:00",
                "files": [
                    {
                        "path": str(path),
                        "source_fingerprint": m.source_fingerprint(path),
                        "summary": "Task file.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "Refresh vector store task.",
                                "content": content,
                                "content_sha256": m.sha256_hex(content.encode("utf-8")),
                            }
                        ],
                    }
                ],
            }
            server = ThreadingHTTPServer(("127.0.0.1", 0), EmbeddingHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def write_catalog(model_id: str, dims: int = 4) -> None:
                catalog = {
                    "realm": "mares",
                    "manager": {"kind": "systemd-socket-worker"},
                    "routes": {
                        "qwen3-embedding-0b6": {
                            "kind": "embedding",
                            "endpoint": f"http://127.0.0.1:{server.server_port}/v1/embeddings",
                            "modelId": model_id,
                            "tasks": ["embedding", "vector_index", "vector_query"],
                            "endpoint_paths": ["/v1/embeddings"],
                            "embedding_dimensions": dims,
                            "maxParallel": 2,
                            "openai_compatible": True,
                        }
                    },
                }
                m.ensure_private_dir(m.config_root())
                m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")

            write_catalog("qwen3-embedding-0.6b-q8-0")
            m.atomic_write(m.index_path("embedding-stale-index"), json.dumps(index, ensure_ascii=False) + "\n")
            store = m.build_vector_store("embedding-stale-index", method=m.EMBEDDING_VECTOR_METHOD)
            assert m.vector_store_freshness(store)[0] == "fresh"

            write_catalog("qwen3-embedding-0.6b-q6-k")
            status, warnings = m.vector_store_freshness(store)
            assert status == "stale"
            assert any("embedding model changed" in warning for warning in warnings)

            write_catalog("qwen3-embedding-0.6b-q6-k", dims=8)
            store["embedding_route"]["model"] = "qwen3-embedding-0.6b-q6-k"
            status, warnings = m.vector_store_freshness(store)
            assert status == "stale"
            assert any("dimensions" in warning for warning in warnings)
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model


def test_embedding_vector_store_resumes_saved_progress(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    old_batch = os.environ.get("MOTOKO_EMBEDDING_BATCH_SIZE")
    old_parallel = os.environ.get("MOTOKO_EMBEDDING_PARALLEL")
    EmbeddingHandler.payloads = []
    EmbeddingHandler.paths = []
    server = None
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        os.environ["MOTOKO_EMBEDDING_BATCH_SIZE"] = "1"
        os.environ["MOTOKO_EMBEDDING_PARALLEL"] = "1"
        with isolated_state() as tmp:
            docs = tmp / "docs"
            docs.mkdir()
            files = []
            for idx in range(3):
                path = docs / f"task-{idx}.org"
                content = f"* TODO Vector task {idx}\n"
                path.write_text(content, encoding="utf-8")
                files.append(
                    {
                        "path": str(path),
                        "source_fingerprint": m.source_fingerprint(path),
                        "summary": f"Vector task {idx}.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": f"Vector task chunk {idx}.",
                                "content": content,
                                "content_sha256": m.sha256_hex(content.encode("utf-8")),
                            }
                        ],
                    }
                )
            index = {
                "id": "resume-vector-index",
                "name": "docs",
                "root": str(docs),
                "glob": m.AUTO_INDEX_GLOB,
                "created": "2026-05-21T10:00:00+00:00",
                "files": files,
            }
            server = ThreadingHTTPServer(("127.0.0.1", 0), EmbeddingHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen3-embedding-0b6": {
                        "kind": "embedding",
                        "endpoint": f"http://127.0.0.1:{server.server_port}/v1/embeddings",
                        "modelId": "qwen3-embedding-0.6b-q8-0",
                        "tasks": ["embedding", "vector_index", "vector_query"],
                        "endpoint_paths": ["/v1/embeddings"],
                        "embedding_dimensions": 4,
                        "maxParallel": 1,
                        "openai_compatible": True,
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            m.atomic_write(m.index_path("resume-vector-index"), json.dumps(index, ensure_ascii=False) + "\n")

            paused = {"requested": False}
            progress_messages = []

            def pause_after_first_batch(message: str) -> None:
                progress_messages.append(message)
                if not paused["requested"]:
                    paused["requested"] = True
                    m.request_work_pause("test")

            try:
                m.build_vector_store_from_index(
                    index,
                    method=m.EMBEDDING_VECTOR_METHOD,
                    progress_callback=pause_after_first_batch,
                )
                raise AssertionError("expected vector build to pause")
            except m.WorkPaused:
                pass

            progress_files = list(m.vector_progress_dir().glob("*.json"))
            assert len(progress_files) == 1
            progress = json.loads(progress_files[0].read_text(encoding="utf-8"))
            assert progress["completed_rows"] == 1
            assert "eta_seconds" in progress
            assert any("eta" in message for message in progress_messages)

            store = m.build_vector_store("resume-vector-index", method=m.EMBEDDING_VECTOR_METHOD)
            raw_rows = [row for row in store["rows"] if row["kind"] == "raw_chunk_embedding"]
            assert len(raw_rows) == 3
            assert store["row_count"] >= 3
            assert len(EmbeddingHandler.payloads) >= 3
            assert list(m.vector_progress_dir().glob("*.json")) == []
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model
        if old_batch is None:
            os.environ.pop("MOTOKO_EMBEDDING_BATCH_SIZE", None)
        else:
            os.environ["MOTOKO_EMBEDDING_BATCH_SIZE"] = old_batch
        if old_parallel is None:
            os.environ.pop("MOTOKO_EMBEDDING_PARALLEL", None)
        else:
            os.environ["MOTOKO_EMBEDDING_PARALLEL"] = old_parallel


def test_embedding_vector_store_falls_back_from_excess_parallelism(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    old_batch = os.environ.get("MOTOKO_EMBEDDING_BATCH_SIZE")
    old_parallel = os.environ.get("MOTOKO_EMBEDDING_PARALLEL")
    ThrottledEmbeddingHandler.payloads = []
    ThrottledEmbeddingHandler.paths = []
    ThrottledEmbeddingHandler.active = 0
    ThrottledEmbeddingHandler.failures = 0
    ThrottledEmbeddingHandler.max_active = 0
    server = None
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        os.environ["MOTOKO_EMBEDDING_BATCH_SIZE"] = "1"
        os.environ["MOTOKO_EMBEDDING_PARALLEL"] = "4"
        with isolated_state() as tmp:
            docs = tmp / "docs"
            docs.mkdir()
            files = []
            for idx in range(8):
                path = docs / f"fallback-{idx}.org"
                content = f"* TODO Vector fallback task {idx}\n"
                path.write_text(content, encoding="utf-8")
                files.append(
                    {
                        "path": str(path),
                        "source_fingerprint": m.source_fingerprint(path),
                        "summary": f"Vector fallback task {idx}.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": f"Vector fallback task chunk {idx}.",
                                "content": content,
                                "content_sha256": m.sha256_hex(content.encode("utf-8")),
                            }
                        ],
                    }
                )
            index = {
                "id": "fallback-vector-index",
                "name": "docs",
                "root": str(docs),
                "glob": m.AUTO_INDEX_GLOB,
                "created": "2026-05-21T10:00:00+00:00",
                "files": files,
            }
            server = ThreadingHTTPServer(("127.0.0.1", 0), ThrottledEmbeddingHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen3-embedding-0b6": {
                        "kind": "embedding",
                        "endpoint": f"http://127.0.0.1:{server.server_port}/v1/embeddings",
                        "modelId": "qwen3-embedding-0.6b-q8-0",
                        "tasks": ["embedding", "vector_index", "vector_query"],
                        "endpoint_paths": ["/v1/embeddings"],
                        "embedding_dimensions": 4,
                        "maxParallel": 4,
                        "openai_compatible": True,
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            m.atomic_write(m.index_path("fallback-vector-index"), json.dumps(index, ensure_ascii=False) + "\n")

            store = m.build_vector_store("fallback-vector-index", method=m.EMBEDDING_VECTOR_METHOD)

            raw_rows = [row for row in store["rows"] if row["kind"] == "raw_chunk_embedding"]
            assert len(raw_rows) == 8
            assert store["row_count"] >= 8
            assert store["embedding_requested_parallelism"] == 4
            assert store["embedding_parallelism"] == 2
            assert len(store["embedding_parallel_fallbacks"]) == 1
            assert ThrottledEmbeddingHandler.failures >= 1
            assert len(ThrottledEmbeddingHandler.payloads) > len(raw_rows)
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model
        if old_batch is None:
            os.environ.pop("MOTOKO_EMBEDDING_BATCH_SIZE", None)
        else:
            os.environ["MOTOKO_EMBEDDING_BATCH_SIZE"] = old_batch
        if old_parallel is None:
            os.environ.pop("MOTOKO_EMBEDDING_PARALLEL", None)
        else:
            os.environ["MOTOKO_EMBEDDING_PARALLEL"] = old_parallel


def test_vector_query_can_use_catalog_reranker_route(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    socket_path = None
    RerankHandler.payloads = []
    RerankHandler.paths = []
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        with isolated_state() as tmp:
            docs = tmp / "docs"
            docs.mkdir()
            first = "* Notes\nAlpha notes about errands.\n"
            second = "* TODO [#A] Priority deadline task\nDEADLINE: <2026-05-22 Fri>\nAlpha notes.\n"
            first_path = docs / "notes.org"
            second_path = docs / "priority.org"
            first_path.write_text(first, encoding="utf-8")
            second_path.write_text(second, encoding="utf-8")
            index = {
                "id": "rerank-index",
                "name": "docs",
                "root": str(docs),
                "glob": m.AUTO_INDEX_GLOB,
                "created": "2026-05-21T10:00:00+00:00",
                "corpus_summary": "Rerank route test corpus.",
                "files": [
                    {
                        "path": str(first_path),
                        "source_fingerprint": m.source_fingerprint(first_path),
                        "summary": "General alpha notes.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "General alpha notes.",
                                "content": first,
                                "content_sha256": m.sha256_hex(first.encode("utf-8")),
                            }
                        ],
                    },
                    {
                        "path": str(second_path),
                        "source_fingerprint": m.source_fingerprint(second_path),
                        "summary": "Priority deadline task notes.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "Priority deadline task.",
                                "content": second,
                                "content_sha256": m.sha256_hex(second.encode("utf-8")),
                            }
                        ],
                    },
                ],
            }
            socket_path = tmp / "rerank.sock"
            server = UnixHTTPServer(str(socket_path), RerankHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen3-reranker-0b6": {
                        "kind": "reranker",
                        "endpoint": f"unix://{socket_path}",
                        "modelId": "qwen3-reranker-0.6b-q6-k",
                        "tasks": ["reranker", "rerank", "vector_rerank"],
                        "endpoint_paths": ["/v1/rerank"],
                        "maxParallel": 4,
                        "openai_compatible": True,
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            m.atomic_write(m.index_path("rerank-index"), json.dumps(index, ensure_ascii=False) + "\n")
            store = m.build_vector_store_from_index(index, method=m.LEXICAL_VECTOR_METHOD, write=False)

            report = m.query_vector_store(store, "alpha notes", limit=2, rerank=True)
            assert report["rerank"] is True
            assert report["rerank_route"]["catalog_route"] == "qwen3-reranker-0b6"
            assert report["rows"][0]["path"].endswith("priority.org")
            assert report["rows"][0]["rerank_score"] == 0.95
            assert RerankHandler.paths == ["/v1/rerank"]
            assert RerankHandler.payloads[0]["model"] == "qwen3-reranker-0.6b-q6-k"
            assert len(RerankHandler.payloads[0]["documents"]) == 2
            server.shutdown()
            server.server_close()
    finally:
        if socket_path is not None:
            with contextlib.suppress(OSError):
                pathlib.Path(socket_path).unlink()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model


def test_normal_retrieval_uses_embedding_rerank_by_default(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    old_rerank = os.environ.get("MOTOKO_VECTOR_RERANK")
    embed_socket = None
    rerank_socket = None
    EmbeddingHandler.payloads = []
    EmbeddingHandler.paths = []
    RerankHandler.payloads = []
    RerankHandler.paths = []
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        os.environ.pop("MOTOKO_VECTOR_RERANK", None)
        with isolated_state() as tmp:
            docs = tmp / "docs"
            docs.mkdir()
            first = "* Notes\nAlpha notes about errands.\n"
            second = "* TODO [#A] Priority deadline task\nDEADLINE: <2026-05-22 Fri>\nAlpha notes.\n"
            first_path = docs / "notes.org"
            second_path = docs / "priority.org"
            first_path.write_text(first, encoding="utf-8")
            second_path.write_text(second, encoding="utf-8")
            index = {
                "id": "default-rerank-index",
                "name": "docs",
                "root": str(docs),
                "glob": m.AUTO_INDEX_GLOB,
                "created": "2026-05-21T10:00:00+00:00",
                "corpus_summary": "Default rerank route test corpus.",
                "files": [
                    {
                        "path": str(first_path),
                        "source_fingerprint": m.source_fingerprint(first_path),
                        "summary": "General alpha notes.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "General alpha notes.",
                                "content": first,
                                "content_sha256": m.sha256_hex(first.encode("utf-8")),
                            }
                        ],
                    },
                    {
                        "path": str(second_path),
                        "source_fingerprint": m.source_fingerprint(second_path),
                        "summary": "Priority deadline task notes.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "Priority deadline task.",
                                "content": second,
                                "content_sha256": m.sha256_hex(second.encode("utf-8")),
                            }
                        ],
                    },
                ],
            }
            embed_socket = tmp / "embed.sock"
            embed_server = UnixHTTPServer(str(embed_socket), EmbeddingHandler)
            embed_thread = threading.Thread(target=embed_server.serve_forever, daemon=True)
            embed_thread.start()
            rerank_socket = tmp / "rerank.sock"
            rerank_server = UnixHTTPServer(str(rerank_socket), RerankHandler)
            rerank_thread = threading.Thread(target=rerank_server.serve_forever, daemon=True)
            rerank_thread.start()
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen3-embedding-0b6": {
                        "kind": "embedding",
                        "endpoint": f"unix://{embed_socket}",
                        "modelId": "qwen3-embedding-0.6b-q8-0",
                        "tasks": ["embedding", "vector_index", "vector_query"],
                        "endpoint_paths": ["/v1/embeddings"],
                        "embedding_dimensions": 4,
                        "maxParallel": 4,
                        "openai_compatible": True,
                    },
                    "qwen3-reranker-0b6": {
                        "kind": "reranker",
                        "endpoint": f"unix://{rerank_socket}",
                        "modelId": "qwen3-reranker-0.6b-q6-k",
                        "tasks": ["reranker", "rerank", "vector_rerank"],
                        "endpoint_paths": ["/v1/rerank"],
                        "maxParallel": 4,
                        "openai_compatible": True,
                    },
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            m.atomic_write(m.index_path("default-rerank-index"), json.dumps(index, ensure_ascii=False) + "\n")
            store = m.build_vector_store("default-rerank-index", method=m.EMBEDDING_VECTOR_METHOD)

            text, sources = m.retrieve_from_index(index, "alpha notes")
            assert "Hybrid retrieval:" in text
            assert RerankHandler.paths
            assert set(RerankHandler.paths) == {"/v1/rerank"}
            index_source = next(source for source in sources if source.get("kind") == "index")
            assert index_source["vector_store"] == store["id"]
            assert index_source["hybrid_rerank_route"] == "qwen3-reranker-0b6"
            assert not index_source.get("hybrid_rerank_fallback")
            chunk_sources = [source for source in sources if source.get("kind") == "chunk"]
            assert chunk_sources[0]["path"].endswith("priority.org")
            assert "lexical" in chunk_sources[0]["retrieval_methods"]
            assert "vector" in chunk_sources[0]["retrieval_methods"]
            assert chunk_sources[0]["rerank_score"] == 0.95
            embed_server.shutdown()
            embed_server.server_close()
            rerank_server.shutdown()
            rerank_server.server_close()
    finally:
        for socket_path in (embed_socket, rerank_socket):
            if socket_path is not None:
                with contextlib.suppress(OSError):
                    pathlib.Path(socket_path).unlink()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model
        if old_rerank is None:
            os.environ.pop("MOTOKO_VECTOR_RERANK", None)
        else:
            os.environ["MOTOKO_VECTOR_RERANK"] = old_rerank


def test_index_limits(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "a.txt").write_text("alpha\n", encoding="utf-8")
        (docs / "b.txt").write_text("bravo\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))
        config = m.load_config()
        config["index"]["max_files"] = 1
        m.save_config(config)
        try:
            m.plan_document_index(str(docs))
        except SystemExit as exc:
            assert "candidate count" in str(exc)
        else:
            raise AssertionError("max_files should block oversized indexes")

        config["index"]["max_files"] = 10
        config["index"]["max_file_bytes"] = "4B"
        m.save_config(config)
        try:
            m.plan_document_index(str(docs))
        except SystemExit as exc:
            assert "index.max_file_bytes" in str(exc)
        else:
            raise AssertionError("max_file_bytes should block oversized files")


def test_index_progress_state(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "plan.org").write_text("* TODO Plan tomorrow\n", encoding="utf-8")
        (docs / "notes.txt").write_text("alpha\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        try:
            m.quiet_model = lambda *args, **kwargs: "summary"
            events = []
            index = m.build_document_index(str(docs), progress_callback=events.append)
            assert index["id"]
            assert any(event.get("phase") == "summarizing chunk" for event in events)
            assert any(event.get("phase") == "summarizing file" for event in events)
            assert events[-1]["status"] == "completed"
            progress = m.read_index_progress(index["id"])
            assert progress is not None
            assert progress["status"] == "completed"
            assert progress["completed_files"] == 2
            assert progress["completed_model_calls"] >= 5
            assert progress["percent"] == 100
            assert "active index jobs: 0" in m.format_status()
        finally:
            m.quiet_model = old_quiet_model


def test_index_progress_eta_tracks_model_timing(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        first = docs / "a.txt"
        first.write_text("alpha\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))
        progress = m.begin_index_progress("idx", docs, m.AUTO_INDEX_GLOB, "docs", [first])
        assert progress["estimated_model_calls"] == 3

        m.index_progress_begin_model(progress, "summarizing chunk", "a chunk")
        progress["_current_model_started_monotonic"] = m.time.monotonic() - 12
        m.update_index_progress_estimates(progress)
        assert progress["current_model_elapsed_seconds"] >= 11
        assert "call " in m.format_index_progress_status(progress)

        m.index_progress_finish_model(progress)
        assert progress["completed_model_calls"] == 1
        assert progress["completed_model_seconds"] >= 11
        assert progress["average_model_call_seconds"] >= 11
        assert "completed model-call timing" == progress["eta_basis"]


def test_summary_block_estimates_expand_progress_total(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        first = docs / "big.txt"
        first.write_text("alpha\n", encoding="utf-8")
        progress = m.begin_index_progress("idx", docs, m.AUTO_INDEX_GLOB, "docs", [first])
        before = progress["estimated_model_calls"]
        blocks = ["x" * m.SUMMARY_INPUT_CHARS for _idx in range(4)]
        expected = m.estimate_summary_block_calls(blocks)
        assert expected > 1
        m.index_progress_reserve_model_calls(
            progress,
            "summarizing file:big",
            expected,
            preplanned_calls=1,
        )
        assert progress["estimated_model_calls"] == before + expected - 1


def test_list_indexes_ignores_progress_files(m):
    with isolated_state():
        index = {
            "id": "idx",
            "name": "docs",
            "root": "/tmp/docs",
            "glob": m.AUTO_INDEX_GLOB,
            "created": m.now(),
            "corpus_summary": "",
            "files": [],
        }
        m.atomic_write(m.index_path("idx"), json.dumps(index, ensure_ascii=False, indent=2) + "\n")
        m.write_index_progress({"id": "idx", "status": "running", "phase": "summarizing chunk"})
        m.write_partial_index(index, status="failed", error="timeout")
        rows = m.list_indexes()
        assert len(rows) == 1
        assert rows[0]["id"] == "idx"
        assert "phase" not in rows[0]


def test_superseded_partials_do_not_look_unfinished(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        source = docs / "tasks.org"
        source.write_text("* TODO Fresh task\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))
        partial = {
            "id": "old-partial",
            "name": "docs",
            "root": str(docs.resolve()),
            "glob": m.AUTO_INDEX_GLOB,
            "created": "2026-05-21T12:00:00+00:00",
            "updated": "2026-05-21T12:30:00+00:00",
            "status": "failed",
            "completed_files": 1,
            "total_files": 1,
            "files": [
                {
                    "path": str(source.resolve()),
                    "source_fingerprint": m.source_fingerprint(source),
                    "chunks": [],
                }
            ],
        }
        index = dict(partial)
        index["id"] = "new-complete"
        index["created"] = "2026-05-21T13:00:00+00:00"
        index.pop("updated", None)
        index.pop("status", None)
        m.atomic_write(m.index_partial_path(partial["id"]), json.dumps(partial, ensure_ascii=False, indent=2) + "\n")
        m.atomic_write(m.index_path(index["id"]), json.dumps(index, ensure_ascii=False, indent=2) + "\n")

        assert [row["id"] for row in m.list_partial_indexes()] == ["old-partial"]
        assert [row["id"] for row in m.list_superseded_partial_indexes()] == ["old-partial"]
        assert m.list_resumable_partial_indexes() == []
        assert m.unfinished_work_notice() == ""
        assert m.completion_ids("partial-index") == []
        assert m.select_partial_index("old-partial")["id"] == "old-partial"


def test_context_catalog_prefers_latest_index_per_family(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        source = docs / "logbook.org"
        source.write_text("* TODO Fresh logbook task\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))
        base = {
            "name": "docs",
            "root": str(docs.resolve()),
            "glob": m.AUTO_INDEX_GLOB,
            "files": [
                {
                    "path": str(source.resolve()),
                    "source_fingerprint": m.source_fingerprint(source),
                    "chunks": [],
                }
            ],
        }
        old_index = {
            **base,
            "id": "old-index",
            "created": "2026-05-21T12:00:00+00:00",
            "corpus_summary": "old stale logbook map",
        }
        new_index = {
            **base,
            "id": "new-index",
            "created": "2026-05-21T13:00:00+00:00",
            "corpus_summary": "new fresh logbook map",
        }
        m.atomic_write(m.index_path(old_index["id"]), json.dumps(old_index, ensure_ascii=False, indent=2) + "\n")
        m.atomic_write(m.index_path(new_index["id"]), json.dumps(new_index, ensure_ascii=False, indent=2) + "\n")

        catalog = m.build_context_catalog()
        catalog_ids = [row["id"] for row in catalog["indexes"]]
        assert "new-index" in catalog_ids
        assert "old-index" not in catalog_ids
        ranked = m.ranked_indexes_for_query("logbook")
        assert [row["id"] for row in ranked] == ["new-index"]


def test_index_resume_after_model_timeout(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "a.org").write_text("* TODO Alpha\n", encoding="utf-8")
        (docs / "b.org").write_text("* TODO Bravo\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        try:
            def flaky_model(messages, **_kwargs):
                prompt = messages[-1]["content"]
                if "b.org chunk 1" in prompt:
                    raise SystemExit("model request failed: timed out")
                return "summary"

            m.quiet_model = flaky_model
            try:
                m.build_document_index(str(docs))
            except SystemExit as exc:
                assert "timed out" in str(exc)
            else:
                raise AssertionError("index build should fail on the simulated timeout")

            partials = m.list_partial_indexes()
            assert len(partials) == 1
            partial = partials[0]
            assert partial["status"] == "failed"
            assert partial["completed_files"] == 1
            assert partial["total_files"] == 2
            assert m.index_partial_path(partial["id"]).exists()
            assert m.index_data_dir(partial["id"]).exists()
            assert not m.index_path(partial["id"]).exists()

            buf = m.io.StringIO()
            with contextlib.redirect_stdout(buf):
                m.command_indexes_text()
            listing = buf.getvalue()
            assert "partial" in listing
            assert f"motoko index-resume {partial['id']}" in listing

            m.quiet_model = lambda *args, **kwargs: "summary"
            index = m.resume_document_index(partial["id"])
            assert index["id"] == partial["id"]
            assert len(index["files"]) == 2
            assert any(file_item["path"].endswith("b.org") for file_item in index["files"])
            assert m.index_path(index["id"]).exists()
            assert not m.index_partial_path(index["id"]).exists()
        finally:
            m.quiet_model = old_quiet_model


def test_index_pause_resume_rescans_new_files_without_overwriting_chunks(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "a.org").write_text("* TODO Alpha\nalpha body\n", encoding="utf-8")
        (docs / "b.org").write_text("* TODO Bravo\nbravo body\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        try:
            pause_requested = {"done": False}

            def pausing_model(messages, **_kwargs):
                prompt = messages[-1]["content"]
                if (
                    "Create a file-level summary" in prompt
                    and "b.org" in prompt
                    and not pause_requested["done"]
                ):
                    pause_requested["done"] = True
                    m.request_work_pause("test")
                return "summary"

            m.quiet_model = pausing_model
            try:
                m.build_document_index(str(docs))
            except m.WorkPaused as exc:
                partial_id = exc.work_id
            else:
                raise AssertionError("index build should pause at a durable checkpoint")

            partial = m.load_partial_index(partial_id)
            assert partial["status"] == "paused"
            assert partial["completed_files"] == 2
            (docs / "aa.org").write_text("* TODO Inserted\ninserted body\n", encoding="utf-8")

            m.quiet_model = lambda *args, **kwargs: "summary"
            index = m.resume_document_index(partial_id)
            assert len(index["files"]) == 3
            paths = [pathlib.Path(item["path"]).name for item in index["files"]]
            assert set(paths) == {"a.org", "aa.org", "b.org"}
            b_item = next(item for item in index["files"] if item["path"].endswith("b.org"))
            b_text = m.read_chunk_content(index, b_item["chunks"][0])
            assert "bravo body" in b_text
            aa_item = next(item for item in index["files"] if item["path"].endswith("aa.org"))
            aa_text = m.read_chunk_content(index, aa_item["chunks"][0])
            assert "inserted body" in aa_text
        finally:
            m.clear_work_pause_request()
            m.quiet_model = old_quiet_model


def test_org_task_signals_drive_retrieval(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        tasks = docs / "tasks.org"
        tasks.write_text(
            "\n".join(
                [
                    "* TODO [#A] Prepare tomorrow plan :work:",
                    "DEADLINE: <2026-05-19 Tue>",
                    "Details about the highest priority task.",
                    "* DONE Archive old note",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (docs / "ideas.org").write_text("* Idea unrelated\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        try:
            m.quiet_model = lambda *args, **kwargs: "summary"
            index = m.build_document_index(str(docs))
            assert index["signals"]["active_task_count"] == 1
            assert index["signals"]["done_task_count"] == 1
            assert index["signals"]["priorities"]["A"] == 1
            assert index["signals"]["task_items"][0]["deadline_date"] == "2026-05-19"
            assert "Prepare tomorrow plan" in index["signal_summary"]
            assert index["corpus_profile_schema"] == m.CORPUS_PROFILE_SCHEMA_VERSION
            assert index["corpus_profile"]["role_counts"].get("planning") == 1
            assert "Prepare tomorrow plan" in index["corpus_profile_text"]
            assert not m.index_needs_artifact_upgrade(index)
            assert index["corpus_summary_artifact"]["route"] == m.MODEL_ROUTE_INDEX_CORPUS
            first_file = index["files"][0]
            assert first_file["summary_artifact"]["route"] == m.MODEL_ROUTE_INDEX_FILE
            assert first_file["chunks"][0]["summary_artifact"]["route"] == m.MODEL_ROUTE_INDEX_CHUNK
            quality = m.index_quality_gate(index)
            assert quality["status"] == "pass", m.format_index_quality_gate(quality)

            text, sources = m.retrieve_from_index(index, "highest priority tasks for 2026-05-19")
            assert "Corpus profile:" in text
            assert "Ranked task candidates:" in text
            assert "Structured task signals:" in text
            assert "Prepare tomorrow plan" in text
            assert any(source.get("corpus_profile_schema") == m.CORPUS_PROFILE_SCHEMA_VERSION for source in sources)
            assert any(source.get("kind") == "chunk" for source in sources)

            conv = m.new_conversation("Tasks")
            conv["context_items"] = [m.context_item_from_index(index)]
            task_view = m.format_task_candidates_from_chat(conv, "priority tasks for 2026-05-19")
            assert "Task candidates for:" in task_view
            assert "Prepare tomorrow plan" in task_view
            args = type("Args", (), {"index": [index["id"]], "query": ["priority", "tasks"]})()
            buf = m.io.StringIO()
            with contextlib.redirect_stdout(buf):
                m.command_tasks(args)
            assert "Prepare tomorrow plan" in buf.getvalue()
            args = type("Args", (), {"index": index["id"], "refresh": False})()
            buf = m.io.StringIO()
            with contextlib.redirect_stdout(buf):
                m.command_corpus_profile(args)
            profile_output = buf.getvalue()
            assert m.CORPUS_PROFILE_SCHEMA_VERSION in profile_output
            assert "Prepare tomorrow plan" in profile_output
            args = type("Args", (), {"index": index["id"]})()
            buf = m.io.StringIO()
            with contextlib.redirect_stdout(buf):
                m.command_index_quality(args)
            assert "index quality: pass" in m.strip_ansi(buf.getvalue())
        finally:
            m.quiet_model = old_quiet_model


def test_index_health_reports_new_files(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "a.org").write_text("* TODO [#A] Alpha\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        try:
            m.quiet_model = lambda *args, **kwargs: "summary"
            index = m.build_document_index(str(docs))
            summary = m.index_change_summary(index)
            assert summary["coverage_score"] == 100
            assert m.format_index_health(summary) == "health 100%"

            (docs / "b.org").write_text("* TODO [#B] Bravo\n", encoding="utf-8")
            summary = m.index_change_summary(index)
            assert len(summary["new_files"]) == 1
            assert summary["coverage_score"] == 50
            assert "new 1" in m.format_index_health(summary)
        finally:
            m.quiet_model = old_quiet_model


def test_index_signal_enrichment_upgrades_legacy_index(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "tasks.org").write_text("* TODO [#A] Enrich legacy task\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        try:
            m.quiet_model = lambda *args, **kwargs: "summary"
            index = m.build_document_index(str(docs))
            legacy = dict(index)
            legacy.pop("signals", None)
            legacy.pop("signal_summary", None)
            legacy.pop("signal_schema", None)
            legacy.pop("corpus_profile", None)
            legacy.pop("corpus_profile_text", None)
            legacy.pop("corpus_profile_schema", None)
            legacy.pop("corpus_profile_artifact", None)
            legacy.pop("corpus_summary_artifact", None)
            legacy["files"] = []
            for file_item in index["files"]:
                legacy_file = dict(file_item)
                legacy_file.pop("signals", None)
                legacy_file.pop("summary_artifact", None)
                legacy_file["chunks"] = []
                for chunk in file_item["chunks"]:
                    legacy_chunk = dict(chunk)
                    legacy_chunk.pop("signals", None)
                    legacy_chunk.pop("summary_artifact", None)
                    legacy_file["chunks"].append(legacy_chunk)
                legacy["files"].append(legacy_file)
            m.atomic_write(m.index_path(index["id"]), json.dumps(legacy, ensure_ascii=False, indent=2) + "\n")

            loaded = m.load_index_exact(index["id"])
            assert m.index_needs_signal_enrichment(loaded)
            enriched, changed, note = m.enrich_index_signals(loaded)
            assert changed
            assert "enriched" in note
            assert enriched["signal_schema"] == m.SIGNAL_SCHEMA_VERSION
            assert enriched["signals"]["priorities"]["A"] == 1
            assert "Enrich legacy task" in enriched["signal_summary"]
            assert enriched["corpus_profile_schema"] == m.CORPUS_PROFILE_SCHEMA_VERSION
            assert "Enrich legacy task" in enriched["corpus_profile_text"]
            assert enriched["corpus_summary_artifact"]["quality_status"] == "legacy-unverified"
            assert enriched["files"][0]["summary_artifact"]["quality_status"] == "legacy-unverified"
            assert not m.index_needs_signal_enrichment(enriched)
            assert not m.index_needs_corpus_profile(enriched)
            assert not m.index_needs_summary_provenance(enriched)
        finally:
            m.quiet_model = old_quiet_model


def test_empty_org_signal_upgrade_converges(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "notes.org").write_text("* Notes\nPlain note without task metadata.\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        try:
            m.quiet_model = lambda *args, **kwargs: "summary"
            index = m.build_document_index(str(docs))
            assert not m.index_needs_signal_enrichment(index)

            legacy = dict(index)
            legacy["files"] = []
            for file_item in index["files"]:
                legacy_file = dict(file_item)
                legacy_file.pop("signals", None)
                legacy_file["chunks"] = []
                for chunk in file_item["chunks"]:
                    legacy_chunk = dict(chunk)
                    legacy_chunk.pop("signals", None)
                    legacy_file["chunks"].append(legacy_chunk)
                legacy["files"].append(legacy_file)
            m.atomic_write(m.index_path(legacy["id"]), json.dumps(legacy, ensure_ascii=False, indent=2) + "\n")

            upgraded, changed, note = m.upgrade_index_artifacts(legacy)
            assert changed, note
            assert not m.index_needs_signal_enrichment(upgraded)
            upgraded_again, changed_again, note_again = m.upgrade_index_artifacts(upgraded)
            assert upgraded_again["id"] == upgraded["id"]
            assert not changed_again, note_again
        finally:
            m.quiet_model = old_quiet_model


def test_index_repair_regenerates_failed_chunk_artifacts(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        source = docs / "tasks.org"
        source.write_text(
            "\n".join(
                [
                    "* TODO [#A] Repair Alvarez packet",
                    "DEADLINE: <2026-05-22 Fri>",
                    "Ana Alvarez needs the countersigned packet.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        old_summarize_text = m.summarize_text
        try:
            m.quiet_model = lambda *args, **kwargs: "initial summary"
            index = m.build_document_index(str(docs))
            damaged = dict(index)
            damaged["corpus_summary"] = ""
            damaged["files"] = []
            for file_item in index["files"]:
                damaged_file = dict(file_item)
                damaged_file["summary"] = ""
                damaged_file["chunks"] = []
                for chunk in file_item["chunks"]:
                    damaged_chunk = dict(chunk)
                    damaged_chunk["summary"] = ""
                    damaged_file["chunks"].append(damaged_chunk)
                damaged["files"].append(damaged_file)
            m.atomic_write(m.index_path(damaged["id"]), json.dumps(damaged, ensure_ascii=False, indent=2) + "\n")

            def repair_summary(label, text, instruction, **kwargs):
                route = kwargs.get("route")
                if route == m.MODEL_ROUTE_INDEX_CHUNK:
                    return "TODO [#A] Repair Alvarez packet due 2026-05-22 for Ana Alvarez."
                if route == m.MODEL_ROUTE_INDEX_FILE:
                    return "tasks.org tracks the Alvarez packet repair task and deadline."
                return "The corpus contains the Alvarez packet repair task."

            m.summarize_text = repair_summary
            repaired, changed, note = m.repair_index_artifacts(damaged, limit=4)
            assert changed, note
            assert "index quality repaired" in note
            assert repaired["repair_history"][-1]["chunk_repairs"] == 1
            assert repaired["files"][0]["summary"]
            assert repaired["files"][0]["chunks"][0]["summary"]
            assert repaired["corpus_summary"]
            assert m.index_quality_gate(repaired)["status"] == "pass", m.format_index_quality_gate(m.index_quality_gate(repaired))
        finally:
            m.quiet_model = old_quiet_model
            m.summarize_text = old_summarize_text


def test_background_study_repairs_quality_failure(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        source = docs / "tasks.org"
        source.write_text("* TODO [#A] Background repair task\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        old_summarize_text = m.summarize_text
        try:
            m.quiet_model = lambda *args, **kwargs: "initial summary"
            index = m.build_document_index(str(docs))
            damaged = dict(index)
            damaged["files"] = []
            for file_item in index["files"]:
                damaged_file = dict(file_item)
                damaged_file["chunks"] = []
                for chunk in file_item["chunks"]:
                    damaged_chunk = dict(chunk)
                    damaged_chunk["summary"] = ""
                    damaged_file["chunks"].append(damaged_chunk)
                damaged["files"].append(damaged_file)
            m.atomic_write(m.index_path(damaged["id"]), json.dumps(damaged, ensure_ascii=False, indent=2) + "\n")

            def repair_summary(label, text, instruction, **kwargs):
                if kwargs.get("route") == m.MODEL_ROUTE_INDEX_CHUNK:
                    return "TODO [#A] Background repair task."
                if kwargs.get("route") == m.MODEL_ROUTE_INDEX_FILE:
                    return "tasks.org contains the background repair task."
                return "Corpus summary for the background repair task."

            m.summarize_text = repair_summary
            conv = m.new_conversation("Repair background")
            notes = m.background_study_step(conv)
            repaired = m.load_index_exact(index["id"])
            assert any("index quality repaired" in note for note in notes)
            assert m.index_quality_gate(repaired)["status"] == "pass", m.format_index_quality_gate(m.index_quality_gate(repaired))
        finally:
            m.quiet_model = old_quiet_model
            m.summarize_text = old_summarize_text


def test_index_signal_enrichment_skips_active_index(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "tasks.org").write_text("* TODO Active task\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        try:
            m.quiet_model = lambda *args, **kwargs: "summary"
            index = m.build_document_index(str(docs))
            m.write_index_progress({"id": index["id"], "status": "running", "phase": "summarizing chunk"})
            try:
                m.enrich_index_signals(index)
            except SystemExit as exc:
                assert "still being built" in str(exc)
            else:
                raise AssertionError("active index enrichment should be refused")
        finally:
            m.quiet_model = old_quiet_model


def test_repo_context_item(m):
    with isolated_state() as tmp:
        item = m.context_item_from_repo_report("status", tmp, "repo: fake\nclean")
        text, sources = m.render_context_with_sources([item], "")
        assert "repo:status" in text
        assert "clean" in text
        assert sources[0]["kind"] == "repo"
        assert sources[0]["command"] == "status"


def test_core_context_renderer_uses_injected_loaders(m):
    items = [
        {"kind": "index", "id": "idx"},
        {"kind": "repo", "command": "status", "root": "/repo", "content": "clean", "bytes": 5},
        {"kind": "file", "path": "/tmp/a.txt", "content": "alpha", "bytes": 5},
    ]

    text, sources = m.core_render_context_items_with_sources(
        items,
        "alpha",
        load_index=lambda index_id: {"id": index_id},
        render_index_query=lambda index, query: (f"index {index['id']} query {query}", [{"kind": "index", "id": index["id"]}]),
        render_index_overview=lambda index: ("overview", [{"kind": "index", "id": index["id"]}]),
        load_topic=lambda topic_id: {"id": topic_id},
        render_topic=lambda topic, query: ("topic", [{"kind": "topic", "id": topic["id"]}]),
        load_dossier=lambda dossier_id: {"id": dossier_id},
        render_dossier=lambda dossier, query: ("dossier", [{"kind": "dossier", "id": dossier["id"]}]),
    )

    assert "index idx query alpha" in text
    assert "repo:status /repo" in text
    assert "file:/tmp/a.txt" in text
    assert [source["kind"] for source in sources] == ["index", "repo", "file"]


def test_repo_command_request_attaches_context(m):
    with isolated_state() as tmp:
        conv = m.new_conversation("Repo request")
        old_repo_report = m.repo_report
        try:
            m.repo_report = lambda command, path=None: (tmp, f"repo: fake\n{command} {path}")
            request = m.repo_command_request("/repo status /tmp/example", conv)
            assert request is not None
            label, run = request
            assert label == "/repo"
            output = run()
            assert "attached repo status report" in output
            assert "status /tmp/example" in output
            assert conv.get("context_items", [])[0]["kind"] == "repo"
            assert conv["context_items"][0]["command"] == "status"
            assert m.conversation_path(conv["id"]).exists()
        finally:
            m.repo_report = old_repo_report


def test_conversation_mutation_command_request_renames_chat(m):
    with isolated_state():
        conv = m.new_conversation("Old title")
        conv["title_generated"] = True
        request = m.conversation_mutation_command_request("/rename New title", conv)
        assert request is not None
        label, run = request
        assert label == "/rename"
        assert run() == "title: New title"
        assert conv["title"] == "New title"
        assert conv["title_kind"] == "manual"
        assert "title_generated" not in conv
        saved = json.loads(m.conversation_path(conv["id"]).read_text(encoding="utf-8"))
        assert saved["title"] == "New title"


def test_conversation_lifecycle_helpers(m):
    with isolated_state():
        current = m.new_conversation("Current")
        current["messages"] = [{"role": "user", "content": "keep me"}]
        m.save_conversation(current)
        replacement = m.start_new_conversation_from_current(current, "Replacement")
        assert replacement["title"] == "Replacement"
        assert m.conversation_path(current["id"]).exists()
        assert m.conversation_path(replacement["id"]).exists()

        resumed = m.resume_conversation_from_current(replacement, current["id"])
        assert resumed["id"] == current["id"]

        next_conv, report = m.delete_conversation_then_new(resumed)
        assert report["conversation_id"] == current["id"]
        assert next_conv["id"] != current["id"]
        assert not m.conversation_path(current["id"]).exists()


def test_feedback_command_request_records_private_feedback(m):
    with isolated_state():
        conv = m.new_conversation("Feedback command")
        conv["messages"] = [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ]
        request = m.feedback_command_request("/down missed source", conv)
        assert request is not None
        label, run = request
        assert label == "/feedback"
        output = run()
        assert "feedback saved" in output
        rows = m.read_jsonl(m.response_feedback_path())
        assert rows[0]["rating"] == "down"
        assert rows[0]["note"] == "missed source"


def test_help_uses_shared_report_command_request(m):
    with isolated_state():
        conv = m.new_conversation("Help")
        request = m.shared_command_request("/help", conv)
        assert request is not None
        label, run = request
        assert label == "/help"
        assert "/status" in run()


def test_blocking_command_request_attaches_index(m):
    with isolated_state():
        conv = m.new_conversation("Index attach")
        old_build = m.build_document_index
        try:
            m.build_document_index = lambda path, glob: {
                "id": "idx1",
                "name": "docs",
                "root": path,
                "files": [],
                "corpus_summary": "summary",
            }
            request = m.blocking_command_request("/index /tmp/docs", conv)
            assert request is not None
            label, run = request
            assert label == "Building document index..."
            assert run() == "attached index: idx1"
            assert conv.get("context_items", [])[0]["id"] == "idx1"
            saved = json.loads(m.conversation_path(conv["id"]).read_text(encoding="utf-8"))
            assert saved["context_items"][0]["kind"] == "index"
        finally:
            m.build_document_index = old_build


def test_blocking_command_request_studies_context(m):
    with isolated_state():
        conv = m.new_conversation("Study")
        old_study_query = m.study_query
        try:
            m.study_query = lambda conv_arg, query, *, focus=None: f"{conv_arg['id']} {query} {focus}"
            request = m.blocking_command_request("/study tomorrow --focus recent", conv)
            assert request is not None
            label, run = request
            assert label == "Studying context..."
            assert run() == f"{conv['id']} tomorrow recent"
        finally:
            m.study_query = old_study_query


def test_cwd_indexing_ignores_light_study_done(m):
    progress = {
        "status": "running",
        "phase": "summarizing chunk",
        "current_file_index": 3,
        "total_files": 54,
        "completed_chunks": 10,
        "estimated_chunks": 100,
        "percent": 9,
        "eta_seconds": 3600,
    }
    ui = object.__new__(m.MotokoTui)
    ui.events = m.collections.deque([("cwd_index_progress", progress), ("study_done", ["catalog fresh"])])
    ui.events_lock = m.threading.Lock()
    ui.cwd_indexing = True
    ui.study_running = True
    ui.study_status = "bg-heavy: indexing(model)"
    ui.index_progress = None
    ui.study_last_note = ""
    ui.pending_prompts = m.collections.deque()
    ui.generating = False
    ui.maintaining = False
    ui.dirty = False

    ui.drain_events()

    assert ui.cwd_indexing
    assert ui.study_running
    assert "file 3/54" in ui.study_status
    assert ui.index_progress["phase"] == "summarizing chunk"
    assert ui.study_last_note == ""


def test_color_survives_quiet_index_redirect(m):
    class FakeTty:
        def isatty(self):
            return True

    old_stdout = m.sys.stdout
    old_real_stdout = m.sys.__stdout__
    old_term = os.environ.get("TERM")
    old_no_color = os.environ.get("NO_COLOR")
    try:
        os.environ["TERM"] = "xterm-256color"
        os.environ.pop("NO_COLOR", None)
        m.sys.stdout = m.io.StringIO()
        m.sys.__stdout__ = FakeTty()
        assert "\033[" in m.style("Motoko", "purple")
    finally:
        m.sys.stdout = old_stdout
        m.sys.__stdout__ = old_real_stdout
        if old_term is None:
            os.environ.pop("TERM", None)
        else:
            os.environ["TERM"] = old_term
        if old_no_color is None:
            os.environ.pop("NO_COLOR", None)
        else:
            os.environ["NO_COLOR"] = old_no_color


def main() -> int:
    m = load_motoko()
    tests = [
        test_recent_conversation_lanes,
        test_maintenance_state_and_phases,
        test_memory_proposal_sends_transcript_not_assistant_prefill,
        test_interrupted_maintenance_resume,
        test_other_conversation_maintenance_is_quietly_abandoned,
        test_profile_dossier,
        test_memory_dossier,
        test_spinner_and_input_wrapping,
        test_phase_timer_key_ignores_progress_counters,
        test_generated_title,
        test_dropdown_scrolls_without_header,
        test_wall_timeout,
        test_help_about_and_explicit_memory,
        test_help_overlay_closes,
        test_tui_about_opens_overlay,
        test_tui_overlay_highlights_report_labels,
        test_fake_openai_stream,
        test_unix_socket_model_loading_retries,
        test_unix_socket_connection_reset_retries_while_activating,
        test_unix_socket_connection_reset_retries_while_active,
        test_model_route_config_and_summary_cache,
        test_local_model_catalog_unix_socket_route,
        test_local_model_catalog_task_routes,
        test_embedding_route_fails_fast_when_model_file_missing,
        test_local_model_status_diagnostic_uses_catalog_route_without_hashing,
        test_model_service_status_and_stop_use_motoko_model_helper,
        test_summary_reductions_fan_out_across_worker_routes,
        test_sources_fallback_lists_attached_topic_context,
        test_answer_grounding_audit_sources,
        test_named_file_query_boosts_matching_path,
        test_retrieval_debug_explains_scores,
        test_named_logbook_recent_query_uses_latest_org_sections,
        test_hierarchical_evidence_store_retrieves_org_day_and_terms,
        test_span_selection_uses_embedding_and_rerank_routes,
        test_study_focus_recent_is_parsed_and_bounded,
        test_index_plan,
        test_nix_managed_allowdirs_message,
        test_cwd_learning_plan_and_existing_index,
        test_permissions_config,
        test_identity_config,
        test_assistant_color_config,
        test_report_highlighting_is_render_only,
        test_tui_role_markers_working_and_worked_line,
        test_tui_alt_backspace_deletes_previous_word,
        test_tui_bottom_status_omits_chat_phase_and_spinner,
        test_tui_append_renderer_keeps_transcript_in_scrollback,
        test_tui_seed_messages_renders_full_saved_history_without_redundant_banner,
        test_tui_resume_without_id_uses_dropdown_instead_of_terminal_prompt,
        test_conversation_delete_removes_owned_derived_artifacts,
        test_tui_report_commands_do_not_persist_system_output,
        test_tui_report_command_does_not_block_render_thread,
        test_tui_prompt_is_saved_before_context_preparation,
        test_response_feedback_is_private_and_does_not_pollute_conversation,
        test_feedback_eval_exports_private_retrieval_fixtures,
        test_retrieval_preview_shows_context_without_model_call,
        test_index_storage_audit_reports_duplicates_and_cleanup_plan,
        test_index_cleanup_removes_stale_superseded_snapshots_after_materializing_latest,
        test_vector_plan_reports_storage_and_readiness_gates,
        test_vector_build_and_query_lexical_baseline,
        test_embedding_vector_store_uses_catalog_route,
        test_embedding_vector_store_splits_long_chunks_with_parent_mapping,
        test_embedding_vector_store_parallelizes_batches,
        test_embedding_parallelism_allows_32_cap,
        test_embedding_vector_store_stale_when_route_model_changes,
        test_embedding_vector_store_resumes_saved_progress,
        test_embedding_vector_store_falls_back_from_excess_parallelism,
        test_vector_query_can_use_catalog_reranker_route,
        test_normal_retrieval_uses_embedding_rerank_by_default,
        test_index_limits,
        test_index_progress_state,
        test_index_progress_eta_tracks_model_timing,
        test_summary_block_estimates_expand_progress_total,
        test_list_indexes_ignores_progress_files,
        test_superseded_partials_do_not_look_unfinished,
        test_context_catalog_prefers_latest_index_per_family,
        test_index_resume_after_model_timeout,
        test_index_pause_resume_rescans_new_files_without_overwriting_chunks,
        test_org_task_signals_drive_retrieval,
        test_index_health_reports_new_files,
        test_index_signal_enrichment_upgrades_legacy_index,
        test_empty_org_signal_upgrade_converges,
        test_index_repair_regenerates_failed_chunk_artifacts,
        test_background_study_repairs_quality_failure,
        test_index_signal_enrichment_skips_active_index,
        test_repo_context_item,
        test_cwd_indexing_ignores_light_study_done,
        test_color_survives_quiet_index_redirect,
    ]
    for test in tests:
        test(m)
    print(f"{len(tests)} motoko regression tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
