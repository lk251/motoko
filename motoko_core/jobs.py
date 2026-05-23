"""Content-free job supervision primitives for Motoko live work."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable


JOB_SUPERVISOR_SCHEMA = "job-supervisor-v1"

JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_PAUSE_REQUESTED = "pause-requested"
JOB_STATUS_STOP_REQUESTED = "stop-requested"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"


@dataclass
class JobRecord:
    job_id: str
    kind: str
    lane: str
    label: str
    status: str = JOB_STATUS_PENDING
    created_monotonic: float = 0.0
    updated_monotonic: float = 0.0
    checkpoint: dict = field(default_factory=dict)
    progress: dict = field(default_factory=dict)
    error_type: str = ""
    cancel_event: threading.Event | None = None
    pause_event: threading.Event | None = None

    def content_free_snapshot(self, now_monotonic: float | None = None) -> dict:
        now_value = self.updated_monotonic if now_monotonic is None else now_monotonic
        return {
            "schema": JOB_SUPERVISOR_SCHEMA,
            "job_id": self.job_id,
            "kind": self.kind,
            "lane": self.lane,
            "label": self.label,
            "status": self.status,
            "age_seconds": max(0, int(now_value - self.created_monotonic)),
            "updated_seconds_ago": max(0, int(now_value - self.updated_monotonic)),
            "checkpoint": dict(self.checkpoint),
            "progress": dict(self.progress),
            "error_type": self.error_type,
            "stop_requested": bool(self.cancel_event and self.cancel_event.is_set()),
            "pause_requested": bool(self.pause_event and self.pause_event.is_set()),
        }


class JobSupervisor:
    """Small in-process job registry.

    It deliberately stores only labels, status, checkpoint metadata, and
    caller-provided progress dictionaries. Callers must not put prompts,
    retrieved source text, summaries, or private filenames in those fields.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.clock = clock or time.monotonic
        self.id_factory = id_factory or (lambda: uuid.uuid4().hex[:12])
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}

    def begin(
        self,
        *,
        kind: str,
        lane: str,
        label: str,
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        checkpoint: dict | None = None,
    ) -> JobRecord:
        now_value = self.clock()
        record = JobRecord(
            job_id=self.id_factory(),
            kind=str(kind),
            lane=str(lane),
            label=str(label),
            status=JOB_STATUS_RUNNING,
            created_monotonic=now_value,
            updated_monotonic=now_value,
            checkpoint=dict(checkpoint or {}),
            cancel_event=cancel_event or threading.Event(),
            pause_event=pause_event or threading.Event(),
        )
        with self._lock:
            self._jobs[record.job_id] = record
        return record

    def start_thread(
        self,
        *,
        kind: str,
        lane: str,
        label: str,
        target,
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        checkpoint: dict | None = None,
        daemon: bool = True,
    ) -> JobRecord:
        record = self.begin(
            kind=kind,
            lane=lane,
            label=label,
            cancel_event=cancel_event,
            pause_event=pause_event,
            checkpoint=checkpoint,
        )

        def runner() -> None:
            try:
                target()
            except BaseException as exc:
                self.finish(record.job_id, status=JOB_STATUS_FAILED, error_type=type(exc).__name__)
                raise
            else:
                self.finish(record.job_id, status=JOB_STATUS_COMPLETED)

        threading.Thread(target=runner, daemon=daemon).start()
        return record

    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: dict | None = None,
        checkpoint: dict | None = None,
    ) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return
            if status is not None:
                record.status = str(status)
            if progress is not None:
                record.progress = dict(progress)
            if checkpoint is not None:
                record.checkpoint = dict(checkpoint)
            record.updated_monotonic = self.clock()

    def finish(self, job_id: str, *, status: str, error_type: str = "") -> None:
        self.update(job_id, status=status)
        with self._lock:
            record = self._jobs.get(job_id)
            if record is not None:
                record.error_type = str(error_type or "")

    def request_stop(self, job_id: str) -> bool:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return False
            if record.cancel_event is not None:
                record.cancel_event.set()
            record.status = JOB_STATUS_STOP_REQUESTED
            record.updated_monotonic = self.clock()
            return True

    def request_pause(self, job_id: str) -> bool:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return False
            if record.pause_event is not None:
                record.pause_event.set()
            record.status = JOB_STATUS_PAUSE_REQUESTED
            record.updated_monotonic = self.clock()
            return True

    def request_stop_by_kind(self, kind: str) -> int:
        count = 0
        for snapshot in self.snapshots(include_done=False):
            if snapshot.get("kind") == kind and self.request_stop(str(snapshot.get("job_id", ""))):
                count += 1
        return count

    def active(self) -> list[JobRecord]:
        with self._lock:
            return [
                record
                for record in self._jobs.values()
                if record.status
                not in {
                    JOB_STATUS_COMPLETED,
                    JOB_STATUS_FAILED,
                }
            ]

    def snapshots(self, *, include_done: bool = True) -> list[dict]:
        now_value = self.clock()
        with self._lock:
            records = list(self._jobs.values())
        rows = []
        for record in records:
            if (
                not include_done
                and record.status
                in {
                    JOB_STATUS_COMPLETED,
                    JOB_STATUS_FAILED,
                }
            ):
                continue
            rows.append(record.content_free_snapshot(now_value))
        rows.sort(key=lambda row: (row.get("status") not in {JOB_STATUS_RUNNING, JOB_STATUS_PAUSE_REQUESTED}, row.get("job_id", "")))
        return rows


def format_job_snapshots(rows: list[dict], *, limit: int = 12) -> str:
    lines = [f"jobs: {JOB_SUPERVISOR_SCHEMA}"]
    if not rows:
        lines.append("active: none")
        return "\n".join(lines)
    for row in rows[:limit]:
        line = (
            f"- {row.get('job_id', '')} {row.get('kind', '')} "
            f"{row.get('lane', '')} {row.get('status', '')} "
            f"age={row.get('age_seconds', 0)}s"
        )
        label = str(row.get("label", "")).strip()
        if label:
            line += f" label={label}"
        lines.append(line)
    extra = len(rows) - limit
    if extra > 0:
        lines.append(f"... {extra} more job(s)")
    return "\n".join(lines)
