"""Conservative READ-ONLY source inventory of GitHub Actions runner exposure.

NOT a YAML parser or proof of actual GitHub admin/runner group configuration.
No network, subprocess, file write, runner dispatch or production action.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re

AUTO = frozenset({"push", "pull_request", "pull_request_target",
                  "workflow_run", "schedule", "repository_dispatch",
                  "issue_comment", "issues", "check_run", "release",
                  "create", "delete", "merge_group"})
MANUAL = frozenset({"workflow_dispatch", "workflow_call"})
EVENT = re.compile(r"^([ \t]*)['\"]?([a-z][a-z_]+)['\"]?\s*:")
ON = re.compile(r"^['\"]?on['\"]?\s*:\s*(?:#.*)?$")
RUNNER = re.compile(r"^[ \t]*runs-on\s*:\s*(.+)$")
WRITE = re.compile(r"^[ \t]*[a-z_-]+\s*:\s*write\s*(?:#.*)?$")


def summarize_source(path, source):
    """Flags are review leads, NEVER security authorization."""
    lines = source.splitlines()
    events, runners = set(), []
    on_indent = None
    writing = False
    for line in lines:
        if line.lstrip().startswith("#"):
            continue
        clean = line.rstrip()
        if ON.match(clean):
            on_indent = len(clean) - len(clean.lstrip())
            continue
        if on_indent is not None and clean.strip():
            spaces = len(clean) - len(clean.lstrip())
            if spaces <= on_indent:
                on_indent = None
            else:
                m = EVENT.match(clean)
                if m and len(m.group(1)) > on_indent:
                    if m.group(2) in AUTO | MANUAL:
                        events.add(m.group(2))
        if re.match(r"^['\"]?on['\"]?\s*:\s*\[", clean):
            events.update(event for event in AUTO | MANUAL
                          if re.search(r"\b" + re.escape(event) + r"\b", clean))
        m = RUNNER.match(clean)
        if m:
            runners.append(m.group(1).split("#", 1)[0].strip())
        writing = writing or bool(WRITE.match(clean))
    joined = " ".join(runners).lower()
    uses_self_hosted = "self-hosted" in joined or "ventuno-q" in joined
    dynamic = (chr(36)+"{{" in joined or "fromjson(" in joined or not runners)
    auto = bool(events & AUTO)
    risk = ("REVIEW_AUTO_SELF_HOSTED" if auto and uses_self_hosted
            else "REVIEW_DYNAMIC_RUNNER" if auto and dynamic
            else "REVIEW_MANUAL_SELF_HOSTED" if uses_self_hosted
            else "NO_STATIC_SELF_HOSTED_RUNNER_INDICATION")
    return {"path": str(path), "risk": risk,
            "auto_triggers": sorted(events & AUTO),
            "manual_triggers": sorted(events & MANUAL),
            "runner_expressions": runners,
            "self_hosted_runner_reference": uses_self_hosted,
            "dynamic_or_unknown_runner": dynamic,
            "write_permissions_declared": writing}


def inventory(directory):
    root = Path(directory)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Expected real non-symlink workflow directory")
    names = sorted([*root.glob("*.yml"), *root.glob("*.yaml")])
    if not names:
        raise ValueError("Missing workflows")
    findings = []
    for path in names:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 256_000:
            raise ValueError("Unsafe workflow source path/size")
        findings.append(summarize_source(
            path.name, path.read_text(encoding="utf-8")
        ))
    risk = [x for x in findings
            if x["risk"] != "NO_STATIC_SELF_HOSTED_RUNNER_INDICATION"]
    return {
        "status": "SOURCE_ONLY_INVENTORY_NOT_ADMIN_SECURITY_ASSERTION",
        "total_workflows": len(findings),
        "auto_self_hosted_leads": sum(
            x["risk"] == "REVIEW_AUTO_SELF_HOSTED" for x in findings),
        "auto_dynamic_runner_leads": sum(
            x["risk"] == "REVIEW_DYNAMIC_RUNNER" for x in findings),
        "manual_self_hosted_leads": sum(
            x["risk"] == "REVIEW_MANUAL_SELF_HOSTED" for x in findings),
        "write_permissions_declarations": sum(
            x["write_permissions_declared"] for x in findings),
        "source_findings": risk,
        "historical_branches_checked": False,
        "runner_group_admin_settings_verified": False,
        "physical_ventuno_touched": False,
        "production_deployment_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflows-dir", default=".github/workflows")
    args = parser.parse_args()
    print(json.dumps(inventory(args.workflows_dir), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
