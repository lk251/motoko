"""Realm-local state paths and JSON file helpers for Motoko."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re


APP = "motoko"
LOCAL_MODELS_CONFIG = "local-models.json"


def state_root() -> pathlib.Path:
    root = os.environ.get("MOTOKO_STATE_HOME")
    if root:
        return pathlib.Path(root).expanduser()
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        return pathlib.Path(xdg_state).expanduser() / APP
    return pathlib.Path.home() / ".local" / "state" / APP


def config_root() -> pathlib.Path:
    root = os.environ.get("MOTOKO_CONFIG_HOME")
    if root:
        return pathlib.Path(root).expanduser()
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return pathlib.Path(xdg_config).expanduser() / APP
    return pathlib.Path.home() / ".config" / APP


def ensure_private_dir(path: pathlib.Path) -> pathlib.Path:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def _safe_component(value: str, fallback: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip("-") or fallback


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def conversations_dir() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return ensure_private_dir(root / "conversations")


def memories_path() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return root / "memories.jsonl"


def indexes_dir() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return ensure_private_dir(root / "indexes")


def topics_dir() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return ensure_private_dir(root / "topics")


def dossiers_dir() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return ensure_private_dir(root / "dossiers")


def allowdirs_path() -> pathlib.Path:
    root = ensure_private_dir(config_root())
    return root / "allowdirs"


def personality_path() -> pathlib.Path:
    root = ensure_private_dir(config_root())
    return root / "personality.md"


def config_path() -> pathlib.Path:
    root = ensure_private_dir(config_root())
    return root / "config.json"


def local_models_path() -> pathlib.Path:
    return config_root() / LOCAL_MODELS_CONFIG


def maintenance_path() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return root / "maintenance.json"


def profile_path() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return root / "profile.json"


def context_catalog_path() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return root / "context-catalog.json"


def study_state_path() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return root / "study-state.json"


def study_jobs_path() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return root / "study-jobs.jsonl"


def heavy_study_path() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return root / "heavy-study.json"


def work_pause_path() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return root / "pause-request.json"


def model_cache_dir() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return ensure_private_dir(root / "model-cache")


def model_evals_dir() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return ensure_private_dir(root / "model-evals")


def retrieval_evals_dir() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return ensure_private_dir(root / "retrieval-evals")


def retrieval_debug_dir() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return ensure_private_dir(root / "retrieval-debug")


def response_feedback_path() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return root / "response-feedback.jsonl"


def feedback_evals_dir() -> pathlib.Path:
    root = ensure_private_dir(state_root())
    return ensure_private_dir(root / "feedback-evals")


def feedback_eval_path(eval_id: str) -> pathlib.Path:
    return feedback_evals_dir() / f"{_safe_component(eval_id, 'feedback-eval')}.json"


def evidence_stores_dir() -> pathlib.Path:
    return state_root() / "evidence-stores"


def ensure_evidence_stores_dir() -> pathlib.Path:
    return ensure_private_dir(evidence_stores_dir())


def evidence_store_path(store_id: str) -> pathlib.Path:
    return ensure_evidence_stores_dir() / f"{_safe_component(store_id, 'evidence-store')}.json"


def vector_stores_dir() -> pathlib.Path:
    return state_root() / "vector-stores"


def ensure_vector_stores_dir() -> pathlib.Path:
    return ensure_private_dir(vector_stores_dir())


def vector_store_path(store_id: str) -> pathlib.Path:
    return ensure_vector_stores_dir() / f"{_safe_component(store_id, 'vector-store')}.json"


def vector_progress_dir() -> pathlib.Path:
    return state_root() / "vector-progress"


def ensure_vector_progress_dir() -> pathlib.Path:
    return ensure_private_dir(vector_progress_dir())


def vector_progress_path(progress_id: str) -> pathlib.Path:
    return ensure_vector_progress_dir() / f"{_safe_component(progress_id, 'vector-progress')}.json"


def conversation_path(conversation_id: str) -> pathlib.Path:
    return conversations_dir() / f"{conversation_id}.json"


def index_path(index_id: str) -> pathlib.Path:
    return indexes_dir() / f"{index_id}.json"


def topic_path(topic_id: str) -> pathlib.Path:
    return topics_dir() / f"{topic_id}.json"


def dossier_path(dossier_id: str) -> pathlib.Path:
    return dossiers_dir() / f"{dossier_id}.json"


def index_data_dir(index_id: str) -> pathlib.Path:
    return ensure_private_dir(indexes_dir() / f"{index_id}.chunks")


def index_progress_path(index_id: str) -> pathlib.Path:
    return indexes_dir() / f"{index_id}.progress.json"


def index_partial_path(index_id: str) -> pathlib.Path:
    return indexes_dir() / f"{index_id}.partial.json"


def model_cache_path(cache_key: str) -> pathlib.Path:
    safe = re.sub(r"[^a-f0-9]", "", cache_key.lower())
    if len(safe) < 8:
        safe = _sha256_hex(cache_key.encode("utf-8"))
    return ensure_private_dir(model_cache_dir() / safe[:2]) / f"{safe}.json"


def model_eval_path(eval_id: str) -> pathlib.Path:
    return model_evals_dir() / f"{_safe_component(eval_id, 'model-eval')}.json"


def retrieval_eval_path(eval_id: str) -> pathlib.Path:
    return retrieval_evals_dir() / f"{_safe_component(eval_id, 'retrieval-eval')}.json"


def retrieval_debug_path(debug_id: str) -> pathlib.Path:
    return retrieval_debug_dir() / f"{_safe_component(debug_id, 'retrieval-debug')}.json"


def atomic_write(path: pathlib.Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)


def safe_load_json(path: pathlib.Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def append_jsonl(path: pathlib.Path, row: dict) -> None:
    ensure_private_dir(path.parent)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    path.chmod(0o600)


def read_jsonl(path: pathlib.Path, *, limit: int | None = None) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        return []
    if limit is not None and limit >= 0:
        return rows[-limit:]
    return rows
