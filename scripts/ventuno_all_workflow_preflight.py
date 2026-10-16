"""Review all tracked GitHub Actions for accidental board/hardware triggers.

Source-only: NEVER invokes Actions jobs or reads installed runner config.
Classifies potential risk conservatively; an allowlist is not a permission
to run a microphone, STT model or NPU. Useful for release/manual review.
"""
from __future__ import annotations

from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
CURRENT_BRANCH = "dev/ventuno-remote-preflight-completion-20261016"
SENSITIVE = re.compile(
    r"(arecord|aplay|qnn[-_]net[-_]run|tiny_qnn_htp_once|"
    r"systemctl[ ]+(stop|restart|enable|disable)|"
    r"scripts[./]ventuno_usb_dialogue_once|"
    r"scripts[./]ventuno_usb_dialogue_hardware|"
    r"scripts[./]ventuno_tiny_qnn|"
    r"geniex[ ]+serve)", re.I,
)
ONLY_COMMENTS = re.compile(r"(?m)^\s*#.*$")
SELF_HOSTED = re.compile(r"(?m)^\s*runs-on\s*:\s*.*self-hosted", re.I)
TOP_PUSH = re.compile(r"(?m)^  push\s*:")
TOP_DISPATCH = re.compile(r"(?m)^  workflow_dispatch\s*:")
BRANCHES = re.compile(r"(?m)^    branches:\s*\[([^\]]+)\]")


def inventory(root=ROOT):
    folder = root / ".github/workflows"
    names = sorted(folder.glob("*.yml")) + sorted(folder.glob("*.yaml"))
    counts = {"total_workflows": len(names), "hardware_candidates": 0,
              "manual_hardware_candidates": 0,
              "current_branch_automatic_risks": 0,
              "main_only_quarantined": 0}
    risk = []
    for path in names:
        if path.is_symlink() or not path.is_file():
            return {"status": "blocked-unreadable-actions-source", "counts": counts,
                    "risk": [], "hardware_authorized": False}
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return {"status": "blocked-unreadable-actions-source", "counts": counts,
                    "risk": [], "hardware_authorized": False}
        # Ignore comment-only markers; still a source-text heuristic not
        # a YAML parser or proof of no executable dynamic action.
        no_comments = ONLY_COMMENTS.sub("", content)
        hardware = bool(SENSITIVE.search(no_comments))
        if not hardware:
            continue
        counts["hardware_candidates"] += 1
        manually_runnable = bool(TOP_DISPATCH.search(no_comments))
        if manually_runnable:
            counts["manual_hardware_candidates"] += 1
        push = bool(TOP_PUSH.search(no_comments))
        patterns = BRANCHES.findall(no_comments)
        # If push has no supported branch restriction, conservatively block.
        branch_scoped = (len(patterns) == 1
                         and CURRENT_BRANCH not in patterns[0]
                         and "'**'" not in patterns[0]
                         and "'*'" not in patterns[0]
                         and "**" not in patterns[0])
        automatic = push and not branch_scoped
        if automatic:
            counts["current_branch_automatic_risks"] += 1
        risk.append({
            "filename": path.name,
            "manual": manually_runnable,
            "automatic_on_candidate_branch_possible": automatic,
        })
    # No old manual workflows can be presumed consented automatically.
    return {
        "status": ("no-automatic-hardware-triggers-on-candidate"
                   if counts["current_branch_automatic_risks"] == 0
                   else "blocked-possible-automatic-hardware-triggers"),
        "counts": counts,
        "risk": risk,
        "manual_workflows_are_not_approved_by_this_audit": True,
        "dynamic_workflow_expressions_certified_safe": False,
        "hardware_authorized": False,
    }


def main():
    result = inventory()
    print("MYAI_ALL_WORKFLOWS_REVIEW_JSON=" + json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "no-automatic-hardware-triggers-on-candidate" else 2


if __name__ == "__main__":
    raise SystemExit(main())
