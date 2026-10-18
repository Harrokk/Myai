"""No UID changes, Docker, sockets, process fork or file writes at collection."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/test_disposable_witness_file_boundary.py"
WORKFLOW = ROOT / ".github/workflows/disposable-witness-file-boundary.yml"


def test_witness_identity_dac_and_atomic_writer_are_explicit():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "WITNESS_UID = 23005" in source
    assert "OTHER_UIDS = (23001, 23002, 23003)" in source
    assert "os.setgroups([])" in source
    assert "os.setgid(uid)" in source
    assert "os.setuid(uid)" in source
    assert "os.chown(private, WITNESS_UID, WITNESS_UID)" in source
    assert "private.chmod(0o700)" in source
    assert "os.open(temporary, flags, 0o600)" in source
    assert "os.O_EXCL" in source
    assert "os.replace(temporary, final)" in source
    assert "os.fsync(fd)" in source
    assert "os.fsync(dir_fd)" in source
    assert "os.replace(source_path, final)" in source


def test_disposable_script_has_no_live_identity_or_signing_side_effect_on_import():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in source
    assert 'os.environ.get("MYAI_DISPOSABLE_WITNESS_TEST")' in source
    assert 'Path("/.dockerenv").is_file()' in source
    assert '"production_deployment_authorized": False' in source
    assert '"ventuno_touched": False' in source
    assert '"physical_power_loss_durability_proven": False' in source
    assert '"test_witness_contents_are_synthetic_unsigned": True' in source
    assert "Ed25519PrivateKey" not in source
    assert "SelfDevPromotionManager" not in source
    assert "systemctl" not in source


def test_hosted_workflow_pins_disposable_networkless_root_and_single_script():
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert "runs-on: ubuntu-24.04" in wf
    assert "runs-on: [self-hosted" not in wf
    assert "permissions:\n  contents: read" in wf
    assert 'test "$RUNNER_ENVIRONMENT" = "github-hosted"' in wf
    assert '"$GITHUB_SHA"' in wf
    assert "rev-parse HEAD" in wf
    assert "docker run --rm --network none --read-only" in wf
    assert "--security-opt no-new-privileges" in wf
    assert "--cap-drop ALL" in wf
    assert "--tmpfs /tmp:rw,nosuid,nodev,size=32m" in wf
    assert wf.count("type=bind") == 1
    assert "dst=/opt/test-witness.py,readonly" in wf
    assert "sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258" in wf
    assert "workflow_dispatch:" not in wf
    assert "secrets." not in wf
    assert "/home/arduino/" not in wf
    assert "docker.sock" not in wf
    assert "--privileged" not in wf
