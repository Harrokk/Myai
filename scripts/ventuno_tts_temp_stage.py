"""Ephemeral eSpeak NG Swedish TTS on VENTUNO ARM64, no audio playback.

Download ONLY allowlisted Ubuntu distro .deb packages; unpack via dpkg-deb
in runner temporary storage without sudo, dpkg --install, apt install or
system mutations. Synthesize a fixed sentence into an in-memory WAV and
discard the audio after aggregate signal analysis. No microphone, speaker,
user text, model inference, or change to MyAI/GenieX services.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from scripts.ventuno_tts_synthesis_probe import (
    PHRASE, TIMEOUT_SECONDS, MAX_WAV_BYTES, validate_wav,
)

PACKAGES = ("espeak-ng-data", "libespeak-ng1", "espeak-ng")
MAX_PACKAGE_BYTES = 18 * 1024 * 1024
MIN_RAM_AVAILABLE_KIB = 1024 * 1024
MIN_DISK_AVAILABLE_BYTES = 150 * 1024 * 1024
PACKAGE_TIMEOUT = 75


def safe_deb(path: Path, folder: Path, name: str) -> bool:
    if name not in PACKAGES:
        return False
    try:
        return (path.is_file() and not path.is_symlink()
                and path.parent.resolve() == folder.resolve()
                and path.name.startswith(name + "_")
                and (path.name.endswith("_arm64.deb") or
                     path.name.endswith("_all.deb"))
                and 0 < path.stat().st_size <= MAX_PACKAGE_BYTES)
    except OSError:
        return False


def staging_allowed(folder: Path, root: Path, *, arm: bool) -> bool:
    try:
        return (arm and root.is_dir() and not root.is_symlink()
                and folder.name == "myai-tts-espeak-stage"
                and folder.parent.resolve() == root.resolve()
                and not folder.exists() and not folder.is_symlink()
                and shutil.which("apt") is not None
                and shutil.which("dpkg-deb") is not None
                and shutil.disk_usage(root).free >= MIN_DISK_AVAILABLE_BYTES)
    except OSError:
        return False


def run_command(args: list[str], cwd: Path, *, timeout: int,
                env: dict[str, str] | None = None) -> dict[str, object]:
    try:
        proc = subprocess.run(
            args, cwd=cwd, env=env, capture_output=True,
            check=False, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout"}
    except OSError:
        return {"ok": False, "reason": "launch-error"}
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        # Raw stdout and stderr are intentionally never reported.
        "stdout": proc.stdout if proc.returncode == 0 else b"",
    }


def espeak_paths(root: Path) -> tuple[Path | None, Path | None]:
    extracted = root / "extracted"
    exe = extracted / "usr" / "bin" / "espeak-ng"
    data = extracted / "usr" / "share" / "espeak-ng-data"
    try:
        if (exe.is_symlink() or not exe.is_file()
                or not exe.resolve().is_relative_to(extracted.resolve())
                or data.is_symlink() or not data.is_dir()
                or not data.resolve().is_relative_to(extracted.resolve())):
            return None, None
        return exe, data
    except OSError:
        return None, None


def stage_sweden_tts(folder: Path, runner_temp: Path,
                     *, arm: bool | None = None) -> dict[str, object]:
    arm_ok = (platform.machine().lower() in ("aarch64", "arm64")
              if arm is None else arm)
    report: dict[str, object] = {
        "status": "no-go-isolated-swedish-tts",
        "arm64_verified": arm_ok,
        "packages_extracted_in_runner_temp": False,
        "synthesis_in_memory_attempted": False,
        "swedish_pcm_synthesis_verified": False,
        "physical_playback_verified": False,
        "microphone_used": False,
        "audio_written_to_disk": False,
        "system_packages_installed": False,
        "production_venv_changed": False,
        "services_changed": False,
    }
    if not staging_allowed(folder, runner_temp, arm=arm_ok):
        report["status"] = "no-go-runner-temp-or-package-tool"
        return report
    folder.mkdir(mode=0o700)
    extracted = folder / "extracted"
    extracted.mkdir(mode=0o700)
    apt = shutil.which("apt")
    dpkg = shutil.which("dpkg-deb")
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    for name in PACKAGES:
        downloaded = run_command(
            [apt, "download", name], folder,
            timeout=PACKAGE_TIMEOUT, env=env,
        )
        if not downloaded["ok"]:
            report["status"] = "no-go-distro-package-unavailable"
            report["failed_package"] = name
            return report
        found = list(folder.glob(name + "_*.deb"))
        if len(found) != 1 or not safe_deb(found[0], folder, name):
            report["status"] = "no-go-unexpected-deb-identity-or-size"
            return report
        version = run_command(
            [dpkg, "--field", str(found[0]), "Architecture"],
            folder, timeout=10, env=env,
        )
        if not version["ok"] or version["stdout"].strip() not in (b"arm64", b"all"):
            report["status"] = "no-go-deb-architecture"
            return report
        out = run_command(
            [dpkg, "--extract", str(found[0]), str(extracted)],
            folder, timeout=30, env=env,
        )
        if not out["ok"]:
            report["status"] = "no-go-distro-package-extract"
            return report
    exe, data = espeak_paths(folder)
    if exe is None or data is None:
        report["status"] = "no-go-espeak-cli-or-voice-data-missing"
        return report
    report["packages_extracted_in_runner_temp"] = True
    env["LD_LIBRARY_PATH"] = str(extracted / "usr" / "lib" / "aarch64-linux-gnu") + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    # --path expects the directory that CONTAINS espeak-ng-data.
    argv = [
        str(exe), "--path=" + str(data.parent),
        "-v", "sv", "--stdout", PHRASE,
    ]
    report["synthesis_in_memory_attempted"] = True
    synth = run_command(argv, folder, timeout=TIMEOUT_SECONDS, env=env)
    if not synth["ok"]:
        report["status"] = "inconclusive-espeak-runtime"
        return report
    raw = synth["stdout"]
    if len(raw) > MAX_WAV_BYTES:
        report["status"] = "no-go-espeak-output-over-limit"
        return report
    result = validate_wav(raw)
    report["sample_rate_hz"] = result["sample_rate_hz"]
    report["duration_seconds"] = result["duration_seconds"]
    report["rms_fraction_full_scale"] = result["rms_fraction_full_scale"]
    report["swedish_pcm_synthesis_verified"] = bool(result["signal_verified"])
    report["status"] = (
        "isolated-swedish-tts-signal-verified"
        if result["signal_verified"] else "inconclusive-synthetic-wav"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp", required=True, type=Path)
    args = parser.parse_args()
    result = stage_sweden_tts(
        args.runner_temp / "myai-tts-espeak-stage", args.runner_temp
    )
    print("VENTUNO ephemeral Swedish eSpeak NG TTS:", json.dumps(result, sort_keys=True))
    print("No playback, microphone recording, OS package installation or service modifications.")
    return 0 if result["swedish_pcm_synthesis_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
