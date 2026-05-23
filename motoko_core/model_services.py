"""Pure local model service formatting helpers for Motoko."""

from __future__ import annotations

import grp
import os
import pathlib
import subprocess
import urllib.parse

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


def run_local_model_helper_process(
    command: str,
    route_info: dict,
    *,
    timeout: float,
    helper_path: str | None,
) -> str:
    if not helper_path:
        raise FileNotFoundError("motoko-model helper is not on PATH")
    route = local_model_helper_route(route_info)
    result = subprocess.run(
        [helper_path, command, route],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    detail = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if result.returncode != 0:
        raise RuntimeError(detail or f"motoko-model {command} {route} failed")
    return detail


def local_model_status_text_with_runner(route_info: dict, run_helper) -> str:
    try:
        return run_helper("status", route_info)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return f"motoko-model status could not run: {exc}"


def local_model_status_is_activating(status: str) -> bool:
    status = status.lower()
    if not status:
        return False
    if "backend=activating" in status or "proxy=activating" in status:
        return True
    return "loading model" in status or "model loading" in status


def group_name_for_gid(gid: int) -> str:
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError:
        return str(gid)


def local_model_verify_hint(
    route_info: dict,
    *,
    status_provider,
    helper_available: bool,
    current_groups: set[int] | None = None,
) -> str:
    endpoint_text = str(route_info.get("endpoint", ""))
    if not endpoint_text.startswith("unix://"):
        return ""
    lines = []
    parsed = urllib.parse.urlparse(endpoint_text)
    socket_path = pathlib.Path(urllib.parse.unquote(parsed.path))
    try:
        parent_stat = socket_path.parent.stat()
    except OSError:
        parent_stat = None
    if parent_stat is not None:
        groups = current_groups if current_groups is not None else set(os.getgroups())
        group_name = group_name_for_gid(parent_stat.st_gid)
        if parent_stat.st_gid not in groups:
            current_names = ", ".join(group_name_for_gid(gid) for gid in sorted(groups))
            lines.append(
                f"current process groups do not include {group_name}; groups are: {current_names or 'none'}"
            )
            lines.append(
                f"start Motoko from a fresh login/tmux session after the rebuild, or run: sg {group_name} -c 'motoko'"
            )
    status = status_provider(route_info)
    if status:
        lines.append("motoko-model status:")
        lines.append(status[:1200])
    model_path = str(route_info.get("model_path") or "")
    if model_path:
        try:
            if not pathlib.Path(model_path).exists():
                lines.append(f"declared model file is missing: {model_path}")
        except OSError as exc:
            lines.append(f"declared model file could not be checked: {exc}")
    if helper_available:
        lines.append(f"verify declared model files with: motoko-model verify {local_model_helper_route(route_info)}")
    else:
        lines.append("motoko-model helper is not on PATH")
    if route_info.get("download_url"):
        lines.append(f"download: {route_info['download_url']}")
    if route_info.get("download_hash"):
        lines.append(f"hash: {route_info['download_hash']}")
    return "\n".join(lines)
