"""Pure mock contracts for non-invasive full VENTUNO test campaign gate."""
import json

import pytest

from scripts import ventuno_big_test_readiness as mod


def evidence():
    return {
        "voice": {
            "status": "ready-for-separate-consented-dialogue-test",
            "arm64": True, "production_voice_disabled": True,
            "services_active": True,
            "usb_capture_and_playback_1_0_accessible": True,
            "ram_gate_passed": True, "disk_gate_passed": True,
            "microphone_opened": False, "speaker_opened": False,
            "model_loaded": False, "physical_dialogue_attempted": False,
            "production_changed": False,
        },
        "npu": {
            "status": "no_go", "qnn_or_htp_attempted": False,
            "npu_inference_verified": False,
            "npu_operator_placement_measured": False,
            "devices_opened": False,
            "service_or_packages_modified": False,
        },
        "htp_capture": {
            "status": "no_go_direct_htp_profile_not_yet_reproducible",
            "htp_per_op_cycles_measured": False,
            "model_graph_placement_verified": False,
            "new_model_or_qnn_client_started": False,
            "live_service_restart_or_stop_performed": False,
            "device_or_firmware_modified": False,
        },
        "htp_concurrency": {
            "status": "no_go_geniex_active_concurrent_htp_unsafe",
            "htp_inference_attempted": False,
            "fast_rpc_device_open_attempted": False,
            "service_changed": False,
        },
        "recovery": {
            "status": "no_go_dry_run_only",
            "qnn_htp_executed": False,
            "npu_profile_measured": False,
            "service_control_commands_executed": False,
            "service_changes_authorized": False,
            "out_of_band_recovery_verified": False,
        },
    }


def test_complete_metadata_still_no_go_for_actual_npu_and_audio():
    result = mod.classify(evidence())
    assert result["status"] == "metadata-completed-needs-operator-test"
    assert result["all_five_probe_reports_present"] is True
    assert result["safe_to_request_separate_voice_consent"] is True
    assert result["physical_audio_authorized"] is False
    assert result["exclusive_npu_maintenance_authorized"] is False
    assert result["htp_operator_placement_verified"] is False
    assert result["automatic_rollback_armed"] is False
    assert result["human_operator_verification_still_required"] is True


@pytest.mark.parametrize("source,key,untrusted", [
    ("voice", "usb_capture_and_playback_1_0_accessible", False),
    ("voice", "services_active", False),
    ("voice", "model_loaded", True),
    ("voice", "production_changed", True),
    ("npu", "qnn_or_htp_attempted", True),
    ("npu", "devices_opened", True),
    ("npu", "npu_operator_placement_measured", True),
    ("htp_capture", "new_model_or_qnn_client_started", True),
    ("htp_capture", "live_service_restart_or_stop_performed", True),
    ("htp_concurrency", "htp_inference_attempted", True),
    ("recovery", "service_control_commands_executed", True),
    ("recovery", "out_of_band_recovery_verified", True),
])
def test_any_unexpected_hardware_side_effect_fails_closed(
        source, key, untrusted):
    value = evidence()
    value[source][key] = untrusted
    result = mod.classify(value)
    assert result["status"] == "incomplete-or-unsafe-metadata"
    assert result["safe_to_request_separate_voice_consent"] is False


@pytest.mark.parametrize("source", mod.PROBE_NAMES)
def test_missing_report_blocks_full_readiness(source):
    value = evidence()
    value.pop(source)
    result = mod.classify(value)
    assert result["status"] == "incomplete-or-unsafe-metadata"
    assert result["all_five_probe_reports_present"] is False


def test_only_missing_usb_does_not_lie_about_readonly_npu():
    value = evidence()
    value["voice"]["status"] = "blocked-usb-reenumerated-or-inaccessible"
    assert mod.classify(value)["board_usb_voice_metadata_ready"] is False
    assert mod.classify(value)["read_only_npu_metadata_valid"] is True
    assert mod.classify(value)["safe_to_request_separate_voice_consent"] is False


def test_probe_error_is_redacted_and_other_reports_still_run():
    calls = []
    def failure():
        calls.append("failure")
        raise RuntimeError("PRIVATE_PATH_TTS_TOKEN_NEVER_LOG")
    reader = {
        name: (lambda name=name: (calls.append(name) or evidence()[name]))
        for name in mod.PROBE_NAMES
    }
    reader["npu"] = failure
    result = mod.classify(mod.collect(reader))
    assert result["read_only_npu_metadata_valid"] is False
    assert result["status"] == "incomplete-or-unsafe-metadata"
    assert calls == ["voice", "failure", "htp_capture", "htp_concurrency", "recovery"]
    assert "PRIVATE" not in json.dumps(result)


def test_extra_private_fields_never_pass_through_to_output():
    value = evidence()
    value["voice"]["raw_microphone_serial"] = "PRIVATE_USB_ID"
    value["npu"]["raw_fastrpc_descriptor"] = "PRIVATE_FD_INFO"
    value["recovery"]["private_service_value"] = "PRIVATE_SERVICE"
    result = mod.classify(value)
    serialized = json.dumps(result)
    assert "PRIVATE" not in serialized
    assert all(isinstance(v, (bool, str)) for v in result.values())


def test_source_only_cli_does_not_import_or_execute_board_readers(
        monkeypatch, capsys):
    monkeypatch.setattr(
        mod, "existing_readers",
        lambda: pytest.fail("Unexpected board probe"),
    )
    assert mod.main([]) == 0
    output = capsys.readouterr().out
    assert output.startswith("MYAI_BIG_TEST_READINESS_JSON=")
    result = json.loads(output.partition("=")[2])
    assert result["safe_to_request_separate_voice_consent"] is False
    assert result["physical_audio_authorized"] is False


def test_board_flag_invokes_only_injected_mocked_readers(monkeypatch, capsys):
    mocked = {
        name: (lambda name=name: evidence()[name])
        for name in mod.PROBE_NAMES
    }
    monkeypatch.setattr(mod, "existing_readers", lambda: mocked)
    assert mod.main(["--board-metadata-only"]) == 0
    output = capsys.readouterr().out
    result = json.loads(output.partition("=")[2])
    assert result["all_five_probe_reports_present"] is True
    assert result["safe_to_request_separate_voice_consent"] is True
    assert result["exclusive_npu_maintenance_authorized"] is False


def test_no_physical_test_activation_option():
    with pytest.raises(SystemExit):
        mod.main(["--enable-npu-inference"])
    with pytest.raises(SystemExit):
        mod.main(["--record-microphone"])


@pytest.mark.parametrize("source", mod.PROBE_NAMES)
def test_false_or_string_false_cannot_replace_required_literal_bool(source):
    value = evidence()
    key = (
        "arm64" if source == "voice" else
        "npu_inference_verified" if source == "npu" else
        "htp_per_op_cycles_measured" if source == "htp_capture" else
        "htp_inference_attempted" if source == "htp_concurrency" else
        "service_control_commands_executed"
    )
    value[source][key] = "false"
    result = mod.classify(value)
    assert result["status"] == "incomplete-or-unsafe-metadata"
