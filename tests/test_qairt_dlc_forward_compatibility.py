"""QAIRT QNN DLC forward format compatibility, not HTP certification."""
import json
import pytest
from scripts.qairt_dlc_forward_compatibility import (
    KNOWN_SOURCE_MINOR, evaluate_forward_compatibility as evaluate,
)
from scripts import ventuno_v75_npu_readiness_readonly as readiness


def test_qualcomm_245_dlc_format_forward_compatible_with_246_runtime():
    value = evaluate(KNOWN_SOURCE_MINOR, "2.46", source_sha_verified=True)
    assert value["format_forward_compatibility"] == (
        "documented_dlc_format_compatibility_not_htp_proof"
    )
    assert value["vendor_dlc_forward_compatibility_policy_applied"] is True
    assert value["compatible_runtime_minor"] is True
    assert value["htp_v75_operator_compatibility_verified"] is False
    assert value["htp_or_npu_executed"] is False
    assert value["qnn_cpu_inference_executed"] is False
    assert value["backend_initialization_verified"] is False
    assert value["npu_placement_verified"] is False


@pytest.mark.parametrize("source,target", [
    ("2.45", "2.45"), ("2.45", "2.46"), ("2.46", "2.50"),
])
def test_same_major_newer_or_equal_runtime_preserves_format_policy(source, target):
    report = evaluate(source, target, source_sha_verified=True)
    assert report["compatible_runtime_minor"] is True
    assert report["npu_placement_verified"] is False


@pytest.mark.parametrize("source,target", [
    ("2.46", "2.45"), ("2.45", "3.0"), ("3.0", "3.1"),
    ("2.45", "2.44"), ("2.50", "2.46"),
])
def test_older_runtime_or_different_major_not_automatically_compatible(source, target):
    report = evaluate(source, target, source_sha_verified=True)
    assert report["compatible_runtime_minor"] is False


@pytest.mark.parametrize("source,target", [
    ("2.45.0", "2.46"), ("2.45", "2.46.0"), ("2.45", "2.46-SECRET"),
    ("2.45", "/private/runtime"), (None, "2.46"),
    (True, "2.46"), ("2.45", True), ("2.45", ""),
])
def test_untrusted_version_metadata_cannot_authorize(source, target):
    report = evaluate(source, target, source_sha_verified=True)
    assert report["compatible_runtime_minor"] is False
    assert "SECRET" not in json.dumps(report)
    assert "/private/" not in json.dumps(report)


@pytest.mark.parametrize("verified", [None, False, 1, "yes"])
def test_unverified_dlc_is_rejected_even_on_compatible_runtime(verified):
    report = evaluate("2.45", "2.46", source_sha_verified=verified)
    assert report["compatible_runtime_minor"] is False
    assert report["vendor_dlc_forward_compatibility_policy_applied"] is False


def good():
    return {
        "packages": {
            "qairt-libs": {"status": "installed", "version": "2.46.0-0ubuntu1"},
            "qairt-dsp-binaries": {
                "status": "installed", "version": "2.46.0-0ubuntu1"
            },
        },
        "libraries": {name: object() for name in readiness.LIBS},
        "skel_present": True,
        "service": {
            "service_mainpid_present": True,
            "geniex_process_count": 1,
            "complete_fast_rpc_fd_scan": True,
            "complete_process_maps": True,
            "fast_rpc_secure_fd_open": False,
        },
        "available_kib": 12 * 1048576,
        "fixture": {"file_identity_verified": True},
        "policy": {"nodes": {
            "cdsp_secure": {
                "character_device": True,
                "runner_effective_read_access": True,
                "runner_effective_write_access": False,
            },
            "dma_heap_system": {
                "character_device": True,
                "runner_effective_read_access": True,
                "runner_effective_write_access": True,
            },
        }},
        "machine": "aarch64",
    }


def test_format_compatibility_never_authorizes_htp_on_live_geniex():
    assessment = readiness.evaluate(**good())
    assert assessment["status"] == "no_go"
    assert assessment["qnn_dlc_forward_compatibility"]["compatible_runtime_minor"] is True
    assert assessment["matching_246_artifact_required_for_dlc_format"] is False
    assert "matching_246_htp_artifact_not_attested" not in assessment["blockers"]
    assert "qnn_dlc_runtime_format_compatibility_unverified" not in assessment["blockers"]
    assert "htp_v75_operator_support_unverified" in assessment["blockers"]
    assert "active_geniex_concurrency_unsafe" in assessment["blockers"]
    assert assessment["npu_inference_verified"] is False


def test_missing_fixture_stays_no_go_even_with_246_runtime():
    values = good()
    values["fixture"] = {"file_identity_verified": False}
    assessment = readiness.evaluate(**values)
    assert "existing_245_fixture_integrity_unverified" in assessment["blockers"]
    assert "qnn_dlc_runtime_format_compatibility_unverified" in assessment["blockers"]
    assert assessment["qnn_dlc_forward_compatibility"]["compatible_runtime_minor"] is False


def test_different_runtime_package_minors_reject_forward_evidence():
    values = good()
    values["packages"]["qairt-dsp-binaries"]["version"] = "2.45.0"
    assessment = readiness.evaluate(**values)
    assert "qnn_dlc_runtime_format_compatibility_unverified" in assessment["blockers"]
    assert assessment["status"] == "no_go"
