"""Evaluation helper logic for Motoko."""

from __future__ import annotations

import json
import re
import textwrap


def worker_eval_instruction(fixture: dict) -> str:
    keys = ", ".join(fixture.get("required_keys", []))
    return textwrap.dedent(
        f"""
        You are a Motoko local indexing worker. Build a source-grounded artifact
        for the role: {fixture.get('role', '')}.

        Return only one valid JSON object. Do not use Markdown fences. Do not
        include hidden reasoning or <think> text. Preserve exact names, dates,
        TODO states, obligations, project names, and file paths from the source.
        Do not invent people, dates, statuses, payments, or completed work.

        Required top-level keys: {keys}

        Label: {fixture.get('label', '')}

        Source:
        {fixture.get('text', '')}
        """
    ).strip()


def worker_eval_messages(fixture: dict) -> list[dict]:
    return [
        {
            "role": "system",
            "content": "Create strict JSON indexing artifacts. Be faithful, compact, and source-grounded.",
        },
        {"role": "user", "content": worker_eval_instruction(fixture)},
    ]


def extract_json_object(text: str) -> tuple[dict | None, str]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    candidates = [raw]
    start = raw.find("{")
    end = raw.rfind("}")
    if 0 <= start < end:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed, ""
    return None, "response is not a valid JSON object"


def fact_matches(text: str, fact: dict) -> bool:
    lowered = text.lower()
    for option in fact.get("any", []) or []:
        needle = str(option).strip().lower()
        if needle and needle in lowered:
            return True
    return False


def score_worker_eval_output(fixture: dict, output: str, *, error: str = "") -> dict:
    parsed, json_error = extract_json_object(output) if output else (None, "empty response")
    output_for_scoring = output
    if parsed is not None:
        output_for_scoring = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
    required = fixture.get("required_facts", []) or []
    missing = [fact.get("name", "") for fact in required if not fact_matches(output_for_scoring, fact)]
    forbidden = [fact.get("name", "") for fact in fixture.get("forbidden_facts", []) or [] if fact_matches(output_for_scoring, fact)]
    required_keys = fixture.get("required_keys", []) or []
    missing_keys = [key for key in required_keys if not isinstance(parsed, dict) or key not in parsed]
    fact_ratio = 1.0 if not required else (len(required) - len(missing)) / len(required)
    max_chars = int(fixture.get("max_output_chars", 4000) or 4000)
    length_ok = len(output) <= max_chars
    no_think = "<think" not in output.lower()
    json_valid = parsed is not None
    status = (
        "pass"
        if not error
        and json_valid
        and not missing_keys
        and fact_ratio >= float(fixture.get("min_fact_ratio", 0.8))
        and not forbidden
        and length_ok
        and no_think
        else "fail"
    )
    score = 0.0
    score += 55.0 * fact_ratio
    score += 15.0 if json_valid else 0.0
    score += 10.0 if not missing_keys else max(0.0, 10.0 * (1.0 - len(missing_keys) / max(1, len(required_keys))))
    score += 10.0 if not forbidden else 0.0
    score += 5.0 if length_ok else 0.0
    score += 5.0 if no_think else 0.0
    return {
        "status": status,
        "score": round(score, 1),
        "json_valid": json_valid,
        "json_error": json_error,
        "required_fact_count": len(required),
        "matched_fact_count": len(required) - len(missing),
        "missing_facts": missing,
        "forbidden_hits": forbidden,
        "required_key_count": len(required_keys),
        "missing_keys": missing_keys,
        "length_ok": length_ok,
        "no_think": no_think,
        "error": error,
    }
