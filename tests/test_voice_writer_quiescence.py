"""Disposable, POSIX-only writer-presence safety tests.

No live processes, real user files, microphones, NPU or MyAI runtime.
"""
import multiprocessing
import os
import time

import pytest

from core.tool_manager import run_tools, EXECUTION_FAILED_MESSAGE
from core.voice_write_journal import (
    ACTIVE_LOCK, MARKER, VoiceWriteAheadMarker,
)
from core.voice_write_recovery import (
    ATTESTATION_PREFIX, VoiceWriteReconciliation,
)


def _hold_writer(root, send_ready, recv_exit):
    """Synthetic second process; no actual file-writing tool."""
    marker = VoiceWriteAheadMarker(root)
    with marker.active_writer():
        send_ready.send("lease-active")
        if recv_exit.recv() != "release":
            os._exit(72)


def _start_leased_process(root):
    ctx = multiprocessing.get_context("fork")
    ready_recv, ready_send = ctx.Pipe(duplex=False)
    release_recv, release_send = ctx.Pipe(duplex=False)
    process = ctx.Process(
        target=_hold_writer,
        args=(str(root), ready_send, release_recv),
    )
    process.start()
    ready_send.close()
    release_recv.close()
    try:
        assert ready_recv.poll(5), "Synthetic child did not acquire lease"
        assert ready_recv.recv() == "lease-active"
        return process, release_send
    finally:
        ready_recv.close()


def _stop_leased_process(process, release_send):
    try:
        if process.is_alive():
            release_send.send("release")
        process.join(timeout=5)
        assert process.exitcode == 0
    finally:
        release_send.close()
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        process.close()


def test_distinct_process_writer_lease_denies_manual_release(tmp_path):
    journal = VoiceWriteAheadMarker(tmp_path)
    assert journal.begin_effect()
    recovery = VoiceWriteReconciliation(tmp_path)
    ticket = recovery.prepare()
    child, sender = _start_leased_process(tmp_path)
    try:
        with pytest.raises(OSError):
            recovery.finalize(ticket, ATTESTATION_PREFIX + ticket)
        assert (tmp_path / "runtime" / MARKER).exists()
        assert recovery.inspect() == {"status": "review_ticket_pending"}
    finally:
        _stop_leased_process(child, sender)

    assert recovery.finalize(ticket, ATTESTATION_PREFIX + ticket)
    assert not (tmp_path / "runtime" / MARKER).exists()


def test_distinct_process_writer_lease_denies_prepare(tmp_path):
    journal = VoiceWriteAheadMarker(tmp_path)
    assert journal.begin_effect()
    child, sender = _start_leased_process(tmp_path)
    try:
        with pytest.raises(OSError):
            VoiceWriteReconciliation(tmp_path).prepare()
        assert (tmp_path / "runtime" / MARKER).exists()
    finally:
        _stop_leased_process(child, sender)
    ticket = VoiceWriteReconciliation(tmp_path).prepare()
    assert len(ticket) == 32
    assert (tmp_path / "runtime" / MARKER).exists()


def test_scoped_guarded_tool_holds_writer_presence_through_callback(tmp_path):
    journal = VoiceWriteAheadMarker(tmp_path)
    calls = []

    def action():
        # A marker already exists; while the callback is executing,
        # the offline operator cannot even PREPARE a release ticket.
        assert journal.review_required
        with pytest.raises(OSError):
            VoiceWriteReconciliation(tmp_path).prepare()
        calls.append("performed")
        return "verified-synthetic"

    results = run_tools(
        ["workspace_write"],
        {"workspace_write": {"function": action}},
        execution_guard=lambda *_: True,
        execution_before_call=lambda *_: journal.begin_effect(),
        execution_call_scope=lambda *_: journal.active_writer(),
        execution_cancelled=lambda: False,
    )
    assert results == {"workspace_write": "verified-synthetic"}
    assert calls == ["performed"]
    assert VoiceWriteReconciliation(tmp_path).prepare()
    # The lease closes but the marker still protects any later voice write.
    assert VoiceWriteAheadMarker(tmp_path).review_required


def test_scoped_guarded_tool_releases_lease_even_if_callback_raises(tmp_path):
    journal = VoiceWriteAheadMarker(tmp_path)
    effects = []

    def failed():
        effects.append("possibly-performed")
        with pytest.raises(OSError):
            VoiceWriteReconciliation(tmp_path).prepare()
        raise RuntimeError("SYNTHETIC_PRIVATE_FAILURE")

    output = run_tools(
        ["workspace_write"],
        {"workspace_write": {"function": failed}},
        execution_guard=lambda *_: True,
        execution_before_call=lambda *_: journal.begin_effect(),
        execution_call_scope=lambda *_: journal.active_writer(),
        execution_cancelled=lambda: False,
    )
    assert effects == ["possibly-performed"]
    assert output == {"workspace_write": EXECUTION_FAILED_MESSAGE}
    assert VoiceWriteReconciliation(tmp_path).prepare()


def test_active_writer_lease_is_reaped_on_child_process_exit(tmp_path):
    marker = VoiceWriteAheadMarker(tmp_path)
    assert marker.begin_effect()
    token = VoiceWriteReconciliation(tmp_path).prepare()
    child, sender = _start_leased_process(tmp_path)
    try:
        assert child.is_alive()
        child.terminate()  # Synthetic crash, no active board process.
        child.join(timeout=5)
        assert child.exitcode is not None
    finally:
        sender.close()
        if child.is_alive():
            child.kill()
            child.join(timeout=5)
        child.close()
    recovery = VoiceWriteReconciliation(tmp_path)
    assert recovery.finalize(token, ATTESTATION_PREFIX + token)


def test_untrusted_active_writer_lock_fails_closed(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    sentinel = tmp_path / "safe-sentinel"
    sentinel.write_text("NO_CHANGE", encoding="utf-8")
    (runtime / ACTIVE_LOCK).symlink_to(sentinel)
    journal = VoiceWriteAheadMarker(tmp_path)
    with pytest.raises(OSError):
        with journal.active_writer():
            pytest.fail("Symlinked active lock must not be accepted")
    assert sentinel.read_text(encoding="utf-8") == "NO_CHANGE"
    assert not (runtime / MARKER).exists()


def test_failed_writer_lease_scope_denies_effect_before_marker(tmp_path):
    effects = []

    class NoLease:
        def __enter__(self):
            raise OSError("SYNTHETIC_NO_WRITER_LEASE")
        def __exit__(self, *_args):
            return False

    result = run_tools(
        ["workspace_write"],
        {"workspace_write": {"function": lambda: effects.append("unsafe")}},
        execution_guard=lambda *_: True,
        execution_call_scope=lambda *_: NoLease(),
        execution_before_call=lambda *_: pytest.fail("not called"),
    )
    from core.tool_manager import EXECUTION_BLOCKED_MESSAGE
    assert result == {"workspace_write": EXECUTION_BLOCKED_MESSAGE}
    assert effects == []
