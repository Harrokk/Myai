"""Tests for explicit-consent, audio-content-free microphone smoke test."""
import array
from types import SimpleNamespace

import pytest

import scripts.ventuno_microphone_smoke as mod


def test_default_does_not_run_microphone_even_when_available(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/bin/arecord")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        pytest.fail("default must never record"))
    r = mod.microphone_capture(explicit_flag=False, consent=False)
    assert r["status"] == "read-only-capture-not-authorized"
    assert r["capture_executed"] is False


def test_single_flag_is_insufficient(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/bin/arecord")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        pytest.fail("one flag must never record"))
    for flag, consent in ((True, False), (False, True)):
        r = mod.microphone_capture(explicit_flag=flag, consent=consent)
        assert r["capture_executed"] is False


def test_non_arm_is_rejected_without_attempting_recording(monkeypatch):
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/bin/arecord")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        pytest.fail("never capture on host"))
    r = mod.microphone_capture(explicit_flag=True, consent=True)
    assert r["status"] == "reject-non-ventuno-architecture"


def test_no_alsa_utility_fails_closed(monkeypatch):
    monkeypatch.setattr(mod.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(mod.shutil, "which", lambda _: None)
    r = mod.microphone_capture(explicit_flag=True, consent=True)
    assert r["status"] == "no-go-alsa-utils-arecord-not-installed"
    assert r["capture_executed"] is False


def test_only_two_seconds_raw_audio_and_aggregate_level(monkeypatch):
    monkeypatch.setattr(mod.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/arecord")
    waveform = array.array("h", [1500] * (mod.SAMPLE_RATE * mod.SECONDS))
    def fake_run(argv, **kwargs):
        assert argv[0] == "/usr/bin/arecord"
        assert "--duration=2" in argv
        assert "--rate=16000" in argv
        assert "--type=raw" in argv
        assert kwargs["timeout"] <= 6
        return SimpleNamespace(
            returncode=0, stdout=waveform.tobytes(), stderr=b""
        )
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    r = mod.microphone_capture(explicit_flag=True, consent=True)
    assert r["status"] == "microphone-signal-measured"
    assert r["bytes_received"] == 64000
    assert r["audio_saved_to_disk"] is False
    assert r["geniex_service_touched"] is False
    assert r["content_discarded"] is True
    assert "waveform" not in r
    assert "stdout" not in r


def test_silent_signal_does_not_count_as_good_mic():
    r = mod.evaluate_pcm(b"\x00" * mod.BYTES_EXPECTED)
    assert r["captured_sound_present"] is False
    assert r["status"] == "capture-completed-but-signal-too-low"


def test_short_and_overlong_audio_never_assumed_valid():
    r = mod.evaluate_pcm(b"\x01" * 128)
    assert r["status"] == "inconclusive-unexpected-raw-length"
    assert r["captured_sound_present"] is False


def test_timeout_report_cannot_leak_microphone_content(monkeypatch):
    monkeypatch.setattr(mod.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/arecord")
    def timedout(*args, **kwargs):
        raise __import__("subprocess").TimeoutExpired(
            cmd="arecord", timeout=6, output=b"private_audio_bytes"
        )
    monkeypatch.setattr(mod.subprocess, "run", timedout)
    r = mod.microphone_capture(explicit_flag=True, consent=True)
    assert r["status"] == "capture-timeout"
    assert "private_audio_bytes" not in str(r)

def test_explicit_capture_device_without_fresh_dual_flags_does_not_record(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(mod.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/arecord")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        pytest.fail("microphone must not open"))
    for enabled, consent in ((False, False), (True, False), (False, True)):
        report = mod.microphone_capture(
            explicit_flag=enabled, consent=consent,
            device="plughw:0,1", proc_pcm_path=tmp_path / "missing",
        )
        assert report["capture_executed"] is False


def test_reject_other_capture_target_even_when_recording_authorized(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(mod.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/arecord")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        pytest.fail("unapproved target must not execute"))
    report = mod.microphone_capture(
        explicit_flag=True, consent=True,
        device="plughw:0,0", proc_pcm_path=tmp_path / "missing",
    )
    assert report["status"] == "reject-unapproved-capture-target"
    assert report["capture_executed"] is False


def test_refuse_explicit_device_without_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/arecord")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        pytest.fail("no hardware capture pair"))
    report = mod.microphone_capture(
        explicit_flag=True, consent=True, device="plughw:0,1",
        proc_pcm_path=tmp_path / "missing",
    )
    assert report["status"] == "no-go-explicit-capture-device-not-present"


def test_explicit_device_invokes_only_two_seconds_when_authorized(
    monkeypatch, tmp_path
):
    pcm = tmp_path / "pcm"
    pcm.write_text("00-01: ALSA capture device : capture 1\n")
    monkeypatch.setattr(mod.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/arecord")
    samples = array.array("h", [1200] * (mod.SAMPLE_RATE * mod.SECONDS))
    invoked = []
    def fake(argv, **kwargs):
        invoked.append(argv)
        assert "--device=plughw:0,1" in argv
        assert "--duration=2" in argv
        assert "--rate=16000" in argv
        assert "--type=raw" in argv
        assert argv[-1] == "-"
        assert kwargs["timeout"] <= 6
        return SimpleNamespace(
            returncode=0, stdout=samples.tobytes(), stderr=b"",
        )
    monkeypatch.setattr(mod.subprocess, "run", fake)
    report = mod.microphone_capture(
        explicit_flag=True, consent=True, device="plughw:0,1",
        proc_pcm_path=pcm,
    )
    assert len(invoked) == 1
    assert report["status"] == "microphone-signal-measured"
    assert report["bytes_received"] == 64000
    assert report["audio_saved_to_disk"] is False
    assert report["service_changed"] is False
