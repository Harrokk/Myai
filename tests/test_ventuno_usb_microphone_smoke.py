"""Opt-in USB microphone capture safety; all samples are synthetic."""
import array
from types import SimpleNamespace

import pytest

from scripts import ventuno_usb_microphone_smoke as mod


def usb_inventory(*, good=True, accessible=True):
    return {
        "status": "usb-capture-and-playback-pcm-detected" if good
                  else "no-usb-audio-card-detected",
        "usb_audio_cards": [1] if good else [],
        "usb_capture_pairs": [[1, 0]] if good else [],
        "capture_device_nodes": [
            {"pair": [1, 0], "character_device": True, "accessible": accessible}
        ],
    }


def setup_allowed(monkeypatch, *, inventory=None):
    monkeypatch.setattr(mod.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/arecord")
    monkeypatch.setattr(mod, "inventory_usb_audio",
                        lambda: usb_inventory() if inventory is None else inventory)


@pytest.mark.parametrize("record,consent", [(False, False), (True, False), (False, True)])
def test_one_or_zero_flags_cannot_open_usb_microphone(monkeypatch, record, consent):
    setup_allowed(monkeypatch)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        pytest.fail("USB microphone must remain closed"))
    report = mod.usb_microphone_capture(record_2s=record, consent=consent)
    assert report["status"] == "not-authorized"
    assert report["capture_executed"] is False


def test_non_arm64_fails_closed(monkeypatch):
    setup_allowed(monkeypatch)
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        pytest.fail("no physical capture on development host"))
    assert mod.usb_microphone_capture(record_2s=True, consent=True)["status"] == "reject-non-arm64"


@pytest.mark.parametrize("inventory", [usb_inventory(good=False), usb_inventory(accessible=False)])
def test_usb_card_changed_or_unavailable_prevents_capture(monkeypatch, inventory):
    setup_allowed(monkeypatch, inventory=inventory)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        pytest.fail("capture must not open unavailable USB device"))
    status = mod.usb_microphone_capture(record_2s=True, consent=True)["status"]
    assert status.startswith("reject-usb-")


def test_other_device_is_never_allowed(monkeypatch):
    setup_allowed(monkeypatch)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        pytest.fail("must not open other ALSA device"))
    status = mod.usb_microphone_capture(
        record_2s=True, consent=True, device="plughw:0,1")["status"]
    assert status == "reject-unapproved-target"


def test_authorized_usb_two_second_capture_reports_only_aggregate(monkeypatch):
    setup_allowed(monkeypatch)
    audio = array.array("h", [1800] * mod.BYTES_EXPECTED.__floordiv__(2)).tobytes()
    def fake_run(argv, **kw):
        assert argv == [
            "/usr/bin/arecord", "--quiet", "--device=plughw:1,0",
            "--format=S16_LE", "--rate=16000", "--channels=1",
            "--duration=2", "--file-type=raw", "-",
        ]
        assert kw["timeout"] <= 6
        assert kw["stdout"] == mod.subprocess.PIPE
        return SimpleNamespace(returncode=0, stdout=audio, stderr=b"")
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    report = mod.usb_microphone_capture(record_2s=True, consent=True)
    assert report["status"] == "microphone-signal-measured"
    assert report["bytes_received"] == 64000
    assert report["captured_sound_present"] is True
    assert report["audio_saved_to_disk"] is False
    assert report["audio_transmitted"] is False
    assert report["speech_transcribed"] is False
    assert "stdout" not in report


def test_raw_alsa_error_is_not_logged(monkeypatch):
    setup_allowed(monkeypatch)
    monkeypatch.setattr(
        mod.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=1, stdout=b"", stderr=b"Device or resource busy private-speech"
        ),
    )
    report = mod.usb_microphone_capture(record_2s=True, consent=True)
    assert report["status"] == "alsa-capture-nonzero"
    assert report["alsa_error_category"] == "device-busy"
    assert "private-speech" not in str(report)
    assert "stderr" not in report


def test_silence_is_not_reported_as_working_microphone(monkeypatch):
    setup_allowed(monkeypatch)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        SimpleNamespace(returncode=0,
                                        stdout=b"\0" * 64000, stderr=b""))
    report = mod.usb_microphone_capture(record_2s=True, consent=True)
    assert report["status"] == "capture-completed-but-signal-too-low"
    assert report["captured_sound_present"] is False


def test_timeout_is_sanitized(monkeypatch):
    setup_allowed(monkeypatch)
    def timed_out(*args, **kwargs):
        raise mod.subprocess.TimeoutExpired("arecord", 6, output=b"private-speech")
    monkeypatch.setattr(mod.subprocess, "run", timed_out)
    report = mod.usb_microphone_capture(record_2s=True, consent=True)
    assert report["status"] == "capture-timeout"
    assert "private-speech" not in str(report)
