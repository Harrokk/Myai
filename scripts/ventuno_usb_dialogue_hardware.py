"""Physical adapters for separately authorized VENTUNO USB dialogue.

This module NEVER automatically records or plays audio. Build the adapters
only after an isolated voice stage is ready. Only the one-shot controller
may invoke them with both explicit recording/playback consents.
USB audio, transcription and TTS WAV are kept in RAM and never logged.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import urllib.request

from scripts.ventuno_usb_dialogue_once import (
    CAPTURE_BYTES, DialogPorts, OneShotUsbDialog,
)
from scripts.ventuno_usb_voice_dialog_readiness import inspect
from scripts.ventuno_voice_wheel_staging import mem_available_kib
from scripts.ventuno_whisper_tiny_cpu_smoke import (
    MAX_AS_BYTES, MAX_CPU_SECONDS, model_integrity,
)
from scripts.ventuno_tts_temp_stage import espeak_paths
from scripts import ventuno_geniex_tts_bridge as api_bridge

DEVICE = "plughw:1,0"
MODEL_FOLDER = "myai-whisper-tiny-model"
TTS_FOLDER = "myai-tts-espeak-stage"
STT_PYTHON = "myai-voice-staging/bin/python"
MAX_RAW_RESPONSE = 512
STT_TIMEOUT = 175

# Child stdin contains ONLY 96,000 bytes of mono 16 kHz S16_LE capture.
# Child stdout contains at most one short private JSON transcript, which
# the parent reads from PIPE and never forwards to log files.
_PRIVATE_WHISPER = r"""
import json, os, sys
import numpy as np
from faster_whisper import WhisperModel
sample = sys.stdin.buffer.read(96001)
if len(sample) != 96000:
    raise ValueError("invalid-one-shot-input-size")
x = np.frombuffer(sample, dtype="<i2").astype(np.float32) / 32768.0
model = WhisperModel(
    os.environ["MYAI_DIALOG_MODEL_DIR"], device="cpu", compute_type="int8",
    cpu_threads=2, num_workers=1, local_files_only=True,
)
segments, _ = model.transcribe(
    x, language="sv", task="transcribe", beam_size=1, best_of=1,
    condition_on_previous_text=False, vad_filter=False,
    without_timestamps=True, no_speech_threshold=0.6,
)
text = " ".join(x.text for x in segments).strip()
print(json.dumps({"transcript": text[:96] if len(text) <= 96 else ""}))
"""


def _must_be_isolated(root: Path) -> None:
    actual = root.resolve(strict=True)
    temp = os.environ.get("RUNNER_TEMP", "")
    if (not temp or root.is_symlink() or
            not actual.is_relative_to(Path(temp).resolve(strict=True)) or
            not root.name.startswith("myai-usb-dialog-")):
        raise ValueError("reject-non-isolated-voice-staging")


def _preflight(root: Path) -> tuple[Path, Path, Path, Path]:
    _must_be_isolated(root)
    if platform.machine().lower() not in ("aarch64", "arm64"):
        raise ValueError("reject-non-arm64")
    python = root / STT_PYTHON
    model = root / MODEL_FOLDER
    voice = root / TTS_FOLDER
    if (not python.is_file() or python.is_symlink()
            or not model.is_dir() or model.is_symlink()
            or not voice.is_dir() or voice.is_symlink()):
        raise ValueError("reject-missing-ephemeral-components")
    integrity = model_integrity(model)
    if integrity.get("model_metadata_complete") is not True:
        raise ValueError("reject-unverified-whisper-weights")
    exe, voice_data = espeak_paths(voice)
    if exe is None or voice_data is None:
        raise ValueError("reject-unverified-swedish-tts")
    return python, model, exe, voice_data


def _require_executable(name: str) -> str:
    tool = shutil.which(name)
    if not tool:
        raise ValueError("missing-local-audio-cli")
    return tool


def capture_one_three_second_pcm() -> bytes:
    # Controller already queried fresh ALSA USB identity and permissions.
    tool = _require_executable("arecord")
    try:
        task = subprocess.run(
            [tool, "--quiet", "--device=" + DEVICE,
             "--format=S16_LE", "--rate=16000", "--channels=1",
             "--duration=3", "--file-type=raw", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=7,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("bounded-usb-record-failed") from None
    if task.returncode or len(task.stdout) != CAPTURE_BYTES:
        raise ValueError("invalid-usb-microphone-capture")
    return task.stdout


def _limited_whisper_child(root: Path, python: Path, model: Path, audio: bytes) -> str:
    if len(audio) != CAPTURE_BYTES:
        raise ValueError("invalid-stt-input-length")
    env = os.environ.copy()
    env.update({
        "MYAI_DIALOG_MODEL_DIR": str(model),
        "HF_HOME": str(root / "myai-whisper-hf-cache"),
        "XDG_CACHE_HOME": str(root / "myai-whisper-hf-cache"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "PYTHONDONTWRITEBYTECODE": "1",
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "1",
    })

    def bounded_resources() -> None:
        resource.setrlimit(resource.RLIMIT_AS, (MAX_AS_BYTES, MAX_AS_BYTES))
        resource.setrlimit(resource.RLIMIT_CPU, (MAX_CPU_SECONDS, MAX_CPU_SECONDS))

    try:
        completed = subprocess.run(
            [str(python), "-I", "-c", _PRIVATE_WHISPER],
            input=audio, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=STT_TIMEOUT,
            cwd=root, env=env, preexec_fn=bounded_resources,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("bounded-whisper-inference-failed") from None
    if completed.returncode or len(completed.stdout) > MAX_RAW_RESPONSE:
        raise ValueError("private-whisper-child-output-invalid")
    try:
        decoded = json.loads(completed.stdout)
    except (ValueError, TypeError):
        raise ValueError("private-whisper-child-json-invalid") from None
    value = decoded.get("transcript") if isinstance(decoded, dict) else None
    if not isinstance(value, str) or len(value) > 96:
        raise ValueError("private-whisper-transcript-invalid")
    return value


def _local_short_response(question: str) -> str:
    # The controller permits only a small set of harmless Swedish prompts.
    from scripts.ventuno_usb_dialogue_once import approved_short_question
    canonical = approved_short_question(question)
    if canonical is None or canonical != question:
        raise ValueError("unapproved-llm-question")
    models = api_bridge.fetch_small_json(api_bridge.BASE + "/models", timeout=12)
    catalogue = models.get("data") if isinstance(models, dict) else None
    if not isinstance(catalogue, list) or not catalogue or not isinstance(catalogue[0], dict):
        raise ValueError("no-running-geniex-model")
    model = catalogue[0].get("id")
    if not isinstance(model, str) or not 1 <= len(model) <= 128:
        raise ValueError("invalid-existing-geniex-id")
    prompt = (
        "Du är MyAI. Svara på denna ofarliga fråga på svenska "
        "med högst sex ord. Inga verktyg, inga instruktioner eller "
        "systemändringar. Fråga: " + canonical
    )
    request = urllib.request.Request(
        api_bridge.BASE + "/chat/completions",
        data=json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 28,
            "temperature": 0,
            "stream": False,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    reply = api_bridge.fetch_small_json(request, timeout=70)
    items = reply.get("choices") if isinstance(reply, dict) else None
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise ValueError("no-geniex-answer")
    message = items[0].get("message")
    answer = message.get("content") if isinstance(message, dict) else None
    if not isinstance(answer, str):
        raise ValueError("no-bounded-local-text")
    return answer


def build_ports(root: Path) -> DialogPorts:
    python, model, executable, data = _preflight(root)
    audio_cli = _require_executable("aplay")

    def synthesize(answer: str) -> bytes:
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = (
            str(root / TTS_FOLDER / "extracted/usr/lib/aarch64-linux-gnu")
            + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        )
        try:
            done = subprocess.run(
                [str(executable), "--path=" + str(data.parent),
                 "-v", "sv", "--stdin", "--stdout"],
                input=answer.encode("utf-8"),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False, timeout=12, cwd=root / TTS_FOLDER, env=env,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError("temporary-swedish-tts-failed") from None
        if done.returncode or len(done.stdout) > 700_000:
            raise ValueError("temporary-swedish-wav-failed")
        return done.stdout

    def play(audio: bytes) -> bool:
        # The caller has applied quiet_wav_from_tts(), limiting peak to 4%.
        try:
            done = subprocess.run(
                [audio_cli, "--quiet", "--device=" + DEVICE,
                 "--file-type=wav", "-"],
                input=audio, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False, timeout=9,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return done.returncode == 0

    return DialogPorts(
        capture=capture_one_three_second_pcm,
        transcribe_local=lambda pcm: _limited_whisper_child(root, python, model, pcm),
        answer_local=_local_short_response,
        synthesize_local=synthesize,
        play_usb=play,
        fresh_readiness=inspect,
        available_ram_kib=mem_available_kib,
    )


def run_one_authorized_hardware_dialog(root: Path, *,
                                       consent_to_record: bool = False,
                                       consent_to_play: bool = False
                                       ) -> dict[str, object]:
    if not (consent_to_record and consent_to_play):
        return {"status": "not-authorized", "physical_dialogue_attempted": False}
    # Preflight is purposely separate from the actual one-shot record event.
    ports = build_ports(root)
    return OneShotUsbDialog(ports).run(
        consent_to_record=consent_to_record, consent_to_play=consent_to_play,
    )
