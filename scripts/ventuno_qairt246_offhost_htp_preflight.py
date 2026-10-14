"""Off-device QAIRT 2.46 HTP context-preparation prerequisites, metadata only.

This NEVER executes vendor SDK tools, generates a context, imports QNN, or
contacts/changes VENTUNO. Absent official SDK and vendor-verified numerical
SoC target are hard NO-GO, not invitations to guess or download binaries.
Only exact allowlisted x86 host files are read (max 64 header bytes each).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat

from scripts.qairt_245_dlc_static_audit import DEFAULT_FIXTURE, verify_fixture
from scripts.prepare_tiny_qnn_host_sample import is_ventuno_arch

HOST_TRIPLE = "x86_64-linux-clang"
SDK_LABEL_RE = re.compile(r"^2[.]46[.][0-9]{1,3}(?:[.][0-9]{1,12})?$")
HOST_ARTIFACTS = {
    "context_generator": Path("bin") / HOST_TRIPLE / "qnn-context-binary-generator",
    "htp_backend": Path("lib") / HOST_TRIPLE / "libQnnHtp.so",
    "dlc_loader": Path("lib") / HOST_TRIPLE / "libQnnModelDlc.so",
    "htp_extensions": Path("lib") / HOST_TRIPLE / "libQnnHtpNetRunExtensions.so",
}
MAX_HOST_FILE_BYTES = 160 * 1024 * 1024
MAX_ELF_HEADER_BYTES = 64


def classify_x86_elf(raw: bytes) -> str:
    if len(raw) < 20 or raw[:4] != b"\x7fELF":
        return "not_elf_or_truncated"
    if raw[4] != 2 or raw[5] != 1:
        return "unsupported_elf_class_or_byte_order"
    return "x86_64" if int.from_bytes(raw[18:20], "little") == 62 else "different_elf_architecture"


def inspect_regular_x86_file(path: Path) -> str:
    """No symlinks, FIFO, socket or mutable inode substitution accepted."""
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            return "missing_or_untrusted_file_type"
        if not 20 <= before.st_size <= MAX_HOST_FILE_BYTES:
            return "file_size_outside_bound"
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        flags |= getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path, flags)
        try:
            after = os.fstat(fd)
            if (not stat.S_ISREG(after.st_mode)
                    or not 20 <= after.st_size <= MAX_HOST_FILE_BYTES
                    or (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)):
                return "file_changed_or_untrusted"
            return classify_x86_elf(os.read(fd, MAX_ELF_HEADER_BYTES))
        finally:
            os.close(fd)
    except OSError:
        return "file_unavailable"


def inspect_sdk(root: Path | None) -> dict:
    result = {
        "sdk_directory_present": False,
        "sdk_label_looks_like_246": False,
        "sdk_provenance_attested": False,
        "artifacts": {name: "not_checked" for name in HOST_ARTIFACTS},
        "host_tools_look_like_x86_elf": False,
    }
    if root is None:
        return result
    try:
        if root.is_symlink() or not root.is_dir():
            return result
    except OSError:
        return result
    result["sdk_directory_present"] = True
    # A directory label is never evidence of an authentic Qualcomm download.
    result["sdk_label_looks_like_246"] = SDK_LABEL_RE.fullmatch(root.name) is not None
    for name, relative in HOST_ARTIFACTS.items():
        result["artifacts"][name] = inspect_regular_x86_file(root / relative)
    result["host_tools_look_like_x86_elf"] = all(
        result["artifacts"][name] == "x86_64" for name in HOST_ARTIFACTS
    )
    return result


def inspect_synthetic_dlc(path: Path = DEFAULT_FIXTURE) -> dict:
    checked = verify_fixture(path)
    # No raw hash or bytes in the public JSON, and never treat ZIP as HTP.
    return {
        "exact_synthetic_dlc_identity_verified": (
            checked["file_identity_verified"] is True
            and checked["dlc_byte_count"] == 16004
        ),
        "synthetic_dlc_created_with_qairstack": "2.45",
        "runtime_cross_version_htp_operator_support_verified": False,
        "htp_context_generation_completed": False,
    }


def preflight(*, sdk_root: Path | None = None,
              synthetic_dlc: Path = DEFAULT_FIXTURE,
              host_arch: str | None = None) -> dict:
    machine = host_arch or platform.machine()
    on_host = machine.lower() in {"x86_64", "amd64"}
    base = {
        "probe": "ventuno_qairt_246_offhost_htp_preparation_requirements",
        "status": "no_go_non_x86_host",
        "host_is_x86_64": on_host,
        "sdk": None,
        "synthetic_dlc": None,
        "board_chipset_documented": "QCS8275",
        "htp_architecture_documented_by_arduino": "V75",
        "vendor_verified_numeric_soc_id": False,
        "vendor_verified_soc_config_for_exact_sdk": False,
        "sdk_download_or_execution_attempted": False,
        "qnn_context_generated": False,
        "htp_operator_support_tested": False,
        "npu_placement_measured": False,
        "ventuno_accessed_or_modified": False,
        "raw_sdk_paths_file_data_or_secrets_exported": False,
    }
    if not on_host or is_ventuno_arch(machine):
        return base
    base["sdk"] = inspect_sdk(sdk_root)
    base["synthetic_dlc"] = inspect_synthetic_dlc(synthetic_dlc)
    if not base["synthetic_dlc"]["exact_synthetic_dlc_identity_verified"]:
        base["status"] = "no_go_unverified_synthetic_dlc"
    elif not base["sdk"]["sdk_directory_present"]:
        base["status"] = "no_go_sdk_not_supplied"
    elif not base["sdk"]["sdk_label_looks_like_246"]:
        base["status"] = "no_go_unverified_sdk_version_label"
    elif not base["sdk"]["host_tools_look_like_x86_elf"]:
        base["status"] = "no_go_sdk_host_artifacts_missing_or_invalid"
    else:
        # The SDK directory and ELF headers prove neither package authenticity
        # nor target SoC ID. No command is ever assembled/run automatically.
        base["status"] = "no_go_manual_vendor_sdk_and_soc_attestation_required"
    return base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", type=Path, default=None)
    args = parser.parse_args()
    result = preflight(sdk_root=args.sdk_root)
    print("MYAI_QAIRT246_OFFHOST_PREFLIGHT_JSON=" + json.dumps(result, sort_keys=True))
    return 0 if result["host_is_x86_64"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
