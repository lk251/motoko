"""Agentic action and skill-tool validation for Motoko.

This module deliberately does not execute scripts. It validates declarations,
approval state, and typed action records so the runner boundary can stay
inspectable before any future execution path is enabled.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import pathlib
import re
import uuid

from motoko_core.state import append_jsonl, atomic_write, safe_load_json


TOOL_SCHEMA = "motoko-tool-v1"
APPROVAL_SCHEMA = "motoko-tool-approval-v1"
ACTION_SCHEMA = "motoko-action-v1"
ACTION_LEDGER_SCHEMA = "motoko-action-ledger-v1"

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
    "goal_loop_step",
}
SUPPORTED_INTERPRETERS = {"python3"}
SUPPORTED_WRAPPERS = {"motoko-tool-python-stdlib"}

MAX_TOOL_NAME = 80
MAX_DESCRIPTION = 600
MAX_TIMEOUT_SECONDS = 3600
MAX_STDOUT_BYTES = 4 * 1024 * 1024
MAX_STDERR_BYTES = 1024 * 1024


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
    if validation.get("session_repeat_eligible"):
        lines.append(f"session repeat key: {validation.get('session_repeat_key', '')}")
    if validation.get("reason"):
        lines.append(f"reason: {validation.get('reason', '')}")
    return "\n".join(lines)
