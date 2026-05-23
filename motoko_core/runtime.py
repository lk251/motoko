"""Runtime context objects for Motoko live subsystems."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


RUNTIME_CONTEXT_SCHEMA = "runtime-context-v1"


@dataclass(frozen=True)
class RuntimePaths:
    """Realm-local path summary.

    The values are intentionally paths only. Callers decide whether a path is
    safe to print in a user-facing report.
    """

    state_root: Path
    config_root: Path
    conversations_dir: Path | None = None
    indexes_dir: Path | None = None
    vector_stores_dir: Path | None = None
    evidence_stores_dir: Path | None = None

    def public_dict(self) -> dict:
        return {
            "state_root": str(self.state_root),
            "config_root": str(self.config_root),
            "conversations_dir": str(self.conversations_dir) if self.conversations_dir else "",
            "indexes_dir": str(self.indexes_dir) if self.indexes_dir else "",
            "vector_stores_dir": str(self.vector_stores_dir) if self.vector_stores_dir else "",
            "evidence_stores_dir": str(self.evidence_stores_dir) if self.evidence_stores_dir else "",
        }


@dataclass(frozen=True)
class RuntimeRoute:
    route: str
    model: str
    endpoint: str
    lane: str = ""
    kind: str = ""
    catalog_route: str = ""
    max_parallel: int = 1

    @classmethod
    def from_mapping(cls, route: str, data: Mapping) -> "RuntimeRoute":
        try:
            max_parallel = int(data.get("max_parallel") or data.get("maxParallel") or 1)
        except (TypeError, ValueError):
            max_parallel = 1
        return cls(
            route=str(data.get("route") or route),
            model=str(data.get("model") or ""),
            endpoint=str(data.get("endpoint") or ""),
            lane=str(data.get("lane") or ""),
            kind=str(data.get("kind") or ""),
            catalog_route=str(data.get("catalog_route") or data.get("catalog") or ""),
            max_parallel=max(1, max_parallel),
        )

    def content_free_dict(self) -> dict:
        return {
            "route": self.route,
            "model": self.model,
            "endpoint_kind": "unix" if self.endpoint.startswith("unix://") else "http",
            "lane": self.lane,
            "kind": self.kind,
            "catalog_route": self.catalog_route,
            "max_parallel": self.max_parallel,
        }


@dataclass(frozen=True)
class RuntimeContext:
    realm: str
    identity: str
    app_version: str
    revision: str
    permissions: str
    paths: RuntimePaths
    routes: tuple[RuntimeRoute, ...] = field(default_factory=tuple)
    schema: str = RUNTIME_CONTEXT_SCHEMA

    def route(self, name: str) -> RuntimeRoute | None:
        for item in self.routes:
            if item.route == name or item.catalog_route == name:
                return item
        return None

    def content_free_dict(self) -> dict:
        return {
            "schema": self.schema,
            "realm": self.realm,
            "identity": self.identity,
            "app_version": self.app_version,
            "revision": self.revision,
            "permissions": self.permissions,
            "paths": self.paths.public_dict(),
            "routes": [route.content_free_dict() for route in self.routes],
        }


def make_runtime_context(
    *,
    realm: str,
    identity: str,
    app_version: str,
    revision: str,
    permissions: str,
    paths: RuntimePaths,
    routes: list[Mapping] | tuple[Mapping, ...] = (),
) -> RuntimeContext:
    route_rows = tuple(
        RuntimeRoute.from_mapping(str(row.get("route") or row.get("name") or ""), row)
        for row in routes
        if isinstance(row, Mapping)
    )
    return RuntimeContext(
        realm=str(realm or ""),
        identity=str(identity or ""),
        app_version=str(app_version or ""),
        revision=str(revision or ""),
        permissions=str(permissions or ""),
        paths=paths,
        routes=route_rows,
    )
