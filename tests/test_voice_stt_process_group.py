"""Only synthetic Linux subprocesses, never a speech model or microphone."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

import pytest

from core.voice_stt_process_group import (
    _live_group_members, terminate_owned_group,
)
from core.voice_stt_process import run_deadlined


def _leader_with_helper(record_path, *, linger=False):
    # Helper inherits the isolated leader's session/group but NOT the
    # stdout pipe; the leader can exit while its helper sleeps 60s.
    source = (
        "import pathlib,subprocess,sys,time\n"
        "helper=subprocess.Popen([sys.executable,'-I','-c',"
        " 'import time;time.sleep(60)'],"
        " stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,"
        " stderr=subprocess.DEVNULL)\n"
        f"pathlib.Path({str(record_path)!r}).write_text(str(helper.pid))\n"
        + ("time.sleep(60)\n" if linger else "sys.exit(0)\n")
    )
    return subprocess.Popen(
        [sys.executable, "-I", "-u", "-c", source],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, start_new_session=True,
    )


def _wait_helper_file(path):
    end = time.monotonic() + 3
    while time.monotonic() < end:
        if path.exists():
            value = path.read_text().strip()
            if value.isdigit():
                return int(value)
        time.sleep(0.02)
    pytest.fail("Synthetic helper did not start")


def _safe_cleanup_group(proc):
    # Only the disposable group created by the test, never system units.
    if proc is None:
        return
    if _live_group_members(proc.pid):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        proc.wait(timeout=2)
    for stream in (proc.stdin, proc.stdout):
        if stream is not None:
            stream.close()


def test_helper_is_killed_after_stt_leader_already_exited(tmp_path):
    pid_file = tmp_path / "synthetic-helper-pid"
    proc = _leader_with_helper(pid_file)
    try:
        _wait_helper_file(pid_file)
        assert proc.wait(timeout=3) == 0
        # The leader has been reaped but its process GROUP remains.
        assert _live_group_members(proc.pid) is True
        terminate_owned_group(proc)
        assert _live_group_members(proc.pid) is False
        assert proc.poll() == 0
    finally:
        _safe_cleanup_group(proc)


def test_helper_and_active_parent_are_killed_together(tmp_path):
    pid_file = tmp_path / "active-helper-pid"
    proc = _leader_with_helper(pid_file, linger=True)
    try:
        _wait_helper_file(pid_file)
        assert proc.poll() is None
        assert _live_group_members(proc.pid) is True
        terminate_owned_group(proc)
        assert proc.poll() is not None
        assert _live_group_members(proc.pid) is False
    finally:
        _safe_cleanup_group(proc)


def test_group_cleanup_with_invalid_or_own_pgid_never_sends_signal(monkeypatch):
    class NotOwned:
        pid = os.getpgrp()
    monkeypatch.setattr(
        os, "killpg",
        lambda *_: pytest.fail("Must never signal CI runner process group"),
    )
    with pytest.raises(RuntimeError, match="cleanup incomplete"):
        terminate_owned_group(NotOwned())


def test_failed_member_scan_is_hard_no_go_without_killing(monkeypatch):
    import core.voice_stt_process_group as module
    class Unknown:
        pid = 1234567
    monkeypatch.setattr(module, "_live_group_members", lambda *_: None)
    monkeypatch.setattr(
        module.os, "killpg",
        lambda *_: pytest.fail("Cannot signal an unverified process group"),
    )
    with pytest.raises(RuntimeError, match="cleanup incomplete"):
        terminate_owned_group(Unknown())


def test_one_shot_timeout_kills_forked_helper_that_holds_stdout(tmp_path):
    pid_file = tmp_path / "stdout-leak-helper-pid"
    source = (
        "import pathlib,subprocess,sys\n"
        "helper=subprocess.Popen([sys.executable,'-I','-c',"
        " 'import time;time.sleep(60)'],"
        " stdin=subprocess.DEVNULL,stderr=subprocess.DEVNULL,"
        " stdout=sys.stdout)\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(helper.pid))\n"
        "sys.stdout.write('')\n"
    )
    # The leader exits, but the helper keeps stdout's write fd open.
    # communicate() would hang without the hard post-return timeout.
    with pytest.raises(TimeoutError, match="deadline exceeded"):
        run_deadlined([sys.executable, "-I", "-u", "-c", source], b"pcm", 1)
    assert _wait_helper_file(pid_file) > 1



def test_persistent_stt_close_cleans_helper_after_valid_leader_reply(tmp_path):
    """A valid transcript does not excuse a leaked native helper."""
    from core.voice_stt_persistent import PersistentFasterWhisperSTT

    record = tmp_path / "persistent-orphan-helper-pid"
    source = (
        "import json,struct,pathlib,subprocess,sys\n"
        "stream=sys.stdin.buffer\n"
        "n=struct.unpack('>I',stream.read(4))[0]\n"
        "assert len(stream.read(n))==n\n"
        "helper=subprocess.Popen([sys.executable,'-I','-c',"
        " 'import time;time.sleep(60)'],"
        " stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,"
        " stderr=subprocess.DEVNULL)\n"
        f"pathlib.Path({str(record)!r}).write_text(str(helper.pid))\n"
        "answer=json.dumps({'text':'synthetic','language':'sv','confidence':None}).encode()\n"
        "sys.stdout.buffer.write(struct.pack('>I',len(answer))+answer)\n"
        "sys.stdout.buffer.flush()\n"
        "sys.exit(0)\n"
    )
    model = PersistentFasterWhisperSTT(
        model_name="tiny", device="cpu", compute_type="int8",
        language="sv", sample_rate=16000, channels=1, sample_width=2,
        timeout_seconds=2, max_utterances=4,
    )
    model._argv = [sys.executable, "-I", "-u", "-c", source]
    proc = None
    try:
        result = model.transcribe(b"synthetic")
        assert result["text"] == "synthetic"
        proc = model._worker
        assert proc is not None
        assert proc.wait(timeout=3) == 0
        _wait_helper_file(record)
        assert _live_group_members(proc.pid) is True
        assert model.close() is True
        assert _live_group_members(proc.pid) is False
        assert model._worker is None
    finally:
        _safe_cleanup_group(proc)
        if model._worker is not None:
            model.close()
