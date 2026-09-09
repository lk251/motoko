"""Local model route catalog helpers for Motoko."""

from __future__ import annotations

import json
import re

from .state import config_path, local_models_path, safe_load_json


MODEL_ROUTE_CHAT = "chat"
MODEL_ROUTE_INDEX_CHUNK = "index_chunk"
MODEL_ROUTE_INDEX_FILE = "index_file"
MODEL_ROUTE_INDEX_CORPUS = "index_corpus"
MODEL_ROUTE_INDEX_LABEL = "index_label"
MODEL_ROUTE_TOPIC = "topic"
MODEL_ROUTE_MEMORY = "memory"
MODEL_ROUTE_PROFILE = "profile"
MODEL_ROUTE_TITLE = "title"
MODEL_ROUTE_AUDIT = "audit"

MODEL_ROUTE_DESCRIPTIONS = {
    MODEL_ROUTE_CHAT: "interactive chat and final user-facing synthesis",
    MODEL_ROUTE_INDEX_CHUNK: "chunk-level retrieval summaries",
    MODEL_ROUTE_INDEX_FILE: "file-level summaries and file-purpose maps",
    MODEL_ROUTE_INDEX_CORPUS: "corpus-level synthesis across file summaries",
    MODEL_ROUTE_INDEX_LABEL: "file/document labels, lightweight classification, and routing hints",
    MODEL_ROUTE_TOPIC: "topic and deep dossiers over indexed evidence",
    MODEL_ROUTE_MEMORY: "conversation compaction and memory proposal work",
    MODEL_ROUTE_PROFILE: "profile dossier synthesis",
    MODEL_ROUTE_TITLE: "short conversation titles and labels",
    MODEL_ROUTE_AUDIT: "expensive quality audits and reflective checks",
}

LOCAL_MODEL_ROUTE_TASK_ALIASES = {
    MODEL_ROUTE_CHAT: (
        "chat",
        "default_chat",
        "quality_chat",
        "short_context_chat",
        "long_context_chat",
        "max_context_chat",
        "max_context",
        "deep_synthesis",
    ),
    MODEL_ROUTE_INDEX_CHUNK: ("index_chunk",),
    MODEL_ROUTE_INDEX_FILE: ("index_file",),
    MODEL_ROUTE_INDEX_CORPUS: ("index_corpus", "synthesis"),
    MODEL_ROUTE_INDEX_LABEL: ("index_label",),
    MODEL_ROUTE_TOPIC: ("synthesis", "deep_synthesis"),
    MODEL_ROUTE_MEMORY: ("memory_maintenance", "synthesis"),
    MODEL_ROUTE_PROFILE: ("synthesis", "deep_synthesis"),
    MODEL_ROUTE_TITLE: ("index_label", "memory_maintenance"),
    MODEL_ROUTE_AUDIT: ("audit", "deep_synthesis"),
}

# Compatibility for older catalogs; explicit task_routes owns managed selection.
LOCAL_MODEL_ROUTE_PREFERENCES = {
    MODEL_ROUTE_CHAT: ("qwen36-chat-default", "qwen36-chat"),
    MODEL_ROUTE_INDEX_CHUNK: ("qwen35-2b-worker", "ministral-3b-worker"),
    MODEL_ROUTE_INDEX_FILE: ("qwen3-4b-instruct-worker", "ministral-3b-worker"),
    MODEL_ROUTE_INDEX_CORPUS: ("qwen35-9b-worker", "qwen3-4b-instruct-worker"),
    MODEL_ROUTE_INDEX_LABEL: ("ministral-3b-worker", "qwen35-2b-worker"),
    MODEL_ROUTE_TOPIC: ("qwen35-9b-worker", "qwen36-chat-deep", "qwen36-chat-default", "qwen36-chat"),
    MODEL_ROUTE_MEMORY: ("qwen35-2b-worker", "qwen35-9b-worker"),
    MODEL_ROUTE_PROFILE: ("qwen35-9b-worker", "qwen36-chat-deep", "qwen36-chat-default", "qwen36-chat"),
    MODEL_ROUTE_TITLE: ("qwen35-2b-worker", "ministral-3b-worker"),
    MODEL_ROUTE_AUDIT: ("qwen35-9b-worker", "qwen36-chat-quality", "qwen36-chat-default", "qwen36-chat"),
}

CHAT_ROUTE_PROFILES = {"default", "quality", "deep", "max"}


def configured_identity_realm() -> str:
    data = safe_load_json(config_path())
    identity = data.get("identity") if isinstance(data, dict) else {}
    realm = identity.get("realm") if isinstance(identity, dict) else ""
    return realm.strip() if isinstance(realm, str) and realm.strip() else "personal"


def load_local_model_catalog() -> dict:
    path = local_models_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if not path.is_symlink():
            return {}
        raise SystemExit("cannot read local-models.json: broken catalog link") from None
    except (OSError, UnicodeError):
        raise SystemExit("cannot read local-models.json") from None
    except json.JSONDecodeError:
        raise SystemExit("invalid local-models.json: malformed JSON") from None
    if not isinstance(data, dict):
        raise SystemExit("invalid local-models.json: expected an object")
    return data


def normalize_model_route(route: str | None, *, strict: bool = True) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(route or MODEL_ROUTE_CHAT).strip().lower()).strip("_")
    if not normalized:
        normalized = MODEL_ROUTE_CHAT
    if strict and normalized not in MODEL_ROUTE_DESCRIPTIONS:
        valid = ", ".join(sorted(MODEL_ROUTE_DESCRIPTIONS))
        raise SystemExit(f"unknown Motoko model route {route!r}; choose one of: {valid}")
    return normalized


def model_route_env_key(route: str, key: str) -> str:
    token = normalize_model_route(route).upper()
    return f"MOTOKO_ROUTE_{token}_{key.upper()}"


def local_model_catalog_routes(catalog: dict | None = None) -> dict:
    catalog = catalog if isinstance(catalog, dict) else load_local_model_catalog()
    for key in ("routes", "model_routes"):
        routes = catalog.get(key)
        if isinstance(routes, dict):
            return routes
    return {}


def local_model_catalog_models(catalog: dict | None = None) -> dict:
    catalog = catalog if isinstance(catalog, dict) else load_local_model_catalog()
    models = catalog.get("models")
    return models if isinstance(models, dict) else {}


def catalog_task_routes(catalog: dict) -> dict | None:
    """Validate explicit task policy; absence preserves the legacy selector."""
    if "task_routes" not in catalog:
        return None
    policy = catalog["task_routes"]
    if not isinstance(policy, dict) or set(policy) != set(MODEL_ROUTE_DESCRIPTIONS):
        raise SystemExit("invalid local-models.json task_routes: expected all ten logical tasks")
    routes = local_model_catalog_routes(catalog)
    for task, references in policy.items():
        if (
            not isinstance(references, list)
            or not references
            or any(not isinstance(item, str) or not item.strip() for item in references)
            or len(set(references)) != len(references)
        ):
            raise SystemExit(f"invalid local-models.json task_routes: invalid route list for {task}")
        aliases = set(LOCAL_MODEL_ROUTE_TASK_ALIASES[task])
        for route_id in references:
            raw = routes.get(route_id)
            if not isinstance(raw, dict):
                raise SystemExit(f"invalid local-models.json task_routes: unknown route for {task}")
            endpoint = raw.get("endpoint")
            model_declared = any(
                isinstance(raw.get(key), str) and raw[key].strip()
                for key in ("model", "model_name", "modelId", "model_id")
            )
            if not isinstance(endpoint, str) or not endpoint.strip() or not model_declared:
                raise SystemExit(f"invalid local-models.json task_routes: incomplete route for {task}")
            summary = local_model_route_summary(route_id, raw, catalog)
            if not aliases.intersection(summary["tasks"]):
                raise SystemExit(f"invalid local-models.json task_routes: incompatible route for {task}")
            if not summary["endpoint"] or not summary["model"]:
                raise SystemExit(f"invalid local-models.json task_routes: incomplete route for {task}")
    return policy


def normalize_route_cache_policy(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    policy = {}
    if isinstance(raw.get("prompt"), bool):
        policy["prompt"] = raw["prompt"]
    for key in ("reuseMinTokens", "cacheRamMiB"):
        if key not in raw:
            continue
        try:
            value = int(raw.get(key))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            policy[key] = value
    for key in (
        "slotCacheMaxBytes",
        "slot_cache_max_bytes",
        "maxDiskBytes",
        "max_disk_bytes",
        "slotCacheMaxMiB",
        "slot_cache_max_mib",
        "maxDiskMiB",
        "max_disk_mib",
        "slotCacheFileBytes",
        "slot_cache_file_bytes",
        "slotFileBytes",
        "slot_file_bytes",
        "slotCacheEntryBytes",
        "slot_cache_entry_bytes",
        "slotCacheFileMiB",
        "slot_cache_file_mib",
        "slotFileMiB",
        "slot_file_mib",
        "slotCacheEntryMiB",
        "slot_cache_entry_mib",
    ):
        if key not in raw:
            continue
        try:
            value = int(raw.get(key))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            policy[key] = value
    if "slotPromptSimilarity" in raw:
        try:
            value = float(raw.get("slotPromptSimilarity"))
        except (TypeError, ValueError):
            pass
        else:
            if 0.0 <= value <= 1.0:
                policy["slotPromptSimilarity"] = value
    for key in ("metrics", "persistentSlotCache", "slotsEndpoint"):
        if isinstance(raw.get(key), bool):
            policy[key] = raw[key]
    for key in (
        "slotsEndpoint",
        "slotSavePath",
        "slot_save_path",
        "slotSaveRoot",
        "slot_save_root",
        "slotCacheBudgetProfile",
        "slot_cache_budget_profile",
        "slotCacheProfile",
        "slot_cache_profile",
        "note",
    ):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            policy[key] = value.strip()[:1000]
    for key in ("slotId", "slot_id", "persistentSlotId", "persistent_slot_id"):
        if key not in raw:
            continue
        try:
            value = int(raw.get(key))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            policy[key] = value
    return policy


def bounded_json_value(raw, *, depth: int = 0, max_depth: int = 6):
    """Return a bounded JSON-ish value suitable for local route metadata."""
    if depth > max_depth:
        return None
    if isinstance(raw, bool) or raw is None:
        return raw
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return raw
    if isinstance(raw, str):
        return raw.strip()[:2000]
    if isinstance(raw, list):
        values = []
        for item in raw[:128]:
            value = bounded_json_value(item, depth=depth + 1, max_depth=max_depth)
            if value is not None:
                values.append(value)
        return values
    if isinstance(raw, dict):
        values = {}
        for key, value in list(raw.items())[:128]:
            if not isinstance(key, str) or not key.strip():
                continue
            normalized = bounded_json_value(value, depth=depth + 1, max_depth=max_depth)
            if normalized is not None:
                values[key.strip()[:120]] = normalized
        return values
    return None


def normalize_policy_dict(raw) -> dict:
    value = bounded_json_value(raw)
    return value if isinstance(value, dict) else {}


def normalize_request_policy(raw) -> dict:
    return normalize_policy_dict(raw)


def normalize_scheduling_policy(raw) -> dict:
    return normalize_policy_dict(raw)


def normalize_safety_policy(raw) -> dict:
    return normalize_policy_dict(raw)


def normalize_idle_seconds(raw) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def normalize_endpoint_paths(raw) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    paths = []
    for item in raw:
        value = str(item).strip()
        if value.startswith("/") and value not in paths:
            paths.append(value)
    return paths


def route_int_value(raw: dict, key: str, fallback_key: str | None = None) -> int | None:
    for candidate in [key, fallback_key]:
        if not candidate or candidate not in raw:
            continue
        try:
            value = int(raw.get(candidate))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def route_string_value(raw: dict, *keys: str) -> str:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def route_profile_value(raw: dict) -> str:
    value = route_string_value(raw, "route_profile", "routeProfile", "profile")
    value = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if value == "long":
        value = "deep"
    return value if value in CHAT_ROUTE_PROFILES else ""


def route_selection(raw: dict) -> dict:
    value = raw.get("selection")
    return {str(key): item for key, item in value.items()} if isinstance(value, dict) else {}


def route_selection_default(raw: dict) -> bool:
    return route_selection(raw).get("default") is True


def route_selection_priority(raw: dict) -> int:
    try:
        return int(route_selection(raw).get("priority") or 0)
    except (TypeError, ValueError):
        return 0


def route_kv_cache_policy(raw: dict) -> dict:
    value = raw.get("kv_cache") or raw.get("kvCache")
    return {str(key): item for key, item in value.items()} if isinstance(value, dict) else {}


def route_model_name(raw: dict, catalog: dict | None = None) -> str:
    catalog = catalog if isinstance(catalog, dict) else load_local_model_catalog()
    model_ref = raw.get("model_id") or raw.get("modelId") or raw.get("model") or raw.get("model_name")
    model_record = {}
    if isinstance(model_ref, str):
        candidate = local_model_catalog_models(catalog).get(model_ref)
        if isinstance(candidate, dict):
            model_record = candidate
    for key in ("model", "model_name", "modelId", "model_id", "displayName", "id", "name"):
        value = raw.get(key) or model_record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def catalog_realm(catalog: dict | None = None) -> str:
    catalog = catalog if isinstance(catalog, dict) else load_local_model_catalog()
    manager = catalog.get("manager") if isinstance(catalog.get("manager"), dict) else {}
    realm = catalog.get("realm") or manager.get("realm") or configured_identity_realm()
    return realm.strip() if isinstance(realm, str) and realm.strip() else ""


def local_model_route_summary(route_id: str, raw: dict, catalog: dict | None = None) -> dict:
    catalog = catalog if isinstance(catalog, dict) else load_local_model_catalog()
    tasks = raw.get("tasks")
    task_set = {str(item) for item in tasks} if isinstance(tasks, list) else set()
    endpoint_paths = normalize_endpoint_paths(
        raw.get("endpoint_paths") or raw.get("endpointPaths") or raw.get("paths")
    )
    model_ref = raw.get("model_id") or raw.get("modelId") or raw.get("model")
    model_record = local_model_catalog_models(catalog).get(model_ref) if isinstance(model_ref, str) else {}
    if not isinstance(model_record, dict):
        model_record = {}
    manager = catalog.get("manager") if isinstance(catalog.get("manager"), dict) else {}
    realm = catalog_realm(catalog)
    endpoint = str(raw.get("endpoint") or "")
    if not endpoint and manager.get("kind") == "systemd-socket-worker" and realm:
        endpoint = f"unix:///run/motoko-llm/{realm}/{route_id}.sock"
    dimensions = (
        route_int_value(raw, "embedding_dimensions", "embeddingDimensions")
        or route_int_value(model_record, "embedding_dimensions", "embeddingDimensions")
        or route_int_value(raw, "dimensions")
        or route_int_value(model_record, "dimensions")
    )
    return {
        "route": route_id,
        "catalog_route": route_id,
        "kind": str(raw.get("kind") or ""),
        "model": route_model_name(raw, catalog),
        "endpoint": endpoint,
        "endpoint_paths": endpoint_paths,
        "request_path": endpoint_paths[0] if endpoint_paths else "",
        "tasks": sorted(task_set),
        "lane": route_string_value(raw, "lane"),
        "route_profile": route_profile_value(raw),
        "role": route_string_value(raw, "role"),
        "context_tokens": route_int_value(raw, "context_tokens", "contextTokens"),
        "kv_offload": raw.get("kv_offload") if isinstance(raw.get("kv_offload"), bool) else raw.get("kvOffload"),
        "kv_cache": route_kv_cache_policy(raw),
        "selection": route_selection(raw),
        "max_parallel": raw.get("maxParallel") or raw.get("max_parallel") or 1,
        "embedding_dimensions": dimensions,
        "manager_kind": str(manager.get("kind") or ""),
        "model_path": route_string_value(raw, "model_path", "modelPath", "model_file", "modelFile")
        or route_string_value(model_record, "model_path", "modelPath", "model_file", "modelFile", "path"),
        "download_url": route_string_value(raw, "download_url", "downloadUrl", "url")
        or route_string_value(model_record, "download_url", "downloadUrl", "url"),
        "download_hash": route_string_value(raw, "sha256", "hash")
        or route_string_value(model_record, "sha256", "hash"),
        "openai_compatible": bool(raw.get("openai_compatible") or raw.get("openaiCompatible")),
        "reranker_endpoint_status": str(raw.get("reranker_endpoint_status") or ""),
        "cache": normalize_route_cache_policy(raw.get("cache")),
        "request_policy": normalize_request_policy(raw.get("request_policy") or raw.get("requestPolicy")),
        "scheduling": normalize_scheduling_policy(raw.get("scheduling")),
        "idle_seconds": normalize_idle_seconds(raw.get("idle_seconds") or raw.get("idleSeconds")),
        "safety_policy": normalize_safety_policy(raw.get("safety_policy") or raw.get("safetyPolicy")),
    }


def local_model_routes_for_tasks(task_names: set[str], catalog: dict | None = None) -> list[dict]:
    catalog = catalog if isinstance(catalog, dict) else load_local_model_catalog()
    rows = []
    for route_id, raw in local_model_catalog_routes(catalog).items():
        if not isinstance(route_id, str) or not isinstance(raw, dict):
            continue
        tasks = raw.get("tasks")
        task_set = {str(item) for item in tasks} if isinstance(tasks, list) else set()
        if not (task_names & task_set):
            continue
        rows.append(local_model_route_summary(route_id, raw, catalog))
    return rows


def local_model_routes_for_capability(
    *,
    kind: str = "",
    tasks: set[str] | None = None,
    endpoint_path: str = "",
    catalog: dict | None = None,
) -> list[dict]:
    catalog = catalog if isinstance(catalog, dict) else load_local_model_catalog()
    task_set = tasks or set()
    rows = []
    for route_id, raw in local_model_catalog_routes(catalog).items():
        if not isinstance(route_id, str) or not isinstance(raw, dict):
            continue
        summary = local_model_route_summary(route_id, raw, catalog)
        matches_kind = bool(kind) and summary.get("kind") == kind
        matches_tasks = bool(task_set & set(summary.get("tasks", [])))
        matches_path = bool(endpoint_path) and endpoint_path in summary.get("endpoint_paths", [])
        if matches_kind or matches_tasks or matches_path:
            rows.append(summary)
    rows.sort(
        key=lambda row: (
            0 if endpoint_path and endpoint_path in row.get("endpoint_paths", []) else 1,
            0 if kind and row.get("kind") == kind else 1,
            str(row.get("route", "")),
        )
    )
    return rows


def local_model_route_entry_for_task(route: str, routes: dict) -> tuple[str, dict] | None:
    aliases = set(LOCAL_MODEL_ROUTE_TASK_ALIASES.get(route, (route,)))
    candidates: list[tuple[str, dict]] = []
    for route_id, raw in routes.items():
        if not isinstance(route_id, str) or not isinstance(raw, dict):
            continue
        tasks = raw.get("tasks")
        task_names = {str(item) for item in tasks} if isinstance(tasks, list) else set()
        if aliases & task_names:
            candidates.append((route_id, raw))
    if not candidates:
        return None
    if route == MODEL_ROUTE_CHAT:
        candidates.sort(
            key=lambda item: (
                0 if route_selection_default(item[1]) else 1,
                0 if route_profile_value(item[1]) == "default" else 1,
                -route_selection_priority(item[1]),
                str(item[0]),
            )
        )
        if route_selection_default(candidates[0][1]):
            return candidates[0]
    preferences = LOCAL_MODEL_ROUTE_PREFERENCES.get(route, ())
    for preferred in preferences:
        for route_id, raw in candidates:
            model_id = str(raw.get("modelId") or raw.get("model_id") or "")
            if route_id == preferred or model_id == preferred:
                return route_id, raw
    return candidates[0]


def merged_local_model_route(route: str) -> dict:
    route = normalize_model_route(route)
    catalog = load_local_model_catalog()
    routes = local_model_catalog_routes(catalog)
    task_routes = catalog_task_routes(catalog)
    route_id = task_routes[route][0] if task_routes is not None else route
    raw = routes[route_id] if task_routes is not None else (
        routes.get(route) or routes.get(route.replace("_", "-")) or routes.get(route.replace("_", "."))
    )
    if raw is None:
        selected = local_model_route_entry_for_task(route, routes)
        if selected is not None:
            route_id, raw = selected
    if raw is None:
        return {}
    if isinstance(raw, str):
        raw = {"endpoint": raw}
    if not isinstance(raw, dict):
        return {}
    info = {key: value for key, value in raw.items() if isinstance(key, str)}
    info["task_routes_managed"] = task_routes is not None
    if task_routes is not None:
        info["catalog_route"] = route_id
    else:
        info.setdefault("catalog_route", route_id)
    summary = local_model_route_summary(route_id, raw, catalog)
    if task_routes is not None:
        info["endpoint"], info["model"] = summary["endpoint"], summary["model"]
    for key in ("cache", "request_policy", "scheduling", "idle_seconds", "safety_policy"):
        value = summary.get(key)
        if value not in ({}, None):
            info[key] = value
    model_ref = info.get("model_id") or info.get("modelId") or info.get("model") or info.get("model_name")
    model_record = {}
    if isinstance(model_ref, str):
        candidate = local_model_catalog_models(catalog).get(model_ref)
        if isinstance(candidate, dict):
            model_record = candidate
    for key in ("download_url", "url", "sha256", "hash", "model_path", "modelPath", "model_file", "modelFile"):
        if key not in info and isinstance(model_record.get(key), str):
            info[key] = model_record[key]
    if "download_url" not in info:
        info["download_url"] = route_string_value(info, "downloadUrl", "url")
    if "download_hash" not in info:
        info["download_hash"] = route_string_value(info, "sha256", "hash")
    if "model_path" not in info:
        info["model_path"] = route_string_value(info, "modelPath", "model_file", "modelFile")
    if "model" not in info:
        for key in ("model_name", "modelId", "model_id", "displayName", "id", "name"):
            value = raw.get(key) or model_record.get(key)
            if isinstance(value, str) and value.strip():
                info["model"] = value.strip()
                break
    if "endpoint" not in info:
        manager = catalog.get("manager") if isinstance(catalog.get("manager"), dict) else {}
        realm = catalog_realm(catalog)
        if manager.get("kind") == "systemd-socket-worker" and realm:
            info["endpoint"] = f"unix:///run/motoko-llm/{realm}/{route_id}.sock"
    if "request_path" not in info:
        endpoint_paths = normalize_endpoint_paths(
            raw.get("endpoint_paths") or raw.get("endpointPaths") or raw.get("paths")
        )
        if endpoint_paths:
            info["endpoint_paths"] = endpoint_paths
            info["request_path"] = endpoint_paths[0]
        for key in ("path", "http_path", "openai_path"):
            value = raw.get(key)
            if isinstance(value, str) and value.startswith("/"):
                info["request_path"] = value
                break
    manager = catalog.get("manager")
    if isinstance(manager, dict) and isinstance(manager.get("kind"), str):
        info["manager_kind"] = manager["kind"]
    return info
