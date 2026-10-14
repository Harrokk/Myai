"""Pure synthetic target-policy tests, never import or contact QAI Hub."""
import json

from scripts import ventuno_qai_hub_offhost_target_policy as policy


def test_documented_arduino_target_is_ubuntu_not_android_proxy():
    result = policy.evaluate_target()
    assert result["requested_target_is_exact_board"] is True
    assert result["board_os_documented"] == "Ubuntu 24.04"
    assert result["numeric_soc_id_not_required_for_named_hub_target"] is True
    assert result["status"] == "no_go_246_not_confirmed_in_live_cloud_catalog"
    assert result["cloud_device_listing_queried"] is False


def test_proxy_is_not_silently_accepted_as_actual_ventuno():
    proxy = policy.evaluate_target(device="QCS8275 (Proxy)")
    assert proxy["requested_target_is_proxy"] is True
    assert proxy["requested_target_is_exact_board"] is False
    assert proxy["numeric_soc_id_not_required_for_named_hub_target"] is False
    assert proxy["status"] == "no_go_exact_arduino_ventuno_q_target_required"


def test_no_near_match_allowed():
    for device in ("Arduino VENTUNO", "Ventuno Q", "Arduino VENTUNO Q ",
                   "QCS8275", "Qualcomm QCS8275 (Proxy)"):
        r = policy.evaluate_target(device=device)
        assert r["status"] == "no_go_exact_arduino_ventuno_q_target_required"


def test_version_required_from_live_service_catalog():
    r = policy.evaluate_target(
        ai_hub_version_246_listed=False,
        credential_available=True,
        cloud_model_upload_authorized=True,
        job_submission_authorized=True,
    )
    assert r["status"] == "no_go_246_not_confirmed_in_live_cloud_catalog"
    assert r["cloud_compile_or_link_submitted"] is False


def test_credentials_alone_are_insufficient_for_upload():
    r = policy.evaluate_target(
        ai_hub_version_246_listed=True,
        credential_available=True,
    )
    assert r["status"] == "no_go_cloud_upload_not_explicitly_authorized"
    assert r["model_uploaded"] is False


def test_requires_separate_cloud_upload_and_job_permissions():
    r = policy.evaluate_target(
        ai_hub_version_246_listed=True,
        credential_available=True,
        cloud_model_upload_authorized=True,
    )
    assert r["status"] == "no_go_cloud_job_not_explicitly_authorized"
    assert r["cloud_compile_or_link_submitted"] is False


def test_even_all_claims_do_not_trigger_job():
    r = policy.evaluate_target(
        ai_hub_version_246_listed=True,
        credential_available=True,
        cloud_model_upload_authorized=True,
        job_submission_authorized=True,
    )
    assert r["status"] == "manual_service_and_model_review_required_no_submission"
    assert r["cloud_compile_or_link_submitted"] is False
    assert r["model_uploaded"] is False
    assert r["npu_inference_or_placement_verified"] is False


def test_dlc_is_not_conflated_with_soc_specific_context():
    dlc = policy.evaluate_target(runtime="qnn_dlc")
    ctx = policy.evaluate_target(runtime="qnn_context")
    assert dlc["output_artifact_semantics"] == (
        "hardware_agnostic_qnn_dlc_not_precompiled_htp_context"
    )
    assert ctx["output_artifact_semantics"] == (
        "soc_specific_npu_context_via_compile_and_link"
    )
    assert dlc["status"] == "no_go_246_not_confirmed_in_live_cloud_catalog"


def test_unknown_runtime_never_invents_compile_options():
    r = policy.evaluate_target(runtime="htp_binary_untested")
    assert r["status"] == "no_go_unknown_target_runtime"
    assert r["requested_runtime"] == "unrecognized"


def test_public_report_never_contains_tokens_identity_or_private_paths():
    r = policy.evaluate_target()
    encoded = json.dumps(r)
    assert "api_token" not in encoded
    assert "/home/" not in encoded
    assert r["source_model_expected_size"] == 608
    assert len(r["source_model_expected_sha256"]) == 64
    assert r["ventuno_accessed_or_modified"] is False
    assert r["no_api_tokens_or_personal_data_exported"] is True
