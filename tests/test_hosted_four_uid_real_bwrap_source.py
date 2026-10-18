"""Mock-only regression; never run sudo, fork, Bubblewrap, socket or UID changes."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import pytest
from scripts import test_hosted_four_uid_real_bwrap as demo

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/test_hosted_four_uid_real_bwrap.py"
WORKFLOW = ROOT / ".github/workflows/disposable-four-uid-real-bwrap.yml"


def successful():
    return SimpleNamespace(
        fixture_sha256=demo.SOURCE_SHA,
        plan_sha256=demo.PLAN_SHA,
        sandbox="bubblewrap",
        network_isolated=True,
        host_devices_exposed=False,
        authorizes_mutation=False,
    )


def test_four_distinct_uids_and_real_observation_digest():
    assert (demo.UPDATER, demo.RUNTIME, demo.CI, demo.VERIFIER) == (
        23001, 23002, 23003, 23004,
    )
    assert demo.SOURCE == b"SAFE = 1\n"
    assert demo.EVIDENCE_SHA == hashlib.sha256(
        b"MyAI/disposable-real-bwrap-observation/v1\0"
        + bytes.fromhex(demo.SOURCE_SHA) + bytes.fromhex(demo.PLAN_SHA)
    ).hexdigest()


def test_observation_required_to_make_signed_fixture(monkeypatch):
    calls = []
    def fake(*, trusted_fixture_root):
        calls.append(trusted_fixture_root)
        return successful()
    monkeypatch.setattr(demo, "observe", fake)
    path = Path("/fake-independent-UID")
    assert demo.independent_observation(path) == demo.EVIDENCE_SHA
    assert calls == [path]


@pytest.mark.parametrize("field,value", [
    ("fixture_sha256", "0" * 64),
    ("plan_sha256", "f" * 64),
    ("sandbox", "host"),
    ("network_isolated", False),
    ("host_devices_exposed", True),
    ("authorizes_mutation", True),
])
def test_forged_or_unsafe_bubblewrap_claim_must_fail(monkeypatch, field, value):
    item = successful()
    setattr(item, field, value)
    monkeypatch.setattr(demo, "observe", lambda **kw: item)
    with pytest.raises(RuntimeError):
        demo.independent_observation(Path("/synthetic-only"))


def test_actual_sandbox_failure_is_not_swallowed(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("bwrap unavailable")
    monkeypatch.setattr(demo, "observe", fail)
    with pytest.raises(RuntimeError, match="unavailable"):
        demo.independent_observation(Path("/fake-only"))


def test_host_guard_fail_closed_by_default(monkeypatch):
    monkeypatch.setattr(demo.os, "geteuid", lambda: 0)
    monkeypatch.delenv("MYAI_HOSTED_FOUR_UID_BWRAP", raising=False)
    with pytest.raises(RuntimeError):
        demo.disposable_only()


def test_signing_only_after_privilege_drop_and_real_bubblewrap():
    src = SCRIPT.read_text(encoding="utf-8")
    verifier = src[src.index("def verifier("):src.index("\ndef probe(")]
    assert verifier.index("as_uid(VERIFIER)") < verifier.index(
        "Ed25519PrivateKey.generate()"
    )
    assert verifier.index("result_digest = independent_observation(private)") < (
        verifier.index("key.sign(signed)")
    )
    assert "require_peer_uid(connection, expected_uid=UPDATER)" in verifier
    assert "parse_inspection_message(receive_frame(connection))" in verifier
    assert "private_bytes(" not in src
    assert "SelfDevPromotionManager" not in src
    assert '"production_deployment_authorized": False' in src
    assert '"physical_ventuno_tests_performed": False' in src


def test_updater_ledger_and_unauthorized_clients():
    src = SCRIPT.read_text(encoding="utf-8")
    assert 'request["passed"] = True' in src
    assert "issue_inspection_challenge(" in src
    assert "consume_signed_inspection(" in src
    assert "db.close()" in src
    assert "reopened = sqlite3.connect(" in src
    assert "raise AssertionError(\"Replay after DB reopen accepted\")" in src
    assert "trusted_verifier_public_key=trusted_key" in src


def test_hosted_workflow_constrains_root_only_to_disposable_runner():
    w = WORKFLOW.read_text(encoding="utf-8")
    assert "runs-on: ubuntu-22.04" in w
    assert "runs-on: [self-hosted" not in w
    assert "workflow_dispatch:" not in w
    assert "permissions:\n  contents: read" in w
    assert 'test "$RUNNER_ENVIRONMENT" = "github-hosted"' in w
    assert 'test "$(uname -m)" = "x86_64"' in w
    assert 'test "$(id -u)" -ne 0' in w
    assert 'test "$(git -C "$root" rev-parse HEAD)" = "$GITHUB_SHA"' in w
    assert "sudo env" in w
    assert "MYAI_HOSTED_FOUR_UID_BWRAP=yes" in w
    assert "MYAI_RUNNER_ENVIRONMENT=github-hosted" in w
    assert "scripts/test_hosted_four_uid_real_bwrap.py" in w
    assert "sudo apt-get install -y -qq --no-install-recommends bubblewrap" in w
    assert "sysctl -w" not in w
    assert "kernel.apparmor_restrict_unprivileged_userns=0" not in w
    assert "--share-net" not in w
    assert "/home/arduino/" not in w
    assert "secrets." not in w
    assert "docker run" not in w
    assert '"cryptography==45.0.7"' in w
