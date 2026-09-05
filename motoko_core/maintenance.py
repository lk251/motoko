"""Durable maintenance job state helpers for Motoko."""

from __future__ import annotations

import contextlib
import json
import pathlib
import uuid

from motoko_core.state import atomic_write
from motoko_core.text import now


def read_maintenance_state_file(path: pathlib.Path) -> dict | None:
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return state if isinstance(state, dict) else None


def write_maintenance_state_file(path: pathlib.Path, state: dict) -> None:
    state["updated"] = now()
    atomic_write(path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    path.chmod(0o600)


def clear_maintenance_state_file(path: pathlib.Path, job_id: str | None = None) -> None:
    state = read_maintenance_state_file(path)
    if job_id and state and state.get("job_id") != job_id:
        return
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


def maintenance_incomplete(state: dict | None) -> bool:
    if not state:
        return False
    return state.get("status") in {"running", "resuming", "deferred"}


def begin_maintenance_state_file(
    path: pathlib.Path,
    conv: dict,
    *,
    resumed: bool = False,
) -> dict:
    previous = read_maintenance_state_file(path)
    retry_count = 0
    if resumed and previous and previous.get("conversation_id") == conv.get("id"):
        retry_count = int(previous.get("retry_count", 0) or 0)
    state = {
        "job_id": "maint-" + uuid.uuid4().hex[:10],
        "kind": "auto-maintenance",
        "conversation_id": conv.get("id", ""),
        "conversation_title": conv.get("title", "Untitled"),
        "started": now(),
        "updated": now(),
        "phase": "memory: checking",
        "status": "resuming" if resumed else "running",
        "retry_count": retry_count,
    }
    write_maintenance_state_file(path, state)
    return state


def update_maintenance_state_file(
    path: pathlib.Path,
    state: dict,
    phase: str,
    *,
    status: str = "running",
    note: str | None = None,
    error: str | None = None,
) -> None:
    state["phase"] = phase
    state["status"] = status
    if note is not None:
        state["note"] = note
    if error is not None:
        state["error"] = error
    write_maintenance_state_file(path, state)


def resume_interrupted_maintenance_file(
    path: pathlib.Path,
    conv: dict,
    *,
    max_retries: int,
) -> tuple[bool, str | None]:
    state = read_maintenance_state_file(path)
    if not maintenance_incomplete(state):
        return False, None
    if state.get("conversation_id") != conv.get("id"):
        state["status"] = "abandoned"
        state["abandoned"] = now()
        state["abandoned_reason"] = "opened different conversation"
        write_maintenance_state_file(path, state)
        return False, None
    retry_count = int(state.get("retry_count", 0) or 0)
    if retry_count >= max_retries:
        state["status"] = "abandoned"
        state["abandoned"] = now()
        write_maintenance_state_file(path, state)
        return False, "abandoned interrupted maintenance after repeated retries"
    state["retry_count"] = retry_count + 1
    state["status"] = "resuming"
    state["phase"] = "memory: queued"
    write_maintenance_state_file(path, state)
    return True, "resuming interrupted memory maintenance"
