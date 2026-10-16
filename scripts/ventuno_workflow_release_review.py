"""Conservative source-only GitHub Actions inventory for the current audit branch.

This is a text heuristic, not a full YAML/expression evaluator. Inventory
success is NOT release approval. Only Git-tracked workflow files are counted,
symlinks and missing files fail closed; no workflow is executed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
CURRENT_BRANCH = "dev/ventuno-workflow-review-closure-20261016"
SENSITIVE = re.compile(
    r"\b(?:arecord|aplay|qnn-net-run|qnn_net_run|geniex|whispermodel)\b|"
    r"(?:tiny_qnn_htp_once|usb_dialogue_hardware|microphone_smoke|"
    r"usb_speaker_smoke|live_qairt_synthetic_once)|"
    r"systemctl\s+(?:stop|restart|enable|disable)|"
    r"\b(?:consent_to_record|consent_to_play)\s*=\s*True",
    re.IGNORECASE,
)
COMMENT_LINES = re.compile(r"(?m)^\s*#.*$")
TOP_PUSH = re.compile(r"(?m)^  push\s*:")
TOP_MANUAL = re.compile(r"(?m)^  workflow_dispatch\s*:")
TOP_SCHEDULE = re.compile(r"(?m)^  schedule\s*:")
BRANCH_INLINE = re.compile(r"(?m)^    branches:\s*\[([^\]\n]+)\]\s*$")
BRANCH_MULTILINE = re.compile(r"(?m)^    branches:\s*\n((?: {6}- [^\n]+\n?)+)")


def _tracked_workflows(root):
    names = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", ".github/workflows"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20,
    ).stdout.split(b"\0")
    return sorted(name.decode("utf-8", "surrogateescape") for name in names
                  if name and name.endswith((b".yml", b".yaml")))


def _restricted_away_from_branch(text, branch):
    """Only one exact, unambiguous literal branch list can exclude our branch."""
    if re.search(r"(?m)^    branches-ignore\s*:", text):
        return False
    single = BRANCH_INLINE.findall(text)
    multi = BRANCH_MULTILINE.findall(text)
    if len(single) + len(multi) != 1:
        return False
    if single:
        names = [name.strip().strip("\"'") for name in single[0].split(",")]
    else:
        names = [line.strip()[1:].strip().strip("\"'") for line in multi[0].splitlines()]
    return bool(names) and all(
        name and name != branch and "*" not in name and "?" not in name
        and not name.startswith("!")
        for name in names
    )


def _workflow_events(text):
    """Extract literal event names and their event-specific filter blocks.

    This is a conservative subset of YAML, not an expressions evaluator.
    Unknown, malformed and aliased trigger shapes must not clear CI.
    """
    headers = list(re.finditer(r"(?m)^on:\s*([^\n]*)$", text))
    if len(headers) != 1:
        return None
    raw = headers[0].group(1).strip()
    if raw:
        if re.fullmatch(r"[a-z][a-z0-9_-]*", raw):
            return {raw: ""}
        if raw.startswith("[") and raw.endswith("]"):
            names = [x.strip().strip("'\"") for x in raw[1:-1].split(",")]
            if names and all(re.fullmatch(r"[a-z][a-z0-9_-]*", x) for x in names):
                return {x: "" for x in names}
        return None
    events = {}
    current = None
    for line in text[headers[0].end():].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            break
        entry = re.fullmatch(r"  ([a-z][a-z0-9_-]*):\s*(?:#.*)?", line)
        if entry:
            current = entry.group(1)
            events[current] = ""
            continue
        if current is None or not line.startswith("    "):
            return None
        events[current] += line + "\n"
    return events or None


def _event_automatic_possible(events, branch):
    if not isinstance(events, dict) or not events:
        return True
    # workflow_call is reachable from another automation. Treat every
    # non-manual event as automatically reachable unless an exact push
    # restriction excludes this specific branch.
    for name, nested in events.items():
        if name == "workflow_dispatch":
            continue
        if name == "push" and _restricted_away_from_branch(nested, branch):
            continue
        return True
    return False


def inventory(root=ROOT, *, branch=CURRENT_BRANCH):
    counts = dict(total_workflows=0, sensitive_candidates=0,
                  manual_sensitive_candidates=0,
                  automatic_sensitive_candidates=0,
                  unreviewed_manual_candidates=0)
    risky = []
    try:
        files = _tracked_workflows(root)
        if not files:
            raise ValueError("no-tracked-workflows")
        for name in files:
            file = root / name
            if file.is_symlink() or not file.is_file():
                raise ValueError("unreadable-workflow")
            source = file.read_text(encoding="utf-8")
            source = COMMENT_LINES.sub("", source)
            counts["total_workflows"] += 1
            if not SENSITIVE.search(source):
                continue
            counts["sensitive_candidates"] += 1
            events = _workflow_events(source)
            manual = isinstance(events, dict) and "workflow_dispatch" in events
            automatic = _event_automatic_possible(events, branch)
            counts["manual_sensitive_candidates"] += int(manual)
            counts["automatic_sensitive_candidates"] += int(automatic)
            counts["unreviewed_manual_candidates"] += int(manual)
            risky.append(dict(filename=Path(name).name,
                              manual_dispatch=manual,
                              candidate_automatic_possible=automatic,
                              parsed_event_names=(sorted(events) if events is not None else []),
                              event_source_clear=events is not None))
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
        return dict(status="incomplete-no-go", counts=counts,
                    candidate_automatic_clear=False,
                    release_ready=False, physical_tests_authorized=False,
                    approval_proven=False, risks=[])
    return dict(
        status=("possible-automatic-effectful-workflow-no-go"
                if counts["automatic_sensitive_candidates"] else
                "inventory-complete-not-release-authorized"),
        counts=counts, risks=risky,
        candidate_automatic_clear=counts["automatic_sensitive_candidates"] == 0,
        approval_proven=False,
        physical_tests_authorized=False,
        release_ready=False,
        human_review_of_manual_dispatch_required=bool(
            counts["unreviewed_manual_candidates"]
        ),
        dynamic_yaml_actions_expressions_verified=False,
    )


def exit_code(result, *, release=False):
    if not isinstance(result, dict) or result.get("status") == "incomplete-no-go":
        return 2
    if result.get("candidate_automatic_clear") is not True:
        return 2
    # An inventory can be safe to run while a release is still forbidden.
    if release:
        return 2
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-gate", action="store_true",
                        help="Always deny until separately reviewed and attested")
    parser.add_argument("--branch", default=None,
                        help="Exact branch/ref to evaluate for automatic triggers")
    args = parser.parse_args(argv)
    # CI checks out a detached SHA, so do not assume this source file's
    # original authoring branch is the current workflow's candidate ref.
    current = args.branch or os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME") or CURRENT_BRANCH
    result = inventory(branch=current)
    print("MYAI_WORKFLOW_REVIEW_JSON=" + json.dumps(result, sort_keys=True))
    return exit_code(result, release=args.release_gate)


if __name__ == "__main__":
    raise SystemExit(main())
