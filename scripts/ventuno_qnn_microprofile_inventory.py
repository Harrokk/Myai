"""Bounded inventory for a small, independent QAIRT profiling sample.

Never execute qnn-net-run, download or convert models, read model bytes, open
user cache files, or change services. Inspect only narrowly selected SDK
example directories for small file metadata. Results expose only aggregate
counts, tool availability, and explicitly fail-closed readiness flags.
"""
from __future__ import annotations

import json
import os
import shutil
from collections import Counter, deque
from pathlib import Path

MAX_DIRECTORIES = 240
MAX_FILES = 1400
MAX_DEPTH = 6
MAX_ENTRIES_PER_DIRECTORY = 320
MAX_SAMPLE_BYTES = 32 * 1024 * 1024

TOOL_NAMES = (
    "qnn-net-run",
    "qnn-profile-viewer",
    "qnn-context-binary-utility",
    "qnn-context-binary-generator",
    "qnn-model-lib-generator",
    "qnn-onnx-converter",
    "qnn-dlc-quantizer",
)
ARTIFACT_KIND = {
    ".dlc": "dlc",
    ".onnx": "onnx",
    ".tflite": "tflite",
    ".bin": "bin-unverified",
}
EXAMPLE_COMPONENTS = frozenset({
    "examples", "example", "samples", "sample", "testdata",
})
INPUT_NAMES = frozenset({
    "input_list.txt", "raw_list.txt", "target_raw_list.txt",
})


def sample_tree(rel: Path) -> bool:
    """Do not count arbitrary binaries in model/cache trees as SDK samples."""
    return any(part.casefold() in EXAMPLE_COMPONENTS for part in rel.parts[:-1])


def candidate_inventory(
    roots: tuple[Path, ...],
    *,
    max_dirs: int = MAX_DIRECTORIES,
    max_files: int = MAX_FILES,
) -> dict[str, object]:
    """Stat small SDK sample artifacts without opening or printing filenames."""
    if type(max_dirs) is not int or not 1 <= max_dirs <= MAX_DIRECTORIES:
        raise ValueError("invalid-directory-cap")
    if type(max_files) is not int or not 1 <= max_files <= MAX_FILES:
        raise ValueError("invalid-file-cap")
    queue = deque()
    roots_found = 0
    for root in roots:
        if root.is_dir() and not root.is_symlink():
            queue.append((root, root, 0))
            roots_found += 1
    dirs = files = 0
    capped = False
    unreadable = False
    counts: Counter[str] = Counter()
    over_limit: Counter[str] = Counter()
    input_list_presence = False
    while queue and dirs < max_dirs and files < max_files:
        root, directory, depth = queue.popleft()
        dirs += 1
        try:
            with os.scandir(directory) as itr:
                entries = []
                for index, entry in enumerate(itr):
                    if index >= MAX_ENTRIES_PER_DIRECTORY:
                        capped = True
                        break
                    entries.append(entry)
        except OSError:
            unreadable = True
            continue
        for entry in entries:
            if files >= max_files:
                capped = True
                break
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if depth < MAX_DEPTH:
                        queue.append((root, Path(entry.path), depth + 1))
                    else:
                        capped = True
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                files += 1
                rel = Path(entry.path).relative_to(root)
                if not sample_tree(rel):
                    continue
                name = entry.name.casefold()
                if name in INPUT_NAMES:
                    input_list_presence = True
                kind = ARTIFACT_KIND.get(Path(name).suffix)
                if kind is None:
                    continue
                size = entry.stat(follow_symlinks=False).st_size
                if not 0 < size <= MAX_SAMPLE_BYTES:
                    over_limit[kind] += 1
                    continue
                counts[kind] += 1
            except (OSError, ValueError):
                unreadable = True
    if queue or dirs >= max_dirs or files >= max_files:
        capped = True
    return {
        "sdk_roots_present": roots_found,
        "directories_inspected": dirs,
        "files_inspected": files,
        "scan_capped": capped,
        "unreadable_entries": unreadable,
        "small_example_artifact_counts": dict(sorted(counts.items())),
        "oversize_or_empty_artifact_counts": dict(sorted(over_limit.items())),
        "example_input_list_found": input_list_presence,
        "independent_compatible_context_verified": False,
        "correct_native_input_values_verified": False,
        "htp_profile_measurement_verified": False,
        "authorization_to_run_qnn": False,
        "authorization_to_modify_services": False,
    }


def installed_tools() -> dict[str, bool]:
    """Only PATH availability; do not invoke converters or their --help."""
    return {name: shutil.which(name) is not None for name in TOOL_NAMES}


def readiness_report(tools: dict[str, bool], inventory: dict[str, object]) -> dict[str, object]:
    has_model = bool(inventory.get("small_example_artifact_counts"))
    if inventory.get("scan_capped") or inventory.get("unreadable_entries"):
        status = "inconclusive-sdk-inventory"
    elif has_model:
        status = "candidate-needs-format-and-runtime-validation"
    elif tools.get("qnn-onnx-converter") and tools.get("qnn-context-binary-generator"):
        status = "host-standalone-sample-preparation-may-be-possible"
    else:
        status = "no-go-separate-prepared-sample-required"
    return {
        "status": status,
        "npu_profiling_go": False,
        "host_or_device_toolchain_presence_not_model_compatibility": True,
        "production_contexts_usable_as_test_sample": False,
        "no_inference_or_conversion_performed": True,
    }


def main() -> int:
    home = Path.home()
    roots = (
        home / ".local" / "share" / "geniex" / "qairt",
        home / ".local" / "share" / "qairt",
        home / "qairt",
        Path("/opt/qairt"),
        Path("/opt/qcom"),
        Path("/opt/qualcomm"),
        Path("/usr/local/share/qairt"),
        Path("/usr/local/share/qnn"),
    )
    tools = installed_tools()
    inventory = candidate_inventory(roots)
    print("Independent small QAIRT sample readiness (read-only)")
    print("QNN tool availability:", json.dumps(tools, sort_keys=True))
    print("SDK example inventory:", json.dumps(inventory, sort_keys=True))
    print("Profiling decision:", json.dumps(readiness_report(tools, inventory), sort_keys=True))
    print("No QNN context opened, model downloaded, generated, loaded, or executed.")
    print("Production GenieX contexts and systemd services untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
