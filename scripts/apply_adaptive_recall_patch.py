#!/usr/bin/env python3
# One-shot branch bootstrap for adaptive episodic recall. This script is removed
# by the bootstrap workflow after it patches and validates the feature branch.

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def save(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_state() -> None:
    path = "motoko_core/state.py"
    text = load(path)
    old = '''def conversations_dir() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return ensure_private_dir(root / "conversations")


def memories_path() -> pathlib.Path:
'''
    new = '''def conversations_dir() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return ensure_private_dir(root / "conversations")


def conversation_history_dir() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return ensure_private_dir(root / "conversation-history")


def conversation_history_path(conversation_id: str) -> pathlib.Path:
    return conversation_history_dir() / f"{_safe_component(conversation_id, 'conversation')}.jsonl"


def conversation_windows_path(conversation_id: str) -> pathlib.Path:
    return conversation_history_dir() / f"{_safe_component(conversation_id, 'conversation')}.windows.jsonl"


def memories_path() -> pathlib.Path:
'''
    save(path, replace_once(text, old, new, label=path))


def patch_conversations() -> None:
    path = "motoko_core/conversations.py"
    text = load(path)
    text = replace_once(
        text,
        'from motoko_core.state import atomic_write, read_jsonl, safe_load_json\n',
        '''from motoko_core.episodic_recall import archive_conversation_messages, delete_episodic_history
from motoko_core.state import atomic_write, read_jsonl, safe_load_json
''',
        label=f"{path}: imports",
    )
    text = replace_once(
        text,
        '''def save_conversation_record(conv: dict, path: pathlib.Path, *, updated: str) -> None:
    conv["updated"] = updated
    atomic_write(path, json.dumps(conv, ensure_ascii=False, indent=2) + "\\n")
''',
        '''def save_conversation_record(conv: dict, path: pathlib.Path, *, updated: str) -> None:
    conv["updated"] = updated
    # Archive before replacing the compact record so a failed or later
    # compaction can never make the summary the only surviving copy.
    archive_conversation_messages(conv, archived_at=updated)
    atomic_write(path, json.dumps(conv, ensure_ascii=False, indent=2) + "\\n")
''',
        label=f"{path}: save",
    )
    text = replace_once(
        text,
        '''    with contextlib.suppress(FileNotFoundError):
        path.unlink()
    return False
''',
        '''    with contextlib.suppress(FileNotFoundError):
        path.unlink()
    delete_episodic_history(str(conv.get("id", "") or ""))
    return False
''',
        label=f"{path}: empty close",
    )
    save(path, text)


def patch_sources() -> None:
    path = "motoko_core/sources.py"
    text = load(path)
    anchor = '''        elif kind == "personality":
'''
    block = '''        elif kind == "adaptive-recall":
            lines.append(
                f"{idx:3d}  adaptive recall  round {source.get('round', 0)}  "
                f"{source.get('status', 'unknown')}  "
                f"queries {source.get('query_count', 0)}  hits {source.get('hit_count', 0)}"
            )
            scopes = ", ".join(str(scope) for scope in source.get("query_scopes", [])[:6]) or "-"
            lines.append(f"     why: model-directed bounded episodic recovery; scopes {scopes}")
        elif kind == "conversation-history":
            windows = ",".join(str(window)[-8:] for window in source.get("window_ids", [])[:4]) or "-"
            lines.append(
                f"{idx:3d}  conversation history {source.get('conversation_id', '')}  "
                f"messages {source.get('start_ordinal')}-{source.get('end_ordinal')}  "
                f"score {source.get('score', 0)}  round {source.get('recall_round', 0)}"
            )
            lines.append(
                f"     why: raw prior-turn evidence selected by adaptive recall; "
                f"matched {source.get('matched_terms', 0)} term(s); windows {windows}"
            )
            if source.get("title"):
                lines.append(f"     conversation: {source.get('title', '')}")
        elif kind == "personality":
'''
    save(path, replace_once(text, anchor, block, label=path))


def patch_flake() -> None:
    path = "flake.nix"
    text = load(path)
    text = replace_once(
        text,
        '''            python3 -m py_compile ${src}/motoko
''',
        '''            python3 -m py_compile ${src}/motoko ${src}/motoko_core/episodic_recall.py
''',
        label=f"{path}: syntax",
    )
    text = replace_once(
        text,
        '''                MOTOKO_SOURCE=${src}/motoko python3 ${src}/tests/motoko_regression.py
                touch "$out"
''',
        '''                MOTOKO_SOURCE=${src}/motoko python3 ${src}/tests/motoko_regression.py
                PYTHONPATH=${src} python3 ${src}/tests/episodic_recall_test.py
                touch "$out"
''',
        label=f"{path}: regression",
    )
    save(path, text)


def patch_project_context() -> None:
    path = "docs/project-context.md"
    text = load(path)
    anchor = '''- compacted conversations;
'''
    replacement = '''- compacted conversations backed by lossless realm-local episodic history, with
  context-window lineage and bounded model-directed adaptive recall so summaries
  are continuity hints rather than the sole surviving representation of older turns;
'''
    save(path, replace_once(text, anchor, replacement, label=path))


def patch_motoko_docs() -> None:
    path = "docs/motoko.md"
    text = load(path)
    anchor = '''`conversation_recall` controls how much same-realm conversation history Motoko
packs automatically. `current_messages` may be an integer or `"all"`; pair
large values with `current_max_chars` so a long chat cannot crowd out source
evidence. Saved conversations are selected by a recency lane plus a
query-relevance lane, then packed as title, summary, matched snippets, recent
turns, and provenance. If `conversation_limit` is omitted, Motoko uses at least
`recent_conversations + relevant_conversations`.
'''
    replacement = anchor + '''
Long conversations also keep append-only raw episodic history under Motoko's
realm-local state. Compaction still produces a dense summary for cheap
continuity, but it archives raw turns before dropping them from the active
transcript and advances a context-window lineage. When older raw history exists,
adaptive episodic recall may use the selected chat model for at most two
structured retrieval-planning rounds, then search and inject bounded raw
conversation excerpts with provenance before final synthesis. Set
`MOTOKO_ADAPTIVE_RECALL=0` for a one-session kill switch. Raw history recovered
this way outranks model-generated summaries when the two conflict.
'''
    save(path, replace_once(text, anchor, replacement, label=path))


def patch_episodic_module() -> None:
    path = "motoko_core/episodic_recall.py"
    text = load(path)
    text = replace_once(
        text,
        'next_ordinal = max(int(row.get("ordinal", -1) or -1) for row in existing) + 1',
        'next_ordinal = max(int(row.get("ordinal", -1)) for row in existing) + 1',
        label=f"{path}: ordinal zero",
    )
    text = replace_once(
        text,
        '''        key = (
            source.get("kind"),
            source.get("conversation_id"),
            source.get("start_ordinal"),
            source.get("end_ordinal"),
            tuple(source.get("message_ids", [])),
        )
''',
        '''        key = (
            source.get("kind"),
            source.get("round"),
            source.get("conversation_id"),
            source.get("start_ordinal"),
            source.get("end_ordinal"),
            tuple(source.get("message_ids", [])),
        )
''',
        label=f"{path}: source dedupe",
    )
    text = replace_once(
        text,
        '''            "queries": [
                {
                    "query": item.get("query", ""),
                    "scope": item.get("scope", ""),
                    "purpose": item.get("purpose", ""),
                }
                for item in plan.get("queries", [])
            ],
            "hit_count": 0,
''',
        '''            # Keep /sources and saved answer diagnostics content-free.
            # Full structured plans remain in the ephemeral AdaptiveRecallResult.
            "query_scopes": [item.get("scope", "") for item in plan.get("queries", [])],
            "query_hashes": [
                _sha256_text(str(item.get("query", "") or ""))
                for item in plan.get("queries", [])
            ],
            "hit_count": 0,
''',
        label=f"{path}: planner provenance",
    )
    save(path, text)


def patch_episodic_test() -> None:
    path = "tests/episodic_recall_test.py"
    text = load(path)
    text = replace_once(
        text,
        '[message("user", "nothing about the concert")],',
        '[message("user", "nothing relevant here")],',
        label=path,
    )
    save(path, text)


def patch_root() -> None:
    path = "motoko"
    text = load(path)

    text = replace_once(
        text,
        '''from motoko_core.commands import (  # noqa: E402
''',
        '''from motoko_core.episodic_recall import (  # noqa: E402
    archive_conversation_messages,
    history_rows as episodic_history_rows,
    run_adaptive_recall,
    seal_context_window,
    delete_episodic_history,
)
from motoko_core.commands import (  # noqa: E402
''',
        label=f"{path}: episodic imports",
    )

    text = replace_once(
        text,
        '''GROUNDING_STRONG_SOURCE_KINDS = {
    "chunk",
    "topic-evidence",
    "file",
    "repo",
    "dossier-memory",
    "dossier-conversation",
}
''',
        '''GROUNDING_STRONG_SOURCE_KINDS = {
    "chunk",
    "topic-evidence",
    "file",
    "repo",
    "dossier-memory",
    "dossier-conversation",
    "conversation-history",
}
''',
        label=f"{path}: strong evidence",
    )
    text = replace_once(
        text,
        '''    "conversation-summary",
}
MAX_MEMORY_CHARS = 1800
''',
        '''    "conversation-summary",
    "adaptive-recall",
}
MAX_MEMORY_CHARS = 1800
''',
        label=f"{path}: context evidence",
    )

    boundary = '''    return expansion.text, expansion.sources, expansion.plan


def render_conversation_summary(conv: dict) -> str:
'''
    adaptive_helpers = '''    return expansion.text, expansion.sources, expansion.plan


_ADAPTIVE_RECALL_CACHE: dict[tuple[str, str, int], tuple[str, list[dict], dict]] = {}


def adaptive_recall_seed_context(
    *,
    profile_text: str,
    memory_text: str,
    recent_text: str,
    summary_text: str,
    context_text: str,
    sufficiency_text: str,
    scope_text: str,
    max_chars: int = 32000,
) -> str:
    sections = [
        ("Profile", profile_text),
        ("Durable memories", memory_text),
        ("Recent saved conversations", recent_text),
        ("Current conversation summary", summary_text),
        ("Attached/retrieved context", context_text),
        ("Deterministic sufficiency expansion", sufficiency_text),
        ("Project scope", scope_text),
    ]
    parts = []
    used = 0
    for label, value in sections:
        value = str(value or "").strip()
        if not value:
            continue
        block = f"{label}:\\n{compact_text(value, 6000)}"
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = compact_text(block, remaining)
        parts.append(block)
        used += len(block)
    return "\\n\\n".join(parts)


def adaptive_recall_conversations(conv: dict, project_scope: dict) -> list[dict]:
    current_id = str(conv.get("id", "") or "")
    roots = project_scope_roots(project_scope)
    selected = []
    for row in list_conversations():
        row_id = str(row.get("id", "") or "")
        if row_id == current_id:
            selected.append(row)
            continue
        if not roots:
            selected.append(row)
            continue
        row_roots = conversation_project_roots(row)
        if not row_roots:
            continue
        if any(project_root_matches(root, roots) for root in row_roots):
            selected.append(row)
    if not any(str(row.get("id", "") or "") == current_id for row in selected):
        selected.append(conv)
    return selected


def adaptive_recall_context(
    conv: dict,
    query: str,
    *,
    seed_context: str,
    project_scope: dict,
    cancel_event=None,
) -> tuple[str, list[dict], dict]:
    if not env_flag("MOTOKO_ADAPTIVE_RECALL", True):
        return "", [], {"status": "disabled"}

    archive_conversation_messages(conv)
    cache_key = (
        str(conv.get("id", "") or ""),
        str(query or "").strip(),
        len(episodic_history_rows(str(conv.get("id", "") or ""))),
    )
    cached = _ADAPTIVE_RECALL_CACHE.get(cache_key)
    if cached is not None:
        return cached

    def planner(messages: list[dict], schema: dict, _round_number: int):
        raise_if_work_cancelled(
            cancel_event,
            "adaptive episodic recall interrupted by request",
            work_kind="retrieval",
        )
        return call_model(
            messages,
            temperature=0.1,
            stream=False,
            echo=False,
            timeout=MODEL_TIMEOUT_SECONDS,
            route=MODEL_ROUTE_CHAT,
            sampling_preset="deterministic",
            json_schema=schema,
            reasoning_preset=conversation_reasoning_preset(conv),
            max_tokens=800,
            chat_model=conversation_chat_model(conv),
            cancel_event=cancel_event,
        )

    try:
        result = run_adaptive_recall(
            conv=conv,
            conversations=adaptive_recall_conversations(conv, project_scope),
            user_query=str(query or "").strip(),
            seed_context=seed_context,
            planner=planner,
        )
    except WorkPaused:
        raise
    except (Exception, SystemExit) as exc:
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("__motoko_stopped__") from exc
        return (
            "",
            [
                {
                    "kind": "adaptive-recall",
                    "schema": "adaptive-recall-source-v1",
                    "round": 0,
                    "status": "planner-error",
                    "query_count": 0,
                    "query_scopes": [],
                    "hit_count": 0,
                    "error_type": type(exc).__name__,
                }
            ],
            {"status": "planner-error", "error_type": type(exc).__name__},
        )

    value = (result.text, result.sources, result.diagnostics)
    if result.diagnostics.get("status") != "not-needed":
        if len(_ADAPTIVE_RECALL_CACHE) >= 16:
            _ADAPTIVE_RECALL_CACHE.pop(next(iter(_ADAPTIVE_RECALL_CACHE)))
        _ADAPTIVE_RECALL_CACHE[cache_key] = value
    return value


def render_conversation_summary(conv: dict) -> str:
'''
    text = replace_once(text, boundary, adaptive_helpers, label=f"{path}: adaptive helpers")

    prompt_block = '''    personality_text, personality_file, personality_exists = load_personality()
    identity_text = format_identity()
    summary_text = render_conversation_summary(conv)
    lanes = build_prompt_context_lanes(
'''
    prompt_new = '''    personality_text, personality_file, personality_exists = load_personality()
    identity_text = format_identity()
    summary_text = render_conversation_summary(conv)
    adaptive_seed = adaptive_recall_seed_context(
        profile_text=profile_text,
        memory_text=memory_text,
        recent_text=recent_text,
        summary_text=summary_text,
        context_text=context_text,
        sufficiency_text=sufficiency_text,
        scope_text=scope_text,
    )
    adaptive_text, adaptive_sources, _adaptive_diagnostics = adaptive_recall_context(
        conv,
        query.strip() or retrieval_query,
        seed_context=adaptive_seed,
        project_scope=project_scope,
        cancel_event=cancel_event,
    )
    lanes = build_prompt_context_lanes(
'''
    text = replace_once(text, prompt_block, prompt_new, label=f"{path}: prompt adaptive call")

    lanes_end = '''        catalog=catalog,
        project_roots=project_roots,
    )
    context_package = build_context_package(
'''
    lanes_new = '''        catalog=catalog,
        project_roots=project_roots,
    )
    if adaptive_text or adaptive_sources:
        lanes.insert(
            max(0, len(lanes) - 1),
            ContextLane(
                "adaptive episodic recall",
                adaptive_text,
                adaptive_sources,
                "model-directed recovery of raw prior conversation evidence",
            ),
        )
    context_package = build_context_package(
'''
    text = replace_once(text, lanes_end, lanes_new, label=f"{path}: adaptive lane")

    text = replace_once(
        text,
        '''        "sufficiency_text": sufficiency_text,
        "catalog_text": catalog_text,
''',
        '''        "sufficiency_text": sufficiency_text,
        "adaptive_text": adaptive_text,
        "catalog_text": catalog_text,
''',
        label=f"{path}: context values",
    )

    text = replace_once(
        text,
        '''    sufficiency_text = context_values["sufficiency_text"]
    catalog_text = context_values["catalog_text"]
''',
        '''    sufficiency_text = context_values["sufficiency_text"]
    adaptive_text = context_values["adaptive_text"]
    catalog_text = context_values["catalog_text"]
''',
        label=f"{path}: system values",
    )

    text = replace_once(
        text,
        '''        Use the context sufficiency note to decide whether to answer directly,
        mention uncertainty, or suggest /study for a deeper bounded study pass.
''',
        '''        Use the context sufficiency note to decide whether to answer directly,
        mention uncertainty, or suggest /study for a deeper bounded study pass.
        Raw excerpts under Adaptive episodic recall are primary evidence about
        what was actually said or happened in prior conversation turns. If a
        model-generated summary or durable memory conflicts with recovered raw
        history, prefer the raw source and surface the conflict. Do not turn an
        old hypothesis or interpretation into a fact merely because it appears
        in a summary.
''',
        label=f"{path}: system instructions",
    )

    text = replace_once(
        text,
        '''        Compacted conversation summary:
        {summary_text}

        Attached documents and dossiers:
''',
        '''        Compacted conversation summary:
        {summary_text}

        Adaptive episodic recall:
        {adaptive_text or 'No raw-history recovery was needed for this turn.'}

        Attached documents and dossiers:
''',
        label=f"{path}: system adaptive text",
    )

    text = replace_once(
        text,
        '''    messages = conv.get("messages", [])
    if len(messages) <= COMPACT_KEEP_MESSAGES:
''',
        '''    messages = conv.get("messages", [])
    # Preserve the source transcript before any lossy reduction.
    archive_conversation_messages(conv)
    if len(messages) <= COMPACT_KEEP_MESSAGES:
''',
        label=f"{path}: compaction archive",
    )

    text = replace_once(
        text,
        '''    conv["messages"] = recent
    conv["last_auto_compact_message_count"] = len(recent)
''',
        '''    seal_context_window(
        conv,
        reason="compaction",
        retained_message_count=len(recent),
        summary_text=conv["summary"],
    )
    conv["messages"] = recent
    conv["last_auto_compact_message_count"] = len(recent)
''',
        label=f"{path}: compaction window",
    )

    delete_old = '''def delete_conversation_file_for_id(conversation_id: str) -> bool:
    try:
        conversation_path(conversation_id).unlink()
    except FileNotFoundError:
        return False
    return True
'''
    delete_new = '''def delete_conversation_file_for_id(conversation_id: str) -> bool:
    deleted = True
    try:
        conversation_path(conversation_id).unlink()
    except FileNotFoundError:
        deleted = False
    delete_episodic_history(conversation_id)
    return deleted
'''
    text = replace_once(text, delete_old, delete_new, label=f"{path}: delete episodic")

    save(path, text)


def main() -> None:
    patch_state()
    patch_episodic_module()
    patch_episodic_test()
    patch_conversations()
    patch_sources()
    patch_flake()
    patch_project_context()
    patch_motoko_docs()
    patch_root()
    print("adaptive episodic recall patch applied")


if __name__ == "__main__":
    main()
