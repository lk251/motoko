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
        assert "q or Esc" in help_text
        about = m.format_about()
        assert "Motoko " in about
        assert "model badge:" in about
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
            assert "index quality: pass" in buf.getvalue()
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
        test_interrupted_maintenance_resume,
        test_other_conversation_maintenance_is_quietly_abandoned,
        test_profile_dossier,
        test_memory_dossier,
        test_spinner_and_input_wrapping,
        test_generated_title,
        test_dropdown_scrolls_without_header,
        test_wall_timeout,
        test_help_about_and_explicit_memory,
        test_help_overlay_closes,
        test_fake_openai_stream,
        test_model_route_config_and_summary_cache,
        test_index_plan,
        test_nix_managed_allowdirs_message,
        test_cwd_learning_plan_and_existing_index,
        test_permissions_config,
        test_identity_config,
        test_index_limits,
        test_index_progress_state,
        test_index_progress_eta_tracks_model_timing,
        test_summary_block_estimates_expand_progress_total,
        test_list_indexes_ignores_progress_files,
        test_index_resume_after_model_timeout,
        test_index_pause_resume_rescans_new_files_without_overwriting_chunks,
        test_org_task_signals_drive_retrieval,
        test_index_health_reports_new_files,
        test_index_signal_enrichment_upgrades_legacy_index,
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
