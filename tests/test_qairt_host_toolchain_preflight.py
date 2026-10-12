"""Fail-closed host QAIRT converter SDK and fixture identity tests."""
import hashlib

import pytest

import scripts.qairt_host_toolchain_preflight as mod


def test_missing_sdk_does_not_claim_converter(tmp_path):
    r = mod.sdk_tool_status(tmp_path / "missing", "linux")
    assert r["sdk_root_present"] is False
    assert mod.readiness(r, False)["status"] == "sdk-not-supplied"


def test_known_sdk_linux_tool_locations_are_metadata_only(tmp_path):
    bin_dir = tmp_path / "sdk" / "bin" / "x86_64-linux-clang"
    bin_dir.mkdir(parents=True)
    (bin_dir / "qnn-onnx-converter").write_text("synthetic")
    (bin_dir / "qnn-model-lib-generator").write_text("synthetic")
    r = mod.sdk_tool_status(tmp_path / "sdk", "linux")
    assert r["converter_found"] is True
    assert r["model_lib_generator_found"] is True
    assert mod.readiness(r, True)["status"] == (
        "candidate-tools-present-manual-qairt-version-and-abi-review"
    )
    assert mod.readiness(r, True)["qairt_sdk_version_245_verified"] is False
    assert mod.readiness(r, True)["npu_profiling_authorized"] is False


def test_known_sdk_windows_tool_locations_are_metadata_only(tmp_path):
    bin_dir = tmp_path / "sdk" / "bin" / "x86_64-windows-msvc"
    bin_dir.mkdir(parents=True)
    (bin_dir / "qnn-onnx-converter").write_text("synthetic")
    (bin_dir / "qnn-model-lib-generator").write_text("synthetic")
    result = mod.sdk_tool_status(tmp_path / "sdk", "windows")
    assert result["converter_found"]
    assert result["model_lib_generator_found"]


def test_converter_is_not_alone_enough(tmp_path):
    bin_dir = tmp_path / "sdk" / "bin" / "x86_64-linux-clang"
    bin_dir.mkdir(parents=True)
    (bin_dir / "qnn-onnx-converter").write_text("synthetic")
    r = mod.sdk_tool_status(tmp_path / "sdk", "linux")
    assert mod.readiness(r, True)["status"] == "no-go-host-converter-chain-incomplete"


def test_unknown_host_rejected():
    with pytest.raises(ValueError, match="unsupported-development-host"):
        mod.sdk_tool_status(__import__("pathlib").Path("/"), "arm64")


def test_unsafe_symlinked_tool_and_sdk_rejected(tmp_path):
    root = tmp_path / "sdk"
    sub = root / "bin" / "x86_64-linux-clang"
    sub.mkdir(parents=True)
    file = tmp_path / "outside"
    file.write_text("not-a-tool")
    try:
        (sub / "qnn-onnx-converter").symlink_to(file)
    except OSError:
        pytest.skip("symlinks unsupported")
    report = mod.sdk_tool_status(root, "linux")
    assert report["converter_found"] is False


def test_fixture_requires_exact_size_and_verified_digest(tmp_path, monkeypatch):
    folder = tmp_path / "fixture"
    folder.mkdir()
    model = folder / "tiny_qdq_conv.onnx"
    model.write_bytes(b"synthetic")
    assert mod.verified_fixture_presence(folder) is False
    monkeypatch.setattr(mod, "EXPECTED_MODEL_SIZE", 9)
    monkeypatch.setattr(mod, "EXPECTED_SHA256",
                        hashlib.sha256(b"synthetic").hexdigest())
    assert mod.verified_fixture_presence(folder) is True
    model.write_bytes(b"different")
    assert mod.verified_fixture_presence(folder) is False


def test_source_missing_is_no_go_even_if_tools_present():
    sdk = {"sdk_root_present": True, "converter_found": True,
           "model_lib_generator_found": True}
    report = mod.readiness(sdk, False)
    assert report["status"] == "no-go-onnx-artifact-identity-unverified"
    assert report["onnx_to_qnn_conversion_completed"] is False
    assert report["myai_geniex_services_changed"] is False


def test_host_sdk_report_has_no_path_information(tmp_path):
    r = mod.sdk_tool_status(tmp_path / "sensitive_name", "linux")
    assert str(tmp_path) not in str(r)
    assert "sensitive_name" not in str(r)
