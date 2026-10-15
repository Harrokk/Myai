"""Pure + disposable subprocess STT hard deadline tests (NO speech model)."""
import json
import math
import os
import subprocess
import sys
import time

import pytest

from core.voice_stt_process import (
    IsolatedFasterWhisperSTT, bounded_seconds, worker_argv,
    run_deadlined, MAX_PCM_BYTES, MAX_REPLY_BYTES,
)

CONFIG = dict(
    model_name="tiny", device="cpu", compute_type="int8",
    language="sv", sample_rate=16000, channels=1, sample_width=2,
)
VALID_JSON = json.dumps({
    "text": "Hej från isolerad process",
    "language": "sv", "confidence": None,
})


def cmd(source):
    return [sys.executable, "-I", "-c", source]


@pytest.mark.parametrize("bad", [
    False, True, None, 0, 0.1, -10, 301, "45", float("nan"),
    float("inf"), float("-inf"), 10 ** 400,
])
def test_timeout_is_strict_numeric_bounded(bad):
    with pytest.raises(ValueError):
        bounded_seconds(bad)


def test_timeboxed_worker_child_reads_stdin_and_returns_strict_json():
    script = (
        "import sys;"
        "received=sys.stdin.buffer.read();"
        "assert received==b'synthetic-pcm';"
        f"sys.stdout.write({VALID_JSON!r})"
    )
    result = run_deadlined(cmd(script), b"synthetic-pcm", 4)
    assert result["text"] == "Hej från isolerad process"
    assert result["confidence"] is None


def test_real_hung_child_is_killed_within_hard_deadline():
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="deadline exceeded"):
        run_deadlined(cmd("import time;time.sleep(60)"), b"abc", 1)
    assert time.monotonic() - started < 8


def test_child_failure_and_private_stdout_never_leak():
    script = (
        "import sys;"
        "sys.stdout.write('SECRET_AUDIO /home/arduino/mic.wav');"
        "sys.exit(7)"
    )
    with pytest.raises(RuntimeError) as e:
        run_deadlined(cmd(script), b"personal audio", 4)
    assert "SECRET" not in str(e.value)
    assert "/home/" not in str(e.value)
    assert "personal audio" not in str(e.value)


@pytest.mark.parametrize("payload", [
    b"", b"not json", b"null", b"[]", b"true",
    b'{"text":"a","language":"sv","confidence":0.9}',
    b'{"text":"a","language":"sv","confidence":null,"extra":1}',
    b'{"text":"a","language":"nl","confidence":null}',
    b"x" * (MAX_REPLY_BYTES + 1),
])
def test_malformed_or_oversize_output_never_counts_as_stt_vote(payload):
    script = "import sys;sys.stdout.buffer.write(" + repr(payload) + ")"
    with pytest.raises(RuntimeError, match="Invalid isolated STT"):
        run_deadlined(cmd(script), b"pcm", 4)


@pytest.mark.parametrize("audio", [
    None, "audio", b"", b"x" * (MAX_PCM_BYTES + 1),
])
def test_no_process_created_for_untrusted_audio(audio):
    def refuse(*args, **kwargs):
        pytest.fail("Popen invoked on invalid audio")
    with pytest.raises(ValueError):
        run_deadlined(cmd("print('danger')"), audio, 1, popen=refuse)


@pytest.mark.parametrize("patch", [
    {"model_name": "/home/arduino/private"},
    {"model_name": "model;bash -c 'sudo'"},
    {"device": "htp"},
    {"compute_type": "secret"},
    {"language": "unknown"},
    {"channels": True},
    {"sample_rate": 48000},
    {"sample_width": 4},
])
def test_worker_launch_settings_cannot_be_arbitrary(patch):
    bad = dict(CONFIG, **patch)
    with pytest.raises(ValueError):
        worker_argv(bad)


def test_no_arbitrary_argv_or_custom_worker_in_public_wrapper():
    iso = IsolatedFasterWhisperSTT(**CONFIG, timeout_seconds=1)
    args = iso._argv
    assert args[:2] == [sys.executable, "-I"]
    assert args[2].endswith("/core/voice_stt_worker.py")
    assert args[3].startswith("{")
    assert iso.timeout_seconds == 1.0
    assert iso.release_for_inference() is False


def test_environment_is_forced_offline_and_does_not_inherit_secrets(monkeypatch):
    monkeypatch.setenv("HF_HUB_TOKEN", "SECRET_TOKEN_DO_NOT_EXPORT")
    captured = {}
    class DummyProc:
        pid = 1000000000
        returncode = 0
        def communicate(self, input=None, timeout=None):
            return VALID_JSON.encode(), b""
    def popen(argv, **kwargs):
        captured.update(kwargs)
        return DummyProc()
    assert run_deadlined(cmd("pass"), b"sample", 1, popen=popen)["text"]
    assert captured["env"]["HF_HUB_OFFLINE"] == "1"
    assert captured["env"]["TRANSFORMERS_OFFLINE"] == "1"
    assert "HF_HUB_TOKEN" not in captured["env"]
    assert captured["start_new_session"] is True
    assert captured["stderr"] == subprocess.DEVNULL
    assert captured["cwd"] == "/"
