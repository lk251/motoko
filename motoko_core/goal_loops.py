"""Goal-loop record validation and formatting for Motoko.

This module validates and formats durable loop plans. Execution stays outside
this module and remains deliberately narrow: only explicit action lists are
run, and the root facade sends each action through the normal action validator,
confirmation, budget, checkpoint, and ledger path.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import re
import uuid

from motoko_core.agentic import (
    ACTION_SCHEMA,
    EFFECT_NETWORK,
    EFFECT_PRIVILEGED,
    EFFECT_PROPOSE_PROJECT_CHANGES,
    EFFECT_READ_ALLOWED_FILES,
    EFFECT_READ_CONTEXT,
    EFFECT_SERVICE_CONTROL,
    EFFECT_WRITE_ALLOWED_PROJECT,
    EFFECT_WRITE_MOTOKO_STATE,
    KNOWN_EFFECTS,
    LOW_RISK_REPEATABLE_EFFECTS,
)
from motoko_core.state import atomic_write, safe_load_json


GOAL_LOOP_SCHEMA = "motoko-goal-loop-v1"
GOAL_LOOP_STATUS_DRAFT = "draft"
GOAL_LOOP_STATUS_NEEDS_APPROVAL = "needs_approval"
GOAL_LOOP_STATUS_REJECTED = "rejected"
GOAL_LOOP_PLANNER_DISABLED = "disabled"
GOAL_LOOP_PLANNER_EXPLICIT_ACTIONS = "explicit_actions"
GOAL_LOOP_PLANNER_MODEL_READONLY = "model_readonly"
GOAL_LOOP_PLANNER_MODEL_CONFIRMED = "model_confirmed"

MAX_OBJECTIVE_CHARS = 1000
MAX_SCOPE_ITEMS = 20
MAX_ALLOWED_TOOLS = 20
MAX_BUDGET_STEPS = 50
MAX_BUDGET_CALLS = 200
MAX_BUDGET_MINUTES = 24 * 60
MAX_GOAL_ACTIONS = 50

FORBIDDEN_GOAL_EFFECTS = {EFFECT_SERVICE_CONTROL, EFFECT_PRIVILEGED}
APPROVAL_REQUIRED_EFFECTS = {EFFECT_WRITE_ALLOWED_PROJECT, EFFECT_NETWORK}
LOW_RISK_GOAL_EFFECTS = {
    EFFECT_READ_CONTEXT,
    EFFECT_READ_ALLOWED_FILES,
    EFFECT_WRITE_MOTOKO_STATE,
    EFFECT_PROPOSE_PROJECT_CHANGES,
}
MODEL_READONLY_GOAL_EFFECTS = {
    EFFECT_READ_CONTEXT,
    EFFECT_READ_ALLOWED_FILES,
    EFFECT_WRITE_MOTOKO_STATE,
    EFFECT_PROPOSE_PROJECT_CHANGES,
}
MODEL_CONFIRMED_GOAL_EFFECTS = {
    EFFECT_READ_CONTEXT,
    EFFECT_READ_ALLOWED_FILES,
    EFFECT_WRITE_MOTOKO_STATE,
    EFFECT_PROPOSE_PROJECT_CHANGES,
    EFFECT_WRITE_ALLOWED_PROJECT,
}
SUPPORTED_GOAL_PLANNERS = {
    GOAL_LOOP_PLANNER_DISABLED,
    GOAL_LOOP_PLANNER_EXPLICIT_ACTIONS,
    GOAL_LOOP_PLANNER_MODEL_READONLY,
    GOAL_LOOP_PLANNER_MODEL_CONFIRMED,
}


class GoalLoopValidationError(ValueError):
    """Raised when a goal-loop plan is not safe to preview."""


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def safe_goal_id(value: str | None = None) -> str:
    if value:
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip(".-")
        if slug:
            return slug[:80].strip(".-")
    return "goal-" + uuid.uuid4().hex[:16]


def normalize_string_list(value, *, limit: int, label: str) -> list[str]:
    if value is None:
        return []
    raw = value if isinstance(value, list) else [value]
    rows = []
    for item in raw:
        text = str(item or "").strip()
        if not text:
            continue
        if "\x00" in text:
            raise GoalLoopValidationError(f"{label} contains NUL")
        if text not in rows:
            rows.append(text)
    if len(rows) > limit:
        raise GoalLoopValidationError(f"{label} has too many entries (max {limit})")
    return rows


def normalize_effects(value) -> list[str]:
    effects = normalize_string_list(value, limit=20, label="allowed_effects")
    if not effects:
        effects = [EFFECT_READ_CONTEXT, EFFECT_READ_ALLOWED_FILES]
    normalized = []
    for effect in effects:
        if effect not in KNOWN_EFFECTS:
            raise GoalLoopValidationError(f"unknown effect: {effect}")
        if effect in FORBIDDEN_GOAL_EFFECTS:
            raise GoalLoopValidationError(f"forbidden effect: {effect}")
        if effect not in normalized:
            normalized.append(effect)
    return normalized


def normalize_budgets(value) -> dict:
    raw = value if isinstance(value, dict) else {}

    def bounded_int(key: str, default: int, max_value: int) -> int:
        try:
            parsed = int(raw.get(key, default))
        except (TypeError, ValueError) as exc:
            raise GoalLoopValidationError(f"budget {key} must be an integer") from exc
        if parsed < 1 or parsed > max_value:
            raise GoalLoopValidationError(f"budget {key} must be 1..{max_value}")
        return parsed

    return {
        "max_steps": bounded_int("max_steps", 3, MAX_BUDGET_STEPS),
        "max_model_calls": bounded_int("max_model_calls", 6, MAX_BUDGET_CALLS),
        "max_tool_calls": bounded_int("max_tool_calls", 6, MAX_BUDGET_CALLS),
        "max_minutes": bounded_int("max_minutes", 30, MAX_BUDGET_MINUTES),
    }


def normalize_actions(value) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise GoalLoopValidationError("actions must be a list")
    if len(value) > MAX_GOAL_ACTIONS:
        raise GoalLoopValidationError(f"actions has too many entries (max {MAX_GOAL_ACTIONS})")
    rows = []
    for idx, item in enumerate(value, 1):
        if not isinstance(item, dict):
            raise GoalLoopValidationError(f"actions[{idx}] must be an object")
        if item.get("schema") != ACTION_SCHEMA:
            raise GoalLoopValidationError(f"actions[{idx}] has unsupported action schema: {item.get('schema')}")
        if "command" in item or "shell" in item:
            raise GoalLoopValidationError(f"actions[{idx}] must not contain shell or command")
        rows.append(dict(item))
    return rows


def validate_scope_paths(scope: list[str], *, path_checker=None) -> None:
    for item in scope:
        text = str(item or "").strip()
        if not text:
            continue
        path = pathlib.PurePosixPath(text.replace("\\", "/"))
        if any(part in {"", ".."} for part in path.parts):
            raise GoalLoopValidationError("scope paths must not contain traversal")
        if path_checker is not None:
            path_checker("scope", text)


def make_goal_loop_record(
    objective: str,
    *,
    loop_id: str | None = None,
    planner: str | None = None,
    scope: list[str] | None = None,
    allowed_tools: list[str] | None = None,
    allowed_effects: list[str] | None = None,
    budgets: dict | None = None,
    stop_conditions: list[str] | None = None,
    actions: list[dict] | None = None,
) -> dict:
    objective = str(objective or "").strip()
    if not objective:
        raise GoalLoopValidationError("objective is required")
    if len(objective) > MAX_OBJECTIVE_CHARS:
        raise GoalLoopValidationError(f"objective is too long (max {MAX_OBJECTIVE_CHARS} chars)")
    stamp = utc_now()
    normalized_actions = normalize_actions(actions)
    planner = str(planner or "").strip() or (
        GOAL_LOOP_PLANNER_EXPLICIT_ACTIONS if normalized_actions else GOAL_LOOP_PLANNER_DISABLED
    )
    if planner not in SUPPORTED_GOAL_PLANNERS:
        raise GoalLoopValidationError(f"unsupported goal planner: {planner}")
    if planner == GOAL_LOOP_PLANNER_MODEL_READONLY and normalized_actions:
        raise GoalLoopValidationError("model_readonly goal loops must not contain explicit actions")
    if planner == GOAL_LOOP_PLANNER_MODEL_CONFIRMED and normalized_actions:
        raise GoalLoopValidationError("model_confirmed goal loops must not contain explicit actions")
    phases = ["plan", "retrieve", "inspect", "audit", "propose", "checkpoint"]
    if planner == GOAL_LOOP_PLANNER_EXPLICIT_ACTIONS:
        phases = ["plan", "retrieve", "act", "observe", "audit", "checkpoint"]
    elif planner == GOAL_LOOP_PLANNER_MODEL_CONFIRMED:
        phases = ["plan", "retrieve", "inspect", "propose", "review", "apply", "audit", "checkpoint"]
    return {
        "schema": GOAL_LOOP_SCHEMA,
        "id": safe_goal_id(loop_id),
        "status": GOAL_LOOP_STATUS_DRAFT,
        "created_at": stamp,
        "updated_at": stamp,
        "objective": objective,
        "planner": planner,
        "scope": normalize_string_list(scope or [], limit=MAX_SCOPE_ITEMS, label="scope"),
        "allowed_tools": normalize_string_list(allowed_tools or [], limit=MAX_ALLOWED_TOOLS, label="allowed_tools"),
        "allowed_effects": normalize_effects(allowed_effects or []),
        "budgets": normalize_budgets(budgets or {}),
        "stop_conditions": normalize_string_list(
            stop_conditions or ["budget_exhausted", "user_stop", "validation_failure"],
            limit=20,
            label="stop_conditions",
        ),
        "phases": phases,
        "actions": normalized_actions,
        "execution_enabled": bool(
            normalized_actions or planner in {GOAL_LOOP_PLANNER_MODEL_READONLY, GOAL_LOOP_PLANNER_MODEL_CONFIRMED}
        ),
    }


def validate_goal_loop_record(record: dict, *, path_checker=None) -> dict:
    if not isinstance(record, dict):
        raise GoalLoopValidationError("goal loop record must be a JSON object")
    if record.get("schema") != GOAL_LOOP_SCHEMA:
        raise GoalLoopValidationError(f"unsupported goal loop schema: {record.get('schema')}")
    normalized = make_goal_loop_record(
        str(record.get("objective") or ""),
        loop_id=str(record.get("id") or ""),
        planner=str(record.get("planner") or ""),
        scope=record.get("scope") if isinstance(record.get("scope"), list) else [],
        allowed_tools=record.get("allowed_tools") if isinstance(record.get("allowed_tools"), list) else [],
        allowed_effects=record.get("allowed_effects") if isinstance(record.get("allowed_effects"), list) else [],
        budgets=record.get("budgets") if isinstance(record.get("budgets"), dict) else {},
        stop_conditions=record.get("stop_conditions") if isinstance(record.get("stop_conditions"), list) else None,
        actions=record.get("actions") if "actions" in record else [],
    )
    validate_scope_paths(normalized["scope"], path_checker=path_checker)
    requested_effects = set(normalized["allowed_effects"])
    if normalized.get("planner") == GOAL_LOOP_PLANNER_MODEL_READONLY and not requested_effects <= MODEL_READONLY_GOAL_EFFECTS:
        normalized["status"] = GOAL_LOOP_STATUS_REJECTED
        normalized["approval"] = "not-applicable"
        normalized["error"] = (
            "model_readonly goal loops may use only read_context, read_allowed_files, "
            "write_motoko_state, and propose_project_changes"
        )
    elif normalized.get("planner") == GOAL_LOOP_PLANNER_MODEL_CONFIRMED and not requested_effects <= MODEL_CONFIRMED_GOAL_EFFECTS:
        normalized["status"] = GOAL_LOOP_STATUS_REJECTED
        normalized["approval"] = "not-applicable"
        normalized["error"] = (
            "model_confirmed goal loops may use only read_context, read_allowed_files, "
            "write_motoko_state, propose_project_changes, and write_allowed_project"
        )
    elif requested_effects & APPROVAL_REQUIRED_EFFECTS:
        normalized["status"] = GOAL_LOOP_STATUS_NEEDS_APPROVAL
        normalized["approval"] = "required-for-" + ",".join(sorted(requested_effects & APPROVAL_REQUIRED_EFFECTS))
    elif requested_effects <= (LOW_RISK_GOAL_EFFECTS | LOW_RISK_REPEATABLE_EFFECTS):
        normalized["status"] = GOAL_LOOP_STATUS_DRAFT
        normalized["approval"] = "not-required-for-preview"
    else:
        normalized["status"] = GOAL_LOOP_STATUS_NEEDS_APPROVAL
        normalized["approval"] = "required-for-nonstandard-effects"
    return normalized


def read_goal_loop(path: pathlib.Path, *, path_checker=None) -> dict:
    data = safe_load_json(path)
    return validate_goal_loop_record(data, path_checker=path_checker)


def write_goal_loop(path: pathlib.Path, record: dict) -> None:
    atomic_write(path, json.dumps(record, ensure_ascii=False, indent=2) + "\n")


def list_goal_loops(root: pathlib.Path) -> list[dict]:
    if not root.exists():
        return []
    rows = []
    for path in sorted(root.glob("*.json")):
        try:
            row = safe_load_json(path)
        except OSError:
            continue
        if isinstance(row, dict) and row.get("schema") == GOAL_LOOP_SCHEMA:
            row = dict(row)
            row["path"] = str(path)
            rows.append(row)
    rows.sort(key=lambda row: (row.get("updated_at", ""), row.get("id", "")), reverse=True)
    return rows


def format_goal_loop(record: dict) -> str:
    lines = [
        "goal loop preview:",
        f"id: {record.get('id', '')}",
        f"status: {record.get('status', '')}",
        f"approval: {record.get('approval', '')}",
        f"execution enabled: {'yes' if record.get('execution_enabled') else 'no'}",
        f"planner: {record.get('planner', '')}",
        f"objective: {record.get('objective', '')}",
        "scope: " + (", ".join(record.get("scope", [])) if record.get("scope") else "none"),
        "allowed tools: " + (", ".join(record.get("allowed_tools", [])) if record.get("allowed_tools") else "none"),
        "allowed effects: " + ", ".join(record.get("allowed_effects", [])),
    ]
    budgets = record.get("budgets", {})
    lines.append(
        "budgets: "
        f"steps={budgets.get('max_steps')} "
        f"model_calls={budgets.get('max_model_calls')} "
        f"tool_calls={budgets.get('max_tool_calls')} "
        f"minutes={budgets.get('max_minutes')}"
    )
    lines.append("stop conditions: " + ", ".join(record.get("stop_conditions", [])))
    lines.append("phases: " + ", ".join(record.get("phases", [])))
    lines.append(f"actions: {len(record.get('actions', []) or [])}")
    if record.get("error"):
        lines.append(f"error: {record.get('error')}")
    if record.get("planner") == GOAL_LOOP_PLANNER_MODEL_READONLY:
        lines.append("runner: read-only model planner; run with motoko goal run FILE --yes")
    elif record.get("planner") == GOAL_LOOP_PLANNER_MODEL_CONFIRMED:
        lines.append("runner: model planner with explicit apply; run to propose, then motoko goal apply RUN_ID --yes")
    elif record.get("execution_enabled"):
        lines.append("runner: explicit action list; run with motoko goal run FILE --yes")
    else:
        lines.append("runner: disabled until an explicit action list is attached")
    return "\n".join(lines)


def format_goal_loop_list(rows: list[dict], *, limit: int = 20) -> str:
    limit = max(1, min(200, int(limit or 20)))
    rows = rows[:limit]
    if not rows:
        return "goal loops: none"
    lines = [f"goal loops: {len(rows)} shown"]
    for row in rows:
        lines.append(
            f"- {row.get('id', '')}  {row.get('status', '')}  "
            f"effects={','.join(row.get('allowed_effects', []))}  "
            f"{row.get('objective', '')[:120]}"
        )
    return "\n".join(lines)
