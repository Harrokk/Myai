"""Disposable child-only tests: no microphone, Whisper model or NPU."""
import json
import os
import subprocess
import sys
import time

import pytest

from core.voice_stt_persistent import (
    PersistentFasterWhisperSTT, bounded_utterances, exchange,
    offline_environment, parse_reply, persistent_argv, terminate_owned,
)
from core.voice_stt_process import MAX_PCM_BYTES

CONFIG = {
    "model_name": "tiny", "device": "cpu", "compute_type": "int8",
    "language": "sv", "sample_rate": 16000, "channels": 1,
    "sample_width": 2,
}
REPLY = json.dumps({"text": "syntetiskt svar", "language": "sv",
                    "confidence": None}, separators=(",", ":")).encode()


def script(mode="reply"):
    # Synthetic isolated child with real POSIX framed pipe I/O, never
    # imports whisper. Only this pytest fixture can set _argv to -c.
    source = """
import json,os,struct,sys,time
i=sys.stdin.buffer
o=sys.stdout.buffer
last_nonce=None
while True:
    hdr=i.read(4)
    if not hdr: break
    n=struct.unpack('>I',hdr)[0]
    nonce=i.read(16)
    if len(nonce)!=16: break
    if MODE=='early_reply':
        # Reply is syntactically valid but input has NOT been consumed.
        payload=json.dumps({'text':'forged','language':'sv','confidence':None}).encode()
        o.write(struct.pack('>I',len(payload)+16)+nonce+payload);o.flush()
        os.close(0);os.close(1);time.sleep(60)
    data=i.read(n)
    if len(data)!=n: break
    if MODE=='sleep':
        time.sleep(60)
    elif MODE=='invalid':
        o.write(struct.pack('>I',999999));o.flush()
    elif MODE=='truncated_header':
        o.write(b'\\x00\\x00');o.flush();sys.exit(0)
    elif MODE=='truncated_body':
        o.write(struct.pack('>I',20)+b'{"text":');o.flush();sys.exit(0)
    elif MODE=='double_reply':
        payload=json.dumps({'text':'syntetiskt svar','language':'sv','confidence':None}).encode()
        frame=struct.pack('>I',len(payload)+16)+nonce+payload
        # Two replies in a single flush: the second would be wrongly
        # accepted as the transcript for a later unrelated utterance.
        o.write(frame+frame);o.flush()
    elif MODE=='die':
        sys.exit(3)
    else:
        assert len(data)>0
        payload=json.dumps({'text':'syntetiskt svar','language':'sv','confidence':None}).encode()
        if MODE=='wrong_nonce':
            echoed=b'X'*16
        elif MODE=='stale_nonce' and last_nonce is not None:
            echoed=last_nonce
        else:
            echoed=nonce
        o.write(struct.pack('>I',len(payload)+16)+echoed+payload);o.flush()
        last_nonce=nonce
""".replace("MODE", repr(mode))
    return [sys.executable, "-I", "-u", "-c", source]


def provider(mode="reply", cap=4, deadline=2):
    worker = PersistentFasterWhisperSTT(
        **CONFIG, timeout_seconds=deadline, max_utterances=cap,
    )
    worker._argv = script(mode)
    return worker


def test_multiple_requests_reuse_single_worker_pid():
    model = provider(cap=3)
    try:
        assert model.transcribe(b"pcm-1")["text"] == "syntetiskt svar"
        first_pid = model._worker.pid
        assert model.transcribe(b"pcm-2")["text"] == "syntetiskt svar"
        assert model._worker.pid == first_pid
        assert model._count == 2
        assert model.transcribe(b"pcm-3")["text"] == "syntetiskt svar"
        assert model._worker is None
        assert model._count == 0
        # Fourth request spawns fresh child, not the old cached model.
        assert model.transcribe(b"pcm-4")["text"] == "syntetiskt svar"
        assert model._worker is not None
    finally:
        model.close()
    assert model._worker is None


def test_actual_hung_process_terminated_then_next_request_can_recover():
    model = provider(mode="sleep", deadline=1)
    start = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="deadline exceeded"):
            model.transcribe(b"test-audio")
        assert time.monotonic() - start < 9
        assert model._worker is None
        model._argv = script("reply")
        assert model.transcribe(b"second-audio")["text"] == "syntetiskt svar"
    finally:
        model.close()


@pytest.mark.parametrize("bad_mode", ["invalid", "die"])
def test_broken_worker_never_reused_after_failed_reply(bad_mode):
    model = provider(mode=bad_mode)
    try:
        with pytest.raises(RuntimeError):
            model.transcribe(b"private-pcm")
        assert model._worker is None
        model._argv = script("reply")
        assert model.transcribe(b"next-good-pcm")["text"] == "syntetiskt svar"
    finally:
        model.close()


def test_release_for_inference_frees_cached_model_and_is_idempotent():
    model = provider()
    assert model.release_for_inference() is False
    try:
        assert model.transcribe(b"synthetic")["language"] == "sv"
        assert model._worker is not None
        assert model.release_for_inference() is True
        assert model._worker is None
        assert model.release_for_inference() is False
    finally:
        model.close()


@pytest.mark.parametrize("bad", [
    True, False, "4", None, 0, 9, 2.0, -1,
])
def test_max_request_cap_rejects_invalid_types_and_values(bad):
    with pytest.raises(ValueError):
        bounded_utterances(bad)


def test_default_optin_off_is_not_model_execution():
    from core.config import DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS["voice"]["stt_persistent_worker_enabled"] is False
    assert DEFAULT_SETTINGS["voice"]["stt_process_isolation_enabled"] is False


@pytest.mark.parametrize("malformed", [
    b"", b"null", b"[]", b"true", b"not json",
    b'{"text":"x","language":"sv","confidence":0.1}',
    b'{"text":true,"language":"sv","confidence":null}',
    b'{"text":"x","language":"sv","confidence":null,"raw_audio":"SECRET"}',
    b'{"text":"x","language":"nl","confidence":null}',
    b'{"text":"x","language":"sv","confidence":NaN}',
    b'{"text":"safe","text":"unsafe","language":"sv","confidence":null}',
])
def test_untrusted_child_reply_never_authorizes_vote(malformed):
    with pytest.raises(RuntimeError):
        parse_reply(malformed)


def test_invalid_audio_rejected_before_worker_process_start(monkeypatch):
    model = provider()
    monkeypatch.setattr(model, "_spawn", lambda: pytest.fail("unexpected worker"))
    with pytest.raises(ValueError):
        model.transcribe(b"")
    with pytest.raises(ValueError):
        model.transcribe(b"x" * (MAX_PCM_BYTES + 1))
    assert model._worker is None


def test_argv_fixed_path_no_shell_or_untrusted_params():
    args = persistent_argv(CONFIG)
    assert args[:2] == [sys.executable, "-I"]
    assert args[2].endswith("core/voice_stt_persistent_worker.py")
    assert args[3].startswith("{")
    assert "/bin/sh" not in args
    with pytest.raises(ValueError):
        persistent_argv(dict(CONFIG, model_name="../private"))


def test_child_environment_does_not_inherit_access_tokens(monkeypatch):
    monkeypatch.setenv("HF_HUB_TOKEN", "PRIVATE_DO_NOT_COPY")
    monkeypatch.setenv("HTTP_PROXY", "http://private.example/")
    env = offline_environment()
    assert env["HF_HUB_OFFLINE"] == "1"
    assert env["TRANSFORMERS_OFFLINE"] == "1"
    assert "HTTP_PROXY" not in env
    assert "HF_HUB_TOKEN" not in env
    assert "PRIVATE" not in json.dumps(env)



def test_failed_reap_keeps_child_handle_and_blocks_duplicate_model(monkeypatch):
    """Incomplete kill/reap cannot authorize spawning a second child."""
    import core.voice_stt_persistent as module
    model = provider(cap=1)
    real_terminate = module.terminate_owned
    try:
        def interrupted_reap(proc):
            assert proc is model._worker
            raise RuntimeError("SECRET_CHILD_PID_OR_CACHE_PATH")
        monkeypatch.setattr(module, "terminate_owned", interrupted_reap)
        with pytest.raises(RuntimeError, match="cleanup incomplete") as err:
            model.transcribe(b"first-synthetic-frame")
        assert "SECRET" not in str(err.value)
        original = model._worker
        assert original is not None
        assert model._cleanup_required is True

        monkeypatch.setattr(
            model, "_spawn",
            lambda: pytest.fail("A second native model must not be loaded"),
        )
        with pytest.raises(RuntimeError, match="cleanup pending"):
            model.transcribe(b"another-synthetic-frame")
        assert model._worker is original

        monkeypatch.setattr(module, "terminate_owned", real_terminate)
        assert model.close() is True
        assert model._worker is None
        assert model._cleanup_required is False
    finally:
        monkeypatch.setattr(module, "terminate_owned", real_terminate)
        model.close()


def test_failed_reap_after_invalid_result_still_blocks_new_child(monkeypatch):
    import core.voice_stt_persistent as module
    model = provider(mode="invalid")
    original_cleanup = module.terminate_owned
    def broken_cleanup(proc):
        raise OSError("SECRET_NATIVE_CLEANUP_FAILURE")
    try:
        monkeypatch.setattr(module, "terminate_owned", broken_cleanup)
        with pytest.raises(RuntimeError, match="cleanup incomplete") as error:
            model.transcribe(b"synthetic-private-audio")
        assert "SECRET" not in str(error.value)
        assert model._worker is not None
        assert model._cleanup_required is True
        model._argv = script("reply")
        with pytest.raises(RuntimeError, match="cleanup pending"):
            model.transcribe(b"valid-second-audio")

        monkeypatch.setattr(module, "terminate_owned", original_cleanup)
        assert model.release_for_inference() is True
        assert model._worker is None
        assert model._cleanup_required is False
        assert model.transcribe(b"third-audio")["text"] == "syntetiskt svar"
    finally:
        monkeypatch.setattr(module, "terminate_owned", original_cleanup)
        model.close()


def test_ipc_nonblocking_setup_failure_reaps_child_and_never_reuses(monkeypatch):
    import core.voice_stt_persistent as module
    model = provider()
    real_set_blocking = module.os.set_blocking
    call_count = []
    try:
        def fail_setup(fd, flag):
            call_count.append(fd)
            if len(call_count) == 2:
                raise OSError("PRIVATE_FILE_DESCRIPTOR")
            return real_set_blocking(fd, flag)
        monkeypatch.setattr(module.os, "set_blocking", fail_setup)
        with pytest.raises(RuntimeError, match="IPC setup failed") as err:
            model.transcribe(b"fake")
        assert "PRIVATE_FILE_DESCRIPTOR" not in str(err.value)
        assert len(call_count) == 2
        assert model._worker is None
        assert model._count == 0
        assert model._cleanup_required is False
    finally:
        monkeypatch.setattr(module.os, "set_blocking", real_set_blocking)
        model.close()



def test_concurrent_close_cancels_real_stalled_child_before_long_deadline(monkeypatch):
    """A user Stop must not wait for the 45–300s STT provider timeout."""
    import threading
    model = provider(mode="sleep", deadline=30)
    spawned = threading.Event()
    original_spawn = model._spawn
    pid_holder = {}
    caught = []

    def report_spawn():
        original_spawn()
        pid_holder["child"] = model._worker
        spawned.set()

    monkeypatch.setattr(model, "_spawn", report_spawn)

    def decode():
        try:
            model.transcribe(b"PRIVATE_SYNTHETIC_PCM")
        except Exception as exc:
            caught.append(str(exc))

    t = threading.Thread(target=decode, daemon=True)
    started = time.monotonic()
    t.start()
    try:
        assert spawned.wait(timeout=3)
        # The in-flight worker will either be in IPC or just about to
        # enter it, but a late result may never be authorized.
        model.close()
        t.join(timeout=3)
        assert not t.is_alive()
        assert time.monotonic() - started < 6
        assert any("cancelled" in item for item in caught)
        assert "PRIVATE_SYNTHETIC_PCM" not in repr(caught)
        assert pid_holder["child"].poll() is not None
        assert model._worker is None
        assert model._cancel.is_set()
        with pytest.raises(RuntimeError, match="cancelled"):
            model.transcribe(b"must-not-relaunch")
        assert model._worker is None
        model.resume()
        model._argv = script("reply")
        assert model.transcribe(b"new-voice-session")["text"] == "syntetiskt svar"
    finally:
        model.close()
        t.join(timeout=3)


def test_cancel_signal_is_nonblocking_even_if_decode_owns_worker_mutex(monkeypatch):
    import threading
    model = provider()
    owns_lock = threading.Event()
    release_lock = threading.Event()

    def hold_lock():
        with model._lock:
            owns_lock.set()
            assert release_lock.wait(timeout=3)

    holder = threading.Thread(target=hold_lock, daemon=True)
    holder.start()
    try:
        assert owns_lock.wait(timeout=2)
        start = time.monotonic()
        model.request_cancel()
        assert time.monotonic() - start < 0.2
        assert model._cancel.is_set()
    finally:
        release_lock.set()
        holder.join(timeout=3)
        model.close()


def test_release_for_inference_is_not_a_permanent_user_stop():
    model = provider()
    try:
        model.transcribe(b"synthetic")
        assert model.release_for_inference() is True
        assert model._cancel.is_set() is False
        assert model.transcribe(b"second-request")["text"] == "syntetiskt svar"
    finally:
        model.close()


def test_cancelled_persistent_stt_can_be_resumed_without_worker_leak():
    model = provider()
    model.request_cancel()
    with pytest.raises(RuntimeError, match="cancelled"):
        model.transcribe(b"synthetic")
    assert model._worker is None
    model.resume()
    try:
        assert model.transcribe(b"valid-after-resume")["language"] == "sv"
    finally:
        model.close()


def test_persistent_stt_startup_failure_is_sanitized_and_retriable(monkeypatch):
    import core.voice_stt_persistent as module
    real_popen = module.subprocess.Popen
    model = provider()
    try:
        def blocked(*args, **kwargs):
            raise PermissionError("SECRET_WORKER_BINARY_PATH /home/arduino")
        monkeypatch.setattr(module.subprocess, "Popen", blocked)
        with pytest.raises(RuntimeError, match="worker start failed") as err:
            model.transcribe(b"synthetic")
        assert "SECRET" not in str(err.value)
        assert model._worker is None
        assert model._cleanup_required is False
        monkeypatch.setattr(module.subprocess, "Popen", real_popen)
        assert model.transcribe(b"retry-ok")["text"] == "syntetiskt svar"
    finally:
        monkeypatch.setattr(module.subprocess, "Popen", real_popen)
        model.close()


def test_persistent_duplicate_stt_json_is_never_trusted():
    import core.voice_stt_persistent as module
    from core.voice_stt_reply import decode_stt_reply
    contradictory = b'{"text":"safe","text":"delete","language":"sv","confidence":null}'
    with pytest.raises(ValueError):
        decode_stt_reply(contradictory)
    with pytest.raises(RuntimeError, match="Invalid persistent STT response"):
        module.parse_reply(contradictory)


def test_persistent_child_resource_env_is_off_by_default_and_opt_in():
    from core.voice_stt_child_limits import CPU_ENV, AS_ENV
    from core.voice_stt_persistent import offline_environment
    empty = offline_environment()
    assert CPU_ENV not in empty and AS_ENV not in empty
    limited = offline_environment(cpu_seconds=10, virtual_memory_mib=2048)
    assert limited[CPU_ENV] == "10"
    assert limited[AS_ENV] == "2048"
    assert "HF_HUB_TOKEN" not in limited
    worker = PersistentFasterWhisperSTT(
        **CONFIG, timeout_seconds=4, cpu_seconds=10,
        virtual_memory_mib=2048,
    )
    assert worker.cpu_seconds == 10
    assert worker.virtual_memory_mib == 2048
    assert worker._worker is None



def test_persistent_worker_early_reply_and_stdin_close_never_authorizes_command():
    from core.voice_stt_process import MAX_PCM_BYTES
    model = provider(mode="early_reply", deadline=5)
    started = time.monotonic()
    try:
        with pytest.raises(RuntimeError) as exc:
            model.transcribe(b"X" * MAX_PCM_BYTES)
        assert "forged" not in str(exc.value)
        assert time.monotonic() - started < 4
        assert model._worker is None
        assert model._cleanup_required is False
        # The next independent utterance can start a newly owned child.
        model._argv = script("reply")
        assert model.transcribe(b"fresh PCM")["text"] == "syntetiskt svar"
    finally:
        model.close()


@pytest.mark.parametrize("mode", ["truncated_header", "truncated_body"])
def test_persistent_worker_partial_frame_is_rejected_and_reaped(mode):
    model = provider(mode=mode)
    try:
        with pytest.raises(RuntimeError) as exc:
            model.transcribe(b"synthetic_pcm")
        assert "synthetic_pcm" not in str(exc.value)
        assert model._worker is None
        model._argv = script("reply")
        assert model.transcribe(b"retry")["text"] == "syntetiskt svar"
    finally:
        model.close()



def test_raw_native_pipe_error_is_redacted_and_child_is_reaped(monkeypatch):
    """BrokenPipeError from os.write/select cannot disclose OS internals."""
    import core.voice_stt_persistent as module
    model = provider(mode="reply")
    original_exchange = module.exchange

    def fail_on_pipe(*args, **kwargs):
        raise BrokenPipeError("SECRET_AUDIO_DEVICE /home/arduino/private")

    try:
        monkeypatch.setattr(module, "exchange", fail_on_pipe)
        with pytest.raises(RuntimeError, match="Persistent STT IPC transfer failed") as err:
            model.transcribe(b"SYNTHETIC_PCM")
        assert "SECRET" not in str(err.value)
        assert "/home/arduino" not in str(err.value)
        assert err.value.__cause__ is None
        assert model._worker is None
        assert model._cleanup_required is False
        # Verify the owned worker was not reused after failed transport.
        monkeypatch.setattr(module, "exchange", original_exchange)
        assert model.transcribe(b"fresh")["text"] == "syntetiskt svar"
    finally:
        monkeypatch.setattr(module, "exchange", original_exchange)
        model.close()


def test_persistent_stt_rejects_two_responses_for_one_audio_frame():
    model = provider(mode="double_reply")
    try:
        with pytest.raises(RuntimeError, match="unsolicited reply data"):
            model.transcribe(b"first-and-only-audio")
        assert model._worker is None
        assert model._count == 0
        assert model._cleanup_required is False
        # A genuinely NEW independent child can serve the next frame.
        model._argv = script("reply")
        assert model.transcribe(b"new-audio")["text"] == "syntetiskt svar"
    finally:
        model.close()


def test_interrupted_reap_poison_flag_prevents_reuse_of_unknown_worker(monkeypatch):
    import core.voice_stt_persistent as module
    model = provider(cap=1)
    normal_cleanup = module.terminate_owned
    try:
        def interrupt_reap(_proc):
            raise KeyboardInterrupt("PRIVATE_KERNEL_REAP_STATE")
        monkeypatch.setattr(module, "terminate_owned", interrupt_reap)
        with pytest.raises(RuntimeError, match="cleanup incomplete") as err:
            model.transcribe(b"synthetic")
        assert "PRIVATE" not in str(err.value)
        assert model._worker is not None
        assert model._cleanup_required is True
        with pytest.raises(RuntimeError, match="cleanup pending"):
            model.transcribe(b"must-not-reuse")
        with pytest.raises(RuntimeError, match="cleanup pending"):
            model.resume()
        monkeypatch.setattr(module, "terminate_owned", normal_cleanup)
        assert model.close() is True
        assert model._worker is None
        assert model._cleanup_required is False
    finally:
        monkeypatch.setattr(module, "terminate_owned", normal_cleanup)
        model.close()


def test_buffered_stt_reply_boundary_allows_normal_end_of_file():
    # After a valid reply, worker EOF is not an extra transcript.
    model = provider(mode="reply")
    try:
        assert model.transcribe(b"valid-frame")["text"] == "syntetiskt svar"
    finally:
        model.close()


def test_mismatched_nonce_rejects_even_valid_json_and_cleans_worker():
    model = provider(mode="wrong_nonce")
    try:
        with pytest.raises(RuntimeError, match="request mismatch") as error:
            model.transcribe(b"private-audio")
        assert "private-audio" not in str(error.value)
        assert model._worker is None
        assert model._cleanup_required is False
        model._argv = script("reply")
        assert model.transcribe(b"fresh-audio")["text"] == "syntetiskt svar"
    finally:
        model.close()


def test_delayed_previous_response_nonce_never_authorizes_next_utterance():
    model = provider(mode="stale_nonce")
    try:
        assert model.transcribe(b"first-utterance")["text"] == "syntetiskt svar"
        old_worker = model._worker
        assert old_worker is not None
        with pytest.raises(RuntimeError, match="request mismatch") as error:
            model.transcribe(b"private-second-utterance")
        assert "private-second-utterance" not in str(error.value)
        assert model._worker is None
        assert old_worker.poll() is not None
        model._argv = script("reply")
        assert model.transcribe(b"third-fresh-utterance")["language"] == "sv"
    finally:
        model.close()


def test_actual_checked_in_worker_echoes_nonce_without_loading_real_model(monkeypatch):
    """Exercise the checked-in worker.main protocol using fake native provider.

    This tests production framing/nonce echo, not Whisper inference or board
    resource limits. No native model is imported or executed.
    """
    import io
    import struct
    import types

    import core.voice_stt_child_limits as child_limits
    import core.voice_stt_persistent_worker as actual_worker

    frames = [(b"A" * 16, b"first-PCM"), (b"B" * 16, b"second-PCM")]
    incoming = b"".join(
        struct.pack(">I", len(pcm)) + nonce + pcm
        for nonce, pcm in frames
    )
    output = io.BytesIO()
    seen_audio = []
    fake_provider_module = types.ModuleType("modules.voice.providers")

    class FakeFasterWhisperSTT:
        def __init__(self, **settings):
            assert settings == CONFIG

        def transcribe(self, audio):
            seen_audio.append(audio)
            return {"text": "synthetic only", "language": "sv"}

    fake_provider_module.FasterWhisperSTT = FakeFasterWhisperSTT
    monkeypatch.setitem(sys.modules, "modules.voice.providers", fake_provider_module)
    monkeypatch.setattr(child_limits, "apply_child_limits", lambda: None)
    monkeypatch.setattr(sys, "argv", ["worker.py", json.dumps(CONFIG)])
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(buffer=io.BytesIO(incoming)))
    monkeypatch.setattr(sys, "stdout", types.SimpleNamespace(buffer=output))

    assert actual_worker.main() == 0
    assert seen_audio == [pcm for _, pcm in frames]
    response = output.getvalue()
    pos = 0
    for expected_nonce, _ in frames:
        assert len(response) - pos >= 4
        length = struct.unpack(">I", response[pos:pos + 4])[0]
        pos += 4
        assert 16 < length <= 16 + 8192
        framed = response[pos:pos + length]
        assert len(framed) == length
        assert framed[:16] == expected_nonce
        assert json.loads(framed[16:]) == {
            "text": "synthetic only", "language": "sv", "confidence": None,
        }
        pos += length
    assert pos == len(response)


def test_checked_in_worker_truncated_nonce_returns_no_transcript(monkeypatch):
    """A partial identifier cannot be promoted into a valid STT response."""
    import io
    import struct
    import types

    import core.voice_stt_child_limits as child_limits
    import core.voice_stt_persistent_worker as actual_worker

    fake_provider_module = types.ModuleType("modules.voice.providers")
    class FakeFasterWhisperSTT:
        def __init__(self, **settings):
            pass
        def transcribe(self, audio):
            pytest.fail("Truncated nonce must not reach transcription")
    fake_provider_module.FasterWhisperSTT = FakeFasterWhisperSTT

    output = io.BytesIO()
    monkeypatch.setitem(sys.modules, "modules.voice.providers", fake_provider_module)
    monkeypatch.setattr(child_limits, "apply_child_limits", lambda: None)
    monkeypatch.setattr(sys, "argv", ["worker.py", json.dumps(CONFIG)])
    monkeypatch.setattr(
        sys, "stdin",
        types.SimpleNamespace(buffer=io.BytesIO(struct.pack(">I", 3) + b"short")),
    )
    monkeypatch.setattr(sys, "stdout", types.SimpleNamespace(buffer=output))
    assert actual_worker.main() == 2
    assert output.getvalue() == b""
