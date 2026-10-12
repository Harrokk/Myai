"""Fail-closed USB full-duplex dialogue preflight, no physical audio."""
import json

import pytest

import scripts.ventuno_usb_voice_dialog_readiness as mod


def usb_metadata(*, card=1, access=True):
    return {
        "usb_audio_cards": [card],
        "usb_capture_pairs": [[card, 0]],
        "usb_playback_pairs": [[card, 0]],
        "capture_device_nodes": [
            {"pair": [card, 0], "character_device": True, "accessible": access}
        ],
        "playback_device_nodes": [
            {"pair": [card, 0], "character_device": True, "accessible": access}
        ],
    }


def args(**overrides):
    data = dict(machine="aarch64", mem_kib=12 * 1024 * 1024,
                free_disk_bytes=10 * 1024**3, usb=usb_metadata(),
                voice={"enabled": False, "tts_enabled": False,
                       "handsfree_enabled": False}, services_active=True)
    data.update(overrides)
    return data


def test_ready_never_claims_actual_audio_or_voice_started():
    result = mod.summarize_readiness(**args())
    assert result["status"] == "ready-for-separate-consented-dialogue-test"
    assert result["ram_required_mib"] == 8192
    assert result["disk_required_mib"] == 3072
    assert result["microphone_opened"] is False
    assert result["speaker_opened"] is False
    assert result["model_loaded"] is False
    assert result["physical_dialogue_attempted"] is False
    assert result["production_changed"] is False


@pytest.mark.parametrize("change,expected", [
    ({"machine": "x86_64"}, "blocked-architecture"),
    ({"services_active": False}, "blocked-inactive-services"),
    ({"voice": None}, "blocked-active-voice-or-invalid-config"),
    ({"voice": {"enabled": True}}, "blocked-active-voice-or-invalid-config"),
    ({"voice": {"tts_enabled": True}}, "blocked-active-voice-or-invalid-config"),
    ({"voice": {"handsfree_enabled": True}}, "blocked-active-voice-or-invalid-config"),
    ({"usb": usb_metadata(card=2)}, "blocked-usb-reenumerated-or-inaccessible"),
    ({"usb": usb_metadata(access=False)}, "blocked-usb-reenumerated-or-inaccessible"),
    ({"mem_kib": 8 * 1024 * 1024 - 1}, "blocked-whisper-8gib-memory-reserve"),
    ({"mem_kib": None}, "blocked-whisper-8gib-memory-reserve"),
    ({"free_disk_bytes": 3 * 1024**3 - 1}, "blocked-temporary-staging-disk-reserve"),
    ({"free_disk_bytes": None}, "blocked-temporary-staging-disk-reserve"),
])
def test_safety_gates_never_start_voice(change, expected):
    result = mod.summarize_readiness(**args(**change))
    assert result["status"] == expected
    assert result["microphone_opened"] is False
    assert result["speaker_opened"] is False
    assert result["model_loaded"] is False


def test_no_usb_labels_serials_or_path_values_exposed():
    metadata = usb_metadata()
    metadata["private_serial"] = "SECRET_SERIAL_NUMBER"
    result = mod.summarize_readiness(**args(usb=metadata))
    assert "SECRET_SERIAL_NUMBER" not in json.dumps(result)
    assert "stderr" not in result and "stdout" not in result


def test_production_profile_is_read_only_and_audio_never_opened(monkeypatch, tmp_path):
    profile = tmp_path / "ventuno_q.json"
    original = b'{"voice":{"enabled":false,"tts_enabled":false,"handsfree_enabled":false}}'
    profile.write_bytes(original)
    monkeypatch.setattr(mod.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(mod, "mem_available_kib", lambda: 11 * 1024 * 1024)
    monkeypatch.setattr(mod, "disk_free_bytes", lambda _: 5 * 1024**3)
    monkeypatch.setattr(mod, "inventory_usb_audio", lambda: usb_metadata())
    monkeypatch.setattr(mod, "check_services", lambda: True)
    result = mod.inspect(profile_path=profile, disk_root=tmp_path)
    assert result["status"] == "ready-for-separate-consented-dialogue-test"
    assert profile.read_bytes() == original


def test_invalid_profile_refuses_ready(monkeypatch, tmp_path):
    profile = tmp_path / "invalid.json"
    profile.write_text("null")
    monkeypatch.setattr(mod.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(mod, "mem_available_kib", lambda: 12 * 1024 * 1024)
    monkeypatch.setattr(mod, "disk_free_bytes", lambda _: 5 * 1024**3)
    monkeypatch.setattr(mod, "inventory_usb_audio", lambda: usb_metadata())
    monkeypatch.setattr(mod, "check_services", lambda: True)
    assert mod.inspect(profile_path=profile, disk_root=tmp_path)["status"] == (
        "blocked-active-voice-or-invalid-config"
    )
