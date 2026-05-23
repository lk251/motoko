"""Model transport and response helpers for Motoko."""

from __future__ import annotations

import http.client
import json
import socket
import time


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


def read_json_response(resp) -> str:
    event = json.loads(resp.read().decode("utf-8", errors="replace"))
    choices = event.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return message.get("content") or ""

