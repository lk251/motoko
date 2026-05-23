"""Index storage audit formatting for Motoko."""

from __future__ import annotations

from motoko_core.text import human_bytes

INDEX_STORAGE_AUDIT_SCHEMA_VERSION = "index-storage-audit-v1"


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
    if audit.get("missing_duplicate_targets"):
        lines.append("")
        lines.append("missing duplicate targets:")
        for ref in audit.get("missing_duplicate_targets", [])[:8]:
            lines.append(
                f"- {ref.get('index_id', '')} {ref.get('path', '')} "
                f"chunk {ref.get('chunk', '')} sha256={ref.get('content_sha256', '')}"
            )
    return "\n".join(lines)
