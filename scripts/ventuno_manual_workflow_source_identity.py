"""Exact-source identity check for manually startable GitHub Actions.

Checks git-blob object identity of each of 103 previously inventoried source
files, not the safety of executing them. No network, subprocess, service,
audio, model or hardware action. A changed file requires fresh human review.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import ventuno_all_manual_actions_drift_gate as manual

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = "config/ventuno_manual_workflow_git_oids_20261016.json"


def _blob_oid(data: bytes) -> str:
    # Git's normal SHA-1 object identity for this repository, not a digital
    # signature. The stored OID is a *drift detector*, not supply-chain trust.
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def check(root=ROOT, *, manifest_path=None):
    root = Path(root)
    path = Path(manifest_path) if manifest_path is not None else root / MANIFEST
    try:
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 32768:
            raise ValueError("missing-manifest")
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        manifest = None
    safe_shape = isinstance(manifest, dict) and (
        type(manifest.get("schema")) is int and manifest["schema"] == 1
        and manifest.get("source_review_complete") is False
        and manifest.get("physical_test_authorized") is False
        and manifest.get("production_release_authorized") is False
    )
    expected = manifest.get("manual_workflow_git_blob_oids") if safe_shape else None
    current_manifest = manual._read(root / manual.MANIFEST)
    actual_names = current_manifest.get("all_manual_workflow_filenames") if isinstance(current_manifest, dict) else None
    if not (
        isinstance(expected, dict) and len(expected) == 103
        and isinstance(actual_names, list) and len(actual_names) == 103
        and set(expected) == set(actual_names)
        and all(type(name) is str and "/" not in name
                and name.endswith((".yml", ".yaml"))
                and type(oid) is str and len(oid) == 40
                and all(c in "0123456789abcdef" for c in oid)
                for name, oid in expected.items())
    ):
        expected = {}
    changed = []
    matched = 0
    for filename, oid in sorted(expected.items()):
        file = root / ".github" / "workflows" / filename
        try:
            if file.is_symlink() or not file.is_file() or file.stat().st_size > 262144:
                raise ValueError("missing-or-unbounded")
            data = file.read_bytes()
            good = _blob_oid(data) == oid
        except (OSError, ValueError):
            good = False
        if good:
            matched += 1
        else:
            changed.append(filename)
    ok = len(expected) == 103 and matched == 103
    return {
        "status": "all-103-source-blobs-unchanged-not-authorized" if ok
                  else "blocked-manual-workflow-source-changed",
        "baseline": 103,
        "matched": matched,
        "unverified_count": 103 - matched,
        "unverified_filenames": changed[:10],
        "manifest_valid": len(expected) == 103,
        "git_sha1_identity_not_signed_attestation": True,
        "real_workflow_execution_performed": False,
        "third_party_actions_verified": False,
        "physical_test_authorized": False,
        "production_release_authorized": False,
    }


def main():
    result = check()
    print("MYAI_MANUAL_WORKFLOW_SOURCE_IDENTITY_JSON=" + json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "all-103-source-blobs-unchanged-not-authorized" else 2


if __name__ == "__main__":
    raise SystemExit(main())
