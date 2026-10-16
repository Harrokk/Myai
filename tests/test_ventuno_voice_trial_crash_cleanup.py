"""Synthetic crash regression for private voice trial checkout hygiene.

A child dies abruptly after writing synthetic PCM-like bytes into a
dedicated disposable tree. The parent demonstrably reclaims the entire
tree; this is NOT a guarantee for SIGKILL of the parent/physical power loss.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile


def test_child_crash_never_moves_trial_files_into_production(tmp_path):
    private_parent = tmp_path / "disposable"
    private_parent.mkdir(mode=0o700)
    trial_root = private_parent / "voice"
    with tempfile.TemporaryDirectory(prefix="myai-voice-", dir=private_parent) as name:
        root = Path(name)
        assert root.is_relative_to(private_parent)
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": name,
            "TMPDIR": name,
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }
        code = (
            "from pathlib import Path; import os,tempfile; "
            "p=Path(tempfile.gettempdir())/'synthetic-test-not-user.wav'; "
            "p.write_bytes(b'SYNTHETIC_PCM_NO_REAL_MICROPHONE'); "
            "os._exit(17)"
        )
        child = subprocess.run(
            [sys.executable, "-I", "-B", "-c", code],
            env=env, cwd=name, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=6, check=False,
        )
        assert child.returncode == 17
        assert (root / "synthetic-test-not-user.wav").exists()
        assert list(tmp_path.glob("*.wav")) == []
    assert not root.exists()
    assert not trial_root.exists()
    assert list(tmp_path.rglob("*.wav")) == []


def test_disposable_child_error_does_not_trigger_automatic_audio_retry():
    # No actual voice provider, model, microphone or NPU is imported here.
    assert "arecord" not in globals()
    assert "faster_whisper" not in sys.modules
