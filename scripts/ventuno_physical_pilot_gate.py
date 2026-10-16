"""Bounded read-only readiness gate for the NEXT separately consented voice test.

This file CANNOT capture/play audio, load a model, install packages,
enable voice or approve a hardware run. Results contain fixed booleans
and category strings only, never device labels, transcripts or paths.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess


HEX_SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_PROFILE_BYTES = 65536
PROFILE_RELATIVE = Path("config/profiles/ventuno_q.json")
PRODUCTION_ROOT = Path("/home/arduino/MyAI")
BOARD_STATUS_CODES = frozenset({
    "ready-for-separate-consented-dialogue-test",
    "blocked-architecture",
    "blocked-inactive-services",
    "blocked-active-voice-or-invalid-config",
    "blocked-usb-reenumerated-or-inaccessible",
    "blocked-whisper-8gib-memory-reserve",
    "blocked-temporary-staging-disk-reserve",
})
SAFE_FLAGS = {
    "voice": ("enabled", "tts_enabled", "handsfree_enabled"),
    "ventuno": ("rpc_write_enabled",),
    "geniex_supervisor": ("restart_enabled",),
    "selfdev": ("enabled", "promotion_enabled"),
    "camera": ("enabled", "stream_enabled"),
    "location": ("enabled",),
    "trusted_terminals": ("enabled", "auto_execute"),
    "excel": ("write_enabled",),
}


def _config_safe(profile):
    return isinstance(profile, dict) and all(
        isinstance(profile.get(section), dict)
        and all(profile[section].get(flag) is False for flag in flags)
        for section, flags in SAFE_FLAGS.items()
    )


def classify(profile, *, expected_sha, actual_sha, board=None,
             active_profile=None):
    """Pure safety classifier: source acceptance is NOT recording consent."""
    same_commit = (
        isinstance(expected_sha, str)
        and isinstance(actual_sha, str)
        and HEX_SHA.fullmatch(expected_sha) is not None
        and expected_sha == actual_sha
    )
    config_ok = _config_safe(profile)
    isolated = board is None
    active_ok = _config_safe(active_profile) if not isolated else False
    board_reason = (
        "not-inspected" if isolated else
        board.get("status", "") if isinstance(board, dict) else ""
    )
    if board_reason not in BOARD_STATUS_CODES and not isolated:
        board_reason = "blocked-unrecognised-readiness"
    board_ok = (
        isolated
        or (
            active_ok
            and isinstance(board, dict)
            and board.get("status") == "ready-for-separate-consented-dialogue-test"
            and board.get("arm64") is True
            and board.get("services_active") is True
            and board.get("production_voice_disabled") is True
            and board.get("usb_capture_and_playback_1_0_accessible") is True
            and board.get("ram_gate_passed") is True
            and board.get("disk_gate_passed") is True
            and board.get("physical_dialogue_attempted") is False
            and board.get("microphone_opened") is False
            and board.get("speaker_opened") is False
            and board.get("model_loaded") is False
            and board.get("production_changed") is False
        )
    )
    passed = same_commit and config_ok and board_ok
    if not same_commit:
        status = "blocked-unpinned-source"
    elif not config_ok:
        status = "blocked-unsafe-production-profile"
    elif not isolated and not active_ok:
        status = "blocked-active-production-profile"
    elif not board_ok:
        status = "blocked-read-only-board-preflight"
    elif isolated:
        status = "source-only-preflight-passed"
    else:
        status = "board-readonly-preflight-passed"
    return {
        "status": status,
        "source_exact_sha": same_commit,
        "source_config_default_off": config_ok,
        "board_preflight_included": not isolated,
        "board_preflight_passed": (board_ok if not isolated else False),
        "board_readiness_reason": board_reason,
        "active_production_profile_default_off": active_ok,
        "ready_for_separate_human_consent": passed and not isolated,
        "recording_authorized": False,
        "playback_authorized": False,
        "physical_recording_attempted": False,
        "speaker_opened": False,
        "model_loaded": False,
        "npu_tested": False,
        "production_changed": False,
        "needs_new_one_shot_audio_consent": True,
    }


def _get_source_profile(root):
    path = root / PROFILE_RELATIVE
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_PROFILE_BYTES:
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def _get_exact_head(root):
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, check=False, timeout=4,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode or len(result.stdout) > 80:
        return ""
    return result.stdout.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--board-readonly", action="store_true")
    args = parser.parse_args(argv)

    # Never load potentially hardware-facing imports unless the caller
    # explicitly selected read-only inventory mode. No consent flags
    # or switches to open a microphone exist in this script.
    board = None
    active_profile = None
    if args.board_readonly:
        from scripts.ventuno_usb_voice_dialog_readiness import inspect
        board = inspect()
        active_profile = _get_source_profile(PRODUCTION_ROOT)
    try:
        profile = _get_source_profile(args.source_root)
        actual_sha = _get_exact_head(args.source_root)
    except (OSError, ValueError, TypeError):
        profile, actual_sha = None, ""
    result = classify(
        profile, expected_sha=args.expected_sha,
        actual_sha=actual_sha, board=board,
        active_profile=active_profile,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {
        "source-only-preflight-passed",
        "board-readonly-preflight-passed",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
