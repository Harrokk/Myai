"""Fail-closed source triage for ALL manually dispatchable sensitive Actions.

This tool reads checked-out source files only. It does not parse arbitrary
GitHub expressions, execute Actions, load models, access devices or authorize
release. It catches source drift relative to a *reviewed* 56-file candidate
list, including a newly added manual job not on the recorded baseline.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import ventuno_workflow_release_review as workflows
from scripts import ventuno_legacy_inference_quarantine as ten
from scripts import ventuno_five_real_model_job_quarantine as five

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = "config/ventuno_manual_workflow_triage_20261016.json"
GROUP_COUNTS = {
    "15 disabled model/GenieX/HTP jobs": 15,
    "12 metadata, inventory or dry-run workflows": 12,
    "27 synthetic tests or source-only controls": 27,
    "2 dependency staging or hosted CPU conversion": 2,
}


def _load_manifest(path):
    try:
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 32768:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None


def reconcile(root=ROOT, *, manifest_path=None, branch="main"):
    root = Path(root)
    path = Path(manifest_path) if manifest_path is not None else root / MANIFEST
    contents = _load_manifest(path)
    baseline = {}
    valid = (
        isinstance(contents, dict)
        and type(contents.get("schema")) is int
        and contents["schema"] == 1
        and contents.get("release_authorized") is False
        and contents.get("physical_test_authorized") is False
    )
    if valid:
        groups = contents.get("groups")
        valid = isinstance(groups, dict) and set(groups) == set(GROUP_COUNTS)
        if valid:
            for label, count in GROUP_COUNTS.items():
                files = groups.get(label)
                if (not isinstance(files, list) or len(files) != count
                        or any(not isinstance(f, str)
                               or not f.endswith((".yml", ".yaml"))
                               or "/" in f or len(f) > 128
                               for f in files)
                        or len(set(files)) != len(files)):
                    valid = False
                    break
                baseline[label] = files
    expected = [x for xs in baseline.values() for x in xs] if valid else []
    if len(expected) != 56 or len(set(expected)) != 56:
        valid = False

    scan = workflows.inventory(root, branch=branch)
    risks = scan.get("risks") if isinstance(scan, dict) else None
    actual = sorted(
        r["filename"] for r in risks
        if isinstance(r, dict) and r.get("manual_dispatch") is True
        and type(r.get("filename")) is str
    ) if isinstance(risks, list) else []
    expected_set = set(expected)
    unexpected = sorted(set(actual) - expected_set)
    missing = sorted(expected_set - set(actual))
    disabled = set(ten.DISABLED) | set(five.REQUIRED)
    old_report = ten.verify(root)
    new_report = five.verify(root)
    passed = all((
        valid,
        not unexpected,
        not missing,
        len(actual) == 56,
        isinstance(scan, dict),
        scan.get("status") == "inventory-complete-not-release-authorized",
        scan.get("candidate_automatic_clear") is True,
        set(baseline.get("15 disabled model/GenieX/HTP jobs", [])) == disabled,
        old_report.get("confirmed_disabled") == 10,
        new_report.get("confirmed_inert") == 5,
    ))
    return {
        "status": ("all-56-source-triage-stable-not-authorized"
                   if passed else "blocked-source-triage-drift"),
        "expected": 56,
        "observed": len(actual),
        "new_unreviewed_count": len(unexpected),
        "missing_from_scanner_count": len(missing),
        "new_unreviewed_filenames": unexpected[:10],
        "missing_from_scanner_filenames": missing[:10],
        "quarantined_model_jobs_expected": 15,
        "quarantined_model_jobs_verified": (
            old_report.get("confirmed_disabled", 0) +
            new_report.get("confirmed_inert", 0)
        ),
        "source_triage_complete": passed,
        "full_action_semantics_verified": False,
        "physical_tests_authorized": False,
        "production_deployment_authorized": False,
        "main_merge_authorized": False,
    }


def main():
    result = reconcile()
    print("MYAI_MANUAL_ACTIONS_TRIAGE_JSON=" + json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "all-56-source-triage-stable-not-authorized" else 2


if __name__ == "__main__":
    raise SystemExit(main())
