"""Regression safety tests for QAIRT host conversion-chain detection."""
from pathlib import Path

import pytest

from scripts.ventuno_qairt_converter_inventory import (
    command_evidence, decision, relevant_cli_options, sdk_file_inventory,
)


def test_help_flags_detect_dlc_route_only_when_documented():
    result = relevant_cli_options(
        "  --dlc_path  Use a DLC\n --backend  library\n"
        "  --binary_file output\n"
    )
    assert result["--dlc_path"] is True
    assert result["--backend"] is True
    assert result["--model"] is False
    assert result["--retrieve_context"] is False


def test_help_text_cannot_impersonate_flags_by_near_matches():
    result = relevant_cli_options("something--dlc_pathology --modelish --backendish")
    assert result["--dlc_path"] is False
    assert result["--model"] is False
    assert result["--backend"] is False


def test_limited_sdk_scan_reports_only_known_filenames(tmp_path):
    root = tmp_path / "sdk"
    directory = root / "bin" / "x86_64-linux-clang"
    directory.mkdir(parents=True)
    (directory / "qnn-onnx-converter").write_text("nothing")
    (directory / "qnn-model-lib-generator").write_text("nothing")
    (directory / "private-user-file.txt").write_text("private")
    libs = root / "lib"
    libs.mkdir()
    (libs / "libQnnHtpV75Stub.so").write_bytes(b"test")
    report = sdk_file_inventory((root,))
    assert report["tool_names_present_beyond_or_within_path"] == [
        "qnn-model-lib-generator", "qnn-onnx-converter"
    ]
    assert report["sdk_library_names_present"] == ["libQnnHtpV75Stub.so"]
    assert report["production_model_files_inspected"] is False
    assert report["scan_capped"] is False
    assert "private-user-file" not in str(report)


def test_symlink_sdk_tool_is_ignored(tmp_path):
    root = tmp_path / "sdk"
    root.mkdir()
    fake = tmp_path / "private"
    fake.write_text("secret")
    try:
        (root / "qnn-onnx-converter").symlink_to(fake)
    except OSError:
        pytest.skip("symlink not supported")
    report = sdk_file_inventory((root,))
    assert not report["tool_names_present_beyond_or_within_path"]


def test_converter_found_offpath_cannot_authorize_profile(tmp_path):
    root = tmp_path / "sdk"
    root.mkdir()
    for tool in ("qnn-onnx-converter", "qnn-model-lib-generator"):
        (root / tool).write_bytes(b"placeholder")
    report = decision({}, sdk_file_inventory((root,)))
    assert report["status"] == "candidate-offpath-tools-not-validated"
    assert report["safe_to_start_htp_profile"] is False


def test_dlc_flag_does_not_imply_standalone_model_is_available():
    evidence = {"qnn-context-binary-generator": {
        "path_available": True,
        "help_readable": True,
        "flags": {"--dlc_path": True},
    }}
    result = decision(evidence, {
        "scan_capped": False, "unreadable": False,
        "tool_names_present_beyond_or_within_path": [],
    })
    assert result["status"] == "dlc-loading-option-present-but-dlc-creation-unverified"
    assert result["valid_independent_dlc_or_qnn_model_available"] is False
    assert result["complete_conversion_chain_verified"] is False


def test_absent_chain_is_explicit_no_go():
    result = decision({}, {
        "scan_capped": False, "unreadable": False,
        "tool_names_present_beyond_or_within_path": [],
    })
    assert result["status"] == "no-go-converter-or-valid-standalone-dlc-missing"
    assert result["safe_to_modify_running_services"] is False


def test_capped_scan_is_inconclusive_not_negative(tmp_path):
    root = tmp_path / "sdk"
    root.mkdir()
    for index in range(400):
        (root / f"some-extra-{index}.txt").write_text("ok")
    inventory = sdk_file_inventory((root,))
    assert inventory["scan_capped"] is True
    assert decision({}, inventory)["status"] == "inconclusive-bounded-scan"


def test_tool_allowlist_rejects_arbitrary_process_execution():
    with pytest.raises(ValueError, match="unapproved-tool"):
        command_evidence("/bin/sh")


def test_read_only_missing_tools_do_not_spawn(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.setattr("subprocess.run", lambda *a, **k:
                        pytest.fail("unexpected process call"))
    assert command_evidence("qnn-onnx-converter") == {
        "path_available": False,
        "help_readable": False,
    }
