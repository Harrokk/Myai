"""Stage distro PortAudio runtime inside an ephemeral VENTUNO CI directory.

No sudo, apt install, dpkg --install, system package mutation, or microphone.
Uses configured distribution metadata via apt download libportaudio2,
verifies an arm64 .deb, extracts only to RUNNER_TEMP and validates an isolated
sounddevice import with the unpacked shared library. Never deploys to MyAI.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

MAX_DEB_BYTES = 3 * 1024 * 1024
APT_TIMEOUT = 90
DPKG_TIMEOUT = 30


def valid_package(path: Path, root: Path) -> bool:
    try:
        return (
            path.parent.resolve() == root.resolve()
            and not path.is_symlink()
            and path.is_file()
            and path.name.startswith("libportaudio2_")
            and path.name.endswith("_arm64.deb")
            and 0 < path.stat().st_size <= MAX_DEB_BYTES
        )
    except OSError:
        return False


def extracted_library(root: Path) -> Path | None:
    lib = root / "usr" / "lib" / "aarch64-linux-gnu" / "libportaudio.so.2"
    try:
        resolved = lib.resolve(strict=True)
        if (
            resolved.is_file()
            and resolved.is_relative_to(root.resolve())
            and resolved.stat().st_size <= MAX_DEB_BYTES
        ):
            return resolved
    except OSError:
        pass
    return None


def run_bounded(argv: list[str], *, cwd: Path, timeout: int,
                env: dict[str, str] | None = None) -> dict[str, object]:
    try:
        result = subprocess.run(
            argv, cwd=cwd, env=env, check=False,
            capture_output=True, text=True, errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "reason": "timeout"}
    except OSError:
        return {"success": False, "reason": "os-error"}
    return {"success": result.returncode == 0,
            "exit_code": result.returncode}


def stage_portaudio_for_import(
    sandbox_python: Path, folder: Path, runner_temp: Path,
    *,
    arm: bool | None = None,
) -> dict[str, object]:
    allowed_arch = platform.machine().lower() in ("aarch64", "arm64")
    if arm is not None:
        allowed_arch = arm
    report: dict[str, object] = {
        "status": "no-go-distro-portaudio-staging",
        "arm64_verified": allowed_arch,
        "portaudio_extracted_only_in_runner_temp": False,
        "sounddevice_import_with_isolated_portaudio": False,
        "system_packages_installed": False,
        "production_venv_changed": False,
        "audio_stream_opened": False,
        "services_modified": False,
    }
    if not allowed_arch:
        return report
    if (folder.exists() or folder.is_symlink() or folder.name != "myai-voice-portaudio"
            or folder.parent.resolve() != runner_temp.resolve()
            or not sandbox_python.is_file()
            or not shutil.which("apt")
            or not shutil.which("dpkg-deb")):
        report["status"] = "no-go-staging-tools-or-path"
        return report
    folder.mkdir(mode=0o700)
    apt = shutil.which("apt")
    dpkg = shutil.which("dpkg-deb")
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    # Standard distribution apt configuration and mirrors only. No sudo.
    fetched = run_bounded(
        [apt, "download", "libportaudio2"],
        cwd=folder, timeout=APT_TIMEOUT, env=env,
    )
    if not fetched["success"]:
        report["status"] = "no-go-official-distro-portaudio-download"
        return report
    packages = list(folder.glob("libportaudio2_*_arm64.deb"))
    if len(packages) != 1 or not valid_package(packages[0], folder):
        report["status"] = "no-go-unsupported-portaudio-package"
        return report
    info = run_bounded(
        [dpkg, "--field", str(packages[0]), "Architecture"],
        cwd=folder, timeout=10, env=env,
    )
    if not info["success"]:
        report["status"] = "no-go-deb-architecture-unreadable"
        return report
    # Filename restricts architecture to arm64 and package name exactly.
    dest = folder / "extracted"
    dest.mkdir(mode=0o700)
    expanded = run_bounded(
        [dpkg, "--extract", str(packages[0]), str(dest)],
        cwd=folder, timeout=DPKG_TIMEOUT, env=env,
    )
    if not expanded["success"]:
        report["status"] = "no-go-portaudio-extract"
        return report
    library = extracted_library(dest)
    if library is None:
        report["status"] = "no-go-portaudio-library-unavailable"
        return report
    report["portaudio_extracted_only_in_runner_temp"] = True
    # sounddevice imports ctypes.util.find_library('portaudio'). Patch the
    # resolver only in this throwaway child interpreter, not in source or
    # production. DLL path points to the exact checked temp library.
    program = (
        "import ctypes.util\n"
        "orig=ctypes.util.find_library\n"
        "ctypes.util.find_library=lambda name: " + repr(str(library)) +
        " if name=='portaudio' else orig(name)\n"
        "import sounddevice\n"
    )
    env["LD_LIBRARY_PATH"] = str(library.parent) + os.pathsep + env.get(
        "LD_LIBRARY_PATH", ""
    )
    outcome = run_bounded(
        [str(sandbox_python), "-I", "-c", program],
        cwd=runner_temp, timeout=20, env=env,
    )
    report["sounddevice_import_with_isolated_portaudio"] = bool(
        outcome["success"]
    )
    report["status"] = (
        "sounddevice-imports-with-temporary-portaudio"
        if outcome["success"] else "no-go-temporary-portaudio-dependency"
    )
    return report


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp", type=Path, required=True)
    parser.add_argument("--staged-python", type=Path, required=True)
    args = parser.parse_args()
    result = stage_portaudio_for_import(
        args.staged_python,
        args.runner_temp / "myai-voice-portaudio",
        args.runner_temp,
    )
    print("Temporary PortAudio ARM64 compatibility:",
          json.dumps(result, sort_keys=True))
    return 0 if result["sounddevice_import_with_isolated_portaudio"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
