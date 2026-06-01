"""Index storage audit formatting for Motoko."""

from __future__ import annotations

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
