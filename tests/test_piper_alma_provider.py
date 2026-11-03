"""Mock-only Piper Alma voice and explicitly routed playback tests.

No voice weights downloaded, no sounddevice imports or real speaker opened.
"""
import io
import wave
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from modules.voice.piper_alma_provider import PiperAlmaTTS, SoundDeviceWavSink


def fake_wav(samples=b"\x01\x00" * 2205):
    data = io.BytesIO()
    with wave.open(data, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(22050)
        out.writeframes(samples)
    return data.getvalue()


class FakeVoice:
    def __init__(self):
        self.calls = []

    def synthesize_wav(self, text, writer, *, syn_config):
        self.calls.append((text, syn_config.length_scale))
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(22050)
        writer.writeframes(b"\x00\x40" * 2205)


class Sink:
    def __init__(self):
        self.audio = []
        self.cancel = False
        self.stops = 0

    def play_wav(self, audio):
        self.audio.append(audio)
        return not self.cancel

    def reset(self):
        self.cancel = False

    def stop(self):
        self.cancel = True
        self.stops += 1
        return True


class FakeModule:
    @staticmethod
    def SynthesisConfig(*, length_scale):
        return SimpleNamespace(length_scale=length_scale)


def test_renderer_has_no_eager_model_or_audio_io():
    provider = PiperAlmaTTS(
        voice_id="/model/sv_SE-alma-medium.onnx", output_device="explicit-device"
    )
    assert provider._voice is None
    assert provider._sink is not None
    assert provider.release_for_inference() is False


def test_fake_piper_synthesizes_wav_in_memory_with_tuned_rate():
    voice, sink = FakeVoice(), Sink()
    provider = PiperAlmaTTS(
        voice=voice, module=FakeModule, sink=sink, rate=150
    )
    data = provider.render_wav(" Vad heter du? ")
    with wave.open(io.BytesIO(data), "rb") as result:
        assert result.getnframes() == 2205
        assert result.getframerate() == 22050
        assert result.getnchannels() == 1
    assert voice.calls == [("Vad heter du?", 1.2)]
    assert provider.speak("Hej!") is True
    assert len(sink.audio) == 1
    assert provider.stop() is True
    assert sink.stops == 1
    assert provider.release_for_inference() is True
    assert provider._voice is None


def test_volume_scaling_keeps_same_wav_duration():
    np = pytest.importorskip("numpy")
    provider = PiperAlmaTTS(
        voice=FakeVoice(), module=FakeModule, sink=Sink(), volume=0.5
    )
    data = provider.render_wav("Hej")
    with wave.open(io.BytesIO(data), "rb") as parsed:
        samples = np.frombuffer(parsed.readframes(2205), dtype="<i2")
        assert samples[0] == 8192
        assert parsed.getnframes() == 2205


@pytest.mark.parametrize("kwargs", [
    {"rate": True}, {"rate": 109}, {"rate": 261},
    {"volume": -0.1}, {"volume": 1.1}, {"volume": float("nan")},
    {"volume": float("inf")},
])
def test_invalid_synthesis_settings_fail_closed(kwargs):
    with pytest.raises(ValueError):
        PiperAlmaTTS(**kwargs)


@pytest.mark.parametrize("bad", [
    "audio" * 100, "bad\x00text", "x" * 225, None,
])
def test_invalid_text_does_not_call_native_voice(bad):
    voice = FakeVoice()
    provider = PiperAlmaTTS(voice=voice, module=FakeModule)
    with pytest.raises(ValueError):
        provider.render_wav(bad)
    assert voice.calls == []


def test_empty_text_does_not_load_or_play():
    provider = PiperAlmaTTS(
        voice_id="/missing/sv_SE-alma-medium.onnx", sink=Sink()
    )
    assert provider.speak("  ") is False
    assert provider._voice is None


def test_no_output_device_refuses_to_speak_after_render():
    provider = PiperAlmaTTS(voice=FakeVoice(), module=FakeModule)
    with pytest.raises(RuntimeError, match="explicit audio output"):
        provider.speak("Hej")
    assert provider._voice is not None


def test_model_missing_or_symlink_fails_closed(tmp_path):
    path = tmp_path / "sv_SE-alma-medium.onnx"
    provider = PiperAlmaTTS(voice_id=str(path))
    with pytest.raises(RuntimeError, match="missing or incomplete"):
        provider.render_wav("Hej")
    path.write_bytes(b"tiny-fake-weights")
    with pytest.raises(RuntimeError, match="missing or incomplete"):
        provider.render_wav("Hej")
    link = tmp_path / "other.onnx"
    link.symlink_to(path)
    with pytest.raises(RuntimeError):
        PiperAlmaTTS(voice_id=str(link)).render_wav("Hej")


def test_synthetic_render_error_redacts_native_details():
    class Fails:
        def synthesize_wav(self, *a, **kw):
            raise RuntimeError("PRIVATE_SPEECH_AUDIO_OR_MODEL_PATH")
    provider = PiperAlmaTTS(voice=Fails(), module=FakeModule)
    with pytest.raises(RuntimeError, match="synthesis failed") as e:
        provider.render_wav("Hej")
    assert "PRIVATE" not in str(e.value)


class FakeStream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.closed = False
        self.written = bytearray()
        self.aborted = False

    def start(self):
        self.started = True

    def write(self, bytes_):
        self.written.extend(bytes_)

    def stop(self):
        self.started = False

    def close(self):
        self.closed = True

    def abort(self):
        self.aborted = True


class FakeAudio:
    def __init__(self):
        self.stream = None

    def RawOutputStream(self, **kwargs):
        self.stream = FakeStream(**kwargs)
        return self.stream


def test_explicit_pcm16_output_to_fake_device():
    audio = FakeAudio()
    sink = SoundDeviceWavSink("explicit-test-output", module=audio)
    assert sink.play_wav(fake_wav()) is True
    assert audio.stream.kwargs["device"] == "explicit-test-output"
    assert audio.stream.kwargs["samplerate"] == 22050
    assert bytes(audio.stream.written) == b"\x01\x00" * 2205
    assert audio.stream.closed is True


def test_output_rejects_wrong_pcm_format_before_opening_device():
    audio = FakeAudio()
    sink = SoundDeviceWavSink(0, module=audio)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(22050)
        writer.writeframes(b"\x00\x00" * 20)
    with pytest.raises(ValueError):
        sink.play_wav(buf.getvalue())
    assert audio.stream is None


@pytest.mark.parametrize("device", [None, -1, True, "", "x" * 121])
def test_output_requires_exact_device_selection(device):
    with pytest.raises(ValueError):
        SoundDeviceWavSink(device)


def test_output_cancel_prevents_speaker_open():
    audio = FakeAudio()
    sink = SoundDeviceWavSink("explicit", module=audio)
    sink.stop()
    assert sink.play_wav(fake_wav()) is False
    assert audio.stream is None


def test_factory_piper_enabled_requires_explicit_model_and_speaker():
    from core.voice_factory import build_voice_components
    class FakeHardware:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
    providers = {
        "microphone": {"sounddevice": FakeHardware},
        "vad": {"webrtcvad": FakeHardware},
        "stt": {"faster_whisper": FakeHardware},
        "tts": {"piper_alma": PiperAlmaTTS},
    }
    cfg = {
        "enabled": True, "tts_enabled": True, "tts_async": False,
        "tts_provider": "piper_alma",
        "stt_provider": "faster_whisper",
        "tts_voice_id": "/approved/local/sv_SE-alma-medium.onnx",
        "tts_output_device": "explicit-usb-headset",
    }
    output = build_voice_components(
        settings={"voice": cfg}, provider_classes=providers)
    assert isinstance(output["tts"], PiperAlmaTTS)
    assert output["tts"]._voice is None
    assert output["tts"]._sink.device == "explicit-usb-headset"


@pytest.mark.parametrize("patch", [
    {"tts_voice_id": ""},
    {"tts_voice_id": "relative/sv_SE-alma-medium.onnx"},
    {"tts_output_device": None}, {"tts_output_device": ""},
    {"tts_output_device": True},
])
def test_factory_rejects_unapproved_piper_tts_modes(patch):
    from core.voice_factory import build_voice_components
    class FakeHardware:
        def __init__(self, **kwargs):
            pass
    classes = {
        "microphone": {"sounddevice": FakeHardware},
        "vad": {"webrtcvad": FakeHardware},
        "stt": {"faster_whisper": FakeHardware},
        "tts": {"piper_alma": PiperAlmaTTS},
    }
    cfg = {
        "enabled": True, "tts_enabled": True, "tts_async": False,
        "tts_provider": "piper_alma",
        "tts_voice_id": "/approved/local/sv_SE-alma-medium.onnx",
        "tts_output_device": "explicit-usb",
    }
    cfg.update(patch)
    with pytest.raises(ValueError):
        build_voice_components(settings={"voice": cfg}, provider_classes=classes)


def test_disabled_voice_does_not_construct_piper():
    from core.voice_factory import build_voice_components
    output = build_voice_components(
        settings={"voice": {"enabled": False,
                            "tts_enabled": True,
                            "tts_provider": "piper_alma"}})
    assert output["enabled"] is False and output["tts"] is None


def test_stop_during_piper_render_never_plays_stale_speech():
    """A stopped old response must not open a speaker after synthesis ends."""
    class BlockedVoice(FakeVoice):
        def __init__(self):
            super().__init__()
            self.entered = threading.Event()
            self.finish = threading.Event()

        def synthesize_wav(self, text, writer, *, syn_config):
            self.entered.set()
            if not self.finish.wait(3):
                raise RuntimeError("unit-test render did not resume")
            return super().synthesize_wav(text, writer, syn_config=syn_config)

    voice, sink = BlockedVoice(), Sink()
    provider = PiperAlmaTTS(voice=voice, module=FakeModule, sink=sink)
    outcomes = []
    worker = threading.Thread(target=lambda: outcomes.append(provider.speak("Hej")))
    worker.start()
    try:
        assert voice.entered.wait(3), "synthetic voice never began rendering"
        provider.stop()
    finally:
        voice.finish.set()
        worker.join(3)
    assert not worker.is_alive()
    assert outcomes == [False]
    assert sink.audio == []
    # A genuinely new request after stop is allowed, with a fresh token.
    assert provider.speak("Nytt säkert svar") is True
    assert len(sink.audio) == 1


def test_stale_generation_refused_before_audio_sink_reset():
    """A pre-stop generation cannot resurrect its playback permission."""
    provider = PiperAlmaTTS(voice=FakeVoice(), module=FakeModule, sink=Sink())
    before = provider._generation
    provider.stop()
    assert provider._generation == before + 1
    assert provider._cancel.is_set()
    assert provider.speak("Ny separat begäran") is True
    assert provider._generation == before + 1
