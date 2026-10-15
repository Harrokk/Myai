"""Bounded process-local quarantine for uncertain voice side effects.

No arguments, transcript, paths, signatures, or raw outcomes are retained.
This is deliberately NOT an exactly-once or crash-durable journal.
"""
from core.orchestration import SAFE_READ_ONLY_TOOLS
from core.tool_outcome import summarize_guarded_outcomes


def known_voice_read_only(name, tool):
    """Same conservative safe-read classification as voice dispatch."""
    if name not in SAFE_READ_ONLY_TOOLS or not isinstance(tool, dict):
        return False
    safety = tool.get("safety", {})
    if not isinstance(safety, dict):
        return False
    effect = safety.get("effect", "read_only")
    return (
        isinstance(effect, str)
        and effect.strip().lower() == "read_only"
        and safety.get("voice_confirmation_required", False) is False
    )


class VoiceRetryQuarantine:
    """Once uncertain effects occur, deny further effectful voice calls.

    This can be cleared only by creating a fresh MyAICore instance after
    external verification; stop/start of a voice session does not clear it.
    """

    def __init__(self):
        self._review_required = False

    @property
    def review_required(self):
        return self._review_required

    def permits(self, name, tool):
        return not self._review_required or known_voice_read_only(name, tool)

    def observe(self, names, tools, outcomes, *, stopped=False):
        """Latch only if an effectful tool was actually attempted.

        A failure, unknown outcome, or interruption after successful work
        needs manual inspection. A completely blocked batch does not.
        """
        if not isinstance(outcomes, dict) or not isinstance(tools, dict):
            return
        if (not stopped
                and summarize_guarded_outcomes(outcomes)
                not in {"failed", "unknown", "partially_completed"}):
            return
        for name in names:
            item = outcomes.get(name)
            if (isinstance(item, dict)
                    and item.get("attempted") is True
                    and not known_voice_read_only(name, tools.get(name))):
                self._review_required = True
                return
