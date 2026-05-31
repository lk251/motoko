#!/usr/bin/env python3
"""Stdlib-only Motoko regression tests."""

from __future__ import annotations

import contextlib
import io
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


SOURCE = pathlib.Path(os.environ.get("MOTOKO_SOURCE", "motoko"))
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from motoko_core import slot_cache as slot_cache_core
from motoko_core.artifact_lifecycle import (
    cleanup_superseded_index_candidates as cleanup_superseded_index_candidates_core,
    collect_source_lifecycle_artifact_records as collect_source_lifecycle_artifact_records_core,
    delete_index_snapshot_artifacts as delete_index_snapshot_artifacts_core,
    delete_json_artifacts_referencing_index as delete_json_artifacts_referencing_index_core,
    dependency_json_artifact_specs as dependency_json_artifact_specs_core,
    derived_delete_report_labels as derived_delete_report_labels_core,
    format_source_lifecycle_report as format_source_lifecycle_report_core,
    index_snapshot_delete_specs as index_snapshot_delete_specs_core,
    index_artifact_dependency_counts as index_artifact_dependency_counts_core,
    index_file_path_keys as index_file_path_keys_core,
    index_source_lifecycle_scan as index_source_lifecycle_scan_core,
    json_matching_source_paths as json_matching_source_paths_core,
    json_paths_referencing_index as json_paths_referencing_index_core,
    json_references_index as json_references_index_core,
    source_artifact_record as source_artifact_record_core,
    source_lifecycle_affected_paths as source_lifecycle_affected_paths_core,
    source_lifecycle_path_variants as source_lifecycle_path_variants_core,
    source_lifecycle_paths_by_status as source_lifecycle_paths_by_status_core,
    source_lifecycle_json_dir_specs as source_lifecycle_json_dir_specs_core,
    source_lifecycle_json_file_specs as source_lifecycle_json_file_specs_core,
    source_lifecycle_jsonl_specs as source_lifecycle_jsonl_specs_core,
    source_lifecycle_report as build_source_lifecycle_report,
    superseded_stale_index_candidates as superseded_stale_index_candidates_core,
)


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

        other_project = m.new_conversation("Other project relevant")
        other_project["id"] = "other-project"
        other_project["project"] = {"kind": "git", "root": "/tmp/not-this-project"}
        other_project["updated"] = "2026-05-17T09:58:00+00:00"
        other_project["messages"] = [{"role": "user", "content": "The codename is violet harbor."}]
        write_conversation(m, other_project)

        selected = m.ranked_recent_conversations(current, "violet harbor")
        by_id = {row["id"]: row for row in selected}
        assert "recent" in by_id
        assert "recent" in by_id["recent"]["_selection_reasons"]
        assert "relevant" in by_id
        assert "relevant" in by_id["relevant"]["_selection_reasons"]
        assert "other-project" not in by_id

        text, sources = m.render_recent_conversations_with_sources(current, "violet harbor")
        assert "violet harbor" in text
        assert any("relevant" in source.get("selection", []) for source in sources)


def test_conversation_recall_config_expands_saved_lanes_and_snippets(m):
    with isolated_state():
        config = m.load_config()
        config["conversation_recall"] = {
            "recent_conversations": 3,
            "relevant_conversations": 3,
            "conversation_messages": 1,
            "matched_snippets": 1,
            "snippet_chars": 140,
            "max_chars": 5000,
        }
        m.save_config(config)

        current = m.new_conversation("Current")
        current["id"] = "current"
        current["updated"] = "2026-05-17T10:00:00+00:00"
        current["messages"] = [{"role": "user", "content": "Find violet harbor and copper bridge notes."}]
        write_conversation(m, current)

        for idx in range(4):
            recent = m.new_conversation(f"Recent {idx}")
            recent["id"] = f"recent-{idx}"
            recent["updated"] = f"2026-05-17T09:5{idx}:00+00:00"
            recent["messages"] = [{"role": "user", "content": f"Routine note {idx}."}]
            write_conversation(m, recent)

        for idx, phrase in enumerate(["violet harbor", "copper bridge", "violet harbor copper bridge"], 1):
            relevant = m.new_conversation(f"Relevant {idx}")
            relevant["id"] = f"relevant-{idx}"
            relevant["updated"] = f"2026-05-17T08:0{idx}:00+00:00"
            relevant["messages"] = [{"role": "user", "content": f"The project phrase is {phrase}."}]
            write_conversation(m, relevant)

        selected = m.ranked_recent_conversations(current, "violet harbor copper bridge")
        assert len(selected) == 6
        assert sum("recent" in row.get("_selection_reasons", []) for row in selected) == 3
        assert sum("relevant" in row.get("_selection_reasons", []) for row in selected) == 3
        assert any(row.get("_matched_snippets") for row in selected)

        text, sources = m.render_recent_conversations_with_sources(current, "violet harbor copper bridge")
        assert "matched snippets:" in text
        assert "violet harbor copper bridge" in text
        assert len(sources) == 6
        assert "conversation recall: current 24 msg(s)" in m.format_status(current)


def test_current_conversation_recall_config_controls_model_history(m):
    with isolated_state():
        config = m.load_config()
        config["conversation_recall"] = {
            "current_messages": "all",
            "current_max_chars": 26,
        }
        m.save_config(config)

        conv = m.new_conversation("Current")
        conv["messages"] = [
            {"role": "user", "content": "older message outside budget"},
            {"role": "assistant", "content": "middle message outside budget"},
            {"role": "user", "content": "latest message"},
        ]

        selected = m.current_conversation_messages_for_model(conv)
        assert [row["content"] for row in selected] == ["latest message"]

        config = m.load_config()
        config["conversation_recall"]["current_max_chars"] = 0
        m.save_config(config)
        selected = m.current_conversation_messages_for_model(conv)
        assert [row["content"] for row in selected] == [
            "older message outside budget",
            "middle message outside budget",
            "latest message",
        ]


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
            m.propose_memories_bounded = lambda _conv, **_kwargs: [
                "Javier prefers concise terminal output."
            ]
            state = m.begin_maintenance_state(conv)
            phases = []
            notes = m.auto_maintain_conversation(conv, phase_callback=phases.append, state=state)
            assert "memory: checking" in phases
            assert any(phase.startswith("memory: proposing(") for phase in phases)
            assert "memory: saving" in phases
            assert phases[-1] == "memory: done"
            assert notes == ["saved 1 queued durable memory"]
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


def test_memory_proposal_helper_timeout_respects_socket_activation(m):
    with isolated_state():
        old_model_route = m.model_route
        try:
            m.model_route = lambda _route: {"endpoint": "unix:///run/motoko-llm/personal/qwen35-2b-worker.sock"}
            assert m.memory_proposal_helper_timeout(90) == m.SOCKET_ACTIVATION_MIN_TIMEOUT_SECONDS + 15
            m.model_route = lambda _route: {"endpoint": "http://127.0.0.1:8083/v1/chat/completions"}
            assert m.memory_proposal_helper_timeout(90) == 105
        finally:
            m.model_route = old_model_route


def test_memory_proposal_queue_retries_until_saved(m):
    with isolated_state():
        conv = m.new_conversation("Queued memory")
        conv["id"] = "queued-memory"
        conv["title_kind"] = "manual"
        conv["title_generated"] = m.now()
        conv["messages"] = [
            {"role": "user", "content": "I prefer careful local memory."},
            {"role": "assistant", "content": "Understood."},
            {"role": "user", "content": "Motoko should retry memory proposals."},
            {"role": "assistant", "content": "I will keep the queue durable."},
        ]
        conv["last_auto_compact_message_count"] = len(conv["messages"])
        write_conversation(m, conv)

        calls = {"count": 0}
        old_propose = m.propose_memories_bounded
        try:
            def fake_propose(_conv, **_kwargs):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise TimeoutError("cold worker")
                return ["Javier wants Motoko memory proposals to retry durably."]

            m.propose_memories_bounded = fake_propose
            first_notes = m.auto_maintain_conversation(conv)
            assert "memory proposal queued for retry" in first_notes
            assert m.queued_memory_proposal_count() == 1
            assert int(conv.get("last_auto_memory_message_count", 0) or 0) == 0

            second_notes = m.auto_maintain_conversation(conv)
            assert any("saved 1 queued durable memory" in note for note in second_notes)
            assert m.queued_memory_proposal_count() == 0
            assert int(conv.get("last_auto_memory_message_count", 0) or 0) == len(conv["messages"])
            assert any(
                row.get("text") == "Javier wants Motoko memory proposals to retry durably."
                for row in m.read_memory_rows()
            )
        finally:
            m.propose_memories_bounded = old_propose


def test_running_memory_proposal_queue_recovers_after_restart(m):
    with isolated_state():
        conv = m.new_conversation("Running memory")
        conv["id"] = "running-memory"
        conv["messages"] = [
            {"role": "user", "content": "Recover running memory jobs."},
            {"role": "assistant", "content": "Yes."},
            {"role": "user", "content": "Treat running rows as retryable."},
            {"role": "assistant", "content": "Understood."},
        ]
        write_conversation(m, conv)
        m.enqueue_memory_proposal(conv, message_count=len(conv["messages"]))
        rows = m.read_memory_proposal_queue()
        rows[0]["status"] = "running"
        m.write_memory_proposal_queue(rows)

        old_propose = m.propose_memories_bounded
        try:
            m.propose_memories_bounded = lambda _conv, **_kwargs: ["Running memory proposal jobs are retryable."]
            notes = m.run_queued_memory_proposals(current_conv=conv)
        finally:
            m.propose_memories_bounded = old_propose

        assert any("saved 1 queued durable memory" in note for note in notes)
        assert m.queued_memory_proposal_count() == 0


def test_memory_proposal_queue_defers_behind_active_chat_route(m):
    with isolated_state():
        conv = m.new_conversation("Busy route memory")
        conv["id"] = "busy-route-memory"
        conv["messages"] = [
            {"role": "user", "content": "Keep memory work queued."},
            {"role": "assistant", "content": "Yes."},
            {"role": "user", "content": "Do not race active chat."},
            {"role": "assistant", "content": "Understood."},
        ]
        write_conversation(m, conv)
        m.enqueue_memory_proposal(conv, message_count=len(conv["messages"]))

        old_prepare = m.prepare_route_residency_for_request
        old_propose = m.propose_memories_bounded
        try:
            m.prepare_route_residency_for_request = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                m.RouteResidencyBusy("worker route qwen35-2b-worker queued behind active chat route qwen36-chat-default")
            )
            m.propose_memories_bounded = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("proposal should not run when chat route is busy")
            )
            notes = m.run_queued_memory_proposals(current_conv=conv)
        finally:
            m.prepare_route_residency_for_request = old_prepare
            m.propose_memories_bounded = old_propose

        assert notes == ["memory proposal queued behind active chat route"]
        assert m.queued_memory_proposal_count() == 1
        rows = m.read_memory_proposal_queue()
        assert rows[0]["status"] == "pending"
        assert "active chat route" in rows[0]["last_error"]


def test_memory_proposal_queue_cancel_leaves_retryable(m):
    with isolated_state():
        conv = m.new_conversation("Cancel queued memory")
        conv["id"] = "cancel-queued-memory"
        conv["messages"] = [
            {"role": "user", "content": "Queued memory cancellation should be durable."},
            {"role": "assistant", "content": "Yes."},
            {"role": "user", "content": "Interrupted proposals should retry later."},
            {"role": "assistant", "content": "Understood."},
        ]
        write_conversation(m, conv)
        m.enqueue_memory_proposal(conv, message_count=len(conv["messages"]))

        cancel_event = threading.Event()
        old_propose = m.propose_memories_bounded
        try:
            def fake_propose(_conv, **kwargs):
                assert kwargs.get("cancel_event") is cancel_event
                cancel_event.set()
                raise m.WorkPaused("memory proposal interrupted by request", work_kind="maintenance")

            m.propose_memories_bounded = fake_propose
            try:
                m.run_queued_memory_proposals(current_conv=conv, cancel_event=cancel_event)
            except m.WorkPaused as exc:
                assert exc.work_kind == "maintenance"
            else:
                raise AssertionError("cancelled memory proposal should raise WorkPaused")
        finally:
            m.propose_memories_bounded = old_propose

        rows = m.read_memory_proposal_queue()
        assert len(rows) == 1
        assert rows[0]["status"] == "pending"
        assert int(rows[0].get("attempts", 0) or 0) == 1
        assert "interrupted" in rows[0].get("last_error", "")
        assert m.queued_memory_proposal_count() == 1
        assert int(conv.get("last_auto_memory_message_count", 0) or 0) == 0


def test_auto_maintenance_passes_cancel_event_to_memory_queue(m):
    with isolated_state():
        conv = m.new_conversation("Cancel event propagation")
        conv["id"] = "cancel-event-propagation"
        conv["title_kind"] = "manual"
        conv["title_generated"] = m.now()
        conv["messages"] = [
            {"role": "user", "content": "Propagate cancel events."},
            {"role": "assistant", "content": "Yes."},
            {"role": "user", "content": "Memory maintenance should receive them."},
            {"role": "assistant", "content": "Understood."},
        ]
        conv["last_auto_compact_message_count"] = len(conv["messages"])
        write_conversation(m, conv)

        cancel_event = threading.Event()
        seen = []
        old_run = m.run_queued_memory_proposals
        try:
            def fake_run(**kwargs):
                seen.append(kwargs.get("cancel_event"))
                return []

            m.run_queued_memory_proposals = fake_run
            m.auto_maintain_conversation(conv, cancel_event=cancel_event)
        finally:
            m.run_queued_memory_proposals = old_run

        assert seen == [cancel_event]


def test_memory_proposal_helper_subprocess_terminates_on_cancel(m):
    with isolated_state():
        cancel_event = threading.Event()
        calls = {"communicate": 0, "terminated": 0, "killed": 0}

        class FakeProcess:
            returncode = None

            def poll(self):
                return self.returncode

            def communicate(self, input=None, timeout=None):
                calls["communicate"] += 1
                cancel_event.set()
                raise subprocess.TimeoutExpired("fake-helper", timeout)

            def terminate(self):
                calls["terminated"] += 1
                self.returncode = -15

            def kill(self):
                calls["killed"] += 1
                self.returncode = -9

            def wait(self, timeout=None):
                return self.returncode

        old_popen = m.subprocess.Popen
        old_timeout = m.memory_proposal_helper_timeout
        try:
            m.subprocess.Popen = lambda *_args, **_kwargs: FakeProcess()
            m.memory_proposal_helper_timeout = lambda _timeout: 30
            try:
                m.propose_memories_subprocess(
                    {"id": "helper-cancel", "messages": [{"role": "user", "content": "hello"}]},
                    cancel_event=cancel_event,
                )
            except m.WorkPaused as exc:
                assert exc.work_kind == "maintenance"
            else:
                raise AssertionError("cancelled helper should raise WorkPaused")
        finally:
            m.subprocess.Popen = old_popen
            m.memory_proposal_helper_timeout = old_timeout

        assert calls["communicate"] == 1
        assert calls["terminated"] == 1
        assert calls["killed"] == 0


def test_delete_conversation_removes_memory_proposal_jobs(m):
    with isolated_state():
        conv = m.new_conversation("Delete queued memory")
        conv["id"] = "delete-queued-memory"
        write_conversation(m, conv)
        m.enqueue_memory_proposal(conv, message_count=4)
        report = m.delete_conversation_and_artifacts(conv)
        assert report["memory_proposals_deleted"] == 1
        assert m.queued_memory_proposal_count() == 0


def test_skill_suggestion_parser_uses_local_review_signal(m):
    with isolated_state():
        text = json.dumps(
            {
                "suggestions": [
                    {
                        "name": "motoko-retrieval-debugging",
                        "description": "Debug Motoko retrieval failures with source-visible checks.",
                        "kind": "workflow",
                        "handler": "prompt_only",
                        "allowed_effects": ["prompt_context"],
                        "triggers": ["retrieval result is wrong or incomplete"],
                        "signals": ["would reduce errors", "encodes project-specific craft"],
                        "reason": "This would save tokens and improve reliability.",
                        "body": "Check recall, ranking, staleness, chunking, summaries, and prompt use before changing retrieval.",
                    }
                ]
            }
        )
        rows = m.parse_skill_suggestion_output(text)
        assert len(rows) == 1
        assert rows[0]["slug"] == "motoko-retrieval-debugging"
        assert rows[0]["handler"] == "prompt_only"
        assert "would reduce errors" in rows[0]["signals"]


def test_skill_registry_downgrades_unknown_handlers_and_effects(m):
    with isolated_state():
        rows = m.parse_skill_suggestion_output(
            json.dumps(
                {
                    "name": "unsafe-skill",
                    "description": "Attempt to declare an unsupported handler.",
                    "handler": "shell:run",
                    "allowed_effects": ["execute_shell", "prompt_context"],
                    "body": "Do not execute this.",
                }
            )
        )
        assert len(rows) == 1
        assert rows[0]["handler"] == "prompt_only"
        assert rows[0]["allowed_effects"] == ["prompt_context"]

        skill = m.learn_skill(
            "unsafe-learned-skill",
            description="Unsupported handler should be normalized.",
            body="Do not execute this.",
            handler="shell:run",
            allowed_effects=["execute_shell", "prompt_context"],
        )
        assert skill["handler"] == "prompt_only"
        assert skill["allowed_effects"] == ["prompt_context"]


def test_auto_maintenance_suggests_skill_without_saving_it(m):
    with isolated_state():
        conv = m.new_conversation("Skill suggestion")
        conv["id"] = "skill-suggestion"
        conv["title_kind"] = "manual"
        conv["title_generated"] = m.now()
        conv["messages"] = [
            {"role": "user", "content": "When retrieval fails, inspect sources first."},
            {"role": "assistant", "content": "I will check sources."},
            {"role": "user", "content": "Then check recall, ranking, stale data, chunking, summaries, and prompt use."},
            {"role": "assistant", "content": "Understood."},
            {"role": "user", "content": "This should become a reusable workflow."},
            {"role": "assistant", "content": "I can suggest a skill."},
        ]
        conv["last_auto_memory_message_count"] = len(conv["messages"])
        conv["last_auto_compact_message_count"] = len(conv["messages"])

        old_propose = m.propose_skill_suggestions
        try:
            def fake_propose(_conv, **_kwargs):
                return [
                    {
                        "name": "retrieval-failure-diagnosis",
                        "description": "Diagnose retrieval failures before changing ranking.",
                        "body": "Check recall, ranking, stale data, chunking, summaries, and prompt use.",
                        "reason": "Saves tokens and reduces errors on repeated retrieval debugging.",
                        "signals": ["user corrected workflow"],
                    }
                ]

            m.propose_skill_suggestions = fake_propose
            notes = m.auto_maintain_conversation(conv)
        finally:
            m.propose_skill_suggestions = old_propose

        assert any("skill suggestion pending: retrieval-failure-diagnosis" in note for note in notes)
        assert "retrieval-failure-diagnosis" not in m.format_skills()
        suggestions = m.list_skill_suggestions(status="pending")
        assert len(suggestions) == 1
        assert suggestions[0]["slug"] == "retrieval-failure-diagnosis"

        accepted = m.accept_skill_suggestion_text(suggestions[0]["id"])
        assert "skill accepted: retrieval-failure-diagnosis" in accepted
        assert "retrieval-failure-diagnosis" in m.format_skills()


def test_auto_skill_review_runs_on_explicit_signal_before_interval(m):
    with isolated_state():
        conv = m.new_conversation("Early skill suggestion")
        conv["id"] = "early-skill-suggestion"
        conv["title_kind"] = "manual"
        conv["title_generated"] = m.now()
        conv["messages"] = [
            {"role": "user", "content": "When retrieval fails, inspect sources first."},
            {"role": "assistant", "content": "I will check sources first."},
            {"role": "user", "content": "This should become a reusable procedure for Motoko."},
            {"role": "assistant", "content": "I can review it as a skill suggestion."},
        ]
        conv["last_auto_memory_message_count"] = len(conv["messages"])
        conv["last_auto_compact_message_count"] = len(conv["messages"])

        calls = []
        old_propose = m.propose_skill_suggestions
        try:
            def fake_propose(_conv, **kwargs):
                calls.append(kwargs.get("review_reasons", []))
                return [
                    {
                        "name": "source-first-retrieval-diagnosis",
                        "description": "Diagnose retrieval failures by inspecting sources first.",
                        "body": "Inspect sources before changing prompts or ranking.",
                        "reason": "The user explicitly marked this as reusable.",
                        "signals": ["explicit reusable procedure signal"],
                    }
                ]

            m.propose_skill_suggestions = fake_propose
            notes = m.auto_maintain_conversation(conv)
        finally:
            m.propose_skill_suggestions = old_propose

        assert calls
        assert any(str(reason).startswith("explicit-signal:") for reason in calls[0])
        assert any("skill suggestion pending: source-first-retrieval-diagnosis" in note for note in notes)


def test_skill_review_prompt_prioritizes_loaded_skill_context(m):
    with isolated_state():
        conv = m.new_conversation("Loaded skill review")
        conv["id"] = "loaded-skill-review"
        conv["messages"] = [
            {"role": "user", "content": "Use the retrieval debugging workflow."},
            {"role": "assistant", "content": "I used the existing workflow, but it needs a source audit step."},
        ]
        conv["last_sources"] = [
            {
                "kind": "skill",
                "name": "retrieval-debugging",
                "description": "Debug retrieval failures.",
                "handler": "prompt_only",
                "matched_terms": ["retrieval", "debugging"],
                "score": 42,
            }
        ]
        calls = []
        old_call_model = m.call_model
        try:
            def fake_call_model(messages, **kwargs):
                calls.append((messages, kwargs))
                return "NO_SKILL"

            m.call_model = fake_call_model
            assert m.propose_skill_suggestions(conv, review_reasons=["loaded-skill"]) == []
        finally:
            m.call_model = old_call_model

        assert calls
        user_prompt = calls[0][0][-1]["content"]
        assert "Review trigger(s): loaded-skill" in user_prompt
        assert "Recently loaded/consulted skills:" in user_prompt
        assert "skill:retrieval-debugging" in user_prompt
        assert "patch that loaded skill first" in calls[0][0][0]["content"]


def test_manual_skill_review_and_suggestion_detail(m):
    with isolated_state():
        conv = m.new_conversation("Manual skill review")
        conv["id"] = "manual-skill-review"
        conv["messages"] = [
            {"role": "user", "content": "When Motoko gives a weak answer, inspect /sources first."},
            {"role": "assistant", "content": "I will inspect sources before changing prompts."},
            {"role": "user", "content": "Then check recall, ranking, staleness, chunking, summaries, and prompt use."},
            {"role": "assistant", "content": "That is a reusable diagnostic workflow."},
        ]

        old_propose = m.propose_skill_suggestions
        try:
            def fake_propose(_conv, **_kwargs):
                return [
                    {
                        "name": "source-first-answer-diagnosis",
                        "description": "Diagnose weak answers from sources before changing prompts.",
                        "body": "Inspect sources, then check recall, ranking, stale data, chunking, summaries, and prompt use.",
                        "reason": "This reduces errors and encodes project-specific craft.",
                        "signals": ["user corrected workflow"],
                        "triggers": ["answer is weak or unsupported"],
                    }
                ]

            m.propose_skill_suggestions = fake_propose
            request = m.shared_command_request("/skill review", conv)
            assert request is not None
            assert request.kind == m.COMMAND_KIND_MUTATION
            assert request.mutates_state
            _label, run = request
            report = run()
        finally:
            m.propose_skill_suggestions = old_propose

        assert "skill review: 1 pending suggestion" in report
        suggestions = m.list_skill_suggestions(status="pending")
        assert len(suggestions) == 1
        suggestion_id = suggestions[0]["id"]

        shown = m.shared_command_request(f"/skill suggestion {suggestion_id}", conv)
        assert shown is not None
        assert shown.kind == m.COMMAND_KIND_REPORT
        _label, run = shown
        detail = run()
        assert "source-first-answer-diagnosis" in detail
        assert "Proposed skill body:" in detail
        assert "Inspect sources" in detail
        assert "motoko skill accept" in detail


def test_skill_suggestion_accepts_patch_action(m):
    with isolated_state():
        m.learn_skill_text(
            "source-first-answer-diagnosis",
            description="Diagnose weak answers from sources.",
            body="Inspect sources first.",
        )
        added = m.add_skill_suggestions(
            [
                {
                    "action": "patch",
                    "name": "source-first-answer-diagnosis",
                    "target_skill": "source-first-answer-diagnosis",
                    "description": "Extend the source-first diagnosis procedure.",
                    "old_string": "Inspect sources first.",
                    "new_string": "Inspect sources first, then run retrieval-debug to separate recall, ranking, stale data, chunking, summary, and final prompt issues.",
                    "reason": "This updates an existing umbrella skill instead of creating a duplicate.",
                    "signals": ["existing skill was incomplete"],
                }
            ],
            conversation_id="patch-skill",
        )
        assert len(added) == 1
        detail = m.format_skill_suggestion(added[0]["id"])
        assert "action: patch" in detail
        assert "Proposed patch:" in detail

        accepted = m.accept_skill_suggestion_text(added[0]["id"])
        assert "skill accepted: source-first-answer-diagnosis" in accepted
        assert "action: patch" in accepted
        shown = m.format_skill("source-first-answer-diagnosis")
        assert "retrieval-debug" in shown


def test_skill_manage_support_file_is_confined(m):
    with isolated_state():
        m.learn_skill_text(
            "retrieval-debugging",
            description="Debug retrieval failures.",
            body="Prefer source-visible diagnostics before prompt changes.",
        )
        added = m.add_skill_suggestions(
            [
                {
                    "action": "write_file",
                    "name": "retrieval-debugging-reference",
                    "target_skill": "retrieval-debugging",
                    "description": "Add a compact retrieval debugging reference.",
                    "file_path": "references/checklist.md",
                    "file_content": "Check recall, ranking, staleness, chunking, summaries, and prompt use.",
                    "reason": "Support files preserve detail without bloating SKILL.md.",
                    "signals": ["support file is better than a new skill"],
                }
            ],
            conversation_id="support-file",
        )
        assert len(added) == 1
        accepted = m.accept_skill_suggestion_text(added[0]["id"])
        assert "support file written: references/checklist.md" in accepted
        support_path = m.skills_dir() / "retrieval-debugging" / "references" / "checklist.md"
        assert support_path.read_text(encoding="utf-8").startswith("Check recall")
        assert "support files: references/checklist.md" in m.format_skill("retrieval-debugging")
        assert "references/checklist.md" in m.format_skill_supports("retrieval-debugging")
        assert "Check recall" in m.format_skill_support_file("retrieval-debugging", "references/checklist.md")

        rendered, sources = m.render_skills_with_sources("retrieval debugging checklist")
        assert "Support file: references/checklist.md" in rendered
        assert any(source.get("kind") == "skill-support" for source in sources)

        try:
            m.core_manage_skill(
                m.skills_dir(),
                action="write_file",
                target_skill="retrieval-debugging",
                file_path="../escape.md",
                file_content="bad",
                writer=m.atomic_write,
            )
        except SystemExit as exc:
            assert "support file path" in str(exc)
        else:
            raise AssertionError("path traversal support file was accepted")


def test_skill_manage_support_file_commands(m):
    with isolated_state():
        conv = m.new_conversation("Skill support commands")
        conv["id"] = "skill-support-commands"
        m.learn_skill_text(
            "retrieval-debugging",
            description="Debug retrieval failures.",
            body="Prefer source-visible diagnostics before prompt changes.",
        )
        write_cmd = m.shared_command_request(
            '/skill write-file retrieval-debugging references/terms.md --content "RaceFocus retrieval checklist support"',
            conv,
        )
        assert write_cmd is not None
        assert write_cmd.kind == m.COMMAND_KIND_MUTATION
        _label, run = write_cmd
        assert "support file written: references/terms.md" in run()

        list_cmd = m.shared_command_request("/skill support retrieval-debugging", conv)
        assert list_cmd is not None
        assert list_cmd.kind == m.COMMAND_KIND_REPORT
        _label, run = list_cmd
        assert "references/terms.md" in run()

        show_cmd = m.shared_command_request("/skill support retrieval-debugging references/terms.md", conv)
        assert show_cmd is not None
        _label, run = show_cmd
        assert "RaceFocus retrieval checklist support" in run()

        patch_cmd = m.shared_command_request(
            '/skill patch retrieval-debugging --file references/terms.md --old RaceFocus --new Motoko',
            conv,
        )
        assert patch_cmd is not None
        _label, run = patch_cmd
        assert "skill file patched: references/terms.md" in run()
        assert "Motoko retrieval checklist support" in m.format_skill_support_file(
            "retrieval-debugging",
            "references/terms.md",
        )

        remove_cmd = m.shared_command_request("/skill remove-file retrieval-debugging references/terms.md --yes", conv)
        assert remove_cmd is not None
        _label, run = remove_cmd
        assert "support file removed: references/terms.md" in run()
        assert "references/terms.md" not in m.format_skill_supports("retrieval-debugging")


def test_skill_upgrade_rewrites_legacy_skill_files(m):
    with isolated_state():
        path = m.skills_dir() / "legacy-debug" / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    "---",
                    "schema: motoko-skill-v1",
                    "name: legacy-debug",
                    "description: Legacy debugging skill",
                    "---",
                    "",
                    "Check sources before changing the prompt.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        report = m.upgrade_skills()
        assert report["checked"] == 1
        assert report["upgraded"] == 1
        upgraded = path.read_text(encoding="utf-8")
        assert "schema: motoko-skill-v3" in upgraded
        assert "handler: prompt_only" in upgraded
        assert "allowed_effects: prompt_context" in upgraded

        second = m.upgrade_skills()
        assert second["checked"] == 1
        assert second["upgraded"] == 0


def test_skill_plan_shows_prompt_and_retrieval_selection(m):
    with isolated_state():
        m.learn_skill_text(
            "racefocus-response-style",
            description="RaceFocus planning responses",
            body="Keep VR, 2D HUD, and OBS renderer contexts distinct.",
        )
        temporal = m.format_skill_plan("summarize the last three days present in logbook.org")
        assert "activated retrieval skills:" in temporal
        assert "org-temporal-retrieval" in temporal
        assert "builtin:org_temporal_latest_entries" in temporal
        assert "count=3" in temporal
        assert "model calls: none" in temporal

        structural = m.format_skill_plan("show me all elements with tag racefocus")
        assert "activated retrieval skills:" in structural
        assert "org-structural-query" in structural
        assert "builtin:org_structural_query" in structural
        assert "structural intent:" in structural
        assert "tags=racefocus" in structural
        assert "model calls: none" in structural

        prompt = m.format_skill_plan("RaceFocus OBS renderer plan")
        assert "selected prompt skills:" in prompt
        assert "racefocus-response-style" in prompt

        conv = m.new_conversation("Skill plan")
        conv["id"] = "skill-plan"
        report = m.shared_command_request("/skill plan RaceFocus OBS renderer plan", conv)
        assert report is not None
        assert report.kind == m.COMMAND_KIND_REPORT
        _label, run = report
        assert "racefocus-response-style" in run()

        codebase = m.format_skill_plan("How should Motoko refactor its codebase command handlers?")
        assert "motoko-codebase-maintainer" in codebase
        assert "builtin:motoko_codebase_query" in codebase
        assert "codebase intent:" in codebase

        retrieval = m.format_skill_plan("diagnose retrieval failure with weak sources and wrong span selection")
        assert "motoko-retrieval-maintainer" in retrieval

        refactor = m.format_skill_plan("careful service boundary refactor with validation and craftsmanship")
        assert "motoko-refactor-craft" in refactor

        agentic = m.format_skill_plan("review skill tool action goal loop authority and approvals")
        assert "motoko-agentic-boundary-review" in agentic


def test_motoko_codebase_context_and_commands_are_deterministic(m):
    with isolated_state():
        code_map = m.motoko_code_map()
        assert code_map["schema"] == "motoko-code-intel-v1"
        assert any(row.get("path") == "motoko" for row in code_map.get("files", []))
        summary = code_map["summary"]
        assert summary["command_traces"] >= summary["commands"] - 20
        assert summary["resolved_call_edges"] > 0
        assert summary["service_boundaries"] > 0
        assert summary["schema_constants"] > 0
        assert summary["root_hotspots"]
        assert any(row["name"] == "SOURCE_LIFECYCLE_REPORT_SCHEMA" for row in code_map["constants"])
        source_trace = next(row for row in code_map["command_traces"] if row["command"] == "source-lifecycle")
        assert source_trace["handler"] == "command_source_lifecycle"
        assert source_trace["handler_found"] is True
        assert any("source_lifecycle" in row["name"] for row in source_trace["tests"])
        assert any(row["path"] == "motoko_core/artifact_lifecycle.py" for row in code_map["service_boundaries"])
        query = m.motoko_code_query("Motoko skill plan command implementation tests")
        assert query["schema"] == "motoko-code-query-v1"
        assert query["symbols"] or query["commands"] or query["tests"]
        assert query["command_traces"]
        assert query["service_boundaries"]
        schema_query = m.motoko_code_query("source lifecycle schema artifact version")
        assert any(row["name"] == "SOURCE_LIFECYCLE_REPORT_SCHEMA" for row in schema_query["constants"])
        rendered = m.format_motoko_code_query("Motoko skill plan command implementation tests")
        assert "Motoko code query:" in rendered
        assert "command traces:" in rendered
        assert "constants:" in rendered
        assert "symbols:" in rendered
        map_rendered = m.format_motoko_code_map()
        assert "root facade hotspots:" in map_rendered
        assert "service boundaries:" in map_rendered
        assert "schema/artifact constants:" in map_rendered

        context_text, sources = m.render_motoko_codebase_context(
            "How should Motoko refactor its codebase command handlers?"
        )
        assert "Motoko code query:" in context_text
        assert any(row.get("kind") == "motoko-codebase" for row in sources)

        conv = m.new_conversation("Code query")
        command = m.shared_command_request("/code-query Motoko skill command implementation", conv)
        assert command is not None
        assert command.kind == m.COMMAND_KIND_REPORT
        _label, run = command
        assert "Motoko code query:" in run()


def test_self_improvement_eval_checks_codebase_skill_and_scanner(m):
    with isolated_state():
        report = m.run_self_improvement_eval()
        assert report["schema"] == "motoko-self-improvement-eval-v1"
        assert report["status"] == "pass"
        names = {row.get("name") for row in report.get("checks", [])}
        assert "code_query_finds_commands_symbols_tests" in names
        assert "self_improvement_umbrella_skills_present" in names
        assert "self_improvement_umbrella_skills_select" in names
        assert "motoko_codebase_skill_activates" in names
        assert "code_map_command_traces_link_tests" in names
        assert "code_map_relationships_present" in names
        assert "code_map_schema_constants_present" in names
        assert "code_query_finds_schema_constants" in names
        assert "code_query_finds_traces_and_services" in names
        assert "skill_scanner_detects_risky_script" in names
        umbrella = next(row for row in report.get("checks", []) if row.get("name") == "self_improvement_umbrella_skills_select")
        selected = umbrella.get("evidence", {}).get("selected", {})
        assert "motoko-retrieval-maintainer" in selected.get("motoko-retrieval-maintainer", [])
        assert "motoko-refactor-craft" in selected.get("motoko-refactor-craft", [])
        assert "motoko-agentic-boundary-review" in selected.get("motoko-agentic-boundary-review", [])
        docs_check = next(row for row in report.get("checks", []) if row.get("name") == "self_improvement_docs_present")
        assert "docs/motoko-self-improvement-playbook.md" in docs_check.get("evidence", {}).get("docs", [])
        rendered = m.format_self_improvement_eval(report)
        assert "self-improvement eval:" in rendered
        assert "status: pass" in rendered

        conv = m.new_conversation("Self eval")
        command = m.shared_command_request("/self-eval", conv)
        assert command is not None
        assert command.kind == m.COMMAND_KIND_REPORT
        _label, run = command
        assert "self-improvement eval:" in run()


def test_skill_scan_reports_script_risks(m):
    with isolated_state():
        m.learn_skill_text(
            "risky-skill",
            description="Risky skill",
            body="Use the helper in scripts/clean.py after review.",
        )
        m.manage_skill_text(
            action="write_file",
            name="risky-skill",
            file_path="scripts/clean.py",
            file_content="import subprocess\nsubprocess.run(['true'])\n",
        )
        report = m.skill_scan_report("risky-skill")
        assert report["status"] == "review"
        text = m.format_skill_scan("risky-skill")
        assert "subprocess_import" in text
        assert "subprocess_call" in text

        suite = m.format_skill_scan()
        assert "risky-skill" in suite
        conv = m.new_conversation("Skill scan")
        command = m.shared_command_request("/skill scan risky-skill", conv)
        assert command is not None
        assert command.kind == m.COMMAND_KIND_REPORT
        _label, run = command
        assert "skill scan: risky-skill" in run()


def test_skill_review_signal_recognizes_skill_candidate_language(m):
    with isolated_state():
        conv = m.new_conversation("Skill candidate")
        conv["messages"] = [
            {"role": "user", "content": "This pattern is worth turning into a skill for next time."},
            {"role": "assistant", "content": "I will treat it as reusable procedural knowledge."},
        ]
        reasons = m.skill_review_triggers(conv, message_count=len(conv["messages"]), last_skill=0)
        assert any(reason.startswith("explicit-signal:worth turning into a skill") for reason in reasons)


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


def test_project_scope_filters_memory_and_profile_context(m):
    with isolated_state():
        current = m.new_conversation("Current project")
        current["id"] = "current-project"
        write_conversation(m, current)
        other = m.new_conversation("Other project")
        other["id"] = "other-project"
        other["project"] = {"kind": "git", "root": "/tmp/not-this-project"}
        write_conversation(m, other)

        m.add_memory("Current project craft note.", source="test", conversation_id=current["id"])
        m.add_memory("Other project craft note.", source="test", conversation_id=other["id"])
        m.add_memory("Global craft preference.", source="test")

        scope = m.project_scope_for_request(current, "craft")
        text, sources = m.render_memories_with_sources(current, "craft", project_scope=scope)
        assert "Current project craft note" in text
        assert "Global craft preference" in text
        assert "Other project craft note" not in text
        assert not any(source.get("conversation_id") == other["id"] for source in sources)

        other_profile = {
            "updated": m.now(),
            "memory_ids": [],
            "conversation_ids": [other["id"]],
            "text": "Other project profile material.",
        }
        m.atomic_write(m.profile_path(), json.dumps(other_profile, ensure_ascii=False, indent=2) + "\n")
        profile_text, profile_sources = m.render_profile_with_sources(project_scope=scope)
        assert "Other project profile material" not in profile_text
        assert profile_sources == []


def test_core_profile_rendering_is_injectable(m):
    profile = {
        "updated": "2026-05-23T00:00:00+00:00",
        "memory_ids": ["mem-1", "mem-2"],
        "conversation_ids": ["conv-1"],
        "text": "Javier values grounded retrieval.",
    }

    text, sources = m.render_profile_with_sources_core(profile)
    report = m.format_profile_dossier(profile)

    assert text == "Javier values grounded retrieval."
    assert sources == [
        {
            "kind": "profile",
            "updated": "2026-05-23T00:00:00+00:00",
            "memory_count": 2,
            "conversation_count": 1,
        }
    ]
    assert "memories: 2" in report
    assert "conversations: 1" in report
    assert m.render_profile_with_sources_core(None)[1] == []
    assert "No profile dossier yet" in m.format_profile_dossier(None)


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


def test_core_dossier_formatters_are_injectable(m):
    dossier = {
        "id": "dossier-1",
        "created": "2026-05-23T00:00:00+00:00",
        "name": "Craft",
        "query": "craftsmanship",
        "summary": "Careful work.",
        "source_memory_count": 1,
        "source_conversation_count": 1,
        "source_memories": [{"id": "mem-1", "importance": 4, "score": 10, "excerpt": "Memory excerpt."}],
        "source_conversations": [{"id": "conv-1", "title": "Chat", "updated": "today", "excerpt": "Chat excerpt."}],
    }

    listing = m.format_dossiers_list([dossier])
    report = m.format_dossier_report_core(dossier, evidence=True)

    assert "dossier-1" in listing
    assert "1 memories" in listing
    assert "Craft [dossier-1]" in report
    assert "query> craftsmanship" in report
    assert "Memory Evidence:" in report
    assert "Memory excerpt." in report
    assert "Conversation Evidence:" in report
    assert m.format_dossiers_list([]) == "No memory dossiers yet."


def test_core_dossier_retrieval_is_injectable(m):
    dossier = {
        "id": "dossier-1",
        "name": "Craft",
        "query": "craftsmanship",
        "summary": "Careful work.",
        "source_memories": [
            {"id": "mem-other", "importance": 3, "score": 1, "source": "test", "excerpt": "Unrelated note."},
            {"id": "mem-hit", "importance": 5, "score": 9, "source": "test", "excerpt": "Grounded retrieval matters."},
        ],
        "source_conversations": [
            {"id": "conv-hit", "title": "Retrieval", "updated": "today", "selection": ["relevant"], "excerpt": "retrieval chat"},
        ],
    }

    text, sources = m.retrieve_from_dossier_core(dossier, "retrieval", max_chars=1000)

    assert "=== Memory dossier: Craft ===" in text
    assert text.index("mem-hit") < text.index("mem-other")
    assert "conversation:conv-hit" in text
    assert [source["kind"] for source in sources] == ["dossier", "dossier-memory", "dossier-memory", "dossier-conversation"]


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
    left = "bg-heavy: vectorizing(model) batch 29/129 parallel 32 rows 2700/10525 eta 1m50s"
    right = "bg-heavy: vectorizing(model) batch 30/129 parallel 32 rows 2780/10525 eta 1m45s"
    assert m.phase_timer_key(left) == m.phase_timer_key(right)
    assert m.phase_timer_key(left) == "bg-heavy: vectorizing(model)"
    incremental = "bg-heavy: vectorizing(model) incremental reuse 9000 new 25 batch 1/2 parallel 32 rows 9012/9025 eta 2s"
    assert m.phase_timer_key(incremental) == "bg-heavy: vectorizing(model)"
    full = "bg-heavy: vectorizing(model) full missing new 160 batch 0/5 parallel 32 rows 0/160 eta ?"
    assert m.phase_timer_key(full) == "bg-heavy: vectorizing(model)"
    resumed = "bg-heavy: vectorizing(model) resumed checkpoint reuse 80 new 80 batch 2/5 parallel 32 rows 80/160 eta 2m00s"
    assert m.phase_timer_key(resumed) == "bg-heavy: vectorizing(model)"
    assert m.phase_timer_key("study: planning") != m.phase_timer_key(left)


def test_vector_progress_phase_is_content_free_and_finalizing(m):
    line = m.format_vector_progress_phase(
        completed_batches=2,
        total_batches=5,
        active_parallelism=32,
        completed_rows=64,
        total_rows=160,
        eta_seconds=120,
    )
    assert line == "bg-heavy: vectorizing(model) batch 2/5 parallel 32 rows 64/160 eta 2m00s"
    assert "orgfiles" not in line
    assert "logbook" not in line

    incremental = m.format_vector_progress_phase(
        completed_batches=0,
        total_batches=1,
        active_parallelism=32,
        completed_rows=150,
        total_rows=160,
        eta_seconds=None,
        reused_rows=150,
        pending_rows=10,
    )
    assert incremental == "bg-heavy: vectorizing(model) incremental reuse 150 new 10 batch 0/1 parallel 32 rows 150/160 eta ?"

    full = m.format_vector_progress_phase(
        completed_batches=0,
        total_batches=5,
        active_parallelism=32,
        completed_rows=0,
        total_rows=160,
        eta_seconds=None,
        refresh_mode="full",
        refresh_cause="missing",
    )
    assert full == "bg-heavy: vectorizing(model) full missing new 160 batch 0/5 parallel 32 rows 0/160 eta ?"

    resumed = m.format_vector_progress_phase(
        completed_batches=2,
        total_batches=5,
        active_parallelism=32,
        completed_rows=80,
        total_rows=160,
        eta_seconds=120,
        reused_rows=80,
        pending_rows=80,
        refresh_mode="resumed",
        refresh_cause="checkpoint",
    )
    assert resumed == "bg-heavy: vectorizing(model) resumed checkpoint reuse 80 new 80 batch 2/5 parallel 32 rows 80/160 eta 2m00s"

    finalizing = m.format_vector_progress_phase(
        completed_batches=5,
        total_batches=5,
        active_parallelism=32,
        completed_rows=160,
        total_rows=160,
        state="finalizing",
    )
    assert finalizing == "bg-heavy: vectorizing finalizing rows 160/160"
    sanitized = m.sanitize_background_phase(
        "bg-heavy: vectorizing(model) orgfiles incremental reuse 150 new 10 batch 0/1 parallel 32 rows 150/160 eta ?"
    )
    assert sanitized == "bg-heavy: vectorizing(model) incremental reuse 150 new 10 batch 0/1 parallel 32 rows 150/160 eta ?"
    assert "orgfiles" not in sanitized
    sanitized_full = m.sanitize_background_phase(
        "bg-heavy: vectorizing(model) orgfiles full missing new 160 batch 0/5 parallel 32 rows 0/160 eta ?"
    )
    assert sanitized_full == "bg-heavy: vectorizing(model) full missing new 160 batch 0/5 parallel 32 rows 0/160 eta ?"


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
        assert "/tips" in help_text
        assert "Enter or Esc" in help_text
        tips = m.format_tips()
        assert "Daily use:" in tips
        assert "/sources" in tips
        assert "Evals are specialized health checks" in tips
        about = m.format_about()
        assert "Motoko" in about
        assert "privacy- and security-conscious" in about
        assert "local corpora, memory, and repo review" in about
        assert "model badge:" in about
        assert "values: intelligence, competence, craft" in about
        assert "$$$$$_" in about
        assert about.index("$$$$$_") < about.index("Motoko")
        assert about.index("Motoko") < about.index("values:")
        assert about.index("values:") < about.index("version:")
        assert about.index("version:") < about.index("revision:")
        logo_rows = [m.strip_ansi(row) for row in m.format_about_header(width=90)[:6]]
        logo_left_pads = [len(row) - len(row.lstrip(" ")) for row in logo_rows]
        assert len(set(logo_left_pads)) == 1
        assert logo_left_pads == [0] * len(logo_left_pads)
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


class SlotCacheHandler(BaseHTTPRequestHandler):
    payloads = []
    paths = []
    slot_payloads = []
    slot_root = None
    slot_file_size = 0

    def do_POST(self):  # noqa: N802 - stdlib handler API
        self.__class__.paths.append(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            payload = {}
        if self.path.startswith("/slots/"):
            self.__class__.slot_payloads.append((self.path, payload))
            action = self.path.split("action=", 1)[-1]
            if action.startswith("save") and self.__class__.slot_root and payload.get("filename"):
                slot_path = pathlib.Path(self.__class__.slot_root) / pathlib.PurePath(payload["filename"]).name
                slot_path.parent.mkdir(parents=True, exist_ok=True)
                slot_path.write_bytes(b"x" * int(self.__class__.slot_file_size or 0))
            response = {
                "id_slot": 0,
                "filename": payload.get("filename", ""),
                "n_saved": 123 if action.startswith("save") else 0,
                "n_restored": 123 if action.startswith("restore") else 0,
                "n_written": int(self.__class__.slot_file_size or 456),
                "n_read": 456,
                "n_erased": 123 if action.startswith("erase") else 0,
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
            return
        self.__class__.payloads.append(payload)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        event = {"choices": [{"delta": {"content": "OK"}}]}
        self.wfile.write(f"data: {json.dumps(event)}\n\n".encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *_args):
        return


class SlotCacheFailingHandler(SlotCacheHandler):
    def do_POST(self):  # noqa: N802 - stdlib handler API
        self.__class__.paths.append(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            payload = {}
        if self.path.startswith("/slots/"):
            self.__class__.slot_payloads.append((self.path, payload))
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"slot unavailable"}}')
            return
        self.__class__.payloads.append(payload)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        event = {"choices": [{"delta": {"content": "OK"}}]}
        self.wfile.write(f"data: {json.dumps(event)}\n\n".encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")


class ReasoningHandler(BaseHTTPRequestHandler):
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
        for event in (
            {"choices": [{"delta": {"reasoning_content": "checking "}}]},
            {"choices": [{"delta": {"reasoning_content": "sources"}}]},
            {"choices": [{"delta": {"content": "OK"}}]},
        ):
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


def test_chat_reasoning_payload_and_stream(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_reasoning = os.environ.get(m.REASONING_MODE_ENV)
    ReasoningHandler.payloads = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), ReasoningHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with isolated_state():
            os.environ["MOTOKO_ENDPOINT"] = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
            os.environ[m.REASONING_MODE_ENV] = "high"
            tokens = []
            reasoning = []
            text = m.call_model_with_callback(
                [{"role": "user", "content": "hello"}],
                on_token=tokens.append,
                on_reasoning=reasoning.append,
                timeout=2,
            )
            assert text == "OK"
            assert tokens == ["OK"]
            assert reasoning == ["checking ", "sources"]
            payload = ReasoningHandler.payloads[-1]
            assert payload["reasoning_format"] == "deepseek"
            assert payload["chat_template_kwargs"]["enable_thinking"] is True
            assert payload["thinking_budget_tokens"] == 16384
            record = m.read_last_model_call()
            assert record["reasoning_mode"] == "high"
            assert record["thinking_budget_tokens"] == 16384
            assert "checking" not in json.dumps(record)
            ReasoningHandler.payloads = []
            worker_tokens = []
            worker_text = m.call_model_with_callback(
                [{"role": "user", "content": "hello"}],
                on_token=worker_tokens.append,
                route=m.MODEL_ROUTE_MEMORY,
                timeout=2,
            )
            assert worker_text == "OK"
            assert worker_tokens == ["OK"]
            worker_payload = ReasoningHandler.payloads[-1]
            assert "reasoning_format" not in worker_payload
            assert "thinking_budget_tokens" not in worker_payload
            assert "chat_template_kwargs" not in worker_payload
    finally:
        server.shutdown()
        server.server_close()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_reasoning is None:
            os.environ.pop(m.REASONING_MODE_ENV, None)
        else:
            os.environ[m.REASONING_MODE_ENV] = old_reasoning


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
                    "qwen36-chat-default": {
                        "endpoint": "unix:///run/motoko-llm/mares/qwen36-chat-default.sock",
                        "modelId": "qwen3.6-27b-ud-q4-k-xl",
                        "tasks": ["chat", "default_chat", "deep_synthesis"],
                        "route_profile": "default",
                        "role": "normal chat/default workhorse",
                        "context_tokens": 131072,
                        "kv_offload": True,
                        "kv_cache": {"location": "gpu"},
                        "selection": {"default": True, "priority": 100},
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
            assert chat["catalog_route"] == "qwen36-chat-default"
            assert chat["route_profile"] == "default"
            assert chat["kv_cache"]["location"] == "gpu"
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


def test_slot_cache_capability_respects_route_gates(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        with isolated_state() as tmp:
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen36-chat-default": {
                        "endpoint": f"unix://{tmp / 'chat.sock'}",
                        "modelId": "qwen3.6-27b-ud-q4-k-xl",
                        "tasks": ["chat", "default_chat"],
                        "route_profile": "default",
                        "context_tokens": 131072,
                        "selection": {"default": True},
                        "cache": {
                            "prompt": True,
                            "persistentSlotCache": True,
                            "slotsEndpoint": True,
                            "slotSavePath": str(tmp / "slots"),
                        },
                        "safety_policy": {"disabled_server_surfaces": ["tools", "slots_endpoint"]},
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")

            route = m.model_route(m.MODEL_ROUTE_CHAT)
            assert route["cache"]["slotsEndpoint"] is True
            assert route["cache"]["slotSavePath"] == str(tmp / "slots")
            capability = m.slot_cache_capability(route)
            assert capability["supported"] is False
            assert any("disables slot surfaces" in reason for reason in capability["reasons"])
            report = m.format_model_services("qwen36-chat-default")
            assert "persistent-slots=declared" in report
            assert "slots-endpoint=on" in report
            assert f"slot-save-path={tmp / 'slots'}" in report
    finally:
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model


def test_persistent_slot_cache_saves_and_restores_chat_slot(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    socket_path = None
    SlotCacheHandler.payloads = []
    SlotCacheHandler.paths = []
    SlotCacheHandler.slot_payloads = []
    SlotCacheHandler.slot_root = None
    SlotCacheHandler.slot_file_size = 0
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        with isolated_state() as tmp:
            socket_path = tmp / "chat-slot.sock"
            server = UnixHTTPServer(str(socket_path), SlotCacheHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen36-chat-default": {
                        "endpoint": f"unix://{socket_path}",
                        "modelId": "qwen3.6-27b-ud-q4-k-xl",
                        "model": "qwen-slot-test",
                        "tasks": ["chat", "default_chat"],
                        "route_profile": "default",
                        "context_tokens": 131072,
                        "selection": {"default": True},
                        "maxParallel": 1,
                        "cache": {
                            "prompt": True,
                            "persistentSlotCache": True,
                            "slotsEndpoint": True,
                            "slotSavePath": str(tmp / "slots"),
                        },
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")

            tokens = []
            first = m.call_model_with_callback(
                [{"role": "user", "content": "hello slot cache"}],
                on_token=tokens.append,
                timeout=2,
                slot_cache_context={"conversation_id": "conv-slot", "client_namespace": "fixture-chat-v1"},
            )
            assert first == "OK"
            assert SlotCacheHandler.payloads[-1]["id_slot"] == 0
            assert SlotCacheHandler.payloads[-1]["cache_prompt"] is True
            assert any(path == "/slots/0?action=save" for path, _payload in SlotCacheHandler.slot_payloads)
            manifest_text = m.slot_cache_manifest_path().read_text(encoding="utf-8")
            assert "hello slot cache" not in manifest_text
            assert "conv-slot" in manifest_text
            assert "fixture-chat-v1" in manifest_text
            first_record = m.read_last_model_call()
            assert first_record["slot_cache_status"] == "supported"
            assert first_record["slot_cache_restore"] == "miss"
            assert first_record["slot_cache_save"] == "saved"
            assert first_record["slot_cache_namespace"] == "fixture-chat-v1"

            SlotCacheHandler.payloads = []
            SlotCacheHandler.slot_payloads = []
            second = m.call_model_with_callback(
                [{"role": "user", "content": "hello slot cache followup"}],
                on_token=lambda _token: None,
                timeout=2,
                slot_cache_context={"conversation_id": "conv-slot", "client_namespace": "fixture-chat-v1"},
            )
            assert second == "OK"
            paths = [path for path, _payload in SlotCacheHandler.slot_payloads]
            assert "/slots/0?action=restore" in paths
            assert "/slots/0?action=save" in paths
            assert SlotCacheHandler.payloads[-1]["id_slot"] == 0
            second_record = m.read_last_model_call()
            assert second_record["slot_cache_restore"] == "restored"
            assert second_record["slot_cache_save"] == "saved"
            assert second_record["slot_cache_n_restored"] == 123

            SlotCacheHandler.payloads = []
            SlotCacheHandler.slot_payloads = []
            third = m.call_model_with_callback(
                [{"role": "user", "content": "hello slot cache new prompt namespace"}],
                on_token=lambda _token: None,
                timeout=2,
                slot_cache_context={"conversation_id": "conv-slot", "client_namespace": "fixture-chat-v2"},
            )
            assert third == "OK"
            third_paths = [path for path, _payload in SlotCacheHandler.slot_payloads]
            assert "/slots/0?action=restore" not in third_paths
            assert "/slots/0?action=save" in third_paths
            third_record = m.read_last_model_call()
            assert third_record["slot_cache_restore"] == "miss"
            assert third_record["slot_cache_namespace"] == "fixture-chat-v2"
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


def test_slot_cache_budget_profile_can_disable_saves(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    socket_path = None
    SlotCacheHandler.payloads = []
    SlotCacheHandler.paths = []
    SlotCacheHandler.slot_payloads = []
    SlotCacheHandler.slot_root = None
    SlotCacheHandler.slot_file_size = 0
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        with isolated_state() as tmp:
            socket_path = tmp / "chat-slot-budget-off.sock"
            server = UnixHTTPServer(str(socket_path), SlotCacheHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            catalog = {
                "realm": "test",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen36-chat-default": {
                        "endpoint": f"unix://{socket_path}",
                        "model": "qwen-slot-test",
                        "tasks": ["chat", "default_chat"],
                        "selection": {"default": True},
                        "cache": {
                            "prompt": True,
                            "persistentSlotCache": True,
                            "slotsEndpoint": True,
                            "slotSavePath": str(tmp / "slots"),
                            "slotCacheBudgetProfile": "off",
                        },
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            text = m.call_model_with_callback(
                [{"role": "user", "content": "budget off"}],
                on_token=lambda _token: None,
                timeout=2,
                slot_cache_context={"conversation_id": "conv-budget-off"},
            )
            assert text == "OK"
            assert not any(path == "/slots/0?action=save" for path, _payload in SlotCacheHandler.slot_payloads)
            record = m.read_last_model_call()
            assert record["slot_cache_save"] == "skipped-budget-disabled"
            assert record["slot_cache_budget_profile"] == "off"
            server.shutdown()
            server.server_close()
    finally:
        if socket_path is not None:
            with contextlib.suppress(OSError):
                pathlib.Path(socket_path).unlink()
        SlotCacheHandler.slot_root = None
        SlotCacheHandler.slot_file_size = 0
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model


def test_slot_cache_budget_gc_removes_old_records(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    socket_path = None
    SlotCacheHandler.payloads = []
    SlotCacheHandler.paths = []
    SlotCacheHandler.slot_payloads = []
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        with isolated_state() as tmp:
            slot_root = tmp / "slots"
            SlotCacheHandler.slot_root = slot_root
            SlotCacheHandler.slot_file_size = 700
            socket_path = tmp / "chat-slot-budget.sock"
            server = UnixHTTPServer(str(socket_path), SlotCacheHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            catalog = {
                "realm": "test",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen36-chat-default": {
                        "endpoint": f"unix://{socket_path}",
                        "model": "qwen-slot-test",
                        "tasks": ["chat", "default_chat"],
                        "selection": {"default": True},
                        "cache": {
                            "prompt": True,
                            "persistentSlotCache": True,
                            "slotsEndpoint": True,
                            "slotSavePath": str(slot_root),
                            "slotCacheBudgetProfile": "tiny",
                        },
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            for conv_id in ("conv-a", "conv-b"):
                assert (
                    m.call_model_with_callback(
                        [{"role": "user", "content": f"cache for {conv_id}"}],
                        on_token=lambda _token: None,
                        timeout=2,
                        slot_cache_context={"conversation_id": conv_id},
                    )
                    == "OK"
                )
            manifest = m.read_slot_cache_manifest()
            records = manifest["records"]
            assert len(records) == 1
            assert records[0]["conversation_id"] == "conv-b"
            assert m.slot_cache_usage(records)["bytes"] <= 700
            record = m.read_last_model_call()
            assert record["slot_cache_budget"] == "within-budget"
            assert record["slot_cache_budget_profile"] == "tiny"
            assert record["slot_cache_budget_bytes"] == 700
            assert record["slot_cache_budget_files_deleted"] == 1
            server.shutdown()
            server.server_close()
    finally:
        if socket_path is not None:
            with contextlib.suppress(OSError):
                pathlib.Path(socket_path).unlink()
        SlotCacheHandler.slot_root = None
        SlotCacheHandler.slot_file_size = 0
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model


def test_slot_cache_budget_reports_service_owned_gc(m):
    with isolated_state() as tmp:
        slot_root = tmp / "service-slots"
        slot_root.mkdir()
        route_info = {
            "route": "chat",
            "catalog_route": "qwen36-chat-default",
            "endpoint": "unix:///tmp/motoko-slot-service.sock",
            "model": "qwen-slot-test",
            "cache": {
                "prompt": True,
                "persistentSlotCache": True,
                "slotsEndpoint": True,
                "slotSavePath": str(slot_root),
                "slotCacheMaxBytes": 1000,
            },
        }
        rows = []
        for idx, conv_id in enumerate(("conv-a", "conv-b"), 1):
            filename = f"motoko-slot-service-{idx}.bin"
            (slot_root / filename).write_bytes(b"x" * 700)
            rows.append(
                {
                    "schema": "slot-kv-cache-v1",
                    "status": "saved",
                    "created": f"2026-05-25T00:00:0{idx}Z",
                    "updated": f"2026-05-25T00:00:0{idx}Z",
                    "last_used": f"2026-05-25T00:00:0{idx}Z",
                    "conversation_id": conv_id,
                    "catalog_route": "qwen36-chat-default",
                    "route": "chat",
                    "route_fingerprint": "fingerprint",
                    "filename": filename,
                    "slot_save_path_declared": str(slot_root),
                    "file_size_bytes": 700,
                }
            )
        m.ensure_private_dir(m.slot_cache_manifest_path().parent)
        m.atomic_write(
            m.slot_cache_manifest_path(),
            json.dumps(
                {
                    "schema": "slot-kv-cache-manifest-v1",
                    "updated": "2026-05-25T00:00:03Z",
                    "records": rows,
                },
                ensure_ascii=False,
            )
            + "\n",
        )
        old_access = slot_cache_core.os.access
        try:
            slot_cache_core.os.access = lambda path, mode: False if pathlib.Path(path) == slot_root else old_access(path, mode)
            report = slot_cache_core.enforce_slot_cache_budget(route_info)
            assert report["status"] == "needs-service-gc"
            assert report["service_gc_required"] is True
            assert report["service_owned_records"] >= 1
            assert report["records_removed"] == 0
            assert len(m.read_slot_cache_manifest()["records"]) == 2
            cleared = m.clear_slot_cache_records(route_name="qwen36-chat-default", yes=True)
            assert cleared["status"] == "needs-service-gc"
            assert cleared["records_removed"] == 0
            assert cleared["service_owned_records"] == 2
            assert len(m.read_slot_cache_manifest()["records"]) == 2
        finally:
            slot_cache_core.os.access = old_access


def test_cross_home_action_policy_is_config_driven(m):
    with isolated_state():
        target = pathlib.Path("/home/motoko-other/private/file.org")
        try:
            m.require_not_cross_home(target)
        except m.AgenticValidationError as exc:
            assert "security.allow_cross_home_paths" in str(exc)
        else:
            raise AssertionError("cross-home path should be denied by default")
        m.ensure_private_dir(m.config_root())
        m.atomic_write(
            m.config_path(),
            json.dumps(
                {
                    "security": {
                        "allow_cross_home_paths": ["/home/motoko-other/private"],
                    }
                },
                ensure_ascii=False,
            )
            + "\n",
        )
        m.require_not_cross_home(target)


def test_slot_cache_failures_are_nonfatal_cache_misses(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    socket_path = None
    SlotCacheFailingHandler.payloads = []
    SlotCacheFailingHandler.paths = []
    SlotCacheFailingHandler.slot_payloads = []
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        with isolated_state() as tmp:
            socket_path = tmp / "chat-slot-failing.sock"
            server = UnixHTTPServer(str(socket_path), SlotCacheFailingHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen36-chat-default": {
                        "endpoint": f"unix://{socket_path}",
                        "model": "qwen-slot-test",
                        "tasks": ["chat", "default_chat"],
                        "route_profile": "default",
                        "context_tokens": 131072,
                        "selection": {"default": True},
                        "cache": {
                            "prompt": True,
                            "persistentSlotCache": True,
                            "slotsEndpoint": True,
                            "slotSavePath": str(tmp / "slots"),
                        },
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            text = m.call_model_with_callback(
                [{"role": "user", "content": "slot save can fail"}],
                on_token=lambda _token: None,
                timeout=2,
                slot_cache_context={"conversation_id": "conv-slot-fail"},
            )
            assert text == "OK"
            record = m.read_last_model_call()
            assert record["status"] == "completed"
            assert record["slot_cache_save"] == "failed"
            assert record["slot_cache_save_error_type"] in {"OSError", "URLError"}
            assert m.read_slot_cache_manifest()["records"] == []
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


def test_catalog_request_policy_shapes_chat_payload_and_telemetry(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    FakeHandler.payloads = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        with isolated_state():
            policy = {
                "sampling_presets": {
                    "balanced": {
                        "temperature": 0.6,
                        "top_p": 0.9,
                        "min_p": 0.05,
                        "repeat_penalty": 1.05,
                    },
                    "deterministic": {
                        "temperature": 0.1,
                        "top_p": 0.8,
                        "min_p": 0.0,
                        "repeat_penalty": 1.0,
                    },
                },
                "structured_output": {
                    "supported": True,
                    "json_schema_field": "json_schema",
                    "grammar_field": "grammar",
                },
                "reasoning": {
                    "supported": True,
                    "format": "deepseek",
                    "per_request_budget_field": "thinking_budget_tokens",
                    "per_request_enable_field": "chat_template_kwargs.enable_thinking",
                    "presets": {
                        "default": {
                            "enable_thinking": True,
                            "thinking_budget_tokens": 4096,
                        },
                        "high": {
                            "enable_thinking": True,
                            "thinking_budget_tokens": 16384,
                        },
                    },
                },
                "cache_measurement": {"supported": True},
            }
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen36-chat": {
                        "endpoint": f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                        "modelId": "qwen3.6-27b-mtp-ud-q4-k-xl",
                        "tasks": ["chat", "deep_synthesis"],
                        "request_policy": policy,
                        "scheduling": {"lane": "large-model", "parallelSlots": 1, "fanout": False},
                        "idle_seconds": 300,
                        "safety_policy": {"disabled_server_surfaces": ["tools", "props", "slots"]},
                    },
                    "qwen35-2b-worker": {
                        "endpoint": f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                        "modelId": "qwen3.5-2b-q4-k-m",
                        "tasks": ["memory_maintenance"],
                        "request_policy": policy,
                        "scheduling": {"lane": "small-model", "parallelSlots": 8, "fanout": True},
                        "idle_seconds": 45,
                    },
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")

            reply = m.quiet_model([{"role": "user", "content": "hello"}], timeout=2)
            assert reply == "hello"
            chat_payload = FakeHandler.payloads[-1]
            assert chat_payload["model"] == "qwen3.6-27b-mtp-ud-q4-k-xl"
            assert chat_payload["temperature"] == 0.6
            assert chat_payload["top_p"] == 0.9
            assert chat_payload["min_p"] == 0.05
            assert chat_payload["repeat_penalty"] == 1.05
            assert chat_payload["chat_template_kwargs"]["enable_thinking"] is True
            assert chat_payload["thinking_budget_tokens"] == 4096
            record = m.read_last_model_call()
            assert record["sampling_preset"] == "balanced"
            assert record["reasoning_preset"] == "default"
            assert record["thinking_budget_tokens"] == 4096
            assert record["cache_measurement_supported"] is True
            assert "hello" not in json.dumps(record, ensure_ascii=False)

            schema = {"type": "object", "properties": {"memories": {"type": "array"}}}
            _ = m.quiet_model(
                [{"role": "user", "content": "extract memory"}],
                timeout=2,
                route=m.MODEL_ROUTE_MEMORY,
                sampling_preset="deterministic",
                json_schema=schema,
                reasoning_preset="high",
            )
            memory_payload = FakeHandler.payloads[-1]
            assert memory_payload["model"] == "qwen3.5-2b-q4-k-m"
            assert memory_payload["temperature"] == 0.1
            assert memory_payload["json_schema"] == schema
            assert memory_payload["thinking_budget_tokens"] == 16384

            routes = m.format_model_routes(include_defaults=True)
            assert "request sampling=balanced/deterministic" in routes
            assert "structured=on(json_schema,grammar)" in routes
            assert "reasoning=on:deepseek/default/high" in routes
            assert "scheduling idle=300s" in routes
            assert "safety disabled=tools/props/slots" in routes
    finally:
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


def test_chat_context_governor_selects_declared_route_profiles(m):
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
                    "qwen36-chat-default": {
                        "endpoint": "unix:///run/motoko-llm/mares/qwen36-chat-default.sock",
                        "modelId": "qwen3.6-27b-ud-q4-k-xl",
                        "tasks": ["chat", "default_chat", "deep_synthesis"],
                        "route_profile": "default",
                        "context_tokens": 131072,
                        "kv_offload": True,
                        "kv_cache": {"location": "gpu"},
                        "selection": {"default": True, "priority": 100},
                    },
                    "qwen36-chat-quality": {
                        "endpoint": "unix:///run/motoko-llm/mares/qwen36-chat-quality.sock",
                        "modelId": "qwen3.6-27b-mtp-ud-q5-k-xl",
                        "tasks": ["chat", "quality_chat", "short_context_chat", "deep_synthesis"],
                        "route_profile": "quality",
                        "context_tokens": 65536,
                        "kv_offload": True,
                        "kv_cache": {"location": "gpu"},
                        "selection": {"priority": 80},
                    },
                    "qwen36-chat-deep": {
                        "endpoint": "unix:///run/motoko-llm/mares/qwen36-chat-deep.sock",
                        "modelId": "qwen3.6-27b-ud-q4-k-xl",
                        "tasks": ["chat", "long_context_chat", "deep_synthesis"],
                        "route_profile": "deep",
                        "context_tokens": 131072,
                        "kv_offload": True,
                        "kv_cache": {"location": "gpu"},
                        "selection": {"priority": 70},
                    },
                    "qwen36-chat-max": {
                        "endpoint": "unix:///run/motoko-llm/mares/qwen36-chat-max.sock",
                        "modelId": "qwen3.6-27b-ud-q4-k-xl",
                        "tasks": ["chat", "max_context_chat", "deep_synthesis"],
                        "route_profile": "max",
                        "context_tokens": 262144,
                        "kv_offload": False,
                        "kv_cache": {"location": "host-ram"},
                        "selection": {"priority": 30},
                    },
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")

            small, small_governor = m.select_chat_route([{"role": "user", "content": "hello"}])
            assert small["catalog_route"] == "qwen36-chat-default"
            assert small_governor["selected_tier"] == "chat_default"
            assert not m.route_kv_offload_disabled(small)

            quality, quality_governor = m.select_chat_route(
                [{"role": "user", "content": "hello"}],
                mode="quality",
            )
            assert quality["catalog_route"] == "qwen36-chat-quality"
            assert quality_governor["selected_tier"] == "chat_quality"

            medium = [{"role": "user", "content": "x" * ((m.CHAT_CONTEXT_DEFAULT_SOFT_TOKENS + 1000) * 4)}]
            deep, deep_governor = m.select_chat_route(medium)
            assert deep["catalog_route"] == "qwen36-chat-deep"
            assert deep_governor["selected_tier"] == "chat_deep"

            large = [{"role": "user", "content": "x" * ((m.CHAT_CONTEXT_DEEP_SOFT_TOKENS + 1000) * 4)}]
            selected, governor = m.select_chat_route(large)
            assert selected["catalog_route"] == "qwen36-chat-max"
            assert governor["selected_tier"] == "chat_max"
            assert governor["max_route_available"] is True
            assert m.route_kv_offload_disabled(selected)
            assert "Chat context governor:" in m.format_model_routes(include_defaults=True)
            assert "profile=default" in m.format_model_routes(include_defaults=True)
    finally:
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model


def test_chat_context_governor_falls_back_without_max_profile(m):
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
                        "args": ["--ctx-size", "131072"],
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            large = [{"role": "user", "content": "x" * ((m.CHAT_CONTEXT_DEEP_SOFT_TOKENS + 1000) * 4)}]
            selected, governor = m.select_chat_route(large)
            assert selected["catalog_route"] == "qwen36-chat"
            assert governor["preferred_tier"] == "chat_max"
            assert "max route unavailable" in governor["reason"]
    finally:
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model


def test_route_kv_offload_notice_detects_catalog_flag(m):
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
                    "qwen36-chat-max": {
                        "endpoint": "unix:///run/motoko-llm/mares/qwen36-chat-max.sock",
                        "modelId": "qwen3.6-27b-ud-q4-k-xl",
                        "tasks": ["chat", "max_context_chat", "deep_synthesis"],
                        "route_profile": "max",
                        "context_tokens": 262144,
                        "kv_offload": False,
                        "kv_cache": {"location": "host-ram"},
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            route, _governor = m.select_chat_route([{"role": "user", "content": "hello"}], mode="max")
            assert m.route_kv_offload_disabled(route)
    finally:
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model


def test_tui_kv_notice_blinks_for_three_seconds(m):
    ui = object.__new__(m.MotokoTui)
    ui.kv_notice_started_monotonic = 100.0
    ui.kv_notice_until_monotonic = 103.0
    assert ui.kv_notice_visible(100.1)
    assert not ui.kv_notice_visible(100.6)
    assert ui.kv_notice_visible(101.1)
    assert not ui.kv_notice_active(103.1)


def test_last_call_telemetry_is_content_free(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    FakeHandler.payloads = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        os.environ["MOTOKO_ENDPOINT"] = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
        with isolated_state():
            reply = m.call_model(
                [{"role": "user", "content": "secret phrase that must not be stored"}],
                echo=False,
                timeout=2,
                source_count=3,
            )
            assert reply == "hello"
            record = m.read_last_model_call()
            assert record["status"] == "completed"
            assert record["source_count"] == 3
            serialized = json.dumps(record, ensure_ascii=False)
            assert "secret phrase" not in serialized
            assert "hello" not in serialized
            text = m.format_last_model_call(record)
            assert "last model call:" in text
            assert "estimated prompt tok" in text
    finally:
        server.shutdown()
        server.server_close()
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint


def test_context_bench_dry_run_uses_governor_without_model_call(m):
    with isolated_state():
        report = m.run_context_bench(dry_run=True, targets=[1000])
        assert report["dry_run"] is True
        assert report["rows"][0]["estimated_prompt_tokens"] > 0
        assert "dry-run" in m.format_context_bench(report)


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


def test_worker_route_releases_idle_large_chat_route(m):
    with isolated_state() as tmp:
        socket_dir = tmp / "sockets"
        socket_dir.mkdir()
        catalog = {
            "realm": "mares",
            "manager": {"kind": "systemd-socket-worker"},
            "routes": {
                "qwen36-chat-default": {
                    "endpoint": f"unix://{socket_dir / 'qwen36-chat-default.sock'}",
                    "modelId": "qwen3.6-27b-mtp-ud-q4-k-xl",
                    "tasks": ["chat", "default_chat"],
                    "route_profile": "default",
                    "selection": {"default": True, "priority": 100},
                    "scheduling": {"exclusiveLane": "large-chat", "parallelSlots": 1, "fanout": False},
                },
                "qwen35-2b-worker": {
                    "endpoint": f"unix://{socket_dir / 'qwen35-2b-worker.sock'}",
                    "modelId": "qwen3.5-2b-q4-k-m",
                    "tasks": ["memory_maintenance"],
                    "scheduling": {"parallelSlots": 8, "fanout": True},
                },
            },
        }
        m.ensure_private_dir(m.config_root())
        m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")

        old_status = m.local_model_status_text
        old_run_helper = m.run_local_model_helper
        calls = []
        try:
            m.local_model_status_text = lambda info: (
                "route=qwen36-chat-default\nsocket=active\nproxy=active\nbackend=active\nactive_requests=0\n"
                if m.local_model_helper_route(info) == "qwen36-chat-default"
                else "route=qwen35-2b-worker\nsocket=active\nproxy=inactive\nbackend=inactive\n"
            )

            def fake_run_helper(command, info, *, timeout=m.LOCAL_MODEL_HELPER_TIMEOUT_SECONDS):
                calls.append((command, m.local_model_helper_route(info)))
                return "stopped"

            m.run_local_model_helper = fake_run_helper
            worker = m.model_route(m.MODEL_ROUTE_MEMORY)
            notes = m.prepare_worker_route_residency(worker)
            assert notes == ["released qwen36-chat-default"]
            assert calls == [("stop", "qwen36-chat-default")]
        finally:
            m.local_model_status_text = old_status
            m.run_local_model_helper = old_run_helper


def test_worker_route_defers_when_large_chat_route_is_busy(m):
    with isolated_state() as tmp:
        socket_dir = tmp / "sockets"
        socket_dir.mkdir()
        catalog = {
            "realm": "mares",
            "manager": {"kind": "systemd-socket-worker"},
            "routes": {
                "qwen36-chat-default": {
                    "endpoint": f"unix://{socket_dir / 'qwen36-chat-default.sock'}",
                    "modelId": "qwen3.6-27b-mtp-ud-q4-k-xl",
                    "tasks": ["chat", "default_chat"],
                    "route_profile": "default",
                    "selection": {"default": True, "priority": 100},
                    "scheduling": {"exclusiveLane": "large-chat", "parallelSlots": 1, "fanout": False},
                },
                "qwen35-2b-worker": {
                    "endpoint": f"unix://{socket_dir / 'qwen35-2b-worker.sock'}",
                    "modelId": "qwen3.5-2b-q4-k-m",
                    "tasks": ["memory_maintenance"],
                    "scheduling": {"parallelSlots": 8, "fanout": True},
                },
            },
        }
        m.ensure_private_dir(m.config_root())
        m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")

        old_status = m.local_model_status_text
        old_run_helper = m.run_local_model_helper
        calls = []
        try:
            m.local_model_status_text = lambda info: (
                "route=qwen36-chat-default\nsocket=active\nproxy=active\nbackend=active\nactive_requests=1\n"
                if m.local_model_helper_route(info) == "qwen36-chat-default"
                else "route=qwen35-2b-worker\nsocket=active\nproxy=inactive\nbackend=inactive\n"
            )
            m.run_local_model_helper = lambda command, info, **_kwargs: calls.append(
                (command, m.local_model_helper_route(info))
            )
            worker = m.model_route(m.MODEL_ROUTE_MEMORY)
            try:
                m.prepare_worker_route_residency(worker)
            except m.RouteResidencyBusy as exc:
                assert "queued behind active chat route qwen36-chat-default" in str(exc)
            else:
                raise AssertionError("busy large chat route should defer worker route")
            assert calls == []
        finally:
            m.local_model_status_text = old_status
            m.run_local_model_helper = old_run_helper


def test_worker_route_waits_for_recent_large_chat_grace(m):
    with isolated_state() as tmp:
        socket_dir = tmp / "sockets"
        catalog = {
            "realm": "mares",
            "manager": {"kind": "systemd-socket-worker"},
            "routes": {
                "qwen36-chat-default": {
                    "endpoint": f"unix://{socket_dir / 'qwen36-chat-default.sock'}",
                    "modelId": "qwen3.6-27b-mtp-ud-q4-k-xl",
                    "tasks": ["chat", "default_chat"],
                    "route_profile": "default",
                    "selection": {"default": True, "priority": 100},
                    "idle_seconds": 120,
                    "scheduling": {"exclusiveLane": "large-chat", "parallelSlots": 1, "fanout": False},
                },
                "qwen35-2b-worker": {
                    "endpoint": f"unix://{socket_dir / 'qwen35-2b-worker.sock'}",
                    "modelId": "qwen3.5-2b-q4-k-m",
                    "tasks": ["memory_maintenance"],
                    "scheduling": {"parallelSlots": 8, "fanout": True},
                },
            },
        }
        m.ensure_private_dir(m.config_root())
        m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
        m.atomic_write(
            m.last_model_call_path(),
            json.dumps(
                {
                    "schema": m.MODEL_CALL_TELEMETRY_SCHEMA_VERSION,
                    "status": "completed",
                    "route": m.MODEL_ROUTE_CHAT,
                    "catalog_route": "qwen36-chat-default",
                    "finished": m.now(),
                },
                ensure_ascii=False,
            )
            + "\n",
        )

        old_status = m.local_model_status_text
        old_run_helper = m.run_local_model_helper
        calls = []
        try:
            m.local_model_status_text = lambda info: (
                "route=qwen36-chat-default\nsocket=active\nproxy=active\nbackend=active\nactive_requests=0\n"
                if m.local_model_helper_route(info) == "qwen36-chat-default"
                else "route=qwen35-2b-worker\nsocket=active\nproxy=inactive\nbackend=inactive\n"
            )
            m.run_local_model_helper = lambda command, info, **_kwargs: calls.append(
                (command, m.local_model_helper_route(info))
            )
            worker = m.model_route(m.MODEL_ROUTE_MEMORY)
            try:
                m.prepare_worker_route_residency(worker)
            except m.RouteResidencyBusy as exc:
                assert "waiting" in str(exc)
                assert "recent chat route qwen36-chat-default" in str(exc)
            else:
                raise AssertionError("recent chat route should keep its residency grace")
            assert calls == []
        finally:
            m.local_model_status_text = old_status
            m.run_local_model_helper = old_run_helper


def test_worker_route_releases_idle_declared_exclusive_lane_peer(m):
    with isolated_state() as tmp:
        socket_dir = tmp / "sockets"
        socket_dir.mkdir()
        catalog = {
            "realm": "mares",
            "manager": {"kind": "systemd-socket-worker"},
            "routes": {
                "worker-a": {
                    "endpoint": f"unix://{socket_dir / 'worker-a.sock'}",
                    "modelId": "worker-a-model",
                    "tasks": ["index_corpus"],
                    "scheduling": {"exclusiveLane": "gpu-heavy", "parallelSlots": 1, "fanout": False},
                },
                "worker-b": {
                    "endpoint": f"unix://{socket_dir / 'worker-b.sock'}",
                    "modelId": "worker-b-model",
                    "tasks": ["audit"],
                    "scheduling": {"exclusiveLane": "gpu-heavy", "parallelSlots": 1, "fanout": False},
                },
            },
        }
        m.ensure_private_dir(m.config_root())
        m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")

        old_status = m.local_model_status_text
        old_run_helper = m.run_local_model_helper
        calls = []
        try:
            m.local_model_status_text = lambda info: (
                "route=worker-b\nsocket=active\nproxy=active\nbackend=active\nactive_requests=0\n"
                if m.local_model_helper_route(info) == "worker-b"
                else "route=worker-a\nsocket=active\nproxy=inactive\nbackend=inactive\n"
            )

            def fake_run_helper(command, info, *, timeout=m.LOCAL_MODEL_HELPER_TIMEOUT_SECONDS):
                calls.append((command, m.local_model_helper_route(info)))
                return "stopped"

            m.run_local_model_helper = fake_run_helper
            worker = m.catalog_route_info("worker-a", logical_route=m.MODEL_ROUTE_INDEX_CORPUS)
            notes = m.prepare_route_residency_for_request(worker)
            assert notes == ["released worker-b"]
            assert calls == [("stop", "worker-b")]
        finally:
            m.local_model_status_text = old_status
            m.run_local_model_helper = old_run_helper


def test_worker_route_defers_when_declared_exclusive_lane_peer_is_busy(m):
    with isolated_state() as tmp:
        socket_dir = tmp / "sockets"
        socket_dir.mkdir()
        catalog = {
            "realm": "mares",
            "manager": {"kind": "systemd-socket-worker"},
            "routes": {
                "worker-a": {
                    "endpoint": f"unix://{socket_dir / 'worker-a.sock'}",
                    "modelId": "worker-a-model",
                    "tasks": ["index_corpus"],
                    "scheduling": {"exclusiveLane": "gpu-heavy", "parallelSlots": 1, "fanout": False},
                },
                "worker-b": {
                    "endpoint": f"unix://{socket_dir / 'worker-b.sock'}",
                    "modelId": "worker-b-model",
                    "tasks": ["audit"],
                    "scheduling": {"exclusiveLane": "gpu-heavy", "parallelSlots": 1, "fanout": False},
                },
            },
        }
        m.ensure_private_dir(m.config_root())
        m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")

        old_status = m.local_model_status_text
        old_run_helper = m.run_local_model_helper
        calls = []
        try:
            m.local_model_status_text = lambda info: (
                "route=worker-b\nsocket=active\nproxy=active\nbackend=active\nactive_requests=1\n"
                if m.local_model_helper_route(info) == "worker-b"
                else "route=worker-a\nsocket=active\nproxy=inactive\nbackend=inactive\n"
            )
            m.run_local_model_helper = lambda command, info, **_kwargs: calls.append(
                (command, m.local_model_helper_route(info))
            )
            worker = m.catalog_route_info("worker-a", logical_route=m.MODEL_ROUTE_INDEX_CORPUS)
            try:
                m.prepare_route_residency_for_request(worker)
            except m.RouteResidencyBusy as exc:
                assert "exclusive lane gpu-heavy" in str(exc)
            else:
                raise AssertionError("busy exclusive-lane peer should defer worker route")
            assert calls == []
        finally:
            m.local_model_status_text = old_status
            m.run_local_model_helper = old_run_helper


def test_chat_route_releases_idle_worker_routes(m):
    with isolated_state() as tmp:
        socket_dir = tmp / "sockets"
        catalog = {
            "realm": "mares",
            "manager": {"kind": "systemd-socket-worker"},
            "routes": {
                "qwen36-chat-default": {
                    "endpoint": f"unix://{socket_dir / 'qwen36-chat-default.sock'}",
                    "modelId": "qwen3.6-27b-mtp-ud-q4-k-xl",
                    "tasks": ["chat", "default_chat"],
                    "route_profile": "default",
                    "selection": {"default": True, "priority": 100},
                    "scheduling": {"exclusiveLane": "large-chat", "parallelSlots": 1, "fanout": False},
                },
                "qwen35-2b-worker": {
                    "endpoint": f"unix://{socket_dir / 'qwen35-2b-worker.sock'}",
                    "modelId": "qwen3.5-2b-q4-k-m",
                    "tasks": ["memory_maintenance"],
                    "scheduling": {"parallelSlots": 8, "fanout": True},
                },
            },
        }
        m.ensure_private_dir(m.config_root())
        m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")

        old_status = m.local_model_status_text
        old_run_helper = m.run_local_model_helper
        calls = []
        try:
            m.local_model_status_text = lambda info: (
                "route=qwen35-2b-worker\nsocket=active\nproxy=active\nbackend=active\nactive_requests=0\n"
                if m.local_model_helper_route(info) == "qwen35-2b-worker"
                else "route=qwen36-chat-default\nsocket=active\nproxy=inactive\nbackend=inactive\n"
            )

            def fake_run_helper(command, info, *, timeout=m.LOCAL_MODEL_HELPER_TIMEOUT_SECONDS):
                calls.append((command, m.local_model_helper_route(info)))
                return "stopped"

            m.run_local_model_helper = fake_run_helper
            chat = m.model_route(m.MODEL_ROUTE_CHAT)
            notes = m.prepare_route_residency_for_request(chat)
            assert notes == ["released qwen35-2b-worker"]
            assert calls == [("stop", "qwen35-2b-worker")]
        finally:
            m.local_model_status_text = old_status
            m.run_local_model_helper = old_run_helper


def test_chat_route_releases_idle_large_chat_peer(m):
    with isolated_state() as tmp:
        socket_dir = tmp / "sockets"
        catalog = {
            "realm": "mares",
            "manager": {"kind": "systemd-socket-worker"},
            "routes": {
                "qwen36-chat-default": {
                    "endpoint": f"unix://{socket_dir / 'qwen36-chat-default.sock'}",
                    "modelId": "qwen3.6-27b-mtp-ud-q4-k-xl",
                    "tasks": ["chat", "default_chat"],
                    "lane": "large-chat",
                    "route_profile": "default",
                    "selection": {"default": True, "priority": 100},
                    "scheduling": {"parallelSlots": 1, "fanout": False},
                },
                "qwen36-chat-quality": {
                    "endpoint": f"unix://{socket_dir / 'qwen36-chat-quality.sock'}",
                    "modelId": "qwen3.6-27b-mtp-ud-q5-k-xl",
                    "tasks": ["chat", "quality_chat"],
                    "route_profile": "quality",
                    "selection": {"priority": 80, "exclusiveLane": "large-chat"},
                    "scheduling": {"parallelSlots": 1, "fanout": False},
                },
            },
        }
        m.ensure_private_dir(m.config_root())
        m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")

        old_status = m.local_model_status_text
        old_run_helper = m.run_local_model_helper
        calls = []
        try:
            m.local_model_status_text = lambda info: (
                "route=qwen36-chat-default\nsocket=active\nproxy=active\nbackend=active\nactive_requests=0\n"
                if m.local_model_helper_route(info) == "qwen36-chat-default"
                else "route=qwen36-chat-quality\nsocket=active\nproxy=inactive\nbackend=inactive\n"
            )

            def fake_run_helper(command, info, *, timeout=m.LOCAL_MODEL_HELPER_TIMEOUT_SECONDS):
                calls.append((command, m.local_model_helper_route(info)))
                return "stopped"

            m.run_local_model_helper = fake_run_helper
            quality = m.catalog_route_info("qwen36-chat-quality", logical_route=m.MODEL_ROUTE_CHAT)
            notes = m.prepare_route_residency_for_request(quality)
            assert notes == ["released qwen36-chat-default"]
            assert calls == [("stop", "qwen36-chat-default")]
        finally:
            m.local_model_status_text = old_status
            m.run_local_model_helper = old_run_helper


def test_chat_route_defers_when_large_chat_peer_is_busy(m):
    with isolated_state() as tmp:
        socket_dir = tmp / "sockets"
        catalog = {
            "realm": "mares",
            "manager": {"kind": "systemd-socket-worker"},
            "routes": {
                "qwen36-chat-default": {
                    "endpoint": f"unix://{socket_dir / 'qwen36-chat-default.sock'}",
                    "modelId": "qwen3.6-27b-mtp-ud-q4-k-xl",
                    "tasks": ["chat", "default_chat"],
                    "route_profile": "default",
                    "selection": {"default": True, "priority": 100, "exclusiveLane": "large-chat"},
                    "scheduling": {"parallelSlots": 1, "fanout": False},
                },
                "qwen36-chat-quality": {
                    "endpoint": f"unix://{socket_dir / 'qwen36-chat-quality.sock'}",
                    "modelId": "qwen3.6-27b-mtp-ud-q5-k-xl",
                    "tasks": ["chat", "quality_chat"],
                    "route_profile": "quality",
                    "selection": {"priority": 80, "exclusiveLane": "large-chat"},
                    "scheduling": {"parallelSlots": 1, "fanout": False},
                },
            },
        }
        m.ensure_private_dir(m.config_root())
        m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")

        old_status = m.local_model_status_text
        old_run_helper = m.run_local_model_helper
        calls = []
        try:
            m.local_model_status_text = lambda info: (
                "route=qwen36-chat-default\nsocket=active\nproxy=active\nbackend=active\nactive_requests=1\n"
                if m.local_model_helper_route(info) == "qwen36-chat-default"
                else "route=qwen36-chat-quality\nsocket=active\nproxy=inactive\nbackend=inactive\n"
            )
            m.run_local_model_helper = lambda command, info, **_kwargs: calls.append(
                (command, m.local_model_helper_route(info))
            )
            quality = m.catalog_route_info("qwen36-chat-quality", logical_route=m.MODEL_ROUTE_CHAT)
            try:
                m.prepare_route_residency_for_request(quality)
            except m.RouteResidencyBusy as exc:
                assert "active route qwen36-chat-default" in str(exc)
            else:
                raise AssertionError("busy large chat peer should defer selected chat route")
            assert calls == []
        finally:
            m.local_model_status_text = old_status
            m.run_local_model_helper = old_run_helper


def test_open_model_response_direct_calls_prepare_residency(m):
    class FakeResponse:
        def read(self):
            return b"{}"

    @contextlib.contextmanager
    def fake_core(*_args, **_kwargs):
        yield FakeResponse()

    old_core = m.open_model_response_core
    old_prepare = m.prepare_route_residency_for_request
    calls = []
    try:
        m.open_model_response_core = fake_core

        def fake_prepare(route_info, *, phase_callback=None):
            calls.append((m.local_model_helper_route(route_info), phase_callback is not None))
            return []

        m.prepare_route_residency_for_request = fake_prepare
        route_info = {
            "route": "embedding",
            "catalog_route": "qwen3-embedding-0b6",
            "endpoint": "unix:///run/motoko-llm/mares/qwen3-embedding-0b6.sock",
            "model": "qwen3-embedding-0.6b-q8-0",
        }
        with m.open_model_response(route_info, {"model": "x"}, timeout=1) as resp:
            assert resp.read() == b"{}"
        assert calls == [("qwen3-embedding-0b6", False)]

        calls.clear()
        with m.open_model_response(route_info, {"model": "x"}, timeout=1, prepare_residency=False) as resp:
            assert resp.read() == b"{}"
        assert calls == []
    finally:
        m.open_model_response_core = old_core
        m.prepare_route_residency_for_request = old_prepare


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
                        "cache": {
                            "prompt": True,
                            "persistentSlotCache": True,
                            "slotsEndpoint": True,
                            "slotSavePath": "/var/lib/motoko-llm-slots-mares-qwen36-chat",
                            "slotCacheMaxMiB": 32768,
                        },
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
                if command == "metrics":
                    return "llama_prompt_seconds_total 1.23\nllama_tokens_total 42"
                if command == "slot-cache-status":
                    return "\n".join(
                        [
                            "realm=mares",
                            f"route={route}",
                            "persistent_slot_cache=1",
                            "slot_cache_total_bytes=1400",
                            "slot_cache_file_count=2",
                            "slot_cache_cap_bytes=1000",
                            "slot_cache_needs_gc=1",
                        ]
                    )
                if command == "slot-cache-gc":
                    return "slot_cache_deleted_files=1\nslot_cache_total_bytes=700"
                if command == "slot-cache-clear":
                    return "slot_cache_deleted_files=2\nslot_cache_total_bytes=0"
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

                metrics = m.model_service_metrics("qwen36-chat")
                assert "model metrics: qwen36-chat" in metrics
                assert "llama_tokens_total 42" in metrics
                assert ("metrics", "qwen36-chat") in calls

                slot_report = m.format_slot_cache("qwen36-chat")
                assert "service status source: motoko-model slot-cache-status qwen36-chat" in slot_report
                assert "slot_cache_needs_gc=1" in slot_report
                assert ("slot-cache-status", "qwen36-chat") in calls

                gc = m.slot_cache_gc_text("qwen36-chat")
                assert "slot/KV service GC: qwen36-chat" in gc
                assert "slot_cache_deleted_files=1" in gc
                assert ("slot-cache-gc", "qwen36-chat") in calls

                cleared = m.slot_cache_clear_text("qwen36-chat", yes=True)
                assert "service clear: completed" in cleared
                assert "slot_cache_deleted_files=2" in cleared
                assert ("slot-cache-clear", "qwen36-chat") in calls
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

    def fake_summarize_text(
        label,
        text,
        instruction,
        *,
        timeout=m.MODEL_TIMEOUT_SECONDS,
        route=m.MODEL_ROUTE_CHAT,
        prompt_version="summary-v1",
        cancel_event=None,
    ):
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
        topic_path = pathlib.Path.cwd() / "logbook.org"
        topic = {
            "id": "topic-test",
            "name": "Yesterday Tasks",
            "query": "unfinished tasks",
            "summary": "Summary",
            "evidence": [
                {
                    "index": "idx",
                    "path": str(topic_path),
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
        assert str(topic_path) in text


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
        fallback = m.format_conversation_sources(conv)
        assert "No recorded sources for the last answer yet" in fallback
        assert "attached topic unavailable" in fallback


def test_answer_grounding_audit_sources(m):
    sources = [
        {
            "kind": "chunk",
            "index": "idx",
            "path": "/tmp/logbook.org",
            "chunk": 1,
            "lexical_score": 25,
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
    assert audit["nominal_strong_evidence_sources"] == 1
    assert audit["weak_nominal_strong_sources"] == 0
    text = m.format_sources(audited)
    assert "answer audit" in text
    assert "paths: /tmp/logbook.org" in text

    thin = m.answer_grounding_audit("summarize according to logbook.org", "No documents are attached.", [])
    assert thin["status"] == "fail"
    assert "attach or study" in thin["recommended_action"]

    weak = m.answer_grounding_audit(
        "summarize according to logbook.org",
        "Weak answer.",
        [{"kind": "chunk", "path": "/tmp/other.org", "chunk": 1, "lexical_score": 0}],
    )
    assert weak["status"] == "fail"
    assert weak["strong_evidence_sources"] == 0
    assert weak["nominal_strong_evidence_sources"] == 1
    assert weak["weak_nominal_strong_sources"] == 1
    assert "weak nominal evidence" in m.format_sources([weak])


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


def test_core_retrieval_sufficiency_planner_selects_bounded_extra_pass(m):
    plan = m.plan_retrieval_sufficiency_expansion(
        "according to plan.org, what is the next task?",
        [{"kind": "memory"}],
        [
            {
                "item": {"kind": "index", "id": "idx-1"},
                "score": 1,
                "reason": "current-project document index",
            }
        ],
        grounding_query_words={"according", "file"},
        task_query_words={"task"},
        strong_source_kinds={"chunk"},
        context_source_kinds={"memory", "index"},
        min_score=1,
    )

    assert plan["schema"] == "retrieval-sufficiency-plan-v1"
    assert plan["status"] == "expand"
    assert plan["selected"]["kind"] == "index"
    assert plan["selected"]["id"] == "idx-1"
    assert plan["strong_source_count"] == 0

    weak_chunk = m.plan_retrieval_sufficiency_expansion(
        "according to plan.org",
        [{"kind": "chunk", "path": "/tmp/other.org", "chunk": 1, "lexical_score": 0}],
        [{"item": {"kind": "index", "id": "idx-1"}, "score": 1}],
        grounding_query_words={"according"},
        task_query_words=set(),
        strong_source_kinds={"chunk"},
        context_source_kinds={"index"},
        min_score=1,
    )
    assert weak_chunk["status"] == "expand"
    assert weak_chunk["nominal_strong_source_count"] == 1
    assert weak_chunk["strong_source_count"] == 0

    stale_strong = m.plan_retrieval_sufficiency_expansion(
        "according to plan.org",
        [{"kind": "chunk", "path": "/tmp/plan.org", "chunk": 1, "lexical_score": 5, "status": "stale"}],
        [{"item": {"kind": "index", "id": "idx-fresh"}, "score": 1, "reason": "fresh replacement"}],
        grounding_query_words={"according"},
        task_query_words=set(),
        strong_source_kinds={"chunk"},
        context_source_kinds={"index"},
        min_score=1,
    )
    assert stale_strong["status"] == "expand"
    assert stale_strong["strong_source_count"] == 1
    assert stale_strong["stale_or_unavailable_source_count"] == 1
    assert "stale or unavailable" in stale_strong["reason"]

    wrong_path_strong = m.plan_retrieval_sufficiency_expansion(
        "according to plan.org",
        [{"kind": "chunk", "path": "/tmp/other.org", "chunk": 1, "lexical_score": 5}],
        [{"item": {"kind": "index", "id": "idx-1"}, "score": 1}],
        grounding_query_words={"according"},
        task_query_words=set(),
        strong_source_kinds={"chunk"},
        context_source_kinds={"index"},
        min_score=1,
    )
    assert wrong_path_strong["status"] == "expand"
    assert wrong_path_strong["strong_source_count"] == 1
    assert wrong_path_strong["strong_requested_path_source_count"] == 0
    assert wrong_path_strong["requested_path_mentions"] == ["plan.org"]
    assert "source path" in wrong_path_strong["reason"]

    matching_path_strong = m.plan_retrieval_sufficiency_expansion(
        "according to plan.org",
        [{"kind": "chunk", "path": "/tmp/plan.org", "chunk": 1, "lexical_score": 5}],
        [{"item": {"kind": "index", "id": "idx-1"}, "score": 1}],
        grounding_query_words={"according"},
        task_query_words=set(),
        strong_source_kinds={"chunk"},
        context_source_kinds={"index"},
        min_score=1,
    )
    assert matching_path_strong["status"] == "sufficient"
    assert matching_path_strong["strong_requested_path_source_count"] == 1

    sufficient = m.plan_retrieval_sufficiency_expansion(
        "according to plan.org",
        [{"kind": "chunk", "path": "/tmp/plan.org", "lexical_score": 1}],
        [{"item": {"kind": "index", "id": "idx-1"}, "score": 1}],
        grounding_query_words={"according"},
        task_query_words=set(),
        strong_source_kinds={"chunk"},
        context_source_kinds={"index"},
        min_score=1,
    )
    assert sufficient["status"] == "sufficient"


def test_retrieval_service_builds_sufficiency_expansion(m):
    service = m.RetrievalService(
        load_index=lambda index_id: {"id": index_id},
        retrieve_index_query=lambda index, query: (
            f"index {index['id']} query {query}\nThe next task is calibrating RaceFocus.",
            [{"kind": "chunk", "index": index["id"], "path": "/tmp/plan.org", "chunk": 1, "lexical_score": 5}],
        ),
        render_index_overview=lambda index: ("overview", [{"kind": "index", "id": index["id"]}]),
        load_topic=lambda topic_id: {"id": topic_id},
        retrieve_topic=lambda topic, query: ("topic", [{"kind": "topic", "id": topic["id"]}]),
        load_dossier=lambda dossier_id: {"id": dossier_id},
        retrieve_dossier=lambda dossier, query: ("dossier", [{"kind": "dossier", "id": dossier["id"]}]),
    )

    expansion = service.build_sufficiency_expansion(
        "according to plan.org, what is the next task?",
        [{"kind": "memory"}],
        [
            {
                "item": {"kind": "index", "id": "idx-1"},
                "score": 3,
                "reason": "current-project document index",
            }
        ],
        grounding_query_words={"according"},
        task_query_words={"task"},
        strong_source_kinds={"chunk"},
        context_source_kinds={"memory", "index"},
        min_score=1,
    )

    assert expansion.plan["status"] == "expand"
    assert expansion.selected_item == {"kind": "index", "id": "idx-1"}
    assert "Retrieval sufficiency planner:" in expansion.text
    assert "calibrating RaceFocus" in expansion.text
    assert expansion.sources[0]["kind"] == "retrieval-sufficiency"
    assert expansion.sources[0]["selected_id"] == "idx-1"
    assert expansion.sources[0]["requested_path_mentions"] == ["plan.org"]
    assert expansion.sources[1]["kind"] == "chunk"
    assert expansion.diagnostics["source_count"] == 2


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
            "nominal_strong_evidence_sources": 1,
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
    assert "source audit: pass  strong 1  nominal 1  context 0  total 2" in report
    assert "source kinds: chunk=1, context-plan=1" in report
    assert "warning: stale source" in report
    assert "Context plan: 10/100 chars (ok)" in report
    assert "1  chunk  /tmp/plan.org" in report
    assert "Evidence block" in report


def test_prompt_context_runs_bounded_retrieval_sufficiency_pass(m):
    old_cwd = os.getcwd()
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "plan.org").write_text(
            "* TODO [#A] Alpha plan\nThe next task is calibrating the RaceFocus wind cue.\n",
            encoding="utf-8",
        )
        m.add_allowed_dir(str(docs))
        old_quiet_model = m.quiet_model
        try:
            os.chdir(docs)
            m.quiet_model = lambda *args, **kwargs: "Plan corpus summary."
            m.build_document_index(str(docs))
            conv = m.new_conversation("Sufficiency")
            conv["id"] = "sufficiency"
            m.save_conversation(conv)

            prompt, sources = m.build_system_prompt_and_sources(
                conv,
                "according to plan.org, what is the next task?",
            )

            assert "Retrieval sufficiency planner:" in prompt
            assert "calibrating the RaceFocus wind cue" in prompt
            assert any(source.get("kind") == "retrieval-sufficiency" for source in sources)
            assert any(source.get("kind") == "chunk" for source in sources)
            assert not conv.get("context_items")
            report = m.format_sources(sources)
            assert "retrieval sufficiency" in report
            assert "bounded extra retrieval pass" in report
        finally:
            m.quiet_model = old_quiet_model
            os.chdir(old_cwd)


def test_core_retrieval_reports_are_injectable(m):
    eval_text = m.format_retrieval_eval_report_core(
        {
            "status": "fail",
            "passed": 0,
            "total": 1,
            "id": "eval-1",
            "fixtures": [
                {
                    "status": "fail",
                    "id": "fixture-1",
                    "chunk_source_count": 0,
                    "answer_audit_status": "fail",
                    "selected_paths": [],
                    "missing_paths": ["logbook.org"],
                }
            ],
        }
    )
    debug_text = m.format_retrieval_debug_report_core(
        {
            "query": "logbook.org",
            "id": "debug-1",
            "query_terms": ["logbook"],
            "path_mentions": ["logbook.org"],
            "indexes": [
                {
                    "id": "idx",
                    "freshness": "fresh",
                    "files_considered": 1,
                    "chunks_considered": 1,
                    "production_retrieval": "hybrid",
                    "diagnosis": ["recall ok"],
                    "files": [{"total": 10, "path": "/tmp/logbook.org", "matched_terms": ["logbook"]}],
                    "chunks": [{"total": 9, "path": "/tmp/logbook.org", "chunk": 1, "summary": "Recent notes"}],
                    "vector_store": {"id": "vec", "method": "embedding-v1", "rerank": True, "rerank_fallback": False},
                    "vector_chunks": [{"score": 1.2, "vector_score": 0.9, "path": "/tmp/logbook.org", "chunk": 1}],
                }
            ],
        }
    )

    assert "retrieval eval: fail (0/1)" in eval_text
    assert "missing paths logbook.org" in eval_text
    assert "retrieval debug: logbook.org" in debug_text
    assert "diagnosis: recall ok" in debug_text
    assert "vector store: vec method=embedding-v1 rerank=True fallback=False" in debug_text


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
        production_sources = report["indexes"][0]["production_sources"]
        assert any(row["kind"] == "chunk" and row["path"].endswith("/logbook.org") for row in production_sources)
        assert report["indexes"][0]["production_diagnostics"]["schema"] == "retrieval-service-v1"
        assert report["indexes"][0]["production_diagnostics"]["source_count"] >= len(production_sources)
        text = m.format_retrieval_debug_report(report)
        assert "retrieval debug:" in text
        assert "production selected sources:" in text
        assert "path=2500" in text
        assert "diagnosis:" in text
        assert "prompt-use check" in text


def test_retrieval_debug_uses_service_debug_result_without_side_probes(m):
    with isolated_state():
        index = {
            "id": "service-debug-index",
            "name": "docs",
            "root": "/tmp/docs",
            "created": "2026-05-30T00:00:00+00:00",
            "files": [],
        }
        m.atomic_write(m.index_path(index["id"]), json.dumps(index, ensure_ascii=False, indent=2) + "\n")

        class FakeResult:
            diagnostics = {
                "debug_index": {
                    "id": "service-debug-index",
                    "name": "docs",
                    "root": "/tmp/docs",
                    "freshness": "fresh",
                    "production_retrieval": "shared result",
                    "warnings": [],
                    "files_considered": 1,
                    "chunks_considered": 1,
                    "files": [{"path": "/tmp/docs/a.org", "total": 9, "lexical": 9}],
                    "chunks": [{"path": "/tmp/docs/a.org", "chunk": 1, "total": 8, "summary": "Alpha"}],
                    "production_sources": [{"kind": "chunk", "path": "/tmp/docs/a.org", "chunk": 1}],
                    "production_diagnostics": {"schema": "retrieval-service-v1", "source_count": 1},
                    "evidence_store": {"id": "evidence-from-service", "freshness": "fresh"},
                    "evidence_rows": [{"path": "/tmp/docs/a.org", "chunk": 1, "total": 7, "kind": "org_day"}],
                    "vector_store": {
                        "id": "vector-from-service",
                        "method": "embedding-v1",
                        "rerank": True,
                        "rerank_fallback": False,
                    },
                    "vector_chunks": [{"path": "/tmp/docs/a.org", "chunk": 1, "score": 6}],
                }
            }

            def source_summary(self, *, limit=8):
                return self.diagnostics["debug_index"]["production_sources"][:limit]

        old_retrieve = m.retrieve_index_result
        old_evidence = m.query_evidence_store
        old_vector = m.query_vector_store_for_retrieval
        try:
            m.retrieve_index_result = lambda _index, _query: FakeResult()
            m.query_evidence_store = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("retrieval-debug should not run an evidence side probe")
            )
            m.query_vector_store_for_retrieval = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("retrieval-debug should not run a vector side probe")
            )
            report = m.run_retrieval_debug("alpha", index_ids=[index["id"]], limit=4)
        finally:
            m.retrieve_index_result = old_retrieve
            m.query_evidence_store = old_evidence
            m.query_vector_store_for_retrieval = old_vector

        debug_index = report["indexes"][0]
        assert debug_index["production_retrieval"] == "shared result"
        assert debug_index["evidence_store"]["id"] == "evidence-from-service"
        assert debug_index["vector_store"]["id"] == "vector-from-service"
        assert debug_index["production_sources"][0]["kind"] == "chunk"


def test_retrieval_service_result_includes_debug_index_shape(m):
    old_evidence = os.environ.get("MOTOKO_EVIDENCE_RETRIEVAL")
    old_vector = os.environ.get("MOTOKO_VECTOR_RETRIEVAL")
    try:
        os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = "0"
        os.environ["MOTOKO_VECTOR_RETRIEVAL"] = "0"
        with isolated_state():
            index = {
                "id": "service-shape-index",
                "name": "docs",
                "root": "/tmp/docs",
                "created": "2026-05-30T00:00:00+00:00",
                "files": [
                    {
                        "path": "/tmp/docs/tasks.org",
                        "summary": "Alpha planning tasks.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "Alpha beta task chunk.",
                                "content": "* TODO Alpha beta work\n",
                                "content_sha256": m.sha256_hex(b"* TODO Alpha beta work\n"),
                            }
                        ],
                    }
                ],
            }

            result = m.retrieve_index_result(index, "alpha beta tasks")
            debug_index = result.diagnostics.get("debug_index")
            assert debug_index["id"] == "service-shape-index"
            assert debug_index["files_considered"] == 1
            assert debug_index["chunks_considered"] == 1
            assert debug_index["production_sources"] == result.source_summary(limit=50)
            assert debug_index["chunks"][0]["path"].endswith("tasks.org")
            assert debug_index["production_diagnostics"]["schema"] == "retrieval-service-v1"
    finally:
        if old_evidence is None:
            os.environ.pop("MOTOKO_EVIDENCE_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = old_evidence
        if old_vector is None:
            os.environ.pop("MOTOKO_VECTOR_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_VECTOR_RETRIEVAL"] = old_vector


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
        assert "newest dates present in the matching file(s): 2026-05-19, 2026-05-18" in text
        index_source = next(source for source in sources if source.get("kind") == "index")
        assert index_source["temporal_selected_dates"] == ["2026-05-19", "2026-05-18"]
        assert index_source["activated_skills"] == ["org-temporal-retrieval"]
        plan_source = next(source for source in sources if source.get("kind") == "retrieval-plan")
        assert plan_source["activated_skills"] == ["org-temporal-retrieval"]
        assert plan_source["handlers"] == ["builtin:org_temporal_latest_entries"]
        assert plan_source["temporal"]["requested_count"] == 2
        chunk_sources = [source for source in sources if source.get("kind") == "chunk"]
        assert chunk_sources and chunk_sources[0]["path"].endswith("logbook.org")
        assert chunk_sources[0]["temporal_selected_dates"] == ["2026-05-19", "2026-05-18"]
        assert "selected newest dates present in source: 2026-05-19, 2026-05-18" in m.format_sources(sources)
        assert "retrieval plan" in m.format_sources(sources)
        assert "builtin:org_temporal_latest_entries" in m.format_sources(sources)


def test_org_structural_tag_query_uses_skill_and_inherited_tags(m):
    old_evidence = os.environ.get("MOTOKO_EVIDENCE_RETRIEVAL")
    old_vector = os.environ.get("MOTOKO_VECTOR_RETRIEVAL")
    try:
        os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = "1"
        os.environ["MOTOKO_VECTOR_RETRIEVAL"] = "0"
        with isolated_state() as tmp:
            docs = tmp / "orgfiles"
            docs.mkdir()
            path = docs / "todo.org"
            content = "\n".join(
                [
                    "* Product :racefocus:",
                    "** TODO [#A] Build HUD complication",
                    "DEADLINE: <2026-06-01 Mon>",
                    "Use fighter HUD symbology.",
                    "** DONE Archive OBS note :archive:",
                    "Keep this as historical RaceFocus context.",
                    "* Other :unrelated:",
                    "** TODO Buy keyboard",
                ]
            ) + "\n"
            path.write_text(content, encoding="utf-8")
            index = {
                "id": "org-structural-index",
                "name": "orgfiles",
                "root": str(docs),
                "created": "2026-05-31T00:00:00+00:00",
                "files": [
                    {
                        "path": str(path),
                        "source_fingerprint": m.source_fingerprint(path),
                        "summary": "Org task and project notes.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "RaceFocus product notes and unrelated task.",
                                "content": content,
                                "content_sha256": m.sha256_hex(content.encode("utf-8")),
                                "content_bytes": len(content.encode("utf-8")),
                            }
                        ],
                    }
                ],
            }

            store = m.build_evidence_store_from_index(index, write=False)
            task_rows = [row for row in store["rows"] if row.get("title") == "Build HUD complication"]
            assert task_rows
            assert "racefocus" in task_rows[0].get("tags", [])
            assert "racefocus" in task_rows[0].get("inherited_tags", [])

            text, sources = m.retrieve_from_index(index, "show me all elements with tag racefocus")
            assert "Org structural selection:" in text
            assert "Matched" in text
            assert "Build HUD complication" in text
            assert "Archive OBS note" in text
            assert "Buy keyboard" not in text
            index_source = next(source for source in sources if source.get("kind") == "index")
            assert index_source["activated_skills"] == ["org-structural-query"]
            assert index_source["structural_matches"] >= 2
            assert "tag:racefocus" in index_source["structural_filters"]
            plan_source = next(source for source in sources if source.get("kind") == "retrieval-plan")
            assert plan_source["activated_skills"] == ["org-structural-query"]
            assert plan_source["handlers"] == ["builtin:org_structural_query"]
            assert plan_source["structural"]["tags"] == ["racefocus"]
            chunks = [source for source in sources if source.get("kind") == "chunk"]
            assert chunks
            assert any("structural" in source.get("retrieval_methods", []) for source in chunks)
            assert "structural: tag:racefocus" in m.format_sources(sources)
    finally:
        if old_evidence is None:
            os.environ.pop("MOTOKO_EVIDENCE_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = old_evidence
        if old_vector is None:
            os.environ.pop("MOTOKO_VECTOR_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_VECTOR_RETRIEVAL"] = old_vector


def test_source_code_locator_prioritizes_implementation_chunks(m):
    old_evidence = os.environ.get("MOTOKO_EVIDENCE_RETRIEVAL")
    old_vector = os.environ.get("MOTOKO_VECTOR_RETRIEVAL")
    old_rerank = os.environ.get("MOTOKO_VECTOR_RERANK")
    os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = "0"
    os.environ["MOTOKO_VECTOR_RETRIEVAL"] = "0"
    os.environ["MOTOKO_VECTOR_RERANK"] = "0"
    try:
        root = "/tmp/motoko-code-locator"
        code = '''
SLASH_COMMANDS = [
    ("/about", "show Motoko version and runtime details"),
]

def format_about():
    return "Motoko about page"

def command_about(_args):
    print_report(format_about())
'''
        docs = "The /about page is documented here, but implementation lives elsewhere."
        index = {
            "id": "idx-code",
            "name": "motoko",
            "root": root,
            "created": "2026-05-25T00:00:00+00:00",
            "files": [
                {
                    "path": root + "/docs/motoko.md",
                    "summary": "Documentation for /about.",
                    "chunks": [
                        {
                            "chunk": 1,
                            "summary": "Docs mention /about.",
                            "content": docs,
                            "content_sha256": m.sha256_hex(docs.encode("utf-8")),
                        }
                    ],
                },
                {
                    "path": root + "/motoko",
                    "summary": "Main executable and command handlers.",
                    "chunks": [
                        {
                            "chunk": 1,
                            "summary": "Command table and about formatter.",
                            "content": code,
                            "content_sha256": m.sha256_hex(code.encode("utf-8")),
                        }
                    ],
                },
            ],
        }
        text, sources = m.retrieve_from_index(index, "which file in the repo takes care of the /about page?")
        assert "Source code locator:" in text
        assert "def format_about" in text
        chunk_sources = [source for source in sources if source.get("kind") == "chunk"]
        assert any(
            source.get("path", "").endswith("/motoko") and "code" in source.get("retrieval_methods", [])
            for source in chunk_sources
        )
        index_source = next(source for source in sources if source.get("kind") == "index")
        assert index_source.get("code_locator_hits", 0) >= 1
    finally:
        if old_evidence is None:
            os.environ.pop("MOTOKO_EVIDENCE_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = old_evidence
        if old_vector is None:
            os.environ.pop("MOTOKO_VECTOR_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_VECTOR_RETRIEVAL"] = old_vector
        if old_rerank is None:
            os.environ.pop("MOTOKO_VECTOR_RERANK", None)
        else:
            os.environ["MOTOKO_VECTOR_RERANK"] = old_rerank


def test_named_logbook_recent_query_keeps_nonconsecutive_latest_dates(m):
    old_evidence = os.environ.get("MOTOKO_EVIDENCE_RETRIEVAL")
    old_vector = os.environ.get("MOTOKO_VECTOR_RETRIEVAL")
    old_max_retrieval_chars = m.MAX_RETRIEVAL_CHARS
    try:
        os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = "0"
        os.environ["MOTOKO_VECTOR_RETRIEVAL"] = "0"
        m.MAX_RETRIEVAL_CHARS = 1200
        with isolated_state() as tmp:
            docs = tmp / "orgfiles"
            docs.mkdir()
            path = docs / "logbook.org"
            older = (
                "* [2026-05-18 Mon 11:14]\n"
                "** log\n"
                "May18 older action that should not be selected.\n"
            )
            second_latest = (
                "* [2026-05-19 Tue 12:34]\n"
                "** do\n"
                "*** TODO May19 second-latest action\n"
                "** log\n"
                "The second latest dated entry is not the previous calendar day.\n"
            )
            latest = (
                "* [2026-05-23 Sat 00:52]\n"
                "** do\n"
                "*** TODO May23 latest action\n"
                "** log\n"
                + ("Long May23 note that could crowd out the prior dated entry.\n" * 140)
            )
            content = older + "\n" + second_latest + "\n" + latest
            path.write_text(content, encoding="utf-8")
            index = {
                "id": "nonconsecutive-logbook-index",
                "name": "orgfiles",
                "root": str(docs),
                "created": "2026-05-24T00:00:00+00:00",
                "files": [
                    {
                        "path": str(path),
                        "source_fingerprint": m.source_fingerprint(path),
                        "summary": "Daily logbook entries.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "Logbook material with nonconsecutive latest dates.",
                                "content": content,
                                "content_sha256": m.sha256_hex(content.encode("utf-8")),
                                "content_bytes": len(content.encode("utf-8")),
                            }
                        ],
                    }
                ],
            }

            text, sources = m.retrieve_from_index(index, "summarize the last two days present in logbook.org")
            assert "May23 latest action" in text
            assert "May19 second-latest action" in text
            assert "May18 older action" not in text
            assert "2026-05-22" not in text
            index_source = next(source for source in sources if source.get("kind") == "index")
            assert index_source["temporal_selected_dates"] == ["2026-05-23", "2026-05-19"]
            plan_source = next(source for source in sources if source.get("kind") == "retrieval-plan")
            assert plan_source["activated_skills"] == ["org-temporal-retrieval"]
            chunks = [source for source in sources if source.get("kind") == "chunk"]
            assert chunks
            assert chunks[0]["temporal_selected_dates"] == ["2026-05-23", "2026-05-19"]
            production_sources = m.summarize_retrieval_sources(sources, limit=3)
            assert production_sources[0]["kind"] == "index"
            assert any(row["kind"] == "chunk" and row["path"].endswith("logbook.org") for row in production_sources)
    finally:
        m.MAX_RETRIEVAL_CHARS = old_max_retrieval_chars
        if old_evidence is None:
            os.environ.pop("MOTOKO_EVIDENCE_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = old_evidence
        if old_vector is None:
            os.environ.pop("MOTOKO_VECTOR_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_VECTOR_RETRIEVAL"] = old_vector


def test_named_temporal_query_ignores_other_dated_org_files(m):
    old_evidence = os.environ.get("MOTOKO_EVIDENCE_RETRIEVAL")
    old_vector = os.environ.get("MOTOKO_VECTOR_RETRIEVAL")
    try:
        os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = "0"
        os.environ["MOTOKO_VECTOR_RETRIEVAL"] = "0"
        with isolated_state() as tmp:
            docs = tmp / "orgfiles"
            docs.mkdir()
            logbook = docs / "logbook.org"
            pluslife = docs / "pluslife.org"
            logbook_content = (
                "* [2026-05-18 Mon 11:14]\n"
                "** log\n"
                "May18 logbook third-latest action.\n\n"
                "* [2026-05-19 Tue 12:34]\n"
                "** log\n"
                "May19 logbook second-latest action.\n\n"
                "* [2026-05-23 Sat 00:52]\n"
                "** log\n"
                "May23 logbook latest action.\n"
            )
            pluslife_content = (
                "* [2026-05-24 Sun 09:00]\n"
                "** log\n"
                "May24 pluslife distractor should not satisfy a logbook.org query.\n"
            )
            logbook.write_text(logbook_content, encoding="utf-8")
            pluslife.write_text(pluslife_content, encoding="utf-8")
            index = {
                "id": "named-temporal-index",
                "name": "orgfiles",
                "root": str(docs),
                "created": "2026-05-24T00:00:00+00:00",
                "files": [
                    {
                        "path": str(logbook),
                        "source_fingerprint": m.source_fingerprint(logbook),
                        "summary": "Daily logbook entries.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "Logbook material.",
                                "content": logbook_content,
                                "content_sha256": m.sha256_hex(logbook_content.encode("utf-8")),
                                "content_bytes": len(logbook_content.encode("utf-8")),
                            }
                        ],
                    },
                    {
                        "path": str(pluslife),
                        "source_fingerprint": m.source_fingerprint(pluslife),
                        "summary": "Other Org notes with dates.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "Pluslife material.",
                                "content": pluslife_content,
                                "content_sha256": m.sha256_hex(pluslife_content.encode("utf-8")),
                                "content_bytes": len(pluslife_content.encode("utf-8")),
                            }
                        ],
                    },
                ],
            }

            text, sources = m.retrieve_from_index(index, "summarize the last three days present in logbook.org")
            assert "May23 logbook latest action" in text
            assert "May19 logbook second-latest action" in text
            assert "May18 logbook third-latest action" in text
            assert "pluslife distractor" not in text
            index_source = next(source for source in sources if source.get("kind") == "index")
            assert index_source["temporal_selected_dates"] == ["2026-05-23", "2026-05-19", "2026-05-18"]
            chunks = [source for source in sources if source.get("kind") == "chunk"]
            assert chunks and all(source["path"].endswith("logbook.org") for source in chunks)
    finally:
        if old_evidence is None:
            os.environ.pop("MOTOKO_EVIDENCE_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = old_evidence
        if old_vector is None:
            os.environ.pop("MOTOKO_VECTOR_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_VECTOR_RETRIEVAL"] = old_vector


def test_live_index_retrieval_uses_service_boundary(m):
    with isolated_state() as tmp:
        docs = tmp / "orgfiles"
        docs.mkdir()
        path = docs / "logbook.org"
        content = "* [2026-05-23 Sat 00:36]\n** log\nRetrieval boundary smoke test.\n"
        path.write_text(content, encoding="utf-8")
        index = {
            "id": "service-boundary-index",
            "name": "orgfiles",
            "root": str(docs),
            "created": "2026-05-24T00:00:00+00:00",
            "files": [
                {
                    "path": str(path),
                    "source_fingerprint": m.source_fingerprint(path),
                    "summary": "Daily logbook entries.",
                    "chunks": [
                        {
                            "chunk": 1,
                            "summary": "Retrieval boundary notes.",
                            "content": content,
                            "content_sha256": m.sha256_hex(content.encode("utf-8")),
                            "content_bytes": len(content.encode("utf-8")),
                        }
                    ],
                }
            ],
        }
        text, sources = m.retrieve_from_index(index, "logbook.org retrieval boundary")
        index_source = next(source for source in sources if source.get("kind") == "index")
        assert index_source["retrieval_service_schema"] == "retrieval-service-v1"
        assert "Retrieval boundary smoke test" in text


def test_render_context_with_sources_uses_live_retrieval_service(m):
    old_evidence = os.environ.get("MOTOKO_EVIDENCE_RETRIEVAL")
    old_vector = os.environ.get("MOTOKO_VECTOR_RETRIEVAL")
    try:
        os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = "0"
        os.environ["MOTOKO_VECTOR_RETRIEVAL"] = "0"
        with isolated_state() as tmp:
            docs = tmp / "orgfiles"
            docs.mkdir()
            (docs / "notes.org").write_text("* Alpha\nRetrieval service attached context.\n", encoding="utf-8")
            m.add_allowed_dir(str(docs))

            old_quiet_model = m.quiet_model
            try:
                m.quiet_model = lambda *args, **kwargs: "summary"
                index = m.build_document_index(str(docs))
                text, sources = m.render_context_with_sources(
                    [{"kind": "index", "id": index["id"]}],
                    "alpha attached context",
                )
            finally:
                m.quiet_model = old_quiet_model

            assert "Retrieval service attached context" in text
            index_source = next(source for source in sources if source.get("kind") == "index")
            assert index_source["retrieval_service_schema"] == "retrieval-service-v1"
    finally:
        if old_evidence is None:
            os.environ.pop("MOTOKO_EVIDENCE_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = old_evidence
        if old_vector is None:
            os.environ.pop("MOTOKO_VECTOR_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_VECTOR_RETRIEVAL"] = old_vector


def test_temporal_retrieval_finds_latest_org_dates_without_evidence_store(m):
    old_evidence = os.environ.get("MOTOKO_EVIDENCE_RETRIEVAL")
    old_vector = os.environ.get("MOTOKO_VECTOR_RETRIEVAL")
    try:
        os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = "0"
        os.environ["MOTOKO_VECTOR_RETRIEVAL"] = "0"
        with isolated_state() as tmp:
            docs = tmp / "orgfiles"
            docs.mkdir()
            path = docs / "logbook.org"
            old_content = (
                "* [2026-04-09 Thu 12:39]\n"
                "** log\n"
                "Older logbook material repeats logbook.org latest days many times.\n"
            )
            recent_content = (
                "* [2026-05-18 Mon 11:14]\n"
                "** do\n"
                "*** TODO Keep the first recent day\n"
                "** log\n"
                "First recent log entry.\n\n"
                "* [2026-05-19 Tue 12:34]\n"
                "** do\n"
                "*** TODO Keep the second recent day\n"
                "** log\n"
                "Second recent log entry.\n"
            )
            path.write_text(old_content + "\n" + recent_content, encoding="utf-8")
            index = {
                "id": "temporal-index",
                "name": "orgfiles",
                "root": str(docs),
                "created": "2026-05-24T00:00:00+00:00",
                "files": [
                    {
                        "path": str(path),
                        "source_fingerprint": m.source_fingerprint(path),
                        "summary": "Daily logbook entries.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "Older logbook material.",
                                "content": old_content,
                                "content_sha256": m.sha256_hex(old_content.encode("utf-8")),
                                "content_bytes": len(old_content.encode("utf-8")),
                            },
                            {
                                "chunk": 2,
                                "summary": "Recent logbook material.",
                                "content": recent_content,
                                "content_sha256": m.sha256_hex(recent_content.encode("utf-8")),
                                "content_bytes": len(recent_content.encode("utf-8")),
                            },
                        ],
                    }
                ],
            }

            text, sources = m.retrieve_from_index(index, "summarize the last two days present in logbook.org")
            assert "2026-05-18" in text
            assert "2026-05-19" in text
            assert "2026-04-09" not in text
            chunks = [source for source in sources if source.get("kind") == "chunk"]
            assert chunks
            assert "temporal" in chunks[0].get("retrieval_methods", [])
            assert chunks[0].get("excerpt_selection") == "evidence-store"
    finally:
        if old_evidence is None:
            os.environ.pop("MOTOKO_EVIDENCE_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = old_evidence
        if old_vector is None:
            os.environ.pop("MOTOKO_VECTOR_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_VECTOR_RETRIEVAL"] = old_vector


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
        index = {
            "id": "20260525-030000-cccccc",
            "name": "study-focus",
            "root": m.current_project_root_record()["root"],
            "created": "2026-05-25T03:00:00+00:00",
            "corpus_summary": "study focus",
            "files": [],
        }
        m.atomic_write(m.index_path(index["id"]), json.dumps(index, ensure_ascii=False) + "\n")
        conv["context_items"] = [m.context_item_from_index(index)]
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


def test_context_package_builds_sources_and_plan(m):
    package = m.build_context_package(
        [
            m.ContextLane("identity", "Motoko realm", [{"kind": "identity"}], "realm"),
            m.ContextLane("attached context", "source excerpt", [{"kind": "chunk"}], "evidence"),
        ],
        budget_chars=100,
    )

    assert [source["kind"] for source in package.sources[:-1]] == ["identity", "chunk"]
    assert package.sources[-1]["kind"] == "context-plan"
    assert package.context_plan["context_package_schema"] == "context-package-v1"
    assert package.context_plan["lanes"][1]["lane"] == "attached context"
    assert package.context_plan["lanes"][1]["sources"] == 1
    assert package.text_for("identity") == "Motoko realm"
    preview = m.build_retrieval_preview_result(
        "source query",
        package,
        audit={"status": "grounded"},
    )
    assert preview.query == "source query"
    assert preview.attached_context == "source excerpt"
    assert preview.context_plan["context_package_schema"] == "context-package-v1"
    assert preview.diagnostics["kind"] == "retrieval-preview"
    assert preview.diagnostics["source_count"] == len(package.sources)


def test_system_prompt_uses_context_package_for_plan(m):
    with isolated_state():
        conv = m.new_conversation("Context package")
        prompt, sources = m.build_system_prompt_and_sources(conv, "planning")
        package, values = m.build_prompt_context_package(conv, "planning")
        plan = next(source for source in sources if source.get("kind") == "context-plan")

        assert "Context selection plan:" in prompt
        assert plan["context_package_schema"] == "context-package-v1"
        lane_names = [row.get("lane") for row in plan.get("lanes", [])]
        assert lane_names[:2] == ["identity", "personality"]
        assert "attached context" in lane_names
        assert package.text_for("attached context") == values["context_text"]


def test_prompt_context_filters_attached_artifacts_to_current_project(m):
    old_cwd = os.getcwd()
    old_evidence = os.environ.get("MOTOKO_EVIDENCE_RETRIEVAL")
    old_vector = os.environ.get("MOTOKO_VECTOR_RETRIEVAL")
    try:
        os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = "0"
        os.environ["MOTOKO_VECTOR_RETRIEVAL"] = "0"
        with isolated_state() as tmp:
            current = tmp / "current"
            other = tmp / "other"
            current.mkdir()
            other.mkdir()
            current_file = current / "notes.md"
            other_file = other / "notes.md"
            current_text = "Alpha current project implementation note."
            other_text = "Alpha other project private note."
            current_file.write_text(current_text, encoding="utf-8")
            other_file.write_text(other_text, encoding="utf-8")
            os.chdir(current)

            current_index = {
                "id": "20260525-010000-aaaaaa",
                "name": "current",
                "root": str(current.resolve()),
                "created": "2026-05-25T01:00:00+00:00",
                "corpus_summary": "current project summary",
                "files": [
                    {
                        "path": str(current_file.resolve()),
                        "source_fingerprint": m.source_fingerprint(current_file),
                        "summary": "current note",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "current chunk",
                                "content": current_text,
                                "content_sha256": m.sha256_hex(current_text.encode("utf-8")),
                            }
                        ],
                    }
                ],
            }
            other_index = {
                "id": "20260525-020000-bbbbbb",
                "name": "other",
                "root": str(other.resolve()),
                "created": "2026-05-25T02:00:00+00:00",
                "corpus_summary": "other project summary",
                "files": [
                    {
                        "path": str(other_file.resolve()),
                        "source_fingerprint": m.source_fingerprint(other_file),
                        "summary": "other note",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "other chunk",
                                "content": other_text,
                                "content_sha256": m.sha256_hex(other_text.encode("utf-8")),
                            }
                        ],
                    }
                ],
            }
            m.atomic_write(m.index_path(current_index["id"]), json.dumps(current_index, ensure_ascii=False, indent=2) + "\n")
            m.atomic_write(m.index_path(other_index["id"]), json.dumps(other_index, ensure_ascii=False, indent=2) + "\n")
            conv = m.new_conversation("Scoped context")
            conv["context_items"] = [
                m.context_item_from_index(current_index),
                m.context_item_from_index(other_index),
            ]
            package, values = m.build_prompt_context_package(conv, "alpha implementation")

            assert current_text in values["context_text"]
            assert other_text not in values["context_text"]
            assert any(source.get("root") == str(current.resolve()) for source in package.sources if source.get("kind") == "index")
            assert not any(source.get("root") == str(other.resolve()) for source in package.sources if source.get("kind") == "index")

            starved = m.new_conversation("Scoped fallback")
            starved["context_items"] = [m.context_item_from_index(other_index)]
            fallback_package, fallback_values = m.build_prompt_context_package(starved, "alpha implementation")
            scope_source = next(source for source in fallback_package.sources if source.get("kind") == "project-scope")
            assert current_text in fallback_values["context_text"]
            assert other_text not in fallback_values["context_text"]
            assert scope_source["filtered_context_items"] == 1
            assert scope_source["fallback_index_id"] == current_index["id"]
            assert "retried with current-project index" in fallback_values["scope_text"]

            missing = m.new_conversation("Missing attached index")
            missing["context_items"] = [{"kind": "index", "id": "20260525-030000-cccccc"}]
            missing_package, missing_values = m.build_prompt_context_package(missing, "alpha implementation")
            missing_scope_source = next(
                source for source in missing_package.sources if source.get("kind") == "project-scope"
            )
            assert current_text in missing_values["context_text"]
            assert missing_scope_source["filtered_context_items"] == 1
            assert missing_scope_source["fallback_index_id"] == current_index["id"]
    finally:
        os.chdir(old_cwd)
        if old_evidence is None:
            os.environ.pop("MOTOKO_EVIDENCE_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = old_evidence
        if old_vector is None:
            os.environ.pop("MOTOKO_VECTOR_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_VECTOR_RETRIEVAL"] = old_vector


def test_project_scope_filters_topic_reuse_before_attachment(m):
    old_cwd = os.getcwd()
    try:
        with isolated_state() as tmp:
            current = tmp / "current"
            other = tmp / "other"
            current.mkdir()
            other.mkdir()
            current_file = current / "notes.md"
            other_file = other / "notes.md"
            current_file.write_text("Alpha implementation current project.", encoding="utf-8")
            other_file.write_text("Alpha implementation other project.", encoding="utf-8")
            os.chdir(current)
            current_topic = {
                "id": "topic-current",
                "name": "Alpha current implementation",
                "query": "alpha implementation",
                "summary": "Alpha implementation current project",
                "source_indexes": [{"root": str(current.resolve())}],
                "evidence": [{"path": str(current_file.resolve()), "chunk": 1}],
            }
            other_topic = {
                "id": "topic-other",
                "name": "Alpha other implementation",
                "query": "alpha implementation",
                "summary": "Alpha implementation other project alpha implementation",
                "source_indexes": [{"root": str(other.resolve())}],
                "evidence": [{"path": str(other_file.resolve()), "chunk": 1}],
            }
            m.atomic_write(m.topic_path(other_topic["id"]), json.dumps(other_topic, ensure_ascii=False, indent=2) + "\n")
            m.atomic_write(m.topic_path(current_topic["id"]), json.dumps(current_topic, ensure_ascii=False, indent=2) + "\n")
            conv = m.new_conversation("Topic reuse")
            scope = m.project_scope_for_request(conv, "alpha implementation")
            topic = m.maybe_attach_relevant_existing_topic(conv, "alpha implementation", project_scope=scope)

            assert topic is not None
            assert topic["id"] == current_topic["id"]
            assert conv["context_items"] == [m.context_item_from_topic(current_topic)]
            assert [row["id"] for row in m.ranked_topics_for_query("alpha implementation", project_scope=scope)] == [
                current_topic["id"]
            ]
    finally:
        os.chdir(old_cwd)


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
        ui.answer_phase = "thinking"
        ui.answer_reasoning = "checking source excerpts"
        ui.events = m.collections.deque()
        ui.events_lock = threading.Lock()
        ui.dirty = False

        rows = [m.strip_ansi(row) for row in ui.body_display(60) if row.strip()]
        assert rows[0].startswith("› identity: Motoko")
        assert rows[1].startswith("› Done answer.")
        assert rows[2].startswith("● Thinking (32s)")
        assert "checking source excerpts" in rows[2]
        assert rows[3].startswith("Worked for 6m 32s ")
        assert "─" in rows[3]
        ui.events.append(("token", "token-fragment"))
        ui.drain_events()
        assert ui.answer_phase == "answering"
        rows = [m.strip_ansi(row) for row in ui.body_display(60) if row.strip()]
        assert rows[2].startswith("● Answering ")
        assert "checking source excerpts" not in rows[2]
        live_rows = [m.strip_ansi(row) for row in ui.live_answer_display(60) if row.strip()]
        assert live_rows[0].startswith("● Answering ")
        assert all("token-fragment" not in row for row in live_rows)


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


def test_tui_vector_status_reports_stale_progress(m):
    with isolated_state():
        ui = object.__new__(m.MotokoTui)
        ui.conv = {"title": "Vector Status"}
        ui.generating = False
        ui.maintaining = False
        ui.report_running = 0
        ui.report_status = ""
        ui.pending_prompts = m.collections.deque()
        ui.study_running = True
        ui.study_status = "bg-heavy: vectorizing(model) batch 1/9 rows 2/20 eta 2m"
        now_value = m.time.monotonic()
        ui.study_phase_started = now_value - 1200
        ui.study_phase_updated = now_value - (m.SAFE_PROGRESS_STALE_SECONDS + 5)
        ui.study_last_note = ""
        ui.status = "ready"
        ui.index_progress = None

        status = m.strip_ansi(" ".join(ui.status_display(100)))
        assert "vectorizing stalled?" in status
        assert "last progress" in status
        assert "ready" not in status


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
        first_raw = "".join(captured)
        first = m.strip_ansi(first_raw)
        assert "\x1b[H" not in first_raw
        assert "\033[1;10r\033[10;1H" in first_raw
        assert "\033[r" in first_raw
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


def test_tui_active_answer_streams_stable_lines_to_scrollback(m):
    with isolated_state():
        captured = []
        ui = object.__new__(m.MotokoTui)
        ui.messages = []
        ui.answer_entry = {
            "role": "assistant",
            "content": "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu",
        }
        ui.generating = True
        ui.rendered_message_ids = set()
        ui.bottom_rows_rendered = 1
        ui.bottom_cursor_row_offset = 0
        ui.bottom_frame_key = None
        ui.answer_stream_width = 0
        ui.answer_stream_emitted_lines = 0
        ui.write = captured.append

        ui.sync_active_answer_transcript(24, 10, reserved_rows=2)

        first = m.strip_ansi("".join(captured))
        assert "\033[1;8r" in "".join(captured)
        assert "alpha" in first
        assert ui.answer_stream_emitted_lines > 0

        captured.clear()
        ui.sync_active_answer_transcript(24, 10, reserved_rows=2)
        assert captured == []

        ui.sync_active_answer_transcript(24, 10, reserved_rows=2, final=True)
        final = m.strip_ansi("".join(captured))
        assert "lambda" in final or "mu" in final
        assert id(ui.answer_entry) in ui.rendered_message_ids


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


def test_core_memory_report_formatters_are_injectable(m):
    rows = [
        {
            "id": "mem-1",
            "text": "Javier likes grounded retrieval.",
            "importance": 4,
            "pinned": True,
            "created": "2026-05-23T00:00:00+00:00",
            "source": "test",
            "conversation_id": "conv-1",
            "derived_from": "manual",
            "tags": ["retrieval"],
            "seen_count": 2,
            "_score": 42,
            "_matched_terms": 3,
        }
    ]

    memories = m.format_memory_rows(rows, verbose=True)
    search = m.format_memory_search_rows(rows)

    assert "mem-1" in memories
    assert "i4 pin" in memories
    assert "source: test" in memories
    assert "conversation: conv-1" in memories
    assert "tags: retrieval" in memories
    assert "score= 42" in search
    assert "match= 3" in search
    assert m.format_memory_rows([]) == "No memories yet."
    assert m.format_memory_search_rows([]) == "No matching memories."


def test_core_memory_context_renderer_is_injectable(m):
    text, sources = m.render_memories_with_sources_core(
        [
            {
                "id": "mem-1",
                "text": "Javier likes grounded retrieval.",
                "source": "test",
                "conversation_id": "conv-1",
                "created": "2026-05-23T00:00:00+00:00",
                "importance": 4,
                "pinned": True,
                "_score": 20,
                "_matched_terms": 3,
                "_thread_matched_terms": 1,
            }
        ],
        has_any_memory=True,
    )

    assert "[memory:mem-1; pinned, importance=4, match=3, thread=1]" in text
    assert sources == [
        {
            "kind": "memory",
            "id": "mem-1",
            "source": "test",
            "conversation_id": "conv-1",
            "created": "2026-05-23T00:00:00+00:00",
            "importance": 4,
            "pinned": True,
            "score": 20,
            "matched_terms": 3,
        }
    ]
    assert m.render_memories_with_sources_core([], has_any_memory=True)[0] == "No saved memories matched this turn strongly."
    assert m.render_memories_with_sources_core([], has_any_memory=False)[0] == "No saved memories yet."


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


def test_list_conversations_omits_empty_chats_but_keeps_queued_prompts(m):
    with isolated_state():
        empty = m.new_conversation("Empty")
        empty["id"] = "empty-chat"
        m.save_conversation(empty)

        queued = m.new_conversation("Queued")
        queued["id"] = "queued-chat"
        m.append_queued_prompt_record(queued, "run this after bg-heavy work", created=m.now())
        m.save_conversation(queued)

        rows = m.list_conversations()
        ids = [row.get("id") for row in rows]
        assert "empty-chat" not in ids
        assert "queued-chat" in ids


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

        old_default_vector_index = m.default_vector_index
        old_latest_evidence_store_for_index = m.latest_evidence_store_for_index
        old_build_evidence_store_from_index = m.build_evidence_store_from_index
        old_query_evidence_store = m.query_evidence_store
        old_format_evidence_query_report = m.format_evidence_query_report
        try:
            m.default_vector_index = lambda conv_arg, project_scope=None: {"id": "idx"}
            m.latest_evidence_store_for_index = lambda index, fresh_only=True: {"id": "store", "index": index["id"]}
            m.build_evidence_store_from_index = lambda index, write=False, **_kwargs: {"id": "built-store", "index": index["id"]}
            m.query_evidence_store = lambda store, query, **_kwargs: {"store": store, "query": query}
            m.format_evidence_query_report = lambda report: f"evidence query: {report['query']}"
            ui.handle_command("/evidence-query texere")
            deadline = time.monotonic() + 2
            while ui.report_running and time.monotonic() < deadline:
                ui.drain_events()
                time.sleep(0.01)
            ui.drain_events()
        finally:
            m.default_vector_index = old_default_vector_index
            m.latest_evidence_store_for_index = old_latest_evidence_store_for_index
            m.build_evidence_store_from_index = old_build_evidence_store_from_index
            m.query_evidence_store = old_query_evidence_store
            m.format_evidence_query_report = old_format_evidence_query_report

        assert ui.overlay_title == "/evidence-query"
        assert ui.overlay_lines == ["evidence query: texere"]

        old_latest_vector_store = m.latest_vector_store
        old_query_vector_store = m.query_vector_store
        old_format_vector_query_report = m.format_vector_query_report
        try:
            m.latest_vector_store = lambda: {"id": "vector-store"}
            m.query_vector_store = lambda store, query, limit=None, rerank=False, **_kwargs: {
                "store": store,
                "query": query,
                "rerank": rerank,
                "rows": [],
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
            def slow_build_messages(conv_arg, query="", **_kwargs):
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


def test_tui_queued_prompt_is_durable_and_history_seeded(m):
    with isolated_state():
        conv = m.new_conversation("Queued prompt")
        conv["id"] = "queued-prompt"
        write_conversation(m, conv)

        ui = object.__new__(m.MotokoTui)
        ui.conv = conv
        ui.messages = []
        ui.scroll = 0
        ui.dirty = False
        ui.status = "ready"
        ui.pending_prompts = m.collections.deque()

        ui.queue_prompt("queued behind active work", "prompt queued")

        saved = json.loads(m.conversation_path(conv["id"]).read_text(encoding="utf-8"))
        assert saved["queued_prompts"][0]["content"] == "queued behind active work"
        assert ui.pending_prompts[0] == "queued behind active work"
        assert any(row.get("role") == "queued" for row in ui.messages)

        history = m.MotokoTui.seed_input_history(ui, saved)
        assert history[-1] == "queued behind active work"

        popped = ui.pop_next_queued_prompt()
        assert popped == "queued behind active work"
        saved_after = json.loads(m.conversation_path(conv["id"]).read_text(encoding="utf-8"))
        assert saved_after.get("queued_prompts") == []


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
            def slow_build_messages(conv_arg, query="", **_kwargs):
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


def test_tui_blocking_command_records_foreground_job(m):
    ui = object.__new__(m.MotokoTui)
    ui.conv = {"messages": []}
    ui.messages = []
    ui.scroll = 0
    ui.dirty = False
    ui.generating = False
    ui.jobs = m.JobSupervisor(id_factory=lambda: "foreground-job")
    ui.restore_for_blocking = lambda: None
    ui.reenter_after_blocking = lambda: None
    ui.seed_messages = lambda conv: []
    ui.append = lambda role, content: ui.messages.append({"role": role, "content": content})

    with contextlib.redirect_stdout(io.StringIO()):
        ui.run_blocking_command("Studying context...", lambda: "study done")

    rows = ui.jobs.snapshots(include_done=True)
    assert rows[0]["kind"] == "foreground"
    assert rows[0]["lane"] == "cpu"
    assert rows[0]["status"] == m.JOB_STATUS_COMPLETED
    assert rows[0]["label"] == "Studying context..."


def test_cli_heavy_commands_pass_cancel_events(m):
    seen = {}
    old_build_document_index = m.build_document_index
    old_refresh_vector_stores = m.refresh_vector_stores
    old_refresh_evidence_stores = m.refresh_evidence_stores
    old_cleanup_superseded_stale_indexes = m.cleanup_superseded_stale_indexes
    old_source_lifecycle_report_for_index = m.source_lifecycle_report_for_index
    old_run_background_now_text = m.run_background_now_text
    old_upgrade_index_artifacts = m.upgrade_index_artifacts
    old_repair_index_artifacts = m.repair_index_artifacts
    old_refresh_profile_dossier = m.refresh_profile_dossier
    old_study_query = m.study_query
    old_load_conversation = m.load_conversation
    old_load_index = m.load_index

    def fake_build_document_index(path, pattern, name=None, max_derived_bytes=None, *, cancel_event=None):
        seen["index"] = cancel_event
        return {"id": "idx", "name": name or "docs", "root": path, "glob": pattern}

    def fake_refresh_vector_stores(**kwargs):
        seen["vector_refresh"] = kwargs.get("cancel_event")
        return {
            "status": "no-build",
            "built": 0,
            "method": kwargs.get("method", ""),
            "created": "2026-05-31T00:00:00+00:00",
            "items": [],
        }

    def fake_refresh_evidence_stores(**kwargs):
        seen["evidence_refresh"] = kwargs.get("cancel_event")
        return {"status": "no-build", "built": 0, "created": "2026-05-31T00:00:00+00:00", "items": []}

    def fake_cleanup_superseded_stale_indexes(*, limit=1, dry_run=False, cancel_event=None):
        seen["index_cleanup"] = cancel_event
        return {
            "schema": m.INDEX_CLEANUP_SCHEMA_VERSION,
            "created": "2026-05-31T00:00:00+00:00",
            "dry_run": dry_run,
            "candidate_count": 0,
            "selected_count": 0,
            "materialized": [],
            "deleted": [],
            "blocked": [],
        }

    def fake_source_lifecycle_report_for_index(index, *, apply=False, yes=False, cancel_event=None):
        seen["source_lifecycle"] = cancel_event
        return {
            "schema": "source-lifecycle-report-v1",
            "created": "2026-05-31T00:00:00+00:00",
            "dry_run": not apply,
            "index": {"id": index.get("id", "")},
            "replacement": {},
            "plan": {"apply_status": "no-op", "apply_reason": "test"},
            "source_lifecycle": [],
        }

    def fake_run_background_now_text(conv, **kwargs):
        seen["bg_now"] = kwargs.get("cancel_event")
        return "bg-now ok"

    def fake_upgrade_index_artifacts(index, *, cancel_event=None):
        seen["index_upgrade"] = cancel_event
        return index, False, "upgrade ok"

    def fake_repair_index_artifacts(index, *, limit=None, phase_callback=None, cancel_event=None):
        seen["index_repair"] = cancel_event
        return index, False, "repair ok"

    def fake_refresh_profile_dossier(*, cancel_event=None):
        seen["profile_refresh"] = cancel_event
        return {"updated": "2026-05-31T00:00:00+00:00"}

    def fake_study_query(conv, query, *, focus=None, cancel_event=None):
        seen["study"] = cancel_event
        return "study ok"

    try:
        m.build_document_index = fake_build_document_index
        m.refresh_vector_stores = fake_refresh_vector_stores
        m.refresh_evidence_stores = fake_refresh_evidence_stores
        m.cleanup_superseded_stale_indexes = fake_cleanup_superseded_stale_indexes
        m.source_lifecycle_report_for_index = fake_source_lifecycle_report_for_index
        m.run_background_now_text = fake_run_background_now_text
        m.upgrade_index_artifacts = fake_upgrade_index_artifacts
        m.repair_index_artifacts = fake_repair_index_artifacts
        m.refresh_profile_dossier = fake_refresh_profile_dossier
        m.study_query = fake_study_query
        m.load_conversation = lambda _selector: {"id": "conv", "title": "Conversation", "messages": []}
        m.load_index = lambda _selector=None: {"id": "idx", "name": "docs", "root": "/tmp/docs"}
        with contextlib.redirect_stdout(io.StringIO()):
            m.command_index(
                m.argparse.Namespace(
                    plan=False,
                    path="/tmp/docs",
                    glob=m.AUTO_INDEX_GLOB,
                    name="docs",
                    max_derived_bytes=None,
                )
            )
            m.command_vector_refresh(
                m.argparse.Namespace(
                    index=None,
                    force=False,
                    limit=1,
                    method=m.EMBEDDING_VECTOR_METHOD,
                    max_chunks=None,
                    json=False,
                )
            )
            m.command_evidence_refresh(
                m.argparse.Namespace(
                    index=None,
                    force=False,
                    limit=1,
                    json=False,
                )
            )
            m.command_index_cleanup(
                m.argparse.Namespace(
                    limit=1,
                    yes=False,
                    json=False,
                )
            )
            m.command_source_lifecycle(
                m.argparse.Namespace(
                    index=None,
                    apply=False,
                    yes=False,
                    json=False,
                )
            )
            m.command_index_upgrade(
                m.argparse.Namespace(
                    all=False,
                    limit=None,
                    index=None,
                )
            )
            m.command_index_repair(
                m.argparse.Namespace(
                    all=False,
                    limit=1,
                    index=None,
                )
            )
            m.command_profile(
                m.argparse.Namespace(
                    profile_command="refresh",
                )
            )
            m.command_bg_now(
                m.argparse.Namespace(
                    conversation=None,
                    no_cwd=True,
                )
            )
            m.command_study(
                m.argparse.Namespace(
                    query=["find", "context"],
                    focus=None,
                    conversation="conv",
                    title=None,
                )
            )
    finally:
        m.build_document_index = old_build_document_index
        m.refresh_vector_stores = old_refresh_vector_stores
        m.refresh_evidence_stores = old_refresh_evidence_stores
        m.cleanup_superseded_stale_indexes = old_cleanup_superseded_stale_indexes
        m.source_lifecycle_report_for_index = old_source_lifecycle_report_for_index
        m.run_background_now_text = old_run_background_now_text
        m.upgrade_index_artifacts = old_upgrade_index_artifacts
        m.repair_index_artifacts = old_repair_index_artifacts
        m.refresh_profile_dossier = old_refresh_profile_dossier
        m.study_query = old_study_query
        m.load_conversation = old_load_conversation
        m.load_index = old_load_index

    assert isinstance(seen["index"], threading.Event)
    assert isinstance(seen["vector_refresh"], threading.Event)
    assert isinstance(seen["evidence_refresh"], threading.Event)
    assert isinstance(seen["index_cleanup"], threading.Event)
    assert isinstance(seen["source_lifecycle"], threading.Event)
    assert isinstance(seen["index_upgrade"], threading.Event)
    assert isinstance(seen["index_repair"], threading.Event)
    assert isinstance(seen["profile_refresh"], threading.Event)
    assert isinstance(seen["bg_now"], threading.Event)
    assert isinstance(seen["study"], threading.Event)


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
    assert ui.answer_phase == "stopping"
    assert ui.messages[-1]["content"] == "stopping current answer"


def test_tui_ctrl_c_stops_active_answer_without_exiting(m):
    with isolated_state():
        conv = m.new_conversation("Interrupt")
        ui = object.__new__(m.MotokoTui)
        ui.conv = conv
        ui.messages = []
        ui.scroll = 0
        ui.dirty = False
        ui.status = "ready"
        ui.running = True
        ui.generating = True
        ui.pending_prompts = m.collections.deque(["queued followup"])
        ui.cancel_event = threading.Event()
        ui.active_model_lock = threading.Lock()
        ui.active_model_response = None
        ui.active_model_connection = None

        ui.handle_key("\x03")

        assert ui.running
        assert ui.cancel_event.is_set()
        assert not ui.pending_prompts
        assert ui.answer_phase == "stopping"
        assert "discarded 1 queued prompt" in ui.messages[-1]["content"]


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


def test_retrieval_eval_replays_private_feedback_fixtures(m):
    with isolated_state() as tmp:
        docs = tmp / "orgfiles"
        docs.mkdir()
        path = docs / "logbook.org"
        content = "* [2026-05-23 Sat 00:36]\n** log\nFeedback replay source.\n"
        path.write_text(content, encoding="utf-8")
        index = {
            "id": "feedback-retrieval-index",
            "name": "orgfiles",
            "root": str(docs),
            "created": "2026-05-24T00:00:00+00:00",
            "files": [
                {
                    "path": str(path),
                    "source_fingerprint": m.source_fingerprint(path),
                    "summary": "Daily logbook entries.",
                    "chunks": [
                        {
                            "chunk": 1,
                            "summary": "Feedback replay notes.",
                            "content": content,
                            "content_sha256": m.sha256_hex(content.encode("utf-8")),
                            "content_bytes": len(content.encode("utf-8")),
                        }
                    ],
                }
            ],
        }
        m.atomic_write(m.index_path(index["id"]), json.dumps(index, ensure_ascii=False, indent=2) + "\n")
        conv = m.new_conversation("Feedback replay")
        conv["id"] = "feedback-replay-conv"
        conv["messages"] = [
            {"role": "user", "content": "summarize logbook.org feedback replay"},
            {"role": "assistant", "content": "It mentions feedback replay."},
        ]
        conv["last_sources"] = [
            {
                "kind": "chunk",
                "index": index["id"],
                "path": str(path),
                "chunk": 1,
                "retrieval": "hybrid",
                "retrieval_methods": ["temporal"],
            }
        ]
        m.record_response_feedback(conv, "down", "check retrieval replay")

        report = m.run_retrieval_eval()
        assert report["feedback_fixture_count"] == 1
        row = report["feedback_fixtures"][0]
        assert row["replay_status"] == "matched_previous_sources"
        assert row["hinted_paths"] == [str(path)]
        text = m.format_retrieval_eval_report(report)
        assert "feedback fixtures: 1" in text
        assert "matched_previous_sources" in text


def test_retrieval_preview_shows_context_without_model_call(m):
    with isolated_state():
        task_path = pathlib.Path.cwd() / "tasks.org"
        conv = m.new_conversation("Preview")
        conv["context_items"] = [
            {
                "kind": "file",
                "path": str(task_path),
                "content": "* TODO Prepare tomorrow plan\nDEADLINE: <2026-05-22 Fri>\n",
                "bytes": 60,
            }
        ]
        report = m.format_retrieval_preview(conv, "tomorrow plan")
        assert "retrieval preview:" in report
        assert "source audit:" in report
        assert "attached context excerpt:" in report
        assert "Prepare tomorrow plan" in report
        assert str(task_path) in report
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


def test_vector_refresh_model_residency_defer_is_retryable(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        index = {
            "id": "vector-defer-index",
            "name": "docs",
            "root": str(docs),
            "glob": m.AUTO_INDEX_GLOB,
            "created": m.now(),
            "corpus_summary": "",
            "files": [],
        }
        m.atomic_write(m.index_path(index["id"]), json.dumps(index, ensure_ascii=False, indent=2) + "\n")

        old_build = m.build_vector_store_from_index
        try:
            m.build_vector_store_from_index = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                SystemExit("embedding request deferred: worker route qwen3-embedding-0b6 waiting 90s for recent chat route qwen36-chat-default")
            )
            report = m.refresh_vector_stores(
                index_id=index["id"],
                force=True,
                limit=1,
                method=m.LEXICAL_VECTOR_METHOD,
            )
        finally:
            m.build_vector_store_from_index = old_build

        assert report["status"] == "deferred"
        assert report["built"] == 0
        assert report["items"][0]["status"] == "deferred"
        assert "embedding request deferred" in report["items"][0]["note"]
        text = m.format_vector_refresh_report(report)
        assert "vector refresh: deferred" in text
        assert "note: embedding request deferred" in text


def test_vector_refresh_report_shows_refresh_mode_and_cause(m):
    report = {
        "status": "built",
        "built": 1,
        "method": "embedding-v1",
        "created": "2026-05-31T00:00:00+00:00",
        "items": [
            {
                "status": "built",
                "index_id": "idx1",
                "name": "docs",
                "reason": "source index fingerprint changed",
                "store_id": "store1",
                "rows": 12,
                "batches": 2,
                "parallelism": 4,
                "requested_parallelism": 8,
                "fallbacks": 1,
                "refresh_mode": "incremental",
                "refresh_cause": "source-change",
                "reused_rows": 10,
                "embedded_rows": 2,
                "superseded_rows": 3,
            }
        ],
    }

    text = m.format_vector_refresh_report(report)

    assert "refresh: mode=incremental cause=source-change" in text
    assert "incremental: reused=10 embedded=2 superseded=3" in text


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


def test_retrieval_vector_query_uses_short_worker_timeouts(m):
    old_timeout = os.environ.get("MOTOKO_RETRIEVAL_MODEL_TIMEOUT")
    old_socket_timeout = os.environ.get("MOTOKO_RETRIEVAL_SOCKET_ACTIVATION_TIMEOUT")
    old_embed = m.embed_texts
    calls = []
    try:
        os.environ["MOTOKO_RETRIEVAL_MODEL_TIMEOUT"] = "7"
        os.environ["MOTOKO_RETRIEVAL_SOCKET_ACTIVATION_TIMEOUT"] = "8"

        def fake_embed(texts, **kwargs):
            calls.append(kwargs)
            return [[1.0, 0.0] for _text in texts], {"catalog_route": "embed-test"}

        m.embed_texts = fake_embed
        store = {
            "id": "short-timeout-store",
            "method": m.EMBEDDING_VECTOR_METHOD,
            "embedding_route": {"catalog_route": "embed-test"},
            "rows": [
                {
                    "id": "row1",
                    "path": "/tmp/logbook.org",
                    "chunk": 1,
                    "vector": [1.0, 0.0],
                    "summary": "latest logbook day",
                }
            ],
        }
        report = m.query_vector_store_for_retrieval(store, "latest logbook", limit=1, rerank=False)
        assert report["rows"]
        assert calls[0]["timeout"] == 7
        assert calls[0]["socket_activation_min_timeout"] == 8
    finally:
        m.embed_texts = old_embed
        if old_timeout is None:
            os.environ.pop("MOTOKO_RETRIEVAL_MODEL_TIMEOUT", None)
        else:
            os.environ["MOTOKO_RETRIEVAL_MODEL_TIMEOUT"] = old_timeout
        if old_socket_timeout is None:
            os.environ.pop("MOTOKO_RETRIEVAL_SOCKET_ACTIVATION_TIMEOUT", None)
        else:
            os.environ["MOTOKO_RETRIEVAL_SOCKET_ACTIVATION_TIMEOUT"] = old_socket_timeout


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


def test_vector_doctor_reports_embedding_parallelism_without_private_rows(m):
    old_endpoint = os.environ.get("MOTOKO_ENDPOINT")
    old_model = os.environ.get("MOTOKO_MODEL")
    old_parallel = os.environ.get("MOTOKO_EMBEDDING_PARALLEL")
    old_batch = os.environ.get("MOTOKO_EMBEDDING_BATCH_SIZE")
    try:
        os.environ.pop("MOTOKO_ENDPOINT", None)
        os.environ.pop("MOTOKO_MODEL", None)
        os.environ.pop("MOTOKO_EMBEDDING_PARALLEL", None)
        os.environ.pop("MOTOKO_EMBEDDING_BATCH_SIZE", None)
        with isolated_state() as tmp:
            docs = tmp / "docs"
            docs.mkdir()
            path = docs / "tasks.org"
            content = "* TODO Vector doctor\n"
            path.write_text(content, encoding="utf-8")
            catalog = {
                "realm": "mares",
                "manager": {"kind": "systemd-socket-worker"},
                "routes": {
                    "qwen3-embedding-0b6": {
                        "kind": "embedding",
                        "endpoint": "http://127.0.0.1:65530/v1/embeddings",
                        "modelId": "qwen3-embedding-0.6b-q8-0",
                        "tasks": ["embedding", "vector_index", "vector_query"],
                        "endpoint_paths": ["/v1/embeddings"],
                        "embedding_dimensions": 1024,
                        "maxParallel": 32,
                        "openai_compatible": True,
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            index = {
                "id": "vector-doctor-index",
                "name": "docs",
                "root": str(docs),
                "glob": m.AUTO_INDEX_GLOB,
                "created": "2026-05-31T00:00:00+00:00",
                "files": [
                    {
                        "path": str(path),
                        "source_fingerprint": m.source_fingerprint(path),
                        "summary": "Vector doctor task file.",
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "Vector doctor task.",
                                "content": content,
                                "content_sha256": m.sha256_hex(content.encode("utf-8")),
                            }
                        ],
                    }
                ],
            }
            m.atomic_write(m.index_path("vector-doctor-index"), json.dumps(index, ensure_ascii=False) + "\n")

            report = m.format_vector_doctor("vector-doctor-index")
            assert "vector doctor: embedding refresh throughput" in report
            assert "declared maxParallel: 32" in report
            assert "candidate rows:" in report
            assert "about 963 MiB VRAM can be normal" in report
    finally:
        if old_endpoint is None:
            os.environ.pop("MOTOKO_ENDPOINT", None)
        else:
            os.environ["MOTOKO_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("MOTOKO_MODEL", None)
        else:
            os.environ["MOTOKO_MODEL"] = old_model
        if old_parallel is None:
            os.environ.pop("MOTOKO_EMBEDDING_PARALLEL", None)
        else:
            os.environ["MOTOKO_EMBEDDING_PARALLEL"] = old_parallel
        if old_batch is None:
            os.environ.pop("MOTOKO_EMBEDDING_BATCH_SIZE", None)
        else:
            os.environ["MOTOKO_EMBEDDING_BATCH_SIZE"] = old_batch


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
                if not paused["requested"] and "rows 0/" not in message:
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


def test_embedding_vector_store_reuses_unchanged_rows_across_index_refresh(m):
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
            alpha_path = docs / "alpha.org"
            beta_path = docs / "beta.org"
            alpha_content = "* TODO Alpha vector task\nDEADLINE: <2026-05-30 Sat>\n"
            beta_content = "* TODO Beta vector task\n"
            alpha_path.write_text(alpha_content, encoding="utf-8")
            beta_path.write_text(beta_content, encoding="utf-8")

            def file_item(path: pathlib.Path, content: str, summary: str) -> dict:
                return {
                    "path": str(path),
                    "source_fingerprint": m.source_fingerprint(path),
                    "summary": summary,
                    "chunks": [
                        {
                            "chunk": 1,
                            "summary": summary,
                            "content": content,
                            "content_sha256": m.sha256_hex(content.encode("utf-8")),
                        }
                    ],
                }

            index1 = {
                "id": "incremental-vector-index-1",
                "name": "docs",
                "root": str(docs),
                "glob": m.AUTO_INDEX_GLOB,
                "created": "2026-05-21T10:00:00+00:00",
                "files": [
                    file_item(alpha_path, alpha_content, "Alpha vector task."),
                    file_item(beta_path, beta_content, "Beta vector task."),
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
                        "maxParallel": 1,
                        "openai_compatible": True,
                    }
                },
            }
            m.ensure_private_dir(m.config_root())
            m.atomic_write(m.local_models_path(), json.dumps(catalog, ensure_ascii=False) + "\n")
            m.atomic_write(m.index_path(index1["id"]), json.dumps(index1, ensure_ascii=False) + "\n")

            store1 = m.build_vector_store(index1["id"], method=m.EMBEDDING_VECTOR_METHOD)
            assert store1["row_count"] >= 4
            assert store1["vector_row_id_schema"] == m.VECTOR_ROW_ID_SCHEMA_VERSION

            beta_content_2 = "* TODO Beta vector task changed\nDEADLINE: <2026-06-01 Mon>\n"
            beta_path.write_text(beta_content_2, encoding="utf-8")
            index2 = {
                "id": "incremental-vector-index-2",
                "name": "docs",
                "root": str(docs),
                "glob": m.AUTO_INDEX_GLOB,
                "created": "2026-05-22T10:00:00+00:00",
                "files": [
                    file_item(alpha_path, alpha_content, "Alpha vector task."),
                    file_item(beta_path, beta_content_2, "Beta vector task changed."),
                ],
            }
            m.atomic_write(m.index_path(index2["id"]), json.dumps(index2, ensure_ascii=False) + "\n")
            due, reason = m.vector_store_due(index2, method=m.EMBEDDING_VECTOR_METHOD)
            assert due is True
            assert "reusable family vector store" in reason

            EmbeddingHandler.payloads = []
            phases = []
            store2 = m.build_vector_store_from_index(
                index2,
                method=m.EMBEDDING_VECTOR_METHOD,
                progress_callback=phases.append,
            )

            model_inputs = []
            for payload in EmbeddingHandler.payloads:
                inputs = payload.get("input", [])
                model_inputs.extend(inputs if isinstance(inputs, list) else [inputs])
            assert store2["source_index"]["id"] == index2["id"]
            assert store2["source_index"]["family_key"] == m.index_family_key(index2)
            assert store2["embedding_reuse_store_id"] == store1["id"]
            assert store2["embedding_refresh_mode"] == "incremental"
            assert store2["embedding_previous_store_reused_rows"] >= 2
            assert store2["embedding_superseded_rows"] >= 1
            assert len(model_inputs) == store2["embedding_embedded_rows"]
            assert store2["embedding_embedded_rows"] < store2["row_count"]
            assert m.vector_store_freshness(store2)[0] == "fresh"
            assert phases
            assert any("incremental" in phase for phase in phases)
            assert any(f"reuse {store2['embedding_reused_rows']}" in phase for phase in phases)
            assert any(f"new {store2['embedding_embedded_rows']}" in phase for phase in phases)

            alpha_rows_1 = {
                row["id"]: row
                for row in store1["rows"]
                if row.get("path") == str(alpha_path)
            }
            alpha_rows_2 = {
                row["id"]: row
                for row in store2["rows"]
                if row.get("path") == str(alpha_path)
            }
            assert alpha_rows_1
            assert alpha_rows_1.keys() <= alpha_rows_2.keys()
            for row_id, row in alpha_rows_1.items():
                assert alpha_rows_2[row_id]["vector"] == row["vector"]
                assert alpha_rows_2[row_id]["index"] == index2["id"]
            server.shutdown()
            server.server_close()
            server = None
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


def test_diagnose_safe_redacts_private_progress_metadata(m):
    with isolated_state():
        m.ensure_private_dir(m.indexes_dir())
        m.ensure_vector_progress_dir()
        old_time = (
            m._dt.datetime.now(m._dt.timezone.utc) - m._dt.timedelta(minutes=10)
        ).astimezone().isoformat(timespec="seconds")
        m.write_study_state(
            {
                "updated": old_time,
                "status": "running",
                "phase": "bg-heavy: vectorizing(model) orgfiles batch 1/9 rows 2/20 eta 2m",
                "notes": ["private logbook.org note"],
            }
        )
        index_progress = {
            "id": "secret-index-logbook",
            "kind": "index",
            "status": "running",
            "phase": "summarizing chunk",
            "root": "/home/mares/repos/orgfiles",
            "name": "orgfiles",
            "current_file": "/home/mares/repos/orgfiles/logbook.org",
            "last_model_label": "/home/mares/repos/orgfiles/logbook.org chunk 1",
            "error": "private filename logbook.org",
            "updated": old_time,
            "elapsed_seconds": 30,
            "eta_seconds": 120,
            "total_files": 3,
            "completed_files": 1,
            "estimated_chunks": 8,
            "completed_chunks": 2,
            "estimated_model_calls": 12,
            "completed_model_calls": 3,
            "percent": 25,
            "model_route": m.MODEL_ROUTE_INDEX_CHUNK,
            "background_lane": "small-model",
        }
        m.atomic_write(
            m.index_progress_path(index_progress["id"]),
            json.dumps(index_progress, ensure_ascii=False) + "\n",
        )
        vector_progress = {
            "schema": m.VECTOR_PROGRESS_SCHEMA_VERSION,
            "id": "embedding-secret-logbook-orgfiles",
            "updated": old_time,
            "source_index": {
                "id": "secret-index-logbook",
                "name": "orgfiles",
                "root": "/home/mares/repos/orgfiles",
            },
            "embedding_route": {
                "catalog_route": "qwen3-embedding-0b6",
                "model": "qwen3-embedding-0.6b",
            },
            "embedding_batch_size": 2,
            "embedding_requested_parallelism": 4,
            "embedding_parallelism": 4,
            "embedding_parallel_fallbacks": [],
            "expected_rows": 10,
            "completed_rows": 4,
            "eta_seconds": 90,
            "rows": [
                {
                    "id": "private-row",
                    "path": "/home/mares/repos/orgfiles/logbook.org",
                    "summary": "private summary text",
                    "evidence_excerpt": "private excerpt",
                    "vector": [0.1, 0.2],
                }
            ],
        }
        m.atomic_write(
            m.vector_progress_path(vector_progress["id"]),
            json.dumps(vector_progress, ensure_ascii=False) + "\n",
        )
        old_route_state = m.safe_model_route_state
        try:
            m.safe_model_route_state = lambda route: f"route={route} socket=inactive backend=inactive"
            report = m.format_diagnose_safe()
        finally:
            m.safe_model_route_state = old_route_state

        assert "safe diagnose: diagnose-safe-v1" in report
        assert "kind=index" in report
        assert "kind=vector" in report
        assert "state=stale" in report
        assert "rows=4/10" in report
        assert "files=1/3" in report
        assert "route=qwen3-embedding-0b6" in report
        for private_text in [
            "secret",
            "orgfiles",
            "logbook",
            "/home/mares",
            "private summary",
            "private excerpt",
            "private filename",
        ]:
            assert private_text not in report


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
        assert "call " not in m.format_index_progress_status(progress)

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
        scoped = m.format_context_catalog(
            {
                **catalog,
                "indexes": catalog["indexes"]
                + [
                    {
                        "id": "other-index",
                        "name": "other",
                        "root": "/tmp/other-project",
                        "status": "fresh",
                        "summary": "other project",
                    }
                ],
                "topics": [{"id": "topic-other", "name": "other", "query": "other"}],
                "dossiers": [{"id": "dossier-other", "name": "other", "query": "other"}],
            },
            project_roots={str(docs.resolve())},
        )
        assert "new-index" in scoped
        assert "other-index" not in scoped
        assert "available topic dossiers" not in scoped
        assert "available memory dossiers" not in scoped
        ranked = m.ranked_indexes_for_query("logbook")
        assert [row["id"] for row in ranked] == ["new-index"]


def test_prompt_context_uses_current_catalog_not_stale_catalog_file(m):
    old_cwd = os.getcwd()
    old_evidence = os.environ.get("MOTOKO_EVIDENCE_RETRIEVAL")
    old_vector = os.environ.get("MOTOKO_VECTOR_RETRIEVAL")
    try:
        os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = "0"
        os.environ["MOTOKO_VECTOR_RETRIEVAL"] = "0"
        with isolated_state() as tmp:
            docs = tmp / "docs"
            docs.mkdir()
            source = docs / "logbook.org"
            source.write_text("* TODO Fresh catalog task\n", encoding="utf-8")
            m.add_allowed_dir(str(docs))
            os.chdir(docs)
            stale_catalog = {
                "updated": "2026-05-01T00:00:00+00:00",
                "model": "old-model",
                "endpoint": "old-endpoint",
                "memory_count": 0,
                "pinned_memory_count": 0,
                "conversation_count": 0,
                "indexes": [
                    {
                        "id": "old-index",
                        "name": "docs",
                        "root": str(docs.resolve()),
                        "status": "fresh",
                        "summary": "old catalog index",
                    }
                ],
                "topics": [],
                "dossiers": [],
            }
            m.atomic_write(m.context_catalog_path(), json.dumps(stale_catalog, ensure_ascii=False, indent=2) + "\n")
            index = {
                "id": "new-catalog-index",
                "name": "docs",
                "root": str(docs.resolve()),
                "glob": m.AUTO_INDEX_GLOB,
                "created": "2026-05-24T13:00:00+00:00",
                "corpus_summary": "fresh catalog index",
                "files": [
                    {
                        "path": str(source.resolve()),
                        "source_fingerprint": m.source_fingerprint(source),
                        "chunks": [],
                    }
                ],
            }
            m.atomic_write(m.index_path(index["id"]), json.dumps(index, ensure_ascii=False, indent=2) + "\n")
            conv = m.new_conversation("Catalog freshness")

            package, values = m.build_prompt_context_package(conv, "logbook")

            assert "new-catalog-index" in values["catalog_text"]
            assert "old-index" not in values["catalog_text"]
            catalog_source = next(source for source in package.sources if source.get("kind") == "context-catalog")
            assert catalog_source["updated"] != stale_catalog["updated"]
            saved_catalog = json.loads(m.context_catalog_path().read_text(encoding="utf-8"))
            assert saved_catalog["indexes"][0]["id"] == "old-index"
    finally:
        os.chdir(old_cwd)
        if old_evidence is None:
            os.environ.pop("MOTOKO_EVIDENCE_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = old_evidence
        if old_vector is None:
            os.environ.pop("MOTOKO_VECTOR_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_VECTOR_RETRIEVAL"] = old_vector


def test_prompt_context_resyncs_attached_index_to_newer_completed_index(m):
    old_cwd = os.getcwd()
    old_evidence = os.environ.get("MOTOKO_EVIDENCE_RETRIEVAL")
    old_vector = os.environ.get("MOTOKO_VECTOR_RETRIEVAL")
    try:
        os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = "0"
        os.environ["MOTOKO_VECTOR_RETRIEVAL"] = "0"
        with isolated_state() as tmp:
            docs = tmp / "docs"
            docs.mkdir()
            source = docs / "logbook.org"
            current_content = "* [2026-05-24 Sun 09:00]\n** log\nFresh in-session note.\n"
            source.write_text(current_content, encoding="utf-8")
            m.add_allowed_dir(str(docs))
            os.chdir(docs)
            base = {
                "name": "docs",
                "root": str(docs.resolve()),
                "glob": m.AUTO_INDEX_GLOB,
                "files": [
                    {
                        "path": str(source.resolve()),
                        "source_fingerprint": m.source_fingerprint(source),
                        "summary": "Daily logbook entries.",
                    }
                ],
            }
            old_index = {
                **base,
                "id": "20260524-010000-aaaaaa",
                "created": "2026-05-24T01:00:00+00:00",
                "corpus_summary": "old attached summary",
                "files": [
                    {
                        **base["files"][0],
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "Old chunk.",
                                "content": "* [2026-05-23 Sat 00:52]\n** log\nOld attached note.\n",
                            }
                        ],
                    }
                ],
            }
            new_index = {
                **base,
                "id": "20260524-020000-bbbbbb",
                "created": "2026-05-24T02:00:00+00:00",
                "corpus_summary": "new completed summary",
                "files": [
                    {
                        **base["files"][0],
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "Fresh chunk.",
                                "content": current_content,
                            }
                        ],
                    }
                ],
            }
            m.atomic_write(m.index_path(old_index["id"]), json.dumps(old_index, ensure_ascii=False, indent=2) + "\n")
            m.atomic_write(m.index_path(new_index["id"]), json.dumps(new_index, ensure_ascii=False, indent=2) + "\n")
            conv = m.new_conversation("Open session")
            conv["context_items"] = [m.context_item_from_index(old_index)]
            m.save_conversation(conv)

            package, values = m.build_prompt_context_package(
                conv,
                "summarize the last day present in logbook.org",
            )

            assert conv["context_items"][0]["id"] == new_index["id"]
            assert "Fresh in-session note" in values["context_text"]
            assert "Old attached note" not in values["context_text"]
            assert any(source.get("id") == new_index["id"] for source in package.sources if source.get("kind") == "index")
    finally:
        os.chdir(old_cwd)
        if old_evidence is None:
            os.environ.pop("MOTOKO_EVIDENCE_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = old_evidence
        if old_vector is None:
            os.environ.pop("MOTOKO_VECTOR_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_VECTOR_RETRIEVAL"] = old_vector


def test_prompt_context_recovers_when_attached_index_snapshot_was_cleaned_up(m):
    old_cwd = os.getcwd()
    old_evidence = os.environ.get("MOTOKO_EVIDENCE_RETRIEVAL")
    old_vector = os.environ.get("MOTOKO_VECTOR_RETRIEVAL")
    try:
        os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = "0"
        os.environ["MOTOKO_VECTOR_RETRIEVAL"] = "0"
        with isolated_state() as tmp:
            docs = tmp / "docs"
            docs.mkdir()
            source = docs / "logbook.org"
            fresh_content = "* [2026-05-24 Sun 09:00]\n** log\nRecovered fresh note.\n"
            source.write_text(fresh_content, encoding="utf-8")
            m.add_allowed_dir(str(docs))
            os.chdir(docs)
            base = {
                "name": "docs",
                "root": str(docs.resolve()),
                "glob": "*.org",
                "files": [
                    {
                        "path": str(source.resolve()),
                        "source_fingerprint": m.source_fingerprint(source),
                        "summary": "Daily logbook entries.",
                    }
                ],
            }
            old_index = {
                **base,
                "id": "20260524-010000-cleaned",
                "created": "2026-05-24T01:00:00+00:00",
                "corpus_summary": "cleaned old summary",
                "files": [],
            }
            new_index = {
                **base,
                "id": "20260524-020000-current",
                "created": "2026-05-24T02:00:00+00:00",
                "corpus_summary": "current summary",
                "files": [
                    {
                        **base["files"][0],
                        "chunks": [
                            {
                                "chunk": 1,
                                "summary": "Fresh chunk.",
                                "content": fresh_content,
                            }
                        ],
                    }
                ],
            }
            m.atomic_write(m.index_path(old_index["id"]), json.dumps(old_index, ensure_ascii=False, indent=2) + "\n")
            m.atomic_write(m.index_path(new_index["id"]), json.dumps(new_index, ensure_ascii=False, indent=2) + "\n")
            attached = m.context_item_from_index(old_index)
            m.index_path(old_index["id"]).unlink()
            conv = m.new_conversation("Cleaned attached snapshot")
            conv["context_items"] = [attached]
            m.save_conversation(conv)

            package, values = m.build_prompt_context_package(
                conv,
                "summarize the latest logbook note",
            )

            assert conv["context_items"][0]["id"] == new_index["id"]
            assert conv["context_items"][0]["glob"] == "*.org"
            assert "Recovered fresh note" in values["context_text"]
            assert not any(source.get("context_kind") == "index" for source in package.sources)
    finally:
        os.chdir(old_cwd)
        if old_evidence is None:
            os.environ.pop("MOTOKO_EVIDENCE_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_EVIDENCE_RETRIEVAL"] = old_evidence
        if old_vector is None:
            os.environ.pop("MOTOKO_VECTOR_RETRIEVAL", None)
        else:
            os.environ["MOTOKO_VECTOR_RETRIEVAL"] = old_vector


def test_sync_attached_context_refreshes_topic_and_dossier_metadata(m):
    with isolated_state():
        topic = {
            "id": "topic-refresh",
            "name": "Fresh Topic Name",
            "query": "fresh topic query",
            "summary": "Fresh topic summary",
        }
        dossier = {
            "id": "dossier-refresh",
            "name": "Fresh Dossier Name",
            "query": "fresh dossier query",
            "summary": "Fresh dossier summary",
        }
        m.atomic_write(m.topic_path(topic["id"]), json.dumps(topic, ensure_ascii=False, indent=2) + "\n")
        m.atomic_write(m.dossier_path(dossier["id"]), json.dumps(dossier, ensure_ascii=False, indent=2) + "\n")
        conv = m.new_conversation("Stale context metadata")
        conv["context_items"] = [
            {
                "kind": "topic",
                "id": topic["id"],
                "name": "Old Topic Name",
                "query": "old topic query",
                "summary": "Old topic summary",
            },
            {
                "kind": "dossier",
                "id": dossier["id"],
                "name": "Old Dossier Name",
                "query": "old dossier query",
                "summary": "Old dossier summary",
            },
        ]

        notes = m.sync_attached_indexes_to_latest(conv)

        assert "refreshed attached topic metadata topic-refresh" in notes
        assert "refreshed attached dossier metadata dossier-refresh" in notes
        assert conv["context_items"] == [
            m.context_item_from_topic(topic),
            m.context_item_from_dossier(dossier),
        ]


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

            saved_progress = m.read_index_progress(partial["id"])
            assert saved_progress is not None
            saved_progress["elapsed_seconds"] = 185
            m.atomic_write(
                m.index_progress_path(partial["id"]),
                json.dumps(saved_progress, ensure_ascii=False, indent=2) + "\n",
            )

            m.quiet_model = lambda *args, **kwargs: "summary"
            resume_events = []
            index = m.resume_document_index(partial["id"], progress_callback=resume_events.append)
            assert index["id"] == partial["id"]
            assert len(index["files"]) == 2
            assert any(file_item["path"].endswith("b.org") for file_item in index["files"])
            assert resume_events[0]["elapsed_seconds"] >= 185
            final_progress = m.read_index_progress(index["id"])
            assert final_progress is not None
            assert final_progress["elapsed_seconds"] >= 185
            assert m.index_path(index["id"]).exists()
            assert not m.index_partial_path(index["id"]).exists()
        finally:
            m.quiet_model = old_quiet_model


def test_index_model_residency_defer_is_resumable_not_failed(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "a.org").write_text("* TODO Alpha\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        try:
            m.quiet_model = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                SystemExit("model request deferred: worker route index_chunk waiting 90s for recent chat route qwen36-chat-default")
            )
            try:
                m.build_document_index(str(docs))
            except SystemExit as exc:
                assert "request deferred" in str(exc)
            else:
                raise AssertionError("index build should defer on model residency contention")

            partials = m.list_partial_indexes()
            assert len(partials) == 1
            partial = partials[0]
            assert partial["status"] == "deferred"
            assert partial["completed_files"] == 0
            progress = m.read_index_progress(partial["id"])
            assert progress is not None
            assert progress["status"] == "deferred"
            assert m.format_index_progress_status(progress) == "bg-heavy: index deferred"
            assert m.list_resumable_partial_indexes()[0]["id"] == partial["id"]

            m.quiet_model = lambda *args, **kwargs: "summary"
            index = m.resume_document_index(partial["id"])
            assert index["id"] == partial["id"]
            assert len(index["files"]) == 1
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


def test_summarize_blocks_cancel_event_raises_work_paused(m):
    event = threading.Event()
    event.set()
    try:
        m.summarize_blocks("cancelled", ["alpha"], "summarize", cancel_event=event)
    except m.WorkPaused as exc:
        assert "interrupted" in str(exc)
        assert exc.work_kind == "summarizing"
    else:
        raise AssertionError("summarize_blocks should honor a pre-set cancel event")


def test_index_cancel_event_writes_paused_partial(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "a.org").write_text("* TODO Alpha\nalpha body\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))
        event = threading.Event()
        event.set()
        try:
            m.build_document_index(str(docs), cancel_event=event)
        except m.WorkPaused as exc:
            assert exc.work_kind == "index"
        else:
            raise AssertionError("index build should pause when its cancel event is set")

        partials = m.list_partial_indexes()
        assert len(partials) == 1
        partial = partials[0]
        assert partial["status"] == "paused"
        assert partial["completed_files"] == 0
        progress = m.read_index_progress(partial["id"])
        assert progress is not None
        assert progress["status"] == "paused"


def test_vector_build_cancel_event_stops_before_work(m):
    with isolated_state() as tmp:
        source = tmp / "doc.txt"
        source.write_text("alpha", encoding="utf-8")
        index = {
            "id": "vector-cancel-index",
            "name": "docs",
            "root": str(tmp),
            "glob": m.AUTO_INDEX_GLOB,
            "created": m.now(),
            "files": [
                {
                    "path": str(source),
                    "summary": "alpha",
                    "source_fingerprint": m.source_fingerprint(source),
                    "chunks": [
                        {
                            "chunk": 1,
                            "summary": "alpha",
                            "content": "alpha",
                            "content_sha256": m.sha256_hex(b"alpha"),
                        }
                    ],
                }
            ],
        }
        event = threading.Event()
        event.set()
        try:
            m.build_vector_store_from_index(
                index,
                method=m.LEXICAL_VECTOR_METHOD,
                write=False,
                cancel_event=event,
            )
        except m.WorkPaused as exc:
            assert exc.work_kind == "vector"
        else:
            raise AssertionError("vector build should honor a pre-set cancel event")


def test_tui_stop_requests_report_job_cancel(m):
    with isolated_state():
        ui = object.__new__(m.MotokoTui)
        ui.conv = m.new_conversation("Stop report")
        ui.messages = []
        ui.pending_prompts = m.collections.deque(["queued prompt"])
        ui.generating = False
        ui.report_running = 1
        ui.maintaining = False
        ui.study_running = False
        ui.cwd_indexing = False
        ui.status = "ready"
        ui.scroll = 0
        ui.dirty = False
        ui.jobs = m.JobSupervisor()
        event = threading.Event()
        job = ui.jobs.begin(kind="report", lane="cpu", label="slow report", cancel_event=event)

        assert ui.stop_active_answer()

        snapshot = ui.jobs.snapshots(include_done=False)[0]
        assert snapshot["job_id"] == job.job_id
        assert snapshot["status"] == "stop-requested"
        assert event.is_set()
        assert "stop requested" in ui.status
        assert not ui.pending_prompts


def test_report_query_commands_pass_cancel_events(m):
    with isolated_state():
        conv = m.new_conversation("Report cancellation")
        seen = {}
        old_run_retrieval_debug = m.run_retrieval_debug
        old_query_vector_result = m.query_vector_result
        old_default_vector_index = m.default_vector_index
        old_latest_evidence_store_for_index = m.latest_evidence_store_for_index
        old_query_evidence_store = m.query_evidence_store

        class FakeVectorResult:
            report = {
                "query": "alpha",
                "store_id": "vec",
                "method": m.LEXICAL_VECTOR_METHOD,
                "rows": [],
            }

        def fake_run_retrieval_debug(query, *, conv=None, cancel_event=None, **_kwargs):
            seen["retrieval_debug"] = cancel_event
            return {"schema": m.RETRIEVAL_DEBUG_SCHEMA_VERSION, "query": query, "indexes": []}

        def fake_query_vector_result(query, *, cancel_event=None, **_kwargs):
            seen["vector_query"] = cancel_event
            return FakeVectorResult()

        def fake_default_vector_index(*_args, **_kwargs):
            return {"id": "idx", "name": "docs", "root": "/tmp/docs", "files": []}

        def fake_latest_evidence_store_for_index(_index, *, fresh_only=False):
            return {"id": "ev", "rows": [], "source_index": {"id": "idx"}, "path": ""}

        def fake_query_evidence_store(_store, _query, *, cancel_event=None, **_kwargs):
            seen["evidence_query"] = cancel_event
            return {
                "schema": m.EVIDENCE_QUERY_SCHEMA_VERSION,
                "query": _query,
                "store_id": "ev",
                "source_index": {"id": "idx"},
                "freshness": "fresh",
                "warnings": [],
                "rows": [],
            }

        try:
            m.run_retrieval_debug = fake_run_retrieval_debug
            m.query_vector_result = fake_query_vector_result
            m.default_vector_index = fake_default_vector_index
            m.latest_evidence_store_for_index = fake_latest_evidence_store_for_index
            m.query_evidence_store = fake_query_evidence_store

            event = threading.Event()
            retrieval = m.report_command_request("/retrieval-debug alpha", conv)
            assert retrieval is not None
            m.run_command_callable(retrieval[1], cancel_event=event)
            vector = m.vector_command_request("/vector-query alpha", conv)
            assert vector is not None
            m.run_command_callable(vector[1], cancel_event=event)
            evidence = m.evidence_command_request("/evidence-query alpha", conv)
            assert evidence is not None
            m.run_command_callable(evidence[1], cancel_event=event)

            assert seen == {
                "retrieval_debug": event,
                "vector_query": event,
                "evidence_query": event,
            }
        finally:
            m.run_retrieval_debug = old_run_retrieval_debug
            m.query_vector_result = old_query_vector_result
            m.default_vector_index = old_default_vector_index
            m.latest_evidence_store_for_index = old_latest_evidence_store_for_index
            m.query_evidence_store = old_query_evidence_store


def test_report_query_helpers_stop_when_pre_cancelled(m):
    event = threading.Event()
    event.set()
    store = {
        "id": "store",
        "method": m.LEXICAL_VECTOR_METHOD,
        "dims": 8,
        "rows": [{"id": "row", "vector": [1.0] + [0.0] * 7, "summary": "alpha"}],
    }
    evidence_store = {
        "id": "ev",
        "rows": [{"kind": "org_day", "path": "/tmp/log.org", "text": "alpha"}],
    }
    checks = [
        lambda: m.run_retrieval_debug("alpha", cancel_event=event),
        lambda: m.query_vector_store(store, "alpha", cancel_event=event),
        lambda: m.query_evidence_store(evidence_store, "alpha", cancel_event=event),
    ]
    for check in checks:
        try:
            check()
        except m.WorkPaused as exc:
            assert exc.work_kind in {"retrieval", "vector", "evidence"}
        else:
            raise AssertionError("pre-cancelled report helper should raise WorkPaused")


def test_org_task_signals_drive_retrieval(m):
    old_cwd = os.getcwd()
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
        os.chdir(docs)

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
            os.chdir(old_cwd)
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


def test_index_change_summary_reports_source_lifecycle_decisions(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        source = docs / "a.org"
        source.write_text("* TODO [#A] Alpha\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        try:
            m.quiet_model = lambda *args, **kwargs: "summary"
            index = m.build_document_index(str(docs))
            m.atomic_write(
                m.vector_store_path("vec-source-lifecycle"),
                json.dumps({"id": "vec-source-lifecycle", "source_index": index["id"]}) + "\n",
            )
            m.atomic_write(
                m.evidence_store_path("ev-source-lifecycle"),
                json.dumps({"id": "ev-source-lifecycle", "source_index": index["id"]}) + "\n",
            )
            m.append_jsonl(
                m.action_ledger_path(),
                {
                    "schema": "motoko-action-ledger-v1",
                    "id": "action-ledger-source-lifecycle",
                    "source_index": index["id"],
                    "path": str(source),
                },
            )

            source.write_text("* TODO [#A] Alpha\nUpdated body\n", encoding="utf-8")
            summary = m.index_change_summary(index)
            assert summary["source_lifecycle_counts"]["changed"] == 1
            assert summary["source_lifecycle"][0]["recommended_action"] == "reprocess-from-source"
            plan = summary["artifact_lifecycle_plan"]
            assert plan["recommended_action"] == "rebuild-index-and-refresh-derived-artifacts"
            assert {item["kind"]: item["count"] for item in plan["affected_artifacts"]} == {
                "evidence_store": 1,
                "vector_store": 1,
            }
            assert "changed 1" in m.format_index_health(summary)

            source.unlink()
            summary = m.index_change_summary(index)
            assert summary["source_lifecycle_counts"]["deleted"] == 1
            assert summary["source_lifecycle"][0]["recommended_action"] == "mark-stale-and-clean-derived-artifacts"
            assert "deleted 1" in m.format_index_health(summary)

            source.write_text("* TODO [#A] Alpha\nUpdated body\n", encoding="utf-8")
            (docs / ".motokoignore").write_text("a.org\n", encoding="utf-8")
            summary = m.index_change_summary(index)
            assert summary["source_lifecycle_counts"]["ignored"] == 1
            assert summary["source_lifecycle"][0]["recommended_action"] == "detach-derived-artifacts"
            assert "ignored-indexed 1" in m.format_index_health(summary)

            audit = m.index_storage_audit()
            assert audit["source_lifecycle_plans"]
            audit_plan = audit["source_lifecycle_plans"][0]
            assert audit_plan["derived_artifact_count"] == 2
            assert audit_plan["manual_review_artifact_count"] == 1
            assert audit_plan["apply_status"] == "blocked"
            assert any(item["kind"] == "source-lifecycle-work" for item in audit["blocked_cleanup"])
            audit_text = m.format_index_storage_audit(audit)
            assert "source lifecycle work:" in audit_text
            assert "2 derived artifact(s), 1 manual-review artifact(s)" in audit_text
        finally:
            m.quiet_model = old_quiet_model


def test_source_lifecycle_report_blocks_changed_sources(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        source = docs / "a.org"
        source.write_text("* TODO [#A] Alpha\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        try:
            m.quiet_model = lambda *args, **kwargs: "summary"
            index = m.build_document_index(str(docs))
            m.atomic_write(
                m.vector_store_path("vec-source-lifecycle-blocked"),
                json.dumps({"id": "vec-source-lifecycle-blocked", "source_index": index["id"]}) + "\n",
            )

            source.write_text("* TODO [#A] Alpha\nChanged body\n", encoding="utf-8")
            report = m.source_lifecycle_report_for_index(index)
            plan = report["plan"]
            assert plan["status"] == "needs-rebuild"
            assert plan["apply_status"] == "blocked"
            assert plan["source_counts"]["changed"] == 1
            assert plan["derived_artifact_count"] == 1
            assert "changed sources require source reprocessing" in plan["apply_reason"]
            text = m.format_source_lifecycle_report(report)
            assert "next: rebuild/refresh the corpus first" in text
        finally:
            m.quiet_model = old_quiet_model


def test_source_lifecycle_cleanup_allows_reprocessed_changed_sources(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        source = docs / "a.org"
        source.write_text("* TODO [#A] Alpha\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        try:
            m.quiet_model = lambda *args, **kwargs: "summary"
            old_index = m.build_document_index(str(docs))
            old_index["created"] = "2026-05-01T00:00:00+00:00"
            m.atomic_write(m.index_path(old_index["id"]), json.dumps(old_index, ensure_ascii=False, indent=2) + "\n")
            m.atomic_write(
                m.vector_store_path("vec-changed-source-lifecycle"),
                json.dumps({"id": "vec-changed-source-lifecycle", "source_index": old_index["id"]}) + "\n",
            )
            m.atomic_write(
                m.evidence_store_path("ev-changed-source-lifecycle"),
                json.dumps({"id": "ev-changed-source-lifecycle", "source_index": old_index["id"]}) + "\n",
            )

            source.write_text("* TODO [#A] Alpha\nChanged body\n", encoding="utf-8")
            new_index = m.build_document_index(str(docs))
            new_index["created"] = "2026-05-02T00:00:00+00:00"
            m.atomic_write(m.index_path(new_index["id"]), json.dumps(new_index, ensure_ascii=False, indent=2) + "\n")

            report = m.source_lifecycle_report_for_index(old_index)
            plan = report["plan"]
            assert plan["status"] == "cleanup-ready"
            assert plan["apply_status"] == "ready"
            assert plan["source_counts"]["changed"] == 1
            assert plan["derived_artifact_count"] == 2
            assert "includes reprocessed changed source" in report["replacement"]["reason"]

            applied = m.source_lifecycle_report_for_index(old_index, apply=True, yes=True)
            assert applied["applied"]["status"] == "deleted-superseded-index-snapshot"
            assert not m.index_path(old_index["id"]).exists()
            assert m.index_path(new_index["id"]).exists()
            assert not m.vector_store_path("vec-changed-source-lifecycle").exists()
            assert not m.evidence_store_path("ev-changed-source-lifecycle").exists()
        finally:
            m.quiet_model = old_quiet_model


def test_artifact_lifecycle_family_specs_are_service_owned(m):
    dependency_specs = dependency_json_artifact_specs_core()
    assert {spec["artifact_kind"] for spec in dependency_specs} >= {
        "vector_store",
        "evidence_store",
        "vector_progress",
        "feedback_eval",
        "model_eval",
    }
    assert all("path_key" in spec and "path" not in spec for spec in dependency_specs)

    json_dir_specs = source_lifecycle_json_dir_specs_core()
    assert {spec["cleanup_policy"] for spec in json_dir_specs} == {"delete-derived", "manual-review"}
    assert any(spec["artifact_kind"] == "conversation" for spec in json_dir_specs)
    assert any(spec["artifact_kind"] == "topic_dossier" for spec in json_dir_specs)

    jsonl_specs = source_lifecycle_jsonl_specs_core()
    assert {spec["artifact_kind"] for spec in jsonl_specs} >= {
        "response_feedback",
        "action_ledger",
        "memory_proposal",
        "study_job",
    }
    json_file_specs = source_lifecycle_json_file_specs_core()
    assert {spec["artifact_kind"] for spec in json_file_specs} >= {
        "skill_suggestion",
        "skill_lifecycle",
        "profile_dossier",
    }

    delete_specs = index_snapshot_delete_specs_core()
    assert ("vector_progress_deleted", "vector-progress") in derived_delete_report_labels_core()
    assert {spec["report_key"] for spec in delete_specs} >= {
        "vector_stores_deleted",
        "evidence_stores_deleted",
        "vector_progress_deleted",
    }

    with isolated_state() as tmp:
        resolved = m.resolve_artifact_lifecycle_specs(dependency_specs)
        assert len(resolved) == len(dependency_specs)
        assert all("path" in spec and "path_key" not in spec for spec in resolved)
        assert {spec["artifact_kind"] for spec in resolved} == {
            spec["artifact_kind"] for spec in dependency_specs
        }
        assert not (tmp / "state" / "goal-loops").exists()
        assert not (tmp / "state" / "conversations").exists()


def test_source_lifecycle_report_service_owns_apply_decision(_m):
    assert json_references_index_core({"context_items": [{"kind": "index", "id": "old-index"}]}, "old-index")
    assert json_matching_source_paths_core({"sources": ["/tmp/docs/a.org"]}, {"/tmp/docs/a.org"}) == {
        "/tmp/docs/a.org"
    }
    assert "/tmp/docs/a.org" in source_lifecycle_affected_paths_core(
        [{"path": "/tmp/docs/a.org", "status": "ignored"}]
    )
    assert "/tmp/docs/a.org" in source_lifecycle_path_variants_core("/tmp/docs/a.org")
    grouped_paths = source_lifecycle_paths_by_status_core(
        [
            {"path": "/tmp/docs/a.org", "status": "changed"},
            {"path": "/tmp/docs/b.org", "status": "ignored"},
            {"path": "/tmp/docs/c.org", "status": "fresh"},
        ]
    )
    assert "/tmp/docs/a.org" in grouped_paths["changed"]
    assert "/tmp/docs/b.org" in grouped_paths["ignored"]
    assert "fresh" not in grouped_paths
    cleanup_candidates = superseded_stale_index_candidates_core(
        [
            {"id": "old-a", "root": "/docs", "glob": "*.org", "created": "2026-05-01T00:00:00+00:00"},
            {"id": "new-a", "root": "/docs", "glob": "*.org", "created": "2026-05-02T00:00:00+00:00"},
            {"id": "fresh-b", "root": "/other", "glob": "*.org", "created": "2026-05-01T00:00:00+00:00"},
        ],
        family_key=lambda row: f"{row.get('root')}:{row.get('glob')}",
        index_sort_key=lambda row: (row.get("created", ""), row.get("id", "")),
        staleness=lambda row: ("stale", ["older index"]) if row.get("id") == "old-a" else ("fresh", []),
        bytes_estimate=lambda row: 64 if row.get("id") == "old-a" else 0,
    )
    assert len(cleanup_candidates) == 1
    assert cleanup_candidates[0]["index"]["id"] == "old-a"
    assert cleanup_candidates[0]["latest"]["id"] == "new-a"
    assert cleanup_candidates[0]["warnings"] == ["older index"]
    assert cleanup_candidates[0]["bytes"] == 64
    cleanup_cancel_calls = {"count": 0}
    cleanup_deleted = []

    def cleanup_cancel_before_delete():
        cleanup_cancel_calls["count"] += 1
        if cleanup_cancel_calls["count"] >= 4:
            raise RuntimeError("cancelled cleanup")

    try:
        cleanup_superseded_index_candidates_core(
            cleanup_candidates,
            schema="index-cleanup-v1",
            created="2026-05-31T00:00:00+00:00",
            dry_run=False,
            load_latest=lambda _latest_id: {"id": "new-a"},
            materialize_latest=lambda _latest: {"changed": False, "missing_chunks": 0},
            latest_missing_artifacts=lambda _latest: [],
            delete_snapshot=lambda index: cleanup_deleted.append(index["id"]) or {"index": index["id"]},
            check_cancelled=cleanup_cancel_before_delete,
        )
        raise AssertionError("cleanup cancellation should stop before deletion")
    except RuntimeError as exc:
        assert "cancelled cleanup" in str(exc)
    assert cleanup_deleted == []
    with tempfile.TemporaryDirectory() as source_tmp:
        source_root = pathlib.Path(source_tmp)
        kept = source_root / "kept.org"
        ignored = source_root / "ignored.org"
        changed = source_root / "changed.org"
        deleted = source_root / "deleted.org"
        for path in [kept, ignored, changed]:
            path.write_text("* source\n", encoding="utf-8")
        index_for_scan = {
            "id": "source-scan-index",
            "files": [
                {"path": str(kept), "status": "fresh"},
                {"path": str(ignored), "status": "fresh"},
                {"path": str(changed), "status": "stale"},
                {"path": str(deleted), "status": "fresh"},
            ],
        }
        scan = index_source_lifecycle_scan_core(
            index_for_scan,
            current_paths={str(kept.resolve()), str(changed.resolve())},
            root=source_root,
            ignore_rules=[
                {
                    "pattern": "ignored.org",
                    "directory": False,
                    "negated": False,
                    "line": 1,
                    "raw": "ignored.org",
                }
            ],
            file_status=lambda item: str(item.get("status", "fresh")),
        )
        assert index_file_path_keys_core(index_for_scan) >= {str(kept), str(kept.resolve())}
        assert scan["covered_files"] == 2
        assert str(ignored.resolve()) in scan["missing_paths"]
        statuses = {pathlib.Path(row["path"]).name: row["status"] for row in scan["source_lifecycle"]}
        assert statuses == {
            "ignored.org": "ignored",
            "changed.org": "changed",
            "deleted.org": "deleted",
        }
        assert scan["source_lifecycle_counts"] == {"ignored": 1, "changed": 1, "deleted": 1}
    record = source_artifact_record_core(
        artifact_id="artifact",
        artifact_kind="vector_store",
        state_path="/tmp/state/artifact.json",
        cleanup_policy="delete-derived",
        bytes_estimate=42,
    )
    assert record["bytes_estimate"] == 42
    assert record["cleanup_policy"] == "delete-derived"
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        json_dir = root / "json"
        json_dir.mkdir()
        json_path = json_dir / "vector.json"
        json_path.write_text(
            json.dumps(
                {
                    "id": "vector-store",
                    "source_index": "old-index",
                    "sources": [{"path": "/tmp/docs/a.org"}],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        jsonl_path = root / "feedback.jsonl"
        jsonl_path.write_text(
            json.dumps({"source": "/tmp/docs/a.org"}) + "\n"
            + "{not-json}\n"
            + json.dumps({"source_index": "other-index"}) + "\n",
            encoding="utf-8",
        )
        single_path = root / "profile.json"
        single_path.write_text(
            json.dumps({"source_indexes": ["old-index"], "note": "manual durable state"}) + "\n",
            encoding="utf-8",
        )

        def load_json(path):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None

        assert json_paths_referencing_index_core(json_dir, "old-index", load_json=load_json) == [json_path]
        assert index_artifact_dependency_counts_core(
            "old-index",
            [
                {"path": json_dir, "artifact_kind": "vector_store"},
                {"path": root / "missing", "artifact_kind": "missing_kind"},
            ],
            load_json=load_json,
        ) == {"vector_store": 1, "missing_kind": 0}
        deletion_dir = root / "delete-json"
        deletion_dir.mkdir()
        (deletion_dir / "drop.json").write_text(
            json.dumps({"id": "drop", "source_index": "old-index"}) + "\n",
            encoding="utf-8",
        )
        (deletion_dir / "keep.json").write_text(
            json.dumps({"id": "keep", "source_index": "new-index"}) + "\n",
            encoding="utf-8",
        )
        assert delete_json_artifacts_referencing_index_core(
            deletion_dir,
            "old-index",
            load_json=load_json,
            unlink_path=lambda path: path.unlink(),
        ) == 1
        assert not (deletion_dir / "drop.json").exists()
        assert (deletion_dir / "keep.json").exists()

        records = collect_source_lifecycle_artifact_records_core(
            index_id="old-index",
            source_paths={"/tmp/docs/a.org"},
            load_json=load_json,
            path_size=lambda path: path.stat().st_size,
            json_dirs=[
                {
                    "path": json_dir,
                    "artifact_kind": "vector_store",
                    "cleanup_policy": "delete-derived",
                }
            ],
            jsonl_files=[
                {
                    "path": jsonl_path,
                    "artifact_kind": "response_feedback",
                    "cleanup_policy": "manual-review",
                }
            ],
            json_files=[
                {
                    "path": single_path,
                    "artifact_id": "profile",
                    "artifact_kind": "profile_dossier",
                    "cleanup_policy": "manual-review",
                }
            ],
        )
        assert [item["artifact_kind"] for item in records] == [
            "vector_store",
            "profile_dossier",
            "response_feedback",
        ]
        assert records[0]["artifact_id"] == "vector-store"
        assert records[0]["cleanup_policy"] == "delete-derived"
        assert records[0]["source_index_ids"] == ["old-index"]
        assert records[0]["source_paths"] == ["/tmp/docs/a.org"]
        assert records[1]["artifact_id"] == "profile"
        assert records[1]["source_index_ids"] == ["old-index"]
        assert records[2]["artifact_id"] == "feedback"
        assert records[2]["row_count"] == 1
        assert records[2]["source_paths"] == ["/tmp/docs/a.org"]
        assert all(item["bytes_estimate"] > 0 for item in records)

        index_file = root / "old-index.json"
        progress_file = root / "old-index.progress.json"
        partial_file = root / "old-index.partial.json"
        chunk_dir = root / "old-index.chunks"
        chunk_dir.mkdir()
        (chunk_dir / "1.txt").write_text("chunk text", encoding="utf-8")
        for path in [index_file, progress_file, partial_file]:
            path.write_text(json.dumps({"id": path.stem}) + "\n", encoding="utf-8")
        derived_dir = root / "derived"
        derived_dir.mkdir()
        (derived_dir / "derived.json").write_text(
            json.dumps({"id": "derived", "source_index": "old-index"}) + "\n",
            encoding="utf-8",
        )
        (derived_dir / "unrelated.json").write_text(
            json.dumps({"id": "unrelated", "source_index": "other-index"}) + "\n",
            encoding="utf-8",
        )

        deletion_report = delete_index_snapshot_artifacts_core(
            {"id": "old-index"},
            index_path=index_file,
            progress_path=progress_file,
            partial_path=partial_file,
            chunk_dir=chunk_dir,
            json_artifact_dirs=[{"path": derived_dir, "report_key": "derived_deleted"}],
            load_json=load_json,
            path_size=lambda path: path.stat().st_size,
            tree_size=lambda path: sum(item.stat().st_size for item in path.rglob("*") if item.is_file()),
            unlink_path=lambda path: path.unlink(),
            remove_tree=lambda path: shutil.rmtree(path, ignore_errors=True),
        )
        assert deletion_report["index_deleted"] is True
        assert deletion_report["progress_deleted"] is True
        assert deletion_report["partial_deleted"] is True
        assert deletion_report["chunk_dir_deleted"] is True
        assert deletion_report["derived_deleted"] == 1
        assert deletion_report["bytes"] > 0
        assert not index_file.exists()
        assert not progress_file.exists()
        assert not partial_file.exists()
        assert not chunk_dir.exists()
        assert not (derived_dir / "derived.json").exists()
        assert (derived_dir / "unrelated.json").exists()

    index = {
        "id": "old-index",
        "name": "docs",
        "root": "/tmp/docs",
        "glob": "*.org",
    }
    summary = {
        "status": "stale",
        "warnings": ["source changed"],
        "source_lifecycle": [
            {
                "path": "/tmp/docs/a.org",
                "status": "ignored",
                "recommended_action": "detach-derived-artifacts",
            }
        ],
    }
    artifacts = [
        {
            "artifact_id": "vec",
            "artifact_kind": "vector_store",
            "cleanup_policy": "delete-derived",
            "bytes_estimate": 120,
        },
        {
            "artifact_id": "ledger",
            "artifact_kind": "action_ledger",
            "cleanup_policy": "manual-review",
            "bytes_estimate": 80,
        },
    ]
    deleted = []
    invalidated = []

    def delete_snapshot(item):
        deleted.append(item["id"])
        return {"index": item["id"], "index_deleted": True, "vector_stores_deleted": 1}

    def invalidate_catalog():
        invalidated.append(True)

    dry_run = build_source_lifecycle_report(
        index=index,
        summary=summary,
        artifact_records=artifacts,
        replacement_index={"id": "new-index"},
        replacement_ready=True,
        replacement_reason="replacement is fresh",
        created="2026-05-31T00:00:00+00:00",
        apply=False,
        delete_snapshot=delete_snapshot,
        invalidate_catalog=invalidate_catalog,
    )
    assert dry_run["schema"] == "source-lifecycle-report-v1"
    assert dry_run["dry_run"] is True
    assert dry_run["plan"]["apply_status"] == "ready"
    assert dry_run["plan"]["derived_artifact_count"] == 1
    assert dry_run["plan"]["manual_review_artifact_count"] == 1
    assert deleted == []

    lifecycle_cancel_calls = {"count": 0}
    lifecycle_deleted = []

    def lifecycle_cancel_before_delete():
        lifecycle_cancel_calls["count"] += 1
        if lifecycle_cancel_calls["count"] >= 3:
            raise RuntimeError("cancelled source lifecycle")

    try:
        build_source_lifecycle_report(
            index=index,
            summary=summary,
            artifact_records=artifacts,
            replacement_index={"id": "new-index"},
            replacement_ready=True,
            replacement_reason="replacement is fresh",
            apply=True,
            yes=True,
            delete_snapshot=lambda item: lifecycle_deleted.append(item["id"]) or {"index": item["id"]},
            check_cancelled=lifecycle_cancel_before_delete,
        )
        raise AssertionError("source lifecycle cancellation should stop before deletion")
    except RuntimeError as exc:
        assert "cancelled source lifecycle" in str(exc)
    assert lifecycle_deleted == []

    try:
        build_source_lifecycle_report(
            index=index,
            summary=summary,
            artifact_records=artifacts,
            replacement_index={"id": "new-index"},
            replacement_ready=True,
            replacement_reason="replacement is fresh",
            apply=True,
            yes=False,
            delete_snapshot=delete_snapshot,
        )
        raise AssertionError("source lifecycle apply should require explicit confirmation")
    except SystemExit as exc:
        assert "--yes" in str(exc)

    applied = build_source_lifecycle_report(
        index=index,
        summary=summary,
        artifact_records=artifacts,
        replacement_index={"id": "new-index"},
        replacement_ready=True,
        replacement_reason="replacement is fresh",
        apply=True,
        yes=True,
        delete_snapshot=delete_snapshot,
        invalidate_catalog=invalidate_catalog,
    )
    assert applied["applied"]["status"] == "deleted-superseded-index-snapshot"
    assert applied["applied"]["manual_review_artifacts_preserved"] == 1
    assert deleted == ["old-index"]
    assert invalidated == [True]
    text = format_source_lifecycle_report_core(applied)
    assert "manual review: 1 durable artifact(s)" in text
    assert "action ledgers, or goal-loop records" in text
    assert "deleted: index=True chunks=" in text

    changed_summary = dict(summary)
    changed_summary["source_lifecycle"] = [
        {
            "path": "/tmp/docs/a.org",
            "status": "changed",
            "recommended_action": "reprocess-from-source",
        }
    ]
    blocked = build_source_lifecycle_report(
        index=index,
        summary=changed_summary,
        artifact_records=artifacts,
        replacement_index={"id": "new-index"},
        replacement_ready=False,
        replacement_reason="replacement is fresh",
        apply=True,
        yes=True,
        delete_snapshot=delete_snapshot,
    )
    assert blocked["applied"]["status"] == "blocked"
    assert "changed sources require source reprocessing" in blocked["applied"]["reason"]
    assert deleted == ["old-index"]


def test_source_lifecycle_apply_deletes_only_safe_superseded_derived_artifacts(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        source = docs / "a.org"
        keeper = docs / "b.org"
        source.write_text("* TODO [#A] Alpha\n", encoding="utf-8")
        keeper.write_text("* TODO [#B] Bravo\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        old_quiet_model = m.quiet_model
        try:
            m.quiet_model = lambda *args, **kwargs: "summary"
            old_index = m.build_document_index(str(docs))
            old_index["created"] = "2026-05-01T00:00:00+00:00"
            m.atomic_write(m.index_path(old_index["id"]), json.dumps(old_index, ensure_ascii=False, indent=2) + "\n")

            m.atomic_write(
                m.vector_store_path("vec-source-lifecycle-apply"),
                json.dumps({"id": "vec-source-lifecycle-apply", "source_index": old_index["id"]}) + "\n",
            )
            m.atomic_write(
                m.evidence_store_path("ev-source-lifecycle-apply"),
                json.dumps({"id": "ev-source-lifecycle-apply", "source_index": old_index["id"]}) + "\n",
            )
            m.atomic_write(
                m.topic_path("topic-source-lifecycle-apply"),
                json.dumps({"id": "topic-source-lifecycle-apply", "source_index": old_index["id"]}) + "\n",
            )
            m.atomic_write(
                m.action_eval_path("action-source-lifecycle-apply"),
                json.dumps({"id": "action-source-lifecycle-apply", "source_index": old_index["id"]}) + "\n",
            )
            m.atomic_write(
                m.model_eval_path("model-source-lifecycle-apply"),
                json.dumps({"id": "model-source-lifecycle-apply", "source_index": old_index["id"]}) + "\n",
            )
            m.atomic_write(
                m.goal_run_path("goal-source-lifecycle-apply"),
                json.dumps(
                    {
                        "id": "goal-source-lifecycle-apply",
                        "source_index": old_index["id"],
                        "sources": [{"path": str(source)}],
                    },
                    ensure_ascii=False,
                )
                + "\n",
            )
            m.append_jsonl(
                m.action_ledger_path(),
                {
                    "schema": "motoko-action-ledger-v1",
                    "id": "action-ledger-source-lifecycle-apply",
                    "source_index": old_index["id"],
                    "path": str(source),
                },
            )
            m.append_jsonl(
                m.response_feedback_path(),
                {
                    "schema": m.RESPONSE_FEEDBACK_SCHEMA_VERSION,
                    "id": "feedback-source-lifecycle-apply",
                    "sources": [{"path": str(source), "index": old_index["id"]}],
                },
            )

            (docs / ".motokoignore").write_text("a.org\n", encoding="utf-8")
            new_index = m.build_document_index(str(docs))
            new_index["created"] = "2026-05-02T00:00:00+00:00"
            m.atomic_write(m.index_path(new_index["id"]), json.dumps(new_index, ensure_ascii=False, indent=2) + "\n")

            report = m.source_lifecycle_report_for_index(old_index)
            plan = report["plan"]
            assert plan["status"] == "cleanup-ready"
            assert plan["apply_status"] == "ready"
            assert plan["source_counts"]["ignored"] == 1
            affected = {(item["kind"], item["policy"]): item["count"] for item in plan["affected_artifacts"]}
            assert affected[("action_eval", "delete-derived")] == 1
            assert affected[("model_eval", "delete-derived")] == 1
            assert affected[("action_ledger", "manual-review")] == 1
            assert affected[("goal_run", "manual-review")] == 1
            assert plan["derived_artifact_count"] == 5
            assert plan["manual_review_artifact_count"] == 3
            assert m.response_feedback_path().exists()

            applied = m.source_lifecycle_report_for_index(old_index, apply=True, yes=True)
            assert applied["applied"]["status"] == "deleted-superseded-index-snapshot"
            assert not m.index_path(old_index["id"]).exists()
            assert m.index_path(new_index["id"]).exists()
            assert not m.vector_store_path("vec-source-lifecycle-apply").exists()
            assert not m.evidence_store_path("ev-source-lifecycle-apply").exists()
            assert not m.topic_path("topic-source-lifecycle-apply").exists()
            assert not m.action_eval_path("action-source-lifecycle-apply").exists()
            assert not m.model_eval_path("model-source-lifecycle-apply").exists()
            assert m.goal_run_path("goal-source-lifecycle-apply").exists()
            assert m.response_feedback_path().exists()
            assert m.read_jsonl(m.response_feedback_path())[0]["id"] == "feedback-source-lifecycle-apply"
            assert m.read_jsonl(m.action_ledger_path())[0]["id"] == "action-ledger-source-lifecycle-apply"
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


def test_retrieval_service_renders_attached_context_without_generic_callback(m):
    service = m.RetrievalService(
        load_index=lambda index_id: {"id": index_id},
        retrieve_index_query=lambda index, query: (f"index {index['id']} query {query}", [{"kind": "index", "id": index["id"]}]),
        render_index_overview=lambda index: ("overview", [{"kind": "index", "id": index["id"]}]),
        load_topic=lambda topic_id: {"id": topic_id},
        retrieve_topic=lambda topic, query: ("topic", [{"kind": "topic", "id": topic["id"]}]),
        load_dossier=lambda dossier_id: {"id": dossier_id},
        retrieve_dossier=lambda dossier, query: ("dossier", [{"kind": "dossier", "id": dossier["id"]}]),
        load_vector_store=lambda store_id: {"id": store_id},
        latest_vector_store=lambda: {"id": "latest-vector"},
        query_vector_store=lambda store, query, limit=None, rerank=False: {
            "store_id": store["id"],
            "query": query,
            "rerank": rerank,
            "rows": [{"path": "/tmp/a.txt"}],
        },
    )

    result = service.render_attached_context(
        [
            {"kind": "index", "id": "idx"},
            {"kind": "repo", "command": "status", "root": "/repo", "content": "clean", "bytes": 5},
            {"kind": "file", "path": "/tmp/a.txt", "content": "alpha", "bytes": 5},
        ],
        "alpha",
    )

    assert "index idx query alpha" in result.text
    assert "repo:status /repo" in result.text
    assert "file:/tmp/a.txt" in result.text
    assert [source["kind"] for source in result.sources] == ["index", "repo", "file"]
    assert result.diagnostics["source_count"] == 3
    vector = service.query_vector("alpha", store_id="vec-1", limit=4, rerank=True)
    assert vector.report["retrieval_service_schema"] == "retrieval-service-v1"
    assert vector.report["store_id"] == "vec-1"
    assert vector.diagnostics["kind"] == "vector-query"
    assert vector.diagnostics["row_count"] == 1


def test_core_recent_conversation_renderer_is_injectable(m):
    text, sources = m.render_recent_conversations_with_sources_core(
        [
            {
                "id": "conv-1",
                "title": "Planning",
                "updated": "2026-05-23T00:00:00+00:00",
                "branch": "master",
                "summary": "Long-term Motoko planning.",
                "messages": [
                    {"role": "user", "content": "What next?"},
                    {"role": "assistant", "content": "Use grounded retrieval."},
                ],
                "_recall_score": 12,
                "_matched_terms": 3,
                "_selection_reasons": ["recent", "relevant"],
            }
        ],
        relative_time_func=lambda value: "today" if value else "-",
        max_chars=500,
        snippet_chars=80,
        recent_message_limit=2,
    )

    assert "conversation:conv-1" in text
    assert "updated=today" in text
    assert "Javier: What next?" in text
    assert "Motoko: Use grounded retrieval." in text
    assert sources == [
        {
            "kind": "recent-conversation",
            "conversation_id": "conv-1",
            "title": "Planning",
            "updated": "2026-05-23T00:00:00+00:00",
            "branch": "master",
            "score": 12,
            "matched_terms": 3,
            "selection": ["recent", "relevant"],
        }
    ]


def test_core_recent_conversation_ranking_is_injectable(m):
    rows = [
        {"id": "new", "title": "Newest", "body": "recent but unrelated"},
        {"id": "match", "title": "Relevant", "body": "grounded retrieval and memory"},
        {"id": "old", "title": "Old", "body": "archive"},
    ]
    query_counts = m.token_counts("retrieval")

    ranked = m.rank_recent_conversation_rows(
        rows,
        query_counts=query_counts,
        recall_text_func=lambda row: f"{row.get('title', '')} {row.get('body', '')}",
        score_text_func=m.score_text,
        recency_lane=1,
        relevance_lane=1,
        limit=3,
    )

    assert [row["id"] for row in ranked[:2]] == ["new", "match"]
    assert ranked[0]["_selection_reasons"] == ["recent"]
    assert ranked[1]["_selection_reasons"] == ["relevant"]


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

        plain = m.shared_command_request("feedback up excellent answer", conv)
        assert plain is not None
        plain_label, plain_run = plain
        assert plain_label == "/feedback"
        assert "feedback saved" in plain_run()
        rows = m.read_jsonl(m.response_feedback_path())
        assert rows[1]["rating"] == "up"
        assert rows[1]["note"] == "excellent answer"


def test_tui_feedback_plain_command_is_not_queued_during_active_work(m):
    with isolated_state():
        conv = m.new_conversation("Feedback plain command")
        conv["messages"] = [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ]
        ui = object.__new__(m.MotokoTui)
        ui.conv = conv
        ui.cwd_index_offer = None
        ui.cwd_indexing = True
        ui.study_running = True
        ui.study_status = "bg-heavy: vectorizing(model)"
        ui.generating = False
        ui.pending_prompts = m.collections.deque()
        handled = []
        ui.handle_command = handled.append

        m.MotokoTui.submit_text(ui, "feedback up excellent answer")

        assert handled == ["feedback up excellent answer"]
        assert not ui.pending_prompts
        assert not conv.get("queued_prompts")


def test_help_uses_shared_report_command_request(m):
    with isolated_state():
        conv = m.new_conversation("Help")
        request = m.shared_command_request("/help", conv)
        assert request is not None
        label, run = request
        assert label == "/help"
        assert "/status" in run()
        tips_request = m.shared_command_request("/tips", conv)
        assert tips_request is not None
        tips_label, tips_run = tips_request
        assert tips_label == "/tips"
        assert "/feedback up|down|ok" in tips_run()


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


def test_live_command_request_metadata(m):
    with isolated_state():
        conv = m.new_conversation("Command boundary")
        conv["id"] = "command-boundary"
        report = m.shared_command_request("/status", conv)
        assert report is not None
        assert report.kind == m.COMMAND_KIND_REPORT
        assert not report.blocks
        label, run = report
        assert label == "/status"
        assert "runtime schema:" in run()

        old_route_state = m.safe_model_route_state
        try:
            m.safe_model_route_state = lambda route: f"route={route} socket=inactive backend=inactive"
            diagnose = m.shared_command_request("/diagnose", conv)
            assert diagnose is not None
            diagnose_label, diagnose_run = diagnose
            assert diagnose_label == "/diagnose"
            assert "safe diagnose:" in diagnose_run()
        finally:
            m.safe_model_route_state = old_route_state

        mutation = m.shared_command_request("/rename Better title", conv)
        assert mutation is not None
        assert mutation.kind == m.COMMAND_KIND_MUTATION
        assert mutation.mutates_state

        blocking = m.blocking_command_request("/study current context", conv)
        assert blocking is not None
        assert blocking.kind == m.COMMAND_KIND_FOREGROUND_JOB
        assert blocking.blocks


def test_procedural_skills_are_realm_local_and_retrievable(m):
    with isolated_state():
        text = m.learn_skill_text(
            "racefocus-response-style",
            description="RaceFocus planning responses",
            body="When discussing RaceFocus, preserve the distinction between VR, 2D HUD, and OBS renderer contexts.",
        )
        assert "racefocus-response-style" in text
        assert "racefocus-response-style" in m.format_skills()
        assert "VR, 2D HUD, and OBS" in m.format_skill("racefocus-response-style")

        rendered, sources = m.render_skills_with_sources("RaceFocus OBS renderer plan")
        assert "Skill: racefocus-response-style" in rendered
        assert sources and sources[0]["kind"] == "skill"
        assert sources[0]["name"] == "racefocus-response-style"


def test_builtin_source_scoped_temporal_skill_is_available(m):
    with isolated_state():
        listed = m.format_skills()
        assert "org-temporal-retrieval" in listed
        assert "org-structural-query" in listed
        assert "motoko-codebase-maintainer" in listed
        assert "motoko-retrieval-maintainer" in listed
        assert "motoko-refactor-craft" in listed
        assert "motoko-agentic-boundary-review" in listed
        assert "Source-scoped retrieval" in listed
        assert "Deterministic retrieval for Org tags" in listed
        assert "builtin:org_temporal_latest_entries" in listed
        assert "builtin:org_structural_query" in listed
        shown = m.format_skill("org-temporal-retrieval")
        assert "schema: motoko-skill-v3" in shown
        assert "kind: retrieval" in shown
        assert "handler: builtin:org_temporal_latest_entries" in shown
        structural = m.format_skill("org-structural-query")
        assert "schema: motoko-skill-v3" in structural
        assert "kind: retrieval" in structural
        assert "handler: builtin:org_structural_query" in structural
        retrieval = m.format_skill("motoko-retrieval-maintainer")
        assert "kind: self-improvement" in retrieval
        assert "handler: prompt_only" in retrieval
        assert "Classify retrieval failures precisely" in retrieval or "Name the failure precisely" in retrieval

        rendered, sources = m.render_skills_with_sources("summarize last three days present in logbook.org")
        assert "Skill: org-temporal-retrieval" in rendered
        assert "newest distinct dates actually present" in rendered
        assert sources and sources[0]["kind"] == "skill"
        assert sources[0]["path"] == "builtin:org-temporal-retrieval"
        assert sources[0]["handler"] == "builtin:org_temporal_latest_entries"

        rendered, sources = m.render_skills_with_sources("show all entries tagged racefocus")
        assert "Skill: org-structural-query" in rendered
        assert "inherited tags" in rendered
        assert sources and sources[0]["kind"] == "skill"
        assert sources[0]["path"] == "builtin:org-structural-query"
        assert sources[0]["handler"] == "builtin:org_structural_query"

        rendered, sources = m.render_skills_with_sources("diagnose retrieval failure from stale sources")
        assert "Skill: motoko-retrieval-maintainer" in rendered
        assert sources and any(row.get("path") == "builtin:motoko-retrieval-maintainer" for row in sources)


def test_procedural_skills_are_included_in_prompt_and_sources(m):
    with isolated_state():
        conv = m.new_conversation("Skill prompt")
        conv["id"] = "skill-prompt"
        prompt, sources = m.build_system_prompt_and_sources(conv, "latest days in logbook.org")
        assert "Relevant procedural skills:" in prompt
        assert "source-scoped temporal retrieval task" in prompt
        assert any(source.get("kind") == "skill" for source in sources)


def test_procedural_skill_commands(m):
    with isolated_state():
        conv = m.new_conversation("Skill commands")
        conv["id"] = "skill-commands"
        mutation = m.shared_command_request(
            '/skill learn org-temporal --description "Named Org temporal retrieval" --body "Scope to the named file."',
            conv,
        )
        assert mutation is not None
        assert mutation.kind == m.COMMAND_KIND_MUTATION
        assert mutation.mutates_state
        _label, run = mutation
        assert "skill saved" in run()

        report = m.shared_command_request("/skills", conv)
        assert report is not None
        assert report.kind == m.COMMAND_KIND_REPORT
        _label, run = report
        assert "org-temporal" in run()

        shown = m.shared_command_request("/skill show org-temporal", conv)
        assert shown is not None
        _label, run = shown
        assert "Scope to the named file." in run()

        deleted = m.shared_command_request("/skill delete org-temporal", conv)
        assert deleted is not None
        _label, run = deleted
        assert "skill deleted" in run()
        assert "org-temporal-retrieval" in m.format_skills()


def test_skill_lifecycle_records_usage_and_archive_restore(m):
    with isolated_state():
        m.learn_skill_text(
            "racefocus-response-style",
            description="RaceFocus planning responses",
            body="When discussing RaceFocus, preserve VR, 2D HUD, and OBS renderer boundaries.",
        )
        rendered, sources = m.render_skills_with_sources("RaceFocus OBS renderer plan")
        assert "racefocus-response-style" in rendered
        assert sources and sources[0]["kind"] == "skill"
        listed = m.format_skills()
        assert "selected 1x" in listed

        assert "skill pinned: racefocus-response-style" in m.pin_skill_text("racefocus-response-style", True)
        assert "pinned" in m.format_skills()
        assert "cannot archive pinned skill" in m.archive_skill_text("racefocus-response-style", yes=True)
        assert "skill unpinned: racefocus-response-style" in m.pin_skill_text("racefocus-response-style", False)
        assert "refusing to archive skill without --yes" in m.archive_skill_text("racefocus-response-style")
        assert "skill archived: racefocus-response-style" in m.archive_skill_text("racefocus-response-style", yes=True)

        rendered, sources = m.render_skills_with_sources("RaceFocus OBS renderer plan")
        assert "racefocus-response-style" not in rendered
        assert not sources
        report = m.skill_curator_report_text()
        assert "skill curator report: report-only" in report
        assert "archived skills:" in report
        assert "motoko skill restore racefocus-response-style" in report

        assert "skill restored: racefocus-response-style" in m.restore_skill_text("racefocus-response-style")
        rendered, sources = m.render_skills_with_sources("RaceFocus OBS renderer plan")
        assert "racefocus-response-style" in rendered
        assert sources and sources[0]["name"] == "racefocus-response-style"


def test_skill_lifecycle_commands_are_realm_local(m):
    with isolated_state():
        conv = m.new_conversation("Skill lifecycle commands")
        conv["id"] = "skill-lifecycle-commands"
        m.learn_skill_text(
            "retrieval-debugging",
            description="Retrieval debugging checklist",
            body="Use retrieval-debug and sources before changing ranking.",
        )
        report = m.shared_command_request("/skill curator", conv)
        assert report is not None
        assert report.kind == m.COMMAND_KIND_REPORT
        _label, run = report
        assert "report-only" in run()

        pinned = m.shared_command_request("/skill pin retrieval-debugging", conv)
        assert pinned is not None
        assert pinned.kind == m.COMMAND_KIND_MUTATION
        _label, run = pinned
        assert "skill pinned" in run()

        archived = m.shared_command_request("/skill archive retrieval-debugging --yes", conv)
        assert archived is not None
        _label, run = archived
        assert "cannot archive pinned skill" in run()

        unpinned = m.shared_command_request("/skill unpin retrieval-debugging", conv)
        assert unpinned is not None
        _label, run = unpinned
        assert "skill unpinned" in run()

        archived = m.shared_command_request("/skill archive retrieval-debugging --yes", conv)
        assert archived is not None
        _label, run = archived
        assert "skill archived" in run()

        restored = m.shared_command_request("/skill restore retrieval-debugging", conv)
        assert restored is not None
        _label, run = restored
        assert "skill restored" in run()


def test_skill_curator_creates_feedback_patch_suggestion(m):
    with isolated_state():
        m.learn_skill_text(
            "retrieval-debugging",
            description="Retrieval debugging checklist",
            body="Inspect sources first.",
        )
        conv = m.new_conversation("Curator feedback")
        conv["id"] = "curator-feedback"
        conv["messages"] = [
            {"role": "user", "content": "retrieval debugging failed on a stale source"},
            {"role": "assistant", "content": "I should have inspected ranking after sources."},
        ]
        m.record_response_feedback(conv, "down", "retrieval debugging needs ranking and stale-source checks")

        report = m.skill_curator_report_text()
        assert "curator suggestion candidates: 1" in report
        assert "queue them with: motoko skill curator --suggest" in report
        assert "retrieval debugging needs ranking" not in report
        assert "raw note hidden" in report

        command = m.shared_command_request("/skill curator suggest", conv)
        assert command is not None
        assert command.kind == m.COMMAND_KIND_MUTATION
        _label, run = command
        queued = run()
        assert "skill curator: 1 pending suggestion" in queued
        suggestions = m.list_skill_suggestions(status="pending")
        assert len(suggestions) == 1
        assert suggestions[0]["action"] == "patch"
        assert suggestions[0]["target_skill"] == "retrieval-debugging"
        assert "Feedback-derived review notes" in suggestions[0]["new_string"]
        assert "retrieval debugging needs ranking" not in suggestions[0]["new_string"]

        duplicate = m.curator_skill_suggestions_text()
        assert "no new suggestions" in duplicate
        accepted = m.accept_skill_suggestion_text(suggestions[0]["id"])
        assert "skill accepted: retrieval-debugging" in accepted
        assert "Feedback-derived review notes" in m.format_skill("retrieval-debugging")


def test_skill_curator_creates_loaded_skill_patch_suggestion(m):
    with isolated_state():
        m.learn_skill_text(
            "racefocus-response-style",
            description="RaceFocus planning responses",
            body="Preserve the VR, 2D HUD, and OBS renderer split.",
        )
        for _idx in range(3):
            rendered, sources = m.render_skills_with_sources("RaceFocus OBS renderer planning")
            assert "racefocus-response-style" in rendered
            assert sources

        candidates = m.curator_skill_suggestion_candidates()
        assert candidates
        assert candidates[0]["action"] == "patch"
        assert candidates[0]["target_skill"] == "racefocus-response-style"
        assert "Curator usage review notes" in candidates[0]["new_string"]


def test_skill_curator_creates_support_file_plan_for_large_skill(m):
    with isolated_state():
        m.learn_skill_text(
            "large-retrieval-workflow",
            description="Large retrieval workflow",
            body="Keep retrieval grounded.\n" * 180,
        )

        candidates = m.curator_skill_suggestion_candidates()
        support = next(row for row in candidates if row.get("file_path") == "references/support-file-plan.md")
        assert support["action"] == "write_file"
        assert support["target_skill"] == "large-retrieval-workflow"
        assert "Support-file plan" in support["file_content"]
        assert "body chars" in support["file_content"]


def test_skill_curator_creates_consolidation_support_suggestion(m):
    with isolated_state():
        m.learn_skill(
            "racefocus-hud-review",
            description="RaceFocus HUD renderer review",
            body="Keep RaceFocus renderer answers grounded.",
            triggers=["racefocus", "renderer", "hud"],
        )
        m.learn_skill(
            "racefocus-renderer-planning",
            description="RaceFocus renderer planning",
            body="Preserve RaceFocus renderer planning constraints.",
            triggers=["racefocus", "renderer", "planning"],
        )

        candidates = m.curator_skill_suggestion_candidates()
        consolidation = next(row for row in candidates if row.get("file_path") == "references/consolidation-review.md")
        assert consolidation["action"] == "write_file"
        assert consolidation["target_skill"] == "racefocus-hud-review"
        assert "racefocus-renderer-planning" in consolidation["file_content"]
        assert "overlap terms" in consolidation["file_content"]


def test_skill_curator_creates_stale_unused_archive_review_suggestion(m):
    with isolated_state():
        m.learn_skill_text(
            "dormant-retrieval-trick",
            description="Dormant retrieval trick",
            body="Use a one-off retrieval trick only if it still proves useful.",
        )
        row = m.core_load_skill(m.skills_dir(), "dormant-retrieval-trick")
        path = pathlib.Path(row["path"])
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            row["created_at"],
            "2026-01-01T00:00:00+00:00",
            1,
        ).replace(
            row["updated_at"],
            "2026-01-01T00:00:00+00:00",
            1,
        )
        path.write_text(text, encoding="utf-8")

        report = m.skill_curator_report_text()
        assert "stale unused skills that may deserve archive review:" in report
        assert "dormant-retrieval-trick" in report

        candidates = m.curator_skill_suggestion_candidates()
        archive_review = next(row for row in candidates if row.get("file_path") == "references/archive-review.md")
        assert archive_review["action"] == "write_file"
        assert archive_review["target_skill"] == "dormant-retrieval-trick"
        assert "does not archive anything by itself" in archive_review["file_content"]
        assert "motoko skill archive dormant-retrieval-trick --yes" in archive_review["file_content"]
        assert "curator-stale-unused-skill" in archive_review["signals"]

        queued = m.curator_skill_suggestions_text()
        assert "skill curator: 1 pending suggestion" in queued
        suggestions = m.list_skill_suggestions(status="pending")
        assert len(suggestions) == 1
        accepted = m.accept_skill_suggestion_text(suggestions[0]["id"])
        assert "skill accepted: dormant-retrieval-trick" in accepted
        support = m.format_skill_support_file("dormant-retrieval-trick", "references/archive-review.md")
        assert "Archive review for dormant-retrieval-trick" in support


def write_demo_tool(m, skill_name="tool-backed-skill"):
    m.learn_skill_text(
        skill_name,
        description="Skill with an inert script-backed tool",
        body="Use the tool only through Motoko action validation.",
    )
    scripts = m.skills_dir() / skill_name / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "demo.py").write_text(
        "import json, sys\n"
        "data = json.loads(sys.stdin.read() or '{}')\n"
        "args = data.get('arguments') or {}\n"
        "print(json.dumps({'ok': True, 'path': args.get('path', ''), 'realm': data.get('realm', '')}))\n",
        encoding="utf-8",
    )
    (scripts / "demo.tool.json").write_text(
        json.dumps(
            {
                "schema": "motoko-tool-v1",
                "name": "demo",
                "description": "Read an allowed path and write Motoko state.",
                "script": "demo.py",
                "interpreter": "python3",
                "wrapper": "motoko-tool-python-stdlib",
                "allowed_effects": ["read_allowed_files", "write_motoko_state"],
                "argument_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "timeout_seconds": 30,
                "max_stdout_bytes": 65536,
                "max_stderr_bytes": 16384,
                "network": False,
                "writes_project_files": False,
                "requires_confirmation": False,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def write_project_proposal_tool(m, skill_name="project-proposer", *, include_effect=True):
    m.learn_skill_text(
        skill_name,
        description="Skill with a project-change proposal tool",
        body="Use the tool to propose typed project_file_write actions; Motoko applies them.",
    )
    scripts = m.skills_dir() / skill_name / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "propose.py").write_text(
        "import json, sys\n"
        "data = json.loads(sys.stdin.read() or '{}')\n"
        "args = data.get('arguments') or {}\n"
        "action = {\n"
        "  'schema': 'motoko-action-v1',\n"
        "  'kind': 'project_file_write',\n"
        "  'path': args.get('target', ''),\n"
        "  'mode': 'create',\n"
        "  'content': args.get('content', ''),\n"
        "  'reason': 'tool proposed a bounded project write'\n"
        "}\n"
        "print(json.dumps({'ok': True, 'proposed_actions': [action]}))\n",
        encoding="utf-8",
    )
    effects = ["write_motoko_state"]
    if include_effect:
        effects.append("propose_project_changes")
    (scripts / "propose.tool.json").write_text(
        json.dumps(
            {
                "schema": "motoko-tool-v1",
                "name": "propose",
                "description": "Prepare a project_file_write proposal without writing project files.",
                "script": "propose.py",
                "interpreter": "python3",
                "wrapper": "motoko-tool-python-stdlib",
                "allowed_effects": effects,
                "argument_schema": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["target", "content"],
                    "additionalProperties": False,
                },
                "input_schema": {"type": "object"},
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean"},
                        "proposed_actions": {"type": "array"},
                    },
                    "required": ["ok", "proposed_actions"],
                    "additionalProperties": False,
                },
                "timeout_seconds": 30,
                "max_stdout_bytes": 65536,
                "max_stderr_bytes": 16384,
                "network": False,
                "writes_project_files": False,
                "requires_confirmation": False,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def test_skill_tool_metadata_validation_and_approval(m):
    with isolated_state():
        write_demo_tool(m)
        tools = m.format_skill_tools("tool-backed-skill")
        assert "demo: not approved" in tools
        assert "read_allowed_files, write_motoko_state" in tools
        assert "script sha256:" in tools

        refused = m.approve_skill_tool_text("tool-backed-skill", "demo", yes=False)
        assert "refusing to approve without --yes" in refused

        approved = m.approve_skill_tool_text("tool-backed-skill", "demo", yes=True)
        assert "tool approved: demo" in approved
        assert "requires confirmation: no" in approved
        tools = m.format_skill_tools("tool-backed-skill")
        assert "demo: approved" in tools


def test_action_preview_requires_approval_then_validates(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        m.add_allowed_dir(str(docs))
        write_demo_tool(m)
        action_path = tmp / "action.json"
        action_path.write_text(
            json.dumps(
                {
                    "schema": "motoko-action-v1",
                    "kind": "skill_tool_run",
                    "skill": "tool-backed-skill",
                    "tool": "demo",
                    "arguments": {"path": str(docs / "notes.org")},
                    "reason": "Need a bounded deterministic helper.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        preview = m.validate_action_text(str(action_path), preview=True)
        assert "status: needs_approval" in preview
        assert "approval: missing" in preview
        assert m.action_ledger_path().exists()

        m.approve_skill_tool_text("tool-backed-skill", "demo", yes=True)
        preview = m.validate_action_text(str(action_path), preview=True)
        assert "status: valid" in preview
        assert "approval: persistent" in preview
        assert "tool: demo" in preview


def test_action_preview_rejects_shell_and_bad_tool_metadata(m):
    with isolated_state() as tmp:
        bad_action = tmp / "shell.json"
        bad_action.write_text(
            json.dumps(
                {
                    "schema": "motoko-action-v1",
                    "kind": "shell",
                    "command": "rm -rf /",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        preview = m.validate_action_text(str(bad_action), preview=True)
        assert "status: rejected" in preview
        assert "unsupported action kind" in preview

        m.learn_skill_text(
            "bad-tool-skill",
            description="Bad tool metadata",
            body="This skill has an invalid script declaration.",
        )
        scripts = m.skills_dir() / "bad-tool-skill" / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        (scripts / "bad.tool.json").write_text(
            json.dumps(
                {
                    "schema": "motoko-tool-v1",
                    "name": "bad",
                    "description": "Bad path",
                    "script": "../bad.py",
                    "interpreter": "python3",
                    "wrapper": "motoko-tool-python-stdlib",
                    "allowed_effects": ["read_allowed_files"],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        tools = m.format_skill_tools("bad-tool-skill")
        assert "bad: invalid" in tools
        assert "traversal" in tools


def test_action_run_executes_approved_tool_and_records_private_result(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        m.add_allowed_dir(str(docs))
        note_path = docs / "notes.org"
        write_demo_tool(m)
        action_path = tmp / "run-action.json"
        action_path.write_text(
            json.dumps(
                {
                    "schema": "motoko-action-v1",
                    "kind": "skill_tool_run",
                    "skill": "tool-backed-skill",
                    "tool": "demo",
                    "arguments": {"path": str(note_path)},
                    "reason": "Need a bounded deterministic helper.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        blocked = m.run_action_text(str(action_path))
        assert "status: blocked" in blocked
        assert "approval: missing" in blocked
        assert "not run" in blocked

        m.approve_skill_tool_text("tool-backed-skill", "demo", yes=True)
        output = m.run_action_text(str(action_path))
        assert "action run:" in output
        assert "status: completed" in output
        assert "output json valid: yes" in output
        assert "private result:" in output

        result_files = list((m.state_root() / "tool-runs").glob("*/result.json"))
        assert len(result_files) == 1
        result = json.loads(result_files[0].read_text(encoding="utf-8"))
        assert result["status"] == "completed"
        assert result["output_json"]["path"] == str(note_path)
        rows = m.read_jsonl(m.action_ledger_path())
        assert any(row.get("status") == "running" for row in rows)
        assert any(row.get("status") == "completed" and row.get("tool_run_id") for row in rows)
        ledger = m.format_action_ledger(limit=5)
        assert "action ledger:" in ledger
        assert "completed" in ledger
        run_id = result_files[0].parent.name
        public_result = m.format_tool_result(run_id)
        assert "private content: hidden" in public_result
        private_result = m.format_tool_result(run_id, private=True)
        assert f'"path": "{note_path}"' in private_result


def test_action_run_interruption_records_durable_status(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        m.add_allowed_dir(str(docs))
        note_path = docs / "notes.org"
        write_demo_tool(m)
        m.approve_skill_tool_text("tool-backed-skill", "demo", yes=True)
        action_path = tmp / "interrupt-action.json"
        action_path.write_text(
            json.dumps(
                {
                    "schema": "motoko-action-v1",
                    "kind": "skill_tool_run",
                    "skill": "tool-backed-skill",
                    "tool": "demo",
                    "arguments": {"path": str(note_path)},
                    "reason": "Check interruption status.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        cancel_event = threading.Event()
        cancel_event.set()
        output = m.run_action_text(str(action_path), cancel_event=cancel_event)
        assert "status: interrupted" in output
        rows = m.read_jsonl(m.action_ledger_path())
        assert any(row.get("status") == "running" for row in rows)
        assert any(row.get("status") == "interrupted" for row in rows)
        results = list((m.state_root() / "tool-runs").glob("*/result.json"))
        assert len(results) == 1
        result = json.loads(results[0].read_text(encoding="utf-8"))
        assert result["status"] == "interrupted"

        invalid = {
            "schema": "motoko-action-v1",
            "kind": "shell",
            "command": "echo should-not-run",
        }
        validation, result = m.execute_action_record(invalid, yes=True, cancel_event=cancel_event)
        assert validation["status"] == "rejected"
        assert result is None
        assert m.read_jsonl(m.action_ledger_path())[-1]["status"] == "rejected"


def test_skill_tool_relative_path_arguments_require_allowed_cwd(m):
    old_cwd = os.getcwd()
    with isolated_state() as tmp:
        docs = tmp / "docs"
        other = tmp / "other"
        docs.mkdir()
        other.mkdir()
        m.add_allowed_dir(str(docs))
        write_demo_tool(m)
        m.approve_skill_tool_text("tool-backed-skill", "demo", yes=True)

        action_path = tmp / "relative-action.json"
        action_path.write_text(
            json.dumps(
                {
                    "schema": "motoko-action-v1",
                    "kind": "skill_tool_run",
                    "skill": "tool-backed-skill",
                    "tool": "demo",
                    "arguments": {"path": "notes.org"},
                    "reason": "Relative paths must resolve through Motoko's allowlist.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        os.chdir(other)
        try:
            rejected = m.validate_action_text(str(action_path), preview=True)
            assert "status: rejected" in rejected
            assert "outside Motoko's allowed directories" in rejected

            os.chdir(docs)
            accepted = m.validate_action_text(str(action_path), preview=True)
            assert "status: valid" in accepted
            output = m.run_action_text(str(action_path))
            assert "status: completed" in output
        finally:
            os.chdir(old_cwd)


def test_skill_tool_read_paths_respect_motokoignore(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / ".motokoignore").write_text("archive.org\narchive/\n", encoding="utf-8")
        (docs / "keep.org").write_text("* Keep\n", encoding="utf-8")
        (docs / "archive.org").write_text("* Archive\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))
        write_demo_tool(m)
        m.approve_skill_tool_text("tool-backed-skill", "demo", yes=True)

        ignored_action = tmp / "ignored-read.json"
        ignored_action.write_text(
            json.dumps(
                {
                    "schema": "motoko-action-v1",
                    "kind": "skill_tool_run",
                    "skill": "tool-backed-skill",
                    "tool": "demo",
                    "arguments": {"path": str(docs / "archive.org")},
                    "reason": "Ignored files must not be read through skill tools.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        ignored = m.validate_action_text(str(ignored_action), preview=True)
        assert "status: rejected" in ignored
        assert "read path is ignored by .motokoignore" in ignored

        keep_action = tmp / "keep-read.json"
        keep_action.write_text(
            json.dumps(
                {
                    "schema": "motoko-action-v1",
                    "kind": "skill_tool_run",
                    "skill": "tool-backed-skill",
                    "tool": "demo",
                    "arguments": {"path": str(docs / "keep.org")},
                    "reason": "Non-ignored allowlisted files may be read.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        keep = m.validate_action_text(str(keep_action), preview=True)
        assert "status: valid" in keep


def test_skill_tool_session_confirmation_is_argument_scoped(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        m.add_allowed_dir(str(docs))
        write_demo_tool(m)
        metadata_path = m.skills_dir() / "tool-backed-skill" / "scripts" / "demo.tool.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["requires_confirmation"] = True
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False) + "\n", encoding="utf-8")
        m.approve_skill_tool_text("tool-backed-skill", "demo", yes=True)

        keys = []
        hashes = []
        for name in ("a.org", "b.org"):
            action_path = tmp / f"{name}.json"
            action_path.write_text(
                json.dumps(
                    {
                        "schema": "motoko-action-v1",
                        "kind": "skill_tool_run",
                        "skill": "tool-backed-skill",
                        "tool": "demo",
                        "arguments": {"path": str(docs / name)},
                        "reason": "Check session confirmation scope.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            preview = m.validate_action_text(str(action_path), preview=True)
            assert "status: needs_confirmation" in preview
            row = m.read_jsonl(m.action_ledger_path())[-1]
            keys.append(row.get("session_repeat_key"))
            hashes.append(row.get("argument_hash"))

        assert keys[0] != keys[1]
        assert hashes[0] != hashes[1]


def test_tool_catalog_and_action_plan_are_inspectable_without_running(m):
    old_cwd = os.getcwd()
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        m.add_allowed_dir(str(docs))
        os.chdir(docs)
        try:
            write_demo_tool(m)
            catalog = m.format_tool_catalog()
            assert "tool catalog:" in catalog
            assert "tool-backed-skill/demo" in catalog
            assert "external_process" in catalog

            plan = m.format_action_plan("use demo for logbook.org")
            assert "action plan:" in plan
            assert "model calls: none" in plan
            assert "tool-backed-skill/demo" in plan
            assert "status=needs_approval" in plan
            assert '"path": "logbook.org"' in plan

            m.approve_skill_tool_text("tool-backed-skill", "demo", yes=True)
            plan = m.format_action_plan("use demo for logbook.org")
            assert "status=valid" in plan
            assert "approval=persistent" in plan
        finally:
            os.chdir(old_cwd)


def test_action_run_keeps_project_write_tools_disabled(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        m.add_allowed_dir(str(docs))
        m.learn_skill_text(
            "project-writer",
            description="Project write tool",
            body="This tool declares project writes and should not run yet.",
        )
        scripts = m.skills_dir() / "project-writer" / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        (scripts / "writer.py").write_text("print('{}')\n", encoding="utf-8")
        (scripts / "writer.tool.json").write_text(
            json.dumps(
                {
                    "schema": "motoko-tool-v1",
                    "name": "writer",
                    "description": "Writes a project file.",
                    "script": "writer.py",
                    "interpreter": "python3",
                    "wrapper": "motoko-tool-python-stdlib",
                    "allowed_effects": ["write_allowed_project", "external_process"],
                    "argument_schema": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "timeout_seconds": 30,
                    "max_stdout_bytes": 65536,
                    "max_stderr_bytes": 16384,
                    "network": False,
                    "writes_project_files": True,
                    "requires_confirmation": True,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        m.approve_skill_tool_text("project-writer", "writer", yes=True)
        action_path = tmp / "write-action.json"
        action_path.write_text(
            json.dumps(
                {
                    "schema": "motoko-action-v1",
                    "kind": "skill_tool_run",
                    "skill": "project-writer",
                    "tool": "writer",
                    "arguments": {"path": str(docs / "notes.org")},
                    "reason": "Attempt a project mutation.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        output = m.run_action_text(str(action_path), yes=True)
        assert "status: failed" in output
        assert "project-writing skill tools are not enabled" in output


def test_skill_tool_project_write_proposal_is_validated_and_applied(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / ".motokoignore").write_text("ignored.org\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))
        target = docs / "proposal.org"
        write_project_proposal_tool(m)
        m.approve_skill_tool_text("project-proposer", "propose", yes=True)
        action_path = tmp / "proposal-action.json"
        action_path.write_text(
            json.dumps(
                {
                    "schema": "motoko-action-v1",
                    "kind": "skill_tool_run",
                    "skill": "project-proposer",
                    "tool": "propose",
                    "arguments": {"target": str(target), "content": "* Proposed\nprivate body\n"},
                    "reason": "Prepare a bounded project write proposal.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        output = m.run_action_text(str(action_path))
        assert "status: completed" in output
        assert "proposed actions: 1" in output
        assert not target.exists()

        result_path = next((m.state_root() / "tool-runs").glob("*/result.json"))
        run_id = result_path.parent.name
        proposals = m.format_action_proposals(run_id)
        assert "count: 1" in proposals
        assert "project_file_write needs_confirmation" in proposals
        assert "private body" not in proposals

        blocked = m.apply_action_proposal_text(run_id, 1, yes=False)
        assert "status: blocked" in blocked
        assert not target.exists()

        applied = m.apply_action_proposal_text(run_id, 1, yes=True)
        assert "status: completed" in applied
        assert target.read_text(encoding="utf-8") == "* Proposed\nprivate body\n"

        ledger_text = "\n".join(json.dumps(row, ensure_ascii=False) for row in m.read_jsonl(m.action_ledger_path()))
        assert "private body" not in ledger_text
        assert str(target) not in ledger_text


def test_skill_tool_project_write_proposal_respects_motokoignore(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / ".motokoignore").write_text("ignored.org\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))
        write_project_proposal_tool(m)
        m.approve_skill_tool_text("project-proposer", "propose", yes=True)
        action_path = tmp / "ignored-proposal-action.json"
        action_path.write_text(
            json.dumps(
                {
                    "schema": "motoko-action-v1",
                    "kind": "skill_tool_run",
                    "skill": "project-proposer",
                    "tool": "propose",
                    "arguments": {"target": str(docs / "ignored.org"), "content": "* Ignored\n"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        output = m.run_action_text(str(action_path))
        assert "status: completed" in output
        result_path = next((m.state_root() / "tool-runs").glob("*/result.json"))
        run_id = result_path.parent.name
        proposals = m.format_action_proposals(run_id)
        assert "project_file_write rejected" in proposals
        assert "ignored by .motokoignore" in proposals
        applied = m.apply_action_proposal_text(run_id, 1, yes=True)
        assert "status: rejected" in applied
        assert not (docs / "ignored.org").exists()


def test_skill_tool_project_write_proposal_requires_declared_effect(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        m.add_allowed_dir(str(docs))
        write_project_proposal_tool(m, skill_name="undeclared-proposer", include_effect=False)
        m.approve_skill_tool_text("undeclared-proposer", "propose", yes=True)
        action_path = tmp / "undeclared-proposal-action.json"
        action_path.write_text(
            json.dumps(
                {
                    "schema": "motoko-action-v1",
                    "kind": "skill_tool_run",
                    "skill": "undeclared-proposer",
                    "tool": "propose",
                    "arguments": {"target": str(docs / "proposal.org"), "content": "* Proposed\n"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        output = m.run_action_text(str(action_path))
        assert "status: failed" in output
        assert "without propose_project_changes effect" in output


def test_project_file_write_action_is_code_owned_and_confirmed(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        (docs / ".motokoignore").write_text("ignored.org\narchive/\n", encoding="utf-8")
        (docs / "existing.org").write_text("* Old\n", encoding="utf-8")
        archive = docs / "archive"
        archive.mkdir()
        m.add_allowed_dir(str(docs))

        target = docs / "new.org"
        action_path = tmp / "project-write.json"
        action_path.write_text(
            json.dumps(
                {
                    "schema": "motoko-action-v1",
                    "kind": "project_file_write",
                    "path": str(target),
                    "mode": "create",
                    "content": "* New\nsecret body\n",
                    "reason": "Create a bounded project file through Motoko-owned write machinery.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        preview = m.validate_action_text(str(action_path), preview=True)
        assert "kind: project_file_write" in preview
        assert "status: needs_confirmation" in preview
        assert "effects: write_allowed_project" in preview

        blocked = m.run_action_text(str(action_path))
        assert "status: blocked" in blocked
        assert not target.exists()

        output = m.apply_action_text(str(action_path), yes=True)
        assert "action run:" in output
        assert "status: completed" in output
        assert "bytes written:" in output
        assert target.read_text(encoding="utf-8") == "* New\nsecret body\n"

        ledger_text = "\n".join(json.dumps(row, ensure_ascii=False) for row in m.read_jsonl(m.action_ledger_path()))
        assert "secret body" not in ledger_text
        assert str(target) not in ledger_text
        assert "target_path_sha256" in ledger_text

        ignored_action = tmp / "ignored-write.json"
        ignored_action.write_text(
            json.dumps(
                {
                    "schema": "motoko-action-v1",
                    "kind": "project_file_write",
                    "path": str(docs / "ignored.org"),
                    "mode": "create",
                    "content": "* Ignored\n",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        ignored = m.validate_action_text(str(ignored_action), preview=True)
        assert "status: rejected" in ignored
        assert "ignored by .motokoignore" in ignored


def test_project_file_write_overwrite_requires_expected_hash(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        target = docs / "existing.org"
        target.write_text("* Old\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))

        missing_expected = tmp / "missing-expected.json"
        missing_expected.write_text(
            json.dumps(
                {
                    "schema": "motoko-action-v1",
                    "kind": "project_file_write",
                    "path": str(target),
                    "mode": "overwrite",
                    "content": "* New\n",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        rejected = m.validate_action_text(str(missing_expected), preview=True)
        assert "status: rejected" in rejected
        assert "overwrite requires expected_sha256" in rejected

        good = tmp / "overwrite.json"
        good.write_text(
            json.dumps(
                {
                    "schema": "motoko-action-v1",
                    "kind": "project_file_write",
                    "path": str(target),
                    "mode": "overwrite",
                    "expected_sha256": m.sha256_file(target),
                    "content": "* New\n",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        output = m.apply_action_text(str(good), yes=True)
        assert "status: completed" in output
        assert target.read_text(encoding="utf-8") == "* New\n"


def test_goal_loop_preview_save_and_list_without_execution(m):
    with isolated_state() as tmp:
        docs = tmp / "orgfiles"
        docs.mkdir()
        m.add_allowed_dir(str(docs))
        preview = m.format_goal_plan(
            "Review orgfiles priorities",
            scope=[str(docs)],
            allowed_tools=["tool-backed-skill/demo"],
            allowed_effects=["read_allowed_files", "write_motoko_state"],
            save=True,
        )
        assert "goal loop preview:" in preview
        assert "status: draft" in preview
        assert "execution enabled: no" in preview
        listing = m.format_goal_loops()
        assert "goal loops:" in listing
        assert "Review orgfiles priorities" in listing

        path = next(m.goal_loops_dir().glob("*.json"))
        preview_file = m.format_goal_preview(str(path))
        assert "goal loop preview:" in preview_file
        assert "runner: disabled" in preview_file

        broad = m.format_goal_plan(
            "Patch project files",
            scope=[str(docs)],
            allowed_effects=["write_allowed_project"],
        )
        assert "status: needs_approval" in broad
        assert "required-for-write_allowed_project" in broad

        bad = tmp / "bad-goal.json"
        bad.write_text(
            json.dumps(
                {
                    "schema": "motoko-goal-loop-v1",
                    "objective": "Bad loop",
                    "allowed_effects": ["privileged"],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        rejected = m.format_goal_preview(str(bad))
        assert "status: rejected" in rejected
        assert "forbidden effect" in rejected


def test_goal_loop_model_readonly_runs_and_stores_reviewable_proposals(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        m.add_allowed_dir(str(docs))
        target = docs / "planned.org"
        preview = m.format_goal_plan(
            "Review context and propose a project note",
            scope=[str(docs)],
            model_readonly=True,
            save=True,
        )
        assert "planner: model_readonly" in preview
        assert "runner: read-only model planner" in preview
        assert "propose_project_changes" in preview
        goal_path = next(m.goal_loops_dir().glob("*.json"))

        original_call_model = m.call_model

        def fake_call_model(messages, **kwargs):
            assert kwargs["route"] == m.MODEL_ROUTE_AUDIT
            assert kwargs["stream"] is False
            assert kwargs["json_schema"]["required"] == [
                "plan",
                "retrieval_assessment",
                "observations",
                "proposed_actions",
                "audit",
                "next_steps",
            ]
            prompt_text = "\n".join(str(message.get("content", "")) for message in messages)
            assert "Review context and propose a project note" in prompt_text
            return json.dumps(
                {
                    "plan": ["Inspect retrieved context", "Prepare a reviewable proposal"],
                    "retrieval_assessment": "Enough context for a safe proposal.",
                    "observations": ["The scope is allowlisted."],
                    "proposed_actions": [
                        {
                            "schema": "motoko-action-v1",
                            "kind": "project_file_write",
                            "path": str(target),
                            "mode": "create",
                            "content": "* Planned\nprivate planned body\n",
                            "reason": "Model-planned read-only proposal.",
                        }
                    ],
                    "audit": "No mutation was performed; proposal requires review.",
                    "next_steps": ["Review the proposed action before applying it elsewhere."],
                },
                ensure_ascii=False,
            )

        try:
            m.call_model = fake_call_model
            output = m.run_goal_text(str(goal_path), yes=True)
        finally:
            m.call_model = original_call_model

        assert "planner: model_readonly" in output
        assert "status: completed" in output
        assert "proposed actions: 1" in output
        assert not target.exists()

        run = next(iter(m.goal_runs_dir().glob("*.json")))
        run_record = m.safe_load_json(run)
        assert run_record["status"] == "completed"
        assert run_record["planner"] == "model_readonly"
        assert run_record["readonly_result"]["schema"] == "goal-readonly-result-v1"
        assert run_record["readonly_result"]["proposed_action_validations"][0]["status"] == "needs_confirmation"
        assert run_record["readonly_result"]["proposed_action_validations"][0]["kind"] == "project_file_write"

        proposals = m.format_goal_proposals(run_record["id"])
        assert "goal proposals:" in proposals
        assert "project_file_write needs_confirmation" in proposals
        assert "private planned body" not in proposals
        assert "private content: hidden" in proposals

        private = m.format_goal_proposals(run_record["id"], private=True)
        assert "private planned body" in private

        resumed = m.resume_goal_run_text(run_record["id"], yes=True)
        assert "status: completed" in resumed
        assert not target.exists()


def test_goal_loop_model_readonly_rejects_mutating_effects(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        m.add_allowed_dir(str(docs))
        preview = m.format_goal_plan(
            "Do not allow mutation in read-only planner",
            scope=[str(docs)],
            allowed_effects=["write_allowed_project"],
            model_readonly=True,
            save=True,
        )
        assert "status: rejected" in preview
        assert "model_readonly goal loops may use only" in preview
        goal_path = next(m.goal_loops_dir().glob("*.json"))
        output = m.run_goal_text(str(goal_path), yes=True)
        assert "status: rejected" in output
        assert "model_readonly goal loops may use only" in output
        assert not list(m.goal_runs_dir().glob("*.json"))


def test_goal_loop_model_confirmed_applies_reviewed_proposals(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        m.add_allowed_dir(str(docs))
        target = docs / "confirmed.org"
        preview = m.format_goal_plan(
            "Plan then apply a confirmed project note",
            scope=[str(docs)],
            model_confirmed=True,
            save=True,
        )
        assert "planner: model_confirmed" in preview
        assert "runner: model planner with explicit apply" in preview
        assert "write_allowed_project" in preview
        goal_path = next(m.goal_loops_dir().glob("*.json"))

        original_call_model = m.call_model

        def fake_call_model(messages, **kwargs):
            assert kwargs["route"] == m.MODEL_ROUTE_AUDIT
            prompt_text = "\n".join(str(message.get("content", "")) for message in messages)
            assert "user-confirmed goal loop" in prompt_text
            return json.dumps(
                {
                    "plan": ["Retrieve context", "Prepare confirmed write proposal"],
                    "retrieval_assessment": "Enough context.",
                    "observations": ["The docs scope is allowlisted."],
                    "proposed_actions": [
                        {
                            "schema": "motoko-action-v1",
                            "kind": "project_file_write",
                            "path": str(target),
                            "mode": "create",
                            "content": "* Confirmed\nprivate confirmed body\n",
                            "reason": "Model-confirmed proposal.",
                        }
                    ],
                    "audit": "Proposal only; apply requires explicit confirmation.",
                    "next_steps": ["Run goal apply after review."],
                },
                ensure_ascii=False,
            )

        try:
            m.call_model = fake_call_model
            output = m.run_goal_text(str(goal_path), yes=True)
        finally:
            m.call_model = original_call_model

        assert "planner: model_confirmed" in output
        assert "status: awaiting_confirmation" in output
        assert "proposed actions: 1" in output
        assert not target.exists()

        run_record = m.safe_load_json(next(m.goal_runs_dir().glob("*.json")))
        proposals = m.format_goal_proposals(run_record["id"])
        assert "project_file_write needs_confirmation" in proposals
        assert "private confirmed body" not in proposals

        refused = m.apply_goal_proposals_text(run_record["id"])
        assert "status: refused" in refused
        assert not target.exists()

        applied = m.apply_goal_proposals_text(run_record["id"], yes=True)
        assert "goal apply:" in applied
        assert "status: completed" in applied
        assert target.read_text(encoding="utf-8") == "* Confirmed\nprivate confirmed body\n"
        final = m.find_goal_run_record(run_record["id"])
        assert final["status"] == "completed"
        assert final["apply_results"][0]["status"] == "completed"


def test_git_worktree_actions_are_managed_confirmed_and_mergeable(m):
    if not shutil.which("git"):
        return
    with isolated_state() as tmp:
        repos = tmp / "repos"
        repos.mkdir()
        repo = repos / "repo"
        subprocess.run(["git", "init", "-b", "master", str(repo)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Motoko Test"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "motoko-test@example.invalid"], check=True)
        (repo / "README.md").write_text("# Test\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-m", "Initial commit"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        m.add_allowed_dir(str(repo))

        branch = "motoko-test-worktree"
        worktree = m.default_git_worktree_path(repo, branch)
        create = {
            "schema": "motoko-action-v1",
            "kind": "git_worktree_create",
            "repo": str(repo),
            "path": str(worktree),
            "branch": branch,
            "base": "master",
        }
        blocked = m.run_action_text_from_record(create)
        assert "status: needs_confirmation" in blocked or "status: blocked" in blocked
        created = m.run_action_text_from_record(create, yes=True)
        assert "status: completed" in created
        assert worktree.exists()
        assert m.managed_git_worktree_root_for_path(worktree / "note.txt") == worktree

        target = worktree / "note.txt"
        write = {
            "schema": "motoko-action-v1",
            "kind": "project_file_write",
            "path": str(target),
            "mode": "create",
            "content": "worktree note\n",
        }
        written = m.run_action_text_from_record(write, yes=True)
        assert "status: completed" in written
        commit = {
            "schema": "motoko-action-v1",
            "kind": "git_commit",
            "repo": str(worktree),
            "paths": [str(target)],
            "message": "Add worktree note",
        }
        committed = m.run_action_text_from_record(commit, yes=True)
        assert "status: completed" in committed

        merge = {
            "schema": "motoko-action-v1",
            "kind": "git_worktree_merge",
            "repo": str(repo),
            "path": str(worktree),
            "branch": branch,
            "target_branch": "master",
        }
        merged = m.run_action_text_from_record(merge, yes=True)
        assert "status: completed" in merged
        assert (repo / "note.txt").read_text(encoding="utf-8") == "worktree note\n"

        remove = {
            "schema": "motoko-action-v1",
            "kind": "git_worktree_remove",
            "path": str(worktree),
        }
        removed = m.run_action_text_from_record(remove, yes=True)
        assert "status: completed" in removed
        assert not worktree.exists()
        listing = m.format_git_worktrees()
        assert branch in listing
        assert "removed" in listing


def test_goal_loop_runs_explicit_confirmed_action_list(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        m.add_allowed_dir(str(docs))
        target = docs / "goal-output.org"
        action = {
            "schema": "motoko-action-v1",
            "kind": "project_file_write",
            "path": str(target),
            "mode": "create",
            "content": "* Goal output\n",
            "reason": "Explicit goal action.",
        }
        goal_path = tmp / "goal.json"
        goal_path.write_text(
            json.dumps(
                {
                    "schema": "motoko-goal-loop-v1",
                    "objective": "Create one bounded file",
                    "allowed_effects": ["write_allowed_project"],
                    "budgets": {"max_steps": 2, "max_tool_calls": 2, "max_model_calls": 1, "max_minutes": 5},
                    "actions": [action],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        preview = m.format_goal_preview(str(goal_path))
        assert "actions: 1" in preview
        assert "runner: explicit action list" in preview

        refused = m.run_goal_text(str(goal_path), yes=False)
        assert "status: refused" in refused
        assert not target.exists()
        assert not list(m.goal_runs_dir().glob("*.json"))

        output = m.run_goal_text(str(goal_path), yes=True)
        assert "goal run:" in output
        assert "completed: 1/1" in output
        assert "status: completed" in output
        assert target.read_text(encoding="utf-8") == "* Goal output\n"
        run_paths = list(m.goal_runs_dir().glob("*.json"))
        assert len(run_paths) == 1
        run_record = m.safe_load_json(run_paths[0])
        assert run_record["schema"] == "goal-run-v1"
        assert run_record["status"] == "completed"
        assert run_record["cursor"] == 1
        assert run_record["source_path"] == str(goal_path)
        assert run_record["action_results"][0]["status"] == "completed"
        assert run_record["action_results"][0]["validation_id"]
        listing = m.format_goal_runs()
        assert run_record["id"] in listing
        assert "Create one bounded file" in listing
        resumed = m.resume_goal_run_text(run_record["id"], yes=True)
        assert "status: completed" in resumed
        assert "cursor: 1/1" in resumed


def test_goal_run_pause_resume_preserves_completed_actions(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        m.add_allowed_dir(str(docs))
        first = docs / "first.org"
        second = docs / "second.org"
        actions = [
            {
                "schema": "motoko-action-v1",
                "kind": "project_file_write",
                "path": str(first),
                "mode": "create",
                "content": "* First\n",
                "reason": "First durable action.",
            },
            {
                "schema": "motoko-action-v1",
                "kind": "project_file_write",
                "path": str(second),
                "mode": "create",
                "content": "* Second\n",
                "reason": "Second durable action.",
            },
        ]
        goal_path = tmp / "goal-pause.json"
        goal_path.write_text(
            json.dumps(
                {
                    "schema": "motoko-goal-loop-v1",
                    "objective": "Create two bounded files",
                    "allowed_effects": ["write_allowed_project"],
                    "budgets": {"max_steps": 2, "max_tool_calls": 2, "max_model_calls": 1, "max_minutes": 5},
                    "actions": actions,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        original_execute = m.execute_action_record
        calls = {"count": 0}

        def pause_after_first(action, *, yes, cancel_event=None):
            validation, result = original_execute(action, yes=yes, cancel_event=cancel_event)
            calls["count"] += 1
            if calls["count"] == 1:
                m.request_work_pause("test goal pause")
            return validation, result

        try:
            m.execute_action_record = pause_after_first
            paused = m.run_goal_text(str(goal_path), yes=True)
        finally:
            m.execute_action_record = original_execute

        assert "status: paused" in paused
        assert first.read_text(encoding="utf-8") == "* First\n"
        assert not second.exists()
        run_record = m.safe_load_json(next(m.goal_runs_dir().glob("*.json")))
        assert run_record["status"] == "paused"
        assert run_record["cursor"] == 1
        assert run_record["action_results"][0]["status"] == "completed"
        assert run_record["action_results"][1]["status"] == "pending"

        resumed = m.resume_goal_run_text(run_record["id"], yes=True)
        assert "status: completed" in resumed
        assert "completed: 2/2" in resumed
        assert first.read_text(encoding="utf-8") == "* First\n"
        assert second.read_text(encoding="utf-8") == "* Second\n"
        final = m.find_goal_run_record(run_record["id"])
        assert final["status"] == "completed"
        assert final["cursor"] == 2
        assert final["action_results"][0]["status"] == "completed"
        assert final["action_results"][1]["status"] == "completed"


def test_goal_run_interruption_preserves_completed_actions(m):
    with isolated_state() as tmp:
        docs = tmp / "docs"
        docs.mkdir()
        m.add_allowed_dir(str(docs))
        first = docs / "first.org"
        second = docs / "second.org"
        goal_path = tmp / "goal-interrupt.json"
        goal_path.write_text(
            json.dumps(
                {
                    "schema": "motoko-goal-loop-v1",
                    "objective": "Interrupt after first file",
                    "allowed_effects": ["write_allowed_project"],
                    "budgets": {"max_steps": 2, "max_tool_calls": 2, "max_model_calls": 1, "max_minutes": 5},
                    "actions": [
                        {
                            "schema": "motoko-action-v1",
                            "kind": "project_file_write",
                            "path": str(first),
                            "mode": "create",
                            "content": "* First\n",
                        },
                        {
                            "schema": "motoko-action-v1",
                            "kind": "project_file_write",
                            "path": str(second),
                            "mode": "create",
                            "content": "* Second\n",
                        },
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        original_execute = m.execute_action_record
        cancel_event = threading.Event()
        calls = {"count": 0}

        def interrupt_after_first(action, *, yes, cancel_event=None):
            validation, result = original_execute(action, yes=yes, cancel_event=cancel_event)
            calls["count"] += 1
            if calls["count"] == 1 and cancel_event is not None:
                cancel_event.set()
            return validation, result

        try:
            m.execute_action_record = interrupt_after_first
            interrupted = m.run_goal_text(str(goal_path), yes=True, cancel_event=cancel_event)
        finally:
            m.execute_action_record = original_execute

        assert "status: interrupted" in interrupted
        assert first.read_text(encoding="utf-8") == "* First\n"
        assert not second.exists()
        run_record = m.safe_load_json(next(m.goal_runs_dir().glob("*.json")))
        assert run_record["status"] == "interrupted"
        assert run_record["cursor"] == 1
        assert run_record["action_results"][0]["status"] == "completed"
        assert run_record["action_results"][1]["status"] == "pending"

        resumed = m.resume_goal_run_text(run_record["id"], yes=True)
        assert "status: completed" in resumed
        assert first.read_text(encoding="utf-8") == "* First\n"
        assert second.read_text(encoding="utf-8") == "* Second\n"
        final = m.find_goal_run_record(run_record["id"])
        assert final["cursor"] == 2
        assert final["action_results"][0]["status"] == "completed"
        assert final["action_results"][1]["status"] == "completed"


def test_action_eval_report_covers_agentic_safety_fixtures(m):
    with isolated_state():
        report = m.run_action_eval()
        assert report["schema"] == "action-eval-v1"
        assert report["summary"]["status"] == "pass"
        fixture_ids = {row["id"] for row in report["fixtures"]}
        assert {
            "project_file_write_confirmed",
            "motokoignore_project_write_denied",
            "motokoignore_skill_read_denied",
            "session_confirmation_scopes_arguments",
            "script_project_write_blocked",
            "script_project_write_proposal_applied_by_motoko",
            "script_project_write_proposal_respects_motokoignore",
            "explicit_goal_run_confirmed",
            "goal_budget_refuses_extra_actions",
            "action_interruption_records_ledger",
            "goal_interruption_preserves_completed_actions",
        } <= fixture_ids
        text = m.format_action_eval_report(report)
        assert "action eval:" in text
        assert "fixtures: 11/11 passed" in text


def main() -> int:
    m = load_motoko()
    tests = [
        test_recent_conversation_lanes,
        test_maintenance_state_and_phases,
        test_memory_proposal_sends_transcript_not_assistant_prefill,
        test_memory_proposal_helper_timeout_respects_socket_activation,
        test_memory_proposal_queue_retries_until_saved,
        test_running_memory_proposal_queue_recovers_after_restart,
        test_memory_proposal_queue_defers_behind_active_chat_route,
        test_memory_proposal_queue_cancel_leaves_retryable,
        test_auto_maintenance_passes_cancel_event_to_memory_queue,
        test_memory_proposal_helper_subprocess_terminates_on_cancel,
        test_delete_conversation_removes_memory_proposal_jobs,
        test_skill_suggestion_parser_uses_local_review_signal,
        test_skill_registry_downgrades_unknown_handlers_and_effects,
        test_auto_maintenance_suggests_skill_without_saving_it,
        test_auto_skill_review_runs_on_explicit_signal_before_interval,
        test_skill_review_prompt_prioritizes_loaded_skill_context,
        test_manual_skill_review_and_suggestion_detail,
        test_skill_suggestion_accepts_patch_action,
        test_skill_manage_support_file_is_confined,
        test_skill_manage_support_file_commands,
        test_skill_upgrade_rewrites_legacy_skill_files,
        test_skill_plan_shows_prompt_and_retrieval_selection,
        test_skill_tool_metadata_validation_and_approval,
        test_action_preview_requires_approval_then_validates,
        test_action_preview_rejects_shell_and_bad_tool_metadata,
        test_action_run_executes_approved_tool_and_records_private_result,
        test_action_run_interruption_records_durable_status,
        test_skill_tool_relative_path_arguments_require_allowed_cwd,
        test_skill_tool_read_paths_respect_motokoignore,
        test_skill_tool_session_confirmation_is_argument_scoped,
        test_tool_catalog_and_action_plan_are_inspectable_without_running,
        test_action_run_keeps_project_write_tools_disabled,
        test_skill_tool_project_write_proposal_is_validated_and_applied,
        test_skill_tool_project_write_proposal_respects_motokoignore,
        test_skill_tool_project_write_proposal_requires_declared_effect,
        test_project_file_write_action_is_code_owned_and_confirmed,
        test_project_file_write_overwrite_requires_expected_hash,
        test_goal_loop_preview_save_and_list_without_execution,
        test_goal_loop_model_readonly_runs_and_stores_reviewable_proposals,
        test_goal_loop_model_readonly_rejects_mutating_effects,
        test_goal_loop_model_confirmed_applies_reviewed_proposals,
        test_git_worktree_actions_are_managed_confirmed_and_mergeable,
        test_goal_loop_runs_explicit_confirmed_action_list,
        test_goal_run_pause_resume_preserves_completed_actions,
        test_goal_run_interruption_preserves_completed_actions,
        test_action_eval_report_covers_agentic_safety_fixtures,
        test_interrupted_maintenance_resume,
        test_other_conversation_maintenance_is_quietly_abandoned,
        test_profile_dossier,
        test_project_scope_filters_memory_and_profile_context,
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
        test_chat_reasoning_payload_and_stream,
        test_unix_socket_model_loading_retries,
        test_unix_socket_connection_reset_retries_while_activating,
        test_unix_socket_connection_reset_retries_while_active,
        test_model_route_config_and_summary_cache,
        test_local_model_catalog_unix_socket_route,
        test_local_model_catalog_task_routes,
        test_slot_cache_capability_respects_route_gates,
        test_persistent_slot_cache_saves_and_restores_chat_slot,
        test_slot_cache_budget_profile_can_disable_saves,
        test_slot_cache_budget_gc_removes_old_records,
        test_slot_cache_budget_reports_service_owned_gc,
        test_cross_home_action_policy_is_config_driven,
        test_slot_cache_failures_are_nonfatal_cache_misses,
        test_catalog_request_policy_shapes_chat_payload_and_telemetry,
        test_chat_context_governor_selects_declared_route_profiles,
        test_chat_context_governor_falls_back_without_max_profile,
        test_route_kv_offload_notice_detects_catalog_flag,
        test_tui_kv_notice_blinks_for_three_seconds,
        test_last_call_telemetry_is_content_free,
        test_context_bench_dry_run_uses_governor_without_model_call,
        test_embedding_route_fails_fast_when_model_file_missing,
        test_local_model_status_diagnostic_uses_catalog_route_without_hashing,
        test_worker_route_releases_idle_large_chat_route,
        test_worker_route_defers_when_large_chat_route_is_busy,
        test_worker_route_waits_for_recent_large_chat_grace,
        test_worker_route_releases_idle_declared_exclusive_lane_peer,
        test_worker_route_defers_when_declared_exclusive_lane_peer_is_busy,
        test_chat_route_releases_idle_worker_routes,
        test_chat_route_releases_idle_large_chat_peer,
        test_chat_route_defers_when_large_chat_peer_is_busy,
        test_open_model_response_direct_calls_prepare_residency,
        test_model_service_status_and_stop_use_motoko_model_helper,
        test_summary_reductions_fan_out_across_worker_routes,
        test_sources_fallback_lists_attached_topic_context,
        test_answer_grounding_audit_sources,
        test_named_file_query_boosts_matching_path,
        test_retrieval_debug_explains_scores,
        test_named_logbook_recent_query_uses_latest_org_sections,
        test_source_code_locator_prioritizes_implementation_chunks,
        test_named_logbook_recent_query_keeps_nonconsecutive_latest_dates,
        test_named_temporal_query_ignores_other_dated_org_files,
        test_live_index_retrieval_uses_service_boundary,
        test_render_context_with_sources_uses_live_retrieval_service,
        test_temporal_retrieval_finds_latest_org_dates_without_evidence_store,
        test_hierarchical_evidence_store_retrieves_org_day_and_terms,
        test_span_selection_uses_embedding_and_rerank_routes,
        test_study_focus_recent_is_parsed_and_bounded,
        test_index_plan,
        test_nix_managed_allowdirs_message,
        test_cwd_learning_plan_and_existing_index,
        test_permissions_config,
        test_identity_config,
        test_context_package_builds_sources_and_plan,
        test_system_prompt_uses_context_package_for_plan,
        test_prompt_context_resyncs_attached_index_to_newer_completed_index,
        test_prompt_context_recovers_when_attached_index_snapshot_was_cleaned_up,
        test_sync_attached_context_refreshes_topic_and_dossier_metadata,
        test_prompt_context_filters_attached_artifacts_to_current_project,
        test_project_scope_filters_topic_reuse_before_attachment,
        test_assistant_color_config,
        test_index_change_summary_reports_source_lifecycle_decisions,
        test_source_lifecycle_report_blocks_changed_sources,
        test_source_lifecycle_cleanup_allows_reprocessed_changed_sources,
        test_artifact_lifecycle_family_specs_are_service_owned,
        test_source_lifecycle_report_service_owns_apply_decision,
        test_source_lifecycle_apply_deletes_only_safe_superseded_derived_artifacts,
        test_report_highlighting_is_render_only,
        test_tui_role_markers_working_and_worked_line,
        test_tui_alt_backspace_deletes_previous_word,
        test_tui_bottom_status_omits_chat_phase_and_spinner,
        test_tui_vector_status_reports_stale_progress,
        test_vector_progress_phase_is_content_free_and_finalizing,
        test_tui_append_renderer_keeps_transcript_in_scrollback,
        test_tui_active_answer_streams_stable_lines_to_scrollback,
        test_tui_seed_messages_renders_full_saved_history_without_redundant_banner,
        test_tui_resume_without_id_uses_dropdown_instead_of_terminal_prompt,
        test_conversation_delete_removes_owned_derived_artifacts,
        test_list_conversations_omits_empty_chats_but_keeps_queued_prompts,
        test_tui_report_commands_do_not_persist_system_output,
        test_tui_report_command_does_not_block_render_thread,
        test_tui_prompt_is_saved_before_context_preparation,
        test_tui_queued_prompt_is_durable_and_history_seeded,
        test_tui_stop_during_preparing_cancels_before_model_call,
        test_tui_clear_queue_discards_pending_prompts,
        test_tui_blocking_command_records_foreground_job,
        test_cli_heavy_commands_pass_cancel_events,
        test_tui_stop_closes_active_model_request,
        test_tui_ctrl_c_stops_active_answer_without_exiting,
        test_response_feedback_is_private_and_does_not_pollute_conversation,
        test_feedback_command_request_records_private_feedback,
        test_tui_feedback_plain_command_is_not_queued_during_active_work,
        test_feedback_eval_exports_private_retrieval_fixtures,
        test_retrieval_eval_replays_private_feedback_fixtures,
        test_retrieval_preview_shows_context_without_model_call,
        test_core_retrieval_sufficiency_planner_selects_bounded_extra_pass,
        test_retrieval_service_builds_sufficiency_expansion,
        test_prompt_context_runs_bounded_retrieval_sufficiency_pass,
        test_index_storage_audit_reports_duplicates_and_cleanup_plan,
        test_index_cleanup_removes_stale_superseded_snapshots_after_materializing_latest,
        test_vector_plan_reports_storage_and_readiness_gates,
        test_vector_build_and_query_lexical_baseline,
        test_embedding_vector_store_uses_catalog_route,
        test_vector_refresh_model_residency_defer_is_retryable,
        test_embedding_vector_store_splits_long_chunks_with_parent_mapping,
        test_embedding_vector_store_parallelizes_batches,
        test_embedding_parallelism_allows_32_cap,
        test_retrieval_vector_query_uses_short_worker_timeouts,
        test_embedding_vector_store_stale_when_route_model_changes,
        test_vector_doctor_reports_embedding_parallelism_without_private_rows,
        test_embedding_vector_store_resumes_saved_progress,
        test_embedding_vector_store_reuses_unchanged_rows_across_index_refresh,
        test_diagnose_safe_redacts_private_progress_metadata,
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
        test_prompt_context_uses_current_catalog_not_stale_catalog_file,
        test_index_resume_after_model_timeout,
        test_index_model_residency_defer_is_resumable_not_failed,
        test_index_pause_resume_rescans_new_files_without_overwriting_chunks,
        test_summarize_blocks_cancel_event_raises_work_paused,
        test_index_cancel_event_writes_paused_partial,
        test_vector_build_cancel_event_stops_before_work,
        test_tui_stop_requests_report_job_cancel,
        test_report_query_commands_pass_cancel_events,
        test_report_query_helpers_stop_when_pre_cancelled,
        test_org_task_signals_drive_retrieval,
        test_index_health_reports_new_files,
        test_index_signal_enrichment_upgrades_legacy_index,
        test_empty_org_signal_upgrade_converges,
        test_index_repair_regenerates_failed_chunk_artifacts,
        test_background_study_repairs_quality_failure,
        test_index_signal_enrichment_skips_active_index,
        test_repo_context_item,
        test_retrieval_service_renders_attached_context_without_generic_callback,
        test_cwd_indexing_ignores_light_study_done,
        test_color_survives_quiet_index_redirect,
        test_live_command_request_metadata,
        test_procedural_skills_are_realm_local_and_retrievable,
        test_builtin_source_scoped_temporal_skill_is_available,
        test_procedural_skills_are_included_in_prompt_and_sources,
        test_procedural_skill_commands,
        test_skill_lifecycle_records_usage_and_archive_restore,
        test_skill_lifecycle_commands_are_realm_local,
        test_motoko_codebase_context_and_commands_are_deterministic,
        test_self_improvement_eval_checks_codebase_skill_and_scanner,
        test_skill_scan_reports_script_risks,
        test_skill_curator_creates_feedback_patch_suggestion,
        test_skill_curator_creates_loaded_skill_patch_suggestion,
        test_skill_curator_creates_support_file_plan_for_large_skill,
        test_skill_curator_creates_consolidation_support_suggestion,
        test_skill_curator_creates_stale_unused_archive_review_suggestion,
    ]
    for test in tests:
        test(m)
    print(f"{len(tests)} motoko regression tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
