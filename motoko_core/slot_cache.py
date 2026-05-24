"""Persistent llama.cpp slot/KV cache coordination for Motoko.

Motoko never writes llama.cpp KV-cache files directly. The model service owns
those files behind its declared ``--slot-save-path``. This module stores only a
realm-local, content-free manifest and calls the route's declared slot endpoint
when NixOS has explicitly enabled that surface.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import time
import urllib.parse

from .model_io import endpoint_is_unix, route_json_request
from .model_services import local_model_helper_route
from .state import atomic_write, ensure_private_dir, safe_load_json, slot_cache_dir, slot_cache_manifest_path


SLOT_CACHE_SCHEMA_VERSION = "slot-kv-cache-v1"
SLOT_CACHE_MANIFEST_SCHEMA_VERSION = "slot-kv-cache-manifest-v1"
SLOT_CACHE_DEFAULT_CLIENT_NAMESPACE = "motoko-chat-slot-input-v1"
SLOT_CACHE_ENV = "MOTOKO_SLOT_CACHE"
SLOT_CACHE_TIMEOUT_SECONDS = 120.0
SLOT_CACHE_SOCKET_ACTIVATION_SECONDS = 900.0
SLOT_CACHE_MAX_RECORDS = 128

SLOT_CACHE_DISABLED_SURFACES = {
    "slot",
    "slots",
    "slots_endpoint",
    "slots-endpoint",
    "slot_endpoint",
    "slot-endpoint",
    "slot_save_path",
    "slot-save-path",
    "persistent_slot_cache",
    "persistent-slot-cache",
    "persistent_kv_cache",
    "persistent-kv-cache",
}


def slot_cache_enabled() -> bool:
    value = os.environ.get(SLOT_CACHE_ENV, "1").strip().lower()
    return value not in {"0", "false", "no", "off", "disable", "disabled"}


def _safe_component(value: str, fallback: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip("-") or fallback


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _cache_policy(route_info: dict) -> dict:
    value = route_info.get("cache")
    return value if isinstance(value, dict) else {}


def _safety_policy(route_info: dict) -> dict:
    value = route_info.get("safety_policy")
    return value if isinstance(value, dict) else {}


def route_slots_endpoint(route_info: dict) -> str:
    policy = _cache_policy(route_info)
    value = policy.get("slotsEndpoint")
    if value is True:
        return "/slots"
    if isinstance(value, str) and value.strip():
        path = value.strip()
        return path if path.startswith("/") else "/" + path
    return ""


def route_slot_save_path(route_info: dict) -> str:
    policy = _cache_policy(route_info)
    for key in ("slotSavePath", "slot_save_path", "slotSaveRoot", "slot_save_root"):
        value = policy.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def route_slot_id(route_info: dict) -> tuple[int | None, str]:
    policy = _cache_policy(route_info)
    for key in ("slotId", "slot_id", "persistentSlotId", "persistent_slot_id"):
        if key not in policy:
            continue
        try:
            value = int(policy.get(key))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value, "declared"
    try:
        max_parallel = int(route_info.get("max_parallel") or 1)
    except (TypeError, ValueError):
        max_parallel = 1
    if max_parallel <= 1:
        return 0, "single-slot-default"
    return None, "parallel route requires declared cache.slotId"


def route_disabled_slot_surfaces(route_info: dict) -> list[str]:
    policy = _safety_policy(route_info)
    disabled = policy.get("disabled_server_surfaces") or policy.get("disabledServerSurfaces")
    if not isinstance(disabled, list):
        return []
    matches = []
    for item in disabled:
        normalized = re.sub(r"[^a-z0-9]+", "_", str(item).strip().lower()).strip("_")
        if normalized in SLOT_CACHE_DISABLED_SURFACES:
            matches.append(str(item))
    return matches


def _client_namespace(value: str | None = None) -> str:
    value = str(value or "").strip()
    return value or SLOT_CACHE_DEFAULT_CLIENT_NAMESPACE


def route_slot_cache_fingerprint(route_info: dict, *, client_namespace: str | None = None) -> str:
    payload = {
        "schema": SLOT_CACHE_SCHEMA_VERSION,
        "client_namespace": _client_namespace(client_namespace),
        "catalog_route": local_model_helper_route(route_info),
        "endpoint": str(route_info.get("endpoint") or ""),
        "model": str(route_info.get("model") or ""),
        "download_hash": str(route_info.get("download_hash") or ""),
        "ctx_size": route_info.get("ctx_size") or route_info.get("context_tokens") or "",
        "quant": str(route_info.get("quant") or ""),
        "slot_id": route_slot_id(route_info)[0],
        "slot_save_path": route_slot_save_path(route_info),
    }
    return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))[:24]


def slot_cache_filename(route_info: dict, conversation_id: str, *, client_namespace: str | None = None) -> str:
    route_token = _safe_component(local_model_helper_route(route_info), "route")
    conv_hash = _sha256_text(str(conversation_id))[:16]
    route_hash = route_slot_cache_fingerprint(route_info, client_namespace=client_namespace)[:16]
    return f"motoko-slot-{route_token}-{conv_hash}-{route_hash}.bin"


def slot_cache_capability(route_info: dict, *, automatic: bool = False) -> dict:
    reasons: list[str] = []
    warnings: list[str] = []
    route_name = local_model_helper_route(route_info)
    policy = _cache_policy(route_info)
    if not slot_cache_enabled():
        reasons.append(f"{SLOT_CACHE_ENV}=off")
    if not endpoint_is_unix(str(route_info.get("endpoint") or "")):
        reasons.append("only declared Unix-socket local model routes may use persistent slots")
    if policy.get("persistentSlotCache") is not True:
        reasons.append("route cache.persistentSlotCache is not true")
    slots_endpoint = route_slots_endpoint(route_info)
    if not slots_endpoint:
        reasons.append("route cache.slotsEndpoint is not enabled")
    save_path = route_slot_save_path(route_info)
    if not save_path:
        reasons.append("route cache.slotSavePath is not declared")
    disabled = route_disabled_slot_surfaces(route_info)
    if disabled:
        reasons.append("route safety policy disables slot surfaces: " + ", ".join(disabled[:6]))
    slot_id, slot_id_source = route_slot_id(route_info)
    if slot_id is None:
        reasons.append(slot_id_source)
    if automatic:
        logical_route = str(route_info.get("route") or "")
        tasks = {str(item) for item in route_info.get("tasks", [])} if isinstance(route_info.get("tasks"), list) else set()
        if logical_route != "chat" and not ({"chat", "default_chat", "quality_chat", "deep_synthesis"} & tasks):
            reasons.append("automatic persistent slot cache is only enabled for chat routes")
    if policy.get("prompt") is not True:
        warnings.append("route prompt cache is not declared on; slot restore may be less useful")
    return {
        "schema": SLOT_CACHE_SCHEMA_VERSION,
        "route": str(route_info.get("route") or ""),
        "catalog_route": route_name,
        "supported": not reasons,
        "status": "supported" if not reasons else "unsupported",
        "reasons": reasons,
        "warnings": warnings,
        "slots_endpoint": slots_endpoint,
        "slot_id": slot_id,
        "slot_id_source": slot_id_source,
        "slot_save_path_declared": save_path,
        "persistent": policy.get("persistentSlotCache") is True,
    }


def read_slot_cache_manifest() -> dict:
    data = safe_load_json(slot_cache_manifest_path())
    if not isinstance(data, dict) or data.get("schema") != SLOT_CACHE_MANIFEST_SCHEMA_VERSION:
        return {"schema": SLOT_CACHE_MANIFEST_SCHEMA_VERSION, "records": []}
    records = data.get("records")
    if not isinstance(records, list):
        data["records"] = []
    return data


def write_slot_cache_manifest(manifest: dict) -> None:
    ensure_private_dir(slot_cache_dir())
    records = [row for row in manifest.get("records", []) if isinstance(row, dict)]
    records.sort(key=lambda row: str(row.get("updated") or row.get("created") or ""))
    manifest = {
        "schema": SLOT_CACHE_MANIFEST_SCHEMA_VERSION,
        "updated": _now(),
        "records": records[-SLOT_CACHE_MAX_RECORDS:],
    }
    atomic_write(slot_cache_manifest_path(), json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def latest_slot_cache_record(route_info: dict, conversation_id: str, *, client_namespace: str | None = None) -> dict | None:
    route_fingerprint = route_slot_cache_fingerprint(route_info, client_namespace=client_namespace)
    namespace = _client_namespace(client_namespace)
    records = [
        row
        for row in read_slot_cache_manifest().get("records", [])
        if row.get("schema") == SLOT_CACHE_SCHEMA_VERSION
        and row.get("conversation_id") == conversation_id
        and row.get("client_namespace", SLOT_CACHE_DEFAULT_CLIENT_NAMESPACE) == namespace
        and row.get("route_fingerprint") == route_fingerprint
        and row.get("status") == "saved"
    ]
    if not records:
        return None
    records.sort(key=lambda row: str(row.get("updated") or row.get("created") or ""))
    return dict(records[-1])


def upsert_slot_cache_record(record: dict) -> dict:
    manifest = read_slot_cache_manifest()
    records = [row for row in manifest.get("records", []) if isinstance(row, dict)]
    key = (record.get("route_fingerprint"), record.get("conversation_id"), record.get("filename"))
    updated = False
    for idx, row in enumerate(records):
        if (row.get("route_fingerprint"), row.get("conversation_id"), row.get("filename")) == key:
            merged = dict(row)
            merged.update(record)
            records[idx] = merged
            record = merged
            updated = True
            break
    if not updated:
        records.append(record)
    manifest["records"] = records
    write_slot_cache_manifest(manifest)
    return record


def slot_action_path(route_info: dict, slot_id: int, action: str) -> str:
    base = route_slots_endpoint(route_info).rstrip("/") or "/slots"
    if "{id_slot}" in base:
        path = base.replace("{id_slot}", str(slot_id))
    elif "{slot_id}" in base:
        path = base.replace("{slot_id}", str(slot_id))
    else:
        path = f"{base}/{slot_id}"
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{urllib.parse.urlencode({'action': action})}"


def call_slot_action(
    route_info: dict,
    slot_id: int,
    action: str,
    *,
    filename: str | None = None,
    timeout: float = SLOT_CACHE_TIMEOUT_SECONDS,
    request_func=route_json_request,
) -> dict:
    payload = {"filename": filename} if filename else None
    return request_func(
        route_info,
        slot_action_path(route_info, slot_id, action),
        method="POST",
        payload=payload,
        timeout=timeout,
        socket_activation_min_timeout=SLOT_CACHE_SOCKET_ACTIVATION_SECONDS,
    )


def prepare_slot_cache_for_request(
    route_info: dict,
    payload: dict,
    *,
    conversation_id: str | None = None,
    client_namespace: str | None = None,
    request_func=route_json_request,
) -> dict:
    capability = slot_cache_capability(route_info, automatic=True)
    client_namespace = _client_namespace(client_namespace)
    context = {
        "schema": SLOT_CACHE_SCHEMA_VERSION,
        "client_namespace": client_namespace,
        "capability": capability,
        "restore": "unsupported",
        "save": "not-attempted",
    }
    if not capability.get("supported"):
        return context
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        context["restore"] = "skipped-no-conversation"
        context["save"] = "skipped-no-conversation"
        return context
    slot_id = int(capability["slot_id"])
    payload["id_slot"] = slot_id
    if _cache_policy(route_info).get("prompt") is True:
        payload.setdefault("cache_prompt", True)
    filename = slot_cache_filename(route_info, conversation_id, client_namespace=client_namespace)
    context.update(
        {
            "conversation_id": conversation_id,
            "route_fingerprint": route_slot_cache_fingerprint(route_info, client_namespace=client_namespace),
            "slot_id": slot_id,
            "filename": filename,
            "catalog_route": local_model_helper_route(route_info),
        }
    )
    record = latest_slot_cache_record(route_info, conversation_id, client_namespace=client_namespace)
    if not record:
        context["restore"] = "miss"
        return context
    context["restored_record_updated"] = str(record.get("updated") or "")
    try:
        response = call_slot_action(
            route_info,
            slot_id,
            "restore",
            filename=str(record.get("filename") or filename),
            request_func=request_func,
        )
    except Exception as exc:  # Cache misses must not fail model requests.
        context["restore"] = "failed"
        context["restore_error_type"] = type(exc).__name__
        return context
    context["restore"] = "restored"
    context["restore_n"] = int(response.get("n_restored") or 0) if isinstance(response, dict) else 0
    record["last_used"] = _now()
    record["restore_count"] = int(record.get("restore_count", 0) or 0) + 1
    record["last_restore_status"] = "restored"
    try:
        upsert_slot_cache_record(record)
        context["manifest"] = "updated"
    except Exception as exc:
        context["manifest"] = "update-failed"
        context["manifest_error_type"] = type(exc).__name__
    return context


def save_slot_cache_after_request(
    route_info: dict,
    context: dict,
    *,
    request_func=route_json_request,
) -> dict:
    capability = context.get("capability") if isinstance(context.get("capability"), dict) else {}
    if not capability.get("supported"):
        context["save"] = "unsupported"
        return context
    conversation_id = str(context.get("conversation_id") or "")
    filename = str(context.get("filename") or "")
    if not conversation_id or not filename:
        context["save"] = "skipped-no-conversation"
        return context
    slot_id = int(context.get("slot_id") or capability.get("slot_id") or 0)
    try:
        response = call_slot_action(
            route_info,
            slot_id,
            "save",
            filename=filename,
            request_func=request_func,
        )
    except Exception as exc:  # Cache save failure is performance-only.
        context["save"] = "failed"
        context["save_error_type"] = type(exc).__name__
        return context
    created = _now()
    record = {
        "schema": SLOT_CACHE_SCHEMA_VERSION,
        "client_namespace": _client_namespace(str(context.get("client_namespace") or "")),
        "status": "saved",
        "created": created,
        "updated": created,
        "last_used": created,
        "conversation_id": conversation_id,
        "catalog_route": local_model_helper_route(route_info),
        "route": str(route_info.get("route") or ""),
        "route_profile": str(route_info.get("route_profile") or ""),
        "route_fingerprint": str(
            context.get("route_fingerprint")
            or route_slot_cache_fingerprint(route_info, client_namespace=str(context.get("client_namespace") or ""))
        ),
        "model": str(route_info.get("model") or ""),
        "quant": str(route_info.get("quant") or ""),
        "ctx_size": route_info.get("ctx_size") or route_info.get("context_tokens") or 0,
        "slot_id": slot_id,
        "filename": filename,
        "slot_save_path_declared": route_slot_save_path(route_info),
        "save_count": 1,
        "restore_count": int(context.get("restore") == "restored"),
        "n_saved": int(response.get("n_saved") or 0) if isinstance(response, dict) else 0,
        "n_written": int(response.get("n_written") or 0) if isinstance(response, dict) else 0,
    }
    previous = latest_slot_cache_record(
        route_info,
        conversation_id,
        client_namespace=str(context.get("client_namespace") or ""),
    )
    if previous and previous.get("filename") == filename:
        record["created"] = previous.get("created") or created
        record["save_count"] = int(previous.get("save_count", 0) or 0) + 1
        record["restore_count"] = max(record["restore_count"], int(previous.get("restore_count", 0) or 0))
    try:
        upsert_slot_cache_record(record)
        context["save"] = "saved"
        context["manifest"] = "updated"
    except Exception as exc:
        context["save"] = "saved-manifest-failed"
        context["manifest"] = "update-failed"
        context["manifest_error_type"] = type(exc).__name__
    context["save_n"] = record["n_saved"]
    return context


def erase_slot_cache(route_info: dict, *, request_func=route_json_request) -> dict:
    capability = slot_cache_capability(route_info, automatic=False)
    if not capability.get("supported"):
        return {"status": "unsupported", "capability": capability}
    slot_id = int(capability["slot_id"])
    try:
        response = call_slot_action(route_info, slot_id, "erase", request_func=request_func)
    except Exception as exc:
        return {"status": "failed", "error_type": type(exc).__name__, "capability": capability}
    return {
        "status": "erased",
        "n_erased": int(response.get("n_erased") or 0) if isinstance(response, dict) else 0,
        "capability": capability,
    }


def clear_slot_cache_records(
    *,
    route_name: str = "",
    conversation_id: str = "",
    yes: bool = False,
) -> dict:
    if not yes:
        raise SystemExit("slot-cache clear requires --yes")
    manifest = read_slot_cache_manifest()
    kept = []
    removed = []
    for row in manifest.get("records", []):
        if not isinstance(row, dict):
            continue
        matches_route = not route_name or row.get("catalog_route") == route_name or row.get("route") == route_name
        matches_conv = not conversation_id or row.get("conversation_id") == conversation_id
        if matches_route and matches_conv:
            removed.append(row)
        else:
            kept.append(row)
    manifest["records"] = kept
    write_slot_cache_manifest(manifest)
    deleted_files = 0
    for row in removed:
        save_root = str(row.get("slot_save_path_declared") or "")
        filename = str(row.get("filename") or "")
        if not save_root or not filename or pathlib.PurePath(filename).name != filename:
            continue
        path = pathlib.Path(save_root).expanduser() / filename
        try:
            resolved_root = pathlib.Path(save_root).expanduser().resolve(strict=False)
            resolved_path = path.resolve(strict=False)
            if resolved_root not in [resolved_path] + list(resolved_path.parents):
                continue
            path.unlink()
            deleted_files += 1
        except OSError:
            continue
    return {
        "status": "cleared",
        "records_removed": len(removed),
        "files_deleted": deleted_files,
        "records_remaining": len(kept),
    }


def slot_cache_report(route_info: dict | None = None) -> str:
    manifest = read_slot_cache_manifest()
    records = [row for row in manifest.get("records", []) if isinstance(row, dict)]
    lines = [
        "slot/KV cache:",
        f"schema: {SLOT_CACHE_MANIFEST_SCHEMA_VERSION}",
        f"state: {slot_cache_dir()}",
        "privacy: manifest is realm-local and content-free; llama.cpp owns cache files behind declared slot-save-path",
        f"records: {len(records)}",
    ]
    if route_info is not None:
        capability = slot_cache_capability(route_info, automatic=False)
        lines.extend(
            [
                f"route: {capability.get('catalog_route', '')}",
                f"status: {capability.get('status', '')}",
                f"slots endpoint: {capability.get('slots_endpoint', '') or 'none'}",
                f"slot id: {capability.get('slot_id') if capability.get('slot_id') is not None else 'none'} ({capability.get('slot_id_source', '')})",
                f"slot save path: {capability.get('slot_save_path_declared', '') or 'not declared'}",
            ]
        )
        for reason in capability.get("reasons", [])[:8]:
            lines.append(f"reason: {reason}")
        route_records = [row for row in records if row.get("catalog_route") == capability.get("catalog_route")]
    else:
        route_records = records
    if route_records:
        lines.append("recent records:")
        for row in sorted(route_records, key=lambda item: str(item.get("updated") or ""), reverse=True)[:10]:
            lines.append(
                "  - "
                f"{row.get('catalog_route', '')} conv={row.get('conversation_id', '')} "
                f"slot={row.get('slot_id', '')} status={row.get('status', '')} "
                f"saved={row.get('n_saved', 0)} updated={row.get('updated', '')}"
            )
    return "\n".join(lines)
