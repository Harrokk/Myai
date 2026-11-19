"""Read-only source checks for the hosted cross-UID App Lab boundary."""
import ast
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1]
          / "scripts/test_disposable_app_lab_cross_uid.py")
WORKFLOW = (Path(__file__).resolve().parents[1]
            / ".github/workflows/disposable-app-lab-cross-uid.yml")


def test_cross_uid_source_requires_disposable_container_and_drops_groups():
    source = SOURCE.read_text(encoding="utf-8")
    ast.parse(source)
    assert "MYAI_DISPOSABLE_ALMA_UID_TEST" in source
    assert 'Path("/.dockerenv").exists()' in source
    assert "os.geteuid() != 0" in source
    assert "os.setgroups([])" in source
    assert "os.setgid(gid)" in source
    assert "os.setuid(uid)" in source
    assert "SERVER_UID = 23211" in source
    assert "CLIENT_UID = 23212" in source
    assert "OUTSIDER_UID = 23213" in source


def test_fixed_synthetic_text_and_ephemeral_key_transport_only():
    source = SOURCE.read_text(encoding="utf-8")
    assert "_SYNTHETIC_TRANSCRIPT" in source
    assert "_SYNTHETIC_ANSWER" in source
    assert "secrets.token_bytes(32)" in source
    assert "os.pipe()" in source
    assert "expected_peer_uid=CLIENT_UID" in source
    assert "expected_peer_uid=SERVER_UID" in source
    assert "fake_dispatches" not in source or "calls" in source
    assert '"wrong-key"' in source
    assert 'ventuno_deployment_authorized' in source


def test_docker_workflow_never_uses_self_hosted_runner():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "runs-on: ubuntu-24.04" in workflow
    assert "runner.environment" in workflow
    assert "docker run --rm --network none --read-only" in workflow
    assert "--security-opt no-new-privileges" in workflow
    assert "--cap-drop ALL" in workflow
    assert "ventuno-q" not in workflow
    assert "workflow_dispatch" not in workflow
