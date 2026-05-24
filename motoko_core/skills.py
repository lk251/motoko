"""Realm-local procedural skill helpers for Motoko."""

from __future__ import annotations

import datetime as _dt
import pathlib
import re

from motoko_core.text import compact_text


SKILL_SCHEMA = "motoko-skill-v1"
MAX_SKILL_NAME = 64
MAX_SKILL_DESCRIPTION = 400
MAX_SKILL_BODY = 12000
DEFAULT_SKILL_CONTEXT_LIMIT = 2
DEFAULT_SKILL_CONTEXT_CHARS = 5000


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
    return {
        "schema": frontmatter.get("schema") or SKILL_SCHEMA,
        "name": name,
        "slug": skill_slug(name),
        "description": compact_text(description, MAX_SKILL_DESCRIPTION) if description else "",
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
    return "\n".join(
        [
            "---",
            f"schema: {SKILL_SCHEMA}",
            f"name: {name}",
            f"description: {description}",
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
    rows = []
    for path in iter_skill_files(root):
        try:
            row = parse_skill_markdown(path.read_text(encoding="utf-8"), path=path)
        except OSError:
            continue
        if row.get("name"):
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
    source: str = "manual",
    replace: bool = False,
    writer,
) -> dict:
    path = skill_markdown_path(root, name)
    if path.exists() and not replace:
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
        source=source,
        created_at=created_at,
    )
    writer(path, text)
    return load_skill(root, name)


def delete_skill(root: pathlib.Path, name: str) -> dict:
    row = load_skill(root, name)
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
            + (f" ({row.get('path', '')})" if row.get("path") else "")
        )
    return "\n".join(lines)


def format_skill(row: dict) -> str:
    return "\n".join(
        [
            f"skill: {row.get('name', '')}",
            f"slug: {row.get('slug', '')}",
            f"description: {row.get('description', '')}",
            f"source: {row.get('source', '')}",
            f"created: {row.get('created_at', '')}",
            f"updated: {row.get('updated_at', '')}",
            f"path: {row.get('path', '')}",
            "",
            str(row.get("body", "")).strip(),
        ]
    ).strip()
