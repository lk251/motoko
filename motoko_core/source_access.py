"""Descriptor-based regular-file reads inside explicitly authorized roots."""

from __future__ import annotations

import contextlib
import errno
import os
import pathlib
import stat


SOURCE_BOUNDARY_VERSION = "regular-contained-source-v1"


def index_source_boundary_reason(index: dict) -> str:
    """Older summaries cannot prove which resolved files supplied their bytes.

    Do not bless legacy content from its current path alone: a formerly unsafe
    symlink may already have changed. Reprocessing is the conservative upgrade.
    """
    policy = index.get("selection_policy") or {}
    if policy.get("source_boundary") != SOURCE_BOUNDARY_VERSION:
        return "index predates contained-source ingestion; source reprocessing required"
    root = str(index.get("root", ""))
    for item in index.get("files", []):
        if item.get("source_boundary") != SOURCE_BOUNDARY_VERSION or item.get("source_root") != root:
            return "index contains sources without verified containment; source reprocessing required"
    return ""


def source_boundary_audit(index: dict) -> dict:
    reason = index_source_boundary_reason(index)
    return {
        "schema": "source-boundary-audit-v1",
        "policy": SOURCE_BOUNDARY_VERSION,
        "status": "reprocess-required" if reason else "verified",
        "reason": reason,
        "source_count": len(index.get("files", [])),
    }


def artifact_source_references(value) -> set[tuple[str, str]]:
    """Extract typed source links without confusing prose with identifiers."""
    singular = {
        "index": "index", "index_id": "index", "source_index": "index",
        "source_index_id": "index", "created_by_index_id": "index",
        "topic": "topic", "topic_id": "topic", "source_topic": "topic",
        "dossier": "dossier", "dossier_id": "dossier", "source_dossier": "dossier",
    }
    plural = {
        "indexes": "index", "index_ids": "index", "source_indexes": "index",
        "source_index_ids": "index", "topics": "topic", "topic_ids": "topic",
        "dossiers": "dossier", "dossier_ids": "dossier",
    }
    refs = set()

    def add(kind, item):
        identifier = item.get("id", "") if isinstance(item, dict) else item
        if isinstance(identifier, str) and identifier:
            refs.add((kind, identifier))

    def visit(item):
        if isinstance(item, dict):
            if item.get("kind") in {"index", "topic", "dossier"}:
                add(item["kind"], item)
            for key, child in item.items():
                if key in singular:
                    add(singular[key], child)
                elif key in plural and isinstance(child, list):
                    for row in child:
                        add(plural[key], row)
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return refs


@contextlib.contextmanager
def open_source(path: pathlib.Path, *, roots):
    """Resolve links within roots, then open without following any changed link.

    Callers supply canonical authorized roots. Resolving the source is not a
    read of its contents; every component of the subsequent open uses nofollow.
    Nonblocking open and fstat reject FIFOs/devices without consuming them.
    """
    try:
        resolved = pathlib.Path(path).expanduser().resolve(strict=True)
    except RuntimeError as exc:
        raise OSError(errno.ELOOP, "source contains a symlink loop", str(path)) from exc
    if not any(resolved.is_relative_to(pathlib.Path(root).absolute()) for root in roots):
        raise PermissionError(errno.EACCES, "source is outside the authorized root", str(path))
    directory = os.open(resolved.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    descriptor = None
    try:
        for part in resolved.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(resolved.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError(errno.EINVAL, "source must be a regular file", str(path))
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None  # fdopen owns it, including exception cleanup.
            yield stream
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)
