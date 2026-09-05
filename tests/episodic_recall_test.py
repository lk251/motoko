#!/usr/bin/env python3
"""Deterministic regression coverage for lossless episodic recall."""

from __future__ import annotations

import json
import os
import tempfile

from motoko_core.episodic_recall import (
    adaptive_recall_needed,
    archive_conversation_messages,
    ensure_context_window_state,
    history_hit_source,
    history_rows,
    normalize_adaptive_recall_plan,
    run_adaptive_recall,
    search_conversation_history,
    seal_context_window,
    window_rows,
)


def conversation(conversation_id: str, title: str, messages: list[dict]) -> dict:
    return {
        "id": conversation_id,
        "title": title,
        "created": "2026-01-01T00:00:00+00:00",
        "updated": "2026-01-01T00:00:00+00:00",
        "messages": list(messages),
        "context_items": [],
    }


def message(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def test_incremental_archive_is_lossless_and_idempotent() -> None:
    conv = conversation(
        "conv-a",
        "Archive",
        [
            message("user", "one"),
            message("assistant", "two"),
            message("user", "three"),
        ],
    )
    assert archive_conversation_messages(conv) == 3
    assert archive_conversation_messages(conv) == 0
    conv["messages"].append(message("assistant", "four"))
    assert archive_conversation_messages(conv) == 1
    rows = history_rows("conv-a")
    assert [row["content"] for row in rows] == ["one", "two", "three", "four"]
    assert [row["ordinal"] for row in rows] == [0, 1, 2, 3]


def test_retained_suffix_does_not_duplicate_after_compaction() -> None:
    messages = [
        message("user" if idx % 2 == 0 else "assistant", f"turn {idx}")
        for idx in range(30)
    ]
    conv = conversation("conv-b", "Long chat", messages)
    assert archive_conversation_messages(conv) == 30
    conv["messages"] = messages[-8:]
    assert archive_conversation_messages(conv) == 0
    conv["messages"].append(message("user", "new turn after rollover"))
    assert archive_conversation_messages(conv) == 1
    rows = history_rows("conv-b")
    assert len(rows) == 31
    assert rows[0]["content"] == "turn 0"
    assert rows[-1]["content"] == "new turn after rollover"


def test_context_window_lineage_advances_without_rewriting_history() -> None:
    conv = conversation(
        "conv-c",
        "Windows",
        [message("user", "old"), message("assistant", "answer")],
    )
    initial = dict(ensure_context_window_state(conv))
    sealed = seal_context_window(
        conv,
        reason="compaction",
        retained_message_count=1,
        summary_text="small summary",
    )
    state = conv["context_window"]
    assert sealed["window_id"] == initial["current_window_id"]
    assert state["first_window_id"] == initial["first_window_id"]
    assert state["previous_window_id"] == initial["current_window_id"]
    assert state["current_window_id"] != initial["current_window_id"]
    assert state["window_number"] == 1
    assert len(history_rows("conv-c")) == 2
    assert len(window_rows("conv-c")) == 1


def test_search_recovers_old_raw_detail_and_adjacent_turns() -> None:
    messages = [
        message("user", "ordinary opening"),
        message("assistant", "ordinary answer"),
        message("user", "The violet umbrella was left at Sants station."),
        message("assistant", "I will remember the station detail."),
        message("user", "later topic"),
        message("assistant", "later answer"),
    ]
    conv = conversation("conv-d", "Trip", messages)
    archive_conversation_messages(conv)
    conv["messages"] = messages[-2:]
    hits = search_conversation_history(
        [conv],
        "violet umbrella Sants station",
        current_conversation_id="conv-d",
        scope="current_conversation",
        limit=3,
        context_radius=1,
    )
    assert hits
    text = "\n".join(row["content"] for row in hits[0]["rows"])
    assert "violet umbrella" in text
    assert "remember the station detail" in text


def test_scope_can_cross_conversations_deliberately() -> None:
    current = conversation(
        "conv-e",
        "Current",
        [message("user", "nothing about the concert")],
    )
    previous = conversation(
        "conv-f",
        "Earlier",
        [message("user", "Mara said the concert would be in Lisbon.")],
    )
    archive_conversation_messages(current)
    archive_conversation_messages(previous)
    local = search_conversation_history(
        [current, previous],
        "Mara concert Lisbon",
        current_conversation_id="conv-e",
        scope="current_conversation",
    )
    cross = search_conversation_history(
        [current, previous],
        "Mara concert Lisbon",
        current_conversation_id="conv-e",
        scope="all_conversations",
    )
    assert not local
    assert cross
    assert cross[0]["conversation_id"] == "conv-f"


def test_plan_normalization_caps_deduplicates_and_sanitizes() -> None:
    plan = normalize_adaptive_recall_plan(
        {
            "status": "need_more_context",
            "queries": [
                {"query": "  first   query ", "scope": "current_conversation", "purpose": "one"},
                {"query": "FIRST QUERY", "scope": "all_conversations", "purpose": "duplicate"},
                {"query": "second query", "scope": "bogus", "purpose": "two"},
                {"query": "third query", "scope": "all_conversations", "purpose": "three"},
                {"query": "fourth query", "scope": "all_conversations", "purpose": "four"},
            ],
        }
    )
    assert plan["status"] == "need_more_context"
    assert [row["query"] for row in plan["queries"]] == [
        "first query",
        "second query",
        "third query",
    ]
    assert plan["queries"][1]["scope"] == "current_conversation"


def test_source_provenance_is_content_free() -> None:
    secret = "private correspondence phrase never expose in metadata"
    conv = conversation("conv-g", "Private", [message("user", secret)])
    archive_conversation_messages(conv)
    hit = search_conversation_history(
        [conv],
        "private correspondence phrase",
        current_conversation_id="conv-g",
        scope="current_conversation",
        limit=1,
        context_radius=0,
    )[0]
    source = history_hit_source(hit, query="private correspondence phrase", round_number=1)
    serialized = json.dumps(source, ensure_ascii=False)
    assert secret not in serialized
    assert "private correspondence phrase" not in serialized
    assert source["message_ids"]
    assert source["query_sha256"]


def test_bounded_adaptive_loop_can_retrieve_then_stop() -> None:
    messages = [
        message("user", "Earlier, Nina explicitly said she wanted to visit Valencia."),
        message("assistant", "That is an explicit future-plan statement."),
        message("user", "many later details"),
    ]
    conv = conversation("conv-h", "Relationship", messages)
    archive_conversation_messages(conv)
    conv["messages"] = [messages[-1]]
    conv["summary"] = "Long relationship discussion."
    calls = []

    def planner(_messages, _schema, round_number):
        calls.append(round_number)
        if round_number == 1:
            return {
                "status": "need_more_context",
                "queries": [
                    {
                        "query": "Nina explicitly wanted visit Valencia",
                        "scope": "current_conversation",
                        "purpose": "recover explicit future-plan statement",
                    }
                ],
            }
        return {"status": "sufficient", "queries": []}

    result = run_adaptive_recall(
        conv=conv,
        conversations=[conv],
        user_query="Am I overinterpreting this week?",
        seed_context="Current context is ambiguous.",
        planner=planner,
    )
    assert calls == [1, 2]
    assert "visit Valencia" in result.text
    assert any(source.get("kind") == "adaptive-recall" for source in result.sources)
    assert any(source.get("kind") == "conversation-history" for source in result.sources)


def test_short_uncompacted_chat_skips_planner() -> None:
    conv = conversation(
        "conv-i",
        "Short",
        [message("user", "hello"), message("assistant", "hi")],
    )
    assert not adaptive_recall_needed(conv)
    called = False

    def planner(_messages, _schema, _round):
        nonlocal called
        called = True
        return {"status": "sufficient", "queries": []}

    result = run_adaptive_recall(
        conv=conv,
        conversations=[conv],
        user_query="How are things?",
        seed_context="",
        planner=planner,
    )
    assert not called
    assert result.diagnostics["status"] == "not-needed"


def main() -> None:
    tests = [
        test_incremental_archive_is_lossless_and_idempotent,
        test_retained_suffix_does_not_duplicate_after_compaction,
        test_context_window_lineage_advances_without_rewriting_history,
        test_search_recovers_old_raw_detail_and_adjacent_turns,
        test_scope_can_cross_conversations_deliberately,
        test_plan_normalization_caps_deduplicates_and_sanitizes,
        test_source_provenance_is_content_free,
        test_bounded_adaptive_loop_can_retrieve_then_stop,
        test_short_uncompacted_chat_skips_planner,
    ]
    with tempfile.TemporaryDirectory(prefix="motoko-episodic-test-") as tmp:
        old_state = os.environ.get("MOTOKO_STATE_HOME")
        os.environ["MOTOKO_STATE_HOME"] = tmp
        try:
            for test in tests:
                test()
        finally:
            if old_state is None:
                os.environ.pop("MOTOKO_STATE_HOME", None)
            else:
                os.environ["MOTOKO_STATE_HOME"] = old_state
    print(f"episodic recall tests: {len(tests)} passed")


if __name__ == "__main__":
    main()
