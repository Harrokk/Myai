"""Bounded, non-device Python import proof for an ephemeral ARM64 voice venv.

Never constructs WhisperModel, sounddevice InputStream, pyttsx3 engine,
GenieX, audio files, or an NPU request. A probe requires an explicit CI-only
environment gate and a fresh venv outside MyAI's installed directory.
All exceptions are reduced to allowlisted *type names*, never traceback,
file paths, audio, text, tokens or environment contents.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import platform
import resource
import sys

MODULES = (
    "numpy", "av", "ctranslate2", "faster_whisper",
    "sounddevice", "webrtcvad", "pyttsx3",
)
SAFE_EXCEPTIONS = frozenset((
    "ImportError", "ModuleNotFoundError", "OSError",
    "RuntimeError", "ValueError", "AttributeError", "TypeError",
))


def permitted(*, stage_root, runner_temp, interpreter_prefix,
              arm64, marker):
    try:
        root = Path(stage_root)
        temp = Path(runner_temp)
        prefix = Path(interpreter_prefix)
        live = Path("/home/arduino/MyAI").resolve()
        if (not arm64 or marker != "disposable-import-only"
                or root.is_symlink() or temp.is_symlink()
                or not root.is_dir() or not temp.is_dir()
                or root.name.startswith("myai-native-voice-") is False):
            return False
        root_res = root.resolve(strict=True)
        temp_res = temp.resolve(strict=True)
        prefix_res = prefix.resolve(strict=True)
        if root_res.parent != temp_res:
            return False
        if root_res == live or root_res.is_relative_to(live):
            return False
        if prefix_res != root_res / "venv":
            return False
        if not (prefix_res / "bin/python").exists():
            return False
        return True
    except (OSError, TypeError, ValueError):
        return False


def import_report(loader=importlib.import_module):
    found = {}
    for module in MODULES:
        try:
            loader(module)
            found[module] = "imported"
        except Exception as exc:
            label = type(exc).__name__
            found[module] = label if label in SAFE_EXCEPTIONS else "other-error"
    complete = all(outcome == "imported" for outcome in found.values())
    return {
        "status": ("isolated-native-package-imports-confirmed"
                   if complete else "blocked-isolated-native-imports"),
        "results": found,
        "all_imports_ok": complete,
        "peak_import_process_rss_mib":
            round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "model_loaded": False,
        "microphone_opened": False,
        "tts_engine_initialized": False,
        "speaker_opened": False,
        "geniex_accessed": False,
        "npu_inference_performed": False,
        "production_venv_modified": False,
        "abi_full_end_to_end_approved": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isolated-native-imports", action="store_true")
    args = parser.parse_args(argv)
    valid = args.isolated_native_imports and permitted(
        stage_root=os.environ.get("MYAI_STAGE_ROOT", ""),
        runner_temp=os.environ.get("RUNNER_TEMP", ""),
        interpreter_prefix=sys.prefix,
        arm64=platform.machine().lower() in ("aarch64", "arm64"),
        marker=os.environ.get("MYAI_NATIVE_PROBE_MARKER"),
    )
    result = import_report() if valid else {
        "status": "blocked-unverified-stage-path",
        "all_imports_ok": False,
        "model_loaded": False,
        "microphone_opened": False,
        "speaker_opened": False,
        "npu_inference_performed": False,
        "production_venv_modified": False,
    }
    print("MYAI_ISOLATED_VOICE_NATIVE_IMPORT_JSON=" + json.dumps(result, sort_keys=True))
    # A known native missing library is informative NO-GO, not a claim of
    # successful import, and does not require stopping the installed service.
    return 0 if valid and result["all_imports_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
