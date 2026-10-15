"""Explicit status contract for tool adapters (no raw error text in voice).

Tool adapters may return ToolOutcome(success, value) so guarded MyAI
can distinguish a failed operation from an ordinary data value, even
when no exception was raised. Text callers keep legacy output behavior.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolOutcome:
    success: bool
    value: object = None

    def __post_init__(self):
        if type(self.success) is not bool:
            raise TypeError("tool-outcome-success-must-be-bool")


def classify_guarded_result(value, metadata):
    """Interpret only explicit contracts and opt-in legacy tool adapters."""
    if isinstance(value, ToolOutcome):
        return value.success, value.value
    if isinstance(value, dict) and value.get("success") is False:
        return False, None
    if isinstance(value, str) and isinstance(metadata, dict):
        prefixes = metadata.get("result_failure_prefixes", ())
        if isinstance(prefixes, (tuple, list)):
            for prefix in prefixes[:16]:
                if (
                    isinstance(prefix, str)
                    and prefix.strip()
                    and value.casefold().startswith(prefix.casefold())
                ):
                    return False, None
    return True, value


def summarize_guarded_outcomes(outcomes):
    """Return a bounded honest plan status; never claim rollback."""
    if not isinstance(outcomes, dict) or not outcomes:
        return "not_started"
    states = [
        entry.get("state") for entry in outcomes.values()
        if isinstance(entry, dict)
    ]
    if len(states) != len(outcomes):
        return "unknown"
    if any(state not in ("succeeded", "failed", "blocked") for state in states):
        return "unknown"
    if all(state == "succeeded" for state in states):
        return "completed"
    if "succeeded" in states:
        return "partially_completed"
    if "failed" in states:
        return "failed"
    return "not_started"
