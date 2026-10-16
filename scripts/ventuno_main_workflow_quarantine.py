"""Quarantined former main-only workflows MUST be inert in this DRAFT.

Source-only checks: no workflow runs, imports, native models or file writes.
"""
from pathlib import Path
import re

NAMES = (
    "ventuno-full-dev-validation.yml",
    "ventuno-integration-validation.yml",
    "ventuno-regression.yml",
    "ventuno-runner-check.yml",
)
ROOT = Path(__file__).resolve().parents[1]


def classify(root=ROOT):
    scans = {}
    for name in NAMES:
        path = root / ".github" / "workflows" / name
        try:
            text = path.read_text(encoding="utf-8")
            # YAML job cannot execute if IF false at job level. Keep
            # permissions minimal, no main push trigger and no actions.
            valid = all([
                "ARCHIVED - NO HARDWARE EXECUTION" in text,
                "  push:" not in text,
                "    if: false" in text,
                "runs-on: ubuntu-24.04" in text,
                "contents: read" in text,
                "self-hosted" not in text,
                "python " not in text and "systemctl" not in text,
                "/home/arduino/MyAI" not in text,
                "actions/checkout" not in text,
                not re.search(r"(?m)^\s*-\s*run:\s*.*(?:pip|curl|wget|pytest|git|qnn|arecord|aplay)", text),
            ])
        except (OSError, UnicodeError):
            valid = False
        scans[name] = bool(valid)
    passed = all(scans.values())
    return {
        "status": ("four-main-workflows-quarantined" if passed
                   else "blocked-unsafe-main-workflow"),
        "quarantined_workflows": sum(scans.values()),
        "expected_workflows": len(NAMES),
        "quarantine_verified": passed,
        "live_production_workflow_run_attempted": False,
        "main_modified": False,
        "hardware_execution_authorized": False,
    }


if __name__ == "__main__":
    import json
    report = classify()
    print("MYAI_MAIN_WORKFLOW_QUARANTINE_JSON=" + json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report["quarantine_verified"] else 2)
