"""Side-effect-free contract tests: no real audio, runtime, or model weights."""

from types import SimpleNamespace

import pytest

np = pytest.importorskip('numpy')

from modules.voice.sherpa_onnx_provider import SherpaOnnxParakeetSTT


class FakeStream:
    def __init__(self, value=" Hej världen "):
        self.result = SimpleNamespace(text=value)
        self.accepted = None

    def accept_waveform(self, sample_rate, samples):
        self.accepted = (sample_rate, np.array(samples, copy=True))


class FakeRecognizer:
    def __init__(self, text=" Hej världen ", fail=False):
        self.stream = FakeStream(text)
        self.fail = fail
        self.decoded = False

    def create_stream(self):
        return self.stream

    def decode_stream(self, stream):
        if self.fail:
            raise ValueError("PRIVATE_RAW_AUDIO_NOT_FOR_LOGS")
        assert stream is self.stream
        self.decoded = True


def test_in_memory_swedish_pcm_with_no_files(tmp_path):
    recognizer = FakeRecognizer()
    stt = SherpaOnnxParakeetSTT(model=recognizer)
    sample = np.array([0, 16384, -16384, -32768], dtype="<i2")
    result = stt.transcribe(sample.tobytes())
    assert result == {"text": "Hej världen", "confidence": None, "language": None}
    assert recognizer.decoded
    rate, waveform = recognizer.stream.accepted
    assert rate == 16000 and waveform.dtype == np.float32
    np.testing.assert_allclose(waveform, [0, 0.5, -0.5, -1.0])
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("bad", [b"", b"\x00", b"\x00" * (30 * 16000 * 2 + 1), "audio", None])
def test_invalid_audio_never_reaches_model(bad):
    recognizer = FakeRecognizer()
    stt = SherpaOnnxParakeetSTT(model=recognizer)
    with pytest.raises((ValueError, TypeError)):
        stt.transcribe(bad)
    assert not recognizer.decoded


@pytest.mark.parametrize("kwargs", [
    {"language": "en"}, {"device": "cuda"}, {"compute_type": "float16"},
    {"sample_rate": 48000}, {"channels": 2}, {"sample_width": 4},
    {"num_threads": 0}, {"num_threads": 5}, {"num_threads": True},
])
def test_unsupported_runtime_settings_refused(kwargs):
    with pytest.raises(ValueError):
        SherpaOnnxParakeetSTT(**kwargs)


def test_absent_model_fails_before_import_or_download(tmp_path):
    stt = SherpaOnnxParakeetSTT(model_name=str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="directory is not available"):
        stt.transcribe(b"\x00\x00" * 32)


def test_local_model_paths_and_trusted_api_contract(tmp_path):
    for name in SherpaOnnxParakeetSTT.MODEL_FILES:
        (tmp_path / name).write_bytes(b"synthetic-model")
    recognizer = FakeRecognizer()
    captured = []
    class Factory:
        @staticmethod
        def from_transducer(**kwargs):
            captured.append(kwargs)
            return recognizer
    module = SimpleNamespace(OfflineRecognizer=Factory)
    stt = SherpaOnnxParakeetSTT(model_name=str(tmp_path), module=module)
    stt.transcribe(b"\x00\x00" * 32)
    assert captured[0]["model_type"] == "nemo_transducer"
    assert captured[0]["provider"] == "cpu"
    assert captured[0]["num_threads"] == 2
    assert captured[0]["encoder"] == str(tmp_path / "encoder.int8.onnx")
    stt.transcribe(b"\x00\x00" * 32)
    assert len(captured) == 1
    assert stt.release_for_inference() is True
    assert stt.release_for_inference() is False


def test_symlink_model_file_rejected(tmp_path):
    for name in SherpaOnnxParakeetSTT.MODEL_FILES:
        (tmp_path / name).write_bytes(b"synthetic-model")
    linked = tmp_path / "tokens.txt"
    linked.unlink()
    linked.symlink_to(tmp_path / "encoder.int8.onnx")
    stt = SherpaOnnxParakeetSTT(model_name=str(tmp_path))
    with pytest.raises(RuntimeError, match="missing or incomplete"):
        stt.transcribe(b"\x00\x00" * 32)


def test_private_native_error_is_redacted():
    stt = SherpaOnnxParakeetSTT(model=FakeRecognizer(fail=True))
    with pytest.raises(RuntimeError, match="recognition failed") as e:
        stt.transcribe(b"\x00\x00" * 32)
    assert "PRIVATE_RAW_AUDIO" not in str(e.value)


def test_does_not_load_on_construct():
    stt = SherpaOnnxParakeetSTT(model_name="/model/not-yet-present")
    assert stt._model is None
    assert stt.release_for_inference() is False


def test_factory_provider_is_registered_but_default_voice_is_off():
    from core.voice_factory import DEFAULT_CLASSES, build_voice_components

    assert DEFAULT_CLASSES["stt"]["sherpa_onnx_parakeet"] is SherpaOnnxParakeetSTT
    components = build_voice_components(settings={"voice": {"enabled": False}})
    assert components["enabled"] is False
    assert components["primary_stt"] is None


def test_factory_constructs_opted_in_parakeet_without_model_or_audio():
    from core.voice_factory import build_voice_components

    class NoSideEffects:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    providers = {
        "microphone": {"sounddevice": NoSideEffects},
        "vad": {"webrtcvad": NoSideEffects},
        "stt": {
            "faster_whisper": NoSideEffects,
            "sherpa_onnx_parakeet": SherpaOnnxParakeetSTT,
        },
        "tts": {"pyttsx3": NoSideEffects},
    }
    voice = {
        "enabled": True, "tts_enabled": False,
        "stt_provider": "sherpa_onnx_parakeet",
        "backup_stt_provider": "faster_whisper",
        "backup_stt_models": [],
        "stt_model": "/offline/approved/parakeet-int8",
        "stt_device": "cpu", "stt_compute_type": "int8",
        "stt_language": "sv",
    }
    result = build_voice_components(
        settings={"voice": voice}, provider_classes=providers,
    )
    assert result["enabled"] is True
    assert isinstance(result["primary_stt"], SherpaOnnxParakeetSTT)
    assert result["primary_stt"]._model is None
    assert result["backup_stt"] == []
    assert result["tts"] is None


def test_existing_isolated_worker_rejects_unreviewed_sherpa_process_use():
    from core.voice_factory import build_voice_components
    from modules.voice.providers import FasterWhisperSTT

    class NoHardware:
        def __init__(self, **kwargs):
            pass

    mocks = {
        "microphone": {"sounddevice": NoHardware},
        "vad": {"webrtcvad": NoHardware},
        "stt": {
            "sherpa_onnx_parakeet": SherpaOnnxParakeetSTT,
            "faster_whisper": FasterWhisperSTT,
        },
        "tts": {"pyttsx3": NoHardware},
    }
    cfg = {
        "voice": {
            "enabled": True,
            "stt_provider": "sherpa_onnx_parakeet",
            "stt_process_isolation_enabled": True,
        }
    }
    with pytest.raises(ValueError, match="built-in FasterWhisper only"):
        build_voice_components(settings=cfg, provider_classes=mocks)
