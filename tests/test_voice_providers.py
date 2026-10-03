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
