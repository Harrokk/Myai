"""Static, resource-bounded QAIRT DLC fixture audit tests."""
import base64
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.qairt_245_dlc_static_audit import (
    DEFAULT_FIXTURE, MAX_B64_BYTES, verify_fixture,
)


def make_fixture(tmp_path, content={"model.bin": b"tiny"}):
    memory = io.BytesIO()
    with ZipFile(memory, "w") as archive:
        for name, raw in content.items():
            archive.writestr(name, raw)
    payload = memory.getvalue()
    filename = tmp_path / "small.b64"
    filename.write_bytes(base64.b64encode(payload) + b"\n")
    return filename, payload


def test_synthetic_valid_zip_and_sha(tmp_path):
    path, payload = make_fixture(tmp_path)
    result = verify_fixture(
        path, expected_sha=hashlib.sha256(payload).hexdigest(),
        expected_size=len(payload),
    )
    assert result["status"] == "synthetic-dlc-container-integrity-verified"
    assert result["dlc_zip_entry_count"] == 1
    assert result["qnn_context_built"] is False
    assert result["htp_model_loaded"] is False
    assert result["npu_profile_measured"] is False
    assert result["services_changed"] is False


def test_checked_in_host_generated_dlc_checksum_matches():
    report = verify_fixture(DEFAULT_FIXTURE)
    assert report["status"] == "synthetic-dlc-container-integrity-verified"
    assert report["dlc_zip_entry_count"] == 4
    assert report["dlc_byte_count"] == 16004


def test_missing_file_fails_closed(tmp_path):
    r = verify_fixture(tmp_path / "absent")
    assert r["status"] == "inconclusive-fixture-unavailable"


def test_corrupt_base64_rejected(tmp_path):
    p = tmp_path / "broken.b64"
    p.write_bytes(b"****")
    assert verify_fixture(p)["status"] == "reject-invalid-base64"


def test_other_model_hash_rejected(tmp_path):
    p, raw = make_fixture(tmp_path)
    assert verify_fixture(p)["status"] == "reject-model-byte-identity-mismatch"


def test_invalid_zip_rejected_even_when_bytes_match(tmp_path):
    p = tmp_path / "fake.b64"
    raw = b"not a DLC zip"
    p.write_bytes(base64.b64encode(raw))
    report = verify_fixture(p, expected_sha=hashlib.sha256(raw).hexdigest(),
                            expected_size=len(raw))
    assert report["status"] == "reject-malformed-dlc-container"


def test_zip_traversal_is_not_accepted(tmp_path):
    p, raw = make_fixture(tmp_path, {"../danger": b"x"})
    r = verify_fixture(p, expected_sha=hashlib.sha256(raw).hexdigest(),
                       expected_size=len(raw))
    assert r["status"] == "reject-unsafe-dlc-member"


def test_oversize_base64_not_read(tmp_path):
    p = tmp_path / "large.b64"
    with p.open("wb") as file:
        file.truncate(MAX_B64_BYTES + 1)
    assert verify_fixture(p)["status"] == "inconclusive-fixture-unavailable"


def test_symlinked_fixture_is_rejected(tmp_path):
    p, _ = make_fixture(tmp_path)
    link = tmp_path / "link.b64"
    try:
        link.symlink_to(p)
    except OSError:
        pytest.skip("symlinks unavailable")
    assert verify_fixture(link)["status"] == "inconclusive-fixture-unavailable"
