"""One isolated tiny DLC/QNN HTP attempt on real VENTUNO; no live model changes.

Only SHA-256 verified 16,004-byte synthetic DLC and deterministic 64-byte
input. Requires explicit CI authorization, free RAM, idle GenieX FastRPC,
toolchain and exact CLI flags. Never sudo/restart/stress/record audio.
All model/output files are held in a private RUNNER_TEMP workspace.
"""

import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import tempfile
import time

from scripts.qairt_245_dlc_static_audit import DEFAULT_FIXTURE, verify_fixture
from scripts.prepare_qairt245_native_fixture import native_input
from scripts.ventuno_live_qairt_synthetic_once import available_memory_kib
from scripts.ventuno_geniex_runtime_attestation import (
    main_pid_from_systemd, summarize_service,
)
from scripts.ventuno_qnn_cli_gate import parse_flags
from scripts.ventuno_tiny_qnn_htp_readiness import ROOTS


MIN_AVAILABLE_KIB = 8 * 1048576
INPUT_SHA = "19a0129fd39c4e7495d7c3cc5e9ffe28220d9239ecb945b79d34f714e4ccdb15"
NEEDED = frozenset({
    "--model", "--backend", "--dlc_path", "--input_list",
    "--output_dir", "--use_native_input_files", "--use_native_output_files",
})
LIBS = ("libQnnHtp.so", "libQnnModelDlc.so", "libQnnHtpV75Stub.so")


def _find_libraries():
    """Search fixed SDK roots without following symlinks or printing paths."""
    found = {}
    queue = [(r, 0) for r in ROOTS if r.is_dir() and not r.is_symlink()]
    visited = set()
    while queue and len(visited) < 600 and len(found) < len(LIBS):
        directory, depth = queue.pop(0)
        try:
            info = directory.stat()
            identity = (info.st_dev, info.st_ino)
            if identity in visited:
                continue
            visited.add(identity)
            entries = list(directory.iterdir())[:120]
        except OSError:
            continue
        for file in entries:
            try:
                if file.is_symlink():
                    continue
                if file.is_file() and file.name in LIBS:
                    found[file.name] = file
                elif file.is_dir() and depth < 6:
                    queue.append((file, depth + 1))
            except OSError:
                continue
    return found


def _find_v75_skel_directory():
    """Use only known vendor locations; never copy or modify DSP libraries."""
    roots = (
        Path("/usr/lib/rfsa/adsp"),
        Path("/vendor/dsp"),
        Path("/opt/qcom"),
        Path("/opt/qualcomm"),
        Path("/home/arduino/.local/share/geniex/qairt"),
    )
    queue = [(root, 0) for root in roots if root.is_dir() and not root.is_symlink()]
    count = 0
    while queue and count < 300:
        folder, depth = queue.pop(0)
        count += 1
        try:
            entries = list(folder.iterdir())[:120]
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_file() and entry.name == "libQnnHtpV75Skel.so":
                    return entry.parent
                if entry.is_dir() and depth < 5:
                    queue.append((entry, depth + 1))
            except OSError:
                continue
    return None


def _help_flags(binary):
    try:
        p = subprocess.run(
            [binary, "--help"], capture_output=True, timeout=6,
            text=True, errors="replace", check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    return parse_flags(p.stdout + "\n" + p.stderr) if p.returncode == 0 else frozenset()


def _child_limits():
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024**2, 2 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))


def _output_summary(root):
    folder = root / "results" / "Result_0"
    if not folder.is_dir() or folder.is_symlink():
        return "no_bounded_native_result"
    try:
        raw_files = [x for x in folder.iterdir() if x.suffix == ".raw"
                     and x.is_file() and not x.is_symlink()]
    except OSError:
        return "unreadable_result"
    if len(raw_files) != 1 or raw_files[0].stat().st_size != 64:
        return "no_bounded_native_result"
    data = raw_files[0].read_bytes()
    if not any(data):
        return "all_zero_output"
    return "native_64_byte_result_nonempty"


def run_once():
    result = {
        "status": "no_go",
        "probe": "one_isolated_tiny_qnn_htp_attempt",
        "tiny_16004_byte_dlc_verified": False,
        "native_64_byte_input_verified": False,
        "existing_geniex_service_modified": False,
        "existing_model_restarted": False,
        "second_large_model_loaded": False,
        "htp_attempted": False,
        "htp_inference_verified": False,
        "qnn_cli_exit_zero": None,
        "dsp_library_path_configured": False,
        "native_output_status": None,
        "wall_seconds": None,
    }
    if platform.machine().lower() != "aarch64":
        result["status"] = "no_go_not_arm64"
        return result
    if os.environ.get("MYAI_ALLOW_ONE_TINY_QNN_HTP_ATTEMPT") != "yes":
        result["status"] = "no_go_not_authorized"
        return result
    if available_memory_kib() is None or available_memory_kib() < MIN_AVAILABLE_KIB:
        result["status"] = "no_go_insufficient_ram"
        return result
    live = summarize_service(Path("/proc"), main_pid_from_systemd())
    if live.get("fast_rpc_secure_fd_open") is True:
        result["status"] = "no_go_existing_geniex_fastrpc_busy"
        return result
    checked = verify_fixture(DEFAULT_FIXTURE)
    if checked.get("file_identity_verified") is not True:
        result["status"] = "no_go_tiny_dlc_identity"
        return result
    result["tiny_16004_byte_dlc_verified"] = True
    source = native_input()
    if len(source) != 64 or hashlib.sha256(source).hexdigest() != INPUT_SHA:
        result["status"] = "no_go_native_input_identity"
        return result
    result["native_64_byte_input_verified"] = True
    program = shutil.which("qnn-net-run")
    if not program or not NEEDED.issubset(_help_flags(program)):
        result["status"] = "no_go_installed_cli_flags"
        return result
    libs = _find_libraries()
    if any(x not in libs for x in LIBS):
        result["status"] = "no_go_required_htp_libraries"
        return result
    dsp_directory = _find_v75_skel_directory()
    if dsp_directory is None:
        result["status"] = "no_go_missing_htp_v75_dsp_skel"
        return result
    with tempfile.TemporaryDirectory(
        prefix="myai-tiny-htp-", dir=os.environ.get("RUNNER_TEMP", "/tmp")
    ) as dirname:
        root = Path(dirname)
        os.chmod(root, 0o700)
        # Only synthetic, verified DLC and native input are materialized.
        dlc_bytes = base64.b64decode(DEFAULT_FIXTURE.read_bytes().strip(), validate=True)
        if len(dlc_bytes) != 16004 or hashlib.sha256(dlc_bytes).hexdigest() != checked["dlc_sha256"]:
            result["status"] = "no_go_dlc_materialization_mismatch"
            return result
        dlc = root / "tiny_synthetic.dlc"
        dlc.write_bytes(dlc_bytes)
        (root / "input.raw").write_bytes(source)
        (root / "inputs.txt").write_text("input.raw\n", encoding="ascii")
        libraries = ":".join(sorted({str(path.parent) for path in libs.values()}))
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(root),
            "LD_LIBRARY_PATH": libraries,
            "ADSP_LIBRARY_PATH": str(dsp_directory),
            "QNN_LOG_LEVEL": "ERROR",
        }
        arguments = [
            program,
            "--backend", str(libs["libQnnHtp.so"]),
            "--model", str(libs["libQnnModelDlc.so"]),
            "--dlc_path", str(dlc),
            "--input_list", str(root / "inputs.txt"),
            "--output_dir", str(root / "results"),
            "--use_native_input_files",
            "--use_native_output_files",
        ]
        start = time.monotonic()
        result["dsp_library_path_configured"] = True
        result["htp_attempted"] = True
        try:
            completed = subprocess.run(
                arguments, cwd=root, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, check=False, timeout=30,
                preexec_fn=_child_limits,
            )
            result["qnn_cli_exit_zero"] = completed.returncode == 0
            result["status"] = (
                "qnn_htp_cli_exit_zero_check_output"
                if completed.returncode == 0 else "qnn_htp_cli_nonzero"
            )
            if completed.returncode == 0:
                check = _output_summary(root)
                result["native_output_status"] = check
                if check == "native_64_byte_result_nonempty":
                    result["status"] = "tiny_qnn_htp_native_inference_succeeded"
                    result["htp_inference_verified"] = True
                else:
                    result["status"] = "htp_result_unverified"
        except subprocess.TimeoutExpired:
            result["status"] = "qnn_htp_timeout"
        except OSError:
            result["status"] = "qnn_htp_process_launch_failed"
        finally:
            result["wall_seconds"] = round(time.monotonic() - start, 3)
    return result


if __name__ == "__main__":
    print("MYAI_TINY_HTP_ONCE_JSON=" + json.dumps(run_once(), sort_keys=True))
