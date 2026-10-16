"""Isolated *real native-import* compatibility smoke checks; never open devices.

This is only for a temporary Python 3.12 virtualenv inside a private Actions
runner scratch tree AFTER all signed-off wheels have been hash-verified.
It uses separate bounded child processes, strips model network environment,
cannot record/play audio and never loads or downloads model weights.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys

MODULES = (
    "numpy", "ctranslate2", "av", "faster_whisper",
    "sounddevice", "webrtcvad", "pyttsx3",
)
DISTS = ("numpy", "ctranslate2", "av", "faster-whisper",
         "sounddevice", "webrtcvad-wheels", "pyttsx3")
VERSION = re.compile(r"[A-Za-z0-9_.+!\-]{1,64}\Z")
CHILD = (
    "import importlib,sys\n"
    "mod=sys.argv[1]\n"
    "if mod=='sounddevice' and len(sys.argv)>2:\n"
    " import ctypes,ctypes.util,os\n"
    " native=os.path.join(os.environ['LD_LIBRARY_PATH'],'libportaudio.so.2')\n"
    " try:\n"
    "  ctypes.CDLL(native,mode=ctypes.RTLD_GLOBAL)\n"
    " except OSError as exc:\n"
    "  reason=str(exc).lower()\n"
    "  if 'libjack' in reason: print('MISSING_JACK_LIBRARY')\n"
    "  elif 'libpulse' in reason: print('MISSING_PULSE_LIBRARY')\n"
    "  elif 'libasound' in reason: print('MISSING_ALSA_LIBRARY')\n"
    "  elif 'libportaudio' in reason: print('MISSING_PORTAUDIO_LIBRARY')\n"
    "  else: print('STAGED_PORTAUDIO_LINK_FAILED')\n"
    "  sys.exit(47)\n"
    " original=ctypes.util.find_library\n"
    " ctypes.util.find_library=lambda name: 'libportaudio.so.2' if name=='portaudio' else original(name)\n"
    "try:\n"
    " importlib.import_module(mod)\n"
    "except BaseException as exc:\n"
    " reason=str(exc).lower()\n"
    " if 'libjack' in reason: print('MISSING_JACK_LIBRARY')\n"
    " elif 'libpulse' in reason: print('MISSING_PULSE_LIBRARY')\n"
    " elif 'libasound' in reason: print('MISSING_ALSA_LIBRARY')\n"
    " elif 'portaudio' in reason: print('MISSING_PORTAUDIO_LIBRARY')\n"
    " elif 'libstdc++' in reason: print('MISSING_STDCXX_LIBRARY')\n"
    " else: print('NATIVE_IMPORT_FAILED')\n"
    " sys.exit(47)\n"
    "print('ISOLATED_NATIVE_IMPORT_OK')"
)


def isolated_prefix(*, staging_root: Path, executable=None):
    """Require an actually isolated venv, never the installed MyAI runtime."""
    executable = Path(executable or sys.executable)
    try:
        root = staging_root.resolve(strict=True)
        prefix = Path(sys.prefix).resolve(strict=True)
        binfile = executable.absolute()  # venv Python may symlink to system CPython
        return bool(
            root.is_dir()
            and prefix.is_relative_to(root)
            and binfile.is_relative_to(prefix)
            and prefix != Path(sys.base_prefix).resolve()
            and not str(prefix).startswith("/home/arduino/MyAI")
            and (prefix / "pyvenv.cfg").is_file()
            and sys.version_info[:2] == (3, 12)
        )
    except (OSError, ValueError):
        return False


def _private_portaudio_dir(root, directory):
    if directory is None:
        return None
    try:
        root = Path(root).resolve(strict=True)
        directory = Path(directory).resolve(strict=True)
        shared = directory / "libportaudio.so.2"
        if (not directory.is_relative_to(root) or not directory.is_dir()
                or not shared.is_file() or shared.is_symlink()
                or not 1 <= shared.stat().st_size <= 20_000_000):
            return None
        with shared.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                return None
        return directory
    except (OSError, ValueError):
        return None


def inspect(staging_root, *, runner=None, metadata=None,
            prefix_check=None, portaudio_directory=None):
    runner = subprocess.run if runner is None else runner
    metadata = importlib.metadata.version if metadata is None else metadata
    safe = (
        isolated_prefix(staging_root=Path(staging_root))
        if prefix_check is None else bool(prefix_check)
    )
    statuses = {module: False for module in MODULES}
    reasons = {module: "not-tested" for module in MODULES}
    versions = {}
    portaudio_dir = _private_portaudio_dir(staging_root, portaudio_directory)
    if portaudio_directory is not None and portaudio_dir is None:
        return _result(statuses, versions, False, reasons, False)
    if not safe:
        return _result(statuses, versions, safe, reasons, portaudio_dir is not None)
    env = {
        "PATH": "/usr/bin:/bin", "HOME": str(staging_root),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1", "CUDA_VISIBLE_DEVICES": "",
    }
    if portaudio_dir is not None:
        # Strictly inside disposable child process. Do NOT affect parent,
        # OS ldconfig, production Python, driver, or systemd.
        env["LD_LIBRARY_PATH"] = str(portaudio_dir)
    for dist in DISTS:
        try:
            version = metadata(dist)
            versions[dist] = version if isinstance(version, str) and VERSION.fullmatch(version) else None
        except Exception:
            versions[dist] = None
    for module in MODULES:
        try:
            process = runner(
                [sys.executable, "-I", "-B", "-c", CHILD, module] +
                (["USE_PRIVATE_PORTAUDIO"] if module == "sounddevice"
                 and portaudio_dir is not None else []),
                cwd=str(staging_root),
                env=env,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, check=False, timeout=12,
            )
            ok = bool(process.returncode == 0 and
                      process.stdout.strip() == "ISOLATED_NATIVE_IMPORT_OK")
            statuses[module] = ok
            categories = {
                "MISSING_PORTAUDIO_LIBRARY": "missing-portaudio-shared-library",
                "MISSING_JACK_LIBRARY": "missing-jack-shared-library",
                "MISSING_PULSE_LIBRARY": "missing-pulse-shared-library",
                "STAGED_PORTAUDIO_LINK_FAILED": "staged-portaudio-native-link-failed",
                "MISSING_ALSA_LIBRARY": "missing-alsa-shared-library",
                "MISSING_STDCXX_LIBRARY": "missing-standard-cxx-shared-library",
            }
            reasons[module] = (
                "ok" if ok else
                categories.get(process.stdout.strip(), "native-import-failed")
            )
        except subprocess.TimeoutExpired:
            statuses[module] = False
            reasons[module] = "native-import-timeout"
        except (OSError, ValueError):
            statuses[module] = False
            reasons[module] = "native-import-unavailable"
    return _result(statuses, versions, safe, reasons, portaudio_dir is not None)


def _result(statuses, versions, isolated, reasons, staged_portaudio):
    all_ok = isolated and all(statuses.values()) and all(
        versions.get(name) is not None for name in DISTS
    )
    return {
        "status": (
            "isolated-native-imports-pass-no-audio"
            if all_ok else "blocked-native-import-or-venv-isolation"
        ),
        "isolated_private_venv_confirmed": isolated,
        "isolated_staged_portaudio_library_used": staged_portaudio,
        "portaudio_installed_in_production": False,
        "per_module_import": statuses,
        "per_module_failure_category": reasons,
        "installed_dist_versions": versions,
        "all_seven_imports_passed": bool(all_ok),
        "microphone_opened": False,
        "speaker_opened": False,
        "model_weights_loaded": False,
        "npu_or_dsp_opened": False,
        "production_packages_modified": False,
        "physical_runtime_compatibility_proven": False,
        "real_audio_authorized": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging-root", required=True, type=Path)
    parser.add_argument("--staged-portaudio-dir", type=Path)
    args = parser.parse_args(argv)
    result = inspect(
        args.staging_root, portaudio_directory=args.staged_portaudio_dir
    )
    print("MYAI_ISOLATED_NATIVE_VOICE_PROBE_JSON=" + json.dumps(result, sort_keys=True))
    return 0 if result["all_seven_imports_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
