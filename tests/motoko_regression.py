#!/usr/bin/env python3
"""Stdlib-only Motoko regression tests."""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import tempfile
import threading
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
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["MOTOKO_STATE_HOME"] = str(pathlib.Path(tmp) / "state")
        os.environ["MOTOKO_CONFIG_HOME"] = str(pathlib.Path(tmp) / "config")
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

        old_propose = m.propose_memories
        try:
            m.propose_memories = lambda _conv, timeout=m.MODEL_TIMEOUT_SECONDS: [
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
            m.propose_memories = old_propose


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


class FakeHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for token in ("hel", "lo"):
            event = {"choices": [{"delta": {"content": token}}]}
            self.wfile.write(f"data: {json.dumps(event)}\n\n".encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *_args):
        return


def test_fake_openai_stream(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
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
    finally:
        server.shutdown()
        server.server_close()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint


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


def main() -> int:
    m = load_motoko()
    tests = [
        test_recent_conversation_lanes,
        test_maintenance_state_and_phases,
        test_interrupted_maintenance_resume,
        test_profile_dossier,
        test_fake_openai_stream,
        test_index_plan,
    ]
    for test in tests:
        test(m)
    print(f"{len(tests)} motoko regression tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
