"""Bounded QNN context metadata probe on VENTUNO.

The Qualcomm context binary utility reads serialized-model metadata without
starting qnn-net-run or a new GenieX inference process. Run against ONE cached
context only and report sanitized structural information. Resource limits,
service integrity and temporary output are explicit safety gates.
"""

from __future__ import annotations

import json
import os
try:
    import resource
except ImportError:  # unavailable on Windows development hosts
    resource = None
import shutil
import subprocess
import tempfile
from collections import Counter, deque
from pathlib import Path

MIN_AVAILABLE_KIB = 3 * 1024 * 1024
MAX_INPUT_BYTES = 1100 * 1024 * 1024
MAX_DIRECTORIES = 100
MAX_FILES = 300
MAX_OUTPUT_BYTES = 3 * 1024 * 1024
TIMEOUT_SECONDS = 22


def find_context_candidates(roots: tuple[Path, ...]) -> list[tuple[Path, int]]:
    pending = deque((root, 0) for root in roots if root.is_dir() and not root.is_symlink())
    candidate_files: list[tuple[Path, int]] = []
    dirs = files = 0
    while pending and dirs < MAX_DIRECTORIES and files < MAX_FILES:
        folder, depth = pending.popleft()
        dirs += 1
        try:
            with os.scandir(folder) as entries:
                children = list(entries)
        except OSError:
            continue
        for entry in children:
            if files >= MAX_FILES:
                break
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if depth < 5:
                        pending.append((Path(entry.path), depth + 1))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                files += 1
                if entry.name.endswith(".bin"):
                    size = entry.stat(follow_symlinks=False).st_size
                    if 0 < size <= MAX_INPUT_BYTES:
                        candidate_files.append((Path(entry.path), size))
            except OSError:
                continue
    return sorted(candidate_files, key=lambda pair: pair[1])


def read_available_kib(path: Path = Path("/proc/meminfo")) -> int:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return 0
    for line in lines:
        if line.startswith("MemAvailable:"):
            fields = line.split()
            return int(fields[1]) if len(fields) > 1 and fields[1].isdigit() else 0
    return 0



def preview_schema(data: object, max_depth: int = 6, max_lines: int = 75) -> list[str]:
    """Key names and value types only. Never include values or model paths."""
    result: list[str] = []
    pending: deque[tuple[str, object, int]] = deque([("$", data, 0)])
    while pending and len(result) < max_lines:
        path, node, depth = pending.popleft()
        if isinstance(node, dict):
            result.append(f"{path}: object({len(node)} keys)")
            if depth < max_depth:
                for key in sorted(node, key=str)[:24]:
                    safe_key = str(key)
                    # Vendor structure keys only, never arbitrary user-defined fields.
                    if len(safe_key) <= 60 and safe_key.replace("_", "").isalnum():
                        pending.append((path + "." + safe_key, node[key], depth + 1))
        elif isinstance(node, list):
            result.append(f"{path}: list({len(node)} items)")
            if depth < max_depth and node:
                pending.append((path + "[]", node[0], depth + 1))
        else:
            result.append(f"{path}: {type(node).__name__}")
    return result


def summarize_context_metadata(data: object) -> dict[str, object]:
    """Report counts and first shapes; never expose arbitrary tensor names/data."""
    if not isinstance(data, dict):
        return {"json_kind": type(data).__name__}
    counts = Counter()
    shapes: list[list[int]] = []
    stack: list[object] = [data]
    visited = 0
    while stack and visited < 12000:
        node = stack.pop()
        visited += 1
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = str(key).lower()
                if "graph" in lowered:
                    counts["graph_related_fields"] += 1
                if "tensor" in lowered:
                    counts["tensor_related_fields"] += 1
                if lowered in ("dimensions", "dims", "shape") and isinstance(value, list):
                    if 1 <= len(value) <= 12 and all(
                        isinstance(x, int) and not isinstance(x, bool) and 0 <= x < 10000000
                        for x in value
                    ) and len(shapes) < 12:
                        shapes.append(value)
                stack.append(value)
        elif isinstance(node, list):
            stack.extend(node[:250])
    return {
        "top_level_keys": sorted(str(x)[:60] for x in data.keys())[:35],
        "graph_related_fields": counts["graph_related_fields"],
        "tensor_related_fields": counts["tensor_related_fields"],
        "tensor_shapes_sample": shapes,
        "visited_nodes": visited,
        "schema_preview": preview_schema(data),
        "traversal_capped": bool(stack),
    }


def limit_child_resources() -> None:
    # Limit total virtual memory, CPU time, and output file size.
    if resource is None:
        return
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (18, 18))
    resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024**2, 4 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_context_probe(path: Path, output_root: Path) -> dict[str, object]:
    binary = shutil.which("qnn-context-binary-utility")
    if not binary:
        return {"status": "skipped", "reason": "utility-not-installed"}
    with tempfile.TemporaryDirectory(prefix="myai-qnn-info-", dir=output_root) as temp:
        base = Path(temp)
        metadata_file = base / "context-metadata.json"
        log_file = base / "tool-output.log"
        with log_file.open("wb") as logfile:
            try:
                completed = subprocess.run(
                    [
                        binary, "--context_binary", str(path),
                        "--json_file", str(metadata_file),
                    ],
                    cwd=base,
                    stdout=logfile,
                    stderr=subprocess.STDOUT,
                    timeout=TIMEOUT_SECONDS,
                    preexec_fn=limit_child_resources,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return {"status": "inconclusive", "reason": "utility-timeout"}
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                return {"status": "inconclusive", "reason": type(exc).__name__}
        if completed.returncode:
            return {
                "status": "inconclusive",
                "reason": "utility-nonzero-exit",
                "exit_code": completed.returncode,
            }
        if not metadata_file.is_file():
            return {"status": "inconclusive", "reason": "no-json-output"}
        if metadata_file.stat().st_size > MAX_OUTPUT_BYTES:
            return {"status": "inconclusive", "reason": "json-output-too-large"}
        try:
            data = json.loads(metadata_file.read_text(errors="replace"))
        except (OSError, ValueError):
            return {"status": "inconclusive", "reason": "json-not-parsable"}
        return {"status": "metadata-read", "summary": summarize_context_metadata(data)}


def main() -> int:
    home = Path.home()
    roots = (
        home / ".cache" / "geniex",
        home / ".local" / "share" / "geniex" / "cache",
        home / ".local" / "share" / "geniex" / "models",
    )
    available = read_available_kib()
    print("QNN metadata probe; available RAM MiB:", round(available / 1024))
    candidates = find_context_candidates(roots)
    print("Cached binary candidates:", len(candidates))
    if available < MIN_AVAILABLE_KIB:
        print("Probe skipped: insufficient available memory")
        return 0
    if not candidates:
        print("Probe skipped: no suitably bounded binary")
        return 0
    selected, size = candidates[0]
    print("Selected binary size MiB:", round(size / 1048576, 1))
    output_root = Path(os.environ.get("RUNNER_TEMP", "/tmp"))
    if not output_root.is_dir() or output_root.is_symlink():
        print("Probe skipped: temporary location invalid")
        return 0
    outcome = run_context_probe(selected, output_root)
    print("Metadata probe outcome:", json.dumps(outcome, sort_keys=True))
    print("No model was loaded for inference and no systemd services were modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
