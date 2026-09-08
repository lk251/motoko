"""Corpus selection, skip, and freshness helpers for Motoko."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import pathlib

from .source_access import SOURCE_BOUNDARY_VERSION, open_source


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


def sha256_file(path: pathlib.Path, *, root: pathlib.Path | None = None) -> str:
    digest = hashlib.sha256()
    with open_source(path, roots=[root if root is not None else path.absolute().parent]) as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_fingerprint(path: pathlib.Path) -> dict:
    digest = hashlib.sha256()
    with open_source(path, roots=[path.absolute().parent]) as fh:
        stat = os.fstat(fh.fileno())
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": digest.hexdigest(),
    }


def is_under(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def read_allowed_dirs_file(path: pathlib.Path) -> list[pathlib.Path]:
    if not path.exists():
        return []
    dirs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            dirs.append(pathlib.Path(line).expanduser().resolve())
    return dirs


def add_allowed_dir_entry(
    allowlist_path: pathlib.Path,
    resolved: pathlib.Path,
    *,
    nix_managed_message_provider=None,
) -> bool:
    existing = read_allowed_dirs_file(allowlist_path)
    if resolved in existing:
        return False
    try:
        with allowlist_path.open("a", encoding="utf-8") as fh:
            fh.write(str(resolved) + "\n")
        allowlist_path.chmod(0o600)
    except OSError as exc:
        message = nix_managed_message_provider(allowlist_path) if nix_managed_message_provider else None
        if message:
            raise SystemExit(message) from None
        raise SystemExit(f"cannot update Motoko document allowlist at {allowlist_path}: {exc}") from None
    return True


def require_path_allowed(path: pathlib.Path, directories: list[pathlib.Path]) -> None:
    resolved = path.expanduser().resolve()
    if not directories:
        raise SystemExit(
            "Motoko has no allowed document directories yet; run 'motoko allow-dir DIR' first"
        )
    if any(resolved == directory or is_under(resolved, directory) for directory in directories):
        return
    raise SystemExit(
        f"{resolved} is outside Motoko's allowed directories; run 'motoko allow-dir DIR' first"
    )


def is_probably_text_file(path: pathlib.Path, *, sample_bytes: int = TEXT_SAMPLE_BYTES,
                          root: pathlib.Path | None = None) -> bool:
    try:
        with open_source(path, roots=[root if root is not None else path.absolute().parent]) as fh:
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
        with open_source(ignore_path, roots=[root.absolute()]) as fh:
            raw = fh.read().decode("utf-8")
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
        "source_boundary": SOURCE_BOUNDARY_VERSION,
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
        candidates = [root] if is_probably_text_file(root, root=root) else []
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
            if is_probably_text_file(candidate, root=root):
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


def file_staleness(file_item: dict, *, hash_on_metadata_change: bool = True,
                   root: pathlib.Path | None = None) -> tuple[str, list[str]]:
    path = pathlib.Path(file_item.get("path", "")).expanduser()
    expected = file_item.get("source_fingerprint") or {}
    if not expected:
        return "unknown", [f"{path}: no fingerprint stored; rebuild index to enable stale checks"]
    if not path.exists():
        return "stale", [f"{path}: missing"]
    try:
        current_stat = path.stat()
    except OSError as exc:
        return "stale", [f"{path}: cannot stat file: {exc}"]

    warnings = []
    if current_stat.st_size != expected.get("size"):
        warnings.append(
            f"{path}: size changed from {expected.get('size')} to {current_stat.st_size}"
        )
    if current_stat.st_mtime_ns != expected.get("mtime_ns"):
        warnings.append(f"{path}: mtime changed")
    if warnings:
        if not hash_on_metadata_change:
            if current_stat.st_size != expected.get("size"):
                warnings.append(f"{path}: content may have changed; exact hash check deferred")
                return "stale", warnings
            return "metadata-changed", warnings
        try:
            boundary = root or pathlib.Path(file_item.get("source_root") or path.absolute().parent)
            current_hash = sha256_file(path, root=boundary)
            if current_hash == expected.get("sha256"):
                return "mtime-only", [f"{path}: metadata changed but content hash still matches"]
            warnings.append(f"{path}: content hash changed")
        except OSError as exc:
            warnings.append(f"{path}: cannot hash current file: {exc}")
        return "stale", warnings
    return "fresh", []


def index_staleness(
    index: dict,
    *,
    artifact_warning_provider=None,
    hash_on_metadata_change: bool = True,
    check_selection_policy: bool = True,
) -> tuple[str, list[str]]:
    selection_status, selection_warnings = selection_policy_staleness(index) if check_selection_policy else ("unknown", [])
    if selection_status == "stale":
        return "stale", selection_warnings
    statuses = []
    warnings = list(selection_warnings)
    for file_item in index.get("files", []):
        status, file_warnings = file_staleness(
            file_item,
            hash_on_metadata_change=hash_on_metadata_change,
            root=pathlib.Path(index["root"]) if index.get("root") else None,
        )
        statuses.append(status)
        warnings.extend(file_warnings)
    if not statuses:
        return "empty", ["index has no files"]
    if "stale" in statuses:
        return "stale", warnings
    if "unknown" in statuses:
        return "unknown", warnings
    if "mtime-only" in statuses or "metadata-changed" in statuses:
        return "metadata-changed", warnings
    artifact_warnings = artifact_warning_provider(index) if artifact_warning_provider else []
    if artifact_warnings:
        return "stale", warnings + artifact_warnings
    return "fresh", warnings
