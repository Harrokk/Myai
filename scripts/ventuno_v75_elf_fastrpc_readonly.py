"""Bounded, read-only Hexagon v75 Skel ELF and FastRPC packaging provenance.

Read at most 64 ELF-header bytes from the resolved V75 Skel regular file
only if within /usr, and fixed metadata for two FastRPC shell locations.
Query only two exact distro package names with sanitized return values.
Never dlopen/execute QNN/DSP binaries or open /dev devices. Do not export
resolved paths, symlink text, process identifiers or raw package output.
"""
import json
import os
from pathlib import Path
import stat
import subprocess
import shutil

from scripts.ventuno_htp_v75_skel_link_readonly import SKEL, package_owner
from scripts.ventuno_qairt_v75_package_readonly import classify_package_output

ROOT = Path("/usr")
FAST_RPC_SHELLS = {
    "usr_lib_dsp": Path("/usr/lib/dsp/fastrpc_shell_unsigned_3"),
    "usr_lib_dsp_cdsp": Path("/usr/lib/dsp/cdsp/fastrpc_shell_unsigned_3"),
}
PACKAGES = ("qcom-fastrpc1", "qcom-fastrpc-dev")
MAX_REGULAR_FILE_BYTES = 128 * 1024 * 1024
MAX_ELF_HEADER = 64


def classify_elf_header(raw):
    """Classify ELF e_machine, never retain any bytes from ELF contents."""
    if not isinstance(raw, bytes) or len(raw) < 20 or raw[:4] != b"\x7fELF":
        return "not_elf_or_incomplete"
    if raw[4] not in (1, 2) or raw[5] != 1:
        return "unsupported_elf_class_or_endian"
    machine = int.from_bytes(raw[18:20], "little")
    if machine == 164:
        return "hexagon_elf_header"
    if machine == 183:
        return "aarch64_elf_header"
    return "other_elf_header"


def inspect_resolved_skel(link=SKEL, allowed_root=ROOT):
    """Resolve by metadata, then read only a bounded regular ELF header.

    Opening a library FILE is required to inspect bytes; never opens a DSP
    DEVICE or maps, dlopens or executes any library.
    """
    outcome = {
        "path_inside_usr": None,
        "file_regular": False,
        "header_class": "unavailable",
        "package_owner": "unverified",
        "library_file_header_read": False,
    }
    try:
        target = link.resolve(strict=True)
        root = allowed_root.resolve(strict=True)
        if not target.is_relative_to(root):
            outcome["path_inside_usr"] = False
            return outcome
        outcome["path_inside_usr"] = True
        file_info = target.lstat()
        if not stat.S_ISREG(file_info.st_mode):
            return outcome
        outcome["file_regular"] = True
        outcome["package_owner"] = package_owner(target)
        if not (20 <= file_info.st_size <= MAX_REGULAR_FILE_BYTES):
            outcome["header_class"] = "size_outside_bound"
            return outcome
        flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
        flags |= getattr(os, "O_CLOEXEC", 0)
        fd = os.open(target, flags)
        try:
            check = os.fstat(fd)
            if (not stat.S_ISREG(check.st_mode)
                    or not 20 <= check.st_size <= MAX_REGULAR_FILE_BYTES
                    or (check.st_dev, check.st_ino) != (file_info.st_dev, file_info.st_ino)):
                outcome["header_class"] = "file_changed_or_outside_bound"
                return outcome
            data = os.read(fd, MAX_ELF_HEADER)
            outcome["library_file_header_read"] = True
            outcome["header_class"] = classify_elf_header(data)
        finally:
            os.close(fd)
    except (OSError, RuntimeError, ValueError, AttributeError):
        outcome["header_class"] = "unavailable"
    return outcome


def shell_metadata(paths=FAST_RPC_SHELLS):
    """Do not open a shell executable; presence is not PD compatibility."""
    result = {}
    for key, target in paths.items():
        try:
            info = target.lstat()
            kind = ("regular_file" if stat.S_ISREG(info.st_mode)
                    else "symlink_unresolved" if stat.S_ISLNK(info.st_mode)
                    else "other_file_type")
        except FileNotFoundError:
            kind = "absent"
        except OSError:
            kind = "unavailable"
        result[key] = kind
    return result


def fastrpc_packages():
    tool = shutil.which("dpkg-query")
    if tool is None:
        return {n: {"status": "tool_unavailable", "version": None}
                for n in PACKAGES}
    output = {}
    format_string = "-f=" + "$" + "{db:Status-Abbrev}|" + "$" + "{Version}"
    for package in PACKAGES:
        try:
            process = subprocess.run(
                [tool, "-W", format_string, package],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                check=False, timeout=5,
                env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
            )
            output[package] = classify_package_output(
                process.returncode, process.stdout
            )
        except (OSError, subprocess.TimeoutExpired):
            output[package] = {"status": "unavailable", "version": None}
    return output


def report():
    skel = inspect_resolved_skel()
    return {
        "probe": "ventuno_v75_hexagon_elf_and_fastrpc_package_readonly",
        "resolved_v75_skel": skel,
        "fastrpc_shell_locations": shell_metadata(),
        "fastrpc_distro_packages": fastrpc_packages(),
        "hexagon_header_is_only_format_indication":
            skel["header_class"] == "hexagon_elf_header",
        "dsp_firmware_compatibility_verified": False,
        "dsp_signed_or_unsigned_pd_verified": False,
        "qnn_htp_runtime_backend_verified": False,
        "no_device_node_opened": True,
        "no_qnn_process_or_inference_started": True,
        "no_production_services_changed": True,
        "raw_file_bytes_or_paths_exported": False,
    }


if __name__ == "__main__":
    print("MYAI_V75_ELF_FASTRPC_JSON=" + json.dumps(report(), sort_keys=True))
