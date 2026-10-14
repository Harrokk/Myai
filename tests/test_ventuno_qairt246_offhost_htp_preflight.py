"""Offline tests only; fake ELF files are never executed or dlopened."""
import json
from pathlib import Path

from scripts import ventuno_qairt246_offhost_htp_preflight as gate


def fake_elf(machine=62):
    raw = bytearray(64)
    raw[:4] = b"\x7fELF"
    raw[4] = 2
    raw[5] = 1
    raw[18:20] = machine.to_bytes(2, "little")
    return bytes(raw)


def synthetic_sdk(root, *, wrong=None):
    for name, relative in gate.HOST_ARTIFACTS.items():
        f = root / relative
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(fake_elf(183 if name == wrong else 62))
    return root


def test_wrong_arch_never_inspects_files_or_vendor_tools(monkeypatch):
    monkeypatch.setattr(gate, "inspect_sdk",
                        lambda *_: (_ for _ in ()).throw(AssertionError("SDK accessed")))
    result = gate.preflight(host_arch="aarch64")
    assert result["status"] == "no_go_non_x86_host"
    assert result["sdk"] is None
    assert result["qnn_context_generated"] is False
    assert result["ventuno_accessed_or_modified"] is False


def test_exact_synthetic_dlc_fixture_integrity_is_real():
    report = gate.inspect_synthetic_dlc()
    assert report["exact_synthetic_dlc_identity_verified"] is True
    assert report["synthetic_dlc_created_with_qairstack"] == "2.45"
    assert report["htp_context_generation_completed"] is False


def test_missing_sdk_is_a_no_go_even_when_dlc_is_verified():
    result = gate.preflight(host_arch="x86_64")
    assert result["status"] == "no_go_sdk_not_supplied"
    assert result["synthetic_dlc"]["exact_synthetic_dlc_identity_verified"]
    assert result["sdk"]["sdk_provenance_attested"] is False
    assert result["vendor_verified_numeric_soc_id"] is False


def test_fake_complete_sdk_still_never_authorizes_prepare(tmp_path):
    root = synthetic_sdk(tmp_path / "2.46.0.260900")
    result = gate.preflight(sdk_root=root, host_arch="x86_64")
    assert result["sdk"]["sdk_label_looks_like_246"] is True
    assert result["sdk"]["host_tools_look_like_x86_elf"] is True
    assert all(v == "x86_64" for v in result["sdk"]["artifacts"].values())
    assert result["status"] == "no_go_manual_vendor_sdk_and_soc_attestation_required"
    assert result["vendor_verified_soc_config_for_exact_sdk"] is False
    assert result["sdk_download_or_execution_attempted"] is False
    assert result["qnn_context_generated"] is False
    assert str(tmp_path) not in json.dumps(result)


def test_wrong_elf_architecture_fails_closed(tmp_path):
    root = synthetic_sdk(tmp_path / "2.46.0.260900", wrong="htp_backend")
    result = gate.preflight(sdk_root=root, host_arch="x86_64")
    assert result["sdk"]["artifacts"]["htp_backend"] == "different_elf_architecture"
    assert result["status"] == "no_go_sdk_host_artifacts_missing_or_invalid"


def test_sdk_directory_label_not_proof_of_246(tmp_path):
    root = synthetic_sdk(tmp_path / "2.45.0.260326")
    result = gate.preflight(sdk_root=root, host_arch="x86_64")
    assert result["sdk"]["sdk_label_looks_like_246"] is False
    assert result["status"] == "no_go_unverified_sdk_version_label"


def test_sdk_symlink_and_artifact_symlink_are_not_trusted(tmp_path):
    original = synthetic_sdk(tmp_path / "2.46.0.260900")
    alias = tmp_path / "sdk-link"
    alias.symlink_to(original, target_is_directory=True)
    assert gate.inspect_sdk(alias)["sdk_directory_present"] is False
    backend = original / gate.HOST_ARTIFACTS["htp_backend"]
    backend.unlink()
    backend.symlink_to(original / gate.HOST_ARTIFACTS["dlc_loader"])
    assert gate.inspect_sdk(original)["artifacts"]["htp_backend"] == (
        "missing_or_untrusted_file_type"
    )


def test_zero_and_invalid_elf_headers_never_pass(tmp_path):
    root = tmp_path / "sdk"
    root.mkdir()
    file = root / "tool"
    file.write_bytes(b"random-garbage")
    assert gate.inspect_regular_x86_file(file) == "file_size_outside_bound"
    file.write_bytes(b"x" * 64)
    assert gate.inspect_regular_x86_file(file) == "not_elf_or_truncated"
    file.write_bytes(fake_elf(183))
    assert gate.inspect_regular_x86_file(file) == "different_elf_architecture"


def test_unverified_model_bytes_keep_no_go_even_with_fake_sdk(tmp_path):
    root = synthetic_sdk(tmp_path / "2.46.0.260900")
    bad_dlc = tmp_path / "bad.b64"
    bad_dlc.write_bytes(b"not-a-qnn-dlc")
    result = gate.preflight(
        sdk_root=root, synthetic_dlc=bad_dlc, host_arch="x86_64"
    )
    assert result["status"] == "no_go_unverified_synthetic_dlc"
    assert result["synthetic_dlc"]["exact_synthetic_dlc_identity_verified"] is False
    assert result["htp_operator_support_tested"] is False


def test_report_never_implies_soc_id_or_htp_is_verified(tmp_path):
    root = synthetic_sdk(tmp_path / "2.46.0.260900")
    report = gate.preflight(sdk_root=root, host_arch="x86_64")
    assert report["board_chipset_documented"] == "QCS8275"
    assert report["htp_architecture_documented_by_arduino"] == "V75"
    assert report["vendor_verified_numeric_soc_id"] is False
    assert report["vendor_verified_soc_config_for_exact_sdk"] is False
    assert report["npu_placement_measured"] is False
    assert report["htp_operator_support_tested"] is False
    assert report["raw_sdk_paths_file_data_or_secrets_exported"] is False
    assert "/tmp/" not in json.dumps(report)
