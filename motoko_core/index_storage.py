"""Index storage audit helpers and formatting for Motoko."""

from __future__ import annotations

import pathlib
from typing import Callable

from motoko_core.text import human_bytes

INDEX_STORAGE_AUDIT_SCHEMA_VERSION = "index-storage-audit-v1"


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def duplicate_reference_target_report(duplicate_refs: list[dict], stored_by_digest: dict[str, list[dict]]) -> dict:
    missing_duplicate_refs = []
    duplicate_reference_bytes_with_target = 0
    for ref in duplicate_refs:
        digest = ref.get("content_sha256", "")
        targets = [
            target
            for target in stored_by_digest.get(digest, [])
            if target.get("index_id") != ref.get("index_id")
            and target.get("kind") == "index"
        ]
        if targets:
            duplicate_reference_bytes_with_target += _safe_int(ref.get("logical_content_bytes"))
        else:
            missing_duplicate_refs.append(ref)
    return {
        "missing_duplicate_targets": missing_duplicate_refs,
        "duplicate_reference_bytes_with_target": duplicate_reference_bytes_with_target,
    }


def index_storage_scan_record(
    record: dict,
    *,
    record_kind: str,
    referenced_paths: set[pathlib.Path],
    stored_by_digest: dict[str, list[dict]],
    unique_digest_bytes: dict[str, int],
    duplicate_refs: list[dict],
    chunk_content_path: Callable[[dict, dict], pathlib.Path | None],
    path_size: Callable[[pathlib.Path], int],
) -> dict:
    """Scan one index-like record and update shared storage-audit collections."""

    row = {
        "id": record.get("id", ""),
        "kind": record_kind,
        "name": record.get("name", ""),
        "root": record.get("root", ""),
        "chunks": 0,
        "stored_chunks": 0,
        "duplicate_reference_chunks": 0,
        "logical_content_bytes": 0,
        "stored_content_bytes": 0,
        "duplicate_reference_bytes": 0,
        "missing_stored_chunks": 0,
        "chunks_missing_digest": 0,
        "warnings": [],
    }
    for file_item in record.get("files", []):
        for chunk in file_item.get("chunks", []):
            row["chunks"] += 1
            digest = str(chunk.get("content_sha256", "")).strip()
            logical_bytes = _safe_int(chunk.get("content_bytes"))
            if not logical_bytes and isinstance(chunk.get("content"), str):
                logical_bytes = len(chunk.get("content", "").encode("utf-8"))
            row["logical_content_bytes"] += logical_bytes
            if not digest:
                row["chunks_missing_digest"] += 1
            if chunk.get("duplicate_of_existing_index"):
                row["duplicate_reference_chunks"] += 1
                row["duplicate_reference_bytes"] += logical_bytes
                duplicate_refs.append(
                    {
                        "index_id": record.get("id", ""),
                        "path": file_item.get("path", ""),
                        "chunk": chunk.get("chunk", ""),
                        "content_sha256": digest,
                        "logical_content_bytes": logical_bytes,
                    }
                )
                continue
            content_bytes = _safe_int(chunk.get("stored_content_bytes"))
            if "content" in chunk:
                text = str(chunk.get("content", ""))
                content_bytes = len(text.encode("utf-8"))
                row["stored_chunks"] += 1
                row["stored_content_bytes"] += content_bytes
                if digest:
                    stored_by_digest.setdefault(digest, []).append(
                        {
                            "index_id": record.get("id", ""),
                            "kind": record_kind,
                            "path": file_item.get("path", ""),
                            "chunk": chunk.get("chunk", ""),
                            "storage": "inline",
                            "bytes": content_bytes,
                        }
                    )
                    unique_digest_bytes.setdefault(digest, content_bytes)
                continue
            try:
                content_path = chunk_content_path(record, chunk)
            except ValueError as exc:
                row["warnings"].append(str(exc))
                row["missing_stored_chunks"] += 1
                continue
            if content_path is None:
                row["missing_stored_chunks"] += 1
                continue
            try:
                resolved = content_path.resolve()
            except OSError:
                resolved = content_path
            referenced_paths.add(resolved)
            if not content_path.exists():
                row["missing_stored_chunks"] += 1
                continue
            if not content_bytes:
                content_bytes = path_size(content_path)
            row["stored_chunks"] += 1
            row["stored_content_bytes"] += content_bytes
            if digest:
                stored_by_digest.setdefault(digest, []).append(
                    {
                        "index_id": record.get("id", ""),
                        "kind": record_kind,
                        "path": file_item.get("path", ""),
                        "chunk": chunk.get("chunk", ""),
                        "storage": str(content_path),
                        "bytes": content_bytes,
                    }
                )
                unique_digest_bytes.setdefault(digest, content_bytes)
    return row


def index_storage_scan_records(
    *,
    indexes: list[dict],
    partials: list[dict],
    latest_ids: set[str],
    resumable_partial_ids: set[str],
    partial_superseded: Callable[[dict], bool],
    chunk_content_path: Callable[[dict, dict], pathlib.Path | None],
    path_size: Callable[[pathlib.Path], int],
    check_cancelled: Callable[[], None] | None = None,
) -> dict:
    """Scan complete and partial indexes into storage-audit rows and indexes."""

    referenced_paths: set[pathlib.Path] = set()
    stored_by_digest: dict[str, list[dict]] = {}
    unique_digest_bytes: dict[str, int] = {}
    duplicate_refs: list[dict] = []
    rows: list[dict] = []

    def maybe_cancel() -> None:
        if check_cancelled is not None:
            check_cancelled()

    for index in indexes or []:
        maybe_cancel()
        row = index_storage_scan_record(
            index,
            record_kind="index",
            referenced_paths=referenced_paths,
            stored_by_digest=stored_by_digest,
            unique_digest_bytes=unique_digest_bytes,
            duplicate_refs=duplicate_refs,
            chunk_content_path=chunk_content_path,
            path_size=path_size,
        )
        row["latest_for_family"] = index.get("id", "") in latest_ids
        rows.append(row)
    for partial in partials or []:
        maybe_cancel()
        row = index_storage_scan_record(
            partial,
            record_kind="partial",
            referenced_paths=referenced_paths,
            stored_by_digest=stored_by_digest,
            unique_digest_bytes=unique_digest_bytes,
            duplicate_refs=duplicate_refs,
            chunk_content_path=chunk_content_path,
            path_size=path_size,
        )
        row["resumable"] = partial.get("id", "") in resumable_partial_ids
        row["superseded"] = partial_superseded(partial)
        rows.append(row)
    return {
        "rows": rows,
        "referenced_paths": referenced_paths,
        "stored_by_digest": stored_by_digest,
        "unique_digest_bytes": unique_digest_bytes,
        "duplicate_refs": duplicate_refs,
    }


def index_storage_orphan_chunk_files(
    data_dirs,
    *,
    referenced_paths: set[pathlib.Path],
    path_size: Callable[[pathlib.Path], int],
    check_cancelled: Callable[[], None] | None = None,
) -> list[dict]:
    """Return stored chunk text files that are no longer referenced."""

    orphan_files: list[dict] = []

    def maybe_cancel() -> None:
        if check_cancelled is not None:
            check_cancelled()

    for data_dir in data_dirs or []:
        maybe_cancel()
        data_dir = pathlib.Path(data_dir)
        if not data_dir.is_dir():
            continue
        for path in data_dir.rglob("*.txt"):
            maybe_cancel()
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved in referenced_paths:
                continue
            orphan_files.append({"path": str(path), "bytes": path_size(path)})
    return orphan_files


def index_storage_audit_report(
    *,
    created: str,
    indexes: list[dict],
    partials: list[dict],
    rows: list[dict],
    latest_ids: set[str],
    resumable_partial_ids: set[str],
    superseded_partials: list[dict],
    older_indexes: list[dict],
    unique_digest_bytes: dict[str, int],
    stored_by_digest: dict[str, list[dict]],
    duplicate_reference_report: dict,
    orphan_files: list[dict],
    source_lifecycle_plans: list[dict],
    cleanup_sections: dict,
) -> dict:
    completed_rows = [row for row in rows if row.get("kind") == "index"]
    missing_duplicate_refs = duplicate_reference_report.get("missing_duplicate_targets", [])
    duplicate_reference_bytes_with_target = _safe_int(
        duplicate_reference_report.get("duplicate_reference_bytes_with_target")
    )
    logical_bytes = sum(_safe_int(row.get("logical_content_bytes")) for row in completed_rows)
    physical_bytes = sum(_safe_int(row.get("stored_content_bytes")) for row in rows)
    unique_stored_bytes = sum(unique_digest_bytes.values())
    stored_body_duplicates = sum(max(0, len(locations) - 1) for locations in stored_by_digest.values())
    return {
        "schema": INDEX_STORAGE_AUDIT_SCHEMA_VERSION,
        "created": created,
        "index_count": len(indexes),
        "latest_index_families": len(latest_ids),
        "older_complete_indexes": len(older_indexes),
        "partial_count": len(partials),
        "resumable_partial_count": len(resumable_partial_ids),
        "superseded_partial_count": len(superseded_partials),
        "total_chunks": sum(_safe_int(row.get("chunks")) for row in completed_rows),
        "stored_chunks": sum(_safe_int(row.get("stored_chunks")) for row in completed_rows),
        "duplicate_reference_chunks": sum(_safe_int(row.get("duplicate_reference_chunks")) for row in completed_rows),
        "stored_body_duplicates": stored_body_duplicates,
        "unique_stored_bodies": len(unique_digest_bytes),
        "logical_content_bytes": logical_bytes,
        "physical_stored_content_bytes": physical_bytes,
        "unique_stored_content_bytes": unique_stored_bytes,
        "duplicate_reference_bytes": sum(_safe_int(row.get("duplicate_reference_bytes")) for row in completed_rows),
        "duplicate_reference_bytes_with_target": duplicate_reference_bytes_with_target,
        "estimated_dedup_saved_bytes": duplicate_reference_bytes_with_target,
        "missing_duplicate_target_count": len(missing_duplicate_refs),
        "missing_stored_chunk_count": sum(_safe_int(row.get("missing_stored_chunks")) for row in rows),
        "orphan_chunk_file_count": len(orphan_files),
        "orphan_chunk_file_bytes": sum(_safe_int(item.get("bytes")) for item in orphan_files),
        "rows": rows,
        "missing_duplicate_targets": missing_duplicate_refs[:50],
        "orphan_chunk_files": orphan_files[:50],
        "source_lifecycle_plans": source_lifecycle_plans[:50],
        "safe_cleanup": cleanup_sections["safe_cleanup"],
        "blocked_cleanup": cleanup_sections["blocked_cleanup"],
    }


def format_index_storage_audit(audit: dict) -> str:
    lines = [
        f"index storage audit: {audit.get('schema', INDEX_STORAGE_AUDIT_SCHEMA_VERSION)}",
        f"created: {audit.get('created', '')}",
        (
            "indexes: "
            f"{audit.get('index_count', 0)} complete, "
            f"{audit.get('latest_index_families', 0)} latest family index(es), "
            f"{audit.get('older_complete_indexes', 0)} older complete"
        ),
        (
            "partials: "
            f"{audit.get('partial_count', 0)} total, "
            f"{audit.get('resumable_partial_count', 0)} resumable, "
            f"{audit.get('superseded_partial_count', 0)} superseded"
        ),
        (
            "chunks: "
            f"{audit.get('total_chunks', 0)} total, "
            f"{audit.get('stored_chunks', 0)} stored, "
            f"{audit.get('duplicate_reference_chunks', 0)} duplicate reference(s)"
        ),
        (
            "stored bodies: "
            f"{audit.get('unique_stored_bodies', 0)} unique, "
            f"{audit.get('stored_body_duplicates', 0)} duplicate stored body/bodies"
        ),
        (
            "bytes: "
            f"{human_bytes(audit.get('logical_content_bytes', 0))} logical corpus, "
            f"{human_bytes(audit.get('physical_stored_content_bytes', 0))} stored files, "
            f"{human_bytes(audit.get('unique_stored_content_bytes', 0))} unique stored"
        ),
        f"dedup saved: {human_bytes(audit.get('estimated_dedup_saved_bytes', 0))} estimated",
        f"missing duplicate targets: {audit.get('missing_duplicate_target_count', 0)}",
        (
            "orphan chunk files: "
            f"{audit.get('orphan_chunk_file_count', 0)} "
            f"({human_bytes(audit.get('orphan_chunk_file_bytes', 0))})"
        ),
        "",
        "largest records:",
    ]
    rows = sorted(
        audit.get("rows", []),
        key=lambda row: _safe_int(row.get("logical_content_bytes")),
        reverse=True,
    )
    for row in rows[:8]:
        markers = []
        if row.get("kind") == "index" and row.get("latest_for_family"):
            markers.append("latest")
        if row.get("kind") == "index" and not row.get("latest_for_family"):
            markers.append("older")
        if row.get("kind") == "partial" and row.get("resumable"):
            markers.append("resumable")
        if row.get("kind") == "partial" and row.get("superseded"):
            markers.append("superseded")
        marker = f" ({', '.join(markers)})" if markers else ""
        lines.append(
            f"- {row.get('kind')} {row.get('id', '')}{marker}: "
            f"{row.get('chunks', 0)} chunk(s), "
            f"{row.get('duplicate_reference_chunks', 0)} duplicate ref(s), "
            f"{human_bytes(row.get('logical_content_bytes', 0))} logical, "
            f"{human_bytes(row.get('stored_content_bytes', 0))} stored  "
            f"{row.get('name', '')} {row.get('root', '')}"
        )
        for warning in row.get("warnings", [])[:2]:
            lines.append(f"  warning: {warning}")
    lines.extend(["", "safe cleanup plan:"])
    if audit.get("safe_cleanup"):
        for item in audit.get("safe_cleanup", []):
            lines.append(
                f"- {item.get('safety', 'candidate')}: {item.get('kind', '')} "
                f"{item.get('count', 0)} item(s), {human_bytes(item.get('bytes', 0))}; "
                f"{item.get('action', '')}"
            )
    else:
        lines.append("- none: no deletion candidates are safe enough to suggest yet")
    if audit.get("blocked_cleanup"):
        lines.append("")
        lines.append("blocked cleanup:")
        for item in audit.get("blocked_cleanup", []):
            lines.append(
                f"- {item.get('safety', 'blocked')}: {item.get('kind', '')} "
                f"{item.get('count', 0)} item(s); {item.get('reason', '')}"
            )
    if audit.get("source_lifecycle_plans"):
        lines.append("")
        lines.append("source lifecycle work:")
        for plan in audit.get("source_lifecycle_plans", [])[:8]:
            counts = plan.get("source_counts", {}) or {}
            count_text = ", ".join(f"{key} {value}" for key, value in sorted(counts.items()))
            derived = _safe_int(plan.get("derived_artifact_count"))
            manual = _safe_int(plan.get("manual_review_artifact_count"))
            if not derived and not manual:
                derived = sum(_safe_int(item.get("count")) for item in plan.get("affected_artifacts", []) or [])
            artifact_parts = [f"{derived} derived artifact(s)"]
            if manual:
                artifact_parts.append(f"{manual} manual-review artifact(s)")
            apply_status = str(plan.get("apply_status", "")).strip()
            apply_part = f"; apply {apply_status}" if apply_status else ""
            lines.append(
                f"- {plan.get('index', '')}: {count_text or 'source changes'}; "
                f"{', '.join(artifact_parts)}; {plan.get('recommended_action', '')}{apply_part}"
            )
    if audit.get("missing_duplicate_targets"):
        lines.append("")
        lines.append("missing duplicate targets:")
        for ref in audit.get("missing_duplicate_targets", [])[:8]:
            lines.append(
                f"- {ref.get('index_id', '')} {ref.get('path', '')} "
                f"chunk {ref.get('chunk', '')} sha256={ref.get('content_sha256', '')}"
            )
    return "\n".join(lines)
