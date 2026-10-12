"""One-turn opt-in USB dialog test: 1 cue -> 4s mic -> Whisper -> GenieX -> TTS.

Exactly ONE physical microphone capture, at most TWO volume-limited speaker
playbacks, and no memory/tool/file actions by the LLM. Everything in RAM.
Must run ONLY in an isolated runner workspace with pinned Whisper model
already checked by the separate public-reference CPU benchmark and
temporarily staged Swedish eSpeak. No production service/config writes.

User hears "Ställ din fråga nu" before the four-second capture begins.
All transcript and reply contents stay in process memory and are never
printed, persisted or uploaded. The already running GenieX uses localhost.
"""
from __future__ import annotations

import array
import io
import json
import os
import platform
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import wave

from core.voice_pipeline import VoicePipeline, classify_voice_risk
from scripts.ventuno_geniex_tts_bridge import (
    BASE, MAX_TEXT_CHARACTERS, fetch_small_json,
)
from scripts.ventuno_tts_temp_stage import espeak_paths
from scripts.ventuno_usb_audio_inventory import inventory_usb_audio
from scripts.ventuno_voice_wheel_staging import mem_available_kib
from scripts.ventuno_whisper_tiny_cpu_smoke import (
    EXPECTED_MODEL_SHA256, MAX_AS_BYTES, MAX_CPU_SECONDS,
    MIN_MEM_AVAILABLE_KIB, model_integrity,
)
from urllib.request import Request
from scripts.ventuno_usb_speaker_smoke import quiet_wav_from_tts

PAIR = [1, 0]
DEVICE = "plughw:1,0"
SAMPLE_RATE = 16000
CAPTURE_SECONDS = 4
RAW_BYTES = SAMPLE_RATE * CAPTURE_SECONDS * 2
CUE = "Ställ din fråga nu."
TRIGGER = b"AUTHORIZED-ONE-TURN-USB-DIALOG"
MAX_USER_TEXT = 160
MAX_RESPONSE_CHARS = 65
MAX_SPEAKER_PLAYS = 2
MAX_SPEAKER_PEAK = 0.04
MODEL_STDIN_TIMEOUT = 120

_WHISPER_STDIN_WORKER = r"""
import json, os, resource, sys
import numpy as np
from faster_whisper import WhisperModel

raw=sys.stdin.buffer.read(128001)
if len(raw) != 128000:
    print(json.dumps({"status":"invalid-capture"}))
    raise SystemExit(0)
speech=np.frombuffer(raw, dtype="<i2").astype(np.float32)/32768.0
model=WhisperModel(
    os.environ["MYAI_TINY_MODEL_DIR"], device="cpu",
    compute_type="int8", cpu_threads=2, num_workers=1,
    local_files_only=True,
)
parts,_=model.transcribe(
    speech, language="sv", task="transcribe", beam_size=1,
    best_of=1, condition_on_previous_text=False,
    vad_filter=False, without_timestamps=True,
    no_speech_threshold=0.6,
)
transcript=" ".join(part.text for part in parts).strip()
# Private in-memory stdout PIPE to parent, never to CI logs.
print(json.dumps({"status":"transcribed" if transcript else "no-speech",
                  "private_transcript":transcript}, ensure_ascii=False))
"""


def acceptable_question(text: object) -> bool:
    if not isinstance(text, str):
        return False
    cleaned = text.strip()
    if not 1 <= len(cleaned) <= MAX_USER_TEXT:
        return False
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in cleaned):
        return False
    if "--" in cleaned:
        return False
    # In this one-off smoke, do NOT execute any high-risk instructions.
    return classify_voice_risk(cleaned)["level"] == "low"


def allowed_usb() -> bool:
    usb = inventory_usb_audio()
    return (
        1 in usb.get("usb_audio_cards", [])
        and PAIR in usb.get("usb_capture_pairs", [])
        and PAIR in usb.get("usb_playback_pairs", [])
        and all(any(
            isinstance(entry, dict) and entry.get("pair") == PAIR
            and entry.get("character_device") is True
            and entry.get("accessible") is True
            for entry in usb.get(key, [])
        ) for key in ("capture_device_nodes", "playback_device_nodes"))
    )


def render_quiet_wav(text: str, stage: Path) -> bytes | None:
    if not isinstance(text, str) or not 1 <= len(text) <= MAX_RESPONSE_CHARS:
        return None
    exe, data = espeak_paths(stage)
    if exe is None or data is None:
        return None
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = (
        str(stage / "extracted/usr/lib/aarch64-linux-gnu")
        + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    )
    try:
        process = subprocess.run(
            [str(exe), "--path=" + str(data.parent),
             "-v", "sv", "--stdin", "--stdout"],
            input=text.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=stage, env=env, check=False, timeout=12,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if process.returncode != 0:
        return None
    quiet, info = quiet_wav_from_tts(process.stdout)
    if not info.get("source_wav_valid"):
        return None
    if info.get("limited_peak_fraction", 1) > MAX_SPEAKER_PEAK:
        return None
    return quiet


def play_one(wav_bytes: bytes) -> bool:
    # Never call this except after explicit authorization and USB recheck.
    if not allowed_usb():
        return False
    tool = shutil.which("aplay")
    if tool is None:
        return False
    try:
        return subprocess.run(
            [tool, "--quiet", "--device=" + DEVICE, "--file-type=wav", "-"],
            input=wav_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=9,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def capture_once() -> bytes | None:
    if not allowed_usb():
        return None
    tool = shutil.which("arecord")
    if tool is None:
        return None
    try:
        process = subprocess.run([
            tool, "--quiet", "--device=" + DEVICE, "--format=S16_LE",
            "--rate=16000", "--channels=1", "--duration=4",
            "--file-type=raw", "-",
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
           check=False, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (process.stdout if process.returncode == 0
            and len(process.stdout) == RAW_BYTES else None)


def decode_live_pcm(pcm: bytes, model_path: Path, python_exe: Path,
                    *, root: Path) -> str | None:
    if (not isinstance(pcm, bytes) or len(pcm) != RAW_BYTES
            or model_integrity(model_path).get("model_sha256")
               != EXPECTED_MODEL_SHA256):
        return None
    expected = root / "myai-voice-staging/bin/python"
    if not python_exe.is_file() or python_exe != expected:
        return None
    if (mem_available_kib() or 0) < MIN_MEM_AVAILABLE_KIB:
        return None
    env = os.environ.copy()
    env.update({
        "MYAI_TINY_MODEL_DIR": str(model_path),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    def restrict():
        resource.setrlimit(resource.RLIMIT_AS, (MAX_AS_BYTES, MAX_AS_BYTES))
        resource.setrlimit(resource.RLIMIT_CPU,
                           (MAX_CPU_SECONDS, MAX_CPU_SECONDS))
    try:
        process = subprocess.run(
            [str(python_exe), "-I", "-c", _WHISPER_STDIN_WORKER],
            input=pcm, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=root, env=env, check=False, timeout=MODEL_STDIN_TIMEOUT,
            preexec_fn=restrict,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if process.returncode != 0 or len(process.stdout) > 4096:
        return None
    try:
        decoded = json.loads(process.stdout)
    except (ValueError, UnicodeError):
        return None
    if not isinstance(decoded, dict) or decoded.get("status") != "transcribed":
        return None
    candidate = decoded.get("private_transcript")
    return candidate.strip() if acceptable_question(candidate) else None


class SingleTranscript:
    def __init__(self, value: str):
        self.value = value
        self.calls = 0

    def transcribe(self, audio: bytes):
        if audio != TRIGGER or self.calls:
            raise ValueError("invalid-one-time-stt-trigger")
        self.calls += 1
        return {"text": self.value, "confidence": None}


class OneTurnGenieX:
    def __init__(self, expected: str):
        self.expected = expected
        self.calls = 0

    def respond(self, transcript: str):
        if self.calls or transcript != self.expected or not acceptable_question(transcript):
            raise ValueError("unapproved-one-turn-transcript")
        self.calls += 1
        models = fetch_small_json(BASE + "/models", timeout=12).get("data")
        if (not isinstance(models, list) or not models
                or not isinstance(models[0], dict)
                or not isinstance(models[0].get("id"), str)
                or not 1 <= len(models[0]["id"]) <= 128):
            raise ValueError("no-running-local-model")
        prompt = (
            "Svara på följande korta fråga på svenska med högst åtta ord. "
            "Använd inga verktyg och utför inga åtgärder: " + transcript
        )
        payload = json.dumps({
            "model": models[0]["id"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 32, "temperature": 0, "stream": False,
        }).encode()
        result = fetch_small_json(Request(
            BASE + "/chat/completions", data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        ), timeout=70)
        choices = result.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("no-local-reply")
        message = choices[0].get("message")
        answer = message.get("content") if isinstance(message, dict) else None
        if not isinstance(answer, str) or not 1 <= len(answer.strip()) <= MAX_RESPONSE_CHARS:
            raise ValueError("unexpected-tts-answer-length")
        return {"answer": answer.strip(), "tools": [], "tool_results": {}}


class SpokenResponse:
    def __init__(self, stage: Path):
        self.stage = stage
        self.calls = 0
        self.played = False

    def speak(self, text: str):
        if self.calls:
            raise ValueError("only-one-response")
        self.calls += 1
        wav = render_quiet_wav(text, self.stage)
        if wav is None:
            raise ValueError("response-too-long-or-unrenderable")
        if not play_one(wav):
            raise RuntimeError("speaker-no-playback")
        self.played = True
        return True


def once(*, authorized: bool, stage: Path, model: Path, python_exe: Path,
         root: Path, machine: str | None = None) -> dict[str, object]:
    report: dict[str, object] = {
        "status": "not-authorized",
        "cue_played": False,
        "microphone_capture_attempted": False,
        "whisper_transcript_accepted": False,
        "geniex_response_attempted": False,
        "response_playback_complete": False,
        "user_reported_audible": False,
        "microphone_recordings": 0,
        "speaker_playbacks": 0,
        "transcript_logged": False,
        "audio_saved": False,
        "response_logged": False,
        "production_modified": False,
    }
    if not authorized:
        return report
    if (machine or platform.machine()).lower() not in ("arm64", "aarch64"):
        report["status"] = "reject-architecture"
        return report
    if (not root.is_dir() or root.is_symlink()
            or stage != root / "myai-tts-espeak-stage"
            or model != root / "myai-whisper-tiny-model"
            or python_exe != root / "myai-voice-staging/bin/python"
            or not allowed_usb()):
        report["status"] = "reject-isolation-or-usb-device"
        return report
    if (mem_available_kib() or 0) < MIN_MEM_AVAILABLE_KIB:
        report["status"] = "reject-memory-budget"
        return report
    if model_integrity(model).get("model_sha256") != EXPECTED_MODEL_SHA256:
        report["status"] = "reject-unverified-model"
        return report
    cue_wav = render_quiet_wav(CUE, stage)
    if not cue_wav:
        report["status"] = "reject-cue-render"
        return report
    report["speaker_playbacks"] = 1
    if not play_one(cue_wav):
        report["status"] = "cue-playback-failed"
        return report
    report["cue_played"] = True
    report["microphone_capture_attempted"] = True
    report["microphone_recordings"] = 1
    pcm = capture_once()
    if pcm is None:
        report["status"] = "no-valid-four-second-usb-capture"
        return report
    question = decode_live_pcm(pcm, model, python_exe, root=root)
    del pcm
    if question is None:
        report["status"] = "no-accepted-swedish-question"
        return report
    report["whisper_transcript_accepted"] = True
    if not allowed_usb() or (mem_available_kib() or 0) < 1536 * 1024:
        report["status"] = "reject-resources-or-usb-before-reply"
        return report
    stt = SingleTranscript(question)
    responder = OneTurnGenieX(question)
    tts = SpokenResponse(stage)
    pipeline = VoicePipeline(
        assistant=responder, primary_stt=stt, tts=tts,
        settings={"voice": {
            "enabled": True, "tts_enabled": True,
            "redundancy_enabled": False,
            "echo_guard_enabled": False,
            "llm_streaming_enabled": False,
        }},
    )
    report["geniex_response_attempted"] = True
    try:
        result = pipeline.process_utterance(TRIGGER)
    except (ValueError, TypeError, RuntimeError, OSError):
        report["status"] = "inconclusive-local-answer-or-tts"
        return report
    report["response_playback_complete"] = (
        result.get("status") == "completed"
        and stt.calls == 1 and responder.calls == 1
        and tts.calls == 1 and tts.played
    )
    if tts.calls:
        report["speaker_playbacks"] = 2
    report["status"] = (
        "one-turn-usb-dialogue-playback-completed"
        if report["response_playback_complete"]
        else "inconclusive-one-turn-dialogue"
    )
    return report
