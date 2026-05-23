"""Derived-artifact lifecycle decisions for Motoko."""

from __future__ import annotations

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
