"""Subprocess crash-injection at each operator receipt/marker boundary.

Only ephemeral tmp_path contents are touched, never a live MyAI runtime.
Real power loss and storage cache loss are intentionally NOT simulated.
"""
import os
import subprocess
import sys

import pytest

from core.voice_write_journal import MARKER, VoiceWriteAheadMarker
from core.voice_write_recovery import (
    ATTESTATION_PREFIX, PENDING, RECEIPT_PREFIX, RECEIPT_SUFFIX,
    VoiceWriteReconciliation,
)


CHILD = r"""
import os, sys
from core.voice_write_recovery import (
    PENDING, MARKER, ATTESTATION_PREFIX, VoiceWriteReconciliation,
)
root, token, phase = sys.argv[1:]
state = {"linked": False, "pending_removed": False, "marker_removed": False}
actual_link, actual_unlink, actual_fsync = os.link, os.unlink, os.fsync

def inject_link(*args, **kwargs):
    result = actual_link(*args, **kwargs)
    state["linked"] = True
    if phase == "after_link":
        os._exit(79)
    return result

def inject_unlink(name, *args, **kwargs):
    result = actual_unlink(name, *args, **kwargs)
    if name == PENDING:
        state["pending_removed"] = True
        if phase == "after_unlink_pending":
            os._exit(79)
    if name == MARKER:
        state["marker_removed"] = True
        if phase == "after_unlink_marker":
            os._exit(79)
    return result

def inject_fsync(fd):
    result = actual_fsync(fd)
    if state["marker_removed"] and phase == "after_marker_fsync":
        os._exit(79)
    if state["pending_removed"] and phase == "after_pending_fsync":
        os._exit(79)
    if state["linked"] and phase == "after_receipt_fsync":
        os._exit(79)
    return result

os.link = inject_link
os.unlink = inject_unlink
os.fsync = inject_fsync
VoiceWriteReconciliation(root).finalize(token, ATTESTATION_PREFIX + token)
sys.exit(0)
"""


@pytest.mark.parametrize("phase,marker_present", [
    ("after_link", True),
    ("after_receipt_fsync", True),
    ("after_unlink_pending", True),
    ("after_pending_fsync", True),
    ("after_unlink_marker", False),
    ("after_marker_fsync", False),
])
def test_reconciliation_crash_boundaries_keep_receipt_and_recover_safely(
        tmp_path, phase, marker_present):
    journal = VoiceWriteAheadMarker(tmp_path)
    assert journal.begin_effect()
    recovery = VoiceWriteReconciliation(tmp_path)
    token = recovery.prepare()
    result = subprocess.run(
        [sys.executable, "-c", CHILD, str(tmp_path), token, phase],
        timeout=8, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=False,
    )
    assert result.returncode == 79
    marker = tmp_path / "runtime" / MARKER
    receipt = tmp_path / "runtime" / (
        RECEIPT_PREFIX + token + RECEIPT_SUFFIX
    )
    assert marker.exists() is marker_present
    assert receipt.exists()
    assert receipt.read_bytes().startswith(
        b"MYAI-VOICE-REVIEW-TICKET-v1\n"
    )

    if marker_present:
        # No unattended replay. Same ticket and explicit operator
        # confirmation are required to resume this interrupted release.
        assert VoiceWriteAheadMarker(tmp_path).review_required
        assert recovery.finalize(token, "not approved") is False
        assert marker.exists()
        assert recovery.finalize(token, ATTESTATION_PREFIX + token) is True
        assert not marker.exists()
    else:
        assert recovery.inspect() == {"status": "no_marker"}
    assert receipt.exists()
    assert not (tmp_path / "runtime" / PENDING).exists()


def test_crash_before_review_ticket_is_complete_stays_blocked(tmp_path):
    marker = VoiceWriteAheadMarker(tmp_path)
    assert marker.begin_effect()
    script = r"""
import os, sys
from core.voice_write_recovery import VoiceWriteReconciliation
real = os.write
def fail_ticket(fd, blob):
    if blob.startswith(b"MYAI-VOICE-REVIEW-TICKET-v1"):
        os._exit(81)
    return real(fd, blob)
os.write = fail_ticket
VoiceWriteReconciliation(sys.argv[1]).prepare()
"""
    p = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        timeout=8, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=False,
    )
    assert p.returncode == 81
    assert VoiceWriteAheadMarker(tmp_path).review_required
    recovery = VoiceWriteReconciliation(tmp_path)
    with pytest.raises(OSError):
        recovery.inspect()
    with pytest.raises(FileExistsError):
        recovery.prepare()
    assert (tmp_path / "runtime" / MARKER).exists()


def test_marker_unlink_fsync_error_requires_inspection_not_retry(
        tmp_path, monkeypatch):
    journal = VoiceWriteAheadMarker(tmp_path)
    assert journal.begin_effect()
    recovery = VoiceWriteReconciliation(tmp_path)
    token = recovery.prepare()
    original = os.fsync
    state = {"removed": False}

    real_unlink = os.unlink
    def unlink_tracking(name, *args, **kwargs):
        result = real_unlink(name, *args, **kwargs)
        if name == MARKER:
            state["removed"] = True
        return result
    def fail_final_fsync(fd):
        if state["removed"]:
            raise OSError("SYNTHETIC_FS_ERROR")
        return original(fd)

    monkeypatch.setattr(os, "unlink", unlink_tracking)
    monkeypatch.setattr(os, "fsync", fail_final_fsync)
    with pytest.raises(OSError):
        recovery.finalize(token, ATTESTATION_PREFIX + token)
    assert state["removed"]
    assert (tmp_path / "runtime" / MARKER).exists() is False
    assert (tmp_path / "runtime" / (
        RECEIPT_PREFIX + token + RECEIPT_SUFFIX)).exists()
    # A reported error here does NOT prove the marker is still present.
    # Recovery must never repeat the previously performed external effect.
