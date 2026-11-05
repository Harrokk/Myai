"""Pure adapter for official Arduino App Lab ASR event streams.

Arduino's ASREvent has .type ("partial_text" | "full_text") and .data,
and transcribe_sentence_stream(timeout=N) returns a context-managed stream.
This module never IMPORTS Arduino SDK, calls transcribe, opens microphones,
loads models, accesses core/tools, or logs words. An authorized future App
owns the stream's creation, microphone lifecycle and timeout.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .boundary import FinalTextOneShotGate, PrivateASRFinal

MAX_SDK_EVENTS = 64
EXPECTED_LANGUAGE = "sv"
EXPECTED_TRANSLATE = False


@dataclass(frozen=True)
class SourceOnlyASRReceipt:
    """Status is safe to log. final_text must remain private in memory."""

    status: str
    events_seen: int
    final_text: PrivateASRFinal | None = field(default=None, repr=False)


def check_official_brick_contract(brick: object) -> bool:
    """Read only known SDK fields; never start or query the ASR brick."""
    try:
        return (
            getattr(brick, "language", None) == EXPECTED_LANGUAGE
            and getattr(brick, "translate", None) is EXPECTED_TRANSLATE
            and callable(getattr(brick, "transcribe_sentence_stream", None))
            and callable(getattr(brick, "cancel", None))
            and callable(getattr(brick, "stop", None))
        )
    except Exception:
        return False


def consume_official_asr_stream(
    stream: object,
    gate: FinalTextOneShotGate,
) -> SourceOnlyASRReceipt:
    """Consume exactly one already-open SDK ASR event stream, fail closed.

    Always exits the passed stream context, including on exception. Only
    full_text is read; partial_text.data is never touched. Only the first
    full_text can be accepted. There is an event count cap, but an actual
    blocking SDK iterator MUST be opened with a finite timeout by the
    future operator-owned App; this helper does not implement wall timeouts.
    """
    if type(gate) is not FinalTextOneShotGate:
        return SourceOnlyASRReceipt("invalid-one-shot-gate", 0)
    seen = 0
    final: PrivateASRFinal | None = None
    status = "no-final"
    try:
        with stream as items:
            for event in items:
                seen += 1
                if seen > MAX_SDK_EVENTS:
                    status = "event-budget-exceeded"
                    break
                kind = getattr(event, "type", None)
                if kind == "partial_text":
                    continue
                if kind != "full_text":
                    status = "unexpected-asr-event"
                    break
                # The first final consumes the one-shot, even if invalid.
                final = gate.consume(kind, getattr(event, "data", None))
                status = "final-ready" if final is not None else "final-rejected"
                break
    except Exception:
        # Never include exceptions, because SDK messages may contain words.
        final = None
        status = "stream-failed"
    finally:
        gate.cancel()
    return SourceOnlyASRReceipt(status, min(seen, MAX_SDK_EVENTS), final)
