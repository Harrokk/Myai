"""Pure synthetic fixtures for the read-only VENTUNO sound metadata gate."""
from pathlib import Path
import json
import subprocess

import pytest

from integrations.arduino_app_lab.asr_v2_official_pilot import preflight_readonly as p


def make_proc(root: Path, *, capture_lines=(), usb_cards=()):
    root.mkdir(parents=True, exist_ok=True)
    (root / "pcm").write_text("\n".join(capture_lines) + "\n", encoding="ascii")
    for card in usb_cards:
        folder = root / f"card{card}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "usbid").write_text("1532:0c01\n", encoding="ascii")
    return root


def service_state(name):
    assert name in p.SERVICE_NAMES
    return True


def test_exactly_one_usb_capture_is_readonly_and_bounded(tmp_path):
    root = make_proc(
        tmp_path, usb_cards=(1,), capture_lines=(
            "00-00: Internal Audio : playback 1 : capture 1",
            "01-00: USB Headset : playback 1 : capture 1",
            "02-00: HDMI Output : playback 1",
        ),
    )
    assert p.usb_capture_devices(root) == ((1, 0),)
    result = p.inspect(root, service_state)
    assert result["status"] == "metadata-only-completed"
    assert result["usb_capture_category"] == "exactly-one-usb-capture-device"
    assert result["usb_capture_count"] == 1
    assert result["myai_geniex_services"] == "both-active"
    for field in (
        "microphone_opened", "recording_performed", "model_loaded",
        "services_modified", "authorizes_recording",
        "authorizes_service_stop",
    ):
        assert result[field] is False
    assert "1532" not in json.dumps(result)
    assert "USB Headset" not in json.dumps(result)


def test_multiple_usb_capture_devices_fail_closed(tmp_path):
    root = make_proc(
        tmp_path, usb_cards=(1, 2), capture_lines=(
            "01-00: Mic A : capture 1",
            "02-00: Mic B : capture 1",
            "02-01: Output only : playback 1",
        ),
    )
    result = p.inspect(root, service_state)
    assert result["usb_capture_category"] == "multiple-usb-capture-devices"
    assert result["usb_capture_count"] == 2
    assert result["authorizes_recording"] is False


@pytest.mark.parametrize("content", [
    "01-00: USB headset : playback 1",
    "01-00: USB headset : capture 0",
    "99-00: invalid card : capture 1",
    "01-99: invalid device : capture 1",
])
def test_no_valid_usb_capture_marker_is_not_ready(tmp_path, content):
    root = make_proc(tmp_path, usb_cards=(1,), capture_lines=(content,))
    assert p.usb_capture_devices(root) == ()
    assert p.inspect(root, service_state)["authorizes_recording"] is False


def test_unknown_vendor_or_missing_usbid_not_counted(tmp_path):
    root = make_proc(
        tmp_path, capture_lines=("01-00: USB: capture 1",)
    )
    assert p.usb_capture_devices(root) == ()
    (root / "card1").mkdir()
    (root / "card1" / "usbid").write_text("INVALID-ID\n")
    assert p.usb_capture_devices(root) == ()


def test_missing_proc_data_and_symlink_are_not_followed(tmp_path):
    assert p.usb_capture_devices(tmp_path) == ()
    other = tmp_path / "outside"
    other.write_text("01-00: USB: capture 1\n")
    root = tmp_path / "asound"
    root.mkdir()
    (root / "pcm").symlink_to(other)
    assert p.usb_capture_devices(root) == ()


def test_unverified_services_not_misrepresented(tmp_path):
    root = make_proc(tmp_path)
    report = p.inspect(root, lambda name: None)
    assert report["myai_geniex_services"] == "unverified"
    assert report["authorizes_service_stop"] is False
    report = p.inspect(root, lambda name: name == "myai-ventuno.service")
    assert report["myai_geniex_services"] == "mixed-state"
    report = p.inspect(root, lambda name: False)
    assert report["myai_geniex_services"] == "both-inactive"


def test_systemctl_query_is_read_only_and_allowlisted(monkeypatch):
    observed = []
    def fake_run(argv, **kwargs):
        observed.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(p.subprocess, "run", fake_run)
    assert p._read_only_service_active("myai-ventuno.service") is True
    assert observed[0][0] == [
        "systemctl", "is-active", "--quiet", "myai-ventuno.service"
    ]
    assert p._read_only_service_active("unsupported.service") is None
    assert len(observed) == 1


def test_status_cannot_expose_private_device_path(tmp_path):
    root = make_proc(tmp_path, usb_cards=(1,), capture_lines=(
        "01-00: Private Mic Name and Serial ABCD1234 : capture 1",
    ))
    r = json.dumps(p.inspect(root, service_state))
    assert "ABCD1234" not in r
    assert "/dev/snd" not in r
    assert "myai-ventuno.service" not in r
