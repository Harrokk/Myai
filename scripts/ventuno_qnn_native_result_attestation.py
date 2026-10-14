"""Attest a tiny QNN output against the verified x86/VENTUNO CPU reference.

Pure post-processing only. A matching digest is evidence of CPU output
parity, NOT that any operator ran on an HTP accelerator.

Use file-descriptor-relative opens for every path component: a symlink
swapped in after directory enumeration must never redirect the 64-byte
read into another file. Neither results nor digests are exported.
"""
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import re
import stat

EXPECTED_X86_CPU_RAW_SHA = (
    "9f776aec98d9e12d5a33bb91fadcb8d6560293cc3e0d816445be6e9d05928174"
)
MAX_DIRECTORY_ENTRIES = 24
OUTPUT_BYTES = 64

# Linux-only primitive; the on-device diagnostic runs on Linux. All opened
# directories are anchored by fd, and the raw file cannot be followed from
# a substituted symlink, even if swapped between listing and open().
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
RAW_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


def _safe_native_bytes(root: Path):
    """Return (reason, 64 bytes or None) with no recursive path traversal."""
    with ExitStack() as stack:
        try:
            root_fd = os.open(root, DIRECTORY_FLAGS)
            stack.callback(os.close, root_fd)
            results_fd = os.open("results", DIRECTORY_FLAGS, dir_fd=root_fd)
            stack.callback(os.close, results_fd)
            folder_fd = os.open("Result_0", DIRECTORY_FLAGS, dir_fd=results_fd)
            stack.callback(os.close, folder_fd)
        except OSError:
            return "missing_or_untrusted_result_directory", None

        names = []
        try:
            # scandir(fd) is a streaming enumeration of the *opened*
            # directory. Unlike listdir(), it does not allocate unlimited
            # entries before the directory budget is checked.
            with os.scandir(folder_fd) as entries:
                for count, entry in enumerate(entries):
                    if count >= MAX_DIRECTORY_ENTRIES:
                        return "directory_entry_limit", None
                    if entry.name.lower().endswith(".raw"):
                        names.append(entry.name)
                        if len(names) > 1:
                            return "ambiguous_raw_outputs", None
        except OSError:
            return "unreadable_output", None

        if len(names) != 1:
            return "missing_or_untrusted_raw_output", None

        try:
            fd = os.open(names[0], RAW_FLAGS, dir_fd=folder_fd)
            stack.callback(os.close, fd)
        except OSError:
            return "missing_or_untrusted_raw_output", None
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                return "missing_or_untrusted_raw_output", None
            if before.st_size != OUTPUT_BYTES:
                return "wrong_native_output_size", None
            # Even if a writer expands the file after fstat, read at most
            # 65 bytes and refuse a changed length. Never read unknown
            # binary sizes, special files, or private paths.
            data = os.read(fd, OUTPUT_BYTES + 1)
            after = os.fstat(fd)
            if (
                len(data) != OUTPUT_BYTES
                or not stat.S_ISREG(after.st_mode)
                or after.st_size != OUTPUT_BYTES
                or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            ):
                return "changed_or_unreadable_output", None
            return "native_64_byte_output_read", data
        except OSError:
            return "unreadable_output", None


def attest_native_output(root: Path, expected_sha: str = EXPECTED_X86_CPU_RAW_SHA):
    """Return bounded status and CPU-reference parity, never HTP placement."""
    result = {
        "status": "unverified",
        "native_64_byte_output_present": False,
        "output_matches_verified_cpu_reference": None,
        "htp_operator_placement_verified": False,
        "npu_execution_verified": False,
        "raw_output_or_digest_exported": False,
    }
    if not isinstance(expected_sha, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_sha
    ):
        result["status"] = "invalid_reference_digest"
        return result

    reason, raw = _safe_native_bytes(root)
    if raw is None:
        result["status"] = reason
        return result
    result["native_64_byte_output_present"] = True
    if not any(raw):
        result["status"] = "all_zero_output"
        result["output_matches_verified_cpu_reference"] = False
        return result

    matches = hashlib.sha256(raw).hexdigest() == expected_sha
    result["output_matches_verified_cpu_reference"] = matches
    result["status"] = (
        "cpu_reference_digest_match_but_placement_unverified"
        if matches else "nonzero_output_differs_from_cpu_reference"
    )
    return result
