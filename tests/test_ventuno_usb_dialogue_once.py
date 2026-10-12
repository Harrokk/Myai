"""Bounded synthetic-only tests of VENTUNO single-turn USB voice dialogue."""
import array
import io
from types import SimpleNamespace
import wave

import pytest

import scripts.ventuno_usb_dialogue_once as mod


def pcm(sample=1800):
    return array.array("h", [sample] * (mod.CAPTURE_BYTES // 2)).tobytes()


def wav(sample=20000, frames=32000):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(array.array("h", [sample] * frames).tobytes())
    return stream.getvalue()


def readiness(ready=True):
    return {
        "status": ("ready-for-separate-consented-dialogue-test" if ready
                   else "blocked-whisper-8gib-memory-reserve"),
        "services_active": True,
        "production_voice_disabled": True,
        "usb_capture_and_playback_1_0_accessible": True,
        "ram_gate_passed": ready,
        "disk_gate_passed": True,
    }


def ports(*, audio=None, transcript="Vad heter du?", answer="Jag heter MyAI.",
          tts=None, ram=11 * 1024 * 1024, snapshots=None):
    events = []
    checks = iter(snapshots if snapshots is not None else [readiness()] * 2)

    def invoked(tag, value):
        events.append(tag)
        return value

    p = mod.DialogPorts(
        capture=lambda: invoked("capture", pcm() if audio is None else audio),
        transcribe_local=lambda value: invoked("transcribe", transcript),
        answer_local=lambda value: invoked("geniex", answer),
        synthesize_local=lambda value: invoked("tts", wav() if tts is None else tts),
        play_usb=lambda value: invoked("play", True),
        fresh_readiness=lambda: invoked("readiness", next(checks)),
        available_ram_kib=lambda: invoked("ram", ram),
    )
    return p, events


def test_actual_stage_order_and_no_private_data_in_report():
    p, events = ports()
    instance = mod.OneShotUsbDialog(p)
    report = instance.run(consent_to_record=True, consent_to_play=True)
    assert report["status"] == "one-shot-usb-dialogue-alsa-playback-completed"
    assert events == [
        "readiness", "capture", "transcribe", "ram",
        "geniex", "tts", "readiness", "play",
    ]
    assert report["transcription_verified"] is True
    assert report["local_geniex_answer_verified"] is True
    assert report["swedish_tts_verified"] is True
    assert report["playback_completed"] is True
    assert report["microphone_audio_saved"] is False
    assert report["microphone_audio_transmitted"] is False
    assert report["generated_wav_saved"] is False
    assert report["production_changed"] is False
    assert "Vad heter du" not in str(report)
    assert "Jag heter MyAI" not in str(report)


@pytest.mark.parametrize("record,play", [(False, False), (True, False), (False, True)])
def test_both_explicit_consents_required(record, play):
    p, events = ports()
    report = mod.OneShotUsbDialog(p).run(
        consent_to_record=record, consent_to_play=play,
    )
    assert report["status"] == "not-authorized"
    assert events == []


def test_one_time_capture_not_repeated_even_after_success():
    p, events = ports()
    instance = mod.OneShotUsbDialog(p)
    assert instance.run(consent_to_record=True, consent_to_play=True)[
        "playback_completed"] is True
    count = len(events)
    second = instance.run(consent_to_record=True, consent_to_play=True)
    assert second["status"] == "reject-second-attempt"
    assert len(events) == count


@pytest.mark.parametrize("text", [
    "Vad heter du?", "Hur mår du?", "Hej My AI!", "Vad kan du göra?",
])
def test_only_intended_short_questions_allowed(text):
    assert mod.approved_short_question(text) is not None


@pytest.mark.parametrize("text", [
    "Stäng av systemet", "radera filerna", "installera program",
    "svenska --disable-guard", "", "\nVad heter du?",
    "Vad heter du?\0", "snälla öppna dörren", "berätta allt om mitt konto",
    "Vad heter du?" * 30,
])
def test_unsafe_and_unexpected_utterances_rejected_without_geniex(text):
    p, events = ports(transcript=text)
    outcome = mod.OneShotUsbDialog(p).run(
        consent_to_record=True, consent_to_play=True,
    )
    assert outcome["status"] == "reject-unapproved-or-unclear-test-utterance"
    assert "geniex" not in events
    assert "play" not in events


@pytest.mark.parametrize("bad", [
    b"", b"\0" * mod.CAPTURE_BYTES,
    b"\0" * (mod.CAPTURE_BYTES - 2),
    b"x" * (mod.CAPTURE_BYTES + 2),
])
def test_incomplete_silent_and_oversize_audio_never_reaches_whisper(bad):
    p, events = ports(audio=bad)
    outcome = mod.OneShotUsbDialog(p).run(
        consent_to_record=True, consent_to_play=True,
    )
    assert outcome["status"] == "reject-weak-or-invalid-3s-capture"
    assert "transcribe" not in events
    assert "play" not in events


def test_usb_disconnected_or_ram_guard_prevents_capture():
    p, events = ports(snapshots=[readiness(False)])
    report = mod.OneShotUsbDialog(p).run(
        consent_to_record=True, consent_to_play=True,
    )
    assert report["status"] == "reject-unsafe-hardware-or-resource-readiness"
    assert events == ["readiness"]


def test_ram_below_whisper_gate_after_recognition_disallows_geniex():
    p, events = ports(ram=5 * 1024 * 1024)
    result = mod.OneShotUsbDialog(p).run(
        consent_to_record=True, consent_to_play=True,
    )
    assert result["status"] == "reject-ram-after-whisper"
    assert "geniex" not in events
    assert "play" not in events


def test_disconnected_speaker_before_playback_stops_audio():
    p, events = ports(snapshots=[readiness(), readiness(False)])
    result = mod.OneShotUsbDialog(p).run(
        consent_to_record=True, consent_to_play=True,
    )
    assert result["status"] == "reject-hardware-changed-before-playback"
    assert "play" not in events


@pytest.mark.parametrize("reply", [
    "En lång mening " * 15, "", "Hej\x00", None,
])
def test_bad_geniex_reply_never_sent_to_speaker(reply):
    p, events = ports(answer=reply)
    result = mod.OneShotUsbDialog(p).run(
        consent_to_record=True, consent_to_play=True,
    )
    assert result["status"] == "reject-unsafe-local-model-reply"
    assert "tts" not in events
    assert "play" not in events


def test_tts_wav_longer_than_limit_never_played():
    p, events = ports(tts=wav(frames=80000))
    result = mod.OneShotUsbDialog(p).run(
        consent_to_record=True, consent_to_play=True,
    )
    assert result["status"] == "reject-unbounded-or-invalid-tts"
    assert "play" not in events


def test_playback_receives_peak_limited_wav_only():
    p, events = ports()
    captured = []
    p.play_usb = lambda value: captured.append(value) or True
    result = mod.OneShotUsbDialog(p).run(
        consent_to_record=True, consent_to_play=True,
    )
    assert result["playback_completed"]
    assert len(captured) == 1
    with wave.open(io.BytesIO(captured[0]), "rb") as stream:
        samples = array.array("h")
        samples.frombytes(stream.readframes(stream.getnframes()))
    assert max(abs(v) for v in samples) <= int(32767 * 0.04)


def test_unexpected_io_failure_is_sanitized_and_cannot_retry():
    p, events = ports()
    def failed_capture():
        raise OSError("secret private system path and transcript")
    p.capture = failed_capture
    instance = mod.OneShotUsbDialog(p)
    first = instance.run(consent_to_record=True, consent_to_play=True)
    assert first["status"] == "one-shot-dialogue-stage-failed"
    assert "secret private" not in str(first)
    second = instance.run(consent_to_record=True, consent_to_play=True)
    assert second["status"] == "reject-second-attempt"
