"""Synthetic MyAI VoicePipeline -> real eSpeak WAV bridge; NO audio I/O.

Exercises the actual VoicePipeline._respond_and_speak() interface with
strictly fixed synthetic STT input and assistant response. The passed renderer
may synthesize to an in-memory WAV but MUST NOT open a speaker/microphone.
Never uses a live LLM or STT model, network, tools or system service.

This is a staging test adapter, not a production TTS provider. The production
voice.enabled / tts_enabled / handsfree_enabled flags remain unchanged.
"""
from __future__ import annotations

from collections.abc import Callable

from core.voice_pipeline import VoicePipeline
from scripts.ventuno_tts_synthesis_probe import PHRASE, validate_wav

FIXED_TRANSCRIPT = "Hej MyAI"
TEST_TRIGGER = b"MYAI-VOICE-SYNTHETIC-TRIGGER-ONLY"


class _SyntheticSTT:
    def __init__(self):
        self.calls = 0

    def transcribe(self, audio: bytes) -> dict[str, object]:
        if audio != TEST_TRIGGER:
            raise ValueError("synthetic-trigger-required")
        self.calls += 1
        return {"text": FIXED_TRANSCRIPT, "confidence": 0.99}


class _SyntheticAssistant:
    def __init__(self):
        self.calls = 0

    def respond(self, text: str) -> dict[str, object]:
        if text != FIXED_TRANSCRIPT:
            raise ValueError("synthetic-transcript-required")
        self.calls += 1
        return {"answer": PHRASE, "tools": [], "tool_results": {}}


class _MemoryWavTTS:
    def __init__(self, synthesize_to_memory: Callable[[str], bytes]):
        self._renderer = synthesize_to_memory
        self.calls = 0
        self.signal: dict[str, object] | None = None

    def speak(self, text: str) -> bool:
        if text != PHRASE:
            raise ValueError("fixed-synthetic-answer-required")
        if self.calls:
            raise ValueError("one-synthetic-tts-call-only")
        self.calls += 1
        wav = self._renderer(text)
        stats = validate_wav(wav)
        if not stats.get("signal_verified"):
            raise ValueError("inconclusive-synthetic-tts-signal")
        # Discard the audio; expose only numeric summaries.
        self.signal = stats
        return True


def run_synthetic_voice_chain(
    synthesize_to_memory: Callable[[str], bytes] | None,
    *,
    explicitly_authorized: bool = False,
) -> dict[str, object]:
    """Invoke voice reply plumbing with a mocked transcript/assistant only.

    Explicit authorization concerns a fixed synthetic TTS buffer, never
    consent for microphone recording or loudspeaker playback.
    """
    report: dict[str, object] = {
        "status": "synthetic-test-not-authorized",
        "real_voice_pipeline_used": False,
        "synthetic_transcript_used": True,
        "synthetic_assistant_response_used": True,
        "actual_stt_model_loaded": False,
        "live_geniex_called": False,
        "speaker_playback_attempted": False,
        "microphone_capture_attempted": False,
        "system_settings_modified": False,
        "production_services_changed": False,
        "tts_signal_verified": False,
        "tts_called_exactly_once": False,
    }
    if not explicitly_authorized:
        return report
    if not callable(synthesize_to_memory):
        report["status"] = "no-go-synthetic-tts-renderer-missing"
        return report
    stt = _SyntheticSTT()
    assistant = _SyntheticAssistant()
    tts = _MemoryWavTTS(synthesize_to_memory)
    pipeline = VoicePipeline(
        assistant=assistant,
        primary_stt=stt,
        tts=tts,
        settings={"voice": {
            "enabled": True,
            "tts_enabled": True,
            "redundancy_enabled": False,
            "echo_guard_enabled": False,
            "llm_streaming_enabled": False,
        }},
    )
    # Strictly fixed synthetic marker: no microphone capture and no speech.
    try:
        result = pipeline.process_utterance(TEST_TRIGGER)
    except (ValueError, RuntimeError, TypeError):
        report["status"] = "inconclusive-synthetic-voice-chain"
        return report
    report["real_voice_pipeline_used"] = True
    report["tts_called_exactly_once"] = tts.calls == 1
    if (result.get("status") == "completed" and
            stt.calls == 1 and assistant.calls == 1 and
            tts.calls == 1 and tts.signal is not None):
        report["tts_signal_verified"] = True
        report["status"] = "synthetic-myai-reply-to-wav-verified"
        for name in ("sample_rate_hz", "duration_seconds",
                     "rms_fraction_full_scale", "nonzero_samples"):
            report[name] = tts.signal[name]
    else:
        report["status"] = "inconclusive-synthetic-voice-chain"
    return report
