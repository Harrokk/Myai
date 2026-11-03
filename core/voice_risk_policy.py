"""Fail-closed risk tiers for the opt-in voice-verification design.

This module performs no I/O and does not authorize tools. The decision is
advisory until it is bound to the dispatch plan by voice_plan_attestation.
Unknown plans and tools must not be silently classified as read-only.
"""

import re

from core.orchestration import SAFE_READ_ONLY_TOOLS


TIERS = ("low", "medium", "critical")
_VOTES = {"low": 1, "medium": 2, "critical": 3}
_RANK = {"low": 0, "medium": 1, "critical": 2, "blocked": 3}

# Terms are only a conservative early signal. A tool's actual effect has
# priority; NLP text matching must NEVER grant execution permission.
_CRITICAL_PHRASES = (
    "radera", "ta bort", "delete", "remove", "formatera",
    "skriv över", "overwrite", "ändra kod", "redigera fil",
    "ändra fil", "skriv kod", "installera", "avinstallera",
    "uninstall", "stäng av", "shutdown", "reboot", "starta om",
    "gpio", "motor", "relä", "relay", "merge", "push",
    "commit", "säkerhetsinställning", "safety", "fabriksåterställ",
)
_MEDIUM_PHRASES = (
    "anslut till", "koppla från", "bluetooth on", "bluetooth off",
    "aktivera bluetooth", "stäng av bluetooth", "ta ett foto",
    "ta en bild", "fotografera", "ändra inställning",
)
_CRITICAL_EFFECTS = frozenset({
    "write", "mutate", "destructive", "execute", "control",
    "physical", "unsafe", "admin",
})
_MEDIUM_EFFECTS = frozenset({"reversible", "connect", "local_capture"})


def _mentions(text, phrase):
    return re.search(
        r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text
    ) is not None


def _tier_for_phrase(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 4096:
        return "blocked"
    text = text.casefold()
    if any(_mentions(text, term) for term in _CRITICAL_PHRASES):
        return "critical"
    if any(_mentions(text, term) for term in _MEDIUM_PHRASES):
        return "medium"
    return "low"


def _tier_for_tool(name, metadata):
    if not isinstance(name, str) or not name or not isinstance(metadata, dict):
        return "blocked"
    safety = metadata.get("safety")
    if not isinstance(safety, dict):
        return "blocked"
    effect = safety.get("effect")
    declared = safety.get("voice_risk_tier")
    confirmation = safety.get("voice_confirmation_required", False)
    if (not isinstance(effect, str) or type(confirmation) is not bool
            or declared not in (None, *TIERS)):
        return "blocked"
    effect = effect.strip().casefold()
    if effect in _CRITICAL_EFFECTS:
        return "critical"
    if effect == "read_only":
        if (name in SAFE_READ_ONLY_TOOLS and confirmation is False
                and declared in (None, "low")):
            return "low"
        # A tool not on the audited read-only allowlist is not low risk,
        # even if its self-reported metadata says read_only.
        return "blocked" if name not in SAFE_READ_ONLY_TOOLS else "critical"
    if effect in _MEDIUM_EFFECTS:
        # Reversible operations require an explicit, reviewed medium tag.
        if declared == "medium":
            return "medium"
        return "critical"
    # Unknown effect has no supported execution path.
    return "blocked"


def classify_voice_tier(transcript, plan, tools):
    """Return the maximum tier of phrase, selected tools and plan validity.

    Call with a freshly previewed plan and trusted tool registry. A blocked
    decision cannot be lowered by another recognizer or LLM answer.
    """
    phrase = _tier_for_phrase(transcript)
    if (not isinstance(plan, dict) or not isinstance(tools, dict)
            or not isinstance(plan.get("steps"), list)
            or len(plan["steps"]) > 16):
        return {
            "tier": "blocked", "required_votes": None,
            "requires_confirmation": True,
            "reason_codes": ("invalid_plan",),
        }

    tier = phrase
    reason_codes = []
    names = set()
    for step in plan["steps"]:
        if not isinstance(step, dict):
            tier = "blocked"
            reason_codes.append("invalid_step")
            continue
        name = step.get("tool")
        if not isinstance(name, str) or not name or name in names:
            tier = "blocked"
            reason_codes.append("invalid_tool_selection")
            continue
        names.add(name)
        step_tier = _tier_for_tool(name, tools.get(name))
        if step_tier == "blocked":
            reason_codes.append("unsupported_tool_or_effect")
        if _RANK[step_tier] > _RANK[tier]:
            tier = step_tier
    if phrase == "blocked":
        reason_codes.append("invalid_transcript")
    if not reason_codes and tier != "low":
        reason_codes.append("extra_verification_required")

    return {
        "tier": tier,
        "required_votes": _VOTES.get(tier),
        "requires_confirmation": tier in ("critical", "blocked"),
        "reason_codes": tuple(dict.fromkeys(reason_codes)),
    }


def tier_at_least(actual, required):
    """Conservative comparison: invalid policy or missing values fail."""
    return (
        actual in TIERS and required in TIERS
        and _RANK[actual] >= _RANK[required]
    )
