"""Derived-artifact lifecycle decisions for Motoko."""

from __future__ import annotations

import collections
import contextlib
import json
import pathlib
from dataclasses import dataclass, field
from typing import Callable

from motoko_core.corpus_selection import motoko_ignore_matches
from motoko_core.text import human_bytes


ARTIFACT_LIFECYCLE_SCHEMA = "artifact-lifecycle-v1"
INDEX_CLEANUP_SCHEMA = "index-cleanup-v1"
SOURCE_LIFECYCLE_PLAN_SCHEMA = "source-lifecycle-plan-v1"
SOURCE_LIFECYCLE_REPORT_SCHEMA = "source-lifecycle-report-v1"


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


def json_references_index(value, index_id: str) -> bool:
    if not index_id:
        return False
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "index",
                "index_id",
                "source_index",
                "source_index_id",
                "created_by_index_id",
                "source_fingerprint_index",
            }:
                if str(item) == index_id:
                    return True
                if isinstance(item, dict) and str(item.get("id", "")) == index_id:
                    return True
            if key in {"indexes", "index_ids", "source_indexes", "source_index_ids"} and isinstance(item, list):
                if any(
                    str(row) == index_id
                    or (isinstance(row, dict) and str(row.get("id", "")) == index_id)
                    for row in item
                ):
                    return True
            if key == "context_items" and isinstance(item, list):
                if any(
                    isinstance(row, dict)
                    and row.get("kind") == "index"
                    and str(row.get("id", "")) == index_id
                    for row in item
                ):
                    return True
            if json_references_index(item, index_id):
                return True
        return False
    if isinstance(value, list):
        return any(json_references_index(item, index_id) for item in value)
    return False


def json_matching_source_paths(value, source_paths: set[str]) -> set[str]:
    matches: set[str] = set()
    if not source_paths:
        return matches
    if isinstance(value, dict):
        for item in value.values():
            matches.update(json_matching_source_paths(item, source_paths))
        return matches
    if isinstance(value, list):
        for item in value:
            matches.update(json_matching_source_paths(item, source_paths))
        return matches
    if isinstance(value, str):
        for source_path in source_paths:
            if source_path and (value == source_path or source_path in value):
                matches.add(source_path)
    return matches


def json_paths_referencing_index(
    directory: str | pathlib.Path,
    index_id: str,
    *,
    load_json: Callable[[pathlib.Path], object | None],
) -> list[pathlib.Path]:
    """Return JSON artifact paths that reference an index id."""

    root = pathlib.Path(directory)
    rows: list[pathlib.Path] = []
    if not root.exists():
        return rows
    for path in sorted(root.glob("*.json")):
        data = load_json(path)
        if data is not None and json_references_index(data, index_id):
            rows.append(path)
    return rows


def delete_json_artifacts_referencing_index(
    directory: str | pathlib.Path,
    index_id: str,
    *,
    load_json: Callable[[pathlib.Path], object | None],
    unlink_path: Callable[[pathlib.Path], None],
) -> int:
    """Delete JSON artifact files in a directory that reference an index id."""

    removed = 0
    for path in json_paths_referencing_index(directory, index_id, load_json=load_json):
        try:
            unlink_path(path)
        except FileNotFoundError:
            continue
        removed += 1
    return removed


def index_artifact_dependency_counts(
    index_id: str,
    artifact_targets: list[dict],
    *,
    load_json: Callable[[pathlib.Path], object | None],
) -> dict[str, int]:
    """Count JSON artifact families that reference an index id."""

    if not index_id:
        return {}
    counts: dict[str, int] = {}
    for target in artifact_targets:
        kind = str(target.get("artifact_kind", "")).strip()
        path = target.get("path", "")
        if not kind or not path:
            continue
        counts[kind] = len(json_paths_referencing_index(path, index_id, load_json=load_json))
    return counts


def source_lifecycle_affected_paths(source_lifecycle: list[dict]) -> set[str]:
    paths = set()
    for item in source_lifecycle:
        if not isinstance(item, dict) or item.get("status") == "fresh":
            continue
        path_text = str(item.get("path", "")).strip()
        if not path_text:
            continue
        paths.add(path_text)
        try:
            paths.add(str(pathlib.Path(path_text).expanduser().resolve()))
        except OSError:
            paths.add(str(pathlib.Path(path_text).expanduser()))
    return paths


def index_file_path_keys(index: dict) -> set[str]:
    """Return normalized path keys for files recorded in an index."""

    keys: set[str] = set()
    for file_item in index.get("files", []):
        path_text = str(file_item.get("path", "")).strip()
        if not path_text:
            continue
        keys.add(path_text)
        try:
            keys.add(str(pathlib.Path(path_text).expanduser().resolve()))
        except OSError:
            keys.add(str(pathlib.Path(path_text).expanduser()))
    return keys


def _path_key(path: pathlib.Path) -> str:
    try:
        return str(path.expanduser().resolve())
    except OSError:
        return str(path.expanduser())


def index_source_lifecycle_scan(
    index: dict,
    *,
    current_paths: set[str],
    root: str | pathlib.Path,
    ignore_rules: list[dict] | None = None,
    file_status: Callable[[dict], str] | None = None,
    path_exists: Callable[[pathlib.Path], bool] | None = None,
) -> dict:
    """Classify indexed source files against current corpus selection.

    The caller supplies the current candidate path set and the file staleness
    callback; this service owns the source lifecycle policy and summary shape.
    """

    current = set(current_paths or set())
    rules = ignore_rules or []
    root_path = pathlib.Path(root).expanduser()
    try:
        root_path = root_path.resolve()
    except OSError:
        pass
    exists_fn = path_exists or (lambda path: path.exists())
    status_fn = file_status or (lambda _file_item: "fresh")
    known_paths: set[str] = set()
    source_lifecycle: list[dict] = []
    for file_item in index.get("files", []):
        path_text = str(file_item.get("path", "")).strip()
        if not path_text:
            continue
        path = pathlib.Path(path_text).expanduser()
        resolved = _path_key(path)
        known_paths.add(resolved)
        exists = bool(exists_fn(path))
        ignored = exists and resolved not in current
        if exists and rules:
            with contextlib.suppress(OSError, ValueError):
                rel = pathlib.Path(resolved).relative_to(root_path).as_posix()
                ignored = ignored or motoko_ignore_matches(rules, rel, is_dir=False) is not None
        source_status = status_fn(file_item)
        lifecycle = source_lifecycle_state(
            path=path_text,
            exists=exists,
            ignored=ignored,
            fingerprint_changed=source_status == "stale" and exists and not ignored,
        )
        if lifecycle.get("status") != "fresh":
            source_lifecycle.append(lifecycle)
    lifecycle_counts = dict(collections.Counter(item.get("status", "unknown") for item in source_lifecycle))
    return {
        "known_paths": sorted(known_paths),
        "missing_paths": sorted(path_text for path_text in known_paths if path_text not in current),
        "covered_files": len(known_paths & current),
        "source_lifecycle": source_lifecycle,
        "source_lifecycle_counts": lifecycle_counts,
    }


def source_artifact_record(
    *,
    artifact_id: str,
    artifact_kind: str,
    state_path: str | pathlib.Path,
    cleanup_policy: str,
    source_index_ids: list[str] | None = None,
    source_paths: list[str] | None = None,
    row_count: int = 0,
    bytes_estimate: int = 0,
) -> dict:
    return {
        "artifact_id": artifact_id,
        "artifact_kind": artifact_kind,
        "state_path": str(state_path),
        "cleanup_policy": cleanup_policy,
        "source_index_ids": source_index_ids or [],
        "source_paths": source_paths or [],
        "row_count": row_count,
        "bytes_estimate": int(bytes_estimate or 0),
    }


def _path_size(path: pathlib.Path, path_size: Callable[[pathlib.Path], int] | None) -> int:
    if path_size is None:
        return 0
    try:
        return int(path_size(path) or 0)
    except OSError:
        return 0


def _tree_size(path: pathlib.Path, tree_size: Callable[[pathlib.Path], int] | None) -> int:
    if tree_size is None:
        return 0
    try:
        return int(tree_size(path) or 0)
    except OSError:
        return 0


def delete_index_snapshot_artifacts(
    index: dict,
    *,
    index_path: str | pathlib.Path,
    progress_path: str | pathlib.Path,
    partial_path: str | pathlib.Path,
    chunk_dir: str | pathlib.Path,
    json_artifact_dirs: list[dict],
    load_json: Callable[[pathlib.Path], object | None],
    unlink_path: Callable[[pathlib.Path], None],
    remove_tree: Callable[[pathlib.Path], None],
    path_size: Callable[[pathlib.Path], int] | None = None,
    tree_size: Callable[[pathlib.Path], int] | None = None,
) -> dict:
    """Delete a superseded index snapshot and derived JSON artifacts.

    Callers provide concrete paths and filesystem callbacks; this service owns
    the lifecycle report shape and the family-wise deletion loop.
    """

    index_id = str(index.get("id", "")).strip()
    index_path = pathlib.Path(index_path)
    progress_path = pathlib.Path(progress_path)
    partial_path = pathlib.Path(partial_path)
    chunk_dir = pathlib.Path(chunk_dir)
    report = {
        "index": index_id,
        "index_deleted": False,
        "chunk_dir_deleted": False,
        "progress_deleted": False,
        "partial_deleted": False,
        "bytes": _path_size(index_path, path_size) + _tree_size(chunk_dir, tree_size),
    }
    for target in json_artifact_dirs:
        report_key = str(target.get("report_key", "")).strip()
        if report_key:
            report[report_key] = 0
    if not index_id:
        return report

    for key, path in [
        ("index_deleted", index_path),
        ("progress_deleted", progress_path),
        ("partial_deleted", partial_path),
    ]:
        try:
            unlink_path(path)
        except FileNotFoundError:
            continue
        report[key] = True

    if chunk_dir.exists():
        remove_tree(chunk_dir)
        report["chunk_dir_deleted"] = True

    for target in json_artifact_dirs:
        report_key = str(target.get("report_key", "")).strip()
        path = target.get("path", "")
        if not report_key or not path:
            continue
        report[report_key] = delete_json_artifacts_referencing_index(
            path,
            index_id,
            load_json=load_json,
            unlink_path=unlink_path,
        )
    return report


def json_artifact_records_for_source_lifecycle(
    directory: str | pathlib.Path,
    *,
    artifact_kind: str,
    cleanup_policy: str,
    index_id: str,
    source_paths: set[str],
    load_json: Callable[[pathlib.Path], object | None],
    path_size: Callable[[pathlib.Path], int] | None = None,
) -> list[dict]:
    """Collect lifecycle records from JSON artifacts in one state directory."""

    root = pathlib.Path(directory)
    records: list[dict] = []
    if not root.exists():
        return records
    for path in sorted(root.glob("*.json")):
        data = load_json(path)
        if data is None:
            continue
        references_index = json_references_index(data, index_id)
        matched_paths = sorted(json_matching_source_paths(data, source_paths))
        if not references_index and not matched_paths:
            continue
        records.append(
            source_artifact_record(
                artifact_id=str(data.get("id", path.stem)) if isinstance(data, dict) else path.stem,
                artifact_kind=artifact_kind,
                state_path=path,
                cleanup_policy=cleanup_policy,
                source_index_ids=[index_id] if references_index else [],
                source_paths=matched_paths,
                bytes_estimate=_path_size(path, path_size),
            )
        )
    return records


def json_file_artifact_record_for_source_lifecycle(
    path: str | pathlib.Path,
    *,
    artifact_id: str,
    artifact_kind: str,
    cleanup_policy: str,
    index_id: str,
    source_paths: set[str],
    load_json: Callable[[pathlib.Path], object | None],
    path_size: Callable[[pathlib.Path], int] | None = None,
) -> dict | None:
    """Collect one lifecycle record from a single JSON state file."""

    state_path = pathlib.Path(path)
    if not state_path.exists():
        return None
    data = load_json(state_path)
    if data is None:
        return None
    references_index = json_references_index(data, index_id)
    matched_paths = sorted(json_matching_source_paths(data, source_paths))
    if not references_index and not matched_paths:
        return None
    return source_artifact_record(
        artifact_id=artifact_id,
        artifact_kind=artifact_kind,
        state_path=state_path,
        cleanup_policy=cleanup_policy,
        source_index_ids=[index_id] if references_index else [],
        source_paths=matched_paths,
        bytes_estimate=_path_size(state_path, path_size),
    )


def jsonl_artifact_record_for_source_lifecycle(
    path: str | pathlib.Path,
    *,
    artifact_kind: str,
    cleanup_policy: str,
    index_id: str,
    source_paths: set[str],
    path_size: Callable[[pathlib.Path], int] | None = None,
) -> dict | None:
    """Collect one lifecycle record from a JSONL artifact ledger."""

    state_path = pathlib.Path(path)
    if not state_path.exists():
        return None
    row_count = 0
    references_index = False
    matched_paths: set[str] = set()
    try:
        with state_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                row_index = json_references_index(row, index_id)
                row_paths = json_matching_source_paths(row, source_paths)
                if row_index or row_paths:
                    row_count += 1
                    references_index = references_index or row_index
                    matched_paths.update(row_paths)
    except OSError:
        return None
    if not row_count:
        return None
    return source_artifact_record(
        artifact_id=state_path.stem,
        artifact_kind=artifact_kind,
        state_path=state_path,
        cleanup_policy=cleanup_policy,
        source_index_ids=[index_id] if references_index else [],
        source_paths=sorted(matched_paths),
        row_count=row_count,
        bytes_estimate=_path_size(state_path, path_size),
    )


def collect_source_lifecycle_artifact_records(
    *,
    index_id: str,
    source_paths: set[str],
    load_json: Callable[[pathlib.Path], object | None],
    path_size: Callable[[pathlib.Path], int] | None = None,
    json_dirs: list[dict] | None = None,
    jsonl_files: list[dict] | None = None,
    json_files: list[dict] | None = None,
) -> list[dict]:
    """Collect normalized lifecycle records from known artifact families.

    The Motoko facade supplies explicit state paths and filesystem callbacks;
    this service owns the matching, policy normalization, and stable sorting.
    """

    records: list[dict] = []
    for target in json_dirs or []:
        records.extend(
            json_artifact_records_for_source_lifecycle(
                target.get("path", ""),
                artifact_kind=str(target.get("artifact_kind", "")),
                cleanup_policy=str(target.get("cleanup_policy", "manual-review")),
                index_id=index_id,
                source_paths=source_paths,
                load_json=load_json,
                path_size=path_size,
            )
        )
    for target in jsonl_files or []:
        record = jsonl_artifact_record_for_source_lifecycle(
            target.get("path", ""),
            artifact_kind=str(target.get("artifact_kind", "")),
            cleanup_policy=str(target.get("cleanup_policy", "manual-review")),
            index_id=index_id,
            source_paths=source_paths,
            path_size=path_size,
        )
        if record is not None:
            records.append(record)
    for target in json_files or []:
        artifact_kind = str(target.get("artifact_kind", ""))
        record = json_file_artifact_record_for_source_lifecycle(
            target.get("path", ""),
            artifact_id=str(target.get("artifact_id") or artifact_kind),
            artifact_kind=artifact_kind,
            cleanup_policy=str(target.get("cleanup_policy", "manual-review")),
            index_id=index_id,
            source_paths=source_paths,
            load_json=load_json,
            path_size=path_size,
        )
        if record is not None:
            records.append(record)
    records.sort(
        key=lambda item: (
            item.get("cleanup_policy", ""),
            item.get("artifact_kind", ""),
            item.get("artifact_id", ""),
        )
    )
    return records


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


def source_lifecycle_report(
    *,
    index: dict,
    summary: dict,
    artifact_records: list[dict] | None,
    replacement_index: dict | None = None,
    replacement_ready: bool = False,
    replacement_reason: str = "",
    created: str = "",
    default_glob: str = "**/*",
    apply: bool = False,
    yes: bool = False,
    delete_snapshot: Callable[[dict], dict] | None = None,
    invalidate_catalog: Callable[[], None] | None = None,
    check_cancelled: Callable[[], None] | None = None,
) -> dict:
    """Build and optionally apply a source lifecycle cleanup report.

    Filesystem discovery and mutation stay behind injected callbacks. This
    function owns the report shape and the ready/blocked/apply decision flow.
    """

    index_id = str(index.get("id", "")).strip()
    if check_cancelled is not None:
        check_cancelled()
    source_lifecycle = [
        row for row in summary.get("source_lifecycle", []) or [] if isinstance(row, dict)
    ]
    replacement_id = str((replacement_index or {}).get("id", ""))
    plan = source_lifecycle_cleanup_plan(
        index_id=index_id,
        source_lifecycle=source_lifecycle,
        artifact_records=artifact_records or [],
        replacement_index_id=replacement_id,
        replacement_ready=replacement_ready,
    )
    report = {
        "schema": SOURCE_LIFECYCLE_REPORT_SCHEMA,
        "created": created,
        "index": {
            "id": index_id,
            "name": index.get("name", ""),
            "root": index.get("root", ""),
            "glob": index.get("glob") or default_glob,
            "status": summary.get("status", ""),
            "warnings": summary.get("warnings", [])[:6],
        },
        "replacement": {
            "id": replacement_id,
            "ready": bool(replacement_ready),
            "reason": replacement_reason,
        },
        "dry_run": not apply,
        "source_lifecycle": source_lifecycle[:100],
        "plan": plan,
        "artifact_records": (artifact_records or [])[:200],
        "artifact_record_count": len(artifact_records or []),
        "applied": None,
    }
    if not apply:
        return report
    if check_cancelled is not None:
        check_cancelled()
    if not yes:
        raise SystemExit("refusing source lifecycle cleanup without --yes")
    if plan.get("apply_status") != "ready":
        report["applied"] = {
            "status": "blocked",
            "reason": plan.get("apply_reason", "cleanup is not ready"),
        }
        return report
    if delete_snapshot is None:
        report["applied"] = {
            "status": "blocked",
            "reason": "source lifecycle cleanup has no deletion callback",
        }
        return report
    if check_cancelled is not None:
        check_cancelled()
    deletion = delete_snapshot(index)
    if check_cancelled is not None:
        check_cancelled()
    if invalidate_catalog is not None:
        invalidate_catalog()
    report["applied"] = {
        "status": "deleted-superseded-index-snapshot",
        "index": index_id,
        "deleted": deletion,
        "manual_review_artifacts_preserved": plan.get("manual_review_artifact_count", 0),
    }
    return report


def format_source_lifecycle_report(report: dict) -> str:
    index = report.get("index", {})
    replacement = report.get("replacement", {})
    plan = report.get("plan", {})
    lines = [
        f"source lifecycle: {report.get('schema', SOURCE_LIFECYCLE_REPORT_SCHEMA)}",
        f"created: {report.get('created', '')}",
        f"mode: {'dry-run' if report.get('dry_run') else 'apply'}",
        f"index: {index.get('id', '')} {index.get('name', '')} {index.get('root', '')}".rstrip(),
        f"index status: {index.get('status', '')}",
        f"replacement: {replacement.get('id') or '-'} ({'ready' if replacement.get('ready') else 'not ready'})",
        f"replacement reason: {replacement.get('reason', '')}",
        f"plan: {plan.get('status', '')} -> {plan.get('recommended_action', '')}",
        f"apply: {plan.get('apply_status', '')} ({plan.get('apply_reason', '')})",
    ]
    source_counts = plan.get("source_counts") or {}
    if source_counts:
        lines.append("sources: " + ", ".join(f"{key}:{source_counts[key]}" for key in sorted(source_counts)))
    else:
        lines.append("sources: fresh")
    for source in report.get("source_lifecycle", [])[:20]:
        lines.append(
            f"- {source.get('status', '')}: {source.get('path', '')} "
            f"({source.get('recommended_action', '')})"
        )
    if plan.get("affected_artifacts"):
        lines.append("affected artifacts:")
        for item in plan.get("affected_artifacts", []):
            bytes_part = f", {human_bytes(item.get('bytes', 0))}" if item.get("bytes") else ""
            lines.append(
                f"- {item.get('kind', '')}: {item.get('count', 0)} "
                f"policy={item.get('policy', '')}{bytes_part}"
            )
    else:
        lines.append("affected artifacts: none")
    manual = plan.get("manual_review_artifact_count", 0)
    if manual:
        lines.append(
            f"manual review: {manual} durable artifact(s) may mention these sources; "
            "Motoko will not delete memories, conversations, profile, raw feedback, "
            "action ledgers, or goal-loop records automatically."
        )
    applied = report.get("applied")
    if applied:
        lines.append(f"applied: {applied.get('status', '')}")
        if applied.get("reason"):
            lines.append(f"reason: {applied.get('reason')}")
        deleted = applied.get("deleted") or {}
        if deleted:
            extras = []
            for key, label in [
                ("vector_stores_deleted", "vector"),
                ("evidence_stores_deleted", "evidence"),
                ("topics_deleted", "topics"),
                ("dossiers_deleted", "dossiers"),
                ("retrieval_debug_deleted", "retrieval-debug"),
                ("retrieval_evals_deleted", "retrieval-evals"),
                ("feedback_evals_deleted", "feedback-evals"),
                ("action_evals_deleted", "action-evals"),
                ("model_evals_deleted", "model-evals"),
            ]:
                if deleted.get(key):
                    extras.append(f"{label}:{deleted.get(key)}")
            lines.append(
                "deleted: "
                f"index={deleted.get('index_deleted')} chunks={deleted.get('chunk_dir_deleted')} "
                + (", ".join(extras) if extras else "derived=0")
            )
    elif plan.get("apply_status") == "ready" and report.get("dry_run"):
        lines.append("next: run motoko source-lifecycle INDEX --apply --yes after reviewing this report")
    elif plan.get("apply_status") == "blocked":
        lines.append("next: rebuild/refresh the corpus first, then rerun source-lifecycle")
    return "\n".join(lines)


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
    check_cancelled: Callable[[], None] | None = None,
) -> dict:
    """Apply lifecycle decisions for stale superseded index candidates.

    Filesystem authority stays with injected callbacks from the Motoko facade.
    This function owns the cleanup decision flow and report shape.
    """

    limit = max(0, int(limit or 0))
    selected = candidates if limit == 0 else candidates[:limit]
    latest_ids = {str(row.get("latest", {}).get("id", "")) for row in selected}
    materialized = []
    if check_cancelled is not None:
        check_cancelled()
    if not dry_run:
        for latest_id in sorted(latest_ids):
            if check_cancelled is not None:
                check_cancelled()
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
        if check_cancelled is not None:
            check_cancelled()
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
        if check_cancelled is not None:
            check_cancelled()
        deleted_item = delete_snapshot(index)
        if check_cancelled is not None:
            check_cancelled()
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


def superseded_stale_index_candidates(
    indexes: list[dict],
    *,
    family_key: Callable[[dict], str],
    index_sort_key: Callable[[dict], tuple],
    staleness: Callable[[dict], tuple[str, list[str]]],
    bytes_estimate: Callable[[dict], int],
) -> list[dict]:
    """Select stale index snapshots superseded by a newer same-family index."""

    latest_by_key: dict[str, dict] = {}
    for index in indexes:
        key = family_key(index)
        current = latest_by_key.get(key)
        if current is None or index_sort_key(index) > index_sort_key(current):
            latest_by_key[key] = index
    candidates = []
    for index in indexes:
        index_id = str(index.get("id", "")).strip()
        latest = latest_by_key.get(family_key(index))
        if not index_id or latest is None or latest.get("id") == index_id:
            continue
        status, warnings = staleness(index)
        if status != "stale":
            continue
        candidates.append(
            {
                "index": index,
                "latest": latest,
                "status": status,
                "warnings": warnings,
                "bytes": int(bytes_estimate(index) or 0),
            }
        )
    candidates.sort(key=lambda row: index_sort_key(row.get("index", {})))
    return candidates


def format_index_cleanup_report(report: dict) -> str:
    lines = [
        f"index cleanup: {report.get('schema', INDEX_CLEANUP_SCHEMA)}",
        f"created: {report.get('created', '')}",
        f"mode: {'dry-run' if report.get('dry_run') else 'apply'}",
        f"candidates: {report.get('candidate_count', 0)} selected: {report.get('selected_count', 0)}",
    ]
    for item in report.get("materialized", []):
        lines.append(
            f"- materialized latest {item.get('index', '')}: "
            f"{item.get('materialized_chunks', 0)} chunk(s), {human_bytes(item.get('materialized_bytes', 0))}"
        )
        if item.get("missing_chunks"):
            lines.append(f"  warning: {item.get('missing_chunks', 0)} duplicate chunk(s) still missing source text")
    for item in report.get("deleted", []):
        status = item.get("status", "deleted")
        lines.append(
            f"- {status}: {item.get('index', '')} "
            f"{human_bytes(item.get('bytes', 0))}"
        )
        extras = []
        for key, label in [
            ("vector_stores_deleted", "vector"),
            ("evidence_stores_deleted", "evidence"),
            ("vector_progress_deleted", "vector-progress"),
            ("topics_deleted", "topics"),
            ("dossiers_deleted", "dossiers"),
            ("retrieval_debug_deleted", "retrieval-debug"),
            ("retrieval_evals_deleted", "retrieval-evals"),
            ("feedback_evals_deleted", "feedback-evals"),
            ("action_evals_deleted", "action-evals"),
            ("model_evals_deleted", "model-evals"),
        ]:
            if item.get(key):
                extras.append(f"{label}:{item.get(key)}")
        if extras:
            lines.append("  derived deleted: " + ", ".join(extras))
        for warning in item.get("warnings", [])[:3]:
            lines.append(f"  warning: {warning}")
    for item in report.get("blocked", []):
        lines.append(f"- blocked: {item.get('index', '')} {item.get('reason', '')}".rstrip())
        for warning in item.get("warnings", [])[:3]:
            lines.append(f"  warning: {warning}")
    if not report.get("deleted") and not report.get("blocked") and not report.get("materialized"):
        lines.append("no stale superseded index artifacts were safe to clean")
    return "\n".join(lines)
