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


@contextlib.contextmanager
def temporary_env(updates: dict[str, str]):
    old_values = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


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
        "source_conversations": [{"id": conv["id"]}],
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


def test_retrieval_eval_scores_grounded_fixtures(m):
    report = m.run_retrieval_eval()
    text = m.format_retrieval_eval_report(report)
    assert report["status"] == "pass", text
    assert report["passed"] == report["total"]
    assert any(row["id"] == "named-logbook-recent" for row in report["fixtures"])
    assert "retrieval eval: pass" in text
    path = m.save_retrieval_eval_report(report)
    assert path.exists()


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


def test_background_study_enriches_legacy_index(m):
    docs = pathlib.Path(os.environ["MOTOKO_STATE_HOME"]).parent / "docs"
    docs.mkdir()
    (docs / "tasks.org").write_text("* TODO [#A] Background enrich task\n", encoding="utf-8")
    m.add_allowed_dir(str(docs))
    old_quiet_model = m.quiet_model
    try:
        m.quiet_model = lambda *args, **kwargs: "summary"
        index = m.build_document_index(str(docs))
    finally:
        m.quiet_model = old_quiet_model

    index.pop("signal_schema", None)
    index.pop("signals", None)
    index.pop("signal_summary", None)
    for file_item in index["files"]:
        file_item.pop("signals", None)
        for chunk in file_item["chunks"]:
            chunk.pop("signals", None)
    write_json(m.index_path(index["id"]), index)

    conv = m.new_conversation("Background enrich")
    conv["id"] = "background-enrich"
    notes = m.background_study_step(conv)
    enriched = m.load_index_exact(index["id"])
    assert any("index artifacts enriched" in note for note in notes)
    assert enriched["signal_schema"] == m.SIGNAL_SCHEMA_VERSION
    assert enriched["corpus_profile_schema"] == m.CORPUS_PROFILE_SCHEMA_VERSION
    assert "Background enrich task" in enriched["signal_summary"]
    assert "Background enrich task" in enriched["corpus_profile_text"]


def test_background_study_builds_evidence_store(m):
    docs = pathlib.Path(os.environ["MOTOKO_STATE_HOME"]).parent / "docs"
    docs.mkdir()
    source = docs / "logbook.org"
    content = (
        "* [2026-05-19 Tue 12:34]\n"
        "** do\n"
        "*** TODO Preserve evidence stores\n"
        "** log\n"
        "Evidence stores should be rebuilt deterministically in the CPU lane.\n"
    )
    source.write_text(content, encoding="utf-8")
    index = {
        "id": "evidence-bg-index",
        "name": "docs",
        "root": str(docs),
        "glob": "*.org",
        "created": m.now(),
        "files": [
            {
                "path": str(source),
                "source_fingerprint": m.source_fingerprint(source),
                "summary": "Logbook.",
                "chunks": [
                    {
                        "chunk": 1,
                        "summary": "Evidence store note.",
                        "content": content,
                        "content_sha256": m.sha256_hex(content.encode("utf-8")),
                        "content_bytes": len(content.encode("utf-8")),
                    }
                ],
            }
        ],
    }
    write_json(m.index_path(index["id"]), index)
    conv = m.new_conversation("Evidence background")
    conv["id"] = "evidence-background"
    with temporary_env({"MOTOKO_BACKGROUND_VECTOR_REFRESH": "0"}):
        phases = []
        notes = m.background_study_step(conv, phase_callback=phases.append)
    stores = m.list_evidence_stores()
    assert stores
    assert any("study: evidence-store" == phase for phase in phases)
    assert any("evidence store(s) refreshed" in note for note in notes)
    report = m.query_evidence_store(stores[0], "Preserve evidence stores")
    assert report["rows"]


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


def test_heavy_index_refresh_attaches_newer_completed_index(m):
    docs = pathlib.Path(os.environ["MOTOKO_STATE_HOME"]).parent / "docs"
    docs.mkdir()
    source = docs / "logbook.org"
    source.write_text("* TODO Current log entry\n", encoding="utf-8")
    m.add_allowed_dir(str(docs))

    old_index = {
        "id": "old-index",
        "name": "orgfiles",
        "root": str(docs),
        "glob": "*.org",
        "created": "2026-05-21T12:00:00+00:00",
        "corpus_summary": "old org index",
        "files": [
            {
                "path": str(source),
                "source_fingerprint": m.source_fingerprint(source),
                "chunks": [],
            }
        ],
    }
    new_index = dict(old_index)
    new_index["id"] = "new-index"
    new_index["created"] = "2026-05-21T13:00:00+00:00"
    new_index["corpus_summary"] = "new org index"
    write_json(m.index_path(old_index["id"]), old_index)
    write_json(m.index_path(new_index["id"]), new_index)

    conv = m.new_conversation("Heavy index")
    conv["id"] = "heavy-index"
    conv["context_items"] = [m.context_item_from_index(old_index)]
    m.save_conversation(conv)

    old_build = m.build_document_index
    try:
        def fail_build(*_args, **_kwargs):
            raise AssertionError("fresh newer index should be attached without rebuilding")

        m.build_document_index = fail_build
        notes = m.refresh_heavy_attached_indexes(conv)
    finally:
        m.build_document_index = old_build

    assert any("attached newer index old-index -> new-index" in note for note in notes)
    assert conv["context_items"][0]["id"] == "new-index"


def test_routed_index_quality_gate_preserves_org_evidence(m):
    docs = pathlib.Path(tempfile.mkdtemp()) / "docs"
    docs.mkdir()
    try:
        (docs / "tasks.org").write_text(
            "\n".join(
                [
                    "* TODO [#A] Prepare client filing :legal:urgent:",
                    "DEADLINE: <2026-05-20 Wed>",
                    "Obligation: send the signed packet to Alvarez before noon.",
                    "* TODO [#B] Draft support note",
                    "SCHEDULED: <2026-05-21 Thu>",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (docs / "reference.org").write_text("* Reference\nProject code name: violet harbor\n", encoding="utf-8")
        m.add_allowed_dir(str(docs))
        old_quiet_model = m.quiet_model
        routes = []
        try:
            def routed_summary(messages, **kwargs):
                routes.append(kwargs.get("route"))
                prompt = messages[-1]["content"]
                if "Prepare client filing" in prompt:
                    return "summary: Prepare client filing, deadline 2026-05-20, Alvarez packet, urgent legal task."
                if "violet harbor" in prompt:
                    return "summary: reference note for violet harbor."
                return "summary: corpus map preserving task priorities, deadlines, project names, and file paths."

            m.quiet_model = routed_summary
            index = m.build_document_index(str(docs))
        finally:
            m.quiet_model = old_quiet_model

        assert m.MODEL_ROUTE_INDEX_CHUNK in routes
        assert m.MODEL_ROUTE_INDEX_FILE in routes
        assert m.MODEL_ROUTE_INDEX_CORPUS in routes
        assert index["signals"]["priorities"]["A"] == 1
        assert index["signals"]["task_items"][0]["deadline_date"] == "2026-05-20"
        assert "Prepare client filing" in index["corpus_profile_text"]
        assert index["files"][0]["summary_artifact"]["artifact_schema"] == m.FILE_SUMMARY_SCHEMA_VERSION
        assert index["files"][0]["chunks"][0]["summary_artifact"]["source_fingerprint"]["sha256"]
        text, sources = m.retrieve_from_index(index, "highest priority legal tasks for 2026-05-20")
        assert "Prepare client filing" in text
        assert "2026-05-20" in text
        assert "tasks.org" in text
        assert any(source.get("kind") == "chunk" for source in sources)
        quality = m.index_quality_gate(index)
        assert quality["status"] == "pass", m.format_index_quality_gate(quality)
    finally:
        try:
            for path in sorted(docs.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            docs.rmdir()
        except OSError:
            pass


def test_worker_model_eval_scores_routes_and_json_artifacts(m):
    calls = []
    old_quiet_model = m.quiet_model
    try:
        def fake_worker(messages, **kwargs):
            route = kwargs.get("route")
            calls.append(route)
            prompt = messages[-1]["content"]
            if route == m.MODEL_ROUTE_INDEX_CHUNK:
                return json.dumps(
                    {
                        "summary": "TODO priority A send countersigned packet to Ana Alvarez for violet harbor.",
                        "title": "Alvarez packet deadline",
                        "kind": "org_task",
                        "dates": ["2026-05-21", "2026-05-22"],
                        "todos": ["TODO [#A] Send signed Alvarez packet"],
                        "obligations": ["email the countersigned packet before noon"],
                        "files_or_paths_mentioned": ["/home/mares/repos/orgfiles/legal.org"],
                        "confidence": 0.93,
                        "escalation_needed": False,
                    }
                )
            if route == m.MODEL_ROUTE_INDEX_FILE:
                return json.dumps(
                    {
                        "file_summary": "Planning file for tasks.org with the Alvarez packet as priority work.",
                        "file_title": "Tasks planning",
                        "file_role": "active planning task file",
                        "file_kind": "org",
                        "main_projects": ["violet harbor"],
                        "main_dates": ["2026-05-22"],
                        "main_todos": ["Send signed Alvarez packet", "Draft support note"],
                        "main_obligations": ["email Ana Alvarez before noon"],
                        "confidence": 0.91,
                        "escalation_needed": False,
                    }
                )
            if route == m.MODEL_ROUTE_INDEX_LABEL:
                assert "inbox.org" in prompt
                return json.dumps(
                    {
                        "label": "active client legal org task",
                        "kind": "org task notes",
                        "active": True,
                        "task_bearing": True,
                        "sensitive": "client legal",
                        "confidence": 0.88,
                        "escalation_needed": False,
                    }
                )
            if route == m.MODEL_ROUTE_INDEX_CORPUS:
                return json.dumps(
                    {
                        "corpus_summary": "Orgfiles corpus prioritizes the Alvarez packet before repo notes.",
                        "active_projects": ["violet harbor"],
                        "priority_items": ["Send signed Alvarez packet"],
                        "deadlines": ["2026-05-22"],
                        "scheduled_items": ["2026-05-21 morning"],
                        "obligations": ["email Ana Alvarez"],
                        "files_by_role": {"tasks": ["tasks.org"], "repo planning": ["nixos-configs.org"]},
                        "audit_needed": False,
                    }
                )
            raise AssertionError(f"unexpected route {route}")

        m.quiet_model = fake_worker
        with temporary_env(
            {
                "MOTOKO_ROUTE_INDEX_CHUNK_MODEL": "Qwen/Qwen3.5-2B",
                "MOTOKO_ROUTE_INDEX_FILE_MODEL": "Qwen/Qwen3-4B-Instruct-2507",
                "MOTOKO_ROUTE_INDEX_LABEL_MODEL": "mistralai/Ministral-3-3B-Instruct-2512",
                "MOTOKO_ROUTE_INDEX_CORPUS_MODEL": "Qwen/Qwen3.5-9B",
            }
        ):
            report = m.run_worker_model_eval(timeout=0.01)
            path = m.save_worker_model_eval_report(report)
            text = m.format_worker_model_eval_report(report)
        assert report["status"] == "pass", text
        assert report["passed"] == 4
        assert calls == [
            m.MODEL_ROUTE_INDEX_CHUNK,
            m.MODEL_ROUTE_INDEX_FILE,
            m.MODEL_ROUTE_INDEX_LABEL,
            m.MODEL_ROUTE_INDEX_CORPUS,
        ]
        assert report["route_summaries"][m.MODEL_ROUTE_INDEX_LABEL]["model"] == "mistralai/Ministral-3-3B-Instruct-2512"
        assert "worker model eval: pass" in text
        assert path.exists()
    finally:
        m.quiet_model = old_quiet_model


def test_worker_model_eval_flags_missing_facts(m):
    old_quiet_model = m.quiet_model
    try:
        m.quiet_model = lambda *args, **kwargs: json.dumps(
            {
                "summary": "A vague task note.",
                "title": "Task note",
                "kind": "org_task",
                "dates": [],
                "todos": [],
                "obligations": [],
                "files_or_paths_mentioned": [],
                "confidence": 0.2,
                "escalation_needed": True,
            }
        )
        report = m.run_worker_model_eval(routes=[m.MODEL_ROUTE_INDEX_CHUNK], timeout=0.01)
        assert report["status"] == "fail"
        row = report["fixtures"][0]
        assert row["json_valid"]
        assert "deadline" in row["missing_facts"]
        assert "person" in row["missing_facts"]
        assert "worker model eval: fail" in m.format_worker_model_eval_report(report)
    finally:
        m.quiet_model = old_quiet_model


def main() -> int:
    m = load_motoko()
    with isolated_state():
        test_study_reuses_existing_dossier(m)
    with isolated_state():
        test_context_sufficiency_and_catalog(m)
    with isolated_state():
        test_context_plan_and_source_reasons(m)
    with isolated_state():
        test_retrieval_eval_scores_grounded_fixtures(m)
    with isolated_state():
        test_background_study_state(m)
    with isolated_state():
        test_background_study_enriches_legacy_index(m)
    with isolated_state():
        test_background_study_builds_evidence_store(m)
    with isolated_state():
        test_interrupted_background_study_resume_note(m)
    with isolated_state():
        test_heavy_index_refresh_replaces_attached_index(m)
    with isolated_state():
        test_heavy_index_refresh_attaches_newer_completed_index(m)
    with isolated_state():
        test_routed_index_quality_gate_preserves_org_evidence(m)
    with isolated_state():
        test_worker_model_eval_scores_routes_and_json_artifacts(m)
    with isolated_state():
        test_worker_model_eval_flags_missing_facts(m)
    print("13 motoko evaluation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
