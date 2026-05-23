"""Corpus selection, skip, and freshness helpers for Motoko."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import pathlib


AUTO_INDEX_GLOB = "auto"
TEXT_SAMPLE_BYTES = 8192
MOTOKO_IGNORE_FILE = ".motokoignore"
SOURCE_SELECTION_SCHEMA_VERSION = "source-selection-v1"
MAX_INDEX_IGNORE_EXAMPLES = 8

SKIP_INDEX_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".cache",
    "node_modules",
}
SKIP_INDEX_FILE_NAMES = {
    MOTOKO_IGNORE_FILE,
}


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_under(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_probably_text_file(path: pathlib.Path, *, sample_bytes: int = TEXT_SAMPLE_BYTES) -> bool:
    try:
        with path.open("rb") as fh:
            sample = fh.read(sample_bytes)
    except OSError:
        return False
    if not sample:
        return True
    if b"\x00" in sample:
        return False
    decoded = sample.decode("utf-8", errors="replace")
    if not decoded:
        return False
    replacement_ratio = decoded.count("\ufffd") / len(decoded)
    if replacement_ratio > 0.05:
        return False
    control_chars = sum(
        1
        for char in decoded
        if ord(char) < 32 and char not in "\n\r\t\f\b"
    )
    return control_chars / len(decoded) <= 0.10


def source_selection_mode(pattern: str | None) -> str:
    return "auto-text-v1" if (pattern or AUTO_INDEX_GLOB) == AUTO_INDEX_GLOB else "glob-text-v1"


def motoko_ignore_path(root: pathlib.Path) -> pathlib.Path | None:
    if root.is_dir():
        return root / MOTOKO_IGNORE_FILE
    return None


def parse_motoko_ignore(root: pathlib.Path) -> tuple[list[dict], dict]:
    ignore_path = motoko_ignore_path(root)
    info = {
        "path": str(ignore_path) if ignore_path is not None else "",
        "exists": False,
        "sha256": "",
        "rules": [],
    }
    if ignore_path is None or not ignore_path.exists():
        return [], info
    try:
        raw = ignore_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"{ignore_path}: must be UTF-8 text: {exc}") from exc
    except OSError as exc:
        raise SystemExit(f"{ignore_path}: cannot read corpus ignore file: {exc}") from exc

    info["exists"] = True
    info["sha256"] = sha256_hex(raw.encode("utf-8"))
    rules: list[dict] = []
    for line_number, line in enumerate(raw.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("!"):
            raise SystemExit(
                f"{ignore_path}:{line_number}: negation patterns are not supported in {MOTOKO_IGNORE_FILE}"
            )
        while stripped.startswith("./"):
            stripped = stripped[2:]
        anchored = stripped.startswith("/")
        if anchored:
            stripped = stripped[1:]
        directory_only = stripped.endswith("/")
        stripped = stripped.strip("/")
        if not stripped:
            continue
        rules.append(
            {
                "pattern": stripped,
                "anchored": anchored,
                "directory_only": directory_only,
                "line": line_number,
            }
        )
    info["rules"] = rules
    return rules, info


def document_selection_policy(root: pathlib.Path, pattern: str | None) -> dict:
    normalized = (pattern or AUTO_INDEX_GLOB).strip() or AUTO_INDEX_GLOB
    rules, ignore_info = parse_motoko_ignore(root)
    policy = {
        "schema": SOURCE_SELECTION_SCHEMA_VERSION,
        "mode": source_selection_mode(normalized),
        "glob": normalized,
        "motokoignore": ignore_info,
        "builtin_skip_dirs": sorted(SKIP_INDEX_DIR_NAMES),
        "builtin_skip_files": sorted(SKIP_INDEX_FILE_NAMES),
    }
    fingerprint_source = {
        key: value
        for key, value in policy.items()
        if key != "motokoignore"
    }
    fingerprint_source["motokoignore"] = {
        "exists": ignore_info.get("exists", False),
        "sha256": ignore_info.get("sha256", ""),
        "rules": ignore_info.get("rules", []),
    }
    policy["fingerprint"] = sha256_hex(
        json.dumps(fingerprint_source, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return policy


def rel_posix(path: pathlib.Path, root: pathlib.Path) -> str:
    return path.relative_to(root).as_posix()


def ignore_directory_match(rule: dict, rel: str, *, is_dir: bool) -> bool:
    pattern = str(rule.get("pattern", "")).strip("/")
    if not pattern or not rel:
        return False
    parts = rel.split("/")
    ancestor_count = len(parts) if is_dir else max(0, len(parts) - 1)
    ancestors = ["/".join(parts[:idx]) for idx in range(1, ancestor_count + 1)]
    if "/" not in pattern and not rule.get("anchored"):
        return any(fnmatch.fnmatchcase(ancestor.split("/")[-1], pattern) for ancestor in ancestors)
    for ancestor in ancestors:
        if rule.get("anchored"):
            if fnmatch.fnmatchcase(ancestor, pattern):
                return True
        elif (
            fnmatch.fnmatchcase(ancestor, pattern)
            or fnmatch.fnmatchcase(ancestor, "*/" + pattern)
            or ancestor.endswith("/" + pattern)
        ):
            return True
    return False


def motoko_ignore_matches(rules: list[dict], rel: str, *, is_dir: bool) -> dict | None:
    rel = rel.strip("/")
    if not rel:
        return None
    name = rel.split("/")[-1]
    for rule in rules:
        pattern = str(rule.get("pattern", "")).strip("/")
        if not pattern:
            continue
        if rule.get("directory_only"):
            if ignore_directory_match(rule, rel, is_dir=is_dir):
                return rule
            continue
        if "/" not in pattern and not rule.get("anchored"):
            if fnmatch.fnmatchcase(name, pattern):
                return rule
            if is_dir and fnmatch.fnmatchcase(rel, pattern):
                return rule
            continue
        if rule.get("anchored"):
            if fnmatch.fnmatchcase(rel, pattern):
                return rule
        elif (
            fnmatch.fnmatchcase(rel, pattern)
            or fnmatch.fnmatchcase(rel, "*/" + pattern)
            or rel.endswith("/" + pattern)
        ):
            return rule
    return None


def ignored_path_record(path: pathlib.Path, root: pathlib.Path, kind: str, rule: dict) -> dict:
    return {
        "path": str(path),
        "relative_path": rel_posix(path, root),
        "kind": kind,
        "pattern": rule.get("pattern", ""),
        "line": rule.get("line", 0),
    }


def index_candidate_report(root: pathlib.Path, pattern: str | None) -> dict:
    normalized = (pattern or AUTO_INDEX_GLOB).strip() or AUTO_INDEX_GLOB
    selection_policy = document_selection_policy(root, normalized)
    if root.is_file():
        candidates = [root] if is_probably_text_file(root) else []
        return {
            "root": str(root),
            "glob": normalized,
            "candidates": candidates,
            "ignored_count": 0,
            "ignored_file_count": 0,
            "ignored_dir_count": 0,
            "ignored_examples": [],
            "selection_policy": selection_policy,
        }

    rules = selection_policy.get("motokoignore", {}).get("rules", [])
    candidates: list[pathlib.Path] = []
    ignored_examples: list[dict] = []
    ignored_count = 0
    ignored_file_count = 0
    ignored_dir_count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        current = pathlib.Path(dirpath)
        kept_dirs = []
        for dirname in sorted(dirnames):
            directory = current / dirname
            if dirname in SKIP_INDEX_DIR_NAMES:
                continue
            rel = rel_posix(directory, root)
            ignore_rule = motoko_ignore_matches(rules, rel, is_dir=True)
            if ignore_rule is not None:
                ignored_count += 1
                ignored_dir_count += 1
                if len(ignored_examples) < MAX_INDEX_IGNORE_EXAMPLES:
                    ignored_examples.append(ignored_path_record(directory, root, "directory", ignore_rule))
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs
        for filename in sorted(filenames):
            if filename in SKIP_INDEX_FILE_NAMES:
                continue
            candidate = current / filename
            rel = rel_posix(candidate, root)
            ignore_rule = motoko_ignore_matches(rules, rel, is_dir=False)
            if ignore_rule is not None:
                ignored_count += 1
                ignored_file_count += 1
                if len(ignored_examples) < MAX_INDEX_IGNORE_EXAMPLES:
                    ignored_examples.append(ignored_path_record(candidate, root, "file", ignore_rule))
                continue
            if normalized != AUTO_INDEX_GLOB and not (
                fnmatch.fnmatch(filename, normalized)
                or fnmatch.fnmatch(rel, normalized)
            ):
                continue
            if is_probably_text_file(candidate):
                candidates.append(candidate)
    return {
        "root": str(root),
        "glob": normalized,
        "candidates": sorted(candidates),
        "ignored_count": ignored_count,
        "ignored_file_count": ignored_file_count,
        "ignored_dir_count": ignored_dir_count,
        "ignored_examples": ignored_examples,
        "selection_policy": selection_policy,
    }


def iter_index_candidates(root: pathlib.Path, pattern: str | None) -> list[pathlib.Path]:
    return index_candidate_report(root, pattern)["candidates"]


def selection_policy_staleness(index: dict) -> tuple[str, list[str]]:
    root_text = index.get("root", "")
    if not root_text:
        return "unknown", ["index has no root path; cannot verify source selection policy"]
    root = pathlib.Path(root_text).expanduser()
    pattern = index.get("glob") or AUTO_INDEX_GLOB
    try:
        current = document_selection_policy(root, pattern)
    except SystemExit as exc:
        return "stale", [str(exc)]
    stored = index.get("selection_policy") or {}
    if stored:
        if stored.get("fingerprint") != current.get("fingerprint"):
            return "stale", [f"source selection policy changed for {root}"]
    elif current.get("motokoignore", {}).get("exists"):
        return "stale", [f"{MOTOKO_IGNORE_FILE} is present but this index has no stored source selection policy"]

    rules = current.get("motokoignore", {}).get("rules", [])
    if rules and root.is_dir():
        ignored_indexed_paths = []
        for file_item in index.get("files", []):
            path_text = file_item.get("path", "")
            if not path_text:
                continue
            path = pathlib.Path(path_text).expanduser()
            try:
                rel = path.resolve().relative_to(root.resolve()).as_posix()
            except (OSError, ValueError):
                continue
            if motoko_ignore_matches(rules, rel, is_dir=False):
                ignored_indexed_paths.append(path_text)
        if ignored_indexed_paths:
            examples = ", ".join(ignored_indexed_paths[:3])
            return "stale", [f"source selection policy now excludes indexed file(s): {examples}"]
    return "fresh", []
