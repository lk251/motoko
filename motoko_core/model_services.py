"""Pure local model service formatting helpers for Motoko."""

from __future__ import annotations

from .model_routes import MODEL_ROUTE_CHAT


def local_model_helper_route(route_info: dict) -> str:
    return str(route_info.get("catalog_route") or route_info.get("route", MODEL_ROUTE_CHAT))


def parse_local_model_status(raw: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in raw.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip()
    return values


def compact_local_model_status(raw: str) -> str:
    values = parse_local_model_status(raw)
    if not values:
        return raw.strip()[:240]
    fields = []
    for key in ("route", "socket", "proxy", "backend"):
        if values.get(key):
            fields.append(f"{key}={values[key]}")
    return " ".join(fields) if fields else raw.strip()[:240]


def format_route_cache_policy(route_info: dict) -> str:
    policy = route_info.get("cache") if isinstance(route_info.get("cache"), dict) else {}
    pieces = []
    if "prompt" in policy:
        pieces.append("prompt-cache=on" if policy.get("prompt") else "prompt-cache=off")
    if "reuseMinTokens" in policy:
        pieces.append(f"reuse>={policy.get('reuseMinTokens')}tok")
    if "cacheRamMiB" in policy:
        pieces.append(f"cache-ram={policy.get('cacheRamMiB')}MiB")
    if "slotPromptSimilarity" in policy:
        pieces.append(f"similarity={policy.get('slotPromptSimilarity')}")
    if "metrics" in policy:
        pieces.append("metrics=on" if policy.get("metrics") else "metrics=off")
    if policy.get("persistentSlotCache"):
        pieces.append("persistent-slots=declared")
    elif "persistentSlotCache" in policy:
        pieces.append("persistent-slots=off")
    if route_info.get("metrics_endpoint"):
        metrics_path = route_info.get("metrics_path") or "/metrics"
        pieces.append(f"metrics-endpoint={route_info.get('metrics_endpoint')} path={metrics_path}")
    return "; cache " + ", ".join(pieces) if pieces else ""


def model_service_selector_tokens(info: dict) -> set[str]:
    tokens = {
        str(info.get("route", "")),
        str(info.get("catalog_route", "")),
        local_model_helper_route(info),
    }
    tokens.update(str(route) for route in info.get("_logical_routes", []))
    return {token for token in tokens if token}
