from types import SimpleNamespace

from modules.voice import providers


class FakeRawStream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.closed = False

    def start(self):
        self.started = True

    def read(self, samples):
        return b"x" * (samples * 2), True

    def stop(self):
        self.started = False

    def close(self):
        self.closed = True


class FakeSoundDevice:
    def __init__(self):
        self.stream = None

    def RawInputStream(self, **kwargs):
        self.stream = FakeRawStream(
            **kwargs
        )
        return self.stream


def test_sounddevice_microphone_start_read_stop():
    module = FakeSoundDevice()
    mic = providers.SoundDeviceMicrophone(
        sample_rate=16000,
        channels=1,
        frame_ms=20,
        module=module,
    )

    assert mic.frame_samples == 320
    assert mic.start() is True
    result = mic.read_frame()

    assert len(result["frame"]) == 640
    assert result["overflowed"] is True
    assert mic.stop() is True
    assert module.stream.closed is True


class FakeVad:
    def __init__(self, level):
        self.level = level
        self.calls = []

    def is_speech(self, frame, rate):
        self.calls.append(
            (frame, rate)
        )
        return True


class FakeVadModule:
    def __init__(self):
        self.instance = None

    def Vad(self, level):
        self.instance = FakeVad(level)
        return self.instance


def test_webrtc_vad_provider_passes_pcm_and_rate():
    module = FakeVadModule()
    vad = providers.WebRTCVADProvider(
        aggressiveness=3,
        sample_rate=16000,
        module=module,
    )

    assert vad.is_speech(b"abc") is True
    assert module.instance.level == 3
    assert module.instance.calls == [
        (b"abc", 16000)
    ]


class FakeWhisperModel:
    def __init__(self):
        self.calls = []

    def transcribe(
        self,
        source,
        language=None,
        vad_filter=None,
    ):
        self.calls.append(
            {
                "source": source,
                "language": language,
                "vad_filter": vad_filter,
            }
        )
        return (
            [
                SimpleNamespace(
                    text=" Hej "
                ),
                SimpleNamespace(
                    text=" världen "
                ),
            ],
            SimpleNamespace(
                language="sv"
            ),
        )


def test_faster_whisper_stt_accepts_pcm_bytes():
    model = FakeWhisperModel()
    stt = providers.FasterWhisperSTT(
        model=model,
        sample_rate=16000,
        channels=1,
        sample_width=2,
    )

    result = stt.transcribe(
        b"\x00\x00" * 320
    )

    assert result["text"] == "Hej världen"
    assert result["confidence"] is None
    assert result["language"] == "sv"
    assert model.calls[0]["language"] == "sv"
    assert model.calls[0]["vad_filter"] is False


def test_faster_whisper_accepts_existing_audio_path(tmp_path):
    model = FakeWhisperModel()
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake")
    stt = providers.FasterWhisperSTT(
        model=model,
    )

    stt.transcribe(audio)

    assert model.calls[0]["source"] == audio


class FakeEngine:
    def __init__(self):
        self.properties = []
        self.spoken = []
        self.waited = False
        self.stopped = False

    def setProperty(self, key, value):
        self.properties.append(
            (key, value)
        )

    def say(self, text):
        self.spoken.append(text)

    def runAndWait(self):
        self.waited = True

    def stop(self):
        self.stopped = True


def test_pyttsx3_tts_speaks_and_stops():
    engine = FakeEngine()
    tts = providers.Pyttsx3TTS(
        rate=170,
        volume=0.8,
        voice_id="voice-1",
        engine=engine,
    )

    assert tts.speak("Hej") is True
    assert engine.spoken == ["Hej"]
    assert engine.waited is True
    assert tts.stop() is True
    assert engine.stopped is True


def test_pyttsx3_empty_text_is_ignored():
    tts = providers.Pyttsx3TTS(
        engine=FakeEngine()
    )

    assert tts.speak("   ") is False



def test_faster_whisper_can_release_loaded_model(monkeypatch):
    model = FakeWhisperModel()
    stt = providers.FasterWhisperSTT(
        model=model,
    )
    collected = []

    monkeypatch.setattr(
        providers.gc,
        "collect",
        lambda: collected.append(True),
    )

    assert stt.release_for_inference() is True
    assert stt._model is None
    assert collected == [True]
    assert stt.release_for_inference() is False


def test_pcm_wav_write_failure_removes_private_temporary_file(
        tmp_path, monkeypatch):
    """A failing WAV encoder must not strand a file before transcribe finally."""
    import pytest

    model = FakeWhisperModel()
    monkeypatch.setattr(providers.tempfile, "tempdir", str(tmp_path))

    def broken_encoder(*_args, **_kwargs):
        raise OSError("SYNTHETIC_WAV_WRITE_FAILED_PRIVATE_DATA")

    monkeypatch.setattr(providers.wave, "open", broken_encoder)
    stt = providers.FasterWhisperSTT(model=model)
    with pytest.raises(OSError, match="SYNTHETIC_WAV_WRITE_FAILED"):
        stt.transcribe(b"\x01\x02" * 80)
    assert list(tmp_path.iterdir()) == []
    assert model.calls == []


def test_pcm_wav_cleanup_failure_never_reports_completed_transcript(
        tmp_path, monkeypatch):
    """If unlink fails, source must not claim audio can be safely discarded."""
    import pytest

    path = tmp_path / "synthetic-private-audio.wav"
    path.write_bytes(b"SYNTHETIC_PCM_NOT_USER_AUDIO")
    stt = providers.FasterWhisperSTT(model=FakeWhisperModel())
    monkeypatch.setattr(stt, "_write_temp_wav", lambda _pcm: path)
    original = type(path).unlink

    def refuse_cleanup(target, *args, **kwargs):
        if target == path:
            raise PermissionError("RAW_PRIVATE_TEMP_PATH_SHOULD_NOT_ESCAPE")
        return original(target, *args, **kwargs)

    monkeypatch.setattr(type(path), "unlink", refuse_cleanup)
    with pytest.raises(RuntimeError, match="STT temporary audio cleanup failed") as exc:
        stt.transcribe(b"\x00\x00" * 20)
    assert "RAW_PRIVATE_TEMP_PATH" not in str(exc.value)
    assert "syntetiskt" not in str(exc.value)



class _FakeFloatAudio:
    def __init__(self, raw):
        self.raw = raw

    def astype(self, dtype):
        assert dtype == "float32"
        return self

    def __truediv__(self, divisor):
        assert divisor == 32768.0
        return self


def test_isolated_whisper_memory_only_pcm_never_creates_private_wav(monkeypatch):
    import sys
    from types import SimpleNamespace

    raw = b"\x01\x00" * 160
    result = _FakeFloatAudio(raw)

    def frombuffer(data, dtype):
        assert data == raw
        assert dtype == "<i2"
        return result

    monkeypatch.setitem(sys.modules, "numpy", SimpleNamespace(frombuffer=frombuffer))
    monkeypatch.setattr(
        providers.tempfile, "NamedTemporaryFile",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("private WAV on disk forbidden")
        ),
    )
    model = FakeWhisperModel()
    stt = providers.FasterWhisperSTT(model=model, pcm_memory_only=True)
    transcript = stt.transcribe(raw)
    assert transcript["text"] == "Hej världen"
    assert model.calls[0]["source"] is result
    assert model.calls[0]["language"] == "sv"


def test_memory_only_pcm_fails_closed_on_malformed_input_without_disk(monkeypatch):
    import pytest

    monkeypatch.setattr(
        providers.tempfile, "NamedTemporaryFile",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("No WAV permitted")),
    )
    model = FakeWhisperModel()
    stt = providers.FasterWhisperSTT(model=model, pcm_memory_only=True)
    for invalid in (b"", b"\x01", b"\0" * (2 * 1024 * 1024 + 2), "private-path.wav"):
        with pytest.raises(ValueError, match="Invalid private PCM"):
            stt.transcribe(invalid)
    assert not model.calls


def test_memory_only_pcm_without_numpy_does_not_fallback_to_disk(monkeypatch):
    import builtins
    import pytest

    old_import = builtins.__import__

    def no_numpy(name, *args, **kwargs):
        if name == "numpy":
            raise ImportError("SENSITIVE_PRIVATE_AUDIO")
        return old_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_numpy)
    monkeypatch.setattr(
        providers.tempfile, "NamedTemporaryFile",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("No disk")),
    )
    model = FakeWhisperModel()
    stt = providers.FasterWhisperSTT(model=model, pcm_memory_only=True)
    with pytest.raises(RuntimeError, match="Memory-only STT requires numpy") as e:
        stt.transcribe(b"\x00\x00" * 100)
    assert "SENSITIVE_PRIVATE_AUDIO" not in str(e.value)
    assert model.calls == []


def test_checked_in_isolated_worker_enforces_diskless_pcm():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] /
              "core/voice_stt_worker.py").read_text(encoding="utf-8")
    assert "FasterWhisperSTT(**config, pcm_memory_only=True)" in source
    assert 'sys.stdin.buffer.read(MAX_PCM_BYTES + 1)' in source
