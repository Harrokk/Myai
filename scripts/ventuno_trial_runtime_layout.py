"""Fail-closed source and filesystem boundary checks for disposable pilot paths.

For staging only; no directory/database or temporary file is created. Even
passing checks does NOT authorize a real microphone or device action.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

PREFIX = PurePosixPath("runtime/isolated_voice_trial")
PAIRS = (
    ("memory", "database"),
    ("error_logging", "path"),
    ("audit_logging", "path"),
    ("runtime", "heartbeat_path"),
    ("health", "state_path"),
    ("geniex_supervisor", "state_path"),
    ("stability_analysis", "log_path"),
    ("files", "workspace_root"),
)


def inspect(settings, checkout_root):
    trusted = False
    try:
        root = Path(checkout_root)
        # Explicitly deny any installed production subtree.
        resolved = root.resolve(strict=True)
        production = Path("/home/arduino/MyAI")
        if (root.is_symlink() or not root.is_dir()
                or resolved == production
                or production in resolved.parents):
            raise ValueError("Untrusted runtime root")
        for section, key in PAIRS:
            value = settings[section][key]
            if type(value) is not str:
                raise ValueError("Unreviewed path")
            p = PurePosixPath(value)
            if (p.is_absolute() or ".." in p.parts
                    or p.parts[:2] != PREFIX.parts
                    or len(p.parts) <= len(PREFIX.parts)):
                raise ValueError("Unreviewed stage output")
            actual = root
            for component in p.parts:
                actual = actual / component
                # Any existing symlink at ANY parent or leaf must block.
                if actual.is_symlink():
                    raise ValueError("Symbolic link in stage path")
            if not actual.resolve(strict=False).is_relative_to(resolved):
                raise ValueError("Escaped stage root")
        trusted = True
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        trusted = False
    return {
        "status": ("source-stage-file-layout-guard-passed" if trusted
                   else "blocked-unsafe-stage-file-layout"),
        "source_stage_file_boundary_trusted": trusted,
        "sqlite_or_audio_file_created": False,
        "symlinks_allowed": False,
        "native_model_loaded": False,
        "user_audio_captured": False,
        "runtime_activation_authorized": False,
    }


def main():
    from core.config import DEFAULT_SETTINGS, _merge_settings
    root = Path(__file__).resolve().parents[1]
    stage = json.loads((root / "config/profiles/ventuno_voice_trial_DISABLED.json").read_text())
    settings = _merge_settings(DEFAULT_SETTINGS, stage)
    report = inspect(settings, root)
    print("MYAI_VOICE_TRIAL_LAYOUT_JSON=" + json.dumps(report, sort_keys=True))
    return 0 if report["source_stage_file_boundary_trusted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
