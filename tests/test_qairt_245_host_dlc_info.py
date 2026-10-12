"""Native QAIRT DLC-info host-only safety and evidence regression tests."""
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.qairt_245_host_dlc_info as mod


def test_missing_sdk_or_dlc_never_invokes_vendor_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(mod.subprocess, "run", lambda *args, **kwargs:
                        pytest.fail("unexpected process execution"))
    assert mod.inspect_with_qualcomm(tmp_path, tmp_path)["status"] == (
        "no-go-unverified-inputs"
    )


def test_only_approved_digest_allows_reader(tmp_path, monkeypatch):
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    sdk = tmp_path / mod.SDK_VERSION
    sdk.mkdir()
    p = tmp_path / "model.dlc"
    p.write_bytes(b"fake")
    monkeypatch.setattr(mod.subprocess, "run", lambda *args, **kwargs:
                        pytest.fail("unexpected process execution"))
    assert mod.inspect_with_qualcomm(sdk, p)["dlc_bytes_verified"] is False


def test_missing_reader_reports_inconclusive_without_faking_structure(tmp_path, monkeypatch):
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    sdk = tmp_path / mod.SDK_VERSION
    sdk.mkdir()
    p = tmp_path / "model.dlc"
    raw = b"x" * 20
    p.write_bytes(raw)
    import hashlib
    monkeypatch.setattr(mod, "DLC_SIZE", len(raw))
    monkeypatch.setattr(mod, "SHA256", hashlib.sha256(raw).hexdigest())
    report = mod.inspect_with_qualcomm(sdk, p)
    assert report["status"] == "inconclusive-official-dlc-reader-missing"
    assert report["dlc_bytes_verified"] is True
    assert report["reader_structure_claim_proven"] is False


def test_native_reader_zero_exit_and_structure_keywords(tmp_path, monkeypatch):
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    sdk = tmp_path / mod.SDK_VERSION
    tool = sdk / "bin" / "x86_64-linux-clang" / "qairt-dlc-info"
    tool.parent.mkdir(parents=True)
    tool.write_text("#!/usr/bin/env python3\n")
    p = tmp_path / "small.dlc"
    raw = b"x" * 20
    p.write_bytes(raw)
    import hashlib
    monkeypatch.setattr(mod, "DLC_SIZE", len(raw))
    monkeypatch.setattr(mod, "SHA256", hashlib.sha256(raw).hexdigest())
    observed = []
    def fake_run(argv, **kwargs):
        observed.append(argv)
        assert argv[-3:] == [str(tool), "-i", str(p)]
        assert kwargs["timeout"] <= 25
        return SimpleNamespace(returncode=0,
                               stdout="Input\nOutput\nLayer\n",
                               stderr="")
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    result = mod.inspect_with_qualcomm(sdk, p)
    assert len(observed) == 1
    assert result["status"] == "official-dlc-reader-parsed-model"
    assert result["reader_exit_zero"] is True
    assert result["htp_execution_verified"] is False
    assert result["native_tensor_encoding_verified"] is False
    assert result["services_modified"] is False


def test_zero_exit_without_structure_remains_inconclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    sdk = tmp_path / mod.SDK_VERSION
    tool = sdk / "bin" / "x86_64-linux-clang" / "qairt-dlc-info"
    tool.parent.mkdir(parents=True)
    tool.write_text("qairt")
    p = tmp_path / "small.dlc"
    raw = b"x" * 20
    p.write_bytes(raw)
    import hashlib
    monkeypatch.setattr(mod, "DLC_SIZE", len(raw))
    monkeypatch.setattr(mod, "SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(mod.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0,
                                        stdout="QNN info only", stderr=""))
    result = mod.inspect_with_qualcomm(sdk, p)
    assert result["status"] == "inconclusive-reader-output"
    assert result["reader_structure_claim_proven"] is False


def test_reader_failures_keep_backend_and_graph_claims_false(tmp_path, monkeypatch):
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    sdk = tmp_path / mod.SDK_VERSION
    tool = sdk / "bin" / "x86_64-linux-clang" / "qairt-dlc-info"
    tool.parent.mkdir(parents=True)
    tool.write_text("qairt")
    p = tmp_path / "small.dlc"
    raw = b"x" * 20
    p.write_bytes(raw)
    import hashlib
    monkeypatch.setattr(mod, "DLC_SIZE", len(raw))
    monkeypatch.setattr(mod, "SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(mod.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=1,
                            stdout="",stderr="Error in /tmp/private/data"))
    result = mod.inspect_with_qualcomm(sdk, p)
    assert result["status"] == "inconclusive-official-dlc-reader-error"
    assert result["reader_structure_claim_proven"] is False
    assert result["htp_compatibility_verified"] is False
    assert "/tmp/private" not in str(result)

def test_official_io_table_shape_type_and_bytes_are_safely_reported():
    snippet = """
    | Input Name | Dimensions | Type | Encoding Info |
    | private/user/path | 1,8,8,1 | Float_32 | No encoding info for this tensor |
    | Output Name | Dimensions | Type | Encoding Info |
    | private/output | 1,8,8,1 | Float_32 | No encoding info for this tensor |
    """
    result = mod.summarize_official_io_tables(snippet)
    assert result["dlc_io_tables_both_parsed"] is True
    assert result["synthetic_float32_input_byte_size_matches_dlc"] is True
    assert result["dlc_declared_inputs"] == [{
        "dimensions": [1, 8, 8, 1],
        "declared_dtype": "float_32",
        "elements": 64,
        "encoding_declared": False,
    }]
    assert result["qnn_native_io_compatibility_verified"] is False
    assert "private" not in str(result)


def test_incompatible_input_dtype_is_not_accepted():
    text = """
    | Input Name | Dimensions | Type | Encoding Info |
    | input | 1,1,8,8 | UFix_8 | Encoded |
    | Output Name | Dimensions | Type | Encoding Info |
    | out | 1,1,8,8 | Float_32 | No encoding info |
    """
    report = mod.summarize_official_io_tables(text)
    assert report["synthetic_float32_input_byte_size_matches_dlc"] is False
    assert report["dlc_io_tables_both_parsed"] is False


def test_malformed_dlc_tables_cannot_claim_input_layout():
    text = """
    | Input Name | Dimensions | Type | Encoding Info |
    | test | 1,0,8,8 | Float_32 | No encoding info |
    | Output Name | Dimensions | Type | Encoding Info |
    | test | 1,1,8,8 | Float_32 | No encoding info |
    """
    report = mod.summarize_official_io_tables(text)
    assert report["synthetic_float32_input_byte_size_matches_dlc"] is False
    assert report["dlc_declared_inputs"] == []

def test_spaced_bracketed_dimension_format_is_supported():
    snippet = """
    Input Name | Dimensions | Type | Encoding Info
    | synthetic_input | [1, 1, 8, 8] | Float_32 | No encoding info |
    Output Name | Dimensions | Type | Encoding Info
    | output | (1 x 1 x 8 x 8) | Float_32 | No encoding info |
    """
    report = mod.summarize_official_io_tables(snippet)
    assert report["io_table_headers_detected"] == ["input", "output"]
    assert report["dlc_io_tables_both_parsed"] is True
    assert report["synthetic_float32_input_byte_size_matches_dlc"] is True
    assert report["dlc_declared_outputs"][0]["elements"] == 64
    assert "synthetic_input" not in str(report)


def test_sanitized_unknown_table_shape_reports_no_tensor_name():
    report = mod.summarize_official_io_tables(
        "Input Name | Dimensions | Type | Encoding Info\n"
        "| super_private_name | unknown-shape | Float_32 | unknown |\n"
    )
    assert report["dlc_declared_inputs"] == []
    assert report["io_candidate_row_counts"]["input"] == 1
    assert report["unrecognized_dimension_formats"] == ["unrecognized"]
    assert "super_private_name" not in str(report)
