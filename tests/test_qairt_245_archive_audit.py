"""Offline QAIRT 2.45 archive-audit safety regression tests."""
from pathlib import Path
from zipfile import ZipFile

from scripts.qairt_245_archive_audit import (
    component_label, inspect_archive, safe_zip_member,
)


def make_zip(path: Path, names: dict[str, bytes]) -> None:
    with ZipFile(path, "w") as archive:
        for name, data in names.items():
            archive.writestr(name, data)


def test_safe_zip_member_rejects_external_path():
    for bad in ("", "../out", "/etc/passwd", "a/../../z", "a\\b"):
        assert safe_zip_member(bad) is False
    assert safe_zip_member("qairt/2.45.0.260326/bin/x86_64-linux-clang/qnn-onnx-converter")


def test_component_restricted_to_exact_names_and_arch():
    assert component_label(
        "qairt/2.45.0.260326/bin/x86_64-linux-clang/qnn-onnx-converter"
    ) == "qnn-onnx-converter"
    assert component_label(
        "qairt/2.45.0.260326/bin/aarch64-linux-gnu/qnn-onnx-converter"
    ) is None
    assert component_label(
        "qairt/2.45.0.260326/bin/x86_64-linux-clang/qnn-onnx-converter-malicious"
    ) is None


def test_valid_synthetic_archive_reports_only_allowlisted_components(tmp_path):
    path = tmp_path / "synthetic.zip"
    make_zip(path, {
        "qairt/2.45.0.260326/bin/x86_64-linux-clang/qnn-onnx-converter": b"x",
        "qairt/2.45.0.260326/bin/x86_64-linux-clang/qnn-model-lib-generator": b"x",
        "qairt/2.45.0.260326/lib/x86_64-linux-clang/libQnnHtp.so": b"x",
        "qairt/2.45.0.260326/models/secret.bin": b"private",
    })
    info = inspect_archive(path)
    assert info["status"] == "host-conversion-components-in-official-archive"
    assert info["archive_sha256"]
    assert info["sdk_extracted"] is False
    assert info["sdk_binaries_executed"] is False
    assert "secret" not in str(info)
    assert info["components_present"] == [
        "libQnnHtp.so", "qnn-model-lib-generator", "qnn-onnx-converter"
    ]


def test_archive_without_converter_is_inconclusive(tmp_path):
    path = tmp_path / "missing.zip"
    make_zip(path, {"qairt/bin/x86_64-linux-clang/qnn-model-lib-generator": b"x"})
    info = inspect_archive(path)
    assert info["status"] == "inconclusive-required-converters-not-found"
    assert info["qnn_model_converted"] is False


def test_path_traversal_rejects_even_if_converters_present(tmp_path):
    path = tmp_path / "unsafe.zip"
    make_zip(path, {
        "qairt/bin/x86_64-linux-clang/qnn-onnx-converter": b"x",
        "qairt/bin/x86_64-linux-clang/qnn-model-lib-generator": b"x",
        "../escape": b"x",
    })
    info = inspect_archive(path)
    assert info["path_traversal_entries_present"] is True
    assert info["status"] == "reject-unsafe-zip-paths"


def test_invalid_archive_fails_closed(tmp_path):
    path = tmp_path / "notzip.zip"
    path.write_bytes(b"not-a-zip")
    assert inspect_archive(path)["status"] == "reject-invalid-zip-file"


def test_missing_archive_fails_closed(tmp_path):
    assert inspect_archive(tmp_path / "missing.zip")["status"] == (
        "inconclusive-archive-unavailable"
    )
