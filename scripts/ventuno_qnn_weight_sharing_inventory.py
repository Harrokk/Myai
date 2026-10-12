"""Bounded read-only HTP weight-sharing declaration inventory for VENTUNO.

Checks only known GenieX cache configuration file names and emits aggregate
boolean evidence. Does not load model binaries, print file paths/config JSON,
start inference, mutate settings, or alter systemd services.
"""
from __future__ import annotations

import json
import os
from collections import Counter, deque
from pathlib import Path

CONFIG_BASENAME = "htp_backend_ext_config.json"
KEYS = frozenset({"weight_sharing_enabled", "weightSharingEnabled"})
MAX_DIRS = 180
MAX_FILES = 700
MAX_JSON_BYTES = 128 * 1024
MAX_VISITED_NODES = 900


def summarize_declaration(payload: object) -> str:
    """Report only a tri-state declaration; never return source values."""
    pending = deque([(payload, 0)])
    values: set[bool] = set()
    invalid = False
    visited = 0
    while pending and visited < MAX_VISITED_NODES:
        node, depth = pending.popleft()
        visited += 1
        if not isinstance(node, dict) or depth >= 8:
            continue
        for key, val in node.items():
            if key in KEYS:
                if type(val) is bool:
                    values.add(val)
                else:
                    invalid = True
            elif isinstance(val, dict):
                pending.append((val, depth + 1))
            elif isinstance(val, list):
                for item in val[:30]:
                    if isinstance(item, dict):
                        pending.append((item, depth + 1))
    if invalid or len(values) > 1:
        return "conflicting-or-invalid"
    if pending:
        return "inconclusive-scan-capped"
    if values == {True}:
        return "declared-enabled"
    if values == {False}:
        return "declared-disabled"
    return "not-declared"


def scan_roots(roots: tuple[Path, ...]) -> dict[str, object]:
    """Visit bounded, nonsymlinked roots; open only a tiny allowlisted JSON."""
    queue = deque(
        (root, 0) for root in roots if root.is_dir() and not root.is_symlink()
    )
    scanned_dirs = scanned_files = 0
    statuses: Counter[str] = Counter()
    while queue and scanned_dirs < MAX_DIRS and scanned_files < MAX_FILES:
        folder, depth = queue.popleft()
        scanned_dirs += 1
        try:
            with os.scandir(folder) as iterator:
                entries = list(iterator)
        except OSError:
            continue
        for entry in entries:
            if scanned_files >= MAX_FILES:
                break
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if depth < 5:
                        queue.append((Path(entry.path), depth + 1))
                elif entry.is_file(follow_symlinks=False):
                    scanned_files += 1
                    if entry.name != CONFIG_BASENAME:
                        continue
                    if entry.stat(follow_symlinks=False).st_size > MAX_JSON_BYTES:
                        statuses["file-too-large"] += 1
                        continue
                    try:
                        data = json.loads(Path(entry.path).read_text(
                            encoding="utf-8", errors="replace"
                        ))
                    except (OSError, ValueError):
                        statuses["unreadable-or-invalid-json"] += 1
                    else:
                        statuses[summarize_declaration(data)] += 1
            except OSError:
                continue
    return {
        "files_inspected": sum(statuses.values()),
        "declaration_status_counts": dict(sorted(statuses.items())),
        "scan_capped": bool(queue or scanned_files >= MAX_FILES),
        "runtime_weight_sharing_proven": False,
        "safe_to_start_second_model": False,
    }


def main() -> int:
    home = Path.home()
    roots = (
        home / ".cache" / "geniex",
        home / ".local" / "share" / "geniex" / "models",
        home / ".local" / "share" / "geniex" / "cache",
    )
    print("HTP weight-sharing configuration declaration inventory (read-only)")
    print(json.dumps(scan_roots(roots), sort_keys=True))
    print("Cached config declarations are not proof that the live model uses them.")
    print("No model loaded, QNN profile started, service stopped, or configuration changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
