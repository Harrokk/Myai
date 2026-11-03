"""Read-only direct ELF dependency gate for pinned hosted ARM64 CLI builds.

This is a BUILD-TIME check only, not complete recursive dependency provenance.
The native loader/OS library closure and VENTUNO ABI remain production NO-GO.
No generated executable is distributed or run on a device by this tool.
"""
import os
from pathlib import Path
import re
import subprocess
import sys


_ALLOWED_NEEDED = frozenset({
    "libc.so.6",
    "libstdc++.so.6",
    "libgcc_s.so.1",
    "libm.so.6",
    "libpthread.so.0",
    "libdl.so.2",
    "librt.so.1",
})
_ALLOWED_INTERPRETERS = frozenset({
    "/lib/ld-linux-aarch64.so.1",
    "/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1",
})
_NEEDED = re.compile(r"Shared library: \[([^\]]+)\]")
_INTERPRETER = re.compile(r"Requesting program interpreter: ([^\]]+)")


def inspect_readelf(header, program, dynamic):
    """Pure parser: refuse unexpected ISA, search paths and native loaders."""
    if not all(type(s) is str for s in (header, program, dynamic)):
        return {"safe": False, "reason": "missing_elf_sections"}
    if not all((
        re.search(r"Class:\s+ELF64\b", header),
        re.search(r"Data:\s+2's complement, little endian", header),
        re.search(r"Machine:\s+AArch64\b", header),
    )):
        return {"safe": False, "reason": "unexpected_architecture"}
    matches = _INTERPRETER.findall(program)
    if len(matches) != 1 or matches[0] not in _ALLOWED_INTERPRETERS:
        return {"safe": False, "reason": "untrusted_elf_interpreter"}
    if re.search(r"\((RPATH|RUNPATH|AUDIT|DEPAUDIT|FILTER|AUXILIARY)\)", dynamic):
        return {"safe": False, "reason": "native_runtime_search_or_audit_hook"}
    needed = _NEEDED.findall(dynamic)
    if not needed or len(needed) != len(set(needed)):
        return {"safe": False, "reason": "invalid_or_missing_library_dependencies"}
    unexpected = sorted(set(needed) - _ALLOWED_NEEDED)
    if unexpected:
        return {
            "safe": False,
            "reason": "unreviewed_direct_dependency",
            "unexpected": unexpected,
        }
    return {"safe": True, "reason": "direct_needed_allowlist_only",
            "needed": sorted(needed)}


def main(argv):
    if (len(argv) != 3
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or os.uname().machine != "aarch64"):
        return 2
    try:
        root = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
        for name, raw in zip(("transcribe-cli", "whisper-cli"), argv[1:]):
            path = Path(raw)
            if (path.is_symlink() or path.name != name
                    or not path.is_file()
                    or root not in path.resolve(strict=True).parents):
                return 3
            sections = []
            for flag in ("-h", "-l", "-d"):
                result = subprocess.run(
                    ["readelf", flag, "--", str(path)],
                    capture_output=True, text=True, timeout=6, check=False,
                    env={"PATH": "/usr/bin:/bin", "LANG": "C"},
                )
                if result.returncode != 0 or len(result.stdout) > 100000:
                    return 4
                sections.append(result.stdout)
            if not inspect_readelf(*sections)["safe"]:
                return 5
        return 0
    except (OSError, KeyError, ValueError, subprocess.SubprocessError):
        return 6


if __name__ == "__main__":
    sys.exit(main(sys.argv))
