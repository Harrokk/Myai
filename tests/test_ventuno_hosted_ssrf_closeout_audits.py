"""Do not let two more legacy source-only audits execute on production VENTUNO."""

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    ("ventuno-web-socket-ssrf-source-audit.yml", "MYAI_SSRF_AUDIT_SCRATCH",
     "myai-ssrf-audit-venv"),
    ("ventuno-final-source-revision-closeout.yml", "MYAI_MAIN_TRIGGER_SCRATCH",
     "myai-final-source-venv"),
)


@pytest.mark.parametrize("name,scratch,venv", WORKFLOWS)
def test_source_only_workflow_uses_hosted_arm64_exact_sha(name, scratch, venv):
    s = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
    assert "runs-on: ubuntu-24.04-arm" in s
    assert "runs-on: [self-hosted" not in s
    assert "RUNNER_ENVIRONMENT: ${{ runner.environment }}" in s
    assert 'test "$RUNNER_ENVIRONMENT" = "github-hosted"' in s
    assert 'test "$(uname -m)" = aarch64' in s
    assert "contents: read" in s
    assert "  push:" in s
    assert "rev-parse HEAD" in s
    assert '"$GITHUB_SHA"' in s
    assert "remote set-url origin" in s


@pytest.mark.parametrize("name,scratch,venv", WORKFLOWS)
def test_source_only_does_not_touch_installed_ventuno_python_or_services(
    name, scratch, venv,
):
    s = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
    assert "/home/arduino/" not in s
    assert "systemctl" not in s
    assert "sudo " not in s
    assert "id -un" not in s
    assert "Install audit dependencies in disposable hosted ARM64 venv" in s
    assert "--only-binary=:all:" in s
    assert "python3 -m venv" in s
    assert '-r "$' + scratch + '/requirements.txt"' in s
    assert 'MYAI_AUDIT_PY=$RUNNER_TEMP/' + venv + "/bin/python" in s
    assert 'rm -rf -- "$RUNNER_TEMP/' + venv + '"' in s
    assert s.count('"$MYAI_AUDIT_PY" -B -m') >= 2
    assert s.index('test "$RUNNER_ENVIRONMENT" = "github-hosted"') < s.index("git init")
    assert s.index("rev-parse HEAD") < s.index("python3 -m venv")
    assert s.index("python3 -m venv") < s.index('"$MYAI_AUDIT_PY" -B -m')


def test_newly_isolated_workflows_not_retroactively_approved_by_old_snapshot():
    manifest = json.loads(
        (ROOT / "config/ventuno_manual_workflow_git_oids_20261016.json")
        .read_text(encoding="utf-8")
    )
    assert manifest["production_release_authorized"] is False
    assert manifest["source_review_complete"] is False
    assert len(manifest["manual_workflow_git_blob_oids"]) == 103
    assert all(
        name not in manifest["manual_workflow_git_blob_oids"]
        for name, _, _ in WORKFLOWS
    )
