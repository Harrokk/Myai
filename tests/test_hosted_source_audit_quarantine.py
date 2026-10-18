"""Enforce safe hosted boundaries for legacy unattended source-audit jobs."""

from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[1]
_AUDITS = (
    "ventuno-full-project-two-pass-audit.yml",
    "ventuno-static-repository-audit.yml",
)


@pytest.mark.parametrize("workflow_name", _AUDITS)
def test_legacy_source_audits_only_run_on_disposable_hosted_arm64(workflow_name):
    workflow = (_ROOT / ".github" / "workflows" / workflow_name).read_text(
        encoding="utf-8"
    )

    assert "runs-on: ubuntu-24.04-arm" in workflow
    assert "runs-on: [self-hosted" not in workflow
    assert "runner.environment" in workflow
    assert 'test "$RUNNER_ENVIRONMENT" = "github-hosted"' in workflow
    assert "test \"$(uname -m)\" = \"aarch64\"" in workflow


@pytest.mark.parametrize("workflow_name", _AUDITS)
def test_source_audit_jobs_never_consult_installed_ventuno_services(workflow_name):
    workflow = (_ROOT / ".github" / "workflows" / workflow_name).read_text(
        encoding="utf-8"
    )

    assert "/home/arduino/MyAI/" not in workflow
    assert "systemctl" not in workflow
    assert "sudo " not in workflow
    assert "actions/checkout@" not in workflow


@pytest.mark.parametrize("workflow_name", _AUDITS)
def test_source_audit_fetches_exact_sha_and_retains_readonly_permissions(
    workflow_name,
):
    workflow = (_ROOT / ".github" / "workflows" / workflow_name).read_text(
        encoding="utf-8"
    )

    assert "contents: read" in workflow
    assert ' "$GITHUB_SHA"' in workflow
    assert "rev-parse HEAD" in workflow
    assert "workflow_dispatch:" in workflow
