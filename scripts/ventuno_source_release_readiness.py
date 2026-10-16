"""Source-only release checklist, never a permission to activate hardware.

Checks the assembled integration source against frozen reviewed invariants.
Native ABI, physical microphones, real models and independent recovery must
remain explicitly NOT ATTESTED regardless of passing software checks.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

from scripts.ventuno_all_workflow_preflight import inventory as workflows
from scripts.ventuno_isolated_voice_stage_contract import inspect as stage
from scripts.ventuno_main_workflow_quarantine import classify as quarantine
from scripts.ventuno_voice_static_lock_check import inspect as wheel_lock

ROOT = Path(__file__).resolve().parents[1]
MAIN_PARENT = "f125fe6dc9abd6b27747f86d440fbb77b0602e58"
DRAFT_PARENT = "4fdaec5cf4f0b99f9fe01aa524d7684c4743ea94"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


def _git(repo, *args, runner=None):
    runner = subprocess.run if runner is None else runner
    try:
        result = runner(
            ["git", "-C", str(repo), *args],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=15, check=False,
        )
        return result.returncode, result.stdout if len(result.stdout) < 4096 else ""
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 255, ""


def inspect(root=ROOT, *, runner=None):
    root = Path(root)
    status, rev = _git(root, "rev-parse", "--verify", "HEAD", runner=runner)
    sha = rev.strip()
    head_ok = status == 0 and HEX40.fullmatch(sha) is not None
    clean, dirty = _git(root, "status", "--porcelain", "--untracked-files=no",
                        runner=runner)
    tracked_clean = clean == 0 and dirty == ""
    main_ret, _ = _git(root, "merge-base", "--is-ancestor", MAIN_PARENT, "HEAD", runner=runner)
    draft_ret, _ = _git(root, "merge-base", "--is-ancestor", DRAFT_PARENT, "HEAD", runner=runner)
    main_in_history = main_ret == 0
    draft_in_history = draft_ret == 0

    work = workflows(root)
    archived = quarantine(root)
    # Source-only config check compares audited profiles in ROOT rather than
    # the installed production path of the current checkout.
    profile = stage(
        root / "config/profiles/ventuno_q.json",
        root / "config/profiles/ventuno_voice_trial_DISABLED.json",
    )
    pinned = wheel_lock(root)
    all_software = all((
        head_ok, tracked_clean, main_in_history, draft_in_history,
        work["status"] == "no-automatic-hardware-triggers-on-candidate",
        archived["quarantine_verified"],
        profile["candidate_safe_by_contract"],
        pinned["source_lock_consistent"],
    ))
    return {
        "status": ("source-candidate-consistent-but-not-deploy-authorized"
                   if all_software else "blocked-source-candidate"),
        "head_is_exact_sha": bool(head_ok),
        "tracked_checkout_clean": bool(tracked_clean),
        "main_reviewed_parent_ancestor": main_in_history,
        "draft_reviewed_parent_ancestor": draft_in_history,
        "all_main_only_workflows_quarantined": archived["quarantine_verified"],
        "no_candidate_branch_auto_hardware_triggers": work["status"] == "no-automatic-hardware-triggers-on-candidate",
        "source_voice_trial_config_off": profile["candidate_safe_by_contract"],
        "voice_wheel_source_lock_consistent": pinned["source_lock_consistent"],
        "physical_operator_present": False,
        "installed_voice_native_abi_signed_off": False,
        "full_voice_model_inference_verified": False,
        "hardware_stop_and_rollback_physically_verified": False,
        "npu_htp_profiler_verified": False,
        "merge_to_main_authorized": False,
        "production_deploy_authorized": False,
    }


def main():
    result = inspect()
    print("MYAI_SOURCE_RELEASE_READINESS_JSON=" + json.dumps(result, sort_keys=True))
    # In a shallow CI checkout, missing ancestry is NO-GO, never guessing.
    return 0 if result["status"].startswith("source-candidate-consistent") else 2


if __name__ == "__main__":
    raise SystemExit(main())
