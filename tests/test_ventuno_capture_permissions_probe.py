"""Safe ALSA device-node permissions and substream-state probe tests."""
import os
import stat
from types import SimpleNamespace

import pytest

import scripts.ventuno_capture_permissions_probe as mod


class FakeCharNode:
    def __init__(self, *, symlink=False, is_char=True):
        self.symlink = symlink
        self.is_char = is_char

    def is_symlink(self):
        return self.symlink

    def stat(self):
        return SimpleNamespace(st_mode=(
            stat.S_IFCHR if self.is_char else stat.S_IFREG
        ))


def test_closed_substream_detected_without_audio_open(tmp_path):
    path = tmp_path / "status"
    path.write_text("closed\n")
    assert mod.status_category(path) == "closed"


def test_only_preapproved_alsa_states_emitted(tmp_path):
    file = tmp_path / "status"
    file.write_text("state: RUNNING\nowner_pid: 123\n")
    assert mod.status_category(file) == "running"
    file.write_text("state: SECRET_USER_PRIVATE_VALUE\n")
    assert mod.status_category(file) == "unknown"


def test_missing_and_symlink_status_refused(tmp_path):
    missing = tmp_path / "absent"
    assert mod.status_category(missing) == "unavailable"
    orig = tmp_path / "s"
    orig.write_text("closed")
    link = tmp_path / "link"
    try:
        link.symlink_to(orig)
    except OSError:
        pytest.skip("symlink not available")
    assert mod.status_category(link) == "unavailable"


def test_oversize_status_not_read_into_output(tmp_path):
    file = tmp_path / "status"
    file.write_bytes(b"private" * 1000)
    assert mod.status_category(file) == "unavailable"


def test_permissions_informational_no_capture(monkeypatch, tmp_path):
    root = tmp_path / "sub0"
    root.mkdir()
    (root / "status").write_text("closed\n")
    (root / "hw_params").write_text("closed\n")
    monkeypatch.setattr(mod.os, "access", lambda *args, **kwargs: True)
    info = mod.inspect_capture_permissions(FakeCharNode(), root)
    assert info["status"] == "capture-node-permissions-appear-available"
    assert info["capture_node_character_device"] is True
    assert info["capture_node_read_access"] is True
    assert info["capture_node_write_access"] is True
    assert info["capture_substream_state"] == "closed"
    assert info["alsa_hw_params_state"] == "closed"
    assert info["mic_stream_opened"] is False
    assert info["recording_performed"] is False
    assert info["production_services_changed"] is False


def test_unreadable_device_is_a_permission_candidate(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.os, "access", lambda path, flag:
                        flag != os.W_OK)
    r = mod.inspect_capture_permissions(FakeCharNode(), tmp_path)
    assert r["status"] == "capture-node-not-accessible-by-runner"
    assert r["recording_performed"] is False


def test_noncharacter_and_symlink_refused_without_access(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.os, "access", lambda *args, **kwargs:
                        pytest.fail("must not check invalid node access"))
    r = mod.inspect_capture_permissions(FakeCharNode(is_char=False), tmp_path)
    assert r["status"] == "reject-capture-node-not-character-device"
    r = mod.inspect_capture_permissions(FakeCharNode(symlink=True), tmp_path)
    assert r["status"] == "inconclusive-capture-device-access"
