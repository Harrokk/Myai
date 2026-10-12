"""Opt-in, strictly bounded live GenieX response -> MyAI VoicePipeline -> WAV.

Uses the EXISTING GenieX server bound to localhost and the already-isolated
ARM64 eSpeak staging files. No microphone, speaker, new LLM model, MyAI
memory/tool/database, service change or voice configuration write.
A synthetic transcript and a single short deterministic GenieX reply are
used only after the explicit --allow-local-geniex-inference flag.
Generated text and raw audio are never printed or saved.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.voice_pipeline import VoicePipeline
from scripts.ventuno_tts_synthesis_probe import MAX_WAV_BYTES, validate_wav
from scripts.ventuno_tts_temp_stage import espeak_paths

BASE = "http://127.0.0.1:18181/v1"
FIXED_TRANSCRIPT = "Säg ett kort hej på svenska"
FIXED_TRIGGER = b"MYAI-LIVE-TTS-SYNTHETIC-TRANSCRIPT"
MAX_TEXT_CHARACTERS = 220
MAX_BODY_BYTES = 64 * 1024


def fetch_small_json(request: Request | str, *, timeout: float) -> dict:
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_BODY_BYTES + 1)
    if len(raw) > MAX_BODY_BYTES:
        raise ValueError("oversized-local-geniex-response")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("invalid-local-geniex-json")
    return parsed


class _SyntheticSTT:
    def __init__(self):
        self.calls = 0

    def transcribe(self, audio: bytes):
        if audio != FIXED_TRIGGER:
            raise ValueError("synthetic-transcript-trigger-required")
        self.calls += 1
        return {"text": FIXED_TRANSCRIPT, "confidence": 0.99}


class ExistingGenieXResponder:
    def __init__(self):
        self.calls = 0
        self.model_is_from_live_catalogue = False

    def respond(self, transcript: str) -> dict[str, object]:
        if transcript != FIXED_TRANSCRIPT or self.calls:
            raise ValueError("single-fixed-synthetic-request-only")
        self.calls += 1
        models = fetch_small_json(BASE + "/models", timeout=12).get("data", [])
        if (not isinstance(models, list) or not models
                or not isinstance(models[0], dict)
                or not isinstance(models[0].get("id"), str)
                or not models[0]["id"] or len(models[0]["id"]) > 128):
            raise ValueError("no-active-local-geniex-model")
        model = models[0]["id"]
        self.model_is_from_live_catalogue = True
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content":
                          "Svara på svenska i en kort mening. Hälsa vänligt."}],
            "max_tokens": 40,
            "temperature": 0,
            "stream": False,
        }).encode("utf-8")
        request = Request(
            BASE + "/chat/completions", data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        data = fetch_small_json(request, timeout=70)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("missing-local-geniex-answer")
        answer = (choices[0].get("message") or {}).get("content")
        if not isinstance(answer, str):
            raise ValueError("nontext-local-geniex-answer")
        answer = answer.strip()
        if (not 1 <= len(answer) <= MAX_TEXT_CHARACTERS
                or any(ord(ch) < 32 and ch not in "\n\t" for ch in answer)):
            raise ValueError("geniex-reply-not-safe-for-bounded-tts")
        return {"answer": answer, "tools": [], "tool_results": {}}


class _InMemoryEspeak:
    def __init__(self, exe: Path, data: Path, env: dict[str, str]):
        self.exe = exe
        self.data = data
        self.env = env
        self.calls = 0
        self.wav_summary: dict[str, object] | None = None

    def speak(self, text: str) -> bool:
        if (self.calls or not isinstance(text, str) or
                not 1 <= len(text) <= MAX_TEXT_CHARACTERS):
            raise ValueError("single-bounded-geniex-speech-only")
        self.calls += 1
        # --stdin avoids interpreting an LLM response as command-line options.
        try:
            process = subprocess.run(
                [str(self.exe), "--path=" + str(self.data.parent),
                 "-v", "sv", "--stdin", "--stdout"],
                input=text.encode("utf-8"), capture_output=True, check=False,
                env=self.env, cwd=self.exe.parent, timeout=12,
            )
        except (subprocess.TimeoutExpired, OSError):
            raise RuntimeError("bounded-espeak-synthesis-failed") from None
        if process.returncode or len(process.stdout) > MAX_WAV_BYTES:
            raise ValueError("espeak-invalid-output")
        report = validate_wav(process.stdout)
        if not report.get("signal_verified"):
            raise ValueError("espeak-no-verifiable-voice-signal")
        self.wav_summary = report
        return True


def run_live_voice_bridge(root: Path, *, explicitly_authorized: bool,
                          machine: str | None = None) -> dict[str, object]:
    report: dict[str, object] = {
        "status": "no-go-live-synthetic-inference-not-authorized",
        "existing_geniex_api_used": False,
        "live_response_to_swedish_tts_verified": False,
        "real_myai_voice_pipeline_used": False,
        "synthetic_transcript_only": True,
        "microphone_used": False,
        "speaker_used": False,
        "new_llm_model_loaded": False,
        "os_packages_installed": False,
        "voice_production_enabled": False,
        "services_changed": False,
        "audio_saved": False,
        "reply_text_logged": False,
    }
    if not explicitly_authorized:
        return report
    if (machine or platform.machine()).lower() not in ("aarch64", "arm64"):
        report["status"] = "no-go-not-ventuno-arm64"
        return report
    if (root.is_symlink() or not root.is_dir()
            or root.name != "myai-tts-espeak-stage"):
        report["status"] = "no-go-tts-temp-root"
        return report
    exe, data = espeak_paths(root)
    if exe is None or data is None:
        report["status"] = "no-go-missing-isolated-espeak"
        return report
    extracted_lib = root / "extracted/usr/lib/aarch64-linux-gnu"
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(extracted_lib) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    stt = _SyntheticSTT()
    assistant = ExistingGenieXResponder()
    tts = _InMemoryEspeak(exe, data, env)
    pipeline = VoicePipeline(
        assistant=assistant,
        primary_stt=stt,
        tts=tts,
        settings={"voice": {
            "enabled": True, "tts_enabled": True,
            "redundancy_enabled": False, "echo_guard_enabled": False,
            "llm_streaming_enabled": False,
        }},
    )
    try:
        result = pipeline.process_utterance(FIXED_TRIGGER)
    except (ValueError, TypeError, RuntimeError, HTTPError, URLError,
            TimeoutError, OSError, json.JSONDecodeError):
        report["status"] = "inconclusive-bounded-live-geniex-voice-bridge"
        return report
    report["existing_geniex_api_used"] = bool(assistant.calls == 1
                                               and assistant.model_is_from_live_catalogue)
    report["real_myai_voice_pipeline_used"] = True
    if (result.get("status") == "completed" and stt.calls == 1
            and tts.calls == 1 and tts.wav_summary is not None):
        report["status"] = "live-geniex-to-swedish-wav-signal-verified"
        report["live_response_to_swedish_tts_verified"] = True
        for key in ("duration_seconds", "sample_rate_hz",
                    "rms_fraction_full_scale"):
            report[key] = tts.wav_summary[key]
    else:
        report["status"] = "inconclusive-bounded-live-geniex-voice-bridge"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp", type=Path, required=True)
    parser.add_argument("--allow-local-geniex-inference", action="store_true")
    args = parser.parse_args()
    result = run_live_voice_bridge(
        args.runner_temp / "myai-tts-espeak-stage",
        explicitly_authorized=args.allow_local_geniex_inference,
    )
    print("Live local GenieX -> synthetic MyAI voice -> Swedish WAV:",
          json.dumps(result, sort_keys=True))
    print("No actual user audio, text logs, speaker, second model or service mutation.")
    return 0 if result["live_response_to_swedish_tts_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
