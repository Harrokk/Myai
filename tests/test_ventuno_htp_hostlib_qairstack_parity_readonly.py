"""Synthetic-only HTP library selector and QAIRT fixture provenance checks."""
import json
from scripts import ventuno_htp_hostlib_qairstack_parity_readonly as probe


def test_library_selection_matches_packaged_files_by_inode(tmp_path):
    root = tmp_path / "usr_lib"
    root.mkdir()
    selected = {}
    for name in probe.HOST_NAMES:
        file = root / name
        file.write_bytes(b"NOT_EXECUTED")
        selected[name] = file
    details, all_match = probe.compare_libraries(selected, root)
    assert all_match is True
    assert all(x["selector_matches_packaged_inode"] is True
               for x in details.values())
    assert str(tmp_path) not in json.dumps(details)


def test_copy_in_different_folder_is_not_same_identity(tmp_path):
    root = tmp_path / "usr_lib"
    legacy = tmp_path / "legacy"
    root.mkdir()
    legacy.mkdir()
    for name in probe.HOST_NAMES:
        (root / name).write_bytes(b"matching content is insufficient")
        (legacy / name).write_bytes(b"matching content is insufficient")
    details, all_match = probe.compare_libraries({
        name: legacy / name for name in probe.HOST_NAMES
    }, root)
    assert all_match is False
    assert all(x["selector_matches_packaged_inode"] is False
               for x in details.values())


def test_missing_library_is_unknown_instead_of_claimed_mismatch(tmp_path):
    root = tmp_path / "usr_lib"
    root.mkdir()
    (root / probe.HOST_NAMES[0]).write_bytes(b"x")
    findings, all_match = probe.compare_libraries({}, root)
    assert all_match is False
    assert findings[probe.HOST_NAMES[0]]["selector_matches_packaged_inode"] is None
    assert findings[probe.HOST_NAMES[1]]["selector_matches_packaged_inode"] is None


def test_runtime_and_fixture_minor_mismatch_not_htp_incompatibility():
    installed = {
        "qairt-libs": {"status": "installed", "version": "2.46.0-0ubuntu1"},
        "qairt-dsp-binaries": {
            "status": "installed", "version": "2.46.0-0ubuntu1"
        },
    }
    result = probe.runtime_version_packages(installed)
    assert result["both_runtime_packages_installed"] is True
    assert result["runtime_package_versions_match_each_other"] is True
    assert result["fixture_generated_qairstack_minor"] == "2.45"
    assert result["fixture_and_runtime_minor_match"] is False
    assert result["cross_minor_htp_compatibility_proven"] is False


def test_same_minor_does_not_claim_htp_success():
    installed = {
        "qairt-libs": {"status": "installed", "version": "2.45.0"},
        "qairt-dsp-binaries": {"status": "installed", "version": "2.45.0"},
    }
    result = probe.runtime_version_packages(installed)
    assert result["fixture_and_runtime_minor_match"] is True
    assert result["cross_minor_htp_compatibility_proven"] is False


def test_missing_package_is_not_claimed_mismatched():
    installed = {
        "qairt-libs": {"status": "installed", "version": "2.46.0"},
        "qairt-dsp-binaries": {"status": "unavailable", "version": None},
    }
    result = probe.runtime_version_packages(installed)
    assert result["fixture_and_runtime_minor_match"] is None
    assert result["runtime_package_versions_match_each_other"] is False


def test_report_never_exports_paths_or_assumes_npu_success(monkeypatch, tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    for name in probe.HOST_NAMES:
        (root / name).write_bytes(b"ELF SECRET")
    monkeypatch.setattr(probe, "verify_fixture",
                        lambda path: {"file_identity_verified": True})
    runtime = {
        "qairt-libs": {"status": "installed", "version": "2.46.0"},
        "qairt-dsp-binaries": {"status": "installed", "version": "2.46.0"},
    }
    report = probe.report(selected={
        name: root / name for name in probe.HOST_NAMES
    }, host_root=root, packages=runtime)
    assert report["all_host_libraries_selected_from_exact_packaged_inodes"] is True
    assert report["fixture_dlc_identity_verified"] is True
    assert report["validated_htp_model_or_operator_support"] is False
    assert report["htp_or_qnn_executed"] is False
    assert report["device_opened"] is False
    assert report["production_modified"] is False
    assert str(tmp_path) not in json.dumps(report)
    assert "SECRET" not in json.dumps(report)
