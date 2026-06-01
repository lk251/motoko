"""Pure skill-curator decision helpers for Motoko."""

from __future__ import annotations

import datetime as _dt
import hashlib
import re

from motoko_core.skills import SKILL_STATE_ARCHIVED
from motoko_core.text import compact_text


def skill_curator_generic_terms() -> set[str]:
    return {
        "skill",
        "workflow",
        "procedure",
        "response",
        "style",
        "planning",
        "debugging",
        "motoko",
        "project",
        "file",
        "files",
        "with",
        "when",
        "this",
        "that",
        "use",
        "using",
        "context",
    }


def skill_curator_terms(text: str) -> set[str]:
    terms = set(re.findall(r"[a-z0-9_.-]{3,}", str(text or "").lower()))
    return terms - skill_curator_generic_terms()


def matched_skills_for_text(active: list[dict], text: str, *, limit: int = 3) -> list[tuple[dict, list[str]]]:
    terms = skill_curator_terms(text)
    if not terms:
        return []
    matched = []
    for row in active:
        skill_terms = skill_curator_terms(
            " ".join([row.get("slug", ""), row.get("description", ""), row.get("body", "")[:1000]])
        )
        overlap = sorted(terms & skill_terms)
        if overlap:
            matched.append((row, overlap))
    return matched[: max(0, int(limit or 0))]


def skill_curator_feedback_matches(
    active: list[dict],
    feedback_rows: list[dict],
) -> list[tuple[dict, list[tuple[dict, list[str]]]]]:
    matches = []
    for feedback in feedback_rows:
        if feedback.get("rating") == "up":
            continue
        matched = matched_skills_for_text(
            active,
            " ".join([feedback.get("note", ""), feedback.get("user_prompt", "")]),
        )
        if matched:
            matches.append((feedback, matched))
    return matches


def skill_curator_feedback_eval_matches(
    active: list[dict],
    fixtures: list[dict],
) -> list[tuple[dict, list[tuple[dict, list[str]]]]]:
    matches = []
    for fixture in fixtures:
        text = " ".join(
            [
                " ".join(str(item) for item in fixture.get("focus", []) if str(item).strip())
                if isinstance(fixture.get("focus"), list)
                else "",
                str(fixture.get("query", "")),
                str(fixture.get("note", "")),
                str(fixture.get("quality_status", "")),
            ]
        )
        matched = matched_skills_for_text(active, text)
        if matched:
            matches.append((fixture, matched))
    return matches


def skill_support_file_count(row: dict) -> int:
    return len([item for item in row.get("support_files", []) or [] if str(item or "").strip()])


def skill_has_support_file(row: dict, file_path: str) -> bool:
    wanted = str(file_path or "").strip().replace("\\", "/")
    return wanted in {str(item or "").strip().replace("\\", "/") for item in row.get("support_files", []) or []}


def _parse_timestamp(value: str) -> _dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone()


def skill_created_age_days(row: dict, *, now: _dt.datetime | None = None) -> int | None:
    parsed = _parse_timestamp(str(row.get("created_at") or ""))
    if parsed is None:
        return None
    now_dt = now.astimezone() if now is not None else _dt.datetime.now(_dt.timezone.utc).astimezone()
    seconds = max(0, int((now_dt - parsed.astimezone()).total_seconds()))
    return seconds // (24 * 60 * 60)


def stale_unused_skill_rows(
    active: list[dict],
    *,
    min_age_days: int,
    now: _dt.datetime | None = None,
) -> list[dict]:
    rows = []
    for row in active:
        if row.get("pinned") or row.get("builtin"):
            continue
        if int(row.get("selected_count", 0) or 0) != 0 or int(row.get("patch_count", 0) or 0) != 0:
            continue
        if skill_has_support_file(row, "references/archive-review.md"):
            continue
        age_days = skill_created_age_days(row, now=now)
        if age_days is None or age_days < min_age_days:
            continue
        item = dict(row)
        item["curator_age_days"] = age_days
        rows.append(item)
    rows.sort(key=lambda item: int(item.get("curator_age_days", 0) or 0), reverse=True)
    return rows


def skill_consolidation_groups(active: list[dict]) -> list[tuple[dict, list[tuple[dict, list[str]]]]]:
    groups = []
    for idx, row in enumerate(active):
        row_terms = skill_curator_terms(
            " ".join([row.get("slug", ""), row.get("description", ""), " ".join(row.get("triggers", []) or [])])
        )
        if len(row_terms) < 2:
            continue
        matches = []
        for other in active[idx + 1 :]:
            other_terms = skill_curator_terms(
                " ".join([other.get("slug", ""), other.get("description", ""), " ".join(other.get("triggers", []) or [])])
            )
            overlap = sorted(row_terms & other_terms)
            if len(overlap) >= 2:
                matches.append((other, overlap))
        if matches:
            groups.append((row, matches))
    return groups


def append_patch_suggestion_for_skill(
    row: dict,
    *,
    description: str,
    heading: str,
    bullet: str,
    reason: str,
    signals: list[str],
    suggestion_body_chars: int,
) -> dict | None:
    body = str(row.get("body", "")).strip()
    if not body or len(body) > 2200:
        return None
    if heading in body and bullet in body:
        return None
    addition = f"\n\n{heading}\n- {bullet}"
    if len(body) + len(addition) > suggestion_body_chars:
        return None
    return {
        "action": "patch",
        "name": row.get("slug", ""),
        "target_skill": row.get("slug", ""),
        "description": description,
        "old_string": body,
        "new_string": body + addition,
        "reason": reason,
        "signals": signals,
    }


def support_file_suggestion_for_skill(
    row: dict,
    *,
    description: str,
    file_slug: str,
    content: str,
    reason: str,
    signals: list[str],
    suggestion_body_chars: int,
) -> dict | None:
    file_slug = re.sub(r"[^a-z0-9_.-]+", "-", str(file_slug).strip().lower()).strip(".-")
    if not file_slug:
        return None
    return {
        "action": "write_file",
        "name": f"{row.get('slug', '')}-{file_slug}",
        "target_skill": row.get("slug", ""),
        "description": description,
        "file_path": f"references/{file_slug}.md",
        "file_content": compact_text(content, suggestion_body_chars),
        "reason": reason,
        "signals": signals,
    }


def curator_skill_suggestion_candidates(
    active: list[dict],
    *,
    feedback_matches: list[tuple[dict, list[tuple[dict, list[str]]]]] | None = None,
    feedback_eval_matches: list[tuple[dict, list[tuple[dict, list[str]]]]] | None = None,
    limit: int,
    suggestion_body_chars: int,
    stale_unused_days: int,
) -> list[dict]:
    candidates = []
    limit = max(0, int(limit or 0))
    for feedback, matched in feedback_matches or []:
        if not matched:
            continue
        row, overlap = matched[0]
        feedback_id = str(feedback.get("id", ""))[:80]
        bullet = (
            f"Feedback {feedback_id or '(unidentified)'} ({feedback.get('rating', '')}) matched "
            f"{', '.join(overlap[:5])}. Inspect the private feedback row before accepting this patch."
        )
        candidate = append_patch_suggestion_for_skill(
            row,
            description=f"Patch {row.get('slug', '')} with recent feedback signal.",
            heading="Feedback-derived review notes:",
            bullet=bullet,
            reason="A recent non-positive feedback row matched this skill; patching the existing skill is safer than creating a duplicate.",
            signals=[f"feedback:{feedback.get('rating', '')}", f"feedback_id:{feedback_id}", "curator-feedback-match"],
            suggestion_body_chars=suggestion_body_chars,
        )
        if candidate is None:
            content = "\n".join(
                [
                    f"# Feedback signal for {row.get('slug', '')}",
                    "",
                    f"- feedback: {feedback_id}",
                    f"- rating: {feedback.get('rating', '')}",
                    f"- matched terms: {', '.join(overlap[:8])}",
                    "",
                    "Use this as content-safe review material before inspecting the private feedback row and patching the skill.",
                ]
            )
            candidate = support_file_suggestion_for_skill(
                row,
                description=f"Record recent feedback signal for {row.get('slug', '')}.",
                file_slug=f"feedback-{feedback_id or hashlib.sha256('|'.join(overlap).encode('utf-8')).hexdigest()[:8]}",
                content=content,
                reason="The skill body is too large for a safe exact patch, so the curator suggests a support file instead.",
                signals=[f"feedback:{feedback.get('rating', '')}", f"feedback_id:{feedback_id}", "curator-feedback-match"],
                suggestion_body_chars=suggestion_body_chars,
            )
        if candidate is not None:
            candidates.append(candidate)
        if len(candidates) >= limit:
            return candidates
    for fixture, matched in feedback_eval_matches or []:
        if not matched:
            continue
        row, overlap = matched[0]
        fixture_id = str(fixture.get("id", ""))[:80]
        report_id = str(fixture.get("_feedback_eval_report_id", ""))[:80]
        focus = [
            str(item)
            for item in fixture.get("focus", [])
            if str(item).strip()
        ] if isinstance(fixture.get("focus"), list) else []
        content = "\n".join(
            [
                f"# Feedback eval review for {row.get('slug', '')}",
                "",
                "This content-safe curator note was generated from a saved private feedback-eval fixture.",
                "It does not expose the raw query, note, answer, source paths, or support-file contents.",
                "",
                "Signals:",
                f"- feedback eval report: {report_id or '-'}",
                f"- fixture: {fixture_id or '-'}",
                f"- rating: {fixture.get('rating', '')}",
                f"- quality status: {fixture.get('quality_status', '')}",
                f"- focus: {', '.join(focus[:8]) if focus else '-'}",
                f"- source path count: {int(fixture.get('source_path_count', 0) or 0)}",
                f"- source evidence count: {int(fixture.get('source_evidence_count', 0) or 0)}",
                f"- matched term count: {len(overlap)}",
                "",
                "Review path:",
                "- inspect the private feedback-eval report if you need the raw query or note",
                "- decide whether this is a retrieval, prompt-packing, or skill-procedure problem",
                "- patch the existing skill only after the procedure generalizes",
                "- prefer a regression, retrieval fixture, or support-file note over an automatic behavior change",
            ]
        )
        candidate = support_file_suggestion_for_skill(
            row,
            description=f"Record feedback-eval review signal for {row.get('slug', '')}.",
            file_slug=f"feedback-eval-{fixture_id or hashlib.sha256('|'.join(overlap).encode('utf-8')).hexdigest()[:8]}",
            content=content,
            reason="A saved feedback-eval fixture matched this skill; the curator records review material without mutating skill behavior.",
            signals=[
                f"feedback_eval:{report_id}",
                f"feedback_fixture:{fixture_id}",
                "curator-feedback-eval-match",
            ],
            suggestion_body_chars=suggestion_body_chars,
        )
        if candidate is not None:
            candidates.append(candidate)
        if len(candidates) >= limit:
            return candidates
    for row in active:
        if row.get("pinned") or int(row.get("selected_count", 0) or 0) < 3 or int(row.get("patch_count", 0) or 0) > 0:
            continue
        lifecycle = row.get("lifecycle", {}) if isinstance(row.get("lifecycle"), dict) else {}
        notes = [
            str(item)
            for item in lifecycle.get("notes", [])[-5:]
            if " selected:" in str(item)
        ]
        if not notes:
            continue
        bullet = (
            f"This skill has been selected {row.get('selected_count', 0)} times. "
            f"Recent selection signals: {'; '.join(compact_text(item, 120) for item in notes[-3:])}"
        )
        candidate = append_patch_suggestion_for_skill(
            row,
            description=f"Patch {row.get('slug', '')} with curator usage signals.",
            heading="Curator usage review notes:",
            bullet=bullet,
            reason="Repeated selection without any patch suggests this skill may need consolidation or clearer trigger guidance.",
            signals=["curator-loaded-skill-signal", f"selected_count:{row.get('selected_count', 0)}"],
            suggestion_body_chars=suggestion_body_chars,
        )
        if candidate is not None:
            candidates.append(candidate)
        if len(candidates) >= limit:
            break
    for row in active:
        if len(candidates) >= limit:
            break
        if row.get("pinned") or skill_support_file_count(row) or len(str(row.get("body", ""))) <= 2500:
            continue
        content = "\n".join(
            [
                f"# Support-file plan for {row.get('slug', '')}",
                "",
                "This content-safe curator note exists to keep SKILL.md short and useful.",
                "",
                f"- skill body chars: {len(str(row.get('body', '')))}",
                "- keep trigger rules and decision boundaries in SKILL.md",
                "- move durable examples, checklists, templates, and long references into support files",
                "- prefer references/ for prose and templates/ for reusable skeletons",
                "- leave scripts/ inert unless a separate tool contract is reviewed and approved",
            ]
        )
        candidate = support_file_suggestion_for_skill(
            row,
            description=f"Create a support-file organization plan for {row.get('slug', '')}.",
            file_slug="support-file-plan",
            content=content,
            reason="The skill body is large and has no support files; a support-file plan helps keep procedural memory maintainable.",
            signals=["curator-support-file-opportunity", f"body_chars:{len(str(row.get('body', '')))}"],
            suggestion_body_chars=suggestion_body_chars,
        )
        if candidate is not None:
            candidates.append(candidate)
    for row, matches in skill_consolidation_groups(active):
        if len(candidates) >= limit:
            break
        content = "\n".join(
            [
                f"# Consolidation review for {row.get('slug', '')}",
                "",
                "This content-safe curator note lists overlapping learned skills. It does not archive or patch anything by itself.",
                "",
                "Candidate related skills:",
            ]
            + [
                f"- {other.get('slug', '')}: overlap terms {', '.join(overlap[:8])}"
                for other, overlap in matches[:8]
            ]
            + [
                "",
                "Review path:",
                "- decide whether one skill should become the umbrella procedure",
                "- move durable examples or edge cases into support files",
                "- patch triggers/descriptions before archiving any duplicate",
                "- archive only after the useful procedure has been preserved elsewhere",
            ]
        )
        candidate = support_file_suggestion_for_skill(
            row,
            description=f"Create a consolidation review note for {row.get('slug', '')}.",
            file_slug="consolidation-review",
            content=content,
            reason="Several active learned skills share trigger terms; reviewing consolidation reduces duplicate narrow skills.",
            signals=["curator-consolidation-candidate", f"match_count:{len(matches)}"],
            suggestion_body_chars=suggestion_body_chars,
        )
        if candidate is not None:
            candidates.append(candidate)
    for row in stale_unused_skill_rows(active, min_age_days=stale_unused_days):
        if len(candidates) >= limit:
            break
        age_days = int(row.get("curator_age_days", 0) or 0)
        content = "\n".join(
            [
                f"# Archive review for {row.get('slug', '')}",
                "",
                "This content-safe curator note does not archive anything by itself.",
                "",
                "Signals:",
                f"- selected count: {int(row.get('selected_count', 0) or 0)}",
                f"- patch count: {int(row.get('patch_count', 0) or 0)}",
                f"- age days: {age_days}",
                "- pinned: false",
                "",
                "Review path:",
                "- inspect the skill body and support files",
                "- preserve any useful procedure in an umbrella skill or support file",
                f"- only then archive with `motoko skill archive {row.get('slug', '')} --yes` if it is obsolete",
                "- do nothing if the skill is still intentionally dormant",
            ]
        )
        candidate = support_file_suggestion_for_skill(
            row,
            description=f"Create an archive review note for stale unused skill {row.get('slug', '')}.",
            file_slug="archive-review",
            content=content,
            reason="A learned skill has no recorded selections or patches after the stale threshold; archive review improves library hygiene without mutating it.",
            signals=["curator-stale-unused-skill", f"age_days:{age_days}"],
            suggestion_body_chars=suggestion_body_chars,
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates[:limit]
