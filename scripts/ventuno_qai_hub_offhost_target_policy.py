"""Offline policy for official Qualcomm AI Hub VENTUNO compilation target.

The public Arduino documentation names "Arduino VENTUNO Q" (Ubuntu 24.04)
as an actual target, in contrast with Android "QCS8275 (Proxy)".
A cloud compile/link job can use a NAMED device instead of a manually
guessed numeric QNN soc_id. This is ONLY a requirements report: do not
import a client, access tokens, upload models or call any remote API.
"""
from __future__ import annotations

import json

from scripts.qairt_host_toolchain_preflight import (
    EXPECTED_MODEL_SIZE, EXPECTED_SHA256,
)

TARGET = "Arduino VENTUNO Q"
OS = "Ubuntu 24.04"
PROXY = "QCS8275 (Proxy)"
QAIRT_MINOR = "2.46"
MODEL_INPUT = {"input": {"shape": [1, 1, 8, 8], "dtype": "float32"}}
REQUESTS = {
    "qnn_dlc": "hardware_agnostic_qnn_dlc_not_precompiled_htp_context",
    "qnn_context": "soc_specific_npu_context_via_compile_and_link",
}


def evaluate_target(*, device: str = TARGET, runtime: str = "qnn_context",
                    ai_hub_version_246_listed: bool = False,
                    credential_available: bool = False,
                    cloud_model_upload_authorized: bool = False,
                    job_submission_authorized: bool = False) -> dict:
    """No host actions; booleans here are caller claims, not attestations."""
    exact = device == TARGET
    proxy = device == PROXY
    supported_runtime = runtime in REQUESTS
    report = {
        "probe": "ventuno_offhost_qai_hub_target_policy",
        "official_target_documented": True,
        "requested_target_is_exact_board": exact,
        "requested_target_is_proxy": proxy,
        "board_os_documented": OS,
        "cloud_device_listing_queried": False,
        "requested_qairt_minor": QAIRT_MINOR,
        "qairt_246_in_live_service_catalog_verified":
            bool(ai_hub_version_246_listed) if exact else False,
        "requested_runtime": runtime if supported_runtime else "unrecognized",
        "output_artifact_semantics": REQUESTS.get(runtime, "unknown"),
        "input_contract": MODEL_INPUT,
        "source_model_expected_size": EXPECTED_MODEL_SIZE,
        "source_model_expected_sha256": EXPECTED_SHA256,
        "credential_available_claimed": bool(credential_available),
        "explicit_cloud_model_upload_authorized":
            bool(cloud_model_upload_authorized),
        "explicit_job_submission_authorized":
            bool(job_submission_authorized),
        "numeric_soc_id_not_required_for_named_hub_target": exact,
        "sdk_246_manual_context_path_independently_verified": False,
        "cloud_compile_or_link_submitted": False,
        "proprietary_sdk_downloaded": False,
        "model_uploaded": False,
        "npu_inference_or_placement_verified": False,
        "ventuno_accessed_or_modified": False,
        "no_api_tokens_or_personal_data_exported": True,
    }
    if not exact:
        report["status"] = "no_go_exact_arduino_ventuno_q_target_required"
    elif not supported_runtime:
        report["status"] = "no_go_unknown_target_runtime"
    elif not ai_hub_version_246_listed:
        report["status"] = "no_go_246_not_confirmed_in_live_cloud_catalog"
    elif not credential_available:
        report["status"] = "no_go_no_authorized_cloud_credentials"
    elif not cloud_model_upload_authorized:
        report["status"] = "no_go_cloud_upload_not_explicitly_authorized"
    elif not job_submission_authorized:
        report["status"] = "no_go_cloud_job_not_explicitly_authorized"
    else:
        report["status"] = "manual_service_and_model_review_required_no_submission"
    return report


def main() -> int:
    print("MYAI_QAI_HUB_TARGET_POLICY_JSON=" + json.dumps(
        evaluate_target(), sort_keys=True
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
