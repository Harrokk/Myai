"""Read-only QNN profiling feasibility probe; no secondary model or service changes."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections import deque
from pathlib import Path

PROFILE_TERMS = ("profil", "optrace", "context", "input_list", "input-list", "binary")
MANIFEST_NAMES = frozenset({
    "geniex.json", "htp_backend_ext_config.json", "config.json", "model.json"
})
MAX_DIRS = 180
MAX_FILES = 850


def parse_help_flags(help_text: str) -> list[str]:
    """Extract option names only; don't leak paths or environment variables."""
    found = set()
    for line in help_text.splitlines():
        if not any(term in line.lower() for term in PROFILE_TERMS):
            continue
        for candidate in re.findall(r"--[a-zA-Z][a-zA-Z0-9_-]*", line):
            found.add(candidate)
    return sorted(found)[:35]


def inspect_manifests(
    roots: tuple[Path, ...],
    max_dirs: int = MAX_DIRS,
    max_files: int = MAX_FILES,
) -> dict[str, object]:
    """Bounded symlink-free scan; reads allowlisted JSON keys, not values."""
    queue = deque((root, 0) for root in roots if root.is_dir() and not root.is_symlink())
    seen_dirs = seen_files = 0
    manifests = []
    qnn_bins = 0
    while queue and seen_dirs < max_dirs and seen_files < max_files:
        current, depth = queue.popleft()
        seen_dirs += 1
        try:
            with os.scandir(current) as entries:
                selected = list(entries)
        except OSError:
            continue
        for entry in selected:
            if seen_files >= max_files:
                break
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if depth < 6:
                        queue.append((Path(entry.path), depth + 1))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                seen_files += 1
                if entry.name.endswith(".bin"):
                    qnn_bins += 1
                if entry.name not in MANIFEST_NAMES or entry.stat().st_size > 131072:
                    continue
                try:
                    obj = json.loads(Path(entry.path).read_text(encoding="utf-8"))
                except (OSError, UnicodeError, ValueError):
                    manifests.append({"filename": entry.name, "json_valid": False})
                    continue
                keys = sorted(str(key) for key in obj.keys()) if isinstance(obj, dict) else []
                # Inspect structural keys only, never model paths, prompts or raw data.
                manifests.append({"filename": entry.name, "json_valid": True, "top_level_keys": keys[:35]})
            except OSError:
                continue
    return {
        "directories": seen_dirs,
        "files": seen_files,
        "capped": bool(queue or seen_files >= max_files),
        "context_or_weight_bin_count": qnn_bins,
        "manifests": manifests[:14],
    }


def command_help(binary: str, subcommand: str | None = None) -> dict[str, object]:
    if not shutil.which(binary):
        return {"binary": binary, "available": False}
    argv = [binary]
    if subcommand:
        argv.append(subcommand)
    argv.append("--help")
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=8,
            errors="replace", check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"binary": binary, "available": True, "error": type(exc).__name__}
    return {
        "binary": binary,
        "available": True,
        "help_exit": result.returncode,
        "profile_relevant_flags": parse_help_flags(result.stdout + "\n" + result.stderr),
    }


def main() -> int:
    print("QAIRT profiling feasibility (read-only)")
    for binary, subcommand in (
        ("qnn-net-run", None),
        ("qnn-context-binary-utility", None),
        ("qnn-profile-viewer", None),
        ("geniex", "infer"),
        ("geniex", "serve"),
    ):
        print("CLI:", json.dumps(command_help(binary, subcommand), sort_keys=True))

    home = Path.home()
    candidates = (
        home / ".cache" / "geniex",
        home / ".local" / "share" / "geniex" / "models",
        home / ".local" / "share" / "geniex" / "cache",
    )
    roots = tuple(root for root in candidates if root.is_dir())
    print("Cache roots inspected:", len(roots))
    print("Manifest structure:", json.dumps(inspect_manifests(roots), sort_keys=True))
    print("Any profiling run needs known QNN graph input tensor data and binary compatibility.")
    print("Readiness inventory only: NO model inference, profile generation, or service pause.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
