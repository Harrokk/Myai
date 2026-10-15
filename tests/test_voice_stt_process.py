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
    def popen(argv, **kwargs):
        captured.update(kwargs)
        return subprocess.Popen(
            cmd(
                "import sys;"
                "sys.stdin.buffer.read();"
                f"sys.stdout.write({VALID_JSON!r})"
            ),
            **kwargs,
        )
    assert run_deadlined(cmd("pass"), b"sample", 1, popen=popen)["text"]
    assert captured["env"]["HF_HUB_OFFLINE"] == "1"
    assert captured["env"]["TRANSFORMERS_OFFLINE"] == "1"
    assert "HF_HUB_TOKEN" not in captured["env"]
    assert captured["start_new_session"] is True
    assert captured["stderr"] == subprocess.DEVNULL
    assert captured["cwd"] == "/"


def test_full_duplex_stt_pipe_handles_backpressure_with_maximum_pcm():
    """Child writes near 8 KiB stdout BEFORE reading 2 MiB stdin.

    A sequential stdin-then-stdout implementation can deadlock if the
    child first blocks writing; our selector must service both ends.
    """
    padded = VALID_JSON.encode()
    padded += b" " * (MAX_REPLY_BYTES - len(padded))
    program = (
        "import sys;"
        f"sys.stdout.buffer.write({padded!r});"
        "sys.stdout.buffer.flush();"
        "got=sys.stdin.buffer.read();"
        f"assert len(got)=={MAX_PCM_BYTES}"
    )
    result = run_deadlined(cmd(program), b"p" * MAX_PCM_BYTES, 5)
    assert result["text"] == "Hej från isolerad process"


def test_oversized_child_output_is_rejected_before_large_allocation():
    """Native model can spam stdout; consume at most 8193 bytes."""
    script = (
        "import sys,time;"
        "[sys.stdout.buffer.write(b'X'*65536) or "
        "sys.stdout.buffer.flush() for _ in range(10000)];"
        "time.sleep(60)"
    )
    start = time.monotonic()
    with pytest.raises(RuntimeError, match="Invalid isolated STT output"):
        run_deadlined(cmd(script), b"some-pcm", 4)
    assert time.monotonic() - start < 4


def test_exactly_max_response_bytes_are_not_false_oversize():
    padded = VALID_JSON.encode()
    padded += b" " * (MAX_REPLY_BYTES - len(padded))
    script = (
        "import sys;"
        "sys.stdin.buffer.read();"
        f"sys.stdout.buffer.write({padded!r})"
    )
    result = run_deadlined(cmd(script), b"fake", 4)
    assert result["text"] == "Hej från isolerad process"


def test_one_byte_over_response_limit_must_fail_closed():
    padded = VALID_JSON.encode()
    padded += b" " * (MAX_REPLY_BYTES + 1 - len(padded))
    script = (
        "import sys;"
        "sys.stdin.buffer.read();"
        f"sys.stdout.buffer.write({padded!r})"
    )
    with pytest.raises(RuntimeError, match="Invalid isolated STT output"):
        run_deadlined(cmd(script), b"fake", 4)


def test_child_never_reads_stdin_and_waits_is_killed_by_deadline():
    script = "import time;time.sleep(60)"
    start = time.monotonic()
    with pytest.raises(TimeoutError, match="deadline exceeded"):
        run_deadlined(cmd(script), b"p" * MAX_PCM_BYTES, 1)
    assert time.monotonic() - start < 7


def test_child_sends_empty_stdout_and_exits_no_false_success():
    script = "import sys;sys.stdin.buffer.read();sys.exit(0)"
    with pytest.raises(RuntimeError, match="Invalid isolated STT"):
        run_deadlined(cmd(script), b"pcm", 4)


def test_stt_bounded_io_rejects_invalid_contract_without_process():
    from core.voice_stt_bounded_io import exchange_bounded
    for invalid in (b"", b"X" * (MAX_PCM_BYTES + 1), None, "abc"):
        with pytest.raises(ValueError):
            exchange_bounded(
                None, invalid, deadline=time.monotonic() + 1,
                max_reply_bytes=MAX_REPLY_BYTES,
            )


@pytest.mark.parametrize("raw", [
    b'{"text":"hello","text":"DELETE","language":"sv","confidence":null}',
    b'{"text":"hello","language":"sv","confidence":NaN}',
    b'{"text":"hello","language":"sv","confidence":Infinity}',
    b'{"text":"hello","language":"sv","confidence":true}',
    b'{"text":"hello","language":"sv","confidence":0.4}',
    b'{"text":"hello","language":"sv","confidence":null,"token":"SECRET"}',
    b'{"text":"hello","language":"sv","confidence":null}\xff',
])
def test_one_shot_worker_rejects_ambiguous_json_without_leaks(raw):
    script = (
        "import sys;"
        "sys.stdin.buffer.read();"
        "sys.stdout.buffer.write(" + repr(raw) + ")"
    )
    with pytest.raises(RuntimeError, match="Invalid isolated STT") as err:
        run_deadlined(cmd(script), b"some synthetic PCM", 4)
    assert "SECRET" not in str(err.value)
    assert "DELETE" not in str(err.value)


def test_one_shot_child_startup_failure_is_private_and_no_audio_sent():
    calls = []
    def unavailable(argv, **kwargs):
        calls.append((argv, kwargs))
        raise FileNotFoundError(
            "SECRET_STT_FILE /home/arduino/voice-model-password"
        )

    with pytest.raises(RuntimeError, match="worker start failed") as err:
        run_deadlined(cmd("pass"), b"PRIVATE_PCM", 4, popen=unavailable)
    assert "SECRET" not in str(err.value)
    assert "PRIVATE_PCM" not in str(err.value)
    assert len(calls) == 1
    assert calls[0][1]["start_new_session"] is True
    assert calls[0][1]["stderr"] == subprocess.DEVNULL
    assert calls[0][1]["cwd"] == "/"



def test_child_forged_early_transcript_without_consuming_pcm_is_rejected():
    """A plausible answer before complete audio transfer is not a vote."""
    fake_answer = VALID_JSON.encode()
    script = (
        "import sys,time;"
        f"sys.stdout.buffer.write({fake_answer!r});"
        "sys.stdout.buffer.flush();"
        "sys.stdout.close();"
        "time.sleep(60)"
    )
    start = time.monotonic()
    with pytest.raises(RuntimeError, match="Isolated STT worker failed"):
        run_deadlined(cmd(script), b"x" * MAX_PCM_BYTES, 5)
    # The process is stopped on early EOF, not after the 5s timeout.
    assert time.monotonic() - start < 4


def test_child_closes_stdin_without_processing_audio_is_not_authorized():
    """EPIPE or early EOF must not turn a forged reply into a valid vote."""
    fake_answer = VALID_JSON.encode()
    script = (
        "import os,sys,time;"
        "os.close(0);"
        f"sys.stdout.buffer.write({fake_answer!r});"
        "sys.stdout.buffer.flush();"
        "sys.stdout.close();"
        "time.sleep(60)"
    )
    with pytest.raises(RuntimeError, match="Isolated STT worker failed"):
        run_deadlined(cmd(script), b"x" * MAX_PCM_BYTES, 3)


def test_truncated_reply_then_closed_stdout_is_never_authorized():
    script = (
        "import sys,time;"
        "sys.stdout.buffer.write(b'{\\\"text\\\":\\\"private\\\"');"
        "sys.stdout.buffer.flush();"
        "sys.stdout.close();"
        "time.sleep(60)"
    )
    with pytest.raises(RuntimeError, match="Isolated STT worker failed"):
        run_deadlined(cmd(script), b"y" * MAX_PCM_BYTES, 3)


def test_one_shot_child_resource_env_is_child_only_and_default_off():
    from core.voice_stt_child_limits import CPU_ENV, AS_ENV
    captured = {}
    def spawn(argv, **kwargs):
        captured["env"] = kwargs["env"]
        return subprocess.Popen(
            cmd(
                "import sys;"
                "sys.stdin.buffer.read();"
                f"sys.stdout.write({VALID_JSON!r})"
            ), **kwargs,
        )
    result = run_deadlined(
        cmd("pass"), b"fake", 4, popen=spawn,
        cpu_seconds=5, virtual_memory_mib=1024,
    )
    assert result["text"] == "Hej från isolerad process"
    assert captured["env"][CPU_ENV] == "5"
    assert captured["env"][AS_ENV] == "1024"
    assert "HF_HUB_TOKEN" not in captured["env"]
    assert CPU_ENV not in os.environ and AS_ENV not in os.environ
