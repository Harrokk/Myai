"""Source-only candidate subprocess tests; use disposable Python child only.

Fake ARM64 ELF headers and fake model bytes are never executed. Each child is
a shell-free, no-network Python -I fixture created by the hosted runner.
"""
import hashlib
import json
import subprocess
import sys
import threading
import time

import pytest

import core.voice_candidate_native as native
from core.voice_candidate_native import IsolatedPinnedNativeCandidateSTT
from core.voice_candidate_preflight import verify_candidate_profile


_NAMES = {
    "canary-1b-v2-q8": ("canary-1b-v2-Q8_0.gguf", "transcribe-cli"),
    "whisper-large-v3-turbo": ("ggml-large-v3-turbo.bin", "whisper-cli"),
}


def fixture(tmp_path, profile_name="canary-1b-v2-q8"):
    model_filename, exe_filename = _NAMES[profile_name]
    model_root = tmp_path / "model"
    exe_root = tmp_path / "runtime"
    model_root.mkdir()
    exe_root.mkdir()
    model_bytes = b"tiny-synthetic-not-real-model"
    header = bytearray(64)
    header[:7] = b"\x7fELF\x02\x01\x01"
    header[16:18] = (3).to_bytes(2, "little")
    header[18:20] = (183).to_bytes(2, "little")
    model_file = model_root / model_filename
    native_file = exe_root / exe_filename
    model_file.write_bytes(model_bytes)
    native_file.write_bytes(bytes(header))
    model_file.chmod(0o444)
    native_file.chmod(0o555)
    model_root.chmod(0o555)
    exe_root.chmod(0o555)
    msha = hashlib.sha256(model_bytes).hexdigest()
    esha = hashlib.sha256(bytes(header)).hexdigest()
    profile = verify_candidate_profile(
        profile_name, model_root=model_root, model_sha256=msha,
        runtime_root=exe_root, runtime_sha256=esha,
    )
    return profile, msha, esha


def stt(tmp_path, profile_name="canary-1b-v2-q8", timeout=3):
    profile, msha, esha = fixture(tmp_path, profile_name)
    return IsolatedPinnedNativeCandidateSTT(
        profile=profile, model_sha256=msha, runtime_sha256=esha,
        timeout_seconds=timeout,
    )


def fixture_launch(monkeypatch, script):
    seen = []
    def launch(argv, **kwargs):
        assert argv[1] == "-I"
        assert argv[2].endswith("/core/voice_candidate_worker.py")
        assert kwargs["start_new_session"] is True
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["stderr"] is subprocess.DEVNULL
        assert kwargs["cwd"] == "/"
        assert len(kwargs["pass_fds"]) == 1
        fd = kwargs["pass_fds"][0]
        assert argv[-1] == str(fd)
        assert "LD_PRELOAD" not in kwargs["env"]
        seen.append((argv, kwargs))
        return subprocess.Popen(
            [sys.executable, "-I", "-c", script, str(fd)],
            **kwargs,
        )
    monkeypatch.setattr(native, "_launch_native_candidate_worker", launch)
    return seen


def test_canary_fake_child_receives_only_inherited_sealed_wav(tmp_path, monkeypatch):
    engine = stt(tmp_path)
    seen = fixture_launch(monkeypatch,
        "import os,sys;"
        "fd=int(sys.argv[1]);"
        "h=os.pread(fd,44,0);"
        "assert h[:4]==b'RIFF' and h[8:12]==b'WAVE';"
        "sys.stdout.write('run: ok\\ntext: Hej världen\\n')"
    )
    result = engine.transcribe(b"\x00\x00" * 32)
    assert result == {"text": "Hej världen", "language": "sv", "confidence": None}
    assert len(seen) == 1
    assert engine.release_for_inference() is False


def test_whisper_fake_native_json_is_strictly_parsed(tmp_path, monkeypatch):
    engine = stt(tmp_path, "whisper-large-v3-turbo")
    fixture_launch(monkeypatch,
        "import json,sys;"
        "sys.stdout.write(json.dumps({"
        "'params':{'language':'sv','translate':False},"
        "'result':{'language':'swedish'},"
        "'transcription':[{'text':' Hej'},{'text':' världen'}]"
        "}))"
    )
    assert engine.transcribe(b"\x00\x00" * 16)["text"] == "Hej världen"


def test_nonzero_exit_never_counts_as_vote_even_with_plausible_text(tmp_path, monkeypatch):
    engine = stt(tmp_path)
    fixture_launch(monkeypatch,
        "import sys;sys.stdout.write('run: ok\\ntext: Radera fil\\n');"
        "sys.exit(4)"
    )
    with pytest.raises(RuntimeError, match="failed"):
        engine.transcribe(b"\x00\x00")


def test_unrecognized_stdout_cannot_become_stt_result(tmp_path, monkeypatch):
    engine = stt(tmp_path)
    fixture_launch(monkeypatch,
        "import sys;sys.stdout.write('native failure\\ntext: radera\\n')"
    )
    with pytest.raises(RuntimeError, match="output invalid"):
        engine.transcribe(b"\x00\x00")


def test_oversized_stdout_stops_child_process(tmp_path, monkeypatch):
    engine = stt(tmp_path)
    fixture_launch(monkeypatch,
        "import sys;sys.stdout.write('x'*60000);sys.stdout.flush()"
    )
    with pytest.raises(RuntimeError, match="stdout exceeded"):
        engine.transcribe(b"\x00\x00")


def test_hung_child_has_real_hard_deadline(tmp_path, monkeypatch):
    engine = stt(tmp_path, timeout=1)
    fixture_launch(monkeypatch, "import time;time.sleep(60)")
    start = time.monotonic()
    with pytest.raises(TimeoutError, match="deadline"):
        engine.transcribe(b"\x00\x00")
    assert time.monotonic() - start < 7


def test_user_stop_interrupts_hung_child_and_blocks_stale_result(tmp_path, monkeypatch):
    engine = stt(tmp_path, timeout=20)
    fixture_launch(monkeypatch, "import time;time.sleep(60)")
    signal = threading.Timer(0.25, engine.request_cancel)
    signal.start()
    start = time.monotonic()
    try:
        with pytest.raises(RuntimeError, match="cancelled|stopped"):
            engine.transcribe(b"\x00\x00")
    finally:
        signal.join(timeout=3)
    assert time.monotonic() - start < 7
    with pytest.raises(RuntimeError, match="stopped"):
        engine.transcribe(b"\x00\x00")
    engine.resume()


def test_model_changed_between_preflight_and_request_blocks_spawn(tmp_path, monkeypatch):
    engine = stt(tmp_path)
    model_file = tmp_path / "model" / "canary-1b-v2-Q8_0.gguf"
    model_file.chmod(0o644)
    monkeypatch.setattr(
        native, "_launch_native_candidate_worker",
        lambda *_a, **_k: pytest.fail("tampered model launched"),
    )
    with pytest.raises(RuntimeError, match="identity changed"):
        engine.transcribe(b"\x00\x00")


@pytest.mark.parametrize("invalid", [
    b"", b"\x00", "PCM", None, bytearray(b"\x00\x00"),
])
def test_invalid_pcm_never_creates_child(tmp_path, monkeypatch, invalid):
    engine = stt(tmp_path)
    monkeypatch.setattr(
        native, "_launch_native_candidate_worker",
        lambda *_a, **_kw: pytest.fail("invalid PCM spawned child"),
    )
    with pytest.raises(ValueError, match="PCM"):
        engine.transcribe(invalid)


def test_cannot_resume_while_child_active(tmp_path, monkeypatch):
    engine = stt(tmp_path)
    def launch(argv, **kwargs):
        with pytest.raises(RuntimeError, match="cleanup incomplete"):
            engine.resume()
        with pytest.raises(RuntimeError, match="cleanup incomplete"):
            engine.release_for_inference()
        # A fake child exits immediately; no real native executable.
        return subprocess.Popen(
            [sys.executable, "-I", "-c",
             "print('run: ok');print('text: Hej')"], **kwargs,
        )
    monkeypatch.setattr(native, "_launch_native_candidate_worker", launch)
    assert engine.transcribe(b"\x00\x00")["text"] == "Hej"


def test_different_model_digest_cannot_be_reused(tmp_path):
    profile, msha, esha = fixture(tmp_path)
    with pytest.raises(ValueError):
        IsolatedPinnedNativeCandidateSTT(
            profile=profile, model_sha256="0" * 64, runtime_sha256=esha,
        )
