"""One-shot orchestration of Arduino's existing ASR Brick and MyAI GenieX text gate.

NO Arduino import; NO auto microphone capture; NO startup side effects.
A *future separately approved* App Lab controller supplies an ASR Brick with
transcribe_stream(duration=5) and stop(), plus explicit human initiation.
Only an already-validated final transcript can reach the isolated local
read-only GenieX client; output never includes private words or model replies.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Callable

from scripts.ventuno_app_lab_readonly_asr_bridge import (
    ArduinoASROneShotGate,
    ReadOnlyASRTurn,
    answer_readonly_geniex,
)

CAPTURE_SECONDS = 5
RELEASE_PAUSE_SECONDS = 1.5


@dataclass(frozen=True)
class OneTurnReport:
    # Reporting intentionally exposes only a closed list of categories.
    status: str
    capture_attempted: bool
    final_accepted: bool
    model_reply_verified: bool  # False can also mean an attempted query failed.


class ArduinoBrickOneTurn:
    """One-use ASR Brick session; prevents second use even on failure.

    This class performs no work on construction. `asr` must be separately
    created and started by an authorized App Lab application, NOT by CI.
    """

    def __init__(self) -> None:
        self._gate = ArduinoASROneShotGate()
        self._run_lock = Lock()

    def run_once(
        self,
        asr: object,
        *,
        explicit_user_action: bool = False,
        local_model_client: object | None = None,
        permit_local_model_query: bool = False,
        release_pause: Callable[[float], None] | None = None,
        private_final_handler: Callable[[str], None] | None = None,
    ) -> OneTurnReport:
        if not self._run_lock.acquire(blocking=False):
            return OneTurnReport("already-active", False, False, False)
        try:
            return self._execute(
                asr,
                explicit_user_action=explicit_user_action,
                local_model_client=local_model_client,
                permit_local_model_query=permit_local_model_query,
                release_pause=release_pause,
                private_final_handler=private_final_handler,
            )
        finally:
            self._run_lock.release()

    def _execute(
        self,
        asr: object,
        *,
        explicit_user_action: bool,
        local_model_client: object | None,
        permit_local_model_query: bool,
        release_pause: Callable[[float], None] | None,
        private_final_handler: Callable[[str], None] | None,
    ) -> OneTurnReport:
        if not self._gate.arm_once(explicit_user_action=explicit_user_action):
            return OneTurnReport("not-authorized-or-used", False, False, False)
        # The permission for a model query is independent of microphone consent.
        wants_model = permit_local_model_query is True
        if wants_model and (
            local_model_client is None
            or release_pause is None
            or not callable(release_pause)
        ):
            self._gate.cancel()
            return OneTurnReport("model-handoff-not-configured", False, False, False)
        captured = False
        turn: ReadOnlyASRTurn | None = None
        error = False
        release_failed = False
        try:
            capture = getattr(asr, "transcribe_stream", None)
            stop = getattr(asr, "stop", None)
            if not callable(capture) or not callable(stop):
                return OneTurnReport("invalid-asr-brick", False, False, False)
            captured = True
            with capture(duration=CAPTURE_SECONDS) as stream:
                for event in stream:
                    # Other event types, including partial_text, never call LLM.
                    kind = getattr(event, "type", None)
                    if kind != "full_text":
                        continue
                    turn = self._gate.consume(kind, getattr(event, "data", None))
                    # First final consumes session even if transcript invalid.
                    break
        except Exception:
            # Never log captured words or a potentially sensitive traceback.
            error = True
        finally:
            if captured:
                try:
                    # Arduino's stop closes its owned microphone; do this
                    # before releasing memory/bandwidth for local GenieX.
                    asr.stop()
                except Exception:
                    release_failed = True
            self._gate.cancel()

        if error:
            return OneTurnReport("asr-failed", captured, False, False)
        if release_failed:
            return OneTurnReport("asr-release-failed", captured, False, False)
        if turn is None:
            return OneTurnReport("no-approved-final", captured, False, False)

        if private_final_handler is not None:
            try:
                private_final_handler(turn.text)
            except Exception:
                return OneTurnReport("private-output-failed", captured, True, False)

        if not wants_model:
            return OneTurnReport("final-ready-no-model-call", captured, True, False)
        try:
            # The 1.5s handoff matches the first-party VENTUNO resource
            # recommendation. A future app supplies a blocking pause.
            release_pause(RELEASE_PAUSE_SECONDS)
            answer_readonly_geniex(
                turn, local_model_client, permit_local_model_query=True,
            )
            # The reply is never stored or reported by this adapter. A
            # future authorized UI/TTS port needs its own safety review.
            return OneTurnReport("local-readonly-answer-completed", captured, True, True)
        except Exception:
            return OneTurnReport("local-answer-blocked", captured, True, False)
