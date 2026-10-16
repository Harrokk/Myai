"""Safe installed-venv package inventory; NO imports of native/audio packages.

Data can be used to plan a pinned wheelhouse, but not as permission to run
audio, install packages, profile an NPU or alter production.
"""
from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import re

VOICE_DISTRIBUTIONS = {
    "sounddevice": "sounddevice",
    "webrtcvad": "webrtcvad-wheels",
    "faster_whisper": "faster-whisper",
    "pyttsx3": "pyttsx3",
}
TRANSITIVE = ("ctranslate2", "numpy", "av", "tokenizers", "huggingface-hub")


def _version(value):
    if (type(value) is not str or len(value) > 64
            or re.fullmatch(r"[A-Za-z0-9_.+!\-]+", value) is None):
        return None
    return value


def inspect(spec_finder=None, version_reader=None):
    spec_finder = spec_finder or importlib.util.find_spec
    version_reader = version_reader or importlib.metadata.version
    found = {}
    packages = {}
    for module, dist in VOICE_DISTRIBUTIONS.items():
        try:
            found[module] = spec_finder(module) is not None
        except (ImportError, ValueError, AttributeError, OSError):
            found[module] = False
        try:
            version = _version(version_reader(dist))
        except (importlib.metadata.PackageNotFoundError, ValueError,
                TypeError, OSError):
            version = None
        packages[module] = version
    for dist in TRANSITIVE:
        try:
            packages[dist] = _version(version_reader(dist))
        except (importlib.metadata.PackageNotFoundError, ValueError,
                TypeError, OSError):
            packages[dist] = None
    all_present = all(found.values()) and all(
        packages[k] is not None for k in VOICE_DISTRIBUTIONS
    )
    return {
        "status": ("metadata-voice-dependencies-listed"
                   if all_present else "blocked-voice-dependencies-incomplete"),
        "voice_import_specs_found": found,
        "installed_distribution_versions": packages,
        "all_four_top_level_requirements_present": all_present,
        "native_audio_backend_abi_verified": False,
        "model_artifacts_and_hashes_verified": False,
        "dependency_wheel_hashes_locked": False,
        "model_loaded": False,
        "packages_installed_by_this_check": False,
        "voice_execution_authorized": False,
        "npu_executed": False,
    }


def main():
    result = inspect()
    print("MYAI_VOICE_DEPENDENCY_INVENTORY_JSON=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
