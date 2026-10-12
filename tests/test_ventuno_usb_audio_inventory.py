"""Regression tests for USB audio metadata-only discovery."""
import json

import pytest

from scripts import ventuno_usb_audio_inventory as mod


def _sample_tree(tmp_path, *, usb=True, usb_id=True):
    proc = tmp_path / "proc" / "asound"
    snd = tmp_path / "dev" / "snd"
    proc.mkdir(parents=True)
    snd.mkdir(parents=True)
    line = "USB-Audio - USB Audio Adapter" if usb else "HDA-Intel - Internal Audio"
    (proc / "cards").write_text(
        " 0 [BuiltIn       ]: SOC-Audio - Integrated\n"
        f" 1 [USB           ]: {line}\n"
        "     no serials or labels should be reported\n",
        encoding="utf-8",
    )
    (proc / "pcm").write_text(
        "00-01: codec : internal mic : capture 1\n"
        "01-00: USB Audio : external device : playback 1 : capture 1\n"
        "01-01: USB playback : external speakers : playback 1\n",
        encoding="utf-8",
    )
    if usb_id:
        card = proc / "card1"
        card.mkdir()
        (card / "usbid").write_text("1234:5678\n")
    return proc, snd


def test_usb_duplex_and_external_speaker_are_detected_without_opening(tmp_path):
    proc, snd = _sample_tree(tmp_path)
    report = mod.inventory_usb_audio(proc, snd)
    assert report["status"] == "usb-capture-and-playback-pcm-detected"
    assert report["usb_audio_cards"] == [1]
    assert report["usb_capture_pairs"] == [[1, 0]]
    assert report["usb_playback_pairs"] == [[1, 0], [1, 1]]
    assert report["usb_duplex_cards"] == [1]
    assert report["microphone_recorded"] is False
    assert report["speaker_playback_started"] is False
    assert report["services_modified"] is False
    assert "1234:5678" not in json.dumps(report)
    assert "external speakers" not in json.dumps(report)


def test_card_detected_from_usb_audio_card_descriptor_when_usbid_missing(tmp_path):
    proc, snd = _sample_tree(tmp_path, usb_id=False)
    assert mod.inventory_usb_audio(proc, snd)["usb_capture_pairs"] == [[1, 0]]


def test_card_detected_from_usbid_when_descriptor_nonstandard(tmp_path):
    proc, snd = _sample_tree(tmp_path, usb=False, usb_id=True)
    assert mod.inventory_usb_audio(proc, snd)["usb_audio_cards"] == [1]


def test_internal_only_returns_no_usb(tmp_path):
    proc, snd = _sample_tree(tmp_path, usb=False, usb_id=False)
    result = mod.inventory_usb_audio(proc, snd)
    assert result["status"] == "no-usb-audio-card-detected"
    assert result["usb_capture_pairs"] == []


@pytest.mark.parametrize("missing", ["cards", "pcm"])
def test_incomplete_proc_metadata_fails_closed(tmp_path, missing):
    proc, snd = _sample_tree(tmp_path)
    (proc / missing).unlink()
    assert mod.inventory_usb_audio(proc, snd)["status"] == "inconclusive-alsa-metadata"


def test_usb_playback_only_does_not_claim_capture(tmp_path):
    proc, snd = _sample_tree(tmp_path)
    (proc / "pcm").write_text("01-00: speakers : playback 1\n")
    result = mod.inventory_usb_audio(proc, snd)
    assert result["status"] == "usb-playback-only-pcm-detected"
    assert result["usb_capture_pairs"] == []


def test_untrusted_metadata_does_not_expand_result(tmp_path):
    proc, snd = _sample_tree(tmp_path)
    (proc / "pcm").write_text(
        "01-00: private USB label : capture 1\n" * 8000
    )
    assert mod.inventory_usb_audio(proc, snd)["status"] == "inconclusive-alsa-metadata"


def test_usb_audio_inventory_never_launches_audio_command(monkeypatch, tmp_path):
    proc, snd = _sample_tree(tmp_path)
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("No audio subprocess allowed"))
    assert mod.inventory_usb_audio(proc, snd)["usb_audio_cards"] == [1]
