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
