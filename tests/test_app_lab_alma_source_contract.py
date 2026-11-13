"""Synthetic tests of the exact uploaded Alma app contract; no audio opened."""
import io
import json
import os
from hashlib import sha256
from types import SimpleNamespace
import zipfile

import pytest

import integrations.arduino_app_lab.alma_reference.source_contract as m
from core.app_lab_unix_final_text import verify_signed_request

K = b"t" * 32
SID = "a" * 32
RID = "b" * 32


def ev(kind, data):
    return SimpleNamespace(type=kind, data=data)


def test_exact_offline_manifest_is_model_and_app_version_pinned():
    assert len(m.FILES) == 13
    assert m.FILES["python/main.py"][0] == "f1d3f3e2ecc94197f3a452f1a13029f41c7778046d14dc28d7346c87c06f2a87"
    assert m.FILES["bricks/piper_sv_tts/container/models/sv_SE-alma-medium.onnx"][0] == "b4bfecd22e30cf28f514eeea06c0da440be1721435a652d0571ee65963ce8f65"


def test_real_asr_full_text_is_accepted_only_once_after_mic_release():
    gate = m.AlmaFinalASRGate()
    assert not gate.feed(ev("partial_text", "Vad he"))
    assert gate.feed(ev("full_text", "Vad heter du?"))
    assert not gate.feed(ev("full_text", "another private command"))
    assert gate.take_final(session_active=True, asr_released=True,
                           stop_requested=lambda: False) == "Vad heter du?"
    assert gate.take_final(session_active=True, asr_released=True,
                           stop_requested=lambda: False) is None


def test_partial_fallback_is_not_forwarded_to_myai():
    gate = m.AlmaFinalASRGate()
    assert not gate.feed(ev("partial_text", "ta bort min"))
    assert gate.take_final(session_active=True, asr_released=True,
                           stop_requested=lambda: False) is None


@pytest.mark.parametrize("bad", [
    None, "", "  ", "sekret\nkommando", "x" * 501, "Hej\u202e",
])
def test_bad_final_is_not_forwarded(bad):
    gate = m.AlmaFinalASRGate()
    assert gate.feed(ev("full_text", bad)) is False
    assert gate.take_final(session_active=True, asr_released=True,
                           stop_requested=lambda: False) is None


@pytest.mark.parametrize("flags", [
    {"session_active": False},
    {"asr_released": False},
    {"stop_requested": None},
    {"stop_requested": lambda: True},
    {"stop_requested": lambda: None},
])
def test_lifecycle_gate_is_mandatory(flags):
    gate = m.AlmaFinalASRGate()
    assert gate.feed(ev("full_text", "Säg något"))
    args = dict(session_active=True, asr_released=True, stop_requested=lambda: False)
    args.update(flags)
    assert gate.take_final(**args) is None


def test_signed_real_event_is_compatible_with_myai_server():
    gate = m.AlmaFinalASRGate()
    assert gate.feed(ev("full_text", "Hur fungerar solceller?"))
    text = gate.take_final(session_active=True, asr_released=True,
                           stop_requested=lambda: False)
    raw = m.sign_final_for_myai(text, secret=K, session_id=SID,
                                request_id=RID, issued_at=1900000000)
    verified = verify_signed_request(raw, secret=K, active_session=SID,
                                     now=1900000000)
    assert verified["text"] == "Hur fungerar solceller?"
    assert verified["request_id"] == RID


def test_signature_changes_if_text_tampered():
    raw = json.loads(m.sign_final_for_myai("Hej", secret=K, session_id=SID,
                       request_id=RID, issued_at=1900000000))
    raw["text"] = "Annat"
    with pytest.raises(ValueError):
        verify_signed_request(json.dumps(raw).encode(),
                              secret=K, active_session=SID, now=1900000000)


def make_zip(tmp_path, *, files=None):
    files = files or {"python/main.py": b"fake text", "app.yaml": b"a: b"}
    archive_path = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, contents in files.items():
            archive.writestr(m.ROOT + filename, contents)
    return archive_path, files


def test_archive_audit_accepts_exact_synthetic_fixture(tmp_path, monkeypatch):
    archive, files = make_zip(tmp_path)
    monkeypatch.setattr(m, "FILES", {
        key: (sha256(value).hexdigest(), len(value)) for key, value in files.items()
    })
    monkeypatch.setattr(m, "ZIP_SHA256", sha256(archive.read_bytes()).hexdigest())
    result = m.verify_operator_archive(archive)
    assert result["status"] == "exact-archive-verified"
    assert result["files_verified"] == 2


def test_archive_audit_rejects_other_zip(tmp_path):
    archive, _ = make_zip(tmp_path)
    with pytest.raises(ValueError, match="exact operator-tested"):
        m.verify_operator_archive(archive)


def test_archive_audit_rejects_duplicate_paths(tmp_path, monkeypatch):
    archive = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(m.ROOT + "README.md", b"a")
        z.writestr(m.ROOT + "README.md", b"a")
    monkeypatch.setattr(m, "ZIP_SHA256", sha256(archive.read_bytes()).hexdigest())
    monkeypatch.setattr(m, "FILES", {"README.md": (sha256(b"a").hexdigest(), 1)})
    with pytest.raises(ValueError):
        m.verify_operator_archive(archive)


def test_archive_audit_refuses_symlink_source(tmp_path):
    archive, _ = make_zip(tmp_path)
    link = tmp_path / "link.zip"
    link.symlink_to(archive)
    with pytest.raises(ValueError):
        m.verify_operator_archive(link)


def test_source_has_no_microphone_or_socket_client():
    import inspect
    source = inspect.getsource(m)
    for forbidden in ("socket.socket(", ".connect(", ".bind(", "arecord",
                      "aplay", "ArduinoASR(", "Microphone("):
        assert forbidden not in source
