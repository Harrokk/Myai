"""Fail-closed bounds for non-production ARM64 audio staging.

The helper does not grant permission for real audio, model inference, service
changes or deployment; it only checks which directory may contain scratch
downloads and an isolated interpreter.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

PRODUCTION_ROOT = Path("/home/arduino/MyAI")


def safe_scratch_root(root: Path, *, production_root: Path = PRODUCTION_ROOT) -> bool:
    """Reject installed MyAI paths, ancestors, and symlinked scratch roots."""
    try:
        root = Path(root)
        if not root.is_dir() or root.is_symlink():
            return False
        scratch = root.resolve(strict=True)
        installed = production_root.resolve()
        return not (
            scratch == installed
            or scratch.is_relative_to(installed)
            or installed.is_relative_to(scratch)
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def authorized_cli_stage(root: Path, env: Mapping[str, str] | None = None) -> bool:
    """Permit the CLI only for the exact CI-created child of RUNNER_TEMP.

    Unit-test functions can exercise stage logic using independent scratch
    fixtures, but direct CLI execution must carry the two matching paths
    established by the workflow. Missing or conflicting paths fail closed.
    """
    env = os.environ if env is None else env
    marker = env.get("MYAI_STAGE_ROOT")
    temp = env.get("RUNNER_TEMP")
    if not marker or not temp:
        return False
    try:
        root = Path(root)
        stage = Path(marker)
        runner = Path(temp)
        return (
            safe_scratch_root(stage)
            and safe_scratch_root(runner)
            and not stage.is_symlink()
            and stage.resolve(strict=True) == root.resolve(strict=True)
            and stage.parent.resolve(strict=True) == runner.resolve(strict=True)
            and stage.name.startswith("myai-native-voice-")
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
