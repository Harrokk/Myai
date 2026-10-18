"""Read-only policy gate for a proposed isolated *source-only* CI runner.

Never calls systemctl, creates OS users, starts jobs, reads credentials, or
grants production authorization. This verifies just a non-installable .example
unit and inventories the tracked source workflow files. It is NOT a live
permission check or a complete YAML/GitHub runner policy interpreter.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
CANDIDATE = "deploy/systemd/myai-ci-runner-isolated.service.example"
MAX_UNIT_BYTES = 16_384
MAX_WORKFLOW_BYTES = 262_144
MAX_WORKFLOWS = 400
UNIT_FIELDS = {
    "Description": "MyAI isolated GitHub source-only CI runner - REVIEW ONLY",
    "After": "network-online.target",
    "Wants": "network-online.target",
}
SERVICE_FIELDS = {
    "Type": "simple",
    "User": "myai-ci",
    "Group": "myai-ci",
    "WorkingDirectory": "/var/lib/myai-ci-runner",
    "ExecStart": "/var/lib/myai-ci-runner/runsvc.sh",
    "StateDirectory": "myai-ci-runner",
    "UMask": "0077",
    "NoNewPrivileges": "yes",
    "PrivateTmp": "yes",
    "PrivateDevices": "yes",
    "ProtectHome": "yes",
    "ProtectSystem": "strict",
    "ProtectKernelTunables": "yes",
    "ProtectKernelModules": "yes",
    "ProtectControlGroups": "yes",
    "RestrictSUIDSGID": "yes",
    "CapabilityBoundingSet": "",
    "AmbientCapabilities": "",
    "TasksMax": "64",
    "Restart": "no",
}
DIRECT_SELF_HOSTED = re.compile(
    r"(?m)^\s*runs-on:\s*(?:\[[^\n\]]*\bself-hosted\b[^\n\]]*\]|self-hosted\b)"
)


def validate_candidate_text(source):
    """Require exactly one safe spelling of each template directive.

    Reject duplicates, line continuations, alternative execs and Install
    sections, so a passing template cannot hide a second unsafe assignment.
    """
    if not isinstance(source, str) or not 1 <= len(source.encode("utf-8")) <= MAX_UNIT_BYTES:
        return False
    found = {}
    section = None
    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if raw != line:
            return False
        if line.startswith("[") and line.endswith("]"):
            if line not in ("[Unit]", "[Service]") or line in found:
                return False
            section = line
            found[section] = {}
            continue
        if section is None or "\\" in line or "=" not in line:
            return False
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", key):
            return False
        if key in found[section]:
            return False
        found[section][key] = value
    return found == {"[Unit]": UNIT_FIELDS, "[Service]": SERVICE_FIELDS}


def inspect(root=ROOT):
    """Inspect source only; never infer live owner/mode safety from a template."""
    root = Path(root)
    valid = False
    reasons = []
    files_checked = 0
    direct_self_hosted = []
    possible_self_hosted = []
    try:
        template = root / CANDIDATE
        if template.is_symlink() or not template.is_file():
            raise ValueError("candidate-not-regular")
        if not 0 < template.stat().st_size <= MAX_UNIT_BYTES:
            raise ValueError("candidate-unbounded")
        valid = validate_candidate_text(template.read_text(encoding="utf-8"))
        if not valid:
            reasons.append("candidate-policy-invalid")
        directory = root / ".github" / "workflows"
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("workflow-dir-invalid")
        paths = sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml"))
        if not 1 <= len(paths) <= MAX_WORKFLOWS:
            raise ValueError("workflow-count-unbounded")
        for path in paths:
            if (path.is_symlink() or not path.is_file()
                    or not 0 < path.stat().st_size <= MAX_WORKFLOW_BYTES):
                raise ValueError("workflow-file-invalid")
            content = path.read_text(encoding="utf-8")
            files_checked += 1
            if DIRECT_SELF_HOSTED.search(content):
                direct_self_hosted.append(path.name)
            if "self-hosted" in content or "ventuno-q" in content:
                possible_self_hosted.append(path.name)
    except (OSError, UnicodeError, ValueError):
        valid = False
        reasons.append("source-inventory-incomplete")
    return {
        "status": ("isolated-runner-template-reviewed-production-no-go"
                   if valid and not reasons else "blocked-runner-boundary-source-review"),
        "candidate_unit_policy_valid": valid and not reasons,
        "workflow_files_scanned": files_checked,
        "direct_self_hosted_runner_workflows": len(direct_self_hosted),
        "other_possible_runner_references": len(set(possible_self_hosted) - set(direct_self_hosted)),
        "direct_self_hosted_workflow_examples": sorted(direct_self_hosted)[:12],
        "source_findings": reasons,
        "source_scan_is_not_full_yaml_or_expression_parsing": True,
        "candidate_unit_is_inert_example_only": True,
        "live_runner_uid_and_groups_verified": False,
        "live_source_and_secret_acl_verified": False,
        "old_trigger_branches_and_runner_group_policy_verified": False,
        "production_runner_service_reconfigured": False,
        "actual_privilege_separation_proven": False,
        "hardware_access_authorized": False,
        "main_merge_authorized": False,
        "production_deployment_authorized": False,
    }


def main():
    result = inspect()
    print("MYAI_RUNNER_UID_BOUNDARY_SOURCE_JSON=" + json.dumps(result, sort_keys=True))
    return 0 if result["candidate_unit_policy_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
