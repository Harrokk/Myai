"""Safety tests for isolated QAIRT 2.45 converter launch planning."""
from pathlib import Path

import pytest

import scripts.qairt_245_host_conversion_trial as m


def test_only_approved_converter_names(tmp_path):
    source = tmp_path / "m.onnx"
    source.write_bytes(b"test")
    output = tmp_path / "out.dlc"
    tool = tmp_path / "arbitrary-command"
    tool.write_bytes(b"#!/bin/python3")
    with pytest.raises(ValueError, match="not-an-allowlisted-converter"):
        m.command_for_tool(tool, source, output)


def test_converter_synthetic_python_arguments(tmp_path):
    tool = tmp_path / "qairt-converter"
    tool.write_bytes(b"#!/usr/bin/env python3\n")
    source = tmp_path / "model.onnx"
    source.write_bytes(b"model")
    argv = m.command_for_tool(tool, source, tmp_path / "output.dlc")
    assert argv[-4:] == ["--input_network", str(source),
                         "--output_path", str(tmp_path / "output.dlc")]
    assert argv[0] == __import__("sys").executable


def test_converter_model_or_output_symlink_rejected(tmp_path):
    tool = tmp_path / "qnn-onnx-converter"
    tool.write_bytes(b"test")
    source = tmp_path / "m.onnx"
    source.write_bytes(b"test")
    external = tmp_path / "external.onnx"
    external.write_bytes(b"test")
    try:
        source.unlink()
        source.symlink_to(external)
    except OSError:
        pytest.skip("symlinks unsupported")
    with pytest.raises(ValueError, match="unverified-source"):
        m.command_for_tool(tool, source, tmp_path / "out.cpp")


def test_python_dependency_error_is_sanitized():
    assert m.sanitized_missing_dependency(
        "ModuleNotFoundError: No module named 'qti.aisw.converters'"
    ) == "qti.aisw.converters"
    assert m.sanitized_missing_dependency("unexpected error private/path") is None


def test_nonhost_target_never_converts(monkeypatch, tmp_path):
    monkeypatch.setattr(m.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(m, "run_one", lambda *args, **kw:
                        pytest.fail("converter executed"))
    result = m.conversion_trial(tmp_path, tmp_path, tmp_path / "out")
    assert result["status"] == "no-go"
    assert result["npu_profiling_verified"] is False
    assert result["production_services_changed"] is False


def test_invalid_sdk_version_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(m.platform, "machine", lambda: "x86_64")
    sdk = tmp_path / "sdk-2.50"
    sdk.mkdir()
    assert m.conversion_trial(sdk, tmp_path, tmp_path / "out")["status"] == (
        "reject-unexpected-sdk-location"
    )


def test_model_identity_required_before_any_execution(monkeypatch, tmp_path):
    monkeypatch.setattr(m.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(m, "run_one", lambda *a, **k:
                        pytest.fail("converter executed"))
    sdk = tmp_path / m.SDK_VERSION
    sdk.mkdir()
    source = tmp_path / "fixture"
    source.mkdir()
    result = m.conversion_trial(sdk, source, tmp_path / "out")
    assert result["status"] == "reject-model-checksum"


def test_missing_converter_is_not_success(tmp_path):
    result = m.run_one(tmp_path / "qairt-converter",
                       tmp_path / "x.onnx",
                       tmp_path / "out.dlc", {})
    assert result["status"] == "tool-not-present"
    assert result["output_created"] is False
