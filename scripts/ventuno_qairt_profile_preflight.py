"""Non-invasive QAIRT profiling preflight for a live VENTUNO Q.

Only reads process metadata, local model inventory and public GenieX API.
Never starts a second model, requests QNN execution or changes the service.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections import deque
from pathlib import Path
from urllib.request import urlopen

MODEL_SUFFIXES = {".bin", ".so", ".dlc", ".gguf"}
MAX_DIRS = 250
MAX_FILES = 1200


def parse_memory_kib(content: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in content.splitlines():
        name, sep, remainder = line.partition(":")
        if not sep or name not in {"MemTotal", "MemAvailable"}:
            continue
        fields = remainder.strip().split()
        if fields and fields[0].isdigit():
            result[name] = int(fields[0])
    return result


def catalog_models(
    roots: tuple[Path, ...], max_dirs: int = MAX_DIRS, max_files: int = MAX_FILES
) -> dict[str, object]:
    """Bounded, symlink-free metadata search; never open model contents."""
    queue = deque((root, 0) for root in roots if root.is_dir())
    checked_dirs = checked_files = 0
    model_files: list[tuple[str, int]] = []
    while queue and checked_dirs < max_dirs and checked_files < max_files:
        current, depth = queue.popleft()
        checked_dirs += 1
        try:
            with os.scandir(current) as iterator:
                entries = list(iterator)
        except OSError:
            continue
        for entry in entries:
            if checked_files >= max_files:
                break
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if depth < 5:
                        queue.append((Path(entry.path), depth + 1))
                elif entry.is_file(follow_symlinks=False):
                    checked_files += 1
                    if Path(entry.name).suffix.lower() in MODEL_SUFFIXES:
                        model_files.append((entry.name, entry.stat(follow_symlinks=False).st_size))
            except OSError:
                continue
    sizes = sorted((size for _, size in model_files), reverse=True)
    suffix_counts = {
        suffix: sum(Path(name).suffix.lower() == suffix for name, _ in model_files)
        for suffix in sorted(MODEL_SUFFIXES)
    }
    return {
        "directories_checked": checked_dirs,
        "files_checked": checked_files,
        "scan_capped": bool(queue or checked_files >= max_files),
        "model_file_counts": suffix_counts,
        "largest_model_file_mib": [round(s / 1048576, 1) for s in sizes[:5]],
    }


def geniex_rss_kib(proc_root: Path = Path("/proc")) -> tuple[list[int], int]:
    pids: list[int] = []
    total_kib = 0
    try:
        processes = list(proc_root.iterdir())
    except OSError:
        return pids, total_kib
    for proc in processes:
        if not proc.name.isdigit():
            continue
        try:
            if (proc / "comm").read_text().strip() != "geniex":
                continue
            status = (proc / "status").read_text(errors="replace")
        except OSError:
            continue
        pids.append(int(proc.name))
        for line in status.splitlines():
            if line.startswith("VmRSS:"):
                tokens = line.split()
                if len(tokens) > 1 and tokens[1].isdigit():
                    total_kib += int(tokens[1])
                break
    return sorted(pids), total_kib


def installed_models() -> tuple[list[str], str]:
    # GenieX's list command is metadata-only; suppress raw output to avoid
    # exposing user-specific cache paths to public CI logs.
    if not shutil.which("geniex"):
        return [], "not installed"
    try:
        completed = subprocess.run(
            ["geniex", "list"], capture_output=True, text=True, errors="replace",
            timeout=12, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], type(exc).__name__
    found = [
        model for model in (
            "Qwen3-4B-Instruct-2507", "Qwen3-4B",
        ) if model.lower() in completed.stdout.lower()
    ]
    return found, "ok" if completed.returncode == 0 else "CLI exited nonzero"


def main() -> int:
    home = Path.home()
    print("=== QAIRT profile preflight (metadata-only) ===")
    print("QNN profile-viewer installed:", bool(shutil.which("qnn-profile-viewer")))
    print("QNN net-run installed:", bool(shutil.which("qnn-net-run")))
    print("QNN context utility installed:", bool(shutil.which("qnn-context-binary-utility")))

    try:
        memory = parse_memory_kib(Path("/proc/meminfo").read_text())
    except OSError:
        memory = {}
    print("Memory MiB:", json.dumps({
        key: round(value / 1024, 1) for key, value in memory.items()
    }, sort_keys=True))
    pids, rss = geniex_rss_kib()
    print("GenieX process count:", len(pids))
    print("GenieX process RSS MiB:", round(rss / 1024, 1))
    print("GenieX processes alive:", bool(pids))

    try:
        with urlopen("http://127.0.0.1:18181/v1/models", timeout=8) as response:
            catalog = json.load(response).get("data", [])
        # Only public model identifiers; no model config/credentials.
        print("Served models:", [m.get("id", "")[:120] for m in catalog[:5]])
    except (OSError, ValueError, TypeError) as exc:
        print("Served model catalog unavailable:", type(exc).__name__)

    models, state = installed_models()
    print("GenieX cached-model listing:", state, "known Qwen matches:", models)

    root_candidates = (
        home / ".cache" / "geniex",
        home / ".local" / "share" / "geniex" / "models",
        home / ".local" / "share" / "geniex" / "cache",
        home / ".cache" / "qairt",
    )
    roots = tuple(root for root in root_candidates if root.is_dir())
    print("Known cache roots found:", len(roots))
    print("Cache model-file metadata:", json.dumps(catalog_models(roots), sort_keys=True))
    print("No inference, profile session, SDK installation or service changes performed.")
    print("QNN profile-viewer cannot generate profiler logs; it only reads existing logs.")
    print("Profiling an existing GenieX QAIRT session requires supported in-process instrumentation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
