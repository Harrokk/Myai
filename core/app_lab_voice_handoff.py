"""Disabled-by-default, text-only handoff from an operator-run App Lab ASR turn.

This component performs NO hardware I/O, network I/O, file I/O, or logging.
It does not start recording, initialize MyAI, or start the LLM. The caller
must supply an already-created MyAICore compatible object.

A single instance consumes at most one final transcript. Construct a fresh
instance only for a new operator-authorized listening turn. Effectful tool
plans are never approved by this adapter; MyAICore's own voice dispatch
checks still apply. Memory policy is owned by MyAICore, not this adapter.
"""

from __future__ import annotations

import threading
import unicodedata


MAX_TRANSCRIPT_CHARS = 500
MAX_ANSWER_CHARS = 2400


class AppLabFinalTextHandoff:
    """One final-text handoff; no ASR/LLM/TTS instances are created here."""

    def __init__(self, assistant, *, enabled=False):
        if type(enabled) is not bool:
            raise ValueError("enabled must be a boolean")
        self._assistant = assistant
        self._enabled = enabled
        self._consumed = False
        self._lock = threading.Lock()

    def dispatch(self, text, *, session_active=False, asr_released=False,
                 stop_requested=None):
        """Send a private final transcript to MyAICore with no write approvals.

        The caller owns user/physical consent and hardware lifecycle; boolean
        preconditions are cooperative, not independently authenticated. A
        callable stop_requested() is mandatory and checked before/after the
        response, and by MyAICore at tool-dispatch boundaries.
        """
        with self._lock:
            if self._consumed:
                return {"status": "already-consumed"}
            self._consumed = True

        if not self._enabled:
            return {"status": "disabled"}
        if session_active is not True or asr_released is not True:
            return {"status": "not-authorized-or-audio-active"}
        if not callable(stop_requested):
            return {"status": "missing-stop-probe"}
        if self._stopped(stop_requested):
            return {"status": "cancelled"}
        if (not isinstance(text, str) or not text.strip()
                or len(text) > MAX_TRANSCRIPT_CHARS
                or any(unicodedata.category(char) == "Cc" for char in text)):
            return {"status": "invalid-final-text"}
        responder = getattr(self._assistant, "respond_voice", None)
        if not callable(responder):
            return {"status": "voice-responder-unavailable"}

        # The callable itself deliberately refuses all unapproved effectful
        # plans; allowlisted read-only tools still use the core's policy.
        def deny_unapproved_plan(_plan, _tools):
            return False

        deny_unapproved_plan.voice_stop_requested = stop_requested

        try:
            response = responder(text.strip(), plan_verifier=deny_unapproved_plan)
        except Exception:
            # No raw transcript or backend exception details in public status.
            return {"status": "voice-responder-failed"}
        if self._stopped(stop_requested):
            return {"status": "cancelled"}
        if not isinstance(response, dict):
            return {"status": "invalid-voice-response"}
        answer = response.get("answer")
        if not isinstance(answer, str) or len(answer) > MAX_ANSWER_CHARS:
            return {"status": "invalid-voice-response"}
        if not answer.strip():
            return {"status": "empty-answer"}

        review = response.get("manual_reconciliation_required") is True
        blocked = response.get("tool_dispatch_blocked") is True
        state = response.get("tool_execution_status")
        if state not in {
            "not_applicable", "completed", "failed", "partially_completed",
            "unknown", "blocked", "not_run",
        }:
            state = "unknown"
        if state in {"unknown", "partially_completed"}:
            review = True
        return {
            "status": (
                "review-required" if review else
                "tool-dispatch-blocked" if blocked else
                "answer-ready"
            ),
            "answer": answer,
            "tool_execution_status": state,
            "manual_reconciliation_required": review,
        }

    @staticmethod
    def _stopped(probe):
        try:
            return probe() is not False
        except BaseException:
            return True
