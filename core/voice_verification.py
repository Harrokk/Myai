"""Pure, offline verification of independently attributed STT transcripts.

No microphone, subprocess, network, disk, or tool execution occurs here.
Model identities MUST be supplied by a trusted factory registry, never by
the text/model response being verified. Unknown identities fail closed.
"""
import re
import unicodedata

from core.voice_risk_policy import TIERS


_REQUIRED = {"low": 1, "medium": 2, "critical": 3}
# Explicit lack of transcription is an abstention, not a consenting vote.
_MAX_TEXT = 4096


def _canonical(text):
    if not isinstance(text, str) or len(text) > _MAX_TEXT:
        return None
    value = unicodedata.normalize("NFKC", text).casefold().strip()
    value = re.sub(r"[^\wåäö-]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def verify_tiered_transcripts(tier, votes, trusted_models):
    """Confirm 1/1 low, 2/2 medium or 2/3 critical without unsafe fallback.

    Each vote has exactly one trusted registry key and a transcript string.
    Different Python objects or two quantizations of the same model family
    do NOT establish independence. Critical disagreement about a meaningful
    phrase is rejected; only a genuine abstention may be a third non-vote.
    """
    failed = lambda reason: {
        "accepted": False, "tier": tier, "support": 0,
        "required_votes": _REQUIRED.get(tier), "reason": reason,
        "text": None,
    }
    if tier not in TIERS:
        return failed("invalid_tier")
    required = _REQUIRED[tier]
    if not isinstance(votes, (list, tuple)) or len(votes) != required:
        return failed("missing_or_extra_votes")
    if not isinstance(trusted_models, dict):
        return failed("missing_model_registry")

    keys = set()
    families = set()
    normalized = []
    for vote in votes:
        if not isinstance(vote, dict):
            return failed("invalid_vote")
        key = vote.get("model_key")
        if not isinstance(key, str) or key in keys:
            return failed("duplicate_or_invalid_model")
        model = trusted_models.get(key)
        if not isinstance(model, dict):
            return failed("unknown_model")
        family = model.get("family")
        revision = model.get("revision")
        # The factory must verify the weights and bind this registry to the
        # concrete provider; a self-declared family in STT output is untrusted.
        if (not isinstance(family, str) or not family.strip()
                or not isinstance(revision, str) or not revision.strip()):
            return failed("unverified_model_identity")
        family = family.strip().casefold()
        if family in families:
            return failed("same_model_family")
        keys.add(key)
        families.add(family)
        item = _canonical(vote.get("text"))
        if item is None:
            return failed("invalid_transcript")
        normalized.append(item)

    usable = [item for item in normalized if item]
    if tier == "low":
        if len(usable) == 1:
            return {
                "accepted": True, "tier": tier, "support": 1,
                "required_votes": 1, "reason": "verified",
                "text": usable[0],
            }
        return failed("empty_transcript")

    if tier == "medium":
        if len(usable) == 2 and usable[0] == usable[1]:
            return {
                "accepted": True, "tier": tier, "support": 2,
                "required_votes": 2, "reason": "verified",
                "text": usable[0],
            }
        return failed("disagreement_or_abstention")

    if len(usable) < 2:
        return failed("insufficient_majority")
    counts = {item: usable.count(item) for item in set(usable)}
    winner = max(counts, key=counts.get)
    if counts[winner] < 2:
        return failed("no_exact_majority")
    # If another recognizer heard a different non-empty instruction, it may
    # differ by negation, a filename, a number or a physical target. Without
    # a provably safe parser we reject it instead of guessing.
    if any(item != winner for item in usable):
        return failed("potentially_material_conflict")
    return {
        "accepted": True, "tier": tier, "support": len(usable),
        "required_votes": 3, "reason": "verified",
        "text": winner,
    }
