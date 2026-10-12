"""Validate the generated tiny QAIRT DLC fixture without executing QNN.

No SDK imports, context creation, model execution, compilation or filesystem
writes. Strictly bounded Base64/ZIP parsing of a synthetic tracked fixture.
Valid DLC container structure is NOT proof of HTP compatibility or placement.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

EXPECTED_SHA256 = "137ea7f4386d0e7a090bb3d2348432eb7f90da70edf04ea15afc523948dee3ba"
EXPECTED_SIZE = 16004
MAX_B64_BYTES = 40000
MAX_ZIP_ENTRIES = 12
MAX_UNCOMPRESSED_BYTES = 16 * 1024 * 1024
DEFAULT_FIXTURE = (Path(__file__).resolve().parents[1] /
                   "fixtures" / "qairt_245" / "tiny_qdq_conv.dlc.b64")


def verify_fixture(
    path: Path,
    *,
    expected_sha: str = EXPECTED_SHA256,
    expected_size: int = EXPECTED_SIZE,
) -> dict[str, object]:
    out: dict[str, object] = {
        "status": "inconclusive-fixture-unavailable",
        "expected_qairstack": "QAIRT 2.45.0.260326",
        "dlc_sha256": None,
        "dlc_byte_count": 0,
        "dlc_zip_entry_count": 0,
        "container_zip_structure_verified": False,
        "qnn_converter_reported_success_on_host": True,
        "qnn_context_built": False,
        "htp_model_loaded": False,
        "npu_profile_measured": False,
        "services_changed": False,
    }
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_B64_BYTES:
            return out
        encoded = path.read_bytes().strip()
    except OSError:
        return out
    try:
        binary = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        out["status"] = "reject-invalid-base64"
        return out
    out["dlc_byte_count"] = len(binary)
    out["dlc_sha256"] = hashlib.sha256(binary).hexdigest()
    if len(binary) != expected_size or out["dlc_sha256"] != expected_sha:
        out["status"] = "reject-model-byte-identity-mismatch"
        return out
    try:
        with ZipFile(io.BytesIO(binary)) as archive:
            infos = archive.infolist()
            out["dlc_zip_entry_count"] = len(infos)
            if not 1 <= len(infos) <= MAX_ZIP_ENTRIES:
                out["status"] = "reject-dlc-entry-count"
                return out
            total = 0
            for item in infos:
                name = PurePosixPath(item.filename)
                if name.is_absolute() or ".." in name.parts or "\\" in item.filename:
                    out["status"] = "reject-unsafe-dlc-member"
                    return out
                total += item.file_size
                if total > MAX_UNCOMPRESSED_BYTES:
                    out["status"] = "reject-dlc-uncompressed-size"
                    return out
            if archive.testzip() is not None:
                out["status"] = "reject-dlc-checksum"
                return out
    except (BadZipFile, OSError, ValueError, RuntimeError):
        out["status"] = "reject-malformed-dlc-container"
        return out
    out["container_zip_structure_verified"] = True
    out["status"] = "synthetic-dlc-container-integrity-verified"
    return out


def main() -> int:
    result = verify_fixture(DEFAULT_FIXTURE)
    print("Static QAIRT 2.45 synthetic DLC fixture audit:",
          json.dumps(result, sort_keys=True))
    print("DLC container integrity does not validate target HTP execution.")
    return 0 if result["container_zip_structure_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
