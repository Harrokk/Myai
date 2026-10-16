"""Classify actual isolated ARM64 native package imports without audio access.

Runs each fixed import in its own bounded child Python. Never constructs a
Whisper model or pyttsx3 engine; never opens PortAudio devices.
Only categorical errors, not stack traces/paths/user data, leave this script.
"""
from __future__ import annotations

import json
import os
import resource
import subprocess
import sys

MODULES = ("webrtcvad", "pyttsx3", "ctranslate2", "av", "faster_whisper", "sounddevice")
TIMEOUT_SECONDS = 35
MAX_VMEM = 8 * 1024**3
MAX_CPU = 25

CHILD = (
    "import importlib, json, resource, sys\n"
    "importlib.import_module(sys.argv[1])\n"
    "print(json.dumps({'ok':True,'rss_kib':"
    "resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}))\n"
)


def _limits():
    resource.setrlimit(resource.RLIMIT_CPU, (MAX_CPU, MAX_CPU))
    resource.setrlimit(resource.RLIMIT_AS, (MAX_VMEM, MAX_VMEM))


def classify(module, result):
    if module not in MODULES:
        return {"status": "blocked-unknown-module"}
    if isinstance(result, subprocess.TimeoutExpired):
        return {"status": "timeout"}
    if isinstance(result, OSError):
        return {"status": "launch-error"}
    if not getattr(result, "returncode", 1):
        try:
            data = json.loads(result.stdout.strip())
            rss = data.get("rss_kib")
            if data.get("ok") is True and type(rss) is int and 0 < rss < 8 * 1024**2:
                return {"status": "import-ok", "rss_mib": round(rss / 1024, 1)}
        except (ValueError, TypeError, AttributeError):
            pass
        return {"status": "bad-import-report"}
    if module == "sounddevice" and "PortAudio library not found" in str(result.stderr)[-1500:]:
        return {"status": "missing-system-portaudio"}
    return {"status": "native-import-failed"}


def probe(*, executable=None, runner=None):
    executable = executable or sys.executable
    runner = runner or subprocess.run
    report = {}
    environment = os.environ.copy()
    environment.update({
        "HF_HUB_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
        "TRANSFORMERS_OFFLINE": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
    })
    for module in MODULES:
        try:
            run = runner(
                [str(executable), "-I", "-c", CHILD, module],
                timeout=TIMEOUT_SECONDS, capture_output=True, text=True,
                errors="replace", check=False, env=environment, preexec_fn=_limits,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            run = exc
        report[module] = classify(module, run)
    all_ok = all(v["status"] == "import-ok" for v in report.values())
    portaudio_only = (
        report["sounddevice"]["status"] == "missing-system-portaudio"
        and all(report[k]["status"] == "import-ok"
                for k in MODULES if k != "sounddevice")
    )
    return {
        "status": ("six-native-package-imports-verified" if all_ok else
                   "blocked-system-portaudio" if portaudio_only else
                   "blocked-other-native-imports"),
        "per_module": report,
        "native_imports_all_succeeded": all_ok,
        "five_non_audio_imports_succeeded": portaudio_only or all_ok,
        "production_venv_modified": False,
        "sounddevice_stream_opened": False,
        "microphone_or_speaker_opened": False,
        "tts_engine_started": False,
        "stt_model_instantiated": False,
        "npu_executed": False,
        "physical_test_authorized": False,
    }


if __name__ == "__main__":
    print("MYAI_NATIVE_VOICE_IMPORT_REPORT_JSON=" + json.dumps(probe(), sort_keys=True))
