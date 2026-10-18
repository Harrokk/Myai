"""Fail-closed, READ-ONLY inventory of VENTUNO self-hosted workflow exposures.

This detects source hints and five explicitly inspected historical Git refs.
It DOES NOT query runner registration/group access, evaluate GitHub Actions YAML
or expressions fully, authorize old-branch executions, or interact with VENTUNO.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = "config/ventuno_historical_runner_ref_exposure_20261018.json"
WORKFLOWS = ".github/workflows"
MAX_EVIDENCE_BYTES = 16384
MAX_WORKFLOW_BYTES = 262144
MAX_WORKFLOWS = 400
LABELS_HOSTED = frozenset({
    "ubuntu-24.04-arm", "ubuntu-22.04-arm", "ubuntu-24.04",
    "ubuntu-22.04", "ubuntu-latest", "windows-latest",
    "windows-2025", "windows-2022", "macos-latest",
})
RUNS_ON = re.compile(r"(?m)^[ \t]*runs-on[ \t]*:[ \t]*([^\r\n]*)$")
ON_LINE = re.compile(r"(?m)^on:[ \t]*([^\r\n]*)$")
EVENT_LINE = re.compile(r"(?m)^  ([a-z][a-z0-9_-]*):(?:\s|$)")
PINNED_HISTORY = {
    ("dev/manual-audit-error-redaction-20261016",
     "ventuno-exception-privacy-manual-audit.yml",
     "c743b18a3e1c6f5e4cfcb556f5797dd63c9bd21f"),
    ("dev/manual-audit-actions-sha-pinning-20261017",
     "ventuno-external-actions-pin-audit.yml",
     "c32d32d4ad3815f918922de13e5e7e1ff43c8e1e"),
    ("dev/manual-audit-historical-device-gates-20261016",
     "ventuno-manual-audit-dependency-and-consent.yml",
     "548209900a36b6aa756d626e667930d882aa06a3"),
    ("dev/manual-full-files-and-dns-ssrf-20261017",
     "ventuno-web-socket-ssrf-source-audit.yml",
     "5bcb4e24fd0880ec9844488e88a7e13cc9f72ba7"),
    ("dev/ventuno-audit-source-closeout-20261016",
     "ventuno-final-source-revision-closeout.yml",
     "9f0ef1d59364c3a04f0b6fdcef874bf87820122b"),
}


def _events_hint(source):
    """Only classify bare scalar event names; everything else is unknown."""
    text = re.sub(r"(?m)^[ \t]*#.*$", "", source)
    head = ON_LINE.findall(text)
    if len(head) != 1:
        return "unknown-event-shape"
    if head[0].strip():
        return "unknown-event-shape"
    tail = text[text.index("\non:") + 4:] if "\non:" in text else text[4:]
    event_names = []
    for line in tail.splitlines():
        if line and not line.startswith((" ", "\t")):
            break
        match = EVENT_LINE.match(line)
        if match:
            event_names.append(match.group(1))
    if not event_names:
        return "unknown-event-shape"
    if len(set(event_names)) != len(event_names):
        return "unknown-event-shape"
    if set(event_names) == {"workflow_dispatch"}:
        return "manual-only-source-hint"
    return "automatic-or-indirect-source-hint"


def classify_workflow(source):
    """A static source hint, NEVER proof a job cannot use a self-hosted runner."""
    without_comment_lines = re.sub(r"(?m)^[ \t]*#.*$", "", source)
    raw = RUNS_ON.findall(without_comment_lines)
    risky = []
    hosted = 0
    for value in raw:
        value = value.strip()
        # Even simple YAML aliases, arrays, mappings, and expression outputs
        # must be considered possibly capable of selecting a sensitive runner.
        if value in LABELS_HOSTED:
            hosted += 1
        else:
            risky.append(value[:160] if value else "<multiline-or-empty-selector>")
    # Dynamic/reusable workflows and literal label strings outside runs-on
    # cannot be demonstrated safe with this regex source scan.
    if not raw and re.search(r"(?m)^[ \t]*uses[ \t]*:", without_comment_lines):
        risky.append("<reusable-or-nested-workflow-unknown>")
    return {
        "selector_count": len(raw),
        "static_hosted_selector_count": hosted,
        "potential_self_hosted_or_unknown_selectors": len(risky),
        "selector_examples": risky[:4],
        "trigger_hint": _events_hint(without_comment_lines),
        "full_github_actions_yaml_semantics_verified": False,
        "runner_group_policy_verified": False,
    }


def _history(path):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_EVIDENCE_BYTES:
        return False, []
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            return False, []
        if (obj.get("schema") != 1 or obj.get("observed_on") != "2026-10-18"
                or obj.get("production_runner_access_policy_verified") is not False
                or obj.get("historical_branch_current_execution_state_verified") is not False
                or obj.get("production_release_authorized") is not False):
            return False, []
        records = obj.get("snapshots")
        if not isinstance(records, list) or len(records) != 5:
            return False, []
        if any(not isinstance(x, dict) or set(x) != {"branch", "workflow", "blob_sha"}
               or any(type(x[k]) is not str for k in x) for x in records):
            return False, []
        observed = {(x["branch"], x["workflow"], x["blob_sha"]) for x in records}
        if observed != PINNED_HISTORY or len(observed) != 5:
            return False, []
        return True, [{"branch": b, "workflow": w, "blob_sha": sha}
                      for b, w, sha in sorted(observed)]
    except (OSError, UnicodeError, ValueError, TypeError):
        return False, []


def inspect(root=ROOT):
    root = Path(root)
    evidence_ok = False
    history = []
    files = 0
    potential = []
    source_errors = []
    try:
        evidence_ok, history = _history(root / EVIDENCE_PATH)
        if not evidence_ok:
            source_errors.append("historic-evidence-invalid")
        directory = root / WORKFLOWS
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("invalid-workflow-directory")
        paths = sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml"))
        if not 1 <= len(paths) <= MAX_WORKFLOWS:
            raise ValueError("workflow-count-not-bounded")
        for path in paths:
            if (path.is_symlink() or not path.is_file()
                    or not 0 < path.stat().st_size <= MAX_WORKFLOW_BYTES):
                raise ValueError("invalid-workflow-file")
            info = classify_workflow(path.read_text(encoding="utf-8"))
            files += 1
            if info["potential_self_hosted_or_unknown_selectors"]:
                potential.append({
                    "workflow": path.name,
                    "trigger_hint": info["trigger_hint"],
                    "risky_selectors": info["potential_self_hosted_or_unknown_selectors"],
                })
    except (OSError, ValueError, UnicodeError) as exc:
        source_errors.append(type(exc).__name__)
    inventory_ok = evidence_ok and not source_errors and files > 0
    return {
        "status": ("source-exposure-inventoried-production-no-go"
                   if inventory_ok else "blocked-incomplete-runner-ref-inventory"),
        "source_inventory_complete": inventory_ok,
        "workflow_files_scanned": files,
        "possible_self_hosted_workflow_count": len(potential),
        "possible_auto_or_indirect_workflow_count": sum(
            x["trigger_hint"] != "manual-only-source-hint" for x in potential),
        "possible_runner_workflow_examples": potential[:20],
        "historical_source_snapshots": history,
        "historical_exposure_snapshots_count": len(history),
        "historical_branches_live_runner_access_verified": False,
        "historical_refs_are_not_updated_by_this_check": True,
        "runner_api_group_permissions_verified": False,
        "yaml_expressions_and_reusable_workflows_fully_verified": False,
        "github_actions_job_execution_was_attempted": False,
        "runner_exposure_closed": False,
        "production_deployment_authorized": False,
        "main_merge_authorized": False,
        "source_errors": source_errors,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-production", action="store_true",
                        help="Always fail until actual runner access and old refs are independently verified.")
    args = parser.parse_args(argv)
    result = inspect()
    print("MYAI_RUNNER_REF_EXPOSURE_JSON=" + json.dumps(result, sort_keys=True))
    if args.strict_production:
        return 2
    return 0 if result["source_inventory_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
