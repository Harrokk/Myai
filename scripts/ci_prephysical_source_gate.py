"""OFF-HOST source release gate for the NEXT separately consented board preflight.

This is deliberately NOT a production deployment or physical voice-test tool:
no microphone, NPU, model inference, network, packages, services or VENTUNO
is touched. It cannot authorize a recording or enable tiered verification.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from core.voice_candidate_hosted_releases import hosted_model_release
from core.voice_risk_policy import classify_voice_tier
from core.voice_verification import verify_tiered_transcripts
from scripts.ventuno_physical_pilot_gate import (
    _get_source_profile, classify as classify_source,
)


_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
# Historical self-hosted audio jobs must remain INERT, irrespective of a push
# to an old branch. They are not allowed to inherit earlier consent.
_HISTORICAL_DISABLED_AUDIO_JOBS = (
    (".github/workflows/ventuno-microphone-consent-once.yml", "microphone"),
    (".github/workflows/ventuno-microphone-plughw-once.yml", "microphone"),
    (".github/workflows/ventuno-usb-live-dialog-consent-once.yml", "dialogue"),
    (".github/workflows/ventuno-one-consented-voice-smoke-20261022.yml", "dialogue"),
    (".github/workflows/ventuno-consented-acoustic-metadata-smoke-20261023.yml", "dialogue"),
    (".github/workflows/ventuno-consented-cue-smoke-20261023.yml", "dialogue"),
)
_REQUIRED_REVIEWED_FILES = (
    "core/voice_plan_attestation.py",
    "core/voice_verification.py",
    "core/voice_risk_policy.py",
    "core/voice_tier_authorization.py",
    "core/voice_model_provenance.py",
    "core/config_validation.py",
    "scripts/ventuno_physical_pilot_gate.py",
    "scripts/ventuno_usb_voice_dialog_readiness.py",
    "scripts/ventuno_big_test_readiness.py",
    ".github/workflows/tests.yml",
)


def _clean_exact_git_head(root):
    """Do not attest modified tracked source or a ref different from HEAD."""
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=6, check=False,
        )
        dirty = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain",
             "--untracked-files=no"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=6, check=False,
        )
        if (head.returncode or dirty.returncode or dirty.stdout
                or not _SHA40.fullmatch(head.stdout.strip())):
            return ""
        return head.stdout.strip()
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return ""



def _historical_audio_jobs_inert(root):
    """Fail closed unless ALL six old audio workflows have one inert job.

    An unexpected second job, duplicate if, or changed runner is unsafe,
    even if the original microphone/dialogue job retains if: false.
    This is a narrow structural source check, not a full YAML semantic
    parser, and cannot inspect other GitHub refs.
    """
    for path_name, job_name in _HISTORICAL_DISABLED_AUDIO_JOBS:
        path = root / path_name
        if not path.is_file() or path.is_symlink():
            return False
        try:
            if path.stat().st_size > 32_768:
                return False
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return False
        if len(re.findall(r"(?m)^jobs:[ \t]*$", source)) != 1:
            return False
        jobs = source.split("jobs:\n", 1)
        if len(jobs) != 2:
            return False
        block = jobs[1]
        job_names = re.findall(
            r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):[ \t]*$", block
        )
        if job_names != [job_name]:
            return False
        header_and_steps = block.split("  " + job_name + ":\n", 1)
        if len(header_and_steps) != 2:
            return False
        contents = header_and_steps[1].split("    steps:\n", 1)
        if len(contents) != 2:
            return False
        header = contents[0]
        # Quoted YAML strings and expressions cannot replace literal false.
        guards = re.findall(r"(?m)^    if:[^\n]*$", header)
        if guards != ["    if: false"]:
            return False
        runners = re.findall(r"(?m)^    runs-on:[^\n]*$", header)
        if runners != ["    runs-on: [self-hosted, Linux, ARM64, ventuno-q]"]:
            return False
    return True

def _security_smoke():
    """Offline denial witnesses, never callable permission receipts."""
    models = {
        "p": {"family": "parakeet", "revision": "source-only"},
        "c": {"family": "canary", "revision": "source-only"},
        "w": {"family": "whisper", "revision": "source-only"},
    }
    disagree = verify_tiered_transcripts(
        "critical",
        [
            {"model_key": "p", "text": "Radera inte filen"},
            {"model_key": "c", "text": "Radera filen"},
            {"model_key": "w", "text": "Radera filen"},
        ],
        models,
    )
    duplicate_family = verify_tiered_transcripts(
        "critical",
        [
            {"model_key": "p", "text": "Radera filen"},
            {"model_key": "c", "text": "Radera filen"},
            {"model_key": "w", "text": "Radera filen"},
        ],
        {**models, "c": {"family": "whisper", "revision": "source-only"}},
    )
    tier = classify_voice_tier("Radera filen", {"steps": []}, {})
    models_pinned = (
        hosted_model_release("canary-1b-v2-q8").family == "canary"
        and hosted_model_release("whisper-small-q5_1").family == "whisper"
        and hosted_model_release("canary-1b-v2-q8").revision
        != hosted_model_release("whisper-small-q5_1").revision
    )
    return bool(
        disagree.get("accepted") is False
        and duplicate_family.get("accepted") is False
        and duplicate_family.get("reason") == "same_model_family"
        and tier["tier"] == "critical"
        and models_pinned
    )


def assess(root, expected_sha, actual_sha, profile):
    """Only source-level eligibility for a future *read-only* board inspection."""
    safe_sha = (type(expected_sha) is str
                and bool(_SHA40.fullmatch(expected_sha)))
    gate = classify_source(
        profile, expected_sha=expected_sha,
        actual_sha=actual_sha, board=None,
    )
    known_source_files = all(
        (root / name).is_file() and not (root / name).is_symlink()
        for name in _REQUIRED_REVIEWED_FILES
    )
    staged_risk_off = (
        isinstance(profile, dict)
        and isinstance(profile.get("voice"), dict)
        and profile["voice"].get("risk_tiered_verification_enabled", False)
        is False
    )
    safe_semantics = _security_smoke()
    historical_audio_inert = _historical_audio_jobs_inert(root)
    eligible = all((
        safe_sha,
        gate.get("status") == "source-only-preflight-passed",
        known_source_files,
        staged_risk_off,
        safe_semantics,
        historical_audio_inert,
    ))
    return {
        "status": (
            "hosted-source-ready-for-separate-board-readonly-preflight"
            if eligible else "blocked-offhost-prephysical-gates"
        ),
        "source_commit_exact_and_clean": bool(safe_sha and expected_sha == actual_sha),
        "source_off_profile_safe": gate.get("source_config_default_off") is True,
        "risk_tiered_voice_activation_still_disabled": staged_risk_off,
        "required_audited_gate_files_present": known_source_files,
        "synthetic_security_denial_contracts_pass": safe_semantics,
        "historical_selfhosted_audio_jobs_inert": historical_audio_inert,
        "eligible_to_request_separate_board_readonly_preflight": eligible,
        # SOURCE-ONLY; these must remain false regardless of result.
        "board_physically_inspected_by_this_gate": False,
        "board_audio_or_npu_opened": False,
        "model_weights_placed_on_ventuno": False,
        "production_changed": False,
        "physical_voice_test_authorized": False,
        "critical_command_authorized": False,
        "hardware_evidence_still_required": True,
        "separate_human_consent_still_required": True,
        "three_model_ventuno_runtime_verified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args(argv)
    try:
        root = args.source_root.resolve(strict=True)
        result = assess(
            root, args.expected_sha,
            _clean_exact_git_head(root),
            _get_source_profile(root),
        )
    except Exception:
        result = {
            "status": "blocked-offhost-prephysical-gates",
            "physical_voice_test_authorized": False,
            "critical_command_authorized": False,
            "hardware_evidence_still_required": True,
        }
    print("MYAI_PREPHYSICAL_SOURCE_GATE_JSON=" +
          json.dumps(result, sort_keys=True))
    return 0 if result.get("eligible_to_request_separate_board_readonly_preflight") is True else 2


if __name__ == "__main__":
    sys.exit(main())
