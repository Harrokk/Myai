#!/usr/bin/env python3
"""Verify whether forbidden runtime/user-data artifacts remain in Git history."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


FORBIDDEN_BASENAMES = {
    "memory.db",
    "__init__.cpython-314.pyc",
    "system.cpython-314.pyc",
}


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def find_forbidden_history_paths() -> list[tuple[str, str]]:
    output = _git("rev-list", "--objects", "--all")
    matches: list[tuple[str, str]] = []

    for line in output.splitlines():
        line = line.strip()

        if not line:
            continue

        parts = line.split(" ", 1)

        if len(parts) != 2:
            continue

        object_id, path = parts

        if Path(path).name in FORBIDDEN_BASENAMES:
            matches.append((object_id, path))

    return matches


def main() -> int:
    matches = find_forbidden_history_paths()

    if matches:
        print("Historiksanering INTE klar. Förbjudna objekt är fortfarande nåbara:")
        for object_id, path in matches:
            print(f"- {object_id}  {path}")
        return 1

    print("Historiksanering verifierad: inga förbjudna objekt är nåbara via branches/tags.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
