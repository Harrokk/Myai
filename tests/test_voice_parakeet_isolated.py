"""Source-only contracts for pinned one-shot Parakeet process isolation.

Uses synthetic tiny weight files and fake worker, never real audio/Parakeet.
"""
import hashlib
import json
import threading

import pytest

from core.voice_parakeet_isolated import (
    IsolatedPinnedParakeetSTT, parakeet_worker_argv,
    validate_parakeet_config,
)


def fixture_config(tmp_path):
    root = tmp_path / "stt"
    root.mkdir()
    manifest = {}
    for name in ("encoder.int8.onnx", "decoder.int8.onnx",
                 "joiner.int8.onnx", "tokens.txt"):
        raw = ("fake-model:" + name).encode("ascii")
        path = root / name
        path.write_bytes(raw)
        path.chmod(0o444)
        manifest[name] = hashlib.sha256(raw).hexdigest()
    root.chmod(0o555)
    return {"model_name": str(root), "trusted_model_file_hashes": manifest,
            "num_threads": 2, "language": "sv", "sample_rate": 16000,
            "channels": 1, "sample_width": 2}


def test_construct_is_offline_and_never_loads_model(tmp_path, monkeypatch):
    import core.voice_parakeet_isolated as module
    monkeypatch.setattr(
        module, "run_deadlined",
        lambda *_a, **_kw: pytest.fail("worker started at construction"),
    )
    config = fixture_config(tmp_path)
    isolated = IsolatedPinnedParakeetSTT(
        model_name=config["model_name"],
        trusted_model_file_hashes=config["trusted_model_file_hashes"],
    )
    assert isolated.model_name == config["model_name"]
    assert isolated.prepare_verified_model().is_current()
    assert isolated.release_for_inference() is False


def test_argv_is_fixed_worker_and_not_arbitrary_executable(tmp_path):
    config = fixture_config(tmp_path)
    argv = parakeet_worker_argv(config)
    assert len(argv) == 4
    assert argv[1] == "-I"
    assert argv[2].endswith("/core/voice_parakeet_worker.py")
    assert json.loads(argv[3]) == config
    assert "bash" not in argv and "-c" not in argv


def test_synthetic_decode_uses_bounded_child_and_returns_result(tmp_path, monkeypatch):
    import core.voice_parakeet_isolated as module
    config = fixture_config(tmp_path)
    observed = {}
    def fake_run(argv, audio, timeout, **kwargs):
        observed.update({"argv": argv, "audio": audio,
                         "timeout": timeout, **kwargs})
        return {"text": "Hej från Parakeet", "language": "sv", "confidence": None}
    monkeypatch.setattr(module, "run_deadlined", fake_run)
    isolated = IsolatedPinnedParakeetSTT(
        model_name=config["model_name"],
        trusted_model_file_hashes=config["trusted_model_file_hashes"],
        timeout_seconds=17, cpu_seconds=20, virtual_memory_mib=2048,
    )
    isolated.prepare_verified_model()
    assert isolated.transcribe(b"\x00\x00"*16)["text"] == "Hej från Parakeet"
    assert observed["timeout"] == 17.0
    assert observed["cpu_seconds"] == 20
    assert observed["virtual_memory_mib"] == 2048
    assert observed["audio"] == b"\x00\x00" * 16
    assert observed["cancel_event"].is_set() is False


def test_cancel_before_decode_refuses_worker(tmp_path, monkeypatch):
    import core.voice_parakeet_isolated as module
    config = fixture_config(tmp_path)
    monkeypatch.setattr(
        module, "run_deadlined",
        lambda *_a, **_kw: pytest.fail("worker launched after Stop"),
    )
    isolated = IsolatedPinnedParakeetSTT(
        model_name=config["model_name"],
        trusted_model_file_hashes=config["trusted_model_file_hashes"],
    )
    isolated.request_cancel()
    with pytest.raises(RuntimeError, match="stopped"):
        isolated.transcribe(b"\x00\x00")
    isolated.resume()


def test_cancel_during_decode_cannot_authorize_finished_reply(tmp_path, monkeypatch):
    import core.voice_parakeet_isolated as module
    config = fixture_config(tmp_path)
    isolated = IsolatedPinnedParakeetSTT(
        model_name=config["model_name"],
        trusted_model_file_hashes=config["trusted_model_file_hashes"],
    )
    def fake_run(*_args, **_kwargs):
        isolated.request_cancel()
        return {"text": "Anslut", "language": "sv", "confidence": None}
    isolated.prepare_verified_model()
    monkeypatch.setattr(module, "run_deadlined", fake_run)
    with pytest.raises(RuntimeError, match="invalidated"):
        isolated.transcribe(b"\x00\x00")


def test_mutated_model_file_cannot_spawn_worker(tmp_path, monkeypatch):
    import core.voice_parakeet_isolated as module
    config = fixture_config(tmp_path)
    isolated = IsolatedPinnedParakeetSTT(
        model_name=config["model_name"],
        trusted_model_file_hashes=config["trusted_model_file_hashes"],
    )
    isolated.prepare_verified_model()
    file = tmp_path / "stt" / "tokens.txt"
    file.chmod(0o644)
    file.write_bytes(b"replaced")
    file.chmod(0o444)
    monkeypatch.setattr(
        module, "run_deadlined",
        lambda *_args, **_kwargs: pytest.fail("untrusted model launched"),
    )
    with pytest.raises(RuntimeError, match="preflight required"):
        isolated.transcribe(b"\x00\x00")


def test_busy_worker_cannot_resume_or_start_parallel_decode(tmp_path, monkeypatch):
    import core.voice_parakeet_isolated as module
    config = fixture_config(tmp_path)
    isolated = IsolatedPinnedParakeetSTT(
        model_name=config["model_name"],
        trusted_model_file_hashes=config["trusted_model_file_hashes"],
    )
    isolated.prepare_verified_model()
    def fake_run(*_args, **_kwargs):
        with pytest.raises(RuntimeError, match="already running"):
            isolated.transcribe(b"\x00\x00")
        with pytest.raises(RuntimeError, match="cleanup incomplete"):
            isolated.resume()
        with pytest.raises(RuntimeError, match="cleanup incomplete"):
            isolated.release_for_inference()
        return {"text": "ignore", "language": "sv", "confidence": None}
    monkeypatch.setattr(module, "run_deadlined", fake_run)
    with pytest.raises(RuntimeError, match="invalidated"):
        isolated.transcribe(b"\x00\x00")
    isolated.resume()


@pytest.mark.parametrize("malformed", [
    {"model_name": "relative/path"},
    {"model_name": "/tmp/no\x00"},
    {"language": "en"},
    {"num_threads": 0},
    {"num_threads": True},
    {"sample_rate": 48000},
    {"channels": 2},
    {"sample_width": 4},
    {"trusted_model_file_hashes": {"encoder.int8.onnx": "a" * 64}},
])
def test_strict_config_rejects_untrusted_settings(tmp_path, malformed):
    config = dict(fixture_config(tmp_path), **malformed)
    with pytest.raises(ValueError):
        validate_parakeet_config(config)


@pytest.mark.parametrize("audio", [
    b"", b"\x00", "audio", None, b"\x00"*(30*16000*2+1),
])
def test_invalid_pcm_does_not_hash_or_spawn(tmp_path, monkeypatch, audio):
    import core.voice_parakeet_isolated as module
    config = fixture_config(tmp_path)
    isolated = IsolatedPinnedParakeetSTT(
        model_name=config["model_name"],
        trusted_model_file_hashes=config["trusted_model_file_hashes"],
    )
    monkeypatch.setattr(
        module, "run_deadlined",
        lambda *_args, **_kwargs: pytest.fail("invalid audio launched"),
    )
    with pytest.raises(ValueError, match="PCM"):
        isolated.transcribe(audio)


def test_unprepared_model_cannot_start_native_child(tmp_path, monkeypatch):
    import core.voice_parakeet_isolated as module
    config = fixture_config(tmp_path)
    isolated = IsolatedPinnedParakeetSTT(
        model_name=config["model_name"],
        trusted_model_file_hashes=config["trusted_model_file_hashes"],
    )
    monkeypatch.setattr(
        module, "run_deadlined",
        lambda *_args, **_kwargs: pytest.fail("preflight skipped"),
    )
    with pytest.raises(RuntimeError, match="preflight required"):
        isolated.transcribe(b"\x00\x00")


def test_stale_preflight_cannot_silently_repin_model(tmp_path):
    config = fixture_config(tmp_path)
    isolated = IsolatedPinnedParakeetSTT(
        model_name=config["model_name"],
        trusted_model_file_hashes=config["trusted_model_file_hashes"],
    )
    isolated.prepare_verified_model()
    path = tmp_path / "stt" / "tokens.txt"
    path.chmod(0o644)
    path.write_bytes(b"tampered")
    path.chmod(0o444)
    with pytest.raises(RuntimeError, match="invalidated"):
        isolated.prepare_verified_model()
