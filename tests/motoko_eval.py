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


def main() -> int:
    m = load_motoko()
    with isolated_state():
        test_study_reuses_existing_dossier(m)
    with isolated_state():
        test_context_sufficiency_and_catalog(m)
    with isolated_state():
        test_background_study_state(m)
    print("3 motoko evaluation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
