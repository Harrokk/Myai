import pytest

from modules.voice import microphone


class FakeController:
    def __init__(self):
        self.frames = []

    def process_frame(self, frame):
        self.frames.append(frame)
        return {
            "event": "speech",
            "completed": False,
        }


class FakeStream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


class FakeSoundDevice:
    def __init__(self):
        self.streams = []

    def RawInputStream(self, **kwargs):
        stream = FakeStream(**kwargs)
        self.streams.append(stream)
        return stream


def settings(provider="sounddevice"):
    return {
        "voice": {
            "microphone_provider": provider,
            "microphone_device": "",
            "vad_sample_rate": 16000,
            "vad_frame_ms": 20,
        }
    }


def test_microphone_uses_vad_frame_geometry():
    source = microphone.SoundDeviceMicrophone(
        FakeController(),
        sample_rate=16000,
        frame_ms=20,
        sounddevice_module=FakeSoundDevice(),
    )

    assert source.frame_samples == 320
    assert source.frame_bytes == 640


def test_invalid_frame_geometry_is_rejected():
    with pytest.raises(ValueError):
        microphone.SoundDeviceMicrophone(
            FakeController(),
            sample_rate=44100,
            frame_ms=0.5,
            sounddevice_module=FakeSoundDevice(),
        )


def test_start_creates_mono_int16_raw_stream():
    sd = FakeSoundDevice()
    controller = FakeController()
    source = microphone.SoundDeviceMicrophone(
        controller,
        sample_rate=16000,
        frame_ms=20,
        sounddevice_module=sd,
    )

    started = source.start()

    assert started is True
    stream = sd.streams[0]
    assert stream.started is True
    assert stream.kwargs["samplerate"] == 16000
    assert stream.kwargs["blocksize"] == 320
    assert stream.kwargs["channels"] == 1
    assert stream.kwargs["dtype"] == "int16"
    assert callable(stream.kwargs["callback"])


def test_audio_callback_forwards_exact_pcm_frame():
    sd = FakeSoundDevice()
    controller = FakeController()
    seen = []
    source = microphone.SoundDeviceMicrophone(
        controller,
        sample_rate=16000,
        frame_ms=20,
        sounddevice_module=sd,
        result_callback=seen.append,
    )
    source.start()
    callback = sd.streams[0].kwargs["callback"]
    audio = b"\x01\x00" * 320

    callback(audio, 320, None, None)

    assert controller.frames == [audio]
    assert source.last_error is None
    assert seen[0]["event"] == "speech"


def test_callback_records_stream_status_and_frame_error():
    sd = FakeSoundDevice()
    source = microphone.SoundDeviceMicrophone(
        FakeController(),
        sample_rate=16000,
        frame_ms=20,
        sounddevice_module=sd,
    )
    source.start()
    callback = sd.streams[0].kwargs["callback"]

    callback(
        b"\x00\x00" * 10,
        10,
        None,
        "input overflow",
    )

    assert source.last_status == "input overflow"
    assert "fel antal samples" in source.last_error


def test_stop_closes_stream():
    sd = FakeSoundDevice()
    source = microphone.SoundDeviceMicrophone(
        FakeController(),
        sounddevice_module=sd,
    )
    source.start()
    stream = sd.streams[0]

    stopped = source.stop()

    assert stopped is True
    assert stream.stopped is True
    assert stream.closed is True
    assert source.stream is None


def test_blank_microphone_provider_returns_none():
    assert microphone.build_microphone(
        FakeController(),
        settings(provider=""),
        sounddevice_module=FakeSoundDevice(),
    ) is None


def test_unknown_microphone_provider_is_rejected():
    with pytest.raises(ValueError):
        microphone.build_microphone(
            FakeController(),
            settings(provider="unknown"),
            sounddevice_module=FakeSoundDevice(),
        )


def test_build_microphone_uses_voice_settings():
    sd = FakeSoundDevice()
    config = settings()
    config["voice"]["microphone_device"] = 3

    source = microphone.build_microphone(
        FakeController(),
        config,
        sounddevice_module=sd,
    )
    source.start()

    assert sd.streams[0].kwargs["device"] == 3
