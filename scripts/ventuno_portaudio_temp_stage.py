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
import re
import shutil
import subprocess
from pathlib import Path

from scripts.ventuno_stage_paths import authorized_cli_stage, safe_scratch_root

MAX_DEB_BYTES = 3 * 1024 * 1024
ALLOWED_PACKAGES = ("libportaudio2", "libjack-jackd2-0")
APT_TIMEOUT = 90
DPKG_TIMEOUT = 30


def valid_package(path: Path, root: Path, package: str = "libportaudio2") -> bool:
    if package not in ALLOWED_PACKAGES:
        return False
    try:
        return (
            path.parent.resolve() == root.resolve()
            and not path.is_symlink()
            and path.is_file()
            and path.name.startswith(package + "_")
            and path.name.endswith("_arm64.deb")
            and 0 < path.stat().st_size <= MAX_DEB_BYTES
        )
    except OSError:
        return False


def extracted_library(root: Path, name: str = "libportaudio.so.2") -> Path | None:
    if name not in ("libportaudio.so.2", "libjack.so.0"):
        return None
    lib = root / "usr" / "lib" / "aarch64-linux-gnu" / name
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
                env: dict[str, str] | None = None,
                safe_error_hint: bool = False) -> dict[str, object]:
    try:
        result = subprocess.run(
            argv, cwd=cwd, env=env, check=False,
            capture_output=True, text=True, errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "reason": "timeout"}
    except OSError:
        return {"success": False, "reason": "os-error"}
    report: dict[str, object] = {
        "success": result.returncode == 0, "exit_code": result.returncode
    }
    if safe_error_hint and result.returncode:
        stderr = result.stderr[-2500:]
        errors = re.findall(
            r"(?m)^(OSError|ImportError|ModuleNotFoundError|RuntimeError):",
            stderr,
        )
        shared = re.findall(
            r"lib[a-zA-Z0-9_+.-]{1,65}[.]so(?:[.][0-9]{1,2}){0,3}",
            stderr,
        )
        report["import_exception"] = errors[-1] if errors else "unknown"
        report["missing_shared_library"] = shared[-1] if shared else None
        report["portaudio_text_mentioned"] = "portaudio" in stderr.lower()
    return report


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
    if (not safe_scratch_root(runner_temp)
            or folder.exists() or folder.is_symlink() or folder.name != "myai-voice-portaudio"
            or folder.parent.resolve() != runner_temp.resolve()
            or not sandbox_python.is_file()
            or not Path(os.path.abspath(sandbox_python)).is_relative_to(runner_temp.resolve())
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
    # libjack.so.0 was separately identified missing in the first isolated
    # PortAudio attempt. Fetch only these two allowlisted distro packages;
    # never install them globally, and refuse unforeseen dependencies.
    dest = folder / "extracted"
    dest.mkdir(mode=0o700)
    for pkg in ALLOWED_PACKAGES:
        fetched = run_bounded(
            [apt, "download", pkg],
            cwd=folder, timeout=APT_TIMEOUT, env=env,
        )
        if not fetched["success"]:
            report["status"] = "no-go-official-distro-audio-download"
            return report
        packages = list(folder.glob(pkg + "_*_arm64.deb"))
        if len(packages) != 1 or not valid_package(packages[0], folder, pkg):
            report["status"] = "no-go-unsupported-audio-package"
            return report
        info = run_bounded(
            [dpkg, "--field", str(packages[0]), "Architecture"],
            cwd=folder, timeout=10, env=env,
        )
        if not info["success"]:
            report["status"] = "no-go-deb-architecture-unreadable"
            return report
        expanded = run_bounded(
            [dpkg, "--extract", str(packages[0]), str(dest)],
            cwd=folder, timeout=DPKG_TIMEOUT, env=env,
        )
        if not expanded["success"]:
            report["status"] = "no-go-audio-extract"
            return report
    library = extracted_library(dest)
    jack = extracted_library(dest, "libjack.so.0")
    if library is None or jack is None:
        report["status"] = "no-go-required-audio-libraries-unavailable"
        return report
    report["jack_extracted_only_in_runner_temp"] = True
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
        cwd=runner_temp, timeout=20, env=env, safe_error_hint=True,
    )
    report["sounddevice_import_with_isolated_portaudio"] = bool(
        outcome["success"]
    )
    if not outcome["success"]:
        report["import_exception"] = outcome.get("import_exception")
        report["missing_shared_library"] = outcome.get("missing_shared_library")
        report["portaudio_text_mentioned"] = outcome.get("portaudio_text_mentioned")
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
    if not authorized_cli_stage(args.runner_temp):
        print("Temporary PortAudio ARM64 compatibility:",
              json.dumps({"status": "no-go-unverified-ci-stage",
                          "sounddevice_import_with_isolated_portaudio": False}))
        return 2
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
