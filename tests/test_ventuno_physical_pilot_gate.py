"""No physical devices, models, network, systemd or user audio."""
import copy
import json

import pytest

from scripts import ventuno_physical_pilot_gate as gate


SHA = "a" * 40


def safe_profile():
    return {
        section: {flag: False for flag in flags}
        for section, flags in gate.SAFE_FLAGS.items()
    }


def board_ready(**changes):
    result = {
        "status": "ready-for-separate-consented-dialogue-test",
        "arm64": True,
        "services_active": True,
        "production_voice_disabled": True,
        "usb_capture_and_playback_1_0_accessible": True,
        "ram_gate_passed": True,
        "disk_gate_passed": True,
        "physical_dialogue_attempted": False,
        "microphone_opened": False,
        "speaker_opened": False,
        "model_loaded": False,
        "production_changed": False,
    }
    result.update(changes)
    return result


def test_source_only_reports_no_audio_authorization_or_hardware_claim():
    value = gate.classify(safe_profile(), expected_sha=SHA, actual_sha=SHA)
    assert value["status"] == "source-only-preflight-passed"
    assert value["ready_for_separate_human_consent"] is False
    assert value["recording_authorized"] is False
    assert value["playback_authorized"] is False
    assert value["physical_recording_attempted"] is False
    assert value["npu_tested"] is False
    assert value["model_loaded"] is False


@pytest.mark.parametrize("bad_sha", [
    "", "g" * 40, "a" * 39, "A" * 40, "b" * 40, SHA + "0",
])
def test_wrong_revision_fails_closed(bad_sha):
    value = gate.classify(
        safe_profile(), expected_sha=SHA, actual_sha=bad_sha
    )
    assert value["status"] == "blocked-unpinned-source"


@pytest.mark.parametrize("section,flag", [
    ("voice", "enabled"),
    ("voice", "tts_enabled"),
    ("voice", "handsfree_enabled"),
    ("ventuno", "rpc_write_enabled"),
    ("geniex_supervisor", "restart_enabled"),
    ("selfdev", "enabled"),
    ("selfdev", "promotion_enabled"),
    ("camera", "enabled"),
    ("camera", "stream_enabled"),
    ("location", "enabled"),
    ("trusted_terminals", "enabled"),
    ("trusted_terminals", "auto_execute"),
    ("excel", "write_enabled"),
])
def test_must_keep_every_risky_switch_exactly_disabled(section, flag):
    source = safe_profile()
    source[section][flag] = True
    assert gate.classify(source, expected_sha=SHA, actual_sha=SHA)["status"] == (
        "blocked-unsafe-production-profile"
    )
    source[section][flag] = "false"
    assert gate.classify(source, expected_sha=SHA, actual_sha=SHA)["status"] == (
        "blocked-unsafe-production-profile"
    )


def test_corrupt_and_missing_sections_never_count_as_disabled():
    assert gate.classify(None, expected_sha=SHA, actual_sha=SHA)["status"] == (
        "blocked-unsafe-production-profile"
    )
    candidate = safe_profile()
    candidate["voice"] = None
    assert gate.classify(candidate, expected_sha=SHA, actual_sha=SHA)["status"] == (
        "blocked-unsafe-production-profile"
    )


def test_readonly_board_gate_pass_still_does_not_authorize_microphone():
    value = gate.classify(
        safe_profile(), expected_sha=SHA, actual_sha=SHA,
        board=board_ready(),
    )
    assert value["status"] == "board-readonly-preflight-passed"
    assert value["board_preflight_passed"] is True
    assert value["ready_for_separate_human_consent"] is True
    assert value["recording_authorized"] is False
    assert value["production_changed"] is False


@pytest.mark.parametrize("mutation", [
    {"status": "blocked-usb-reenumerated-or-inaccessible"},
    {"arm64": False},
    {"services_active": False},
    {"production_voice_disabled": False},
    {"usb_capture_and_playback_1_0_accessible": False},
    {"ram_gate_passed": False},
    {"disk_gate_passed": False},
    {"physical_dialogue_attempted": True},
    {"microphone_opened": True},
    {"speaker_opened": True},
    {"model_loaded": True},
    {"production_changed": True},
])
def test_one_failed_live_readiness_flag_blocks_without_audio(mutation):
    result = gate.classify(
        safe_profile(), expected_sha=SHA, actual_sha=SHA,
        board=board_ready(**mutation),
    )
    assert result["status"] == "blocked-read-only-board-preflight"
    assert result["recording_authorized"] is False


def test_profile_reader_rejects_symlink_and_oversized_data(tmp_path):
    parent = tmp_path / "config" / "profiles"
    parent.mkdir(parents=True)
    private = tmp_path / "sentinel.json"
    private.write_text('{"private":"SECRET"}', encoding="utf-8")
    profile = parent / "ventuno_q.json"
    profile.symlink_to(private)
    assert gate._get_source_profile(tmp_path) is None
    profile.unlink()
    profile.write_text("x" * (gate.MAX_PROFILE_BYTES + 1))
    assert gate._get_source_profile(tmp_path) is None
    assert private.read_text(encoding="utf-8") == '{"private":"SECRET"}'


def test_local_source_cli_never_opens_board_or_writes_state(
        tmp_path, monkeypatch, capsys):
    parent = tmp_path / "config" / "profiles"
    parent.mkdir(parents=True)
    contents = json.dumps(safe_profile())
    profile = parent / "ventuno_q.json"
    profile.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(gate, "_get_exact_head", lambda _: SHA)
    output = gate.main([
        "--source-root", str(tmp_path), "--expected-sha", SHA,
    ])
    assert output == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "source-only-preflight-passed"
    assert result["board_preflight_included"] is False
    assert result["recording_authorized"] is False
    assert profile.read_text(encoding="utf-8") == contents


def test_board_flag_only_calls_existing_readonly_inventory(
        tmp_path, monkeypatch, capsys):
    import scripts.ventuno_usb_voice_dialog_readiness as inventory
    folder = tmp_path / "config" / "profiles"
    folder.mkdir(parents=True)
    (folder / "ventuno_q.json").write_text(json.dumps(safe_profile()))
    monkeypatch.setattr(gate, "_get_exact_head", lambda _: SHA)
    calls = []
    monkeypatch.setattr(
        inventory, "inspect",
        lambda: (calls.append("read-only") or board_ready()),
    )
    assert gate.main([
        "--source-root", str(tmp_path), "--expected-sha", SHA,
        "--board-readonly",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert calls == ["read-only"]
    assert result["status"] == "board-readonly-preflight-passed"
    assert result["recording_authorized"] is False


def test_cli_provides_no_audio_consent_switch(tmp_path):
    with pytest.raises(SystemExit) as exc:
        gate.main([
            "--source-root", str(tmp_path), "--expected-sha", SHA,
            "--allow-exactly-one-three-second-recording",
        ])
    assert exc.value.code != 0


def test_sanitized_report_does_not_copy_sensitive_fields():
    candidate = safe_profile()
    candidate["private_token"] = "SECRET_TOKEN"
    board = board_ready(secret_serial="SECRET_SERIAL", transcript="PRIVAT_TEXT")
    result = gate.classify(
        candidate, expected_sha=SHA, actual_sha=SHA, board=board,
    )
    text = json.dumps(result)
    assert "SECRET_TOKEN" not in text
    assert "SECRET_SERIAL" not in text
    assert "PRIVAT_TEXT" not in text
