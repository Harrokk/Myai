"""Sanitized, no-persistence feedback for explicit memory requests.

This layer never caches a failed raw memory command. A retry requires
the user to repeat their complete request, and normal memory policy
and SQLite deduplication then run again.
"""
import re

from core.memory_policy import contains_sensitive_memory_data


_EXPLICIT_MEMORY_START = re.compile(
    r"^\s*(?:"
    r"kom\s+ihåg(?:\s+att)?|"
    r"lägg\s+på\s+minnet(?:\s+att)?|"
    r"spara\s+detta|spara\s+att|"
    r"remember\s+this|remember\s+that"
    r")(?=\s|[:.!?]|$)",
    re.IGNORECASE,
)

_RETRY = (
    "Minnet sparades inte. Upprepa hela minnesinstruktionen "
    "när långtidsminnet fungerar igen."
)
_UNVERIFIED = (
    "Minnesändringen kan redan vara genomförd, men "
    "revisionsloggen kunde inte bekräfta den. Kontrollera "
    "minnet innan du försöker igen."
)
_REVIEW = (
    "Minnesförslaget väntar på granskning och är inte "
    "godkänt som långtidsminne ännu."
)
_RETRY_REVIEW = (
    "Minnesförslaget kunde inte köas för granskning. "
    "Upprepa hela instruktionen senare."
)


def explicit_memory_request(message):
    return bool(
        isinstance(message, str)
        and _EXPLICIT_MEMORY_START.match(message.casefold())
    )


def memory_write_feedback(message, decision, lookup_status):
    """Return only fixed public status strings; never raw content/errors."""
    if not explicit_memory_request(message):
        return {"status": "not_requested", "message": ""}

    # The database may be offline so no memory policy assessment ran.
    # Do not encourage the user to repeat passwords or other secrets.
    if contains_sensitive_memory_data(message):
        return {
            "status": "not_saved_sensitive",
            "message": "Den informationen sparades inte av integritetsskäl.",
        }

    if lookup_status == "unavailable":
        return {"status": "retry_required", "message": _RETRY}

    if not isinstance(decision, dict):
        return {"status": "unverified", "message": _UNVERIFIED}

    if decision.get("audit_result_status") == "unverified":
        return {"status": "unverified", "message": _UNVERIFIED}

    if decision.get("saved") is True:
        return {"status": "saved", "message": ""}

    if decision.get("lifecycle_action") == "duplicate":
        return {"status": "already_present", "message": ""}

    if decision.get("review_queued") is True:
        return {"status": "pending_review", "message": _REVIEW}

    if decision.get("action") == "review" and not decision.get("sensitive"):
        return {"status": "retry_required", "message": _RETRY_REVIEW}

    if decision.get("sensitive") is True:
        return {
            "status": "not_saved_sensitive",
            "message": "Den informationen sparades inte av integritetsskäl.",
        }

    if decision.get("lifecycle_action") == "audit_blocked":
        return {"status": "retry_required", "message": _RETRY}

    if decision.get("lifecycle_action") == "failed":
        return {"status": "retry_required", "message": _RETRY}

    if decision.get("action") == "save" and not decision.get("saved"):
        return {
            "status": "not_saved",
            "message": "Minnet sparades inte. Kontrollera inställningarna "
                       "och upprepa hela instruktionen om lagring ska göras.",
        }

    return {"status": "not_saved", "message": "Inget minne sparades."}
