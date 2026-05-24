"""Pure local model service formatting helpers for Motoko."""

from __future__ import annotations

import grp
import os
import pathlib
import re
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
    if "slotsEndpoint" in policy:
        slots_endpoint = policy.get("slotsEndpoint")
        if isinstance(slots_endpoint, str):
            pieces.append(f"slots-endpoint={slots_endpoint}")
        else:
            pieces.append("slots-endpoint=on" if slots_endpoint else "slots-endpoint=off")
    slot_id = policy.get("slotId", policy.get("slot_id", policy.get("persistentSlotId", policy.get("persistent_slot_id"))))
    if slot_id is not None:
        pieces.append(f"slot-id={slot_id}")
    slot_path = (
        policy.get("slotSavePath")
        or policy.get("slot_save_path")
        or policy.get("slotSaveRoot")
        or policy.get("slot_save_root")
    )
    if isinstance(slot_path, str) and slot_path.strip():
        pieces.append(f"slot-save-path={slot_path.strip()[:160]}")
    if route_info.get("metrics_endpoint"):
        metrics_path = route_info.get("metrics_path") or "/metrics"
        pieces.append(f"metrics-endpoint={route_info.get('metrics_endpoint')} path={metrics_path}")
    return "; cache " + ", ".join(pieces) if pieces else ""


def format_route_request_policy(route_info: dict) -> str:
    policy = route_info.get("request_policy") if isinstance(route_info.get("request_policy"), dict) else {}
    if not policy:
        return ""
    pieces = []
    sampling = policy.get("sampling_presets") or policy.get("samplingPresets")
    if isinstance(sampling, dict) and sampling:
        pieces.append("sampling=" + "/".join(sorted(str(key) for key in sampling)[:8]))
    structured = policy.get("structured_output") or policy.get("structuredOutput")
    if isinstance(structured, dict) and structured.get("supported"):
        fields = []
        if structured.get("json_schema_field") or structured.get("jsonSchemaField"):
            fields.append(str(structured.get("json_schema_field") or structured.get("jsonSchemaField")))
        if structured.get("grammar_field") or structured.get("grammarField"):
            fields.append(str(structured.get("grammar_field") or structured.get("grammarField")))
        pieces.append("structured=on" + (f"({','.join(fields)})" if fields else ""))
    reasoning = policy.get("reasoning")
    if isinstance(reasoning, dict) and reasoning.get("supported"):
        presets = reasoning.get("presets") if isinstance(reasoning.get("presets"), dict) else {}
        preset_text = "/" + "/".join(sorted(str(key) for key in presets)[:8]) if presets else ""
        fmt = str(reasoning.get("format") or "").strip()
        pieces.append("reasoning=on" + (f":{fmt}" if fmt else "") + preset_text)
    measurement = policy.get("cache_measurement") or policy.get("cacheMeasurement")
    if isinstance(measurement, dict) and measurement.get("supported"):
        pieces.append("cache-measurement=on")
    return "; request " + ", ".join(pieces) if pieces else ""


def format_route_scheduling_policy(route_info: dict) -> str:
    scheduling = route_info.get("scheduling") if isinstance(route_info.get("scheduling"), dict) else {}
    pieces = []
    if route_info.get("idle_seconds") is not None:
        pieces.append(f"idle={route_info.get('idle_seconds')}s")
    for key in ("lane", "parallelSlots", "warmup", "residency"):
        value = scheduling.get(key)
        if isinstance(value, (str, int, float, bool)):
            pieces.append(f"{key}={value}")
    if isinstance(scheduling.get("fanout"), bool):
        pieces.append("fanout=on" if scheduling.get("fanout") else "fanout=off")
    return "; scheduling " + ", ".join(pieces) if pieces else ""


def format_route_safety_policy(route_info: dict) -> str:
    policy = route_info.get("safety_policy") if isinstance(route_info.get("safety_policy"), dict) else {}
    disabled = policy.get("disabled_server_surfaces") or policy.get("disabledServerSurfaces")
    if isinstance(disabled, list) and disabled:
        values = [str(item) for item in disabled[:12]]
        return "; safety disabled=" + "/".join(values)
    return ""


def model_service_selector_tokens(info: dict) -> set[str]:
    tokens = {
        str(info.get("route", "")),
        str(info.get("catalog_route", "")),
        local_model_helper_route(info),
    }
    tokens.update(str(route) for route in info.get("_logical_routes", []))
    return {token for token in tokens if token}


def add_model_service_route(
    rows: dict[str, dict],
    info: dict,
    *,
    logical_route: str = "",
    summary: dict | None = None,
) -> None:
    service_route = local_model_helper_route(info)
    if not service_route:
        return
    endpoint_text = str(info.get("endpoint") or "")
    if not endpoint_text.startswith("unix://") and not info.get("manager_kind"):
        return
    row = rows.get(service_route)
    if row is None:
        row = dict(info)
        row["_logical_routes"] = []
        row["_tasks"] = []
        row["_kind"] = ""
        row["_embedding_dimensions"] = None
        rows[service_route] = row
    if logical_route and logical_route not in row["_logical_routes"]:
        row["_logical_routes"].append(logical_route)
    if summary:
        row["_kind"] = str(summary.get("kind") or row.get("_kind") or "")
        row["_tasks"] = list(summary.get("tasks") or row.get("_tasks") or [])
        row["_embedding_dimensions"] = summary.get("embedding_dimensions") or row.get("_embedding_dimensions")
        row["max_parallel"] = summary.get("max_parallel") or row.get("max_parallel") or 1
        if not row.get("model"):
            row["model"] = summary.get("model", "")
        if not row.get("endpoint"):
            row["endpoint"] = summary.get("endpoint", "")
        if not row.get("manager_kind"):
            row["manager_kind"] = summary.get("manager_kind", "")
        if not row.get("request_path"):
            row["request_path"] = summary.get("request_path", "")
        if not row.get("endpoint_paths"):
            row["endpoint_paths"] = summary.get("endpoint_paths", [])
        for key in ("cache", "request_policy", "scheduling", "idle_seconds", "safety_policy"):
            if key in summary and not row.get(key):
                row[key] = summary.get(key)


def build_model_service_rows(
    configured_routes: list[tuple[str, dict]],
    catalog_summaries: list[tuple[str, dict]],
    *,
    default_request_path: str,
) -> list[dict]:
    rows: dict[str, dict] = {}
    for logical_route, info in configured_routes:
        add_model_service_route(rows, info, logical_route=logical_route)
    for route_id, summary in catalog_summaries:
        info = {
            "route": route_id,
            "catalog_route": route_id,
            "endpoint": summary.get("endpoint", ""),
            "model": summary.get("model", ""),
            "request_path": summary.get("request_path") or default_request_path,
            "endpoint_paths": summary.get("endpoint_paths", []),
            "manager_kind": summary.get("manager_kind", ""),
            "model_path": summary.get("model_path", ""),
            "max_parallel": summary.get("max_parallel") or 1,
            "cache": summary.get("cache", {}),
            "request_policy": summary.get("request_policy", {}),
            "scheduling": summary.get("scheduling", {}),
            "idle_seconds": summary.get("idle_seconds"),
            "safety_policy": summary.get("safety_policy", {}),
            "description": ", ".join(summary.get("tasks", [])),
        }
        add_model_service_route(rows, info, summary=summary)
    return list(rows.values())


def resolve_model_service_route(rows: list[dict], selector: str) -> dict:
    selector = selector.strip()
    if not selector:
        raise SystemExit("usage: /models [ROUTE] or /model-stop ROUTE")
    for row in rows:
        if selector in model_service_selector_tokens(row):
            return row
    normalized = re.sub(r"[^a-z0-9]+", "_", selector.lower()).strip("_")
    matches = [
        row
        for row in rows
        if any(
            re.sub(r"[^a-z0-9]+", "_", token.lower()).strip("_").startswith(normalized)
            for token in model_service_selector_tokens(row)
        )
    ]
    if len(matches) == 1:
        return matches[0]
    available = ", ".join(local_model_helper_route(row) for row in rows) or "none"
    if matches:
        raise SystemExit(f"ambiguous model route {selector!r}; choose one of: {available}")
    raise SystemExit(f"unknown model route {selector!r}; choose one of: {available}")


def format_model_service_status(info: dict, *, include_status: bool = True, status_provider=None) -> str:
    route_name = local_model_helper_route(info)
    lines = [f"- {route_name}: {info.get('model', '') or '(model unknown)'}"]
    endpoint_text = str(info.get("endpoint") or "")
    if endpoint_text:
        lines.append(f"  endpoint: {endpoint_text}")
    logical = ", ".join(info.get("_logical_routes", []) or [])
    if logical:
        lines.append(f"  logical routes: {logical}")
    kind = str(info.get("_kind") or "")
    tasks = ", ".join(info.get("_tasks", []) or [])
    if kind or tasks:
        lines.append(f"  catalog: kind={kind or '-'} tasks={tasks or '-'}")
    if info.get("_embedding_dimensions"):
        lines.append(f"  embedding dimensions: {info.get('_embedding_dimensions')}")
    lines.append(f"  max parallel: {info.get('max_parallel', 1)}")
    if info.get("idle_seconds") is not None:
        lines.append(f"  idle seconds: {info.get('idle_seconds')}")
    cache_policy = format_route_cache_policy(info)
    if cache_policy:
        lines.append(f"  {cache_policy.lstrip('; ')}")
    request_policy = format_route_request_policy(info)
    if request_policy:
        lines.append(f"  {request_policy.lstrip('; ')}")
    scheduling_policy = format_route_scheduling_policy(info)
    if scheduling_policy:
        lines.append(f"  {scheduling_policy.lstrip('; ')}")
    safety_policy = format_route_safety_policy(info)
    if safety_policy:
        lines.append(f"  {safety_policy.lstrip('; ')}")
    if info.get("manager_kind"):
        lines.append(f"  manager: {info.get('manager_kind')}")
    if include_status and endpoint_text.startswith("unix://") and status_provider is not None:
        raw = status_provider(info)
        values = parse_local_model_status(raw)
        lines.append(f"  status source: motoko-model status {route_name}")
        if values:
            state = " ".join(
                f"{key}={values[key]}"
                for key in ("socket", "proxy", "backend")
                if values.get(key)
            )
            if state:
                lines.append(f"  state: {state}")
            if values.get("cache"):
                lines.append(f"  cache: {values['cache']}")
            for key in (
                "resident",
                "loaded",
                "active_requests",
                "requests",
                "vram_mib",
                "gpu_memory_mib",
                "last_exit",
                "last_error",
            ):
                if values.get(key):
                    lines.append(f"  {key}: {values[key]}")
        elif raw.strip():
            lines.append(f"  status: {raw.strip()[:240]}")
    elif include_status:
        lines.append("  status source: not a NixOS Unix-socket route")
    return "\n".join(lines)


def format_model_services_report(
    rows: list[dict],
    *,
    current_endpoint: str,
    status_formatter,
) -> str:
    if not rows:
        return "\n".join(
            [
                "Model services:",
                "No NixOS local model service routes are declared for this realm.",
                f"Current endpoint: {current_endpoint}",
            ]
        )
    header = [
        "Model services:",
        "status source: motoko-model status ROUTE (content-free)",
        "control: /model-stop ROUTE uses motoko-model stop ROUTE; Motoko never calls systemctl",
        "metrics: /model-metrics ROUTE uses motoko-model metrics ROUTE when declared by NixOS",
        "note: backend=active is service/process state; it does not prove full weights are resident in VRAM",
    ]
    return "\n".join(header) + "\n\n" + "\n\n".join(status_formatter(row) for row in rows)


def format_model_stop_report(route_name: str, *, before: str, output: str, after: str) -> str:
    lines = [
        f"model stop requested: {route_name}",
        f"control source: motoko-model stop {route_name}",
    ]
    if before:
        lines.append(f"before: {before}")
    if output.strip():
        lines.append(f"helper: {output.strip()[:500]}")
    if after:
        lines.append(f"after: {after}")
    return "\n".join(lines)


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
