"""Derived-artifact lifecycle decisions for Motoko."""

from __future__ import annotations

import collections
from dataclasses import dataclass, field


ARTIFACT_LIFECYCLE_SCHEMA = "artifact-lifecycle-v1"


@dataclass(frozen=True)
class ArtifactCleanupDecision:
    artifact_id: str
    artifact_kind: str
    action: str
    reason: str
    blocked_by: tuple[str, ...] = field(default_factory=tuple)
    bytes_estimate: int = 0

    def to_dict(self) -> dict:
        return {
            "schema": ARTIFACT_LIFECYCLE_SCHEMA,
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind,
            "action": self.action,
            "reason": self.reason,
            "blocked_by": list(self.blocked_by),
            "bytes_estimate": self.bytes_estimate,
        }


def superseded_index_cleanup_decision(
    *,
    index_id: str,
    latest_id: str,
    stale: bool,
    latest_has_missing_artifacts: bool,
    bytes_estimate: int = 0,
) -> ArtifactCleanupDecision:
    if not index_id:
        return ArtifactCleanupDecision("", "index", "skip", "missing index id")
    if not stale:
        return ArtifactCleanupDecision(index_id, "index", "keep", "index is not stale", bytes_estimate=bytes_estimate)
    if latest_has_missing_artifacts:
        return ArtifactCleanupDecision(
            index_id,
            "index",
            "block",
            "latest index still has unresolved derived-artifact references",
            blocked_by=(latest_id,),
            bytes_estimate=bytes_estimate,
        )
    return ArtifactCleanupDecision(
        index_id,
        "index",
        "delete",
        f"stale index superseded by {latest_id}",
        bytes_estimate=bytes_estimate,
    )


def source_lifecycle_state(*, path: str, exists: bool, ignored: bool, fingerprint_changed: bool) -> dict:
    if ignored:
        status = "ignored"
        action = "detach-derived-artifacts"
    elif not exists:
        status = "deleted"
        action = "mark-stale-and-clean-derived-artifacts"
    elif fingerprint_changed:
        status = "changed"
        action = "reprocess-from-source"
    else:
        status = "fresh"
        action = "keep"
    return {
        "schema": ARTIFACT_LIFECYCLE_SCHEMA,
        "path": path,
        "status": status,
        "recommended_action": action,
    }


def source_lifecycle_artifact_plan(
    *,
    index_id: str,
    source_lifecycle: list[dict],
    dependent_counts: dict[str, int] | None = None,
) -> dict:
    rows = [row for row in source_lifecycle if isinstance(row, dict) and row.get("status") != "fresh"]
    counts = dict(collections.Counter(str(row.get("status", "unknown")) for row in rows))
    affected = [
        {"kind": kind, "count": int(count)}
        for kind, count in sorted((dependent_counts or {}).items())
        if int(count or 0) > 0
    ]
    if not rows:
        return {
            "schema": ARTIFACT_LIFECYCLE_SCHEMA,
            "index": index_id,
            "status": "fresh",
            "recommended_action": "keep-derived-artifacts",
            "source_counts": {},
            "affected_artifacts": affected,
        }
    if counts.get("changed") and (counts.get("deleted") or counts.get("ignored")):
        action = "rebuild-index-and-clean-detached-derived-artifacts"
    elif counts.get("changed"):
        action = "rebuild-index-and-refresh-derived-artifacts"
    else:
        action = "refresh-index-and-clean-detached-derived-artifacts"
    return {
        "schema": ARTIFACT_LIFECYCLE_SCHEMA,
        "index": index_id,
        "status": "needs-work",
        "recommended_action": action,
        "source_counts": counts,
        "source_count": len(rows),
        "affected_artifacts": affected,
    }
