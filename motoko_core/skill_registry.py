"""Allowed skill handlers and effects for Motoko.

The registry is deliberately small. A skill may describe procedures freely, but
only handlers and effects listed here can influence Motoko behavior.
"""

PROMPT_ONLY_HANDLER = "prompt_only"
ORG_TEMPORAL_HANDLER = "builtin:org_temporal_latest_entries"
ORG_STRUCTURAL_HANDLER = "builtin:org_structural_query"

PROMPT_CONTEXT_EFFECT = "prompt_context"
RETRIEVAL_PLAN_EFFECT = "retrieval_plan"
SOURCE_SCOPED_EVIDENCE_EFFECT = "source_scoped_evidence"
STRUCTURED_ORG_EVIDENCE_EFFECT = "structured_org_evidence"

SUPPORTED_SKILL_HANDLERS = {
    PROMPT_ONLY_HANDLER: {
        "kind": "workflow",
        "allowed_effects": [PROMPT_CONTEXT_EFFECT],
        "description": "Prompt-context procedural guidance only.",
    },
    ORG_TEMPORAL_HANDLER: {
        "kind": "retrieval",
        "allowed_effects": [RETRIEVAL_PLAN_EFFECT, SOURCE_SCOPED_EVIDENCE_EFFECT],
        "description": "Deterministic source-scoped latest dated Org retrieval.",
    },
    ORG_STRUCTURAL_HANDLER: {
        "kind": "retrieval",
        "allowed_effects": [RETRIEVAL_PLAN_EFFECT, STRUCTURED_ORG_EVIDENCE_EFFECT],
        "description": "Deterministic Org heading, tag, TODO, priority, and date retrieval.",
    },
}

SUPPORTED_SKILL_EFFECTS = {
    PROMPT_CONTEXT_EFFECT,
    RETRIEVAL_PLAN_EFFECT,
    SOURCE_SCOPED_EVIDENCE_EFFECT,
    STRUCTURED_ORG_EVIDENCE_EFFECT,
}


def parse_string_list(value) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def normalize_skill_handler(value: str | None) -> str:
    handler = str(value or PROMPT_ONLY_HANDLER).strip() or PROMPT_ONLY_HANDLER
    return handler if handler in SUPPORTED_SKILL_HANDLERS else PROMPT_ONLY_HANDLER


def normalize_skill_effects(value, *, handler: str | None = None) -> list[str]:
    normalized_handler = normalize_skill_handler(handler)
    requested = parse_string_list(value)
    if not requested:
        requested = list(SUPPORTED_SKILL_HANDLERS[normalized_handler]["allowed_effects"])
    allowed = set(SUPPORTED_SKILL_HANDLERS[normalized_handler]["allowed_effects"])
    effects = []
    for item in requested:
        if item in SUPPORTED_SKILL_EFFECTS and item in allowed and item not in effects:
            effects.append(item)
    if effects:
        return effects
    return list(SUPPORTED_SKILL_HANDLERS[normalized_handler]["allowed_effects"])


def skill_handler_description(handler: str | None) -> str:
    normalized_handler = normalize_skill_handler(handler)
    return SUPPORTED_SKILL_HANDLERS[normalized_handler]["description"]
