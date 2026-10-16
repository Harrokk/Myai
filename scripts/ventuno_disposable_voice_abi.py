"""Import-only ARM64 native ABI probe for a disposable voice virtualenv.

Does NOT enumerate audio devices, initialize TTS, load a Whisper model,
connect to GenieX, open ALSA, run NPU, or access production settings.
Use one fixed allowlisted module per disposable child process.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import resource
import sys
import time

MODULES = {
    "av": "av",
    "ctranslate2": "ctranslate2",
    "numpy": "numpy",
    "webrtcvad": "webrtcvad-wheels",
    "sounddevice": "sounddevice",
    "faster_whisper": "faster-whisper",
    "pyttsx3": "pyttsx3",
    "onnxruntime": "onnxruntime",
}


def check(module):
    if module not in MODULES:
        return {"status": "blocked-unknown-module", "module": "unknown",
                "native_abi_import_accepted": False,
                "model_loaded": False, "audio_device_opened": False}
    accepted = False
    installed = False
    error_class = "none"
    start = time.monotonic()
    try:
        # In an isolated subprocess, not the installed production interpreter.
        importlib.import_module(module)
        accepted = True
        importlib.metadata.version(MODULES[module])
        installed = True
    except ImportError:
        accepted = False
        error_class = "python-or-native-module-import-error"
    except OSError:
        accepted = False
        error_class = "native-shared-library-loader-error"
    except (Exception, SystemExit):
        accepted = False
        error_class = "other-sanitized-import-error"
    elapsed = round(max(0, time.monotonic() - start), 3)
    return {
        "status": "module-imported-in-disposable-venv" if accepted
                  else "blocked-native-module-import",
        "module": module,
        "native_abi_import_accepted": accepted,
        "import_failure_category": error_class,
        "installed_version_known": installed,
        "import_seconds": elapsed,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "model_loaded": False,
        "audio_device_opened": False,
        "tts_engine_initialized": False,
        "npu_tested": False,
        "production_configuration_modified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", choices=tuple(MODULES), required=True)
    args = parser.parse_args(argv)
    result = check(args.module)
    print("MYAI_DISPOSABLE_VOICE_ABI_JSON=" + json.dumps(result, sort_keys=True))
    return 0 if result["native_abi_import_accepted"] else 2


if __name__ == "__main__":
    sys.exit(main())
