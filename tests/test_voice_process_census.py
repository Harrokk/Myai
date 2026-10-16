"""Source-only Linux /proc veto tests; no real MyAI service interaction."""
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

from core.voice_process_census import (
    _parent_pid, detect_project_processes,
    veto_recognised_project_processes,
)
from core.voice_write_journal import MARKER, VoiceWriteAheadMarker
from core.voice_write_recovery import (
    ATTESTATION_PREFIX, VoiceWriteReconciliation,
)
from scripts.voice_write_reconcile import main

LINUX_PROC = Path("/proc").is_dir()


def _synthetic_parent(root, *, descendants=False):
    if descendants:
        source = (
            "import subprocess,sys\n"
            "p=subprocess.Popen([sys.executable,'-c',"
            "'import time;time.sleep(25)'])\n"
            "print('SYNTHETIC_READY',flush=True)\n"
            "p.wait()\n"
        )
    else:
        source = (
            "import time\n"
            "print('SYNTHETIC_READY',flush=True)\n"
            "time.sleep(25)\n"
        )
    p = subprocess.Popen(
        [sys.executable, "-c", source, str(root)],
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert p.stdout.readline().strip() == "SYNTHETIC_READY"
        return p
    except BaseException:
        os.killpg(p.pid, signal.SIGKILL)
        p.wait(timeout=5)
        raise


def _stop(parent):
    try:
        if parent.poll() is None:
            os.killpg(parent.pid, signal.SIGTERM)
        parent.wait(timeout=5)
    finally:
        if parent.poll() is None:
            os.killpg(parent.pid, signal.SIGKILL)
            parent.wait(timeout=5)
        parent.stdout.close()


@pytest.mark.skipif(not LINUX_PROC, reason="Procfs source-only Linux test")
def test_recognisable_older_process_vetoes_prepare_and_release(tmp_path):
    journal = VoiceWriteAheadMarker(tmp_path)
    assert journal.begin_effect()
    recovery = VoiceWriteReconciliation(tmp_path)
    ticket = recovery.prepare()
    process = _synthetic_parent(tmp_path)
    try:
        assert detect_project_processes(tmp_path) >= 1
        with pytest.raises(OSError):
            recovery.prepare()
        with pytest.raises(OSError):
            recovery.finalize(ticket, ATTESTATION_PREFIX + ticket)
        assert (tmp_path / "runtime" / MARKER).exists()
    finally:
        _stop(process)
    assert detect_project_processes(tmp_path) == 0
    assert recovery.finalize(ticket, ATTESTATION_PREFIX + ticket)
    assert not (tmp_path / "runtime" / MARKER).exists()


@pytest.mark.skipif(not LINUX_PROC, reason="Procfs source-only Linux test")
def test_recognised_process_descendants_with_unrelated_args_veto(tmp_path):
    process = _synthetic_parent(tmp_path, descendants=True)
    try:
        # Child Python has no project-root token and does not hold a
        # writer flock, but is a visible descendant of matched parent.
        assert detect_project_processes(tmp_path) >= 2
        with pytest.raises(OSError):
            veto_recognised_project_processes(tmp_path)
    finally:
        _stop(process)


@pytest.mark.skipif(not LINUX_PROC, reason="Procfs source-only Linux test")
def test_unrelated_synthetic_python_process_not_inaccurately_attributed(tmp_path):
    p = subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(25)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert detect_project_processes(tmp_path) == 0
    finally:
        p.terminate()
        p.wait(timeout=5)


def test_procfs_missing_denies_release_and_never_clears_marker(
        tmp_path, monkeypatch):
    marker = VoiceWriteAheadMarker(tmp_path)
    assert marker.begin_effect()
    recovery = VoiceWriteReconciliation(tmp_path)
    ticket = recovery.prepare()
    import core.voice_write_recovery as module
    monkeypatch.setattr(
        module, "veto_recognised_project_processes",
        lambda _path: (_ for _ in ()).throw(
            OSError("SYNTHETIC_INCOMPLETE_PROCFS")
        ),
    )
    with pytest.raises(OSError):
        recovery.finalize(ticket, ATTESTATION_PREFIX + ticket)
    assert (tmp_path / "runtime" / MARKER).exists()


def test_missing_procfs_scan_is_not_considered_zero(tmp_path):
    absent = tmp_path / "not-a-proc-mount"
    with pytest.raises(OSError):
        detect_project_processes(tmp_path, proc_root=absent)


def test_oversized_same_uid_proc_cmdline_denies_instead_of_guessing(tmp_path):
    fake = tmp_path / "proc"
    fake.mkdir()
    proc = fake / "4999987"
    proc.mkdir()
    (proc / "stat").write_bytes(b"4999987 (fixture name) S 1\n")
    (proc / "cmdline").write_bytes(b"x" * 16385)
    (proc / "cwd").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError):
        detect_project_processes(tmp_path, proc_root=fake)


def test_parent_pid_parser_handles_spaces_and_parentheses_in_comm(tmp_path):
    statfile = tmp_path / "stat"
    statfile.write_bytes(b"123 (my strange (child) process) S 456 0\n")
    assert _parent_pid(statfile) == 456


def test_cli_process_count_is_diagnostic_not_an_unlock(
        tmp_path, monkeypatch, capsys):
    from scripts import voice_write_reconcile as cli
    class NoTTY:
        def isatty(self):
            return False
    monkeypatch.setattr(cli.sys, "stdin", NoTTY())
    marker = VoiceWriteAheadMarker(tmp_path)
    assert marker.begin_effect()
    assert main(["--project-root", str(tmp_path), "processes"]) == 0
    text = capsys.readouterr().out
    assert "does NOT establish" in text
    assert marker.review_required
    assert (tmp_path / "runtime" / MARKER).exists()
