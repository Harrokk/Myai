"""Attest a tiny QNN output against the verified x86/VENTUNO CPU reference.

This is a pure *post-process* helper. Never starts QNN, loads models or uses
devices. A matching digest is evidence of output parity, NOT that an HTP
graph executed or any operator was placed on the accelerator.
"""
import hashlib
from pathlib import Path
import re

EXPECTED_X86_CPU_RAW_SHA = (
    "9f776aec98d9e12d5a33bb91fadcb8d6560293cc3e0d816445be6e9d05928174"
)
MAX_DIRECTORY_ENTRIES = 24


def attest_native_output(root: Path, expected_sha: str = EXPECTED_X86_CPU_RAW_SHA):
    """Return only a bounded status and a Boolean match; no paths or bytes."""
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
    result_parent = root / "results"
    folder = result_parent / "Result_0"
    try:
        if (result_parent.is_symlink() or not result_parent.is_dir()
                or folder.is_symlink() or not folder.is_dir()):
            result["status"] = "missing_or_untrusted_result_directory"
            return result
        matches = []
        for index, child in enumerate(folder.iterdir()):
            if index >= MAX_DIRECTORY_ENTRIES:
                result["status"] = "directory_entry_limit"
                return result
            if child.suffix.lower() == ".raw":
                matches.append(child)
                if len(matches) > 1:
                    result["status"] = "ambiguous_raw_outputs"
                    return result
        if len(matches) != 1 or matches[0].is_symlink():
            result["status"] = "missing_or_untrusted_raw_output"
            return result
        path = matches[0]
        if not path.is_file() or path.stat().st_size != 64:
            result["status"] = "wrong_native_output_size"
            return result
        raw = path.read_bytes()
        if len(raw) != 64:
            result["status"] = "changed_or_unreadable_output"
            return result
        result["native_64_byte_output_present"] = True
        if not any(raw):
            result["status"] = "all_zero_output"
            result["output_matches_verified_cpu_reference"] = False
            return result
        matches_ref = hashlib.sha256(raw).hexdigest() == expected_sha
        result["output_matches_verified_cpu_reference"] = matches_ref
        result["status"] = (
            "cpu_reference_digest_match_but_placement_unverified"
            if matches_ref else "nonzero_output_differs_from_cpu_reference"
        )
    except OSError:
        result["status"] = "unreadable_output"
    return result
