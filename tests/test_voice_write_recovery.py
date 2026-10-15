"""Synthetic offline-only operator recovery tests. Never touch real MyAI."""
import os
import stat

import pytest

from core.voice_write_journal import MARKER, BODY, VoiceWriteAheadMarker
from core.voice_write_recovery import (
    ATTESTATION_PREFIX, PENDING, RECEIPT_PREFIX, RECEIPT_SUFFIX,
    VoiceWriteReconciliation,
)
from scripts.voice_write_reconcile import main


def begin(root):
    journal = VoiceWriteAheadMarker(root)
    assert journal.begin_effect()
    return journal


def test_inspect_and_two_stage_release_preserve_durable_receipt(tmp_path):
    old = begin(tmp_path)
    recovery = VoiceWriteReconciliation(tmp_path)
    assert recovery.inspect() == {"status": "needs_external_review"}
    ticket = recovery.prepare()
    assert len(ticket) == 32
    assert (tmp_path / "runtime" / MARKER).read_bytes() == BODY
    assert recovery.inspect() == {"status": "review_ticket_pending"}
    assert recovery.finalize(ticket, "I DID NOT INSPECT ANYTHING") is False
    assert recovery.finalize("0" * 32, ATTESTATION_PREFIX + "0" * 32) is False
    assert VoiceWriteAheadMarker(tmp_path).review_required
    assert recovery.finalize(ticket, ATTESTATION_PREFIX + ticket) is True
    assert recovery.inspect() == {"status": "no_marker"}
    receipt = (
        tmp_path / "runtime" /
        (RECEIPT_PREFIX + ticket + RECEIPT_SUFFIX)
    )
    body = receipt.read_bytes()
    assert body.startswith(b"MYAI-VOICE-REVIEW-TICKET-v1\n")
    assert b"synthetic user text" not in body
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert not (tmp_path / "runtime" / PENDING).exists()
    assert not (tmp_path / "runtime" / MARKER).exists()
    # Original core remains fail-closed until intentionally recreated.
    assert old.begin_effect() is False
    new_core = VoiceWriteAheadMarker(tmp_path)
    assert new_core.begin_effect() is True
    assert receipt.read_bytes() == body


def test_cannot_prepare_twice_or_release_twice(tmp_path):
    begin(tmp_path)
    recovery = VoiceWriteReconciliation(tmp_path)
    ticket = recovery.prepare()
    with pytest.raises(FileExistsError):
        recovery.prepare()
    assert recovery.finalize(ticket, ATTESTATION_PREFIX + ticket)
    with pytest.raises(FileNotFoundError):
        recovery.finalize(ticket, ATTESTATION_PREFIX + ticket)


def test_mismatched_marker_replacement_prevents_stale_approval(tmp_path):
    begin(tmp_path)
    recovery = VoiceWriteReconciliation(tmp_path)
    ticket = recovery.prepare()
    marker = tmp_path / "runtime" / MARKER
    marker.unlink()
    marker.write_bytes(BODY)
    os.chmod(marker, 0o600)
    assert recovery.finalize(ticket, ATTESTATION_PREFIX + ticket) is False
    assert marker.exists()


def test_marker_corruption_blocks_preparation_and_release(tmp_path):
    begin(tmp_path)
    path = tmp_path / "runtime" / MARKER
    path.write_bytes(b"BAD_MARKER")
    recovery = VoiceWriteReconciliation(tmp_path)
    with pytest.raises(OSError):
        recovery.inspect()
    with pytest.raises(OSError):
        recovery.prepare()
    assert path.exists()


def test_receipt_creation_failure_keeps_original_write_marker(
        tmp_path, monkeypatch):
    begin(tmp_path)
    recovery = VoiceWriteReconciliation(tmp_path)
    ticket = recovery.prepare()
    original = os.link
    def fail_link(*_args, **_kwargs):
        raise OSError("SYNTHETIC_PRIVATE_IO_ERROR")
    monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(OSError):
        recovery.finalize(ticket, ATTESTATION_PREFIX + ticket)
    monkeypatch.setattr(os, "link", original)
    assert (tmp_path / "runtime" / MARKER).exists()
    assert recovery.inspect()["status"] == "review_ticket_pending"


def test_unlink_marker_failure_keeps_block_and_receipt(
        tmp_path, monkeypatch):
    begin(tmp_path)
    recovery = VoiceWriteReconciliation(tmp_path)
    ticket = recovery.prepare()
    original = os.unlink
    def fail_marker(name, *args, **kwargs):
        if name == MARKER:
            raise OSError("SYNTHETIC_PRIVATE_IO_ERROR")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(os, "unlink", fail_marker)
    with pytest.raises(OSError):
        recovery.finalize(ticket, ATTESTATION_PREFIX + ticket)
    monkeypatch.setattr(os, "unlink", original)
    assert VoiceWriteAheadMarker(tmp_path).review_required
    assert (tmp_path / "runtime" / (
        RECEIPT_PREFIX + ticket + RECEIPT_SUFFIX)).exists()


def test_symlinked_pending_ticket_cannot_be_read_or_released(tmp_path):
    begin(tmp_path)
    recovery = VoiceWriteReconciliation(tmp_path)
    marker = tmp_path / "runtime" / MARKER
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("PRIVATE", encoding="utf-8")
    (tmp_path / "runtime" / PENDING).symlink_to(sentinel)
    with pytest.raises(OSError):
        recovery.inspect()
    with pytest.raises(FileExistsError):
        recovery.prepare()
    with pytest.raises(OSError):
        recovery.finalize("a" * 32, ATTESTATION_PREFIX + "a" * 32)
    assert marker.exists()
    assert sentinel.read_text(encoding="utf-8") == "PRIVATE"


def test_cli_cannot_release_without_local_tty(tmp_path, monkeypatch, capsys):
    begin(tmp_path)
    class NoTTY:
        def isatty(self):
            return False
    import scripts.voice_write_reconcile as cli
    monkeypatch.setattr(cli.sys, "stdin", NoTTY())
    root = str(tmp_path)
    assert main(["--project-root", root, "inspect"]) == 0
    assert main(["--project-root", root, "prepare"]) == 2
    assert main(["--project-root", root, "release", "0" * 32]) == 2
    assert VoiceWriteAheadMarker(tmp_path).review_required
    assert "Interactive local terminal required" in capsys.readouterr().out


def test_cli_bad_attestation_never_releases_marker(
        tmp_path, monkeypatch):
    begin(tmp_path)
    ticket = VoiceWriteReconciliation(tmp_path).prepare()
    import scripts.voice_write_reconcile as cli
    class TTY:
        def isatty(self):
            return True
    monkeypatch.setattr(cli.sys, "stdin", TTY())
    monkeypatch.setattr("builtins.input", lambda *_: "not approved")
    assert main(["--project-root", str(tmp_path),
                 "release", ticket]) == 2
    assert VoiceWriteAheadMarker(tmp_path).review_required


def test_no_marker_can_not_be_prepared_for_release(tmp_path):
    recovery = VoiceWriteReconciliation(tmp_path)
    assert recovery.inspect() == {"status": "no_marker"}
    with pytest.raises(FileNotFoundError):
        recovery.prepare()


def test_stable_lock_ownership_and_private_permissions(tmp_path):
    begin(tmp_path)
    runtime = tmp_path / "runtime"
    locks = list(runtime.glob(".voice-write-safety.lock.v1"))
    assert len(locks) == 1
    assert stat.S_ISREG(locks[0].stat().st_mode)
    assert locks[0].stat().st_mode & 0o777 == 0o600
    token = VoiceWriteReconciliation(tmp_path).prepare()
    assert locks[0].exists()
    assert VoiceWriteReconciliation(tmp_path).finalize(
        token, ATTESTATION_PREFIX + token)
    assert locks[0].exists()
