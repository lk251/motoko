"""Model transport and response helpers for Motoko."""

from __future__ import annotations

import contextlib
import http.client
import json
import socket
import time
import urllib.parse
import urllib.request


class UnixSocketHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, *, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self.sock = sock


def endpoint_is_unix(endpoint_text: str) -> bool:
    return str(endpoint_text).startswith("unix://")


def model_loading_response(status: int, body: str) -> bool:
    if status != 503:
        return False
    lowered = body.lower()
    return "loading model" in lowered or "model loading" in lowered


def transient_model_connection_error(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
        return True
    text = str(exc).lower()
    return (
        "connection reset by peer" in text
        or "remote end closed connection" in text
        or "broken pipe" in text
        or "connection aborted" in text
    )


def raise_if_cancelled(cancel_event) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("__motoko_stopped__")


def sleep_with_cancel(seconds: float, cancel_event) -> None:
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        raise_if_cancelled(cancel_event)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.1, remaining))


def iter_cancelable_response_lines(resp, cancel_event):
    while True:
        raise_if_cancelled(cancel_event)
        raw = resp.readline()
        if not raw:
            return
        yield raw


def model_request_timeout(endpoint_text: str, timeout: float, socket_activation_min_timeout: float) -> float:
    if endpoint_is_unix(endpoint_text):
        return max(float(timeout), socket_activation_min_timeout)
    return timeout


def route_request_policy(route_info: dict) -> dict:
    policy = route_info.get("request_policy")
    return policy if isinstance(policy, dict) else {}


def policy_section(policy: dict, *keys: str) -> dict:
    for key in keys:
        value = policy.get(key)
        if isinstance(value, dict):
            return value
    return {}


def payload_path_set(payload: dict, path: str, value) -> None:
    parts = [part for part in str(path).split(".") if part]
    if not parts:
        return
    target = payload
    for part in parts[:-1]:
        child = target.get(part)
        if not isinstance(child, dict):
            child = {}
            target[part] = child
        target = child
    target[parts[-1]] = value


def payload_path_get(payload: dict, path: str):
    target = payload
    for part in [part for part in str(path).split(".") if part]:
        if not isinstance(target, dict) or part not in target:
            return None
        target = target[part]
    return target


SAFE_SAMPLING_FIELDS = {
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "typical_p",
    "repeat_penalty",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    "mirostat",
    "mirostat_tau",
    "mirostat_eta",
}


def apply_sampling_preset(payload: dict, policy: dict, sampling_preset: str | None) -> str:
    preset_name = str(sampling_preset or "").strip()
    if not preset_name:
        return ""
    presets = policy_section(policy, "sampling_presets", "samplingPresets")
    preset = presets.get(preset_name)
    if not isinstance(preset, dict):
        return ""
    for key, value in preset.items():
        if key in SAFE_SAMPLING_FIELDS and isinstance(value, (int, float, bool, str)):
            payload[key] = value
    return preset_name


def apply_structured_output(
    payload: dict,
    policy: dict,
    *,
    json_schema=None,
    grammar: str | None = None,
) -> dict:
    structured = policy_section(policy, "structured_output", "structuredOutput")
    if structured and not structured.get("supported"):
        return {"json_schema": False, "grammar": False}
    used = {"json_schema": False, "grammar": False}
    if json_schema is not None:
        field = str(structured.get("json_schema_field") or structured.get("jsonSchemaField") or "json_schema")
        payload[field] = json_schema
        used["json_schema"] = True
    if grammar:
        field = str(structured.get("grammar_field") or structured.get("grammarField") or "grammar")
        payload[field] = grammar
        used["grammar"] = True
    return used


def apply_reasoning_policy(
    payload: dict,
    policy: dict,
    *,
    reasoning_preset: str | None = None,
    thinking_budget_tokens: int | None = None,
    enable_thinking: bool | None = None,
) -> dict:
    reasoning = policy_section(policy, "reasoning")
    if not reasoning or not reasoning.get("supported"):
        return {}
    selected_name = str(reasoning_preset or reasoning.get("default_preset") or reasoning.get("defaultPreset") or "").strip()
    presets = reasoning.get("presets") if isinstance(reasoning.get("presets"), dict) else {}
    selected = presets.get(selected_name) if selected_name else {}
    if not isinstance(selected, dict):
        selected = {}
    if enable_thinking is None and isinstance(selected.get("enable_thinking"), bool):
        enable_thinking = selected.get("enable_thinking")
    if thinking_budget_tokens is None and selected.get("thinking_budget_tokens") is not None:
        try:
            thinking_budget_tokens = int(selected.get("thinking_budget_tokens"))
        except (TypeError, ValueError):
            thinking_budget_tokens = None
    enable_field = str(
        reasoning.get("per_request_enable_field")
        or reasoning.get("perRequestEnableField")
        or "chat_template_kwargs.enable_thinking"
    )
    budget_field = str(
        reasoning.get("per_request_budget_field")
        or reasoning.get("perRequestBudgetField")
        or "thinking_budget_tokens"
    )
    if enable_thinking is not None:
        payload_path_set(payload, enable_field, bool(enable_thinking))
    if thinking_budget_tokens is not None and thinking_budget_tokens >= -1:
        payload_path_set(payload, budget_field, int(thinking_budget_tokens))
    return {
        "reasoning_preset": selected_name,
        "enable_field": enable_field,
        "budget_field": budget_field,
        "thinking_budget_tokens": payload_path_get(payload, budget_field),
        "enable_thinking": payload_path_get(payload, enable_field),
        "format": str(reasoning.get("format") or ""),
    }


def chat_completion_payload(
    route_info: dict,
    messages: list[dict],
    *,
    temperature: float,
    stream: bool,
    sampling_preset: str | None = None,
    json_schema=None,
    grammar: str | None = None,
    reasoning_preset: str | None = None,
    thinking_budget_tokens: int | None = None,
    enable_thinking: bool | None = None,
    max_tokens: int | None = None,
) -> dict:
    payload = {
        "model": route_info["model"],
        "messages": messages,
        "temperature": temperature,
        "stream": stream,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max(1, int(max_tokens))
    policy = route_request_policy(route_info)
    apply_sampling_preset(payload, policy, sampling_preset)
    apply_structured_output(payload, policy, json_schema=json_schema, grammar=grammar)
    apply_reasoning_policy(
        payload,
        policy,
        reasoning_preset=reasoning_preset,
        thinking_budget_tokens=thinking_budget_tokens,
        enable_thinking=enable_thinking,
    )
    return payload


def request_policy_metadata(
    route_info: dict,
    payload: dict,
    *,
    sampling_preset: str | None = None,
    json_schema=None,
    grammar: str | None = None,
    reasoning_preset: str | None = None,
) -> dict:
    policy = route_request_policy(route_info)
    reasoning = policy_section(policy, "reasoning")
    structured = policy_section(policy, "structured_output", "structuredOutput")
    json_schema_field = str(structured.get("json_schema_field") or structured.get("jsonSchemaField") or "json_schema")
    grammar_field = str(structured.get("grammar_field") or structured.get("grammarField") or "grammar")
    budget_field = str(
        reasoning.get("per_request_budget_field")
        or reasoning.get("perRequestBudgetField")
        or "thinking_budget_tokens"
    )
    enable_field = str(
        reasoning.get("per_request_enable_field")
        or reasoning.get("perRequestEnableField")
        or "chat_template_kwargs.enable_thinking"
    )
    return {
        "sampling_preset": str(sampling_preset or ""),
        "structured_json_schema": json_schema_field in payload,
        "structured_grammar": grammar_field in payload,
        "reasoning_preset": str(reasoning_preset or ""),
        "reasoning_format": str(reasoning.get("format") or "") if isinstance(reasoning, dict) else "",
        "thinking_budget_tokens": payload_path_get(payload, budget_field),
        "enable_thinking": payload_path_get(payload, enable_field),
        "cache_measurement_supported": bool(
            policy_section(policy, "cache_measurement", "cacheMeasurement").get("supported")
        ),
    }


def model_request_failure_detail(prefix: str, exc: BaseException, hint: str = "") -> str:
    detail = f"{prefix}: {exc}"
    if hint:
        detail += "\n" + hint
    return detail


def parse_openai_stream_line_parts(raw: bytes) -> tuple[bool, str, str]:
    line = raw.decode("utf-8", errors="replace").strip()
    if not line or not line.startswith("data:"):
        return False, "", ""
    data = line[5:].strip()
    if data == "[DONE]":
        return True, "", ""
    try:
        event = json.loads(data)
    except json.JSONDecodeError:
        return False, "", ""
    choices = event.get("choices") or []
    if not choices:
        return False, "", ""
    delta = choices[0].get("delta") or {}
    reasoning = (
        delta.get("reasoning_content")
        or delta.get("reasoning")
        or delta.get("reasoningContent")
        or ""
    )
    return False, delta.get("content") or "", reasoning


def parse_openai_stream_line(raw: bytes) -> tuple[bool, str]:
    done, content, _reasoning = parse_openai_stream_line_parts(raw)
    return done, content


@contextlib.contextmanager
def open_model_response(
    route_info: dict,
    payload: dict,
    *,
    timeout: float,
    unix_request_path: str,
    socket_activation_min_timeout: float,
    model_loading_retry_seconds: float,
    cancel_event=None,
    on_connection=None,
    on_response=None,
):
    endpoint_text = str(route_info["endpoint"])
    request_timeout = model_request_timeout(endpoint_text, timeout, socket_activation_min_timeout)
    data = json.dumps(payload).encode("utf-8")
    if endpoint_is_unix(endpoint_text):
        parsed = urllib.parse.urlparse(endpoint_text)
        socket_path = urllib.parse.unquote(parsed.path)
        if not socket_path:
            raise SystemExit(f"model request failed: empty Unix socket endpoint for route {route_info['route']}")
        request_path = str(route_info.get("request_path") or unix_request_path)
        deadline = time.monotonic() + request_timeout
        loading_attempts = 0
        transient_attempts = 0
        while True:
            raise_if_cancelled(cancel_event)
            remaining = max(1.0, deadline - time.monotonic())
            conn = UnixSocketHTTPConnection(socket_path, timeout=remaining)
            try:
                if on_connection is not None:
                    on_connection(conn)
                conn.request(
                    "POST",
                    request_path,
                    body=data,
                    headers={"Content-Type": "application/json", "Host": "localhost"},
                )
                resp = conn.getresponse()
                if on_response is not None:
                    on_response(resp)
                if resp.status >= 400:
                    body = resp.read(1200).decode("utf-8", errors="replace")
                    resp.close()
                    if on_response is not None:
                        on_response(None)
                    if model_loading_response(resp.status, body) and time.monotonic() < deadline:
                        loading_attempts += 1
                        sleep_for = min(model_loading_retry_seconds, max(0.1, deadline - time.monotonic()))
                        sleep_with_cancel(sleep_for, cancel_event)
                        continue
                    suffix = f" after {loading_attempts} loading retries" if loading_attempts else ""
                    raise OSError(f"model endpoint returned HTTP {resp.status}{suffix}: {body}")
                try:
                    yield resp
                finally:
                    if on_response is not None:
                        on_response(None)
                    resp.close()
                return
            except (OSError, http.client.HTTPException) as exc:
                if transient_model_connection_error(exc) and time.monotonic() < deadline:
                    transient_attempts += 1
                    loading_attempts += 1
                    sleep_for = min(model_loading_retry_seconds, max(0.1, deadline - time.monotonic()))
                    sleep_with_cancel(sleep_for, cancel_event)
                    continue
                suffix = (
                    f" after {transient_attempts} transient "
                    f"{'retry' if transient_attempts == 1 else 'retries'}"
                    if transient_attempts
                    else ""
                )
                if suffix:
                    raise OSError(f"{exc}{suffix}") from exc
                raise
            finally:
                if on_connection is not None:
                    on_connection(None)
                conn.close()
        return

    raise_if_cancelled(cancel_event)
    req = urllib.request.Request(
        endpoint_text,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=request_timeout) as resp:
        if on_response is not None:
            on_response(resp)
        try:
            yield resp
        finally:
            if on_response is not None:
                on_response(None)


def read_json_response(resp) -> str:
    event = json.loads(resp.read().decode("utf-8", errors="replace"))
    choices = event.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return message.get("content") or ""
