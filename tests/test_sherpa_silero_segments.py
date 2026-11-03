"""Pure synthetic Silero segmentation tests: no microphone or real ONNX model."""
from types import SimpleNamespace

import pytest

np = pytest.importorskip('numpy')

from modules.voice.sherpa_silero_segments import SherpaSileroSegments


class FakeVad:
    def __init__(self):
        self.chunks = []
        self.segments = []
        self.flushed = False
        self.reset_called = False
        self.fail = False

    def accept_waveform(self, data):
        if self.fail:
            raise RuntimeError("PRIVATE_POSSIBLE_AUDIO_DETAILS")
        self.chunks.append(np.array(data, copy=True))

    def empty(self):
        return len(self.segments) == 0

    @property
    def front(self):
        return SimpleNamespace(samples=self.segments[0])

    def pop(self):
        self.segments.pop(0)

    def flush(self):
        self.flushed = True

    def reset(self):
        self.reset_called = True

    def is_speech_detected(self):
        return bool(self.segments)


def test_frames_buffer_until_exact_512_samples():
    fake = FakeVad()
    s = SherpaSileroSegments(vad=fake)
    frame = np.array([16384] * 320, dtype="<i2").tobytes()
    assert s.feed(frame) == []
    assert len(fake.chunks) == 0
    assert s.feed(frame) == []
    assert len(fake.chunks) == 1
    assert fake.chunks[0].dtype == np.float32
    assert len(fake.chunks[0]) == 512
    np.testing.assert_allclose(fake.chunks[0], 0.5)
    assert len(s._pending) == 256


def test_flush_zero_pads_only_pending_tail_and_prevents_more_feed():
    fake = FakeVad()
    s = SherpaSileroSegments(vad=fake)
    s.feed(bytes(640))
    assert s.flush() == []
    assert len(fake.chunks) == 1
    assert len(fake.chunks[0]) == 512
    assert np.all(fake.chunks[0] == 0)
    assert fake.flushed
    assert s.flush() == []
    with pytest.raises(RuntimeError, match="finalized"):
        s.feed(bytes(640))
    s.reset()
    assert fake.reset_called
    assert s.feed(bytes(640)) == []


def test_speech_segment_copied_and_returned_as_pcm16():
    fake = FakeVad()
    fake.segments.append(np.array([0.0, 0.5, -0.5, -1.0], dtype=np.float32))
    s = SherpaSileroSegments(vad=fake, context_padding_ms=0)
    received = s.feed(bytes(640))
    assert received == [np.array([0, 16384, -16384, -32768], dtype="<i2").tobytes()]
    assert fake.empty()


@pytest.mark.parametrize("bad", [b"", b"a", bytes(638), bytes(642), "audio", None])
def test_wrong_audio_never_passed_to_detector(bad):
    fake = FakeVad()
    s = SherpaSileroSegments(vad=fake)
    with pytest.raises((TypeError, ValueError)):
        s.feed(bad)
    assert fake.chunks == []


def test_missing_model_fails_without_native_import(tmp_path):
    s = SherpaSileroSegments(str(tmp_path / "not-present.onnx"))
    with pytest.raises(RuntimeError, match="not available"):
        s.feed(bytes(640))


def test_model_config_matches_real_sherpa_python_api(tmp_path):
    model = tmp_path / "silero_vad.onnx"
    model.write_bytes(b"synthetic-model-data")
    detected = FakeVad()
    record = []

    class FakeConfig:
        def __init__(self):
            self.silero_vad = SimpleNamespace()

    class FakeApi:
        VadModelConfig = FakeConfig
        @staticmethod
        def VoiceActivityDetector(config, *, buffer_size_in_seconds):
            record.append((config, buffer_size_in_seconds))
            return detected

    vad = SherpaSileroSegments(str(model), module=FakeApi)
    assert vad._vad is None
    assert vad.feed(bytes(640)) == []
    assert len(record) == 1
    config, seconds = record[0]
    assert config.sample_rate == 16000 and config.provider == "cpu"
    assert config.silero_vad.window_size == 512
    assert config.silero_vad.model == str(model)
    assert config.silero_vad.min_speech_duration == 0.25
    assert config.silero_vad.min_silence_duration == 0.5
    assert seconds == 30


def test_native_error_does_not_disclose_private_pcm():
    fake = FakeVad()
    fake.fail = True
    detector = SherpaSileroSegments(vad=fake)
    detector.feed(bytes(640))
    with pytest.raises(RuntimeError, match="processing failed") as err:
        detector.feed(bytes(640))
    assert "PRIVATE" not in str(err.value)


def test_input_budget_rejects_too_many_frames():
    fake = FakeVad()
    detector = SherpaSileroSegments(vad=fake)
    detector._total_bytes = 30 * 16000 * 2
    with pytest.raises(ValueError, match="maximum session length"):
        detector.feed(bytes(640))


def test_invalid_model_config_thread_count():
    with pytest.raises(ValueError):
        SherpaSileroSegments(num_threads=0)
    with pytest.raises(ValueError):
        SherpaSileroSegments(num_threads=True)


@pytest.mark.parametrize("bad", [
    np.array([np.nan], dtype=np.float32),
    np.zeros(12 * 16000 + 1, dtype=np.float32),
])
def test_invalid_native_speech_segments_fail_closed(bad):
    fake = FakeVad()
    fake.segments.append(bad)
    detector = SherpaSileroSegments(vad=fake)
    with pytest.raises(ValueError):
        detector.feed(bytes(640))


def test_no_model_loaded_for_empty_finalization():
    detector = SherpaSileroSegments("/missing/optional/model.onnx")
    assert detector.flush() == []
    assert detector._vad is None


def test_default_context_padding_safely_surrounds_stt_segment():
    fake = FakeVad()
    fake.segments.append(np.array([0.5, -0.5], dtype=np.float32))
    detector = SherpaSileroSegments(vad=fake)
    segments = detector.feed(bytes(640))
    assert len(segments) == 1
    context = bytes(300 * 16 * 2)
    assert segments[0] == (
        context + np.array([16384, -16384], dtype="<i2").tobytes() + context
    )


@pytest.mark.parametrize("bad", [-1, 501, 0.5, True, "300"])
def test_invalid_context_padding_is_rejected(bad):
    with pytest.raises(ValueError, match="context padding"):
        SherpaSileroSegments(context_padding_ms=bad)
