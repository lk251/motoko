#!/usr/bin/env python3
"""Small stdlib evaluation harness for Motoko memory/study behavior."""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import tempfile


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
    old_profile = os.environ.get("MOTOKO_BACKGROUND_PROFILE")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["MOTOKO_STATE_HOME"] = str(pathlib.Path(tmp) / "state")
        os.environ["MOTOKO_CONFIG_HOME"] = str(pathlib.Path(tmp) / "config")
        os.environ["MOTOKO_BACKGROUND_PROFILE"] = "0"
        try:
            yield pathlib.Path(tmp)
        finally:
            for key, old_value in (
                ("MOTOKO_STATE_HOME", old_state),
                ("MOTOKO_CONFIG_HOME", old_config),
                ("MOTOKO_BACKGROUND_PROFILE", old_profile),
            ):
                if old_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old_value


def write_json(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def test_study_reuses_existing_dossier(m):
    conv = m.new_conversation("Study reuse")
    conv["id"] = "study-reuse"
    m.save_conversation(conv)
    dossier = {
        "id": "craft-dossier",
        "name": "Craftsmanship",
        "query": "craftsmanship quality",
        "summary": "Javier wants Motoko to feel like careful swiss watchmaker craftsmanship.",
        "source_memories": [],
        "source_conversations": [],
    }
    write_json(m.dossier_path(dossier["id"]), dossier)
    result = m.study_query(conv, "craftsmanship quality")
    assert "attached existing memory dossier" in result
    assert conv["context_items"][0]["kind"] == "dossier"
    assert conv["context_items"][0]["id"] == dossier["id"]


def test_context_sufficiency_and_catalog(m):
    conv = m.new_conversation("Catalog")
    conv["id"] = "catalog"
    m.save_conversation(conv)
    thin = m.context_sufficiency_note(conv, "craftsmanship", [])
    assert "thin" in thin

    sourceful = m.context_sufficiency_note(
        conv,
        "craftsmanship",
        [{"kind": "dossier", "id": "craft-dossier"}],
    )
    assert "likely enough" in sourceful

    catalog = m.write_context_catalog()
    text = m.format_context_catalog(catalog)
    assert m.DEFAULT_MODEL in text
    assert "endpoint=" in text
    assert "conversations=" in text


def test_context_plan_and_source_reasons(m):
    conv = m.new_conversation("Sources")
    conv["id"] = "sources"
    m.add_memory(
        "Javier wants Motoko source reports to explain why context was included.",
        source="test",
        conversation_id=conv["id"],
        importance=4,
    )
    _prompt, sources = m.build_system_prompt_and_sources(conv, "source reports")
    assert any(source.get("kind") == "context-plan" for source in sources)
    report = m.format_sources(sources)
    assert "context plan" in report
    assert "lane:" in report
    assert "why:" in report


def test_background_study_state(m):
    conv = m.new_conversation("Background")
    conv["id"] = "background"
    conv["messages"] = [{"role": "user", "content": "craftsmanship and memory"}]
    m.save_conversation(conv)
    phases = []
    notes = m.background_study_step(conv, phase_callback=phases.append)
    state = m.read_study_state()
    assert "study: catalog" in phases
    assert "study: planning" in phases
    assert state["phase"] == "study: idle"
    assert isinstance(notes, list)
    jobs = m.read_study_jobs()
    assert jobs
    assert jobs[-1]["event"] == "completed"


def test_interrupted_background_study_resume_note(m):
    conv = m.new_conversation("Interrupted")
    conv["id"] = "interrupted"
    m.save_conversation(conv)
    m.write_study_phase("study: catalog", job_id="study-old", status="running")
    notes = m.background_study_step(conv)
    assert any("resumed after interrupted study job study-old" in note for note in notes)
    state = m.read_study_state()
    assert state["status"] == "completed"


def test_heavy_index_refresh_replaces_attached_index(m):
    docs = pathlib.Path(os.environ["MOTOKO_STATE_HOME"]).parent / "docs"
    docs.mkdir()
    old_file = docs / "a.org"
    old_file.write_text("* TODO Old task\n", encoding="utf-8")
    for idx in range(3):
        (docs / f"new-{idx}.org").write_text(f"* TODO New task {idx}\n", encoding="utf-8")
    m.add_allowed_dir(str(docs))

    old_index = {
        "id": "old-index",
        "name": "orgfiles",
        "root": str(docs),
        "glob": "*.org",
        "created": m.now(),
        "corpus_summary": "old org index",
        "files": [
            {
                "path": str(old_file),
                "source_fingerprint": m.source_fingerprint(old_file),
                "chunks": [],
            }
        ],
    }
    write_json(m.index_path(old_index["id"]), old_index)
    conv = m.new_conversation("Heavy index")
    conv["id"] = "heavy-index"
    conv["context_items"] = [m.context_item_from_index(old_index)]
    m.save_conversation(conv)

    new_index = dict(old_index)
    new_index["id"] = "new-index"
    new_index["created"] = m.now()
    new_index["files"] = [
        {
            "path": str(path),
            "source_fingerprint": m.source_fingerprint(path),
            "chunks": [],
        }
        for path in sorted(docs.glob("*.org"))
    ]

    old_build = m.build_document_index
    phases = []
    try:
        def fake_build(path, pattern, name=None, max_derived_bytes=None, progress_callback=None):
            if progress_callback is not None:
                progress_callback(
                    {
                        "status": "running",
                        "phase": "summarizing chunk",
                        "current_file_index": 1,
                        "total_files": 2,
                        "completed_chunks": 1,
                        "estimated_chunks": 2,
                        "percent": 50,
                        "eta_seconds": 12,
                    }
                )
            return new_index

        m.build_document_index = fake_build
        notes = m.refresh_heavy_attached_indexes(conv, phase_callback=phases.append)
    finally:
        m.build_document_index = old_build

    assert "bg-heavy: indexing(model)" in phases
    assert any("file 1/2" in phase for phase in phases)
    assert any("heavy index refreshed old-index -> new-index" in note for note in notes)
    assert conv["context_items"][0]["id"] == "new-index"


def main() -> int:
    m = load_motoko()
    with isolated_state():
        test_study_reuses_existing_dossier(m)
    with isolated_state():
        test_context_sufficiency_and_catalog(m)
    with isolated_state():
        test_context_plan_and_source_reasons(m)
    with isolated_state():
        test_background_study_state(m)
    with isolated_state():
        test_interrupted_background_study_resume_note(m)
    with isolated_state():
        test_heavy_index_refresh_replaces_attached_index(m)
    print("6 motoko evaluation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
