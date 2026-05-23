"""Live model route management boundary for Motoko."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping


MODEL_ROUTE_MANAGER_SCHEMA = "model-route-manager-v1"


@dataclass(frozen=True)
class RouteReadiness:
    route: str
    endpoint_kind: str
    active: bool
    activating: bool
    status_text: str
    verify_hint: str = ""

    def content_free_dict(self) -> dict:
        return {
            "schema": MODEL_ROUTE_MANAGER_SCHEMA,
            "route": self.route,
            "endpoint_kind": self.endpoint_kind,
            "active": self.active,
            "activating": self.activating,
            "status_text": self.status_text,
            "has_verify_hint": bool(self.verify_hint),
        }


class ModelRouteManager:
    """Content-free facade around approved local model route helpers."""

    def __init__(
        self,
        *,
        route_provider: Callable[[str], Mapping],
        status_provider: Callable[[Mapping], str],
        verify_hint_provider: Callable[[Mapping], str],
        activating_detector: Callable[[str], bool],
    ) -> None:
        self.route_provider = route_provider
        self.status_provider = status_provider
        self.verify_hint_provider = verify_hint_provider
        self.activating_detector = activating_detector

    def readiness(self, route_name: str) -> RouteReadiness:
        route = self.route_provider(route_name)
        endpoint = str(route.get("endpoint", ""))
        endpoint_kind = "unix" if endpoint.startswith("unix://") else "http"
        status = self.status_provider(route) if endpoint_kind == "unix" else "not a NixOS Unix-socket route"
        activating = self.activating_detector(status)
        active = "backend=active" in status or "active" in status.lower()
        hint = self.verify_hint_provider(route) if endpoint_kind == "unix" else ""
        return RouteReadiness(
            route=str(route.get("route") or route_name),
            endpoint_kind=endpoint_kind,
            active=active,
            activating=activating,
            status_text=status.strip() or "unknown",
            verify_hint=hint,
        )

    def content_free_report(self, route_name: str) -> str:
        row = self.readiness(route_name)
        lines = [
            f"model route manager: {MODEL_ROUTE_MANAGER_SCHEMA}",
            f"route: {row.route}",
            f"endpoint kind: {row.endpoint_kind}",
            f"active: {row.active}",
            f"activating: {row.activating}",
            f"status: {row.status_text}",
        ]
        if row.verify_hint:
            lines.append("verify hint available: yes")
        return "\n".join(lines)
