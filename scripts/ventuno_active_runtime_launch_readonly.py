"""Read-only active service entrypoint inventory, privacy-redacted.

This is NOT an attestation of effective settings already held in memory:
even an identical checked-in file might have changed after process start.
Only MainPID numeric systemd metadata, bounded /proc/<pid>/cmdline and a
bounded file hash are inspected. Never print argv, environment or paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

INSTALLED = Path("/home/arduino/MyAI")
UNIT = "myai-ventuno.service"
SOURCE = Path(__file__).resolve().parents[1]
MAX_SCRIPT_BYTES = 128 * 1024
MAX_CMDLINE_BYTES = 4096
PYTHON_CANDIDATES = {
    "/usr/bin/python3", "/usr/bin/python3.12",
    "/home/arduino/MyAI/.venv/bin/python",
    "/home/arduino/MyAI/.venv/bin/python3",
    "/home/arduino/MyAI/.venv/bin/python3.12",
}
SCRIPT_REL = Path("scripts/ventuno_runtime.py")


def _is_known_invocation(raw: bytes) -> bool:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_CMDLINE_BYTES:
        return False
    if not raw.endswith(b"\x00"):
        return False
    try:
        parts = [item.decode("utf-8") for item in raw.split(b"\x00")[:-1]]
    except UnicodeDecodeError:
        return False
    if not parts or parts[0] not in PYTHON_CANDIDATES:
        return False
    # No -c, no standalone unknown module or script and no extra arguments
    # except an explicitly permitted -B interpreter flag.
    args = parts[1:]
    if args[:1] == ["-B"]:
        args = args[1:]
    return args in (
        ["-m", "scripts.ventuno_runtime"],
        [str(INSTALLED / SCRIPT_REL)],
    )


def _file_digest(path):
    try:
        if path.is_symlink() or not path.is_file():
            return None
        if path.stat().st_size <= 0 or path.stat().st_size > MAX_SCRIPT_BYTES:
            return None
        data = path.read_bytes()
        if not data or len(data) > MAX_SCRIPT_BYTES:
            return None
        return hashlib.sha256(data).digest()
    except (OSError, ValueError):
        return None


def classify(pid_output, cmdline, checked_digest, installed_digest):
    try:
        pid_valid = bool(re.fullmatch(r"[1-9]\d{0,8}", pid_output.strip()))
    except (TypeError, AttributeError):
        pid_valid = False
    known = pid_valid and _is_known_invocation(cmdline)
    match = (
        known and isinstance(checked_digest, bytes)
        and len(checked_digest) == 32
        and installed_digest == checked_digest
    )
    return {
        "status": (
            "installed-launch-shape-candidate-not-runtime-attestation"
            if match else "blocked-active-launch-or-code-unverified"
        ),
        "service_main_pid_valid": pid_valid,
        "service_invocation_known": bool(known),
        "installed_runtime_source_matches_exact_checkout": bool(match),
        "effective_live_settings_attested": False,
        "live_memory_settings_confirmed": False,
        "production_service_restart_performed": False,
        "production_config_changed": False,
        "secrets_or_raw_argv_printed": False,
        "hardware_test_authorized": False,
    }


def inspect(*, board=False, runner=None, proc_root=Path("/proc"),
            installed=INSTALLED, source=SOURCE):
    # Default source-only behavior does not inspect running services.
    if not board:
        return classify(None, None, None, None)
    runner = runner or subprocess.run
    try:
        result = runner(
            ["systemctl", "show", UNIT, "--property=MainPID", "--value"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, check=False, timeout=5,
        )
        pid = result.stdout.strip() if result.returncode == 0 else ""
        if not re.fullmatch(r"[1-9]\d{0,8}", pid):
            return classify(pid, None, None, None)
        path = proc_root / pid / "cmdline"
        with path.open("rb") as stream:
            raw = stream.read(MAX_CMDLINE_BYTES + 1)
        checked = _file_digest(source / SCRIPT_REL)
        installed_hash = _file_digest(installed / SCRIPT_REL)
        return classify(pid, raw, checked, installed_hash)
    except (OSError, TypeError, ValueError, subprocess.TimeoutExpired):
        return classify(None, None, None, None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board-readonly", action="store_true")
    args = parser.parse_args(argv)
    result = inspect(board=args.board_readonly)
    print("MYAI_ACTIVE_RUNTIME_LAUNCH_JSON=" + json.dumps(result, sort_keys=True))
    # Diagnostics can complete successfully with blocked service provenance;
    # a diagnostic SUCCESS never means approval to run production voice.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
