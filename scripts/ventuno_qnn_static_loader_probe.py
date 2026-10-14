"""Read-only QAIRT ELF dependencies for the previous instant HTP CLI failure.

The installed QNN CLI or any runtime libraries are NEVER executed/loaded.
Only a bounded readelf invocation reads ELF metadata. Report names of
linked system libraries, not absolute paths, user directories or raw logs.
A missing library in our search is a *candidate*, not proven loader failure.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from scripts.ventuno_tiny_qnn_htp_once import (
    _find_libraries, _find_v75_skel_directory,
)

DYNAMIC_NAMES = (
    "qnn-net-run", "libQnnHtp.so", "libQnnModelDlc.so",
    "libQnnHtpV75Stub.so",
)
_MAX_BYTES = 96 * 1024
_MAX_NEEDED = 64
_ELF_NAME = re.compile(r"^[A-Za-z0-9_.+-]{1,100}\.so(?:\.[0-9.]+)?$")
_NEEDED = re.compile(r"\(NEEDED\)\s+Shared library:\s+\[([^\]]+)\]")
_RUNPATH = re.compile(r"\((RUNPATH|RPATH)\)\s+Library (?:runpath|rpath):")
_BASE_ROOTS = (
    Path("/lib"), Path("/usr/lib"), Path("/usr/local/lib"),
    Path("/lib/aarch64-linux-gnu"), Path("/usr/lib/aarch64-linux-gnu"),
)
_IMPORTANT = frozenset({
    "libQnnHtp.so", "libQnnHtpV75Stub.so", "libQnnModelDlc.so",
    "libQnnSystem.so", "libcdsprpc.so", "libadsprpc.so",
    "libQnnHtpPrepare.so",
})


def parse_dynamic(text):
    """Only include validated ELF NEEDED library basenames; discard paths."""
    found = []
    for value in _NEEDED.findall(text[:_MAX_BYTES]):
        if _ELF_NAME.fullmatch(value) and value not in found:
            found.append(value)
        if len(found) > _MAX_NEEDED:
            return {"valid": False, "needed": [], "has_runpath": False,
                    "truncated": True}
    return {
        "valid": True, "needed": found,
        "has_runpath": bool(_RUNPATH.search(text[:_MAX_BYTES])),
        "truncated": len(text) >= _MAX_BYTES,
    }


def readelf_needed(binary):
    """Get ELF dependencies, never ld(d), dlopen or running QNN."""
    executable = shutil.which("readelf")
    if not executable or not binary or not Path(binary).is_file():
        return {"status": "unavailable", "needed": [], "has_runpath": False}
    try:
        result = subprocess.run(
            [executable, "--wide", "--dynamic", str(binary)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "unreadable", "needed": [], "has_runpath": False}
    if result.returncode != 0 or len(result.stdout) > _MAX_BYTES:
        return {"status": "unreadable", "needed": [], "has_runpath": False}
    parsed = parse_dynamic(result.stdout.decode("utf-8", errors="replace"))
    return {
        "status": "readelf_parsed" if parsed["valid"] else "unreadable",
        "needed": parsed["needed"],
        "has_runpath": parsed["has_runpath"],
    }


def library_exists(name, search_directories):
    """Direct NEEDED-name lookup. This is not dynamic linker emulation."""
    if not _ELF_NAME.fullmatch(name):
        return False
    for directory in search_directories:
        try:
            target = directory / name
            if target.is_file():
                return True
        except (OSError, RuntimeError):
            pass
    return False


def inspect_static_loader():
    program = shutil.which("qnn-net-run")
    libs = _find_libraries()
    targets = {
        "qnn-net-run": program,
        "libQnnHtp.so": libs.get("libQnnHtp.so"),
        "libQnnModelDlc.so": libs.get("libQnnModelDlc.so"),
        "libQnnHtpV75Stub.so": libs.get("libQnnHtpV75Stub.so"),
    }
    dirs = set(_BASE_ROOTS)
    dirs.update(p.parent for p in libs.values())
    if program:
        dirs.add(Path(program).parent)
    skel = _find_v75_skel_directory()
    if skel is not None:
        dirs.add(skel)
    # Several QAIRT deployments arrange dependencies in sibling directories.
    for d in tuple(dirs):
        if d.parent.name in ("lib", "qairt") or d.name in ("lib", "aarch64-linux-gnu"):
            dirs.add(d.parent)
    results = {}
    important_unresolved = set()
    for name, path in targets.items():
        parsed = readelf_needed(path)
        deps = parsed["needed"]
        missing = sorted(n for n in deps if not library_exists(n, dirs))
        important_unresolved.update(n for n in missing if n in _IMPORTANT)
        results[name] = {
            "available": bool(path),
            "elf_dynamic_status": parsed["status"],
            "direct_needed_count": len(deps),
            "direct_needed_basenames": deps[:32],
            "direct_needed_not_found_in_sampled_library_dirs": missing[:32],
            "elf_runpath_present": parsed["has_runpath"],
        }
    return {
        "probe": "ventuno_qnn_elf_loader_static_only",
        "objects": results,
        "sampled_library_dirs_count": len(dirs),
        "important_missing_dependency_candidates": sorted(important_unresolved),
        "loader_failure_cause_proven": False,
        "transitive_or_dlopen_dependencies_exhaustively_checked": False,
        "qnn_process_executed": False,
        "any_inference_executed": False,
        "production_modified": False,
    }


if __name__ == "__main__":
    print("MYAI_QNN_ELF_STATIC_JSON=" +
          json.dumps(inspect_static_loader(), sort_keys=True))
