"""Pure regression of disposable independent Ed25519 observer source policy.

These tests NEVER fork, change UID, bind sockets, issue secrets or run Docker.
The actual four-UID and signer subprocess integration is a separate hosted job.
"""
from pathlib import Path
import hashlib
import stat
from types import SimpleNamespace

import pytest

from scripts import test_disposable_ed25519_observer as demo


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/disposable-independent-ed25519-observer.yml"
SCRIPT = ROOT / "scripts/test_disposable_ed25519_observer.py"


class FakePrivateFixture:
    def __init__(self, source=demo.SOURCE, uid=demo.VERIFIER):
        self.source = source
        self.uid = uid
    def __truediv__(self, child):
        assert child == "fixture.py"
        return self
    def lstat(self):
        return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=self.uid)
    def read_bytes(self):
        return self.source
    def __str__(self):
        return "/test-owned-private/fixed-fixture.py"


def test_real_fixture_digests_are_bound_to_fixed_own_observation():
    assert len({demo.UPDATER, demo.RUNTIME, demo.CI, demo.VERIFIER}) == 4
    assert demo.SOURCE_SHA == hashlib.sha256(b"SAFE = 1\n").hexdigest()
    assert demo.MANIFEST_SHA == hashlib.sha256(
        b"synthetic-fixture.py:" + demo.SOURCE_SHA.encode("ascii")
    ).hexdigest()
    assert demo.EVIDENCE_SHA == hashlib.sha256(
        b"MyAI/disposable-observation/v1\n"
        + demo.SOURCE_SHA.encode("ascii") + b"\nexit=0\n"
    ).hexdigest()


def test_verifier_performs_fixed_own_subprocess_observation(monkeypatch):
    observed = []
    def runner(argv, **kwargs):
        observed.append((argv, kwargs))
        return SimpleNamespace(
            returncode=0, stdout=demo.SOURCE_SHA + "\n", stderr=""
        )
    monkeypatch.setattr(demo.subprocess, "run", runner)
    assert demo.independent_observation(FakePrivateFixture()) == demo.EVIDENCE_SHA
    assert len(observed) == 1
    argv, args = observed[0]
    assert argv[1:4] == ["-I", "-B", "-c"]
    assert argv[-1] == "/test-owned-private/fixed-fixture.py"
    assert "ast.parse(" in argv[4]
    assert args["timeout"] == 4
    assert args["check"] is False
    assert args["env"] == {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp", "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"
    }


@pytest.mark.parametrize("bad", [
    b"SAFE = 2\n", b"", b"import os\n", b"SAFE = 1\nBAD=2\n"
])
def test_observation_never_accepts_changed_fixture(monkeypatch, bad):
    def forbidden(*a, **kw):
        raise AssertionError("Should not launch child for changed bytes")
    monkeypatch.setattr(demo.subprocess, "run", forbidden)
    with pytest.raises(AssertionError):
        demo.independent_observation(FakePrivateFixture(source=bad))


def test_observation_never_accepts_wrong_owner(monkeypatch):
    monkeypatch.setattr(demo.subprocess, "run", lambda *a, **kw: None)
    with pytest.raises(PermissionError):
        demo.independent_observation(FakePrivateFixture(uid=demo.RUNTIME))


@pytest.mark.parametrize("outcome", [
    dict(returncode=1, stdout="", stderr="failed"),
    dict(returncode=0, stdout="", stderr=""),
    dict(returncode=0, stdout="f" * 64 + "\n", stderr=""),
    dict(returncode=0, stdout=demo.SOURCE_SHA + "\n", stderr="unexpected"),
])
def test_observer_fails_closed_on_child_errors(monkeypatch, outcome):
    monkeypatch.setattr(
        demo.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(**outcome),
    )
    with pytest.raises(AssertionError):
        demo.independent_observation(FakePrivateFixture())


def test_test_only_key_created_in_verifier_child_not_public_producer():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "def verifier(" in source
    assert "as_uid(VERIFIER)" in source
    assert "Ed25519PrivateKey.generate()" in source
    assert "private_bytes(" not in source
    assert "key.sign(signed)" in source
    assert "require_peer_uid(connection, expected_uid=UPDATER)" in source
    assert "parse_inspection_message(receive_frame(connection))" in source
    assert "independent_observation(private)" in source
    assert '"passed": True, "sandbox": "bubblewrap"' in source
    # This is synthetic, not real Bubblewrap. Never misreport actual security.
    assert '"test_only_signature_has_synthetic_bubblewrap_flag": True' in source
    assert '"real_bubblewrap_evidence_proven": False' in source
    assert '"production_verifier_service_implemented": False' in source
    assert '"production_deployment_authorized": False' in source
    assert "consume_signed_inspection(" in source
    assert "issue_inspection_challenge(" in source


def test_workflow_is_disposable_hosted_networkless_and_pin_narrow_sources():
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert "runs-on: ubuntu-24.04" in wf
    assert "runs-on: [self-hosted" not in wf
    assert "RUNNER_ENVIRONMENT: " + "${{ runner.environment }}" in wf
    assert 'test "$RUNNER_ENVIRONMENT" = "github-hosted"' in wf
    assert 'test "$(uname -m)" = "x86_64"' in wf
    assert "permissions:\n  contents: read" in wf
    assert "on:\n  push:" in wf
    assert "workflow_dispatch:" not in wf
    assert "docker run --rm --network none --read-only" in wf
    assert "--cap-drop ALL" in wf
    assert "--security-opt no-new-privileges" in wf
    assert "--tmpfs /tmp:rw,nosuid,nodev,size=64m" in wf
    assert "sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258" in wf
    assert wf.count("type=bind") == 5
    assert "dst=/opt/demo.py,readonly" in wf
    assert "dst=/opt/core/selfdev_signed_evidence.py,readonly" in wf
    assert "dst=/opt/core/selfdev_attestation_replay.py,readonly" in wf
    assert "dst=/opt/core/selfdev_unix_peercred.py,readonly" in wf
    assert "dst=/opt/wheels,readonly" in wf
    assert "cryptography==45.0.7" in wf
    assert "--no-index --find-links=/opt/wheels" in wf
    assert '"$GITHUB_SHA"' in wf
    assert "rev-parse HEAD" in wf
    assert "/home/arduino/" not in wf
    assert "secrets." not in wf
    assert "GH_TOKEN" not in wf
    assert "--privileged" not in wf
    assert "docker.sock" not in wf


def test_never_runs_on_import():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in source
    assert "disposable_only()" in source
    assert 'os.environ.get("MYAI_DISPOSABLE_UID_TEST")' in source
    assert 'Path("/.dockerenv").is_file()' in source
