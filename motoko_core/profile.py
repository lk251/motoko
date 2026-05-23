"""Profile dossier rendering helpers for Motoko."""

from __future__ import annotations


def render_profile_with_sources_core(profile: dict | None) -> tuple[str, list[dict]]:
    if not profile or not profile.get("text", "").strip():
        return "No profile dossier yet. Run /profile-refresh to build one.", []
    return profile.get("text", ""), [
        {
            "kind": "profile",
            "updated": profile.get("updated", ""),
            "memory_count": len(profile.get("memory_ids", [])),
            "conversation_count": len(profile.get("conversation_ids", [])),
        }
    ]


def format_profile_dossier(profile: dict | None) -> str:
    if not profile:
        return "No profile dossier yet. Run 'motoko profile refresh' or /profile-refresh."
    return "\n".join(
        [
            f"updated: {profile.get('updated', '')}",
            f"memories: {len(profile.get('memory_ids', []))}",
            f"conversations: {len(profile.get('conversation_ids', []))}",
            "",
            str(profile.get("text", "")),
        ]
    )
