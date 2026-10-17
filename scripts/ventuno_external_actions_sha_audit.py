"""Audit GitHub Actions external 'uses:' references without executing workflows.

A pinned reference is *immutable source selection*, not a trustworthy or
vulnerability-free action. YAML semantics, called actions, composite scripts
and transitive dependencies require independent review before release.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
USE = re.compile(r"(?m)^\s*(?:-\s*)?uses:[ \t]*(\S[^\n]*)$")
SHA_REF = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_./-]+)?@[a-f0-9]{40}$")
DIGEST_REF = re.compile(r"^docker://[^\s@]+@sha256:[a-f0-9]{64}$")


def inspect(root=ROOT):
    root = Path(root)
    base = root / ".github" / "workflows"
    findings = []
    external = []
    local_count = 0
    total = 0
    valid = base.is_dir() and not base.is_symlink()
    try:
        files = sorted(
            f for f in base.iterdir()
            if f.name.endswith((".yml", ".yaml"))
        ) if valid else []
        if not files:
            valid = False
        for path in files:
            total += 1
            if path.is_symlink() or not path.is_file():
                findings.append({"file": path.name, "reason": "untrusted-workflow-file"})
                continue
            data = path.read_text(encoding="utf-8")
            for match in USE.finditer(data):
                target = match.group(1).strip()
                if " #" in target:
                    target = target.split(" #", 1)[0].strip()
                target = target.strip("'\"")
                if target.startswith("./"):
                    parts = Path(target).parts
                    if (".." in parts or not target.startswith("./")
                            or any(part in ("", ".git") for part in parts)):
                        findings.append({"file": path.name, "reason": "unsafe-local-action-path"})
                    else:
                        local_count += 1
                elif SHA_REF.fullmatch(target) or DIGEST_REF.fullmatch(target):
                    external.append({"file": path.name, "reference": target})
                else:
                    findings.append({"file": path.name, "reason": "floating-or-dynamic-action-reference"})
    except (OSError, UnicodeError, ValueError):
        valid = False
    clear = valid and not findings
    return {
        "status": ("external-action-refs-sha-pinned-not-release-ready" if clear
                   else "blocked-unpinned-or-unreadable-action"),
        "workflow_files_inspected": total,
        "external_immutable_refs": len(external),
        "external_references": external,
        "repo_local_refs": local_count,
        "unreviewed_references": findings,
        "external_refs_pinned": clear,
        "yaml_and_nested_actions_semantics_attested": False,
        "third_party_action_security_attested": False,
        "dependencies_and_licenses_audited": False,
        "production_release_authorized": False,
        "physical_hardware_action_authorized": False,
    }


def main():
    result = inspect()
    print("MYAI_EXTERNAL_ACTION_PIN_REVIEW_JSON=" + json.dumps(result, sort_keys=True))
    return 0 if result["external_refs_pinned"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
