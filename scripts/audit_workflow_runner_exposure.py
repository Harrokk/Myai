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


def _push_branch_scope(lines):
    """Conservative recognition of common branch lists under on.push.

    Unknown YAML syntax stays UNKNOWN, never interpreted as safe.
    """
    on_indent = None
    push_indent = None
    branch_indent = None
    found_push = False
    names = []
    for raw in lines:
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if ON.match(line):
            on_indent, push_indent, branch_indent = indent, None, None
            continue
        if on_indent is None:
            continue
        if indent <= on_indent:
            on_indent, push_indent, branch_indent = None, None, None
            continue
        if re.match(r"^push\s*:\s*(?:#.*)?$", stripped) and push_indent is None:
            found_push, push_indent = True, indent
            continue
        if push_indent is None:
            continue
        if indent <= push_indent:
            push_indent, branch_indent = None, None
            continue
        if re.match(r"^branches\s*:", stripped) and branch_indent is None:
            branch_indent = indent
            rest = stripped.split(":", 1)[1].split("#", 1)[0].strip()
            if rest.startswith("[") and rest.endswith("]"):
                names.extend(
                    value.strip().strip("'\"") for value in
                    rest[1:-1].split(",") if value.strip()
                )
            elif rest:
                return "UNKNOWN", ()
            continue
        if branch_indent is not None and indent > branch_indent:
            if stripped.startswith("- "):
                names.append(stripped[2:].split("#", 1)[0].strip().strip("'\""))
        elif branch_indent is not None and indent <= branch_indent:
            branch_indent = None
    if not found_push:
        return "NO_PUSH_OR_INLINE_TRIGGER", ()
    if not names:
        return "UNSCOPED_OR_UNRECOGNIZED", ()
    if any("*" in name or "?" in name or name.startswith("!") for name in names):
        return "PATTERN_BRANCHES", tuple(names)
    return "EXPLICIT_BRANCHES", tuple(names)


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
    push_scope, push_branches = _push_branch_scope(lines)
    joined = " ".join(runners).lower()
    uses_self_hosted = "self-hosted" in joined or "ventuno-q" in joined
    dynamic = (chr(36)+"{{" in joined or "fromjson(" in joined or not runners)
    auto = bool(events & AUTO)
    risk = ("REVIEW_AUTO_SELF_HOSTED" if auto and uses_self_hosted
            else "REVIEW_DYNAMIC_RUNNER" if auto and dynamic
            else "REVIEW_MANUAL_SELF_HOSTED" if uses_self_hosted
            else "NO_STATIC_SELF_HOSTED_RUNNER_INDICATION")
    return {"path": str(path), "risk": risk,
            "push_scope": push_scope,
            "push_branches": list(push_branches),
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
        "auto_self_hosted_exact_push_branch_leads": sum(
            x["risk"] == "REVIEW_AUTO_SELF_HOSTED"
            and x["push_scope"] == "EXPLICIT_BRANCHES" for x in findings),
        "auto_self_hosted_unscoped_or_pattern_push_leads": sum(
            x["risk"] == "REVIEW_AUTO_SELF_HOSTED"
            and x["push_scope"] in ("UNSCOPED_OR_UNRECOGNIZED", "PATTERN_BRANCHES")
            for x in findings),
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
