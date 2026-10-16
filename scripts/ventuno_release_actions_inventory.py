"""Conservative, non-executing inventory of all Actions hardware entrypoints.

This is a source-level release screen, not a YAML parser or authorization.
A triggered hardware workflow still requires fresh human approval.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DANGER = re.compile(
    r"\b(?:arecord|aplay|qnn-net-run|genie-t2t-run|geniex\s+serve|"
    r"systemctl\s+(?:stop|restart|start)|"
    r"tiny_qnn_htp_once|"
    r"--synthesize-synthetic-phrase|"
    r"--record-audio|--play-audio)\b",
    re.I,
)
MAIN_PUSH = re.compile(
    r"(?ms)^  push:\s*\n(?:(?!^  [a-zA-Z_][\w-]*:).)*?"
    r"^    branches:\s*\[[^\n]*\bmain\b[^\n]*\]",
)
MAIN_BRANCH = re.compile(r"(?m)^\s*branches:\s*\[\s*main\s*\]")


def classify_workflow(source: str):
    # Strip whole-line comments; preserve only technical source statements.
    rows = [line for line in source.splitlines()
            if not line.lstrip().startswith("#")]
    clean = "\n".join(rows)
    self_hosted = "self-hosted" in clean
    physical = bool(DANGER.search(clean))
    dispatch = bool(re.search(r"(?m)^  workflow_dispatch\s*:", clean))
    push_main = bool(MAIN_PUSH.search(clean))
    if "if: false" in clean and "runs-on: ubuntu-24.04" in clean:
        self_hosted = False
    return {
        "self_hosted": self_hosted,
        "physical_command_candidate": physical,
        "has_manual_dispatch": dispatch,
        "has_main_push": push_main,
        "unreviewed_main_push_physical": self_hosted and physical and push_main,
        "requires_fresh_operator_gate_if_dispatched": (
            self_hosted and physical and dispatch
        ),
    }


def inspect(root=ROOT):
    folder = Path(root) / ".github/workflows"
    result = {
        "status": "blocked-workflow-inventory-missing",
        "files_scanned": 0,
        "self_hosted_workflows": 0,
        "physical_command_candidates": 0,
        "main_push_physical_risk": 0,
        "manual_dispatch_physical_candidates": 0,
        "candidate_filenames_for_operator_review": [],
        "main_automatic_hardware_safe_by_static_rules": False,
        "manual_workflow_review_complete": False,
        "release_deployed": False,
        "physical_test_authorized": False,
    }
    try:
        files = sorted(x for x in folder.iterdir()
                       if x.suffix in {".yml", ".yaml"})
        if not 100 <= len(files) <= 300:
            return result
        names = []
        for path in files:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 100000:
                return result
            meta = classify_workflow(path.read_text(encoding="utf-8"))
            result["files_scanned"] += 1
            result["self_hosted_workflows"] += meta["self_hosted"]
            result["physical_command_candidates"] += meta["physical_command_candidate"]
            result["main_push_physical_risk"] += meta["unreviewed_main_push_physical"]
            result["manual_dispatch_physical_candidates"] += meta["requires_fresh_operator_gate_if_dispatched"]
            if (meta["unreviewed_main_push_physical"]
                    or meta["requires_fresh_operator_gate_if_dispatched"]):
                names.append(path.name)
        result["candidate_filenames_for_operator_review"] = names[:60]
        result["main_automatic_hardware_safe_by_static_rules"] = (
            result["main_push_physical_risk"] == 0
        )
        result["status"] = (
            "blocked-main-hardware-workflow"
            if result["main_push_physical_risk"]
            else "workflow-inventory-completed-manual-gates-remain"
        )
    except (OSError, UnicodeError, ValueError):
        pass
    return result


if __name__ == "__main__":
    print("MYAI_RELEASE_ACTIONS_INVENTORY_JSON=" + json.dumps(inspect(), sort_keys=True))
