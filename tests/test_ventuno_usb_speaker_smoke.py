"""No-physical-playback tests of low-level Swedish USB speaker diagnostic."""
import array
import io
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from scripts import ventuno_usb_speaker_smoke as mod


def sample_wav(*, peak=24000, length=32000, channels=1, rate=16000):
    pcm = array.array("h", [peak] * (length * channels)).tobytes()
    data = io.BytesIO()
    with wave.open(data, "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(pcm)
    return data.getvalue()


def allowed(monkeypatch, *, usb=True):
    monkeypatch.setattr(mod.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(mod, "inventory_usb_audio", lambda: {
        "usb_audio_cards": [1] if usb else [],
        "usb_playback_pairs": [[1, 0]] if usb else [],
        "playback_device_nodes": [
            {"pair": [1, 0], "character_device": True, "accessible": True}
        ] if usb else [],
    })
    monkeypatch.setattr(
        mod, "espeak_paths",
        lambda folder: (Path("/tmp/dummy-espeak"), Path("/tmp/espeak-ng-data")),
    )
    monkeypatch.setattr(mod.shutil, "which", lambda tool: "/usr/bin/" + tool)


def test_default_and_wrong_device_never_open_speaker(monkeypatch, tmp_path):
    allowed(monkeypatch)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        pytest.fail("Must not play audio"))
    assert mod.play_usb_speaker(stage_folder=tmp_path)["status"] == "not-authorized"
    assert mod.play_usb_speaker(
        authorized=True, stage_folder=tmp_path, device="plughw:0,0"
    )["status"] == "reject-unapproved-device"


def test_architecture_and_reenumeration_fail_closed(monkeypatch, tmp_path):
    allowed(monkeypatch)
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        pytest.fail("Must not play"))
    assert mod.play_usb_speaker(
        authorized=True, stage_folder=tmp_path
    )["status"] == "reject-non-arm64"
    allowed(monkeypatch, usb=False)
    assert mod.play_usb_speaker(
        authorized=True, stage_folder=tmp_path
    )["status"] == "usb-speaker-missing-or-renumbered"


def test_attenuate_loud_wav_to_strict_digital_peak():
    wav, report = mod.quiet_wav_from_tts(sample_wav(peak=30000))
    assert wav is not None
    assert report["source_wav_valid"] is True
    assert report["limited_peak_fraction"] <= mod.DIGITAL_PEAK_LIMIT
    assert report["duration_seconds"] == 2.0
    with wave.open(io.BytesIO(wav), "rb") as stream:
        assert stream.getnchannels() == 1
        assert stream.getframerate() == 16000
        samples = array.array("h")
        samples.frombytes(stream.readframes(stream.getnframes()))
    assert max(abs(v) for v in samples) <= int(32767 * mod.DIGITAL_PEAK_LIMIT)


@pytest.mark.parametrize(
    "raw",
    [
        b"random bytes",
        b"x" * (mod.MAX_WAV_BYTES + 1),
        sample_wav(peak=0),
        sample_wav(length=500),
        sample_wav(length=80000),
        sample_wav(channels=2),
    ],
)
def test_bad_audio_cannot_reach_speaker(raw):
    actual, info = mod.quiet_wav_from_tts(raw)
    assert actual is None
    assert info["source_wav_valid"] is False


def test_real_speaker_subprocess_is_called_once_after_safe_synthesis(
    monkeypatch, tmp_path,
):
    allowed(monkeypatch)
    calls = []
    def simulated_process(argv, **kwargs):
        calls.append(argv)
        if argv[0] == "/tmp/dummy-espeak":
            assert argv[-1] == mod.PHRASE
            assert "--stdout" in argv
            assert kwargs["timeout"] <= mod.TIMEOUT_SECONDS
            return SimpleNamespace(returncode=0, stdout=sample_wav(), stderr=b"")
        assert argv == [
            "/usr/bin/aplay", "--quiet", "--device=plughw:1,0",
            "--file-type=wav", "-",
        ]
        assert kwargs["timeout"] <= mod.TIMEOUT_SECONDS
        assert isinstance(kwargs["input"], bytes)
        assert len(kwargs["input"]) < mod.MAX_WAV_BYTES
        with wave.open(io.BytesIO(kwargs["input"]), "rb") as audio:
            data = array.array("h")
            data.frombytes(audio.readframes(audio.getnframes()))
        assert max(abs(v) for v in data) <= int(32767 * mod.DIGITAL_PEAK_LIMIT)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr(mod.subprocess, "run", simulated_process)
    report = mod.play_usb_speaker(authorized=True, stage_folder=tmp_path)
    assert len(calls) == 2  # one synthesis + exactly one playback
    assert report["status"] == "usb-speaker-pcm-playback-completed"
    assert report["playback_command_succeeded"] is True
    assert report["audible_sound_confirmed_by_person"] is False
    assert report["mic_recorded"] is False
    assert report["audio_file_saved"] is False
    assert report["services_modified"] is False


def test_nonzero_alsa_playback_does_not_claim_audibility(monkeypatch, tmp_path):
    allowed(monkeypatch)
    count = 0
    def fake(argv, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            return SimpleNamespace(returncode=0, stdout=sample_wav(), stderr=b"")
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"private-label")
    monkeypatch.setattr(mod.subprocess, "run", fake)
    report = mod.play_usb_speaker(authorized=True, stage_folder=tmp_path)
    assert report["status"] == "alsa-speaker-playback-nonzero"
    assert "private-label" not in str(report)
    assert report["audible_sound_confirmed_by_person"] is False


def test_playback_timeout_has_no_second_attempt(monkeypatch, tmp_path):
    allowed(monkeypatch)
    count = 0
    def fake(argv, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            return SimpleNamespace(returncode=0, stdout=sample_wav(), stderr=b"")
        raise mod.subprocess.TimeoutExpired("aplay", 9, output=b"private-audio")
    monkeypatch.setattr(mod.subprocess, "run", fake)
    report = mod.play_usb_speaker(authorized=True, stage_folder=tmp_path)
    assert count == 2
    assert report["status"] == "speaker-playback-timeout"
    assert "private-audio" not in str(report)
