"""Limited native ABI import sanity check for a DISPOSABLE voice venv.

Import packages only; no recording/playback, no model initialization, NPU,
network calls or service changes. This never calls sounddevice devices/stream
methods, pyttsx3.init(), WhisperModel(), or inference.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import re
import sys

REQUIRED_MODULES = ("numpy", "av", "ctranslate2", "webrtcvad",
                    "sounddevice", "pyttsx3", "faster_whisper")
DISTRIBUTIONS = ("numpy", "av", "ctranslate2", "webrtcvad-wheels",
                 "sounddevice", "pyttsx3", "faster-whisper")
REDACT_VERSION = re.compile(r"[a-zA-Z0-9_.!+\-]{1,64}\Z")


def preflight(*, venv_prefix=None, imports=None, lookup=None):
    imports = imports or importlib.import_module
    lookup = lookup or importlib.metadata.version
    venv_prefix = venv_prefix or sys.prefix
    isolated = (
        type(venv_prefix) is str
        and bool(os.environ.get("VIRTUAL_ENV"))
        and os.path.realpath(os.environ["VIRTUAL_ENV"])
        == os.path.realpath(venv_prefix)
        and os.path.realpath(venv_prefix) != os.path.realpath(sys.base_prefix)
        and "/MyAI/.venv" not in os.path.realpath(venv_prefix)
    )
    results = {}
    versions = {}
    if isolated:
        for name in REQUIRED_MODULES:
            try:
                imports(name)
                results[name] = True
            except (Exception, SystemExit):
                results[name] = False
        for name in DISTRIBUTIONS:
            try:
                version = lookup(name)
                versions[name] = version if (
                    type(version) is str and REDACT_VERSION.fullmatch(version)
                ) else None
            except (Exception, SystemExit):
                versions[name] = None
    all_imported = bool(isolated and len(results) == len(REQUIRED_MODULES)
                        and all(results.values()) and all(versions.values()))
    return {
        "status": ("disposable-native-import-check-passed"
                   if all_imported else "blocked-disposable-voice-native-import"),
        "temporary_venv_confirmed": bool(isolated),
        "imports_passed": dict(sorted(results.items())),
        "verified_distribution_count": sum(bool(v) for v in versions.values()),
        "model_instantiated": False,
        "microphone_or_speaker_opened": False,
        "service_modified": False,
        "npu_executed": False,
        "production_venv_modified": False,
        "real_audio_authorized": False,
    }


def main():
    result = preflight()
    print("MYAI_VOICE_NATIVE_IMPORT_JSON=" + json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "disposable-native-import-check-passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
