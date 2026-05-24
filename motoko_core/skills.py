"""Realm-local procedural skill helpers for Motoko."""

from __future__ import annotations

import datetime as _dt
import pathlib
import re

from motoko_core.skill_registry import (
    ORG_TEMPORAL_HANDLER,
    PROMPT_CONTEXT_EFFECT,
    PROMPT_ONLY_HANDLER,
    RETRIEVAL_PLAN_EFFECT,
    SOURCE_SCOPED_EVIDENCE_EFFECT,
    normalize_skill_effects,
    normalize_skill_handler,
)
from motoko_core.text import compact_text


SKILL_SCHEMA = "motoko-skill-v2"
LEGACY_SKILL_SCHEMA = "motoko-skill-v1"
SKILL_MANAGE_SCHEMA = "motoko-skill-manage-v1"
SKILL_MANAGE_ACTIONS = {"create", "patch", "write_file", "remove_file"}
MAX_SKILL_NAME = 64
MAX_SKILL_DESCRIPTION = 400
MAX_SKILL_BODY = 12000
MAX_SKILL_SUPPORT_FILE = 100000
DEFAULT_SKILL_CONTEXT_LIMIT = 2
DEFAULT_SKILL_CONTEXT_CHARS = 5000
DEFAULT_SKILL_KIND = "workflow"
DEFAULT_SKILL_HANDLER = PROMPT_ONLY_HANDLER
DEFAULT_SKILL_EFFECTS = [PROMPT_CONTEXT_EFFECT]
ORG_TEMPORAL_SKILL = "org-temporal-retrieval"
ALLOWED_SKILL_SUPPORT_DIRS = {"references", "templates", "scripts"}

BUILTIN_SKILLS = [
    {
        "schema": SKILL_SCHEMA,
        "name": ORG_TEMPORAL_SKILL,
        "slug": ORG_TEMPORAL_SKILL,
        "description": "Source-scoped retrieval for latest dated Org entries",
        "version": "2",
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
    }
]


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def skill_slug(value: str) -> str:
    slug = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    slug = re.sub(r"[^a-z0-9.-]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip(".-")
    return slug[:MAX_SKILL_NAME].strip(".-")


def skill_directory(root: pathlib.Path, name: str) -> pathlib.Path:
    slug = skill_slug(name)
    if not slug:
        raise SystemExit("skill name is empty")
    return root / slug


def skill_markdown_path(root: pathlib.Path, name: str) -> pathlib.Path:
    return skill_directory(root, name) / "SKILL.md"


def parse_skill_markdown(text: str, *, path: pathlib.Path | None = None) -> dict:
    frontmatter: dict[str, str] = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end >= 0:
            raw_frontmatter = text[4:end]
            body = text[end + 5 :]
            for line in raw_frontmatter.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                frontmatter[key.strip()] = value.strip().strip("'\"")
    name = frontmatter.get("name") or (path.parent.name if path else "")
    description = frontmatter.get("description", "")
    if not description:
        for line in body.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                description = stripped
                break
    source_schema = frontmatter.get("schema") or LEGACY_SKILL_SCHEMA
    kind = frontmatter.get("kind") or DEFAULT_SKILL_KIND
    handler = normalize_skill_handler(frontmatter.get("handler"))
    allowed_effects = normalize_skill_effects(frontmatter.get("allowed_effects"), handler=handler)
    triggers = [
        item.strip()
        for item in (frontmatter.get("triggers") or "").split(",")
        if item.strip()
    ]
    support_files = [
        item.strip()
        for item in (frontmatter.get("support_files") or "").split(",")
        if item.strip()
    ]
    return {
        "schema": SKILL_SCHEMA,
        "source_schema": source_schema,
        "name": name,
        "slug": skill_slug(name),
        "description": compact_text(description, MAX_SKILL_DESCRIPTION) if description else "",
        "version": frontmatter.get("version") or ("1" if source_schema == LEGACY_SKILL_SCHEMA else "2"),
        "kind": kind,
        "triggers": triggers,
        "handler": handler,
        "allowed_effects": allowed_effects,
        "support_files": support_files,
        "security": frontmatter.get("security") or "prompt-only learned skill; no script execution",
        "can_upgrade_deterministically": source_schema != SKILL_SCHEMA,
        "created_at": frontmatter.get("created_at", ""),
        "updated_at": frontmatter.get("updated_at", ""),
        "source": frontmatter.get("source", ""),
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
    return "\n".join(
        [
            "---",
            f"schema: {SKILL_SCHEMA}",
            "version: 2",
            f"name: {name}",
            f"description: {description}",
            f"kind: {kind or DEFAULT_SKILL_KIND}",
            f"handler: {handler or DEFAULT_SKILL_HANDLER}",
            f"allowed_effects: {', '.join(allowed_effects)}",
            f"triggers: {', '.join(triggers)}",
            f"support_files: {', '.join(support_files)}",
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


def rank_skills(root: pathlib.Path, query: str, *, limit: int = DEFAULT_SKILL_CONTEXT_LIMIT) -> list[dict]:
    query_terms = skill_tokens(query)
    if not query_terms:
        return []
    ranked = []
    for row in list_skills(root):
        haystack = "\n".join([row.get("name", ""), row.get("description", ""), row.get("body", "")[:3000]])
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
) -> tuple[str, list[dict]]:
    rows = rank_skills(root, query, limit=limit)
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
            }
        )
    return "\n\n".join(parts), sources


def format_skills_list(rows: list[dict]) -> str:
    if not rows:
        return "No Motoko skills yet."
    lines = [f"Motoko skills: {len(rows)}"]
    for row in rows:
        lines.append(
            f"- {row.get('slug', '')}: {row.get('description', '')}"
            f" [{row.get('kind', DEFAULT_SKILL_KIND)} -> {row.get('handler', DEFAULT_SKILL_HANDLER)}]"
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
            f"security: {row.get('security', '')}",
            f"source: {row.get('source', '')}",
            f"created: {row.get('created_at', '')}",
            f"updated: {row.get('updated_at', '')}",
            f"path: {row.get('path', '')}",
            "",
            str(row.get("body", "")).strip(),
        ]
    ).strip()
