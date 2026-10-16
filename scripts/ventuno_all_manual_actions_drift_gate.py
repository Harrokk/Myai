"""Source-only all-manual Actions drift lock (103 workflows at initial audit).

The baseline includes every workflow_dispatch file, not just 56 workflows
matching sensitive keywords. No source inventory authorizes execution, and
unknown reusable actions/secondary script effects remain a manual release gate.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import ventuno_workflow_release_review as review
from scripts import ventuno_manual_actions_triage_gate as triage

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = "config/ventuno_all_manual_actions_20261016.json"


def _read(path):
    try:
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 32768:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None


def inspect(root=ROOT, *, manifest_path=None):
    root = Path(root)
    manifest = _read(Path(manifest_path) if manifest_path else root / MANIFEST)
    valid = isinstance(manifest, dict) and all((
        type(manifest.get("schema")) is int and manifest.get("schema") == 1,
        manifest.get("physical_authorized") is False,
        manifest.get("merge_authorized") is False,
        manifest.get("production_deploy_authorized") is False,
        type(manifest.get("manually_dispatchable_count")) is int
        and manifest.get("manually_dispatchable_count") == 103,
        type(manifest.get("keyword_sensitive_manual_count")) is int
        and manifest.get("keyword_sensitive_manual_count") == 56,
    ))
    all_files = manifest.get("all_manual_workflow_filenames") if valid else None
    extra = manifest.get("non_keyword_manual_workflow_filenames") if valid else None
    if not (isinstance(all_files, list) and len(all_files) == 103
            and isinstance(extra, list) and len(extra) == 47
            and all(type(x) is str and x.endswith((".yml", ".yaml"))
                    and "/" not in x and len(x) <= 128
                    for x in all_files + extra)
            and len(set(all_files)) == 103 and len(set(extra)) == 47
            and set(extra).issubset(all_files)):
        valid = False

    report = review.inventory(root, branch="main")
    actual = report.get("all_manual_workflow_filenames") if isinstance(report, dict) else None
    unknown = report.get("unknown_event_workflow_filenames") if isinstance(report, dict) else None
    primary = triage.reconcile(root, branch="main")
    # The 56 primary sensitive candidates must be exact and already checked
    # by the two disjoint job-level quarantine inventories.
    primary_manifest = triage._load_manifest(root / triage.MANIFEST)
    groups = primary_manifest.get("groups") if isinstance(primary_manifest, dict) else None
    original_56 = set(
        x for group in groups.values() for x in group
    ) if isinstance(groups, dict) and all(isinstance(x, list)
                                         for x in groups.values()) else set()

    actual_set = set(actual) if isinstance(actual, list) and all(type(x) is str for x in actual) else set()
    expected_set = set(all_files) if valid else set()
    unexpected = sorted(actual_set - expected_set)
    missing = sorted(expected_set - actual_set)
    safe = all((
        valid, isinstance(actual, list), len(actual) == 103,
        len(actual_set) == 103, not unexpected, not missing,
        isinstance(unknown, list) and not unknown,
        report.get("candidate_automatic_clear") is True,
        report.get("status") == "inventory-complete-not-release-authorized",
        primary.get("source_triage_complete") is True,
        original_56 == (expected_set - set(extra) if valid else set()),
    ))
    return {
        "status": ("all-103-manual-action-names-accounted-no-release"
                   if safe else "blocked-unaccounted-manual-action"),
        "baseline_manual_count": 103,
        "observed_manual_count": len(actual) if isinstance(actual, list) else None,
        "keyword_sensitive_manual_count": 56,
        "additional_non_keyword_manual_count": 47,
        "new_manual_filenames": unexpected[:10],
        "missing_manual_filenames": missing[:10],
        "unparsed_trigger_count": len(unknown) if isinstance(unknown, list) else None,
        "manual_workflow_source_inventory_complete": safe,
        "indirect_script_and_action_security_certified": False,
        "all_manual_jobs_authorized": False,
        "physical_tests_authorized": False,
        "main_merge_authorized": False,
        "production_deploy_authorized": False,
    }


def main():
    result = inspect()
    print("MYAI_ALL_MANUAL_WORKFLOWS_JSON=" + json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "all-103-manual-action-names-accounted-no-release" else 2


if __name__ == "__main__":
    raise SystemExit(main())
