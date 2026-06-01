"""Realm-local procedural skill helpers for Motoko."""

from __future__ import annotations

import datetime as _dt
import pathlib
import re

from motoko_core.skill_registry import (
    CODE_INTELLIGENCE_EFFECT,
    MOTOKO_CODEBASE_HANDLER,
    ORG_STRUCTURAL_HANDLER,
    ORG_TEMPORAL_HANDLER,
    PROMPT_CONTEXT_EFFECT,
    PROMPT_ONLY_HANDLER,
    RETRIEVAL_PLAN_EFFECT,
    SOURCE_SCOPED_EVIDENCE_EFFECT,
    STRUCTURED_ORG_EVIDENCE_EFFECT,
    normalize_skill_effects,
    normalize_skill_handler,
)
from motoko_core.text import compact_text


SKILL_SCHEMA = "motoko-skill-v3"
LEGACY_SKILL_SCHEMA = "motoko-skill-v1"
PREVIOUS_SKILL_SCHEMA = "motoko-skill-v2"
SKILL_MANAGE_SCHEMA = "motoko-skill-manage-v1"
SKILL_LIFECYCLE_SCHEMA = "motoko-skill-lifecycle-v1"
SKILL_MANAGE_ACTIONS = {"create", "patch", "write_file", "remove_file"}
SKILL_STATE_ACTIVE = "active"
SKILL_STATE_ARCHIVED = "archived"
MAX_SKILL_NAME = 64
MAX_SKILL_DESCRIPTION = 400
MAX_SKILL_BODY = 12000
MAX_SKILL_SUPPORT_FILE = 100000
DEFAULT_SKILL_CONTEXT_LIMIT = 2
DEFAULT_SKILL_CONTEXT_CHARS = 5000
DEFAULT_SKILL_KIND = "workflow"
DEFAULT_SKILL_HANDLER = PROMPT_ONLY_HANDLER
DEFAULT_SKILL_EFFECTS = [PROMPT_CONTEXT_EFFECT]
ORG_STRUCTURAL_SKILL = "org-structural-query"
ORG_TEMPORAL_SKILL = "org-temporal-retrieval"
MOTOKO_CODEBASE_SKILL = "motoko-codebase-maintainer"
MOTOKO_RETRIEVAL_MAINTAINER_SKILL = "motoko-retrieval-maintainer"
MOTOKO_REFACTOR_CRAFT_SKILL = "motoko-refactor-craft"
MOTOKO_AGENTIC_BOUNDARY_SKILL = "motoko-agentic-boundary-review"
ALLOWED_SKILL_SUPPORT_DIRS = {"references", "templates", "scripts"}

BUILTIN_SKILLS = [
    {
        "schema": SKILL_SCHEMA,
        "name": ORG_TEMPORAL_SKILL,
        "slug": ORG_TEMPORAL_SKILL,
        "description": "Source-scoped retrieval for latest dated Org entries",
        "version": "3",
        "kind": "retrieval",
        "triggers": [
            "last/latest/recent N dated entries",
            "explicit named Org source such as logbook.org",
        ],
        "handler": ORG_TEMPORAL_HANDLER,
        "allowed_effects": [RETRIEVAL_PLAN_EFFECT, SOURCE_SCOPED_EVIDENCE_EFFECT],
        "support_files": [],
        "security": "builtin deterministic handler; no script execution",
        "source_schema": SKILL_SCHEMA,
        "created_at": "2026-05-24T00:00:00+00:00",
        "updated_at": "2026-05-24T00:00:00+00:00",
        "source": "builtin",
        "builtin": True,
        "path": "builtin:org-temporal-retrieval",
        "body": "\n".join(
            [
                "When a query asks for the last/latest/recent N dated entries present in a named Org source,",
                "treat that as a source-scoped temporal retrieval task.",
                "",
                "Procedure:",
                "- Prefer the explicitly named file or path before broad corpus candidates.",
                "- Parse dated Org headings from that source and choose the newest distinct dates actually present.",
                "- Do not infer missing intervening calendar days; if May 23 and May 19 are the newest entries, those are the last two days present.",
                "- Include bounded source excerpts for each selected date and preserve source provenance.",
                "- In the final answer, state which dates were selected and avoid implying that absent dates were retrieved.",
                "",
                "This skill activates the built-in deterministic retrieval handler for source selection, date parsing, and evidence extraction.",
            ]
        ),
    },
    {
        "schema": SKILL_SCHEMA,
        "name": ORG_STRUCTURAL_SKILL,
        "slug": ORG_STRUCTURAL_SKILL,
        "description": "Deterministic retrieval for Org tags, TODOs, priorities, and dated headings",
        "version": "3",
        "kind": "retrieval",
        "triggers": [
            "all Org elements with a tag",
            "headings/tasks tagged with a project tag",
            "TODO/DONE/priority/deadline/scheduled Org queries",
        ],
        "handler": ORG_STRUCTURAL_HANDLER,
        "allowed_effects": [RETRIEVAL_PLAN_EFFECT, STRUCTURED_ORG_EVIDENCE_EFFECT],
        "support_files": [],
        "security": "builtin deterministic handler; no script execution",
        "source_schema": SKILL_SCHEMA,
        "created_at": "2026-05-31T00:00:00+00:00",
        "updated_at": "2026-05-31T00:00:00+00:00",
        "source": "builtin",
        "builtin": True,
        "path": "builtin:org-structural-query",
        "body": "\n".join(
            [
                "When a query asks for Org structure, tags, TODO states, priorities, deadlines, scheduled items, or dated headings,",
                "treat that as a deterministic Org evidence-selection task before final synthesis.",
                "",
                "Procedure:",
                "- Let the user ask naturally; do not require Org syntax or a slash command.",
                "- Parse Org headings, inherited tags, TODO state, priority, DEADLINE, SCHEDULED, and dated headings programmatically.",
                "- Scope to an explicitly named file/path when the query names one; otherwise search attached Org indexes.",
                "- Prefer source-linked Org evidence rows over broad chunk summaries.",
                "- Return bounded, cited excerpts so the final answer can explain what matched and where.",
                "",
                "This skill activates the built-in deterministic retrieval handler for Org structure queries.",
            ]
        ),
    },
    {
        "schema": SKILL_SCHEMA,
        "name": MOTOKO_CODEBASE_SKILL,
        "slug": MOTOKO_CODEBASE_SKILL,
        "description": "Maintain and improve Motoko using deterministic source-code intelligence",
        "version": "3",
        "kind": "codebase",
        "triggers": [
            "improve Motoko",
            "refactor Motoko",
            "find a Motoko command implementation",
            "trace Motoko tests or source ownership",
            "prepare Motoko to improve herself",
        ],
        "handler": MOTOKO_CODEBASE_HANDLER,
        "allowed_effects": [PROMPT_CONTEXT_EFFECT, CODE_INTELLIGENCE_EFFECT],
        "support_files": [],
        "security": "builtin deterministic code-intelligence handler; no script execution",
        "source_schema": SKILL_SCHEMA,
        "created_at": "2026-05-31T00:00:00+00:00",
        "updated_at": "2026-05-31T00:00:00+00:00",
        "source": "builtin",
        "builtin": True,
        "path": "builtin:motoko-codebase-maintainer",
        "body": "\n".join(
            [
                "When improving Motoko herself, treat repository understanding as a deterministic code-intelligence task before model synthesis.",
                "",
                "Procedure:",
                "- Read AGENTS.md, docs/project-context.md, docs/agentic-capability-design.md, and relevant docs before architectural or authority changes.",
                "- For long self-improvement work, follow docs/motoko-self-improvement-playbook.md as the current craft checklist.",
                "- Use motoko code-map for a repo overview and motoko code-query QUERY to find commands, handlers, symbols, tests, ownership boundaries, and root-facade hotspots.",
                "- Prefer existing modules in motoko_core over adding more root-facade orchestration.",
                "- Keep changes stdlib-only, realm-local, inspectable, and covered by regression/eval tests.",
                "- For skills/tools, preserve the review-first planner boundary: models may propose, Motoko validators decide, and mutating actions require explicit confirmation.",
                "- For derived artifacts, include schema/provenance and either deterministic migration or source reprocessing through visible resumable work.",
                "- Run py_compile, focused tests, git diff --check, and nix flake check before committing.",
                "",
                "This skill activates deterministic Motoko codebase lookup for self-improvement queries.",
            ]
        ),
    },
    {
        "schema": SKILL_SCHEMA,
        "name": MOTOKO_RETRIEVAL_MAINTAINER_SKILL,
        "slug": MOTOKO_RETRIEVAL_MAINTAINER_SKILL,
        "description": "Diagnose and improve Motoko retrieval without guessing",
        "version": "3",
        "kind": "self-improvement",
        "triggers": [
            "retrieval failure or weak sources",
            "sources missing the right file or span",
            "improve hybrid retrieval or rerank",
            "answer ignored retrieved evidence",
        ],
        "handler": PROMPT_ONLY_HANDLER,
        "allowed_effects": [PROMPT_CONTEXT_EFFECT],
        "support_files": [],
        "security": "builtin prompt-only procedure; no script execution",
        "source_schema": SKILL_SCHEMA,
        "created_at": "2026-05-31T00:00:00+00:00",
        "updated_at": "2026-05-31T00:00:00+00:00",
        "source": "builtin",
        "builtin": True,
        "path": "builtin:motoko-retrieval-maintainer",
        "body": "\n".join(
            [
                "Use this procedure when improving Motoko retrieval, source grounding, or HRAG behavior.",
                "",
                "Procedure:",
                "- Start with the evidence path, not the answer style.",
                "- Use /sources, retrieval-preview, retrieval-debug, evidence-query, vector-query --rerank, and feedback-eval to classify the failure.",
                "- Name the failure precisely: recall, ranking, stale data, source lifecycle, span selection, prompt packing, final synthesis, or route/model failure.",
                "- Preserve hybrid retrieval: lexical/path/date/task truth, evidence rows, embeddings, and rerank should reinforce each other rather than replace each other.",
                "- Add deterministic extraction or service-owned planning before adding prompt prose.",
                "- Add or update fixtures so the same retrieval failure is caught next time.",
                "- Keep source rows and diagnostics content-safe outside the user's Motoko state.",
            ]
        ),
    },
    {
        "schema": SKILL_SCHEMA,
        "name": MOTOKO_REFACTOR_CRAFT_SKILL,
        "slug": MOTOKO_REFACTOR_CRAFT_SKILL,
        "description": "Refactor Motoko with service boundaries and careful validation",
        "version": "4",
        "kind": "self-improvement",
        "triggers": [
            "refactor Motoko",
            "move code out of root facade",
            "extract service boundary",
            "quality craftsmanship pass",
        ],
        "handler": PROMPT_ONLY_HANDLER,
        "allowed_effects": [PROMPT_CONTEXT_EFFECT],
        "support_files": [],
        "security": "builtin prompt-only procedure; no script execution",
        "source_schema": SKILL_SCHEMA,
        "created_at": "2026-05-31T00:00:00+00:00",
        "updated_at": "2026-05-31T00:00:00+00:00",
        "source": "builtin",
        "builtin": True,
        "path": "builtin:motoko-refactor-craft",
        "body": "\n".join(
            [
                "Use this procedure for Motoko refactors and craftsmanship work.",
                "",
                "Procedure:",
                "- Read the local docs first: AGENTS.md, project-context, and the self-improvement playbook.",
                "- Characterize behavior with tests before moving live orchestration.",
                "- Prefer pure helpers, then fakeable service boundaries, then live subsystem extraction.",
                "- Keep the root motoko executable as the compatibility facade until the extracted boundary is safer and simpler.",
                "- When a service owns a per-record decision, consider moving the collection loop into that service too, with injected state/filesystem callbacks and cancellation checkpoints.",
                "- Keep root authority at the edge: realm-local paths, current-state loading, model calls, and filesystem mutation stay behind callbacks unless there is a reviewed boundary change.",
                "- Preserve stdlib-only runtime, realm-local state, content-free observability, migrations, durable checkpoints, and pause/resume behavior.",
                "- For shared state/progress writes, use a unique same-directory temporary file per writer before atomic replace; never reuse one fixed .tmp path across parallel workers.",
                "- Add concurrency regressions for background progress, vector/evidence refresh, ledgers, and any other state file touched by parallel or interruptible work.",
                "- Make each commit coherent, update docs with the new ownership boundary, and run syntax, regression, eval, TTY, diff-check, and flake checks.",
            ]
        ),
    },
    {
        "schema": SKILL_SCHEMA,
        "name": MOTOKO_AGENTIC_BOUNDARY_SKILL,
        "slug": MOTOKO_AGENTIC_BOUNDARY_SKILL,
        "description": "Review Motoko skills, tools, actions, and goal loops safely",
        "version": "3",
        "kind": "self-improvement",
        "triggers": [
            "skill tool or action authority",
            "goal loop or project write",
            "agentic capability design",
            "Hermes-inspired skill machinery",
        ],
        "handler": PROMPT_ONLY_HANDLER,
        "allowed_effects": [PROMPT_CONTEXT_EFFECT],
        "support_files": [],
        "security": "builtin prompt-only procedure; no script execution",
        "source_schema": SKILL_SCHEMA,
        "created_at": "2026-05-31T00:00:00+00:00",
        "updated_at": "2026-05-31T00:00:00+00:00",
        "source": "builtin",
        "builtin": True,
        "path": "builtin:motoko-agentic-boundary-review",
        "body": "\n".join(
            [
                "Use this procedure before widening Motoko skills, script tools, actions, goal loops, or project mutation.",
                "",
                "Procedure:",
                "- Treat model output as planning data only; code-owned validators decide what can run.",
                "- Check the action schema, effect tier, approval record, argument scope, realm boundary, allowlist, .motokoignore, and ledger behavior.",
                "- Scripts stay inert unless tool metadata, fingerprints, approval, typed action records, validators, and explicit confirmation all line up.",
                "- Project mutation goes through project_file_write or reviewed proposals, never raw script writes.",
                "- Run skill scan and action-eval, then add focused regression coverage for every new authority path.",
                "- Keep network, broad terminal tools, service control, and privileged actions disabled until a separate design accepts them.",
            ]
        ),
    },
]


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _empty_lifecycle_record(slug: str) -> dict:
    return {
        "slug": slug,
        "state": SKILL_STATE_ACTIVE,
        "pinned": False,
        "selected_count": 0,
        "patch_count": 0,
        "support_file_change_count": 0,
        "created_count": 0,
        "last_selected_at": "",
        "last_patched_at": "",
        "last_restored_at": "",
        "archived_at": "",
        "updated_at": "",
        "notes": [],
    }


def normalize_skill_lifecycle_state(data) -> dict:
    state = dict(data) if isinstance(data, dict) else {}
    records = state.get("skills")
    if not isinstance(records, dict):
        records = {}
    normalized = {}
    for raw_slug, raw_record in records.items():
        slug = skill_slug(raw_slug)
        if not slug:
            continue
        record = _empty_lifecycle_record(slug)
        if isinstance(raw_record, dict):
            record.update({key: value for key, value in raw_record.items() if key in record})
        record["slug"] = slug
        record["state"] = SKILL_STATE_ARCHIVED if record.get("state") == SKILL_STATE_ARCHIVED else SKILL_STATE_ACTIVE
        record["pinned"] = bool(record.get("pinned"))
        for key in ("selected_count", "patch_count", "support_file_change_count", "created_count"):
            try:
                record[key] = max(0, int(record.get(key, 0) or 0))
            except (TypeError, ValueError):
                record[key] = 0
        notes = record.get("notes")
        record["notes"] = [str(item)[:300] for item in notes[:20]] if isinstance(notes, list) else []
        normalized[slug] = record
    return {
        "schema": SKILL_LIFECYCLE_SCHEMA,
        "updated_at": str(state.get("updated_at") or ""),
        "skills": normalized,
    }


def skill_lifecycle_record(state: dict, name: str) -> dict:
    normalized = normalize_skill_lifecycle_state(state)
    slug = skill_slug(name)
    if not slug:
        raise SystemExit("skill name is empty")
    return dict(normalized["skills"].get(slug) or _empty_lifecycle_record(slug))


def write_skill_lifecycle_record(state: dict, name: str, updates: dict) -> dict:
    normalized = normalize_skill_lifecycle_state(state)
    slug = skill_slug(name)
    if not slug:
        raise SystemExit("skill name is empty")
    record = dict(normalized["skills"].get(slug) or _empty_lifecycle_record(slug))
    for key, value in (updates or {}).items():
        if key in record:
            record[key] = value
    record["slug"] = slug
    record["state"] = SKILL_STATE_ARCHIVED if record.get("state") == SKILL_STATE_ARCHIVED else SKILL_STATE_ACTIVE
    record["pinned"] = bool(record.get("pinned"))
    stamp = _now()
    record["updated_at"] = stamp
    normalized["skills"][slug] = record
    normalized["updated_at"] = stamp
    return normalized


def record_skill_lifecycle_event(state: dict, name: str, event: str, *, note: str = "") -> dict:
    record = skill_lifecycle_record(state, name)
    stamp = _now()
    event = str(event or "").strip().lower()
    updates = {}
    if event == "selected":
        updates["selected_count"] = int(record.get("selected_count", 0) or 0) + 1
        updates["last_selected_at"] = stamp
    elif event in {"patch", "write_file", "remove_file"}:
        updates["patch_count"] = int(record.get("patch_count", 0) or 0) + 1
        updates["last_patched_at"] = stamp
        if event in {"write_file", "remove_file"}:
            updates["support_file_change_count"] = int(record.get("support_file_change_count", 0) or 0) + 1
    elif event == "create":
        updates["created_count"] = int(record.get("created_count", 0) or 0) + 1
        updates["last_patched_at"] = stamp
    elif event == "restore":
        updates["state"] = SKILL_STATE_ACTIVE
        updates["archived_at"] = ""
        updates["last_restored_at"] = stamp
    elif event == "archive":
        updates["state"] = SKILL_STATE_ARCHIVED
        updates["archived_at"] = stamp
    else:
        return normalize_skill_lifecycle_state(state)
    if note:
        notes = list(record.get("notes", []) or [])
        notes.append(f"{stamp} {event}: {str(note)[:240]}")
        updates["notes"] = notes[-20:]
    return write_skill_lifecycle_record(state, name, updates)


def apply_skill_lifecycle(rows: list[dict], state: dict) -> list[dict]:
    normalized = normalize_skill_lifecycle_state(state)
    records = normalized.get("skills", {})
    output = []
    for row in rows:
        item = dict(row)
        record = records.get(item.get("slug", ""))
        if record:
            item["lifecycle"] = dict(record)
            item["lifecycle_state"] = record.get("state", SKILL_STATE_ACTIVE)
            item["pinned"] = bool(record.get("pinned"))
            item["selected_count"] = int(record.get("selected_count", 0) or 0)
            item["last_selected_at"] = record.get("last_selected_at", "")
            item["patch_count"] = int(record.get("patch_count", 0) or 0)
        else:
            item["lifecycle_state"] = SKILL_STATE_ACTIVE
            item["pinned"] = False
            item["selected_count"] = 0
            item["last_selected_at"] = ""
            item["patch_count"] = 0
        output.append(item)
    return output


def skill_is_archived(state: dict, name: str) -> bool:
    return skill_lifecycle_record(state, name).get("state") == SKILL_STATE_ARCHIVED


def skill_slug(value: str) -> str:
    slug = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    slug = re.sub(r"[^a-z0-9.-]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip(".-")
    return slug[:MAX_SKILL_NAME].strip(".-")


def frontmatter_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def skill_directory(root: pathlib.Path, name: str) -> pathlib.Path:
    slug = skill_slug(name)
    if not slug:
        raise SystemExit("skill name is empty")
    return root / slug


def skill_markdown_path(root: pathlib.Path, name: str) -> pathlib.Path:
    return skill_directory(root, name) / "SKILL.md"


def parse_skill_markdown(text: str, *, path: pathlib.Path | None = None) -> dict:
    frontmatter: dict[str, str | list[str]] = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end >= 0:
            raw_frontmatter = text[4:end]
            body = text[end + 5 :]
            current_key = ""
            for line in raw_frontmatter.splitlines():
                stripped = line.strip()
                if current_key and stripped.startswith("- "):
                    value = stripped[2:].strip().strip("'\"")
                    existing = frontmatter.setdefault(current_key, [])
                    if isinstance(existing, list) and value:
                        existing.append(value)
                    continue
                current_key = ""
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip().strip("'\"")
                frontmatter[key] = value
                if not value:
                    frontmatter[key] = []
                    current_key = key
    name = str(frontmatter.get("name") or (path.parent.name if path else ""))
    description = str(frontmatter.get("description", ""))
    if not description:
        for line in body.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                description = stripped
                break
    source_schema = str(frontmatter.get("schema") or LEGACY_SKILL_SCHEMA)
    kind = str(frontmatter.get("kind") or DEFAULT_SKILL_KIND)
    handler = normalize_skill_handler(str(frontmatter.get("handler") or ""))
    allowed_effects = normalize_skill_effects(frontmatter.get("allowed_effects"), handler=handler)
    triggers = frontmatter_list(frontmatter.get("triggers"))
    support_files = frontmatter_list(frontmatter.get("support_files"))
    tools = frontmatter_list(frontmatter.get("tools"))
    return {
        "schema": SKILL_SCHEMA,
        "source_schema": source_schema,
        "name": name,
        "slug": skill_slug(name),
        "description": compact_text(description, MAX_SKILL_DESCRIPTION) if description else "",
        "version": str(frontmatter.get("version") or ("1" if source_schema == LEGACY_SKILL_SCHEMA else "3")),
        "kind": kind,
        "triggers": triggers,
        "handler": handler,
        "allowed_effects": allowed_effects,
        "support_files": support_files,
        "tools": tools,
        "security": str(frontmatter.get("security") or "prompt-only learned skill; no script execution"),
        "can_upgrade_deterministically": source_schema != SKILL_SCHEMA,
        "created_at": str(frontmatter.get("created_at", "")),
        "updated_at": str(frontmatter.get("updated_at", "")),
        "source": str(frontmatter.get("source", "")),
        "body": body.strip(),
        "path": str(path) if path else "",
    }


def format_skill_markdown(
    *,
    name: str,
    description: str,
    body: str,
    kind: str = DEFAULT_SKILL_KIND,
    handler: str = DEFAULT_SKILL_HANDLER,
    allowed_effects: list[str] | None = None,
    triggers: list[str] | None = None,
    support_files: list[str] | None = None,
    tools: list[str] | None = None,
    security: str = "prompt-only learned skill; no script execution",
    source: str = "manual",
    created_at: str = "",
    updated_at: str = "",
) -> str:
    name = compact_text(str(name or "").strip(), MAX_SKILL_NAME)
    description = compact_text(str(description or "").strip(), MAX_SKILL_DESCRIPTION)
    body = str(body or "").strip()
    if not name:
        raise SystemExit("skill name is empty")
    if not description:
        raise SystemExit("skill description is empty")
    if not body:
        raise SystemExit("skill body is empty")
    if len(body) > MAX_SKILL_BODY:
        raise SystemExit(f"skill body is too large ({len(body)} chars, max {MAX_SKILL_BODY})")
    stamp = _now()
    created_at = created_at or stamp
    updated_at = updated_at or stamp
    handler = normalize_skill_handler(handler)
    allowed_effects = normalize_skill_effects(allowed_effects, handler=handler)
    triggers = triggers or []
    support_files = support_files or []
    tools = tools or []
    return "\n".join(
        [
            "---",
            f"schema: {SKILL_SCHEMA}",
            "version: 3",
            f"name: {name}",
            f"description: {description}",
            f"kind: {kind or DEFAULT_SKILL_KIND}",
            f"handler: {handler or DEFAULT_SKILL_HANDLER}",
            f"allowed_effects: {', '.join(allowed_effects)}",
            f"triggers: {', '.join(triggers)}",
            f"support_files: {', '.join(support_files)}",
            f"tools: {', '.join(tools)}",
            f"security: {security}",
            f"created_at: {created_at}",
            f"updated_at: {updated_at}",
            f"source: {source or 'manual'}",
            "---",
            "",
            body,
            "",
        ]
    )


def iter_skill_files(root: pathlib.Path) -> list[pathlib.Path]:
    if not root.exists():
        return []
    files = []
    for path in root.rglob("SKILL.md"):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        if path.is_file() and not path.is_symlink():
            files.append(path)
    return sorted(files, key=lambda path: str(path.relative_to(root)))


def list_skills(root: pathlib.Path) -> list[dict]:
    rows = [dict(row) for row in BUILTIN_SKILLS]
    by_slug = {row.get("slug", ""): idx for idx, row in enumerate(rows)}
    for path in iter_skill_files(root):
        try:
            row = parse_skill_markdown(path.read_text(encoding="utf-8"), path=path)
        except OSError:
            continue
        if row.get("name"):
            slug = row.get("slug", "")
            if slug in by_slug:
                rows[by_slug[slug]] = row
            else:
                by_slug[slug] = len(rows)
                rows.append(row)
    rows.sort(key=lambda row: row.get("slug", ""))
    return rows


def load_skill(root: pathlib.Path, name: str) -> dict:
    direct = skill_markdown_path(root, name)
    candidates = []
    if direct.exists():
        candidates.append(direct)
    slug = skill_slug(name)
    for path in iter_skill_files(root):
        try:
            row = parse_skill_markdown(path.read_text(encoding="utf-8"), path=path)
        except OSError:
            continue
        if row.get("slug") == slug or str(row.get("name", "")).lower() == str(name).lower():
            candidates.append(path)
    unique = []
    seen = set()
    for path in candidates:
        resolved = str(path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    if not unique:
        for row in BUILTIN_SKILLS:
            if row.get("slug") == slug or str(row.get("name", "")).lower() == str(name).lower():
                return dict(row)
        raise SystemExit(f"skill not found: {name}")
    if len(unique) > 1:
        raise SystemExit(f"ambiguous skill name: {name}")
    path = unique[0]
    return parse_skill_markdown(path.read_text(encoding="utf-8"), path=path)


def save_skill(
    root: pathlib.Path,
    *,
    name: str,
    description: str,
    body: str,
    kind: str = DEFAULT_SKILL_KIND,
    handler: str = DEFAULT_SKILL_HANDLER,
    allowed_effects: list[str] | None = None,
    triggers: list[str] | None = None,
    support_files: list[str] | None = None,
    tools: list[str] | None = None,
    security: str = "prompt-only learned skill; no script execution",
    source: str = "manual",
    replace: bool = False,
    writer,
) -> dict:
    path = skill_markdown_path(root, name)
    builtin_conflict = any(row.get("slug") == skill_slug(name) for row in BUILTIN_SKILLS)
    if (path.exists() or builtin_conflict) and not replace:
        raise SystemExit(f"skill already exists: {skill_slug(name)} (use --replace)")
    created_at = ""
    if path.exists():
        try:
            existing = parse_skill_markdown(path.read_text(encoding="utf-8"), path=path)
            created_at = existing.get("created_at", "")
        except OSError:
            created_at = ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    text = format_skill_markdown(
        name=name,
        description=description,
        body=body,
        kind=kind,
        handler=handler,
        allowed_effects=allowed_effects,
        triggers=triggers,
        support_files=support_files,
        tools=tools,
        security=security,
        source=source,
        created_at=created_at,
    )
    writer(path, text)
    return load_skill(root, name)


def normalize_skill_manage_action(value: str | None) -> str:
    action = str(value or "create").strip().lower().replace("-", "_")
    if action not in SKILL_MANAGE_ACTIONS:
        raise SystemExit(f"unsupported skill_manage action: {action or value}")
    return action


def _support_file_relpath(file_path: str) -> pathlib.PurePosixPath:
    raw = str(file_path or "").strip().replace("\\", "/")
    if not raw:
        raise SystemExit("support file path is empty")
    path = pathlib.PurePosixPath(raw)
    parts = path.parts
    if path.is_absolute() or not parts:
        raise SystemExit("support file path must be relative")
    if len(parts) < 2 or parts[0] not in ALLOWED_SKILL_SUPPORT_DIRS:
        allowed = ", ".join(sorted(ALLOWED_SKILL_SUPPORT_DIRS))
        raise SystemExit(f"support file path must start with one of: {allowed}")
    if any(part in {"", ".", ".."} or part.startswith(".") for part in parts):
        raise SystemExit("support file path must not contain traversal or hidden path components")
    return path


def _load_user_skill_for_manage(root: pathlib.Path, name: str) -> tuple[dict, pathlib.Path, pathlib.Path]:
    row = load_skill(root, name)
    if row.get("builtin"):
        raise SystemExit(f"cannot modify built-in skill: {row.get('slug', name)}")
    path_text = row.get("path", "")
    if not path_text:
        raise SystemExit(f"skill has no writable path: {name}")
    path = pathlib.Path(path_text)
    if path.name != "SKILL.md":
        raise SystemExit(f"skill path is not a SKILL.md file: {path}")
    skill_dir = path.parent.resolve(strict=False)
    root_resolved = root.resolve(strict=False)
    try:
        skill_dir.relative_to(root_resolved)
    except ValueError as exc:
        raise SystemExit(f"skill path is outside the skill root: {path}") from exc
    return row, path, skill_dir


def _resolve_support_file(root: pathlib.Path, name: str, file_path: str) -> tuple[dict, pathlib.Path, str]:
    row, _skill_path, skill_dir = _load_user_skill_for_manage(root, name)
    rel = _support_file_relpath(file_path)
    target = (skill_dir / pathlib.Path(*rel.parts)).resolve(strict=False)
    try:
        target.relative_to(skill_dir)
    except ValueError as exc:
        raise SystemExit("support file path escapes the skill directory") from exc
    if target.exists() and target.is_symlink():
        raise SystemExit("refusing to modify symlinked support file")
    return row, target, rel.as_posix()


def list_skill_support_files(root: pathlib.Path, name: str) -> list[dict]:
    row = load_skill(root, name)
    if row.get("builtin"):
        return []
    rows = []
    for item in row.get("support_files", []) or []:
        try:
            _skill, path, rel = _resolve_support_file(root, row.get("name", name), item)
            exists = path.exists() and path.is_file() and not path.is_symlink()
            rows.append(
                {
                    "skill": row.get("slug", ""),
                    "path": str(path),
                    "support_file": rel,
                    "exists": exists,
                    "size_bytes": path.stat().st_size if exists else 0,
                    "updated_at": _dt.datetime.fromtimestamp(
                        path.stat().st_mtime,
                        _dt.timezone.utc,
                    ).astimezone().isoformat(timespec="seconds") if exists else "",
                }
            )
        except (OSError, SystemExit) as exc:
            rows.append(
                {
                    "skill": row.get("slug", ""),
                    "path": "",
                    "support_file": str(item),
                    "exists": False,
                    "size_bytes": 0,
                    "updated_at": "",
                    "error": str(exc),
                }
            )
    return rows


def read_skill_support_file(
    root: pathlib.Path,
    name: str,
    file_path: str,
    *,
    max_chars: int = MAX_SKILL_SUPPORT_FILE,
) -> dict:
    row, path, rel = _resolve_support_file(root, name, file_path)
    if not path.exists() or not path.is_file():
        raise SystemExit(f"support file not found: {rel}")
    if path.is_symlink():
        raise SystemExit(f"refusing to read symlinked support file: {rel}")
    text = path.read_text(encoding="utf-8")
    truncated = len(text) > max_chars
    return {
        "skill": row.get("slug", ""),
        "path": str(path),
        "support_file": rel,
        "content": text[:max_chars],
        "truncated": truncated,
        "size_bytes": path.stat().st_size,
        "updated_at": _dt.datetime.fromtimestamp(
            path.stat().st_mtime,
            _dt.timezone.utc,
        ).astimezone().isoformat(timespec="seconds"),
    }


def _update_skill_support_files(
    root: pathlib.Path,
    name: str,
    *,
    add: str | None = None,
    remove: str | None = None,
    writer,
) -> dict:
    row, path, _skill_dir = _load_user_skill_for_manage(root, name)
    support_files = [item for item in row.get("support_files", []) if item]
    if add and add not in support_files:
        support_files.append(add)
    if remove:
        support_files = [item for item in support_files if item != remove]
    text = format_skill_markdown(
        name=row.get("name", ""),
        description=row.get("description", ""),
        body=row.get("body", ""),
        kind=row.get("kind", DEFAULT_SKILL_KIND),
        handler=row.get("handler", DEFAULT_SKILL_HANDLER),
        allowed_effects=row.get("allowed_effects", list(DEFAULT_SKILL_EFFECTS)),
        triggers=row.get("triggers", []),
        support_files=support_files,
        tools=row.get("tools", []),
        security=row.get("security", "prompt-only learned skill; no script execution"),
        source=row.get("source", "manual"),
        created_at=row.get("created_at", ""),
        updated_at=_now(),
    )
    writer(path, text)
    return load_skill(root, name)


def write_skill_support_file(
    root: pathlib.Path,
    name: str,
    *,
    file_path: str,
    file_content: str,
    writer,
) -> dict:
    if "\x00" in str(file_content):
        raise SystemExit("support file content must be text, not NUL-delimited data")
    encoded_size = len(str(file_content).encode("utf-8"))
    if encoded_size > MAX_SKILL_SUPPORT_FILE:
        raise SystemExit(
            f"support file is too large ({encoded_size} bytes, max {MAX_SKILL_SUPPORT_FILE})"
        )
    row, target, rel = _resolve_support_file(root, name, file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.parent.chmod(0o700)
    writer(target, str(file_content))
    updated = _update_skill_support_files(root, row.get("name", name), add=rel, writer=writer)
    return {
        "schema": SKILL_MANAGE_SCHEMA,
        "action": "write_file",
        "skill": updated,
        "path": str(target),
        "support_file": rel,
        "message": f"support file written: {rel}",
    }


def remove_skill_support_file(root: pathlib.Path, name: str, *, file_path: str, writer) -> dict:
    row, target, rel = _resolve_support_file(root, name, file_path)
    if not target.exists():
        raise SystemExit(f"support file not found: {rel}")
    if target.is_dir():
        raise SystemExit(f"support file path is a directory: {rel}")
    target.unlink()
    updated = _update_skill_support_files(root, row.get("name", name), remove=rel, writer=writer)
    return {
        "schema": SKILL_MANAGE_SCHEMA,
        "action": "remove_file",
        "skill": updated,
        "path": str(target),
        "support_file": rel,
        "message": f"support file removed: {rel}",
    }


def patch_skill_file(
    root: pathlib.Path,
    name: str,
    *,
    old_string: str,
    new_string: str,
    file_path: str = "SKILL.md",
    replace_all: bool = False,
    writer,
) -> dict:
    if not old_string:
        raise SystemExit("patch old_string is empty")
    if new_string is None:
        raise SystemExit("patch new_string is required")
    row, skill_path, _skill_dir = _load_user_skill_for_manage(root, name)
    if not file_path or file_path == "SKILL.md":
        target = skill_path
        rel = "SKILL.md"
    else:
        _row, target, rel = _resolve_support_file(root, name, file_path)
        if not target.exists():
            raise SystemExit(f"support file not found: {rel}")
    original = target.read_text(encoding="utf-8")
    count = original.count(old_string)
    if count == 0:
        raise SystemExit("patch old_string was not found")
    if count > 1 and not replace_all:
        raise SystemExit("patch old_string matched more than once; set replace_all for intentional bulk replacement")
    updated_text = original.replace(old_string, str(new_string), -1 if replace_all else 1)
    if target == skill_path:
        parsed = parse_skill_markdown(updated_text, path=skill_path)
        if parsed.get("slug") != row.get("slug"):
            raise SystemExit("patch cannot rename or retarget a skill")
        if len(parsed.get("body", "")) > MAX_SKILL_BODY:
            raise SystemExit(f"skill body is too large ({len(parsed.get('body', ''))} chars, max {MAX_SKILL_BODY})")
    elif len(updated_text.encode("utf-8")) > MAX_SKILL_SUPPORT_FILE:
        raise SystemExit(f"support file is too large after patch (max {MAX_SKILL_SUPPORT_FILE} bytes)")
    writer(target, updated_text)
    return {
        "schema": SKILL_MANAGE_SCHEMA,
        "action": "patch",
        "skill": load_skill(root, name),
        "path": str(target),
        "support_file": rel,
        "message": f"skill file patched: {rel}",
    }


def manage_skill(
    root: pathlib.Path,
    *,
    action: str,
    name: str = "",
    target_skill: str = "",
    description: str = "",
    body: str = "",
    kind: str = DEFAULT_SKILL_KIND,
    handler: str = DEFAULT_SKILL_HANDLER,
    allowed_effects: list[str] | None = None,
    triggers: list[str] | None = None,
    support_files: list[str] | None = None,
    tools: list[str] | None = None,
    security: str = "prompt-only learned skill; no script execution",
    source: str = "skill-manage",
    replace: bool = False,
    file_path: str = "",
    file_content: str = "",
    old_string: str = "",
    new_string: str = "",
    replace_all: bool = False,
    writer,
) -> dict:
    action = normalize_skill_manage_action(action)
    if action == "create":
        skill = save_skill(
            root,
            name=name,
            description=description,
            body=body,
            kind=kind,
            handler=handler,
            allowed_effects=allowed_effects,
            triggers=triggers,
            support_files=support_files,
            tools=tools,
            security=security,
            source=source,
            replace=replace,
            writer=writer,
        )
        return {
            "schema": SKILL_MANAGE_SCHEMA,
            "action": action,
            "skill": skill,
            "path": skill.get("path", ""),
            "message": f"skill created: {skill.get('slug', '')}",
        }
    skill_name = target_skill or name
    if not skill_name:
        raise SystemExit(f"{action} requires target_skill")
    if action == "write_file":
        return write_skill_support_file(root, skill_name, file_path=file_path, file_content=file_content, writer=writer)
    if action == "remove_file":
        return remove_skill_support_file(root, skill_name, file_path=file_path, writer=writer)
    if action == "patch":
        return patch_skill_file(
            root,
            skill_name,
            old_string=old_string,
            new_string=new_string,
            file_path=file_path or "SKILL.md",
            replace_all=replace_all,
            writer=writer,
        )
    raise SystemExit(f"unsupported skill_manage action: {action}")


def upgrade_skill_files(root: pathlib.Path, *, writer) -> dict:
    report = {
        "schema": "motoko-skill-upgrade-report-v1",
        "checked": 0,
        "upgraded": 0,
        "errors": [],
        "paths": [],
    }
    for path in iter_skill_files(root):
        report["checked"] += 1
        try:
            original = path.read_text(encoding="utf-8")
            row = parse_skill_markdown(original, path=path)
            canonical = format_skill_markdown(
                name=row.get("name", ""),
                description=row.get("description", ""),
                body=row.get("body", ""),
                kind=row.get("kind", DEFAULT_SKILL_KIND),
                handler=row.get("handler", DEFAULT_SKILL_HANDLER),
                allowed_effects=row.get("allowed_effects", list(DEFAULT_SKILL_EFFECTS)),
                triggers=row.get("triggers", []),
                support_files=row.get("support_files", []),
                tools=row.get("tools", []),
                security=row.get("security", "prompt-only learned skill; no script execution"),
                source=row.get("source", "manual"),
                created_at=row.get("created_at", ""),
                updated_at=row.get("updated_at", ""),
            )
            if canonical != original:
                writer(path, canonical)
                report["upgraded"] += 1
                report["paths"].append(str(path))
        except (OSError, SystemExit) as exc:
            report["errors"].append(f"{path}: {exc}")
    return report


def delete_skill(root: pathlib.Path, name: str) -> dict:
    row = load_skill(root, name)
    if row.get("builtin"):
        raise SystemExit(f"cannot delete built-in skill: {row.get('slug', name)}")
    path = pathlib.Path(row.get("path", ""))
    try:
        path.unlink()
        if path.parent != root and not any(path.parent.iterdir()):
            path.parent.rmdir()
    except OSError as exc:
        raise SystemExit(f"cannot delete skill {name}: {exc}") from exc
    return row


def skill_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_.-]{3,}", str(text or "").lower()))


def rank_skills(
    root: pathlib.Path,
    query: str,
    *,
    limit: int = DEFAULT_SKILL_CONTEXT_LIMIT,
    lifecycle_state: dict | None = None,
) -> list[dict]:
    return rank_skill_rows(list_skills(root), query, limit=limit, lifecycle_state=lifecycle_state)


def rank_skill_rows(
    rows: list[dict],
    query: str,
    *,
    limit: int = DEFAULT_SKILL_CONTEXT_LIMIT,
    lifecycle_state: dict | None = None,
) -> list[dict]:
    query_terms = skill_tokens(query)
    if not query_terms:
        return []
    ranked = []
    lifecycle_state = normalize_skill_lifecycle_state(lifecycle_state or {})
    for row in apply_skill_lifecycle(list(rows), lifecycle_state):
        if row.get("lifecycle_state") == SKILL_STATE_ARCHIVED:
            continue
        triggers = "\n".join(str(item) for item in row.get("triggers", []) or [])
        haystack = "\n".join([row.get("name", ""), row.get("description", ""), triggers, row.get("body", "")[:3000]])
        terms = skill_tokens(haystack)
        overlap = query_terms & terms
        if not overlap:
            continue
        score = len(overlap) * 10
        if any(term in skill_tokens(row.get("name", "")) for term in query_terms):
            score += 20
        item = dict(row)
        item["score"] = score
        item["matched_terms"] = sorted(overlap)
        ranked.append(item)
    ranked.sort(key=lambda row: (row.get("score", 0), row.get("updated_at", "")), reverse=True)
    return ranked[: max(0, int(limit or 0))]


def render_skills_with_sources(
    root: pathlib.Path,
    query: str,
    *,
    limit: int = DEFAULT_SKILL_CONTEXT_LIMIT,
    max_chars: int = DEFAULT_SKILL_CONTEXT_CHARS,
    lifecycle_state: dict | None = None,
) -> tuple[str, list[dict]]:
    rows = rank_skills(root, query, limit=limit, lifecycle_state=lifecycle_state)
    parts = []
    sources = []
    used = 0
    for row in rows:
        body = str(row.get("body", "")).strip()
        if not body:
            continue
        header = f"Skill: {row.get('name', '')}\nDescription: {row.get('description', '')}\n"
        remaining = max_chars - used - len(header)
        if remaining <= 0:
            break
        excerpt = body[:remaining].strip()
        if not excerpt:
            continue
        parts.append(header + excerpt)
        used += len(header) + len(excerpt) + 2
        support_sources = []
        for support in rank_skill_support_files(root, row, query, limit=2):
            support_header = f"\nSupport file: {support.get('support_file', '')}\n"
            remaining = max_chars - used - len(support_header)
            if remaining <= 0:
                break
            support_excerpt = support.get("content", "")[:remaining].strip()
            if not support_excerpt:
                continue
            parts.append(support_header.strip() + "\n" + support_excerpt)
            used += len(support_header) + len(support_excerpt) + 2
            support_sources.append(
                {
                    "kind": "skill-support",
                    "name": row.get("name", ""),
                    "description": row.get("description", ""),
                    "skill_kind": row.get("kind", DEFAULT_SKILL_KIND),
                    "handler": row.get("handler", DEFAULT_SKILL_HANDLER),
                    "allowed_effects": row.get("allowed_effects", [])[:8],
                    "path": support.get("path", ""),
                    "support_file": support.get("support_file", ""),
                    "score": support.get("score", 0),
                    "matched_terms": support.get("matched_terms", [])[:12],
                    "updated_at": support.get("updated_at", ""),
                    "lifecycle_state": row.get("lifecycle_state", SKILL_STATE_ACTIVE),
                }
            )
        sources.append(
            {
                "kind": "skill",
                "name": row.get("name", ""),
                "description": row.get("description", ""),
                "skill_kind": row.get("kind", DEFAULT_SKILL_KIND),
                "handler": row.get("handler", DEFAULT_SKILL_HANDLER),
                "allowed_effects": row.get("allowed_effects", [])[:8],
                "path": row.get("path", ""),
                "score": row.get("score", 0),
                "matched_terms": row.get("matched_terms", [])[:12],
                "updated_at": row.get("updated_at", ""),
                "lifecycle_state": row.get("lifecycle_state", SKILL_STATE_ACTIVE),
                "pinned": bool(row.get("pinned")),
                "selected_count": int(row.get("selected_count", 0) or 0),
                "last_selected_at": row.get("last_selected_at", ""),
            }
        )
        sources.extend(support_sources)
    return "\n\n".join(parts), sources


def rank_skill_support_files(root: pathlib.Path, skill: dict, query: str, *, limit: int = 2) -> list[dict]:
    query_terms = skill_tokens(query)
    if not query_terms or skill.get("builtin"):
        return []
    ranked = []
    for support in list_skill_support_files(root, skill.get("name") or skill.get("slug", "")):
        if not support.get("exists"):
            continue
        try:
            row = read_skill_support_file(
                root,
                skill.get("name") or skill.get("slug", ""),
                support.get("support_file", ""),
                max_chars=8000,
            )
        except (OSError, SystemExit):
            continue
        normalized_path = row.get("support_file", "").replace("/", " ").replace(".", " ").replace("-", " ")
        haystack = "\n".join([row.get("support_file", ""), normalized_path, row.get("content", "")])
        terms = skill_tokens(haystack)
        overlap = query_terms & terms
        if not overlap:
            continue
        item = dict(row)
        item["score"] = len(overlap) * 10
        if any(term in skill_tokens(row.get("support_file", "")) for term in query_terms):
            item["score"] += 20
        item["matched_terms"] = sorted(overlap)
        ranked.append(item)
    ranked.sort(key=lambda row: (row.get("score", 0), row.get("updated_at", "")), reverse=True)
    return ranked[: max(0, int(limit or 0))]


def format_skills_list(rows: list[dict], *, lifecycle_state: dict | None = None) -> str:
    if not rows:
        return "No Motoko skills yet."
    rows = apply_skill_lifecycle(rows, lifecycle_state or {})
    lines = [f"Motoko skills: {len(rows)}"]
    for row in rows:
        badges = []
        if row.get("lifecycle_state") == SKILL_STATE_ARCHIVED:
            badges.append("archived")
        if row.get("pinned"):
            badges.append("pinned")
        selected = int(row.get("selected_count", 0) or 0)
        if selected:
            badges.append(f"selected {selected}x")
        badge_text = f" {{{', '.join(badges)}}}" if badges else ""
        lines.append(
            f"- {row.get('slug', '')}: {row.get('description', '')}"
            f" [{row.get('kind', DEFAULT_SKILL_KIND)} -> {row.get('handler', DEFAULT_SKILL_HANDLER)}]"
            f"{badge_text}"
            + (f" ({row.get('path', '')})" if row.get("path") else "")
        )
    return "\n".join(lines)


def format_skill(row: dict) -> str:
    return "\n".join(
        [
            f"skill: {row.get('name', '')}",
            f"slug: {row.get('slug', '')}",
            f"description: {row.get('description', '')}",
            f"schema: {row.get('schema', '')}",
            f"source schema: {row.get('source_schema', '')}",
            f"kind: {row.get('kind', DEFAULT_SKILL_KIND)}",
            f"handler: {row.get('handler', DEFAULT_SKILL_HANDLER)}",
            "allowed effects: " + ", ".join(row.get("allowed_effects", []) or []),
            "triggers: " + ", ".join(row.get("triggers", []) or []),
            "support files: " + ", ".join(row.get("support_files", []) or []),
            "tools: " + ", ".join(row.get("tools", []) or []),
            f"security: {row.get('security', '')}",
            f"source: {row.get('source', '')}",
            f"created: {row.get('created_at', '')}",
            f"updated: {row.get('updated_at', '')}",
            f"path: {row.get('path', '')}",
            "",
            str(row.get("body", "")).strip(),
        ]
    ).strip()
