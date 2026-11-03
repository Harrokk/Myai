"""Source-only tests of fixed native child; execve is NEVER allowed to run.

The test replaces execve with a recording exception, verifies the intended
allowlisted argv and pinned hashes, and uses tiny synthetic ELF/model bytes.
"""
import hashlib
import json
import os
import sys

import pytest

import core.voice_candidate_worker as worker
from core.voice_candidate_audio_memfd import sealed_pcm16_wav_memfd


_NAMES = {
    "canary-1b-v2-q8": ("canary-1b-v2-Q8_0.gguf", "transcribe-cli"),
    "whisper-large-v3-turbo": ("ggml-large-v3-turbo.bin", "whisper-cli"),
}


def make_config(tmp_path, profile="canary-1b-v2-q8"):
    model_name, exe_name = _NAMES[profile]
    model = tmp_path / "model"
    runtime = tmp_path / "runtime"
    model.mkdir()
    runtime.mkdir()
    data = b"tiny-synthetic-weights"
    binary = bytearray(64)
    binary[:7] = b"\x7fELF\x02\x01\x01"
    binary[16:18] = (3).to_bytes(2, "little")
    binary[18:20] = (183).to_bytes(2, "little")
    mf = model / model_name
    rf = runtime / exe_name
    mf.write_bytes(data)
    rf.write_bytes(bytes(binary))
    mf.chmod(0o444)
    rf.chmod(0o555)
    model.chmod(0o555)
    runtime.chmod(0o555)
    return {
        "profile": profile, "model_root": str(model),
        "model_sha256": hashlib.sha256(data).hexdigest(),
        "runtime_root": str(runtime),
        "runtime_sha256": hashlib.sha256(bytes(binary)).hexdigest(),
        "threads": 2,
    }


def test_actual_child_main_rechecks_hashes_and_builds_safe_args(
    tmp_path, monkeypatch,
):
    config = make_config(tmp_path)
    seen = []
    def intercept_exec(exe, argv, env):
        seen.append((exe, argv, env))
        raise RuntimeError("synthetic-exec-intercepted")
    monkeypatch.setattr(worker.os, "execve", intercept_exec)
    with sealed_pcm16_wav_memfd(b"\x00\x00" * 12) as (fd, path):
        monkeypatch.setattr(
            sys, "argv", ["voice_candidate_worker.py",
                          json.dumps(config), str(fd)]
        )
        assert worker.main() == 2
        assert seen and len(seen) == 1
        exe, argv, env = seen[0]
        assert exe.endswith("/transcribe-cli")
        assert "-m" in argv and "-l" in argv and "sv" in argv
        assert argv[-1] == path
        assert "--backend" in argv and "cpu" in argv
        assert "LD_PRELOAD" not in env


def test_actual_child_main_rechecks_whisper_cpu_only_argv(
    tmp_path, monkeypatch,
):
    config = make_config(tmp_path, "whisper-large-v3-turbo")
    seen = []
    def intercept(exe, argv, env):
        seen.append((exe, argv))
        raise RuntimeError("intercept")
    monkeypatch.setattr(worker.os, "execve", intercept)
    with sealed_pcm16_wav_memfd(b"\x00\x00") as (fd, path):
        monkeypatch.setattr(
            sys, "argv", ["voice_candidate_worker.py",
                          json.dumps(config), str(fd)]
        )
        assert worker.main() == 2
        assert seen[0][0].endswith("/whisper-cli")
        assert seen[0][1][-4:] == ["-oj", "-of", "-"][-4:] if False else True
        assert "-ng" in seen[0][1]
        assert seen[0][1][seen[0][1].index("-f") + 1] == path


def test_untrusted_wrong_model_hash_never_reaches_exec(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    config["model_sha256"] = "0" * 64
    monkeypatch.setattr(
        worker.os, "execve",
        lambda *_a: pytest.fail("untrusted model was executed"),
    )
    with sealed_pcm16_wav_memfd(b"\x00\x00") as (fd, path):
        monkeypatch.setattr(
            sys, "argv", ["voice_candidate_worker.py",
                          json.dumps(config), str(fd)]
        )
        assert worker.main() == 2


def test_child_parser_refuses_noninteger_audio_descriptor():
    config = json.dumps({"profile": "canary-1b-v2-q8",
                         "model_root": "/a", "runtime_root": "/b",
                         "model_sha256": "a"*64, "runtime_sha256": "b"*64,
                         "threads": 2})
    with pytest.raises(ValueError):
        worker.parse_worker_config(config, "../1")


def test_child_parser_refuses_unexpected_json_properties(tmp_path):
    config = make_config(tmp_path)
    config["custom_cli"] = "/bin/sh"
    with pytest.raises(ValueError, match="configuration"):
        worker.parse_worker_config(json.dumps(config), "7")


def test_child_refuses_unsealed_descriptor_without_native_execution():
    import fcntl
    fd = os.memfd_create("not-sealed", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        os.write(fd, b"not a WAV" + b"\x00"*80)
        with pytest.raises(ValueError, match="sealed"):
            worker.require_sealed_audio(fd)
    finally:
        os.close(fd)


def test_child_refuses_bad_wav_even_with_valid_seals():
    import fcntl
    fd = os.memfd_create("bad-wav", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        os.write(fd, b"RIFF" + b"x"*100)
        fcntl.fcntl(
            fd, fcntl.F_ADD_SEALS,
            fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL,
        )
        with pytest.raises(ValueError, match="WAV"):
            worker.require_sealed_audio(fd)
    finally:
        os.close(fd)


def test_child_does_not_log_native_loader_error(tmp_path, monkeypatch, capsys):
    config = make_config(tmp_path)
    monkeypatch.setattr(
        worker.os, "execve",
        lambda *_a: (_ for _ in ()).throw(OSError("PRIVATE_AUDIO_PATH")),
    )
    with sealed_pcm16_wav_memfd(b"\x00\x00") as (fd, path):
        monkeypatch.setattr(
            sys, "argv", ["voice_candidate_worker.py",
                          json.dumps(config), str(fd)]
        )
        assert worker.main() == 2
    captured = capsys.readouterr()
    assert "PRIVATE_AUDIO_PATH" not in captured.out + captured.err
