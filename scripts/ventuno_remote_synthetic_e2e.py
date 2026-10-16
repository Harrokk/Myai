"""Bounded, data-free MyAI VoicePipeline STT→assistant→WAV contract.

This test uses existing core.voice_pipeline with strictly synthetic fakes,
not Whisper weights, Ollama/GenieX, microphones, ALSA, pyttsx3, or NPU.
No persistent database, audio files, or temporary user content are created.
"""
from __future__ import annotations

import io
import json
import math
import struct
import tracemalloc
import wave

from scripts.ventuno_synthetic_voice_chain import (
    run_synthetic_voice_chain,
)

SAMPLES = 8_000
SAMPLE_RATE = 16_000
PEAK_BYTES_BUDGET = 32 * 1024 * 1024


def _fixed_wav(_answer: str, *, silent: bool = False) -> bytes:
    samples = [
        0 if silent else int(1800 * math.sin(2 * math.pi * 240 * n / SAMPLE_RATE))
        for n in range(SAMPLES)
    ]
    out = io.BytesIO()
    with wave.open(out, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes(struct.pack("<" + "h" * SAMPLES, *samples))
    return out.getvalue()


def run_contract() -> dict[str, object]:
    report = {
        "status": "synthetic-contract-blocked",
        "normal_voice_pipeline_with_fakes": False,
        "no_model_loaded": True,
        "no_microphone_or_speaker": True,
        "no_geniex_or_ollama": True,
        "no_database_created": True,
        "no_runtime_service_changed": True,
        "peak_python_allocations_under_32mib": False,
        "silence_rejected": False,
        "real_native_abi_verified": False,
        "physical_consent_implied": False,
    }
    tracemalloc.start()
    try:
        result = run_synthetic_voice_chain(
            _fixed_wav, explicitly_authorized=True
        )
        silence = run_synthetic_voice_chain(
            lambda text: _fixed_wav(text, silent=True),
            explicitly_authorized=True,
        )
        _, peak = tracemalloc.get_traced_memory()
    except Exception:
        report["status"] = "synthetic-contract-exception"
        return report
    finally:
        tracemalloc.stop()

    report["normal_voice_pipeline_with_fakes"] = (
        result.get("status") == "synthetic-myai-reply-to-wav-verified"
        and result.get("real_voice_pipeline_used") is True
        and result.get("tts_called_exactly_once") is True
    )
    report["silence_rejected"] = (
        silence.get("status") == "inconclusive-synthetic-voice-chain"
        and silence.get("tts_signal_verified") is False
    )
    report["peak_python_allocations_under_32mib"] = peak < PEAK_BYTES_BUDGET
    report["status"] = (
        "synthetic-stt-llm-tts-fake-chain-verified"
        if (report["normal_voice_pipeline_with_fakes"]
            and report["silence_rejected"]
            and report["peak_python_allocations_under_32mib"])
        else "synthetic-contract-blocked"
    )
    return report


def main() -> int:
    report = run_contract()
    print("MYAI_SYNTHETIC_VOICE_E2E_JSON=" + json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "synthetic-stt-llm-tts-fake-chain-verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
