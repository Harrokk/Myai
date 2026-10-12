"""STT-gated Swedish MyAI/GenieX-to-WAV integration, no physical audio.

Whisper Tiny runs in a separately resource-limited CHILD process through
ventuno_whisper_tiny_cpu_smoke.smoke(), which uses a pinned, publicly
licensed Swedish one-word fixture. That process exits BEFORE GenieX or
eSpeak are used. This gate accepts only its strictly verified outcome.

The downstream real MyAI VoicePipeline still receives a FIXED synthetic
STT trigger, not live microphone audio. This proves stage ordering and
safe API/voice integration, not end-to-end live ASR or handsfree.
"""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

from scripts.ventuno_geniex_tts_bridge import run_live_voice_bridge
from scripts.ventuno_voice_wheel_staging import mem_available_kib

MIN_AVAILABLE_AFTER_STT_KIB = 1536 * 1024


def whisper_reference_accepted(report: object) -> bool:
    """Require the pinned public Swedish word to have been recognized."""
    if not isinstance(report, dict):
        return False
    return (
        report.get("status") == "tiny-sv-cpu-word-and-silence-verified"
        and report.get("cpu_inference_verified") is True
        and report.get("model_files_verified") is True
        and report.get("swedish_public_word_attempted") is True
        and report.get("swedish_public_word_recognized") is True
        and report.get("microphone_used") is False
        and report.get("model_installed_in_production") is False
        and report.get("geniex_restarted") is False
    )


def run_stt_gated_voice_bridge(
    whisper_report: object, stage_root: Path, *,
    authorized: bool = False, machine: str | None = None,
) -> dict[str, object]:
    """Only after the external STT child has finished, use one local LLM call."""
    report: dict[str, object] = {
        "status": "not-authorized",
        "public_fixture_whisper_verified": False,
        "whisper_child_finished_before_geniex": False,
        "geniex_to_wav_verified": False,
        "real_myai_voice_pipeline_used": False,
        "local_geniex_requested": False,
        "microphone_opened": False,
        "speaker_playback_attempted": False,
        "user_audio_used": False,
        "stt_transcript_logged": False,
        "tts_pcm_saved": False,
        "production_services_modified": False,
        "voice_enabled_in_production": False,
    }
    if not authorized:
        return report
    if (machine or platform.machine()).lower() not in ("arm64", "aarch64"):
        report["status"] = "reject-non-ventuno-arm64"
        return report
    if not whisper_reference_accepted(whisper_report):
        report["status"] = "reject-unverified-public-swedish-stt"
        return report
    report["public_fixture_whisper_verified"] = True
    report["whisper_child_finished_before_geniex"] = True
    available = mem_available_kib()
    if available is None or available < MIN_AVAILABLE_AFTER_STT_KIB:
        report["status"] = "reject-insufficient-ram-after-whisper"
        return report
    # The downstream bridge only accepts fixed synthetic transcript bytes.
    # It talks to the ALREADY running GenieX server and renders a single
    # bounded Swedish WAV in memory. It never accesses audio devices.
    report["local_geniex_requested"] = True
    response = run_live_voice_bridge(
        stage_root, explicitly_authorized=True,
        machine=machine or platform.machine(),
    )
    report["real_myai_voice_pipeline_used"] = (
        response.get("real_myai_voice_pipeline_used") is True
    )
    report["geniex_to_wav_verified"] = (
        response.get("live_response_to_swedish_tts_verified") is True
        and response.get("existing_geniex_api_used") is True
        and response.get("microphone_used") is False
        and response.get("speaker_used") is False
        and response.get("services_changed") is False
        and response.get("audio_saved") is False
    )
    report["status"] = (
        "public-swedish-whisper-gated-geniex-to-wav-verified"
        if report["geniex_to_wav_verified"]
        else "inconclusive-whisper-gated-geniex-to-wav"
    )
    if report["geniex_to_wav_verified"]:
        for key in ("duration_seconds", "sample_rate_hz",
                    "rms_fraction_full_scale"):
            report[key] = response.get(key)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp", required=True, type=Path)
    parser.add_argument("--run-isolated-public-fixture-chain", action="store_true")
    args = parser.parse_args()
    if not args.run_isolated_public_fixture_chain:
        print(json.dumps({"status": "not-authorized",
                          "microphone_opened": False,
                          "speaker_playback_attempted": False}))
        return 0
    from scripts.ventuno_whisper_tiny_cpu_smoke import smoke
    from scripts.ventuno_tts_temp_stage import stage_sweden_tts
    temp = args.runner_temp
    # Both functions fail closed on arch/resource/venv and staging identity.
    stt = smoke(temp / "myai-voice-staging/bin/python", temp)
    # No actual microphone waveform or transcript is included in output.
    print("Isolated public Swedish word STT verified:",
          whisper_reference_accepted(stt))
    if not whisper_reference_accepted(stt):
        print(json.dumps({"status": "reject-unverified-public-swedish-stt"}))
        return 2
    stage = stage_sweden_tts(temp / "myai-tts-espeak-stage", temp)
    print("Ephemeral Swedish TTS staging verified:",
          stage.get("swedish_pcm_synthesis_verified") is True)
    if stage.get("status") != "isolated-swedish-tts-signal-verified":
        return 2
    result = run_stt_gated_voice_bridge(
        stt, temp / "myai-tts-espeak-stage", authorized=True,
    )
    print("Whisper-verified public word -> MyAI/GenieX -> WAV:",
          json.dumps(result, sort_keys=True))
    return 0 if result["geniex_to_wav_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
