"""One tiny verified Qualcomm CPU-backend DLC comparison on real VENTUNO.

Does not initialize HTP/NPU, use audio, affect installed GenieX, load an
LLM or log QNN output. Only 16,004 B synthetic DLC, 64 B native test input,
limited files/RAM/CPU and bounded 20s child process. Explicit one-shot opt-in.
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

from scripts.qairt_245_dlc_static_audit import (
    DEFAULT_FIXTURE, verify_fixture,
)
from scripts.prepare_qairt245_native_fixture import native_input
from scripts.ventuno_live_qairt_synthetic_once import available_memory_kib
from scripts.ventuno_tiny_qnn_htp_once import (
    INPUT_SHA, _find_libraries, _help_flags, NEEDED,
)
from scripts.ventuno_v75_elf_fastrpc_readonly import inspect_resolved_skel
from scripts.ventuno_qnn_native_result_attestation import attest_native_output

EXPECTED_X86_CPU_RAW_SHA = "9f776aec98d9e12d5a33bb91fadcb8d6560293cc3e0d816445be6e9d05928174"


def locate_cpu_backend():
    """Use only the installed QAIRT AArch64 CPU library, never an SDK copy.

    Previous recursive ROOTS traversal could select an alternate inode
    from an old SDK; host HTP libraries already have a strict distro gate.
    This preflight reads bounded ELF header/package metadata only.
    """
    candidate = Path("/usr/lib") / "libQnnCpu.so"
    info = inspect_resolved_skel(candidate, Path("/usr"))
    if (
        info["path_inside_usr"] is True
        and info["file_regular"] is True
        and info["header_class"] == "aarch64_elf_header"
        and info["package_owner"] == "qairt-libs"
        and info["library_file_header_read"] is True
    ):
        return candidate
    return None

def _limits():
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024**2, 2 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))


def cpu_once():
    result = {
        "probe": "one_tiny_qnn_cpu_reference_on_real_ventuno",
        "status": "no_go",
        "synthetic_dlc_verified": False,
        "native_64_byte_input_verified": False,
        "cpu_backend_exec_attempted": False,
        "cpu_native_output_status": None,
        "raw_output_matches_previously_verified_x86_cpu": None,
        "htp_backend_loaded": False,
        "htp_npu_inference_attempted": False,
        "active_geniex_modified": False,
        "wall_seconds": None,
    }
    if platform.machine().lower() != "aarch64":
        result["status"] = "no_go_not_ventuno_arm64"
        return result
    if os.environ.get("MYAI_ALLOW_ONE_TINY_QNN_CPU_ATTEMPT") != "yes":
        result["status"] = "no_go_without_explicit_authorization"
        return result
    memory = available_memory_kib()
    if memory is None or memory < 8 * 1048576:
        result["status"] = "no_go_insufficient_memory"
        return result
    verified = verify_fixture(DEFAULT_FIXTURE)
    if verified.get("file_identity_verified") is not True:
        result["status"] = "no_go_dlc_not_verified"
        return result
    result["synthetic_dlc_verified"] = True
    source = native_input()
    if len(source) != 64 or hashlib.sha256(source).hexdigest() != INPUT_SHA:
        result["status"] = "no_go_input_not_verified"
        return result
    result["native_64_byte_input_verified"] = True
    program = shutil.which("qnn-net-run")
    if not program or not NEEDED.issubset(_help_flags(program)):
        result["status"] = "no_go_cli_flags"
        return result
    lib = locate_cpu_backend()
    models = _find_libraries()
    if lib is None or "libQnnModelDlc.so" not in models:
        result["status"] = "no_go_cpu_dlc_backend_missing"
        return result
    encoded = DEFAULT_FIXTURE.read_bytes().strip()
    binary = base64.b64decode(encoded, validate=True)
    if len(binary) != 16004 or hashlib.sha256(binary).hexdigest() != verified["dlc_sha256"]:
        result["status"] = "no_go_dlc_identity_after_decode"
        return result

    with tempfile.TemporaryDirectory(
        prefix="myai-tiny-qnn-cpu-", dir=os.environ.get("RUNNER_TEMP", "/tmp")
    ) as dirname:
        folder = Path(dirname)
        os.chmod(folder, 0o700)
        (folder / "synthetic.dlc").write_bytes(binary)
        (folder / "input.raw").write_bytes(source)
        (folder / "inputs.txt").write_text("input.raw\n", encoding="ascii")
        dll_dirs = sorted({str(lib.parent), str(models["libQnnModelDlc.so"].parent)})
        env = {
            "PATH": "/usr/bin:/bin", "HOME": str(folder),
            "LD_LIBRARY_PATH": ":".join(dll_dirs), "QNN_LOG_LEVEL": "ERROR",
        }
        cmd = [
            program,
            "--backend", str(lib),
            "--model", str(models["libQnnModelDlc.so"]),
            "--dlc_path", str(folder / "synthetic.dlc"),
            "--input_list", str(folder / "inputs.txt"),
            "--output_dir", str(folder / "results"),
            "--use_native_input_files", "--use_native_output_files",
        ]
        start = time.monotonic()
        result["cpu_backend_exec_attempted"] = True
        try:
            proc = subprocess.run(
                cmd, cwd=folder, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=20, check=False, preexec_fn=_limits,
            )
            if proc.returncode != 0:
                result["status"] = "qnn_cpu_cli_nonzero"
            else:
                # Use the same bounded, symlink-rejecting parity check
                # as the HTP diagnostic. Never trust an arbitrary .raw file,
                # multiple outputs, nonzero bytes, or a different digest.
                attested = attest_native_output(folder)
                result["cpu_native_output_status"] = attested["status"]
                match = attested["output_matches_verified_cpu_reference"]
                result["raw_output_matches_previously_verified_x86_cpu"] = match
                if match is True:
                    result["status"] = "tiny_qnn_cpu_reference_matches_x86"
                elif match is False:
                    result["status"] = "cpu_output_present_differs_from_x86_digest"
                else:
                    result["status"] = "qnn_cpu_output_unverified"
        except subprocess.TimeoutExpired:
            result["status"] = "qnn_cpu_timeout"
        except OSError:
            result["status"] = "qnn_cpu_launch_error"
        finally:
            result["wall_seconds"] = round(time.monotonic() - start, 3)
    return result


if __name__ == "__main__":
    print("MYAI_QNN_CPU_REFERENCE_ONCE_JSON=" +
          json.dumps(cpu_once(), sort_keys=True))
