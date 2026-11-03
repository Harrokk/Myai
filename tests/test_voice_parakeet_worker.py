"""One-shot worker protocol tests: no native model, hardware, or real audio."""
import hashlib
import io
import json
import sys
from types import SimpleNamespace

import pytest

import core.voice_parakeet_worker as worker
import core.voice_stt_child_limits as limits
import modules.voice.sherpa_onnx_provider as sherpa
from core.voice_parakeet_isolated import parakeet_worker_argv


def sample(tmp_path):
    root = tmp_path / "fake-model"
    root.mkdir()
    manifest = {}
    for filename in ("encoder.int8.onnx", "decoder.int8.onnx",
                     "joiner.int8.onnx", "tokens.txt"):
        payload = ("fixture-" + filename).encode()
        (root / filename).write_bytes(payload)
        manifest[filename] = hashlib.sha256(payload).hexdigest()
    return dict(
        model_name=str(root),
        trusted_model_file_hashes=manifest,
        num_threads=2, language="sv",
        sample_rate=16000, channels=1, sample_width=2,
    )


def run_worker(monkeypatch, cfg, pcm, *, constructor):
    argv = parakeet_worker_argv(cfg)
    output = io.BytesIO()
    monkeypatch.setattr(sys, "argv", argv[2:])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(pcm)))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=output))
    monkeypatch.setattr(sherpa, "SherpaOnnxParakeetSTT", constructor)
    monkeypatch.setattr(limits, "apply_child_limits", lambda: False)
    status = worker.main()
    return status, output.getvalue()


def test_actual_worker_main_uses_fixed_provider_schema_on_synthetic_pcm(
    tmp_path, monkeypatch,
):
    config = sample(tmp_path)
    seen = {}
    class NoModel:
        def __init__(self, **kwargs):
            seen.update(kwargs)
        def transcribe(self, pcm):
            assert pcm == b"\x00\x00\x01\x00"
            return {"text": "Hej världen", "language": None, "confidence": None}
    status, raw = run_worker(
        monkeypatch, config, b"\x00\x00\x01\x00", constructor=NoModel,
    )
    assert status == 0
    assert json.loads(raw) == {
        "text": "Hej världen", "language": "sv", "confidence": None,
    }
    assert seen["trusted_model_file_hashes"] == config["trusted_model_file_hashes"]
    assert seen["device"] == "cpu"
    assert seen["compute_type"] == "int8"


@pytest.mark.parametrize("answer", [
    {"text": True}, {"text": {"tool": "delete"}}, {"text": "x" * 4097},
])
def test_invalid_native_result_cannot_become_trusted_reply(
    tmp_path, monkeypatch, answer,
):
    class Fake:
        def __init__(self, **_kwargs):
            pass
        def transcribe(self, _pcm):
            return answer
    status, raw = run_worker(
        monkeypatch, sample(tmp_path), b"\x00\x00", constructor=Fake,
    )
    assert status == 2
    assert raw == b""


def test_private_native_error_is_not_emitted(tmp_path, monkeypatch):
    class NativeError:
        def __init__(self, **_kwargs):
            pass
        def transcribe(self, _pcm):
            raise RuntimeError("SECRET_SOUND_PATH_/tmp/mic.wav")
    status, raw = run_worker(
        monkeypatch, sample(tmp_path), b"\x00\x00", constructor=NativeError,
    )
    assert status == 2
    assert b"SECRET" not in raw
    assert raw == b""


@pytest.mark.parametrize("pcm", [b"", b"\x00", b"x"*(30*16000*2+1)])
def test_worker_rejects_invalid_pcm_before_inference(
    tmp_path, monkeypatch, pcm,
):
    def forbidden(**_kwargs):
        pytest.fail("native model loaded on malformed PCM")
    status, raw = run_worker(
        monkeypatch, sample(tmp_path), pcm, constructor=forbidden,
    )
    assert status == 2
    assert raw == b""


def test_worker_does_not_import_native_model_before_child_limits(
    tmp_path, monkeypatch,
):
    config = sample(tmp_path)
    limits_applied = []
    def record_limits():
        limits_applied.append(True)
        return True
    monkeypatch.setattr(limits, "apply_child_limits", record_limits)
    seen = {}
    class Fake:
        def __init__(self, **kwargs):
            assert limits_applied == [True]
            seen.update(kwargs)
        def transcribe(self, _pcm):
            return {"text": "ok"}
    monkeypatch.setattr(sherpa, "SherpaOnnxParakeetSTT", Fake)
    argv = parakeet_worker_argv(config)
    output = io.BytesIO()
    monkeypatch.setattr(sys, "argv", argv[2:])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"\x00\x00")))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=output))
    assert worker.main() == 0
    assert limits_applied == [True]
    assert seen["num_threads"] == 2


def test_worker_rejects_invalid_config_without_inference(tmp_path, monkeypatch):
    config = sample(tmp_path)
    config["language"] = "en"
    output = io.BytesIO()
    monkeypatch.setattr(sys, "argv", ["fixed-worker.py", json.dumps(config)])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"\x00\x00")))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=output))
    assert worker.main() == 2
    assert output.getvalue() == b""
