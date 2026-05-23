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


def chat_completion_payload(
    route_info: dict,
    messages: list[dict],
    *,
    temperature: float,
    stream: bool,
) -> dict:
    return {
        "model": route_info["model"],
        "messages": messages,
        "temperature": temperature,
        "stream": stream,
    }


def model_request_failure_detail(prefix: str, exc: BaseException, hint: str = "") -> str:
    detail = f"{prefix}: {exc}"
    if hint:
        detail += "\n" + hint
    return detail


def parse_openai_stream_line(raw: bytes) -> tuple[bool, str]:
    line = raw.decode("utf-8", errors="replace").strip()
    if not line or not line.startswith("data:"):
        return False, ""
    data = line[5:].strip()
    if data == "[DONE]":
        return True, ""
    try:
        event = json.loads(data)
    except json.JSONDecodeError:
        return False, ""
    choices = event.get("choices") or []
    if not choices:
        return False, ""
    delta = choices[0].get("delta") or {}
    return False, delta.get("content") or ""


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
