"""Source-only guards: three historical manual audits must not run on production VENTUNO.

All assertions inspect committed YAML text. Never dispatch workflows or open hardware.
"""
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    ("ventuno-exception-privacy-manual-audit.yml", "MYAI_MANUAL_AUDIT_SCRATCH",
     "myai-privacy-audit-venv"),
    ("ventuno-external-actions-pin-audit.yml", "MYAI_ACTION_PIN_SCRATCH",
     "myai-actions-audit-venv"),
    ("ventuno-manual-audit-dependency-and-consent.yml", "MYAI_MANUAL_AUDIT_SCRATCH",
     "myai-dependency-consent-venv"),
)


@pytest.mark.parametrize("filename,scratch,venv", WORKFLOWS)
def test_static_review_uses_only_disposable_github_hosted_arm64(filename, scratch, venv):
    workflow = (ROOT / ".github/workflows" / filename).read_text(encoding="utf-8")
    assert "runs-on: ubuntu-24.04-arm" in workflow
    assert "runs-on: [self-hosted" not in workflow
    assert "RUNNER_ENVIRONMENT: ${{ runner.environment }}" in workflow
    assert 'test "$RUNNER_ENVIRONMENT" = "github-hosted"' in workflow
    assert 'test "$(uname -m)" = aarch64' in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "  push:" in workflow
    assert "branches: [dev/" in workflow
    assert '"$GITHUB_SHA"' in workflow
    assert "rev-parse HEAD" in workflow


@pytest.mark.parametrize("filename,scratch,venv", WORKFLOWS)
def test_no_ventuno_installed_venv_or_production_service_access(filename, scratch, venv):
    workflow = (ROOT / ".github/workflows" / filename).read_text(encoding="utf-8")
    assert "/home/arduino/" not in workflow
    assert "systemctl" not in workflow
    assert "sudo " not in workflow
    assert 'test "$(id -un)" = arduino' not in workflow
    assert "RUNNER_TEMP" in workflow
    assert "Create isolated hosted ARM64 audit Python environment" in workflow
    assert "python3 -m venv" in workflow
    assert '--only-binary=:all:' in workflow
    assert '-r "$' + scratch + '/requirements.txt"' in workflow
    assert 'echo "MYAI_AUDIT_PY=$RUNNER_TEMP/' + venv + '/bin/python"' in workflow
    assert 'rm -rf -- "$RUNNER_TEMP/' + venv + '"' in workflow
    assert workflow.count('"$MYAI_AUDIT_PY" -B -m') >= 2


@pytest.mark.parametrize("filename,scratch,venv", WORKFLOWS)
def test_checkout_and_python_gate_precede_untrusted_execution(filename, scratch, venv):
    workflow = (ROOT / ".github/workflows" / filename).read_text(encoding="utf-8")
    hosted_guard = workflow.index('test "$RUNNER_ENVIRONMENT" = "github-hosted"')
    checkout = workflow.index("git init")
    exact_sha = workflow.index("rev-parse HEAD")
    install = workflow.index("python3 -m venv")
    audit_run = workflow.index('"$MYAI_AUDIT_PY" -B -m')
    assert hosted_guard < checkout < exact_sha < install < audit_run
    assert "GH_TOKEN: ${{ github.token }}" in workflow
    # Credentials should be stripped from the configured Git remote
    # before source scripts / pytest are executed.
    assert "remote set-url origin" in workflow


def test_old_source_identity_manifest_is_not_rewritten_to_hide_workflow_changes():
    manifest = json.loads(
        (ROOT / "config/ventuno_manual_workflow_git_oids_20261016.json")
        .read_text(encoding="utf-8")
    )
    assert manifest["source_review_complete"] is False
    assert manifest["production_release_authorized"] is False
    assert len(manifest["manual_workflow_git_blob_oids"]) == 103
    assert all(
        filename not in manifest["manual_workflow_git_blob_oids"]
        for filename, _, _ in WORKFLOWS
    )
