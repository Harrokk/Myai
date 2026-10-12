"""Voice dependency and /dev/snd read-only inventory safety tests."""
import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ventuno_voice_readiness import (
    alsa_card_count, inspect_voice, readiness, snd_device_counts,
)


def test_alsa_header_count(tmp_path):
    path = tmp_path / "cards"
    path.write_text(
        " 0 [Headset        ]: USB-Audio - Example\n"
        "   USB headset at USB bus\n"
        " 1 [Generic        ]: HDA-Intel - Audio\n"
        "   Simplex device\n"
    )
    assert alsa_card_count(path) == 2


def test_no_alsa_file_is_unknown_not_zero(tmp_path):
    assert alsa_card_count(tmp_path / "no-cards") is None


def test_directory_absent_disables_assumptions(tmp_path):
    devices = snd_device_counts(tmp_path / "missing")
    assert devices["snd_directory_present"] is False
    assert devices["scan_complete"] is False
    assert devices["capture_device_nodes"] == 0


def test_regular_files_never_count_as_pcm_nodes(tmp_path):
    for name in ("pcmC0D0c", "pcmC0D0p", "controlC0"):
        (tmp_path / name).write_bytes(b"not a real device")
    devices = snd_device_counts(tmp_path)
    assert devices["scan_complete"] is True
    assert devices["capture_device_nodes"] == 0
    assert devices["playback_device_nodes"] == 0


def test_chr_devices_only_counted_from_exact_name_patterns(monkeypatch, tmp_path):
    class FakeEntry:
        def __init__(self, name):
            self.name = name
        def is_symlink(self):
            return False
        def stat(self, *, follow_symlinks=False):
            assert follow_symlinks is False
            return SimpleNamespace(st_mode=stat.S_IFCHR)
    class FakeScan:
        def __enter__(self):
            return iter([FakeEntry(name) for name in (
                "pcmC0D1c", "pcmC0D2p", "controlC0", "pcmC0D1c.backup"
            )])
        def __exit__(self, *args):
            return False
    monkeypatch.setattr("scripts.ventuno_voice_readiness.os.scandir",
                        lambda _: FakeScan())
    devices = snd_device_counts(tmp_path)
    assert devices["capture_device_nodes"] == 1
    assert devices["playback_device_nodes"] == 1
    assert devices["pcm_control_nodes"] == 1
    assert devices["scan_complete"] is True


def test_ready_for_smoke_never_auto_enables_voice():
    modules = {name: True for name in (
        "sounddevice", "webrtcvad", "faster_whisper", "pyttsx3"
    )}
    devices = {"scan_complete": True, "capture_device_nodes": 1,
               "playback_device_nodes": 1, "snd_directory_present": True}
    result = readiness(modules, devices, 1)
    assert result["status"] == "candidate-for-authorized-physical-audio-smoke-test"
    assert result["safe_to_enable_voice_automatically"] is False
    assert result["physical_microphone_capture_verified"] is False
    assert result["geniex_or_myai_services_changed"] is False


def test_missing_python_voice_package_reports_correctly():
    modules = {"sounddevice": True, "faster_whisper": False,
               "webrtcvad": True, "pyttsx3": False}
    devices = {"scan_complete": True, "capture_device_nodes": 1}
    assert readiness(modules, devices, 1)["status"] == (
        "audio-node-present-optional-voice-dependencies-missing"
    )


def test_no_microphone_not_same_as_capture_proven():
    result = readiness({}, {"scan_complete": True, "capture_device_nodes": 0}, 0)
    assert result["status"] == "no-capture-device-node-seen"
    assert result["physical_microphone_capture_verified"] is False


def test_voice_profile_enabled_requires_manual_review():
    result = readiness({}, {"scan_complete": False}, None,
                       voice_enabled=True, tts_enabled=True)
    assert result["status"] == "configuration-review-required-voice-requested"
    assert result["safe_to_enable_voice_automatically"] is False


def test_real_profile_remains_voice_disabled(tmp_path, monkeypatch):
    profile = tmp_path / "ventuno.json"
    profile.write_text(json.dumps({"voice": {
        "enabled": False, "tts_enabled": False,
    }}))
    monkeypatch.setattr(
        "scripts.ventuno_voice_readiness.package_spec_presence", lambda: {}
    )
    result = inspect_voice(profile, tmp_path / "no-snd", tmp_path / "no-cards")
    assert result["voice_enabled_in_profile"] is False
    assert result["tts_enabled_in_profile"] is False
    assert result["safe_to_enable_voice_automatically"] is False
