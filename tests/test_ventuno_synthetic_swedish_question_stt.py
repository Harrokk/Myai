"""No microphone, no speaker: synthetic Swedish Whisper comparison."""
import array
import io
import json
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest
import scripts.ventuno_synthetic_swedish_question_stt as subject


def make_wav(*, rate=22050, frames=24000, sample=4500, channels=1):
    data = io.BytesIO()
    with wave.open(data, "wb") as sink:
        sink.setnchannels(channels)
        sink.setsampwidth(2)
        sink.setframerate(rate)
        sink.writeframes(array.array("h", [sample] * (frames * channels)).tobytes())
    return data.getvalue()


def test_pcm_is_exactly_real_microphone_format_and_private():
    wav = make_wav()
    pcm = subject.wav_to_three_second_capture(wav)
    assert isinstance(pcm, bytes)
    assert len(pcm) == subject.CAPTURE_BYTES == 96000
    assert pcm[:subject.LEADING_SAMPLES * 2] == bytes(subject.LEADING_SAMPLES * 2)
    assert pcm[-8000:] == bytes(8000)
    assert subject.classify_pcm_quality(pcm) == "bounded-audio-level"


@pytest.mark.parametrize("data", [
    b"", b"fake", make_wav(channels=2), make_wav(frames=66000),
    make_wav(frames=800), make_wav(sample=0),
    b"x" * (subject.SOURCE_MAX_BYTES + 1),
])
def test_invalid_or_unusable_audio_never_accepted(data):
    pcm = subject.wav_to_three_second_capture(data)
    if pcm is not None:
        assert subject.classify_pcm_quality(pcm) == "silence-or-too-quiet"


def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    root = tmp_path / "myai-synthetic-phrase-test"
    root.mkdir()
    (root / subject.MODEL_FOLDER).mkdir()
    py = root / subject.STT_PYTHON
    py.parent.mkdir(parents=True)
    py.write_text("mock")
    (root / subject.TTS_FOLDER).mkdir()
    monkeypatch.setattr(subject, "mem_available_kib", lambda: 12 * 1024 * 1024)
    monkeypatch.setattr(subject, "model_integrity", lambda _: {
        "model_metadata_complete": True,
    })
    monkeypatch.setattr(subject, "espeak_paths", lambda _: (
        root / "dummy-espeak", root / "dummy-voice-data",
    ))
    return root


def test_unapproved_probe_never_runs_process(monkeypatch, tmp_path):
    root = setup(monkeypatch, tmp_path)
    monkeypatch.setattr(subject.subprocess, "run",
                        lambda *a, **k: pytest.fail("no synthesis without opt-in"))
    monkeypatch.setattr(subject, "_limited_whisper_child",
                        lambda *a, **k: pytest.fail("no model without opt-in"))
    report = subject.analyze_isolated_synthetic_question(
        root, authorized=False, machine="aarch64",
    )
    assert report["status"] == "not-authorized"
    assert report["real_microphone_opened"] is False


def test_wrong_arch_and_nonisolated_path_rejected(monkeypatch, tmp_path):
    root = setup(monkeypatch, tmp_path)
    monkeypatch.setattr(subject.subprocess, "run",
                        lambda *a, **k: pytest.fail("must not run"))
    assert subject.analyze_isolated_synthetic_question(
        root, authorized=True, machine="x86_64",
    )["status"] == "blocked-architecture"
    new = tmp_path / "wrong-name"
    new.mkdir()
    assert subject.analyze_isolated_synthetic_question(
        new, authorized=True, machine="aarch64",
    )["status"] == "blocked-nonisolated-workspace"


def test_memory_fails_closed_before_speech(monkeypatch, tmp_path):
    root = setup(monkeypatch, tmp_path)
    monkeypatch.setattr(subject, "mem_available_kib", lambda: 20)
    monkeypatch.setattr(subject.subprocess, "run",
                        lambda *a, **k: pytest.fail("no TTS under RAM pressure"))
    assert subject.analyze_isolated_synthetic_question(
        root, authorized=True, machine="aarch64",
    )["status"] == "blocked-memory-reserve"


def test_both_speeds_and_no_raw_transcript_in_report(monkeypatch, tmp_path):
    root = setup(monkeypatch, tmp_path)
    speeds = []
    def tts(command, **kwargs):
        assert command[-1] == subject.PHRASE
        assert "--stdout" in command and "-v" in command
        assert kwargs["timeout"] <= 10
        speeds.append(command[command.index("-s") + 1])
        return SimpleNamespace(returncode=0, stdout=make_wav(), stderr=b"")
    monkeypatch.setattr(subject.subprocess, "run", tts)
    transcriptions = iter(["Vad heter du?", "Hav er du."])
    def model(root, python, weights, pcm):
        assert len(pcm) == 96000
        return next(transcriptions)
    monkeypatch.setattr(subject, "_limited_whisper_child", model)
    report = subject.analyze_isolated_synthetic_question(
        root, authorized=True, machine="aarch64",
    )
    assert report["status"] == "synthetic-swedish-phrase-inference-completed"
    assert report["synthetic_variants_run"] == 2
    assert speeds == ["175", "130"]
    assert report["normal_speed_question_matched"] is True
    assert report["slow_speed_question_matched"] is False
    assert "Vad heter du?" not in json.dumps(report)
    assert "Hav er du." not in json.dumps(report)
    assert all(report[key] is False for key in (
        "real_microphone_opened", "real_speaker_opened",
        "ollama_called", "geniex_called", "waveform_saved",
        "transcript_logged", "production_settings_changed",
    ))


def test_synthesis_failure_never_loads_model(monkeypatch, tmp_path):
    root = setup(monkeypatch, tmp_path)
    monkeypatch.setattr(subject.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=1, stdout=b"",
                                        stderr=b"secret-tts-error"))
    monkeypatch.setattr(subject, "_limited_whisper_child",
                        lambda *a, **k: pytest.fail("do not load"))
    report = subject.analyze_isolated_synthetic_question(
        root, authorized=True, machine="aarch64",
    )
    assert report["status"] == "synthetic-swedish-tts-failed"
    assert "secret" not in json.dumps(report)


def test_whisper_failure_only_reports_generic_error(monkeypatch, tmp_path):
    root = setup(monkeypatch, tmp_path)
    monkeypatch.setattr(subject.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=0, stdout=make_wav(),
                                        stderr=b""))
    def reject(*args):
        raise RuntimeError("secret recognized transcript from user")
    monkeypatch.setattr(subject, "_limited_whisper_child", reject)
    report = subject.analyze_isolated_synthetic_question(
        root, authorized=True, machine="aarch64",
    )
    assert report["status"] == "offline-whisper-synthetic-inference-failed"
    assert "secret" not in json.dumps(report)


def test_bad_real_reference_model_stops_before_tts(monkeypatch, tmp_path):
    root = setup(monkeypatch, tmp_path)
    monkeypatch.setattr(subject, "model_integrity", lambda _: {
        "model_metadata_complete": False,
    })
    monkeypatch.setattr(subject.subprocess, "run",
                        lambda *a, **k: pytest.fail("no synthesized audio"))
    report = subject.analyze_isolated_synthetic_question(
        root, authorized=True, machine="aarch64",
    )
    assert report["status"] == "blocked-unverified-model"
