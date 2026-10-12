"""Bounded, isolated voice-wheel staging on Arduino VENTUNO Q.

Default: read-only RAM/disk/Python readiness. Explicit --stage-light creates
an ephemeral venv and installs binary wheels for sounddevice, webrtcvad-wheels
and pyttsx3, then imports packages without opening audio devices/engines.
It NEVER loads Whisper STT weights, enables voice, alters the active MyAI venv,
uses privileged system installers, opens microphones, or touches GenieX.

--check-stt-wheels resolves (dry-run only) faster-whisper wheels separately.
The caller must pass a fresh directory inside RUNNER_TEMP and clean it in
an always() CI step. Resource and execution budgets are fail-closed.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

MIN_AVAILABLE_KIB = 1536 * 1024
MIN_DISK_FREE_BYTES = 1536 * 1024 * 1024
STAGING_TIMEOUT_SECONDS = 210
STT_TIMEOUT_SECONDS = 135
LIGHT_WHEELS = (
    "sounddevice>=0.5,<1",
    "webrtcvad-wheels>=2,<3",
    "pyttsx3>=2.90,<3",
)
# faster-whisper 1.2.1 still passes metadata_errors to av.open().
# PyAV 19 removed that argument. Until the next compatible release,
# use an ARM64 PyAV 18.x wheel; see SYSTRAN/faster-whisper issue #1589.
STT_WHEELS = ("faster-whisper>=1,<2", "av>=17,<19")
IMPORTS = ("sounddevice", "webrtcvad", "pyttsx3")
KNOWN_ACTIVE_VENV = Path("/home/arduino/MyAI/.venv")


def mem_available_kib(path: Path = Path("/proc/meminfo")) -> int | None:
    try:
        if path.is_symlink() or path.stat().st_size > 32_768:
            return None
        with path.open("r", encoding="ascii", errors="replace") as stream:
            data = stream.read(32_769)
        if len(data) > 32_768:
            return None
    except OSError:
        return None
    match = re.search(r"^MemAvailable:\s+(\d+)\s+kB\s*$", data, re.M)
    return int(match.group(1)) if match else None


def disk_free_bytes(folder: Path) -> int | None:
    try:
        return shutil.disk_usage(folder).free
    except OSError:
        return None


def preflight(mem_kib: int | None, disk_bytes: int | None,
              *, on_arm: bool) -> dict[str, object]:
    ok_mem = mem_kib is not None and mem_kib >= MIN_AVAILABLE_KIB
    ok_disk = disk_bytes is not None and disk_bytes >= MIN_DISK_FREE_BYTES
    return {
        "status": "staging-eligible" if on_arm and ok_mem and ok_disk
                  else "no-go-voice-staging-resources-or-platform",
        "arm64_verified": on_arm,
        "memory_available_mib": round(mem_kib / 1024) if mem_kib is not None else None,
        "free_disk_mib": round(disk_bytes / (1024 * 1024)) if disk_bytes is not None else None,
        "memory_reserve_threshold_mib": MIN_AVAILABLE_KIB // 1024,
        "disk_reserve_threshold_mib": MIN_DISK_FREE_BYTES // (1024 * 1024),
        "may_stage": on_arm and ok_mem and ok_disk,
        "production_venv_changed": False,
        "microphone_opened": False,
        "whisper_model_downloaded": False,
        "geniex_changed": False,
    }


def fresh_staging_dir(folder: Path, runner_temp: Path) -> bool:
    """Only a new direct child of RUNNER_TEMP, never active or symlinked dirs."""
    try:
        if (folder.exists() or folder.is_symlink()
                or not runner_temp.is_dir() or runner_temp.is_symlink()
                or folder.parent.resolve() != runner_temp.resolve()
                or folder.name not in {"myai-voice-staging", "myai-voice-wheel-report"}
                or KNOWN_ACTIVE_VENV == folder):
            return False
        return True
    except OSError:
        return False


def result_of_command(argv: list[str], *, timeout: int,
                      cwd: Path | None = None,
                      env: dict[str, str] | None = None) -> dict[str, object]:
    """No stderr/stdout or pip paths copied into public output."""
    try:
        completed = subprocess.run(
            argv, cwd=cwd, env=env, check=False,
            timeout=timeout, capture_output=True, text=True,
            errors="replace",
        )
        return {
            "completed": True,
            "exit_zero": completed.returncode == 0,
            "exit_code": completed.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"completed": False, "exit_zero": False, "error": "timeout"}
    except OSError:
        return {"completed": False, "exit_zero": False, "error": "os-error"}



def import_probe(python: Path, module: str, folder: Path,
                 env: dict[str, str]) -> dict[str, object]:
    """Import one allowlisted package, expose error category, never raw output."""
    if module not in IMPORTS:
        raise ValueError("invalid-optional-module")
    try:
        run = subprocess.run(
            [str(python), "-I", "-c", "import " + module],
            cwd=folder, env=env, check=False,
            capture_output=True, text=True, errors="replace", timeout=18,
        )
    except subprocess.TimeoutExpired:
        return {"importable": False, "failure": "import-timeout"}
    except OSError:
        return {"importable": False, "failure": "import-os-error"}
    if run.returncode == 0:
        return {"importable": True, "failure": None}
    # Never publish raw stack traces/paths; extract only known categorical
    # exception kinds and bounded safe library/module basenames.
    tail = run.stderr[-3000:]
    kinds = re.findall(
        r"(?m)^(ModuleNotFoundError|ImportError|OSError|RuntimeError|"
        r"AttributeError|TypeError|ValueError):", tail,
    )
    libraries = re.findall(
        r"lib[a-zA-Z0-9_+.-]{1,65}[.]so(?:[.][0-9]{1,2}){0,3}",
        tail,
    )
    missing = re.findall(
        r"No module named ['\"]([a-zA-Z_][a-zA-Z0-9_.]{0,65})['\"]",
        tail,
    )
    return {
        "importable": False,
        "failure": kinds[-1] if kinds else "unknown-import-error",
        "missing_library": libraries[-1] if libraries else None,
        "missing_module": missing[-1] if missing else None,
    }


def stage_light_voice(python: Path, folder: Path,
                      runner_temp: Path,
                      *, check_stt_wheels: bool = False,
                      allow_missing_portaudio: bool = False) -> dict[str, object]:
    availability = preflight(
        mem_available_kib(), disk_free_bytes(runner_temp),
        on_arm=platform.machine().lower() in {"aarch64", "arm64"},
    )
    report: dict[str, object] = {
        **availability,
        "light_wheels_installed": False,
        "light_imports_verified": False,
        "stt_wheel_resolution_verified": False,
        "stt_model_loaded": False,
        "stage_directory_isolated": False,
    }
    if not report["may_stage"]:
        return report
    if not fresh_staging_dir(folder, runner_temp):
        report["status"] = "reject-unsafe-or-existing-stage"
        return report
    if not python.is_file() or python.is_symlink() or not os.access(python, os.X_OK):
        report["status"] = "reject-python-executable"
        return report
    env = os.environ.copy()
    env.update({
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INPUT": "1",
        "PIP_NO_CACHE_DIR": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    })
    # The isolated environment owns the only created files, not project-root.
    make = result_of_command(
        [str(python), "-m", "venv", str(folder)],
        timeout=45, cwd=runner_temp, env=env,
    )
    report["venv_created"] = bool(make["exit_zero"])
    if not make["exit_zero"]:
        report["status"] = "isolated-venv-unavailable"
        return report
    sandbox_py = folder / "bin" / "python"
    sandbox_pip = [str(sandbox_py), "-m", "pip"]
    if not sandbox_py.is_file() or not sandbox_py.resolve().is_file():
        report["status"] = "isolated-python-missing"
        return report
    report["stage_directory_isolated"] = True
    wheels = result_of_command(
        sandbox_pip + [
            "install", "--only-binary=:all:", "--disable-pip-version-check",
            "--no-cache-dir", "--no-input", "--retries", "1",
            "--timeout", "12", "--progress-bar", "off", *LIGHT_WHEELS,
        ],
        timeout=STAGING_TIMEOUT_SECONDS, cwd=runner_temp, env=env,
    )
    report["light_wheels_installed"] = bool(wheels["exit_zero"])
    if not wheels["exit_zero"]:
        report["status"] = "light-wheel-install-unavailable"
        return report
    # Imports occur in separate bounded subprocesses, without any audio
    # stream, speech engine initialization, or model download.
    module_results = {
        module: import_probe(sandbox_py, module, runner_temp, env)
        for module in IMPORTS
    }
    report["module_imports"] = module_results
    report["light_imports_verified"] = all(
        result["importable"] for result in module_results.values()
    )
    if not report["light_imports_verified"]:
        missing = {
            name for name, outcome in module_results.items()
            if not outcome["importable"]
        }
        if (allow_missing_portaudio and missing == {"sounddevice"}
                and module_results["sounddevice"]["failure"] == "OSError"):
            report["status"] = "light-packages-require-optional-PortAudio-runtime"
            return report
        report["status"] = "light-import-check-failed"
        return report
    report["status"] = "light-voice-packages-import-in-isolation"
    if check_stt_wheels:
        # Dry-run resolution only; no Whisper model weights, no STT import.
        location = runner_temp / "myai-voice-wheel-report"
        if not fresh_staging_dir(location, runner_temp):
            report["status"] = "stt-report-directory-unsafe"
            return report
        location.mkdir(mode=0o700)
        outcome = result_of_command(
            sandbox_pip + [
                "install", "--dry-run", "--ignore-installed",
                "--only-binary=:all:", "--no-cache-dir", "--no-input",
                "--retries", "1", "--timeout", "12", "--progress-bar", "off",
                "--report", str(location / "pip-report.json"), *STT_WHEELS,
            ],
            timeout=STT_TIMEOUT_SECONDS, cwd=runner_temp, env=env,
        )
        report["stt_wheel_resolution_verified"] = bool(outcome["exit_zero"])
        report["stt_wheel_resolution_status"] = (
            "aarch64-wheels-resolved-without-installing"
            if outcome["exit_zero"] else "wheel-resolution-unavailable"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-light", action="store_true",
                        help="Install small voice wheels only to a disposable separate venv")
    parser.add_argument("--allow-missing-portaudio", action="store_true",
                        help="Permit known PortAudio OSError for separate temp-only staging")
    parser.add_argument("--check-stt-wheels", action="store_true",
                        help="Dry-run faster-whisper wheel resolution only, no STT weights")
    parser.add_argument("--runner-temp", type=Path,
                        default=Path(os.environ.get("RUNNER_TEMP", "/tmp")))
    parser.add_argument("--python", type=Path, default=Path("/usr/bin/python3"))
    args = parser.parse_args()
    if args.check_stt_wheels and not args.stage_light:
        parser.error("--check-stt-wheels requires --stage-light")
    if not args.stage_light:
        report = preflight(
            mem_available_kib(), disk_free_bytes(args.runner_temp),
            on_arm=platform.machine().lower() in {"aarch64", "arm64"},
        )
        print("VENTUNO voice staging preflight:", json.dumps(report, sort_keys=True))
        return 0
    folder = args.runner_temp / "myai-voice-staging"
    outcome = stage_light_voice(
        args.python, folder, args.runner_temp,
        check_stt_wheels=args.check_stt_wheels,
        allow_missing_portaudio=args.allow_missing_portaudio,
    )
    print("VENTUNO isolated voice wheel staging:",
          json.dumps(outcome, sort_keys=True))
    print("No microphone opened, Whisper weights downloaded, or production venv changed.")
    successful = outcome["status"] == "light-voice-packages-import-in-isolation"
    recognized_gap = (
        args.allow_missing_portaudio and
        outcome["status"] == "light-packages-require-optional-PortAudio-runtime"
    )
    return 0 if successful or recognized_gap else 2


if __name__ == "__main__":
    raise SystemExit(main())
