"""Derived-artifact lifecycle decisions for Motoko."""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Callable


ARTIFACT_LIFECYCLE_SCHEMA = "artifact-lifecycle-v1"
SOURCE_LIFECYCLE_PLAN_SCHEMA = "source-lifecycle-plan-v1"


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


def source_lifecycle_cleanup_plan(
    *,
    index_id: str,
    source_lifecycle: list[dict],
    artifact_records: list[dict] | None = None,
    replacement_index_id: str = "",
    replacement_ready: bool = False,
) -> dict:
    rows = [row for row in source_lifecycle if isinstance(row, dict) and row.get("status") != "fresh"]
    counts = dict(collections.Counter(str(row.get("status", "unknown")) for row in rows))
    records = [record for record in artifact_records or [] if isinstance(record, dict)]
    policy_counts: dict[tuple[str, str], dict] = {}
    bytes_by_policy: dict[str, int] = collections.Counter()
    for record in records:
        kind = str(record.get("artifact_kind", "artifact") or "artifact")
        policy = str(record.get("cleanup_policy", "manual-review") or "manual-review")
        key = (kind, policy)
        item = policy_counts.setdefault(
            key,
            {
                "kind": kind,
                "policy": policy,
                "count": 0,
                "bytes": 0,
            },
        )
        item["count"] += 1
        item["bytes"] += int(record.get("bytes_estimate", 0) or 0)
        bytes_by_policy[policy] += int(record.get("bytes_estimate", 0) or 0)

    affected_artifacts = sorted(policy_counts.values(), key=lambda item: (item["policy"], item["kind"]))
    derived_records = [record for record in records if record.get("cleanup_policy") == "delete-derived"]
    manual_records = [record for record in records if record.get("cleanup_policy") != "delete-derived"]

    if not rows:
        status = "fresh"
        recommended_action = "keep-derived-artifacts"
        apply_status = "no-op"
        apply_reason = "all indexed sources are fresh"
    elif counts.get("changed"):
        status = "needs-rebuild"
        recommended_action = "rebuild-index-and-refresh-derived-artifacts"
        apply_status = "blocked"
        apply_reason = "changed sources require source reprocessing before cleanup"
    elif not replacement_ready:
        status = "detached-source-work"
        recommended_action = "rebuild-index-before-cleanup"
        apply_status = "blocked"
        apply_reason = "source lifecycle cleanup requires a newer replacement index without the detached sources"
    else:
        status = "cleanup-ready"
        recommended_action = "clean-superseded-derived-artifacts"
        apply_status = "ready"
        apply_reason = f"superseded by replacement index {replacement_index_id}"

    return {
        "schema": SOURCE_LIFECYCLE_PLAN_SCHEMA,
        "index": index_id,
        "status": status,
        "recommended_action": recommended_action,
        "apply_status": apply_status,
        "apply_reason": apply_reason,
        "replacement_index": replacement_index_id,
        "replacement_ready": bool(replacement_ready),
        "source_counts": counts,
        "source_count": len(rows),
        "affected_artifacts": affected_artifacts,
        "affected_artifact_count": len(records),
        "derived_artifact_count": len(derived_records),
        "manual_review_artifact_count": len(manual_records),
        "derived_bytes": int(bytes_by_policy.get("delete-derived", 0)),
        "manual_review_bytes": sum(
            value for policy, value in bytes_by_policy.items() if policy != "delete-derived"
        ),
    }


def cleanup_superseded_index_candidates(
    candidates: list[dict],
    *,
    schema: str,
    created: str,
    limit: int = 1,
    dry_run: bool = False,
    load_latest: Callable[[str], dict],
    materialize_latest: Callable[[dict], dict],
    latest_missing_artifacts: Callable[[dict], list[str]],
    delete_snapshot: Callable[[dict], dict],
    invalidate_catalog: Callable[[], None] | None = None,
) -> dict:
    """Apply lifecycle decisions for stale superseded index candidates.

    Filesystem authority stays with injected callbacks from the Motoko facade.
    This function owns the cleanup decision flow and report shape.
    """

    limit = max(0, int(limit or 0))
    selected = candidates if limit == 0 else candidates[:limit]
    latest_ids = {str(row.get("latest", {}).get("id", "")) for row in selected}
    materialized = []
    if not dry_run:
        for latest_id in sorted(latest_ids):
            if not latest_id:
                continue
            try:
                latest = load_latest(latest_id)
            except (Exception, SystemExit):
                continue
            item = materialize_latest(latest)
            if item.get("changed") or item.get("missing_chunks"):
                materialized.append(item)
    deleted = []
    blocked = []
    for row in selected:
        index = row.get("index", {})
        index_id = str(index.get("id", ""))
        latest_id = str(row.get("latest", {}).get("id", ""))
        if dry_run:
            decision = superseded_index_cleanup_decision(
                index_id=index_id,
                latest_id=latest_id,
                stale=True,
                latest_has_missing_artifacts=False,
                bytes_estimate=int(row.get("bytes", 0) or 0),
            )
            deleted.append(
                {
                    "index": index_id,
                    "latest": latest_id,
                    "status": "candidate",
                    "bytes": row.get("bytes", 0),
                    "warnings": row.get("warnings", [])[:4],
                    "lifecycle": decision.to_dict(),
                }
            )
            continue
        try:
            latest = load_latest(latest_id)
        except (Exception, SystemExit) as exc:
            blocked.append({"index": index_id, "reason": f"latest index unavailable: {exc}"})
            continue
        missing = latest_missing_artifacts(latest)
        decision = superseded_index_cleanup_decision(
            index_id=index_id,
            latest_id=latest_id,
            stale=True,
            latest_has_missing_artifacts=bool(missing),
            bytes_estimate=int(row.get("bytes", 0) or 0),
        )
        if missing:
            blocked.append(
                {
                    "index": index_id,
                    "latest": latest_id,
                    "reason": "latest index still has unresolved stored chunk references",
                    "warnings": missing[:4],
                    "lifecycle": decision.to_dict(),
                }
            )
            continue
        deleted_item = delete_snapshot(index)
        deleted_item["lifecycle"] = decision.to_dict()
        deleted.append(deleted_item)
    if not dry_run and deleted and invalidate_catalog is not None:
        invalidate_catalog()
    return {
        "schema": schema,
        "created": created,
        "dry_run": dry_run,
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "materialized": materialized,
        "deleted": deleted,
        "blocked": blocked,
    }
