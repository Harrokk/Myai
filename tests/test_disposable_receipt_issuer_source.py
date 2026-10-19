"""Source-only checks: never launch root/fork/UID/socket in normal ARM64 CI."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/test_disposable_receipt_issuer.py"
WORKFLOW = ROOT / ".github/workflows/disposable-independent-receipt-issuer.yml"


def test_signer_key_created_after_uid_drop_and_only_after_fixed_inspection():
    src = SCRIPT.read_text()
    start = src.index("def issuer(")
    stop = src.index("\ndef probe(", start)
    body = src[start:stop]
    assert body.index("drop(SIGNER)") < body.index("Ed25519PrivateKey.generate()")
    assert body.index("require_peer_uid(connection, expected_uid=UPDATER)") < (
        body.index("parse_inspection_message(receive_frame(connection))")
    )
    assert body.index("inspect_candidate_for_receipt(") < (
        body.index("signing_key.sign(canonical_milestone_receipt(statement))")
    )
    assert "if challenge != NONCE:" in body
    assert "claim_receipt_once(" in body
    assert body.index("claim_receipt_once(") < body.index("signing_key.sign(")
    assert '"passed": True' not in body
    assert "private_bytes(" not in src
    assert "SelfDevPromotionManager" not in src
    assert '"production_deployment_authorized": False' in src
    assert '"real_disk_write_proven": False' in src
    assert '"fresh_external_head_proven": False' in src
    assert '"ventuno_touched": False' in src


def test_disposable_integration_gates_synthetic_secret_and_real_uid():
    src = SCRIPT.read_text()
    assert 'if __name__ == "__main__":' in src
    assert 'MYAI_HOSTED_RECEIPT_UID_TEST' in src
    assert 'MYAI_RUNNER_ENVIRONMENT' in src
    assert 'Path("/.dockerenv").exists()' in src
    assert "os.setgroups([])" in src
    assert "os.setgid(uid)" in src
    assert "os.setuid(uid)" in src
    assert "private_dir.chmod(0o700)" in src
    assert "os.chmod(journal_path, 0o600)" in src
    assert "os.chmod(witness_path, 0o600)" in src
    assert "os.chmod(address, 0o666)" in src
    assert 'request["passed"] = True' in src
    assert '("replay")' not in src  # replay is a named probe, never code execution


def test_hosted_workflow_is_narrow_exact_sha_read_only_and_self_hosted_free():
    wf = WORKFLOW.read_text()
    assert "runs-on: ubuntu-22.04" in wf
    assert "runs-on: [self-hosted" not in wf
    assert "workflow_dispatch:" not in wf
    assert "permissions:\n  contents: read" in wf
    assert 'test "$RUNNER_ENVIRONMENT" = "github-hosted"' in wf
    assert 'test "$(uname -m)" = "x86_64"' in wf
    assert 'test "$(id -u)" -ne 0' in wf
    assert 'test "$(git -C "$checkout" rev-parse HEAD)" = "$GITHUB_SHA"' in wf
    assert "sudo env" in wf
    assert "MYAI_HOSTED_RECEIPT_UID_TEST=yes" in wf
    assert '"cryptography==45.0.7"' in wf
    assert "dst=/home/arduino" not in wf
    assert "secrets." not in wf
    assert "sudo systemctl" not in wf
    assert "git push" not in wf
    assert "docker.sock" not in wf
