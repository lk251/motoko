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
SLOT_CACHE_GIB = 1024 * 1024 * 1024
SLOT_CACHE_DEFAULT_PROFILE = "standard"
SLOT_CACHE_DEFAULT_SLOT_FILE_BYTES = 16 * SLOT_CACHE_GIB
SLOT_CACHE_DEFAULT_BUDGET_BYTES = 4 * SLOT_CACHE_DEFAULT_SLOT_FILE_BYTES
SLOT_CACHE_MAX_BYTES_ENV = "MOTOKO_SLOT_CACHE_MAX_BYTES"
SLOT_CACHE_PROFILE_FALLBACK_BYTES = {
    "off": 0,
    "disabled": 0,
    "tiny": 1 * SLOT_CACHE_DEFAULT_SLOT_FILE_BYTES,
    "small": 2 * SLOT_CACHE_DEFAULT_SLOT_FILE_BYTES,
    "standard": 4 * SLOT_CACHE_DEFAULT_SLOT_FILE_BYTES,
    "large": 8 * SLOT_CACHE_DEFAULT_SLOT_FILE_BYTES,
}
SLOT_CACHE_PROFILE_FILE_COUNTS = {
    "off": 0,
    "disabled": 0,
    "tiny": 1,
    "small": 2,
    "standard": 4,
    "large": 8,
}

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


def _parse_byte_count(raw, *, default: int = 0) -> int:
    if raw is None:
        return default
    text = str(raw).strip().lower()
    if not text:
        return default
    multiplier = 1
    for suffix, value in (
        ("gib", SLOT_CACHE_GIB),
        ("gb", 1000 * 1000 * 1000),
        ("mib", 1024 * 1024),
        ("mb", 1000 * 1000),
        ("kib", 1024),
        ("kb", 1000),
        ("b", 1),
    ):
        if text.endswith(suffix):
            multiplier = value
            text = text[: -len(suffix)].strip()
            break
    try:
        amount = float(text)
    except ValueError:
        return default
    if amount < 0:
        return default
    return int(amount * multiplier)


def _safe_component(value: str, fallback: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip("-") or fallback


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _cache_policy(route_info: dict) -> dict:
    value = route_info.get("cache")
    return value if isinstance(value, dict) else {}


def _explicit_slot_cache_budget_bytes(route_info: dict) -> int | None:
    policy = _cache_policy(route_info)
    for key in ("slotCacheMaxBytes", "slot_cache_max_bytes", "maxDiskBytes", "max_disk_bytes"):
        if key not in policy:
            continue
        value = _parse_byte_count(policy.get(key), default=-1)
        if value >= 0:
            return value
    for key in ("slotCacheMaxMiB", "slot_cache_max_mib", "maxDiskMiB", "max_disk_mib"):
        if key not in policy:
            continue
        try:
            value = int(policy.get(key))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value * 1024 * 1024
    return None


def route_slot_cache_declared_file_bytes(route_info: dict) -> int:
    policy = _cache_policy(route_info)
    for key in (
        "slotCacheFileBytes",
        "slot_cache_file_bytes",
        "slotFileBytes",
        "slot_file_bytes",
        "slotCacheEntryBytes",
        "slot_cache_entry_bytes",
    ):
        if key not in policy:
            continue
        value = _parse_byte_count(policy.get(key), default=-1)
        if value > 0:
            return value
    for key in (
        "slotCacheFileMiB",
        "slot_cache_file_mib",
        "slotFileMiB",
        "slot_file_mib",
        "slotCacheEntryMiB",
        "slot_cache_entry_mib",
    ):
        if key not in policy:
            continue
        try:
            value = int(policy.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value * 1024 * 1024
    return 0


def observed_slot_file_bytes(route_info: dict, records: list[dict] | None = None) -> int:
    records = records if records is not None else read_slot_cache_manifest().get("records", [])
    route_name = local_model_helper_route(route_info)
    sizes = [
        _slot_record_size_bytes(row)
        for row in records
        if isinstance(row, dict) and row.get("catalog_route") == route_name
    ]
    sizes = [size for size in sizes if size > 0]
    return max(sizes) if sizes else 0


def route_slot_cache_file_budget_bytes(route_info: dict, records: list[dict] | None = None) -> int:
    return route_slot_cache_declared_file_bytes(route_info) or observed_slot_file_bytes(route_info, records=records)


def route_slot_cache_budget_bytes(route_info: dict, records: list[dict] | None = None) -> int:
    if SLOT_CACHE_MAX_BYTES_ENV in os.environ:
        env_budget = _parse_byte_count(os.environ.get(SLOT_CACHE_MAX_BYTES_ENV), default=-1)
        if env_budget >= 0:
            return env_budget
    profile = slot_cache_budget_profile(route_info) or SLOT_CACHE_DEFAULT_PROFILE
    if profile in {"off", "disabled"}:
        return 0
    explicit_budget = _explicit_slot_cache_budget_bytes(route_info)
    if explicit_budget is not None:
        return explicit_budget
    if profile in SLOT_CACHE_PROFILE_FILE_COUNTS:
        count = SLOT_CACHE_PROFILE_FILE_COUNTS[profile]
        if count <= 0:
            return 0
        file_bytes = route_slot_cache_file_budget_bytes(route_info, records=records)
        if file_bytes > 0:
            return count * file_bytes
    if profile in SLOT_CACHE_PROFILE_FALLBACK_BYTES:
        return SLOT_CACHE_PROFILE_FALLBACK_BYTES[profile]
    return SLOT_CACHE_DEFAULT_BUDGET_BYTES


def slot_cache_budget_profile(route_info: dict) -> str:
    policy = _cache_policy(route_info)
    for key in ("slotCacheBudgetProfile", "slot_cache_budget_profile", "slotCacheProfile", "slot_cache_profile"):
        value = policy.get(key)
        if isinstance(value, str) and value.strip():
            return re.sub(r"[^a-z0-9_.-]+", "-", value.strip().lower()).strip("-")
    return ""


def slot_cache_budget_label(route_info: dict) -> str:
    profile = slot_cache_budget_profile(route_info)
    if profile:
        return profile
    env_budget = _parse_byte_count(os.environ.get(SLOT_CACHE_MAX_BYTES_ENV), default=-1)
    if SLOT_CACHE_MAX_BYTES_ENV in os.environ and env_budget >= 0:
        return "env"
    policy = _cache_policy(route_info)
    if _explicit_slot_cache_budget_bytes(route_info) is not None:
        return "explicit"
    if route_slot_cache_declared_file_bytes(route_info) > 0:
        return SLOT_CACHE_DEFAULT_PROFILE
    return SLOT_CACHE_DEFAULT_PROFILE


def route_slot_cache_budget_detail(route_info: dict, records: list[dict] | None = None) -> dict:
    profile = slot_cache_budget_label(route_info)
    explicit_budget = _explicit_slot_cache_budget_bytes(route_info)
    file_bytes = route_slot_cache_file_budget_bytes(route_info, records=records)
    count = SLOT_CACHE_PROFILE_FILE_COUNTS.get(slot_cache_budget_profile(route_info) or SLOT_CACHE_DEFAULT_PROFILE, 0)
    return {
        "profile": profile,
        "bytes": route_slot_cache_budget_bytes(route_info, records=records),
        "file_bytes": file_bytes,
        "file_count": count,
        "explicit": explicit_budget is not None,
    }


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


def _managed_slot_file_path(save_root: str, filename: str) -> pathlib.Path | None:
    if not save_root or not filename or pathlib.PurePath(filename).name != filename:
        return None
    path = pathlib.Path(save_root).expanduser() / filename
    try:
        resolved_root = pathlib.Path(save_root).expanduser().resolve(strict=False)
        resolved_path = path.resolve(strict=False)
    except OSError:
        return None
    if resolved_root not in [resolved_path] + list(resolved_path.parents):
        return None
    return path


def _slot_record_file_path(row: dict) -> pathlib.Path | None:
    return _managed_slot_file_path(str(row.get("slot_save_path_declared") or ""), str(row.get("filename") or ""))


def _slot_record_size_bytes(row: dict) -> int:
    path = _slot_record_file_path(row)
    if path is not None:
        try:
            return max(0, int(path.stat().st_size))
        except OSError:
            pass
    for key in ("file_size_bytes", "n_written"):
        try:
            value = int(row.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return 0


def _unlink_slot_record_file(row: dict) -> bool:
    path = _slot_record_file_path(row)
    if path is None:
        return False
    try:
        if not os.access(path.parent, os.W_OK | os.X_OK):
            return False
    except OSError:
        return False
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def slot_cache_usage(records: list[dict] | None = None) -> dict:
    records = records if records is not None else read_slot_cache_manifest().get("records", [])
    total = 0
    unknown = 0
    for row in records:
        if not isinstance(row, dict):
            continue
        size = _slot_record_size_bytes(row)
        if size <= 0:
            unknown += 1
        total += size
    return {"bytes": total, "records": len([row for row in records if isinstance(row, dict)]), "unknown": unknown}


def _slot_record_client_deletable(row: dict) -> bool:
    path = _slot_record_file_path(row)
    if path is None:
        return False
    try:
        path.stat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    try:
        return os.access(path.parent, os.W_OK | os.X_OK)
    except OSError:
        return False


def enforce_slot_cache_budget(route_info: dict, *, protect_key: tuple | None = None) -> dict:
    manifest = read_slot_cache_manifest()
    records = [row for row in manifest.get("records", []) if isinstance(row, dict)]
    budget = route_slot_cache_budget_bytes(route_info, records=records)
    before = slot_cache_usage(records)
    if before["bytes"] <= budget:
        return {
            "status": "within-budget",
            "budget_profile": slot_cache_budget_label(route_info),
            "budget_bytes": budget,
            "bytes_before": before["bytes"],
            "bytes_after": before["bytes"],
            "records_removed": 0,
            "files_deleted": 0,
            "delete_failures": 0,
            "protected_evicted": 0,
            "service_gc_required": False,
            "service_owned_records": 0,
            "unknown_records": before["unknown"],
        }

    def record_key(row: dict) -> tuple:
        return (row.get("route_fingerprint"), row.get("conversation_id"), row.get("filename"))

    candidates = [row for row in records if record_key(row) != protect_key]
    candidates.sort(key=lambda row: str(row.get("last_used") or row.get("updated") or row.get("created") or ""))
    kept = list(records)
    removed = []
    files_deleted = 0
    delete_failures = 0
    service_owned_records = 0
    current_bytes = before["bytes"]
    for row in candidates:
        if current_bytes <= budget:
            break
        size = _slot_record_size_bytes(row)
        if not _slot_record_client_deletable(row):
            service_owned_records += 1
            continue
        deleted = _unlink_slot_record_file(row)
        if not deleted and size > 0:
            delete_failures += 1
            continue
        removed.append(row)
        files_deleted += 1 if deleted else 0
        current_bytes = max(0, current_bytes - size)
        kept = [item for item in kept if record_key(item) != record_key(row)]

    protected_evicted = 0
    if current_bytes > budget and protect_key is not None:
        for row in list(kept):
            if record_key(row) != protect_key:
                continue
            size = _slot_record_size_bytes(row)
            if not _slot_record_client_deletable(row):
                service_owned_records += 1
                continue
            deleted = _unlink_slot_record_file(row)
            if not deleted and size > 0:
                delete_failures += 1
                continue
            removed.append(row)
            protected_evicted += 1
            files_deleted += 1 if deleted else 0
            current_bytes = max(0, current_bytes - size)
            kept = [item for item in kept if record_key(item) != record_key(row)]

    manifest["records"] = kept
    write_slot_cache_manifest(manifest)
    after = slot_cache_usage(kept)
    service_gc_required = after["bytes"] > budget and service_owned_records > 0
    status = "within-budget" if after["bytes"] <= budget else "needs-service-gc" if service_gc_required else "over-budget"
    return {
        "status": status,
        "budget_profile": slot_cache_budget_label(route_info),
        "budget_bytes": budget,
        "bytes_before": before["bytes"],
        "bytes_after": after["bytes"],
        "records_removed": len(removed),
        "files_deleted": files_deleted,
        "delete_failures": delete_failures,
        "protected_evicted": protected_evicted,
        "service_gc_required": service_gc_required,
        "service_owned_records": service_owned_records,
        "unknown_records": after["unknown"],
    }


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
    budget_before = enforce_slot_cache_budget(route_info)
    context["budget"] = budget_before.get("status")
    context["budget_profile"] = budget_before.get("budget_profile")
    context["budget_bytes"] = budget_before.get("budget_bytes")
    context["cache_bytes"] = budget_before.get("bytes_after")
    if int(budget_before.get("budget_bytes") or 0) <= 0:
        context["save"] = "skipped-budget-disabled"
        return context
    if budget_before.get("status") == "over-budget":
        context["save"] = "skipped-budget-full"
        context["budget_delete_failures"] = budget_before.get("delete_failures", 0)
        return context
    if budget_before.get("status") == "needs-service-gc":
        context["budget_service_gc_required"] = True
        context["budget_service_owned_records"] = budget_before.get("service_owned_records", 0)
        context["budget_delete_failures"] = budget_before.get("delete_failures", 0)
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
    record["file_size_bytes"] = _slot_record_size_bytes(record)
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
    if context.get("manifest") == "updated":
        protect_key = (record.get("route_fingerprint"), record.get("conversation_id"), record.get("filename"))
        try:
            budget_after = enforce_slot_cache_budget(route_info, protect_key=protect_key)
        except Exception as exc:
            context["budget"] = "cleanup-failed"
            context["budget_error_type"] = type(exc).__name__
        else:
            context["budget"] = budget_after.get("status")
            context["budget_profile"] = budget_after.get("budget_profile")
            context["budget_bytes"] = budget_after.get("budget_bytes")
            context["cache_bytes"] = budget_after.get("bytes_after")
            context["budget_records_removed"] = budget_after.get("records_removed", 0)
            context["budget_files_deleted"] = budget_after.get("files_deleted", 0)
            context["budget_delete_failures"] = budget_after.get("delete_failures", 0)
            context["budget_protected_evicted"] = budget_after.get("protected_evicted", 0)
            context["budget_service_gc_required"] = bool(budget_after.get("service_gc_required"))
            context["budget_service_owned_records"] = budget_after.get("service_owned_records", 0)
            if budget_after.get("protected_evicted"):
                context["save"] = "evicted-budget"
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
    service_owned_records = 0
    for row in manifest.get("records", []):
        if not isinstance(row, dict):
            continue
        matches_route = not route_name or row.get("catalog_route") == route_name or row.get("route") == route_name
        matches_conv = not conversation_id or row.get("conversation_id") == conversation_id
        if matches_route and matches_conv:
            if _slot_record_file_path(row) is not None and not _slot_record_client_deletable(row):
                service_owned_records += 1
                kept.append(row)
                continue
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
        path = _managed_slot_file_path(save_root, filename)
        if path is None:
            continue
        try:
            path.unlink()
            deleted_files += 1
        except FileNotFoundError:
            deleted_files += 1
        except OSError:
            continue
    return {
        "status": "needs-service-gc" if service_owned_records else "cleared",
        "records_removed": len(removed),
        "files_deleted": deleted_files,
        "service_owned_records": service_owned_records,
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
        f"estimated bytes: {slot_cache_usage(records).get('bytes', 0)}",
    ]
    if route_info is not None:
        capability = slot_cache_capability(route_info, automatic=False)
        route_records = [row for row in records if row.get("catalog_route") == capability.get("catalog_route")]
        budget_detail = route_slot_cache_budget_detail(route_info, records=route_records)
        budget = int(budget_detail.get("bytes") or 0)
        budget_label = str(budget_detail.get("profile") or "")
        route_usage = slot_cache_usage(route_records)
        lines.extend(
            [
                f"route: {capability.get('catalog_route', '')}",
                f"status: {capability.get('status', '')}",
                f"slots endpoint: {capability.get('slots_endpoint', '') or 'none'}",
                f"slot id: {capability.get('slot_id') if capability.get('slot_id') is not None else 'none'} ({capability.get('slot_id_source', '')})",
                f"slot save path: {capability.get('slot_save_path_declared', '') or 'not declared'}",
                f"budget: {budget_label} ({budget} bytes)",
                f"budget file size: {budget_detail.get('file_bytes', 0)} bytes",
                f"budget file count: {budget_detail.get('file_count', 0)}",
                f"route estimated bytes: {route_usage.get('bytes', 0)}",
            ]
        )
        for reason in capability.get("reasons", [])[:8]:
            lines.append(f"reason: {reason}")
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
