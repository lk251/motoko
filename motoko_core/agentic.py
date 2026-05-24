"""Agentic action and skill-tool validation for Motoko.

This module owns the strict boundary between model/planner output and local
effects. It validates declarations, approval state, typed action records, and
the first narrow script runner for approved stdlib Python skill tools.
"""

from __future__ import annotations

import datetime as _dt
import contextlib
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import uuid

from motoko_core.state import append_jsonl, atomic_write, ensure_private_dir, safe_load_json


TOOL_SCHEMA = "motoko-tool-v1"
APPROVAL_SCHEMA = "motoko-tool-approval-v1"
ACTION_SCHEMA = "motoko-action-v1"
ACTION_LEDGER_SCHEMA = "motoko-action-ledger-v1"
ACTION_RESULT_SCHEMA = "motoko-action-result-v1"
TOOL_INPUT_SCHEMA = "motoko-tool-input-v1"
TOOL_PRIVATE_RESULT_SCHEMA = "motoko-tool-private-result-v1"

EFFECT_PROMPT_ONLY = "prompt_only"
EFFECT_READ_CONTEXT = "read_context"
EFFECT_READ_ALLOWED_FILES = "read_allowed_files"
EFFECT_WRITE_MOTOKO_STATE = "write_motoko_state"
EFFECT_WRITE_ALLOWED_PROJECT = "write_allowed_project"
EFFECT_NETWORK = "network"
EFFECT_EXTERNAL_PROCESS = "external_process"
EFFECT_SERVICE_CONTROL = "service_control"
EFFECT_PRIVILEGED = "privileged"

KNOWN_EFFECTS = {
    EFFECT_PROMPT_ONLY,
    EFFECT_READ_CONTEXT,
    EFFECT_READ_ALLOWED_FILES,
    EFFECT_WRITE_MOTOKO_STATE,
    EFFECT_WRITE_ALLOWED_PROJECT,
    EFFECT_NETWORK,
    EFFECT_EXTERNAL_PROCESS,
    EFFECT_SERVICE_CONTROL,
    EFFECT_PRIVILEGED,
}
FORBIDDEN_EFFECTS = {EFFECT_SERVICE_CONTROL, EFFECT_PRIVILEGED}
LOW_RISK_REPEATABLE_EFFECTS = {
    EFFECT_PROMPT_ONLY,
    EFFECT_READ_CONTEXT,
    EFFECT_READ_ALLOWED_FILES,
    EFFECT_WRITE_MOTOKO_STATE,
}

SUPPORTED_TOOL_SCHEMAS = {TOOL_SCHEMA}
SUPPORTED_ACTION_KINDS = {
    "skill_handler_run",
    "skill_tool_run",
    "artifact_lifecycle_plan",
    "artifact_lifecycle_apply",
    "project_file_write",
    "goal_loop_step",
}
SUPPORTED_INTERPRETERS = {"python3"}
SUPPORTED_WRAPPERS = {"motoko-tool-python-stdlib"}

MAX_TOOL_NAME = 80
MAX_DESCRIPTION = 600
MAX_TIMEOUT_SECONDS = 3600
MAX_STDOUT_BYTES = 4 * 1024 * 1024
MAX_STDERR_BYTES = 1024 * 1024
MAX_RESULT_PREVIEW_CHARS = 1200
MAX_PROJECT_WRITE_BYTES = 1024 * 1024


class AgenticValidationError(ValueError):
    """Raised when an action or tool declaration fails closed."""


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def stable_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def file_sha256(path: pathlib.Path) -> str:
    return sha256_bytes(path.read_bytes())


def safe_slug(value: str, *, limit: int = MAX_TOOL_NAME) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip(".-")
    return slug[:limit].strip(".-")


def current_realm() -> str:
    for key in ("MOTOKO_REALM", "USER", "LOGNAME"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value
    return "unknown"


def normalize_effects(value) -> list[str]:
    if isinstance(value, str):
        raw = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, list):
        raw = [str(item).strip() for item in value if str(item).strip()]
    else:
        raw = []
    effects: list[str] = []
    for item in raw:
        if item not in KNOWN_EFFECTS:
            raise AgenticValidationError(f"unknown effect: {item}")
        if item in FORBIDDEN_EFFECTS:
            raise AgenticValidationError(f"forbidden effect: {item}")
        if item not in effects:
            effects.append(item)
    return effects


def _safe_relative_path(value: str, *, label: str) -> pathlib.PurePosixPath:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        raise AgenticValidationError(f"{label} path is empty")
    path = pathlib.PurePosixPath(raw)
    if path.is_absolute():
        raise AgenticValidationError(f"{label} path must be relative")
    if any(part in {"", ".", ".."} or part.startswith(".") for part in path.parts):
        raise AgenticValidationError(f"{label} path must not contain traversal or hidden components")
    return path


def _path_inside(base: pathlib.Path, candidate: pathlib.Path, message: str) -> pathlib.Path:
    base_resolved = base.resolve(strict=False)
    candidate_resolved = candidate.resolve(strict=False)
    try:
        candidate_resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise AgenticValidationError(message) from exc
    return candidate_resolved


def skill_package_dir(skill: dict) -> pathlib.Path:
    path = pathlib.Path(str(skill.get("path") or ""))
    if not path or path.name != "SKILL.md":
        raise AgenticValidationError(f"skill has no package SKILL.md path: {skill.get('slug') or skill.get('name')}")
    if path.is_symlink():
        raise AgenticValidationError("refusing symlinked SKILL.md")
    return path.parent.resolve(strict=False)


def parse_json_file(path: pathlib.Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AgenticValidationError(f"cannot read tool metadata: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AgenticValidationError(f"invalid tool metadata JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise AgenticValidationError("tool metadata must be a JSON object")
    return data


def validate_schema_subset(schema, *, label: str = "schema") -> dict:
    if not isinstance(schema, dict):
        raise AgenticValidationError(f"{label} must be an object")
    schema_type = schema.get("type", "object")
    if schema_type != "object":
        raise AgenticValidationError(f"{label}.type must be object")
    properties = schema.get("properties", {})
    if properties is None:
        properties = {}
    if not isinstance(properties, dict):
        raise AgenticValidationError(f"{label}.properties must be an object")
    required = schema.get("required", [])
    if required is None:
        required = []
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        raise AgenticValidationError(f"{label}.required must be a list of strings")
    additional = schema.get("additionalProperties", True)
    if not isinstance(additional, bool):
        raise AgenticValidationError(f"{label}.additionalProperties must be boolean when present")
    for key, spec in properties.items():
        if not isinstance(key, str) or not isinstance(spec, dict):
            raise AgenticValidationError(f"{label}.properties must map strings to objects")
        if spec.get("type", "string") not in {"string", "integer", "number", "boolean", "array", "object"}:
            raise AgenticValidationError(f"{label}.properties.{key}.type is unsupported")
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": additional}


def validate_arguments(arguments, schema: dict) -> None:
    schema = validate_schema_subset(schema, label="argument_schema")
    if not isinstance(arguments, dict):
        raise AgenticValidationError("arguments must be an object")
    for key in schema["required"]:
        if key not in arguments:
            raise AgenticValidationError(f"missing required argument: {key}")
    if schema["additionalProperties"] is False:
        allowed = set(schema["properties"])
        extras = sorted(set(arguments) - allowed)
        if extras:
            raise AgenticValidationError(f"unknown argument(s): {', '.join(extras)}")
    for key, value in arguments.items():
        spec = schema["properties"].get(key)
        if not spec:
            continue
        expected = spec.get("type", "string")
        ok = (
            (expected == "string" and isinstance(value, str))
            or (expected == "integer" and isinstance(value, int) and not isinstance(value, bool))
            or (expected == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
            or (expected == "boolean" and isinstance(value, bool))
            or (expected == "array" and isinstance(value, list))
            or (expected == "object" and isinstance(value, dict))
        )
        if not ok:
            raise AgenticValidationError(f"argument {key} must be {expected}")


def validate_json_value(value, schema: dict, *, label: str = "value") -> None:
    """Validate the small JSON-schema subset Motoko accepts for tool I/O."""
    schema = validate_schema_subset(schema, label=label)
    if schema.get("type") == "object":
        validate_arguments(value, schema)


def validate_path_argument_boundaries(arguments: dict, tool: dict, *, realm: str, path_checker=None) -> None:
    if not isinstance(arguments, dict):
        return
    effects = set(tool.get("allowed_effects", []))
    if not ({EFFECT_READ_ALLOWED_FILES, EFFECT_WRITE_ALLOWED_PROJECT} & effects):
        return
    for key, value in arguments.items():
        key_text = str(key).lower()
        if not any(marker in key_text for marker in ("path", "file", "dir")):
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if not isinstance(item, str):
                continue
            if "\x00" in item:
                raise AgenticValidationError(f"argument {key} contains NUL")
            raw = item.strip().replace("\\", "/")
            if not raw:
                continue
            candidate = pathlib.PurePosixPath(raw)
            if any(part in {"..", ""} for part in candidate.parts):
                raise AgenticValidationError(f"argument {key} must not contain traversal")
            if realm == "mares" and (raw == "/home/personal" or raw.startswith("/home/personal/")):
                raise AgenticValidationError("mares actions may not access /home/personal")
            if path_checker is not None:
                path_checker(key, item)


def validate_project_file_write_action(
    action: dict,
    *,
    realm: str,
    path_checker=None,
    preview: bool = False,
    session_approvals: set[str] | None = None,
) -> dict:
    path_text = str(action.get("path") or "").strip()
    if not path_text:
        raise AgenticValidationError("project_file_write requires path")
    if "\x00" in path_text:
        raise AgenticValidationError("project_file_write path contains NUL")
    target = pathlib.Path(path_text).expanduser()
    if not target.is_absolute():
        raise AgenticValidationError("project_file_write path must be absolute")
    raw_posix = path_text.replace("\\", "/")
    if any(part in {"", ".."} for part in pathlib.PurePosixPath(raw_posix).parts):
        raise AgenticValidationError("project_file_write path must not contain traversal")
    if realm == "mares" and (raw_posix == "/home/personal" or raw_posix.startswith("/home/personal/")):
        raise AgenticValidationError("mares actions may not access /home/personal")
    if path_checker is not None:
        path_checker("path", path_text, write=True)
    mode = str(action.get("mode") or "create").strip().lower()
    if mode not in {"create", "overwrite"}:
        raise AgenticValidationError("project_file_write mode must be create or overwrite")
    content = action.get("content")
    if not isinstance(content, str):
        raise AgenticValidationError("project_file_write content must be a string")
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > MAX_PROJECT_WRITE_BYTES:
        raise AgenticValidationError(f"project_file_write content exceeds {MAX_PROJECT_WRITE_BYTES} bytes")
    expected_sha = str(action.get("expected_sha256") or "").strip()
    if expected_sha and not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise AgenticValidationError("expected_sha256 must be a lowercase sha256 hex digest")
    if mode == "create" and expected_sha:
        raise AgenticValidationError("expected_sha256 is only valid for overwrite")
    if mode == "overwrite" and not expected_sha:
        raise AgenticValidationError("project_file_write overwrite requires expected_sha256")
    content_sha = sha256_bytes(content_bytes)
    repeat_key = project_file_write_session_key(
        action,
        target_path=str(target),
        mode=mode,
        content_sha256=content_sha,
        expected_sha256=expected_sha,
    )
    session_ok = repeat_key in (session_approvals or set())
    status = "valid"
    approval = "session-confirmed" if session_ok else "session-confirmation-required"
    if not session_ok:
        status = "needs_confirmation" if preview else "blocked"
    return {
        "target_path": str(target),
        "target_path_sha256": sha256_text(str(target)),
        "mode": mode,
        "content_bytes": len(content_bytes),
        "content_sha256": content_sha,
        "expected_sha256": expected_sha,
        "session_repeat_key": repeat_key,
        "session_repeat_eligible": True,
        "status": status,
        "approval": approval,
    }


class SessionApprovalStore:
    """In-memory session-repeat approvals for the current Motoko process."""

    def __init__(self) -> None:
        self._keys: set[str] = set()

    def approve(self, key: str) -> None:
        if key:
            self._keys.add(key)

    def approved(self, key: str) -> bool:
        return bool(key and key in self._keys)

    def keys(self) -> set[str]:
        return set(self._keys)


def validate_tool_metadata(skill: dict, metadata_path: pathlib.Path) -> dict:
    skill_dir = skill_package_dir(skill)
    metadata_path = _path_inside(skill_dir / "scripts", metadata_path, "tool metadata must stay under scripts/")
    if metadata_path.name.startswith(".") or metadata_path.suffix != ".json" or not metadata_path.name.endswith(".tool.json"):
        raise AgenticValidationError("tool metadata filename must end with .tool.json")
    if metadata_path.is_symlink():
        raise AgenticValidationError("refusing symlinked tool metadata")
    raw = parse_json_file(metadata_path)
    if raw.get("schema") not in SUPPORTED_TOOL_SCHEMAS:
        raise AgenticValidationError(f"unsupported tool schema: {raw.get('schema')}")
    name = safe_slug(str(raw.get("name") or ""))
    if not name:
        raise AgenticValidationError("tool name is empty")
    description = str(raw.get("description") or "").strip()[:MAX_DESCRIPTION]
    script_rel = _safe_relative_path(str(raw.get("script") or ""), label="script")
    if len(script_rel.parts) != 1:
        raise AgenticValidationError("script must be adjacent to its .tool.json metadata")
    script_path = _path_inside(metadata_path.parent, metadata_path.parent / script_rel.as_posix(), "script escapes metadata directory")
    if not script_path.exists() or not script_path.is_file():
        raise AgenticValidationError(f"script file not found: {script_rel.as_posix()}")
    if script_path.is_symlink():
        raise AgenticValidationError("refusing symlinked script file")
    interpreter = str(raw.get("interpreter") or "").strip()
    if interpreter not in SUPPORTED_INTERPRETERS:
        raise AgenticValidationError(f"unsupported interpreter: {interpreter}")
    wrapper = str(raw.get("wrapper") or "").strip()
    if wrapper not in SUPPORTED_WRAPPERS:
        raise AgenticValidationError(f"unsupported wrapper: {wrapper}")
    if interpreter == "python3" and script_path.suffix != ".py":
        raise AgenticValidationError("python3 tools must reference a .py script")
    effects = normalize_effects(raw.get("allowed_effects"))
    if not effects:
        raise AgenticValidationError("allowed_effects must not be empty")
    if EFFECT_PROMPT_ONLY in effects:
        raise AgenticValidationError("script tools cannot declare prompt_only")
    if EFFECT_EXTERNAL_PROCESS not in effects:
        effects.append(EFFECT_EXTERNAL_PROCESS)
    network = bool(raw.get("network", False))
    if network and EFFECT_NETWORK not in effects:
        raise AgenticValidationError("network=true requires the network effect")
    if network:
        raise AgenticValidationError("network tools require a later NixOS-reviewed policy")
    writes_project_files = bool(raw.get("writes_project_files", False))
    if writes_project_files and EFFECT_WRITE_ALLOWED_PROJECT not in effects:
        raise AgenticValidationError("writes_project_files=true requires write_allowed_project")
    argument_schema = validate_schema_subset(raw.get("argument_schema") or {"type": "object"}, label="argument_schema")
    input_schema = validate_schema_subset(raw.get("input_schema") or {"type": "object"}, label="input_schema")
    output_schema = validate_schema_subset(raw.get("output_schema") or {"type": "object"}, label="output_schema")
    timeout = int(raw.get("timeout_seconds") or 30)
    if timeout < 1 or timeout > MAX_TIMEOUT_SECONDS:
        raise AgenticValidationError(f"timeout_seconds must be 1..{MAX_TIMEOUT_SECONDS}")
    max_stdout = int(raw.get("max_stdout_bytes") or 65536)
    max_stderr = int(raw.get("max_stderr_bytes") or 16384)
    if max_stdout < 0 or max_stdout > MAX_STDOUT_BYTES:
        raise AgenticValidationError(f"max_stdout_bytes must be 0..{MAX_STDOUT_BYTES}")
    if max_stderr < 0 or max_stderr > MAX_STDERR_BYTES:
        raise AgenticValidationError(f"max_stderr_bytes must be 0..{MAX_STDERR_BYTES}")
    return {
        "schema": TOOL_SCHEMA,
        "skill": skill.get("slug") or safe_slug(str(skill.get("name") or "")),
        "skill_name": skill.get("name", ""),
        "name": name,
        "description": description,
        "metadata_path": str(metadata_path),
        "metadata_relpath": metadata_path.relative_to(skill_dir).as_posix(),
        "script": script_rel.as_posix(),
        "script_path": str(script_path),
        "script_relpath": script_path.relative_to(skill_dir).as_posix(),
        "script_sha256": file_sha256(script_path),
        "metadata_sha256": file_sha256(metadata_path),
        "interpreter": interpreter,
        "wrapper": wrapper,
        "allowed_effects": effects,
        "argument_schema": argument_schema,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "timeout_seconds": timeout,
        "max_stdout_bytes": max_stdout,
        "max_stderr_bytes": max_stderr,
        "network": network,
        "writes_project_files": writes_project_files,
        "requires_confirmation": bool(raw.get("requires_confirmation", False) or writes_project_files),
    }


def declared_tool_paths(skill: dict) -> list[pathlib.Path]:
    if skill.get("builtin"):
        return []
    skill_dir = skill_package_dir(skill)
    paths = []
    for item in skill.get("tools", []) or []:
        rel = _safe_relative_path(str(item), label="tool metadata")
        candidate = _path_inside(skill_dir, skill_dir / pathlib.Path(*rel.parts), "declared tool escapes skill package")
        paths.append(candidate)
    scripts = skill_dir / "scripts"
    if scripts.exists() and scripts.is_dir() and not scripts.is_symlink():
        paths.extend(sorted(scripts.glob("*.tool.json")))
    unique: list[pathlib.Path] = []
    seen = set()
    for path in paths:
        key = str(path.resolve(strict=False))
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def list_skill_tools(skill: dict) -> list[dict]:
    rows = []
    for path in declared_tool_paths(skill):
        try:
            rows.append(validate_tool_metadata(skill, path))
        except AgenticValidationError as exc:
            rows.append(
                {
                    "schema": TOOL_SCHEMA,
                    "skill": skill.get("slug") or safe_slug(str(skill.get("name") or "")),
                    "name": path.name.removesuffix(".tool.json"),
                    "metadata_path": str(path),
                    "metadata_relpath": "",
                    "valid": False,
                    "error": str(exc),
                }
            )
        else:
            rows[-1]["valid"] = True
    return rows


def resolve_skill_tool(skill: dict, selector: str) -> dict:
    selector = str(selector or "").strip()
    if not selector:
        raise AgenticValidationError("tool selector is empty")
    matches = []
    for row in list_skill_tools(skill):
        if row.get("valid") is not True:
            continue
        if selector in {row.get("name"), row.get("metadata_relpath"), row.get("script_relpath")}:
            matches.append(row)
    if not matches:
        raise AgenticValidationError(f"tool not found: {selector}")
    if len(matches) > 1:
        raise AgenticValidationError(f"ambiguous tool selector: {selector}")
    return matches[0]


def approval_id(tool: dict, *, realm: str | None = None) -> str:
    realm = realm or current_realm()
    key = {
        "realm": realm,
        "skill": tool.get("skill", ""),
        "tool": tool.get("metadata_relpath", ""),
        "script_sha256": tool.get("script_sha256", ""),
        "metadata_sha256": tool.get("metadata_sha256", ""),
        "interpreter": tool.get("interpreter", ""),
        "wrapper": tool.get("wrapper", ""),
        "allowed_effects": tool.get("allowed_effects", []),
        "network": bool(tool.get("network")),
        "writes_project_files": bool(tool.get("writes_project_files")),
    }
    return sha256_text(stable_json(key))


def approval_record_for_tool(tool: dict, *, realm: str | None = None, requires_confirmation: bool | None = None) -> dict:
    realm = realm or current_realm()
    confirmation = bool(tool.get("requires_confirmation", False)) if requires_confirmation is None else bool(requires_confirmation)
    return {
        "schema": APPROVAL_SCHEMA,
        "id": approval_id(tool, realm=realm),
        "realm": realm,
        "skill": tool.get("skill", ""),
        "tool": tool.get("metadata_relpath", ""),
        "tool_name": tool.get("name", ""),
        "script_sha256": tool.get("script_sha256", ""),
        "metadata_sha256": tool.get("metadata_sha256", ""),
        "interpreter": tool.get("interpreter", ""),
        "wrapper": tool.get("wrapper", ""),
        "allowed_effects": tool.get("allowed_effects", []),
        "argument_schema": tool.get("argument_schema", {}),
        "network": bool(tool.get("network")),
        "writes_project_files": bool(tool.get("writes_project_files")),
        "approved_at": utc_now(),
        "approved_by": "user",
        "requires_confirmation": confirmation,
    }


def read_approval_state(path: pathlib.Path) -> dict:
    data = safe_load_json(path)
    if not isinstance(data, dict):
        return {"schema": "motoko-tool-approvals-v1", "approvals": []}
    approvals = data.get("approvals")
    if not isinstance(approvals, list):
        data["approvals"] = []
    data.setdefault("schema", "motoko-tool-approvals-v1")
    return data


def write_approval_state(path: pathlib.Path, state: dict) -> None:
    state = dict(state)
    state.setdefault("schema", "motoko-tool-approvals-v1")
    approvals = state.get("approvals")
    state["approvals"] = approvals if isinstance(approvals, list) else []
    atomic_write(path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def approve_tool(path: pathlib.Path, tool: dict, *, realm: str | None = None, requires_confirmation: bool | None = None) -> dict:
    record = approval_record_for_tool(tool, realm=realm, requires_confirmation=requires_confirmation)
    state = read_approval_state(path)
    rows = [row for row in state.get("approvals", []) if row.get("id") != record["id"]]
    rows.append(record)
    state["approvals"] = rows
    write_approval_state(path, state)
    return record


def matching_approval(path: pathlib.Path, tool: dict, *, realm: str | None = None) -> dict | None:
    expected = approval_id(tool, realm=realm or current_realm())
    for row in read_approval_state(path).get("approvals", []):
        if row.get("id") == expected:
            return row
    return None


def session_approval_key(action: dict, tool: dict | None = None) -> str:
    key = {
        "schema": action.get("schema"),
        "kind": action.get("kind"),
        "skill": action.get("skill"),
        "tool": action.get("tool"),
        "effects": (tool or {}).get("allowed_effects", []),
        "writes_project_files": bool((tool or {}).get("writes_project_files")),
        "network": bool((tool or {}).get("network")),
    }
    return sha256_text(stable_json(key))


def project_file_write_session_key(
    action: dict,
    *,
    target_path: str,
    mode: str,
    content_sha256: str,
    expected_sha256: str,
) -> str:
    key = {
        "schema": action.get("schema"),
        "kind": action.get("kind"),
        "target_path_sha256": sha256_text(str(target_path)),
        "mode": mode,
        "content_sha256": content_sha256,
        "expected_sha256": expected_sha256,
    }
    return sha256_text(stable_json(key))


def action_id(action: dict) -> str:
    return "act-" + uuid.uuid4().hex[:16]


def validate_action_record(
    action: dict,
    *,
    skill_resolver,
    approval_path: pathlib.Path,
    realm: str | None = None,
    session_approvals: set[str] | None = None,
    path_checker=None,
    preview: bool = False,
) -> dict:
    if not isinstance(action, dict):
        raise AgenticValidationError("action must be a JSON object")
    if action.get("schema") != ACTION_SCHEMA:
        raise AgenticValidationError(f"unsupported action schema: {action.get('schema')}")
    kind = str(action.get("kind") or "").strip()
    if kind not in SUPPORTED_ACTION_KINDS:
        raise AgenticValidationError(f"unsupported action kind: {kind}")
    if "command" in action or "shell" in action:
        raise AgenticValidationError("free-form shell commands are not supported action records")
    realm = realm or current_realm()
    result = {
        "schema": "motoko-action-validation-v1",
        "id": action_id(action),
        "created_at": utc_now(),
        "realm": realm,
        "kind": kind,
        "status": "valid",
        "approval": "not-required",
        "reason": str(action.get("reason") or "").strip()[:MAX_DESCRIPTION],
        "action_hash": sha256_text(stable_json(action)),
    }
    if kind == "skill_tool_run":
        skill_name = str(action.get("skill") or "").strip()
        tool_name = str(action.get("tool") or "").strip()
        if not skill_name:
            raise AgenticValidationError("skill_tool_run requires skill")
        if not tool_name:
            raise AgenticValidationError("skill_tool_run requires tool")
        skill = skill_resolver(skill_name)
        tool = resolve_skill_tool(skill, tool_name)
        arguments = action.get("arguments") or {}
        validate_arguments(arguments, tool.get("argument_schema") or {"type": "object"})
        validate_path_argument_boundaries(arguments, tool, realm=realm, path_checker=path_checker)
        approval = matching_approval(approval_path, tool, realm=realm)
        repeat_key = session_approval_key(action, tool)
        session_ok = repeat_key in (session_approvals or set())
        needs_confirmation = bool(tool.get("requires_confirmation"))
        low_risk = set(tool.get("allowed_effects", [])) <= LOW_RISK_REPEATABLE_EFFECTS
        if approval is None:
            result["status"] = "needs_approval" if preview else "blocked"
            result["approval"] = "missing"
        elif needs_confirmation and not session_ok:
            result["status"] = "needs_confirmation" if preview else "blocked"
            result["approval"] = "session-confirmation-required"
        else:
            result["approval"] = "persistent" if approval else "not-required"
        result.update(
            {
                "skill": tool.get("skill", ""),
                "tool": tool.get("name", ""),
                "tool_metadata": tool.get("metadata_relpath", ""),
                "allowed_effects": tool.get("allowed_effects", []),
                "script_sha256": tool.get("script_sha256", ""),
                "metadata_sha256": tool.get("metadata_sha256", ""),
                "approval_id": approval.get("id", "") if approval else "",
                "session_repeat_key": repeat_key,
                "session_repeat_eligible": bool(low_risk or needs_confirmation),
                "argument_hash": sha256_text(stable_json(action.get("arguments") or {})),
            }
        )
        return result
    if kind == "project_file_write":
        project = validate_project_file_write_action(
            action,
            realm=realm,
            path_checker=path_checker,
            preview=preview,
            session_approvals=session_approvals,
        )
        result.update(project)
        result["allowed_effects"] = [EFFECT_WRITE_ALLOWED_PROJECT]
        return result
    if kind == "skill_handler_run":
        skill_name = str(action.get("skill") or "").strip()
        if not skill_name:
            raise AgenticValidationError("skill_handler_run requires skill")
        skill = skill_resolver(skill_name)
        handler = str(action.get("handler") or skill.get("handler") or "").strip()
        if not handler or handler == "prompt_only":
            raise AgenticValidationError("skill_handler_run requires a non-prompt handler")
        if handler != skill.get("handler"):
            raise AgenticValidationError("handler does not match the skill declaration")
        result.update(
            {
                "skill": skill.get("slug", skill_name),
                "handler": handler,
                "allowed_effects": skill.get("allowed_effects", [])[:8],
            }
        )
        return result
    if kind in {"artifact_lifecycle_plan", "artifact_lifecycle_apply"}:
        result["approval"] = "confirmation-required" if kind.endswith("_apply") else "not-required"
        result["status"] = "needs_confirmation" if kind.endswith("_apply") and preview else result["status"]
        return result
    if kind == "goal_loop_step":
        result["status"] = "blocked"
        result["approval"] = "goal-loop-not-implemented"
        return result
    return result


def _atomic_project_write(path: pathlib.Path, text: str, *, mode_bits: int) -> None:
    tmp = path.with_name(f".{path.name}.motoko-tmp-{uuid.uuid4().hex[:12]}")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.chmod(mode_bits & 0o777)
        tmp.replace(path)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def apply_project_file_write_action(action: dict, validation: dict) -> dict:
    """Apply one already validated code-owned project-file write action."""
    if validation.get("status") != "valid":
        raise AgenticValidationError(f"cannot apply invalid action: {validation.get('status', '')}")
    if validation.get("kind") != "project_file_write":
        raise AgenticValidationError(f"unsupported project apply action kind: {validation.get('kind', '')}")
    target = pathlib.Path(str(action.get("path") or "")).expanduser()
    if not target.is_absolute():
        raise AgenticValidationError("project_file_write path must be absolute")
    parent = target.parent
    if not parent.exists() or not parent.is_dir():
        raise AgenticValidationError("project_file_write parent directory must already exist")
    if parent.is_symlink():
        raise AgenticValidationError("project_file_write refuses symlinked parent directories")
    if target.exists() and target.is_symlink():
        raise AgenticValidationError("project_file_write refuses symlink targets")
    if target.exists() and target.is_dir():
        raise AgenticValidationError("project_file_write refuses directory targets")

    mode = str(validation.get("mode") or action.get("mode") or "create").strip().lower()
    expected_sha = str(validation.get("expected_sha256") or action.get("expected_sha256") or "").strip()
    content = action.get("content")
    if not isinstance(content, str):
        raise AgenticValidationError("project_file_write content must be a string")
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > MAX_PROJECT_WRITE_BYTES:
        raise AgenticValidationError(f"project_file_write content exceeds {MAX_PROJECT_WRITE_BYTES} bytes")

    if mode == "create":
        if target.exists():
            raise AgenticValidationError("project_file_write create target already exists")
        previous_sha = ""
        mode_bits = 0o644
    elif mode == "overwrite":
        if not target.exists():
            raise AgenticValidationError("project_file_write overwrite target does not exist")
        if not expected_sha:
            raise AgenticValidationError("project_file_write overwrite requires expected_sha256")
        previous_sha = file_sha256(target)
        if previous_sha != expected_sha:
            raise AgenticValidationError("project_file_write expected_sha256 does not match target")
        mode_bits = target.stat().st_mode & 0o777
    else:
        raise AgenticValidationError("project_file_write mode must be create or overwrite")

    start = time.monotonic()
    _atomic_project_write(target, content, mode_bits=mode_bits)
    duration_ms = int((time.monotonic() - start) * 1000)
    return {
        "result_schema": ACTION_RESULT_SCHEMA,
        "action_id": validation.get("id", ""),
        "status": "completed",
        "duration_ms": duration_ms,
        "target_path_sha256": validation.get("target_path_sha256", ""),
        "mode": mode,
        "bytes_written": len(content_bytes),
        "previous_sha256": previous_sha,
        "new_sha256": file_sha256(target),
        "error": "",
    }


def ledger_record(validation: dict, *, status: str | None = None) -> dict:
    allowed = {
        "id",
        "created_at",
        "realm",
        "kind",
        "skill",
        "handler",
        "tool",
        "tool_metadata",
        "allowed_effects",
        "script_sha256",
        "metadata_sha256",
        "approval",
        "approval_id",
        "session_repeat_key",
        "session_repeat_eligible",
        "argument_hash",
        "action_hash",
        "target_path_sha256",
        "mode",
        "content_bytes",
        "content_sha256",
        "expected_sha256",
        "bytes_written",
        "previous_sha256",
        "new_sha256",
        "result_schema",
        "tool_run_id",
        "private_result_path",
        "exit_code",
        "duration_ms",
        "stdout_bytes",
        "stderr_bytes",
        "stdout_sha256",
        "stderr_sha256",
        "output_json_valid",
        "error",
    }
    row = {key: validation.get(key) for key in allowed if key in validation}
    row["schema"] = ACTION_LEDGER_SCHEMA
    row["recorded_at"] = utc_now()
    row["status"] = status or validation.get("status", "unknown")
    return row


def write_action_ledger(path: pathlib.Path, validation: dict, *, status: str | None = None) -> dict:
    row = ledger_record(validation, status=status)
    append_jsonl(path, row)
    return row


def tool_runs_dir(state_root: pathlib.Path) -> pathlib.Path:
    return ensure_private_dir(state_root / "tool-runs")


def tool_run_dir(state_root: pathlib.Path, run_id: str) -> pathlib.Path:
    return ensure_private_dir(tool_runs_dir(state_root) / safe_slug(run_id, limit=120))


def find_tool_result_path(state_root: pathlib.Path, selector: str) -> pathlib.Path:
    selector = str(selector or "").strip()
    if not selector:
        raise AgenticValidationError("tool run selector is empty")
    root = tool_runs_dir(state_root)
    candidates = []
    exact = root / safe_slug(selector, limit=120) / "result.json"
    if exact.exists():
        candidates.append(exact)
    for path in root.glob("*/result.json"):
        run_id = path.parent.name
        if run_id == selector or run_id.startswith(selector):
            candidates.append(path)
    unique = []
    seen = set()
    for path in candidates:
        key = str(path.resolve(strict=False))
        if key not in seen:
            seen.add(key)
            unique.append(path)
    if not unique:
        raise AgenticValidationError(f"tool result not found: {selector}")
    if len(unique) > 1:
        raise AgenticValidationError(f"ambiguous tool result selector: {selector}")
    return unique[0]


def safe_tool_environment(*, realm: str, state_root: pathlib.Path, run_dir: pathlib.Path) -> dict[str, str]:
    return {
        "HOME": str(run_dir),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1",
        "MOTOKO_REALM": realm,
        "MOTOKO_STATE_HOME": str(state_root),
        "MOTOKO_TOOL_RUN_DIR": str(run_dir),
        "MOTOKO_TOOL_MODE": "1",
    }


def format_action_ledger_rows(rows: list[dict], *, limit: int = 20) -> str:
    limit = max(1, min(200, int(limit or 20)))
    rows = list(rows or [])[-limit:]
    if not rows:
        return "action ledger: empty"
    lines = [f"action ledger: showing {len(rows)} row(s)"]
    for row in reversed(rows):
        parts = [
            str(row.get("recorded_at") or row.get("created_at") or ""),
            str(row.get("status") or ""),
            str(row.get("kind") or ""),
        ]
        if row.get("skill"):
            parts.append(f"skill={row.get('skill')}")
        if row.get("tool"):
            parts.append(f"tool={row.get('tool')}")
        if row.get("tool_run_id"):
            parts.append(f"run={row.get('tool_run_id')}")
        if row.get("duration_ms") is not None:
            parts.append(f"{row.get('duration_ms')}ms")
        if row.get("error"):
            parts.append(f"error={str(row.get('error'))[:160]}")
        lines.append("- " + "  ".join(part for part in parts if part))
    return "\n".join(lines)


def _clip_result_text(text: str, *, limit: int = MAX_RESULT_PREVIEW_CHARS) -> str:
    text = str(text or "")
    if len(text) <= limit:
        return text
    head = text[: max(0, limit // 2)].rstrip()
    tail = text[-max(0, limit // 2) :].lstrip()
    return f"{head}\n... truncated ...\n{tail}"


def format_tool_private_result(result: dict, *, private: bool = False) -> str:
    lines = [
        "tool result:",
        f"run: {result.get('tool_run_id', '')}",
        f"action: {result.get('action_id', '')}",
        f"status: {result.get('status', '')}",
        f"realm: {result.get('realm', '')}",
        f"skill: {result.get('skill', '')}",
        f"tool: {result.get('tool', '')}",
        f"exit code: {result.get('exit_code', '')}",
        f"duration: {result.get('duration_ms', 0)} ms",
        f"output json valid: {'yes' if result.get('output_json_valid') else 'no'}",
        f"stdout bytes: {len(str(result.get('stdout') or '').encode('utf-8'))}",
        f"stderr bytes: {len(str(result.get('stderr') or '').encode('utf-8'))}",
    ]
    if result.get("error"):
        lines.append(f"error: {result.get('error', '')}")
    if not private:
        lines.append("private content: hidden (use --private in this user account to inspect)")
        return "\n".join(lines)
    lines.append("private content:")
    output_json = result.get("output_json")
    if output_json is not None:
        lines.append("output_json:")
        lines.append(_clip_result_text(json.dumps(output_json, ensure_ascii=False, indent=2)))
    if result.get("stdout"):
        lines.append("stdout:")
        lines.append(_clip_result_text(result.get("stdout", "")))
    if result.get("stderr"):
        lines.append("stderr:")
        lines.append(_clip_result_text(result.get("stderr", "")))
    return "\n".join(lines)


def _read_limited_binary(handle, limit: int) -> tuple[bytes, bool]:
    handle.seek(0)
    if limit <= 0:
        data = handle.read(1)
        return b"", bool(data)
    data = handle.read(limit + 1)
    if len(data) > limit:
        return data[:limit], True
    return data, False


def _decode_tool_bytes(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def execute_skill_tool_action(
    action: dict,
    validation: dict,
    *,
    skill_resolver,
    approval_path: pathlib.Path,
    state_root: pathlib.Path,
    realm: str | None = None,
    session_approvals: set[str] | None = None,
    path_checker=None,
) -> dict:
    """Run one already approved skill tool action through the narrow runner."""
    if validation.get("status") != "valid":
        raise AgenticValidationError(f"cannot execute invalid action: {validation.get('status', '')}")
    if validation.get("kind") != "skill_tool_run":
        raise AgenticValidationError(f"unsupported executable action kind: {validation.get('kind', '')}")
    realm = realm or current_realm()
    skill = skill_resolver(str(action.get("skill") or ""))
    tool = resolve_skill_tool(skill, str(action.get("tool") or ""))
    effects = set(tool.get("allowed_effects", []))
    if EFFECT_NETWORK in effects or tool.get("network"):
        raise AgenticValidationError("network skill tools are not enabled")
    if EFFECT_WRITE_ALLOWED_PROJECT in effects or tool.get("writes_project_files"):
        raise AgenticValidationError("project-writing skill tools are not enabled in the first runner")
    if tool.get("interpreter") != "python3" or tool.get("wrapper") != "motoko-tool-python-stdlib":
        raise AgenticValidationError("only motoko-tool-python-stdlib python3 tools are enabled")

    arguments = action.get("arguments") or {}
    validate_arguments(arguments, tool.get("argument_schema") or {"type": "object"})
    validate_path_argument_boundaries(arguments, tool, realm=realm, path_checker=path_checker)
    approval = matching_approval(approval_path, tool, realm=realm)
    if approval is None:
        raise AgenticValidationError("tool approval is missing")
    if tool.get("requires_confirmation") and session_approval_key(action, tool) not in (session_approvals or set()):
        raise AgenticValidationError("session confirmation is required")

    action_run_id = validation.get("id") or action_id(action)
    run_id = "run-" + uuid.uuid4().hex[:16]
    run_dir = tool_run_dir(state_root, run_id)
    input_record = {
        "schema": TOOL_INPUT_SCHEMA,
        "action_id": action_run_id,
        "tool_run_id": run_id,
        "created_at": utc_now(),
        "realm": realm,
        "skill": tool.get("skill", ""),
        "tool": tool.get("name", ""),
        "arguments": arguments,
    }
    input_path = run_dir / "input.json"
    atomic_write(input_path, json.dumps(input_record, ensure_ascii=False, indent=2) + "\n")
    stdin = json.dumps(input_record, ensure_ascii=False, sort_keys=True).encode("utf-8")

    start = time.monotonic()
    proc = None
    timed_out = False
    with tempfile.TemporaryFile() as stdout_fh, tempfile.TemporaryFile() as stderr_fh:
        try:
            proc = subprocess.Popen(
                [sys.executable, str(tool.get("script_path", ""))],
                cwd=str(skill_package_dir(skill)),
                env=safe_tool_environment(realm=realm, state_root=state_root, run_dir=run_dir),
                stdin=subprocess.PIPE,
                stdout=stdout_fh,
                stderr=stderr_fh,
                close_fds=True,
            )
            assert proc.stdin is not None
            proc.communicate(input=stdin, timeout=float(tool.get("timeout_seconds") or 30))
        except subprocess.TimeoutExpired:
            timed_out = True
            if proc is not None:
                proc.kill()
                proc.communicate(timeout=5)
        duration_ms = int((time.monotonic() - start) * 1000)
        stdout_data, stdout_truncated = _read_limited_binary(stdout_fh, int(tool.get("max_stdout_bytes") or 0))
        stderr_data, stderr_truncated = _read_limited_binary(stderr_fh, int(tool.get("max_stderr_bytes") or 0))

    stdout_text = _decode_tool_bytes(stdout_data)
    stderr_text = _decode_tool_bytes(stderr_data)
    stdout_hash = sha256_bytes(stdout_data)
    stderr_hash = sha256_bytes(stderr_data)
    exit_code = proc.returncode if proc is not None and proc.returncode is not None else -1
    output_json = None
    output_json_valid = False
    error = ""
    status = "completed"
    if timed_out:
        status = "timeout"
        error = f"tool exceeded timeout of {tool.get('timeout_seconds')}s"
    elif stdout_truncated or stderr_truncated:
        status = "failed"
        error = "tool output exceeded declared byte limit"
    elif exit_code != 0:
        status = "failed"
        error = f"tool exited with code {exit_code}"
    else:
        stripped = stdout_text.strip()
        if stripped:
            try:
                output_json = json.loads(stripped)
                validate_json_value(output_json, tool.get("output_schema") or {"type": "object"}, label="output_schema")
                output_json_valid = True
            except (json.JSONDecodeError, AgenticValidationError) as exc:
                status = "failed"
                error = f"tool stdout did not match output_schema: {exc}"
        else:
            output_json = {}
            output_json_valid = True
    private_result = {
        "schema": TOOL_PRIVATE_RESULT_SCHEMA,
        "action_id": action_run_id,
        "tool_run_id": run_id,
        "created_at": utc_now(),
        "realm": realm,
        "skill": tool.get("skill", ""),
        "tool": tool.get("name", ""),
        "status": status,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "output_json": output_json,
        "output_json_valid": output_json_valid,
        "error": error,
    }
    private_result_path = run_dir / "result.json"
    atomic_write(private_result_path, json.dumps(private_result, ensure_ascii=False, indent=2) + "\n")
    return {
        "result_schema": ACTION_RESULT_SCHEMA,
        "action_id": action_run_id,
        "tool_run_id": run_id,
        "status": status,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "stdout_bytes": len(stdout_data),
        "stderr_bytes": len(stderr_data),
        "stdout_sha256": stdout_hash,
        "stderr_sha256": stderr_hash,
        "output_json_valid": output_json_valid,
        "private_result_path": str(private_result_path),
        "error": error,
    }


def format_tool_rows(rows: list[dict], *, approval_path: pathlib.Path, realm: str | None = None) -> str:
    if not rows:
        return "skill tools: none"
    lines = ["skill tools:"]
    for row in rows:
        if row.get("valid") is not True:
            lines.append(f"- {row.get('name', '')}: invalid")
            lines.append(f"  error: {row.get('error', '')}")
            lines.append(f"  metadata: {row.get('metadata_path', '')}")
            continue
        approval = matching_approval(approval_path, row, realm=realm)
        status = "approved" if approval else "not approved"
        lines.append(f"- {row.get('name', '')}: {status}")
        lines.append(f"  description: {row.get('description', '')}")
        lines.append(f"  metadata: {row.get('metadata_relpath', '')}")
        lines.append(f"  script: {row.get('script_relpath', '')}")
        lines.append(f"  effects: {', '.join(row.get('allowed_effects', []))}")
        lines.append(f"  confirmation: {'required' if row.get('requires_confirmation') else 'not required'}")
        lines.append(f"  script sha256: {row.get('script_sha256', '')}")
        lines.append(f"  metadata sha256: {row.get('metadata_sha256', '')}")
    return "\n".join(lines)


def format_action_validation(validation: dict) -> str:
    lines = [
        "action preview:",
        f"id: {validation.get('id', '')}",
        f"status: {validation.get('status', '')}",
        f"kind: {validation.get('kind', '')}",
        f"realm: {validation.get('realm', '')}",
        f"approval: {validation.get('approval', '')}",
    ]
    for key in ("skill", "handler", "tool", "tool_metadata"):
        if validation.get(key):
            lines.append(f"{key.replace('_', ' ')}: {validation.get(key)}")
    if validation.get("allowed_effects"):
        lines.append("effects: " + ", ".join(validation.get("allowed_effects", [])))
    if validation.get("kind") == "project_file_write":
        if validation.get("target_path"):
            lines.append(f"target path: {validation.get('target_path')}")
        lines.append(f"mode: {validation.get('mode', '')}")
        lines.append(f"content bytes: {validation.get('content_bytes', 0)}")
        lines.append(f"content sha256: {validation.get('content_sha256', '')}")
        if validation.get("expected_sha256"):
            lines.append(f"expected sha256: {validation.get('expected_sha256', '')}")
    if validation.get("session_repeat_eligible"):
        lines.append(f"session repeat key: {validation.get('session_repeat_key', '')}")
    if validation.get("reason"):
        lines.append(f"reason: {validation.get('reason', '')}")
    return "\n".join(lines)


def format_action_result(validation: dict, result: dict | None = None) -> str:
    if not result:
        return format_action_validation(validation)
    lines = [
        "action run:",
        f"id: {validation.get('id', '')}",
        f"status: {result.get('status', '')}",
        f"kind: {validation.get('kind', '')}",
        f"realm: {validation.get('realm', '')}",
    ]
    for key in ("skill", "tool", "tool_metadata"):
        if validation.get(key):
            lines.append(f"{key.replace('_', ' ')}: {validation.get(key)}")
    if validation.get("allowed_effects"):
        lines.append("effects: " + ", ".join(validation.get("allowed_effects", [])))
    if validation.get("kind") == "project_file_write":
        if validation.get("target_path"):
            lines.append(f"target path: {validation.get('target_path')}")
        lines.extend(
            [
                f"mode: {result.get('mode', validation.get('mode', ''))}",
                f"bytes written: {result.get('bytes_written', 0)}",
                f"target path sha256: {result.get('target_path_sha256', validation.get('target_path_sha256', ''))}",
                f"previous sha256: {result.get('previous_sha256', '')}",
                f"new sha256: {result.get('new_sha256', '')}",
                f"duration: {result.get('duration_ms', 0)} ms",
            ]
        )
        if result.get("error"):
            lines.append(f"error: {result.get('error', '')}")
        return "\n".join(lines)
    lines.extend(
        [
            f"tool run: {result.get('tool_run_id', '')}",
            f"duration: {result.get('duration_ms', 0)} ms",
            f"exit code: {result.get('exit_code', '')}",
            f"stdout: {result.get('stdout_bytes', 0)} B sha256={result.get('stdout_sha256', '')}",
            f"stderr: {result.get('stderr_bytes', 0)} B sha256={result.get('stderr_sha256', '')}",
            f"output json valid: {'yes' if result.get('output_json_valid') else 'no'}",
            f"private result: {result.get('private_result_path', '')}",
        ]
    )
    if result.get("error"):
        lines.append(f"error: {result.get('error', '')}")
    return "\n".join(lines)
