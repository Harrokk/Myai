"""Offline-only staged root systemd recovery tests. Never start any units."""
import json
import os
from pathlib import Path
import pytest

from scripts import ventuno_htp_system_recovery_staged as gate

BOOT = "12345678-abcd-1234-abcd-123456789abc"
NOW = 1_700_000_100


def lease(**overrides):
    data = {
        "schema": 1,
        "boot_id": BOOT,
        "issued_at": NOW - 10,
        "expires_at": NOW + 120,
        "restore_units": list(gate.RESTORE_ORDER),
        "armed": True,
    }
    data.update(overrides)
    return data


def test_valid_short_lived_lease_is_only_gate_not_execution():
    assert gate.inspect_lease(lease(), BOOT, NOW) == "lease_valid_for_this_boot_only"


@pytest.mark.parametrize("invalid,expected", [
    ({"schema": 2}, "no_go_invalid_lease_schema"),
    ({"armed": False}, "no_go_lease_not_armed"),
    ({"boot_id": "attacker-other-boot"}, "no_go_boot_identity_changed"),
    ({"restore_units": ["myai-geniex.service"]}, "no_go_unapproved_service_target"),
    ({"restore_units": ["actions.runner.Harrokk-Myai.ventuno-q.service"]},
     "no_go_unapproved_service_target"),
    ({"restore_units": list(reversed(gate.RESTORE_ORDER))},
     "no_go_unapproved_service_target"),
    ({"issued_at": NOW + 3}, "no_go_stale_or_future_lease"),
    ({"expires_at": NOW - 1}, "no_go_stale_or_future_lease"),
    ({"expires_at": NOW + 999}, "no_go_stale_or_future_lease"),
    ({"issued_at": "secret"}, "no_go_invalid_lease_clock"),
])
def test_invalid_lease_rejected(invalid, expected):
    assert gate.inspect_lease(lease(**invalid), BOOT, NOW) == expected


def test_extra_lease_field_is_not_allowed():
    assert gate.inspect_lease(lease(private_commands="systemctl stop ..."),
                              BOOT, NOW) == "no_go_invalid_lease_keys"


def test_wrong_boot_or_missing_lease_must_not_call_systemctl():
    attempts = []
    for data in (None, lease(boot_id="00000000-0000-0000-0000-000000000000")):
        report = gate.restore_under_validated_lease(
            lease=data, boot_id=BOOT, now=NOW, current_is_root=True,
            lease_identity_valid=True,
            command=lambda cmd: attempts.append(cmd),
        )
        assert report["status"].startswith("no_go")
        assert report["service_start_attempts"] == 0
    assert attempts == []


@pytest.mark.parametrize("root,identity", [
    (False, False), (True, False), (False, True), (None, True),
])
def test_privilege_or_root_owned_file_missing_is_no_go(root, identity):
    calls = []
    report = gate.restore_under_validated_lease(
        lease=lease(), boot_id=BOOT, now=NOW,
        current_is_root=root, lease_identity_valid=identity,
        command=lambda cmd: calls.append(cmd),
    )
    assert report["status"] == "no_go_root_owned_lease_not_attested"
    assert not calls
    assert report["runner_service_touched"] is False


def test_only_start_missing_original_services_never_restart(tmp_path):
    current = {
        "myai-geniex.service": False,
        "myai-ventuno.service": False,
        "myai-geniex-watchdog.service": True,
    }
    requests = []
    def mocked_command(args):
        args = tuple(args)
        requests.append(args)
        if args[:3] == ("systemctl", "is-active", "--quiet"):
            return current[args[3]]
        assert args[:2] == ("systemctl", "start")
        name = args[2]
        assert name in gate.RESTORE_ORDER
        current[name] = True
        return True
    report = gate.restore_under_validated_lease(
        lease=lease(), boot_id=BOOT, now=NOW, command=mocked_command,
        current_is_root=True, lease_identity_valid=True,
    )
    assert report["status"] == "restoration_verified_on_original_three_services"
    assert report["service_start_attempts"] == 2
    assert report["all_required_services_active_afterward"] is True
    assert [x[2] for x in requests if x[1] == "start"] == list(gate.RESTORE_ORDER[:2])
    assert not any("restart" in x or "stop" in x for x in requests)
    assert not any("actions.runner." in y for x in requests for y in x)
    assert report["runner_service_touched"] is False
    assert report["any_service_stopped_or_restarted"] is False


def test_partial_start_failure_attempts_rest_of_restore_and_never_claims_success():
    active = {x: False for x in gate.RESTORE_ORDER}
    commands = []
    def runner(cmd):
        cmd = tuple(cmd)
        commands.append(cmd)
        if cmd[1] == "is-active":
            return active[cmd[-1]]
        if cmd[-1] != "myai-geniex.service":
            active[cmd[-1]] = True
            return True
        return False
    report = gate.restore_under_validated_lease(
        lease=lease(), boot_id=BOOT, now=NOW, command=runner,
        current_is_root=True, lease_identity_valid=True,
    )
    assert report["status"] == "recovery_incomplete_manual_intervention_required"
    assert report["all_required_services_active_afterward"] is False
    assert report["service_start_attempts"] == 3
    assert len([x for x in commands if x[1] == "start"]) == 3


def test_no_private_boot_identity_or_lease_exported():
    report = gate.restore_under_validated_lease(
        lease=lease(), boot_id=BOOT, now=NOW,
        command=lambda _: True, current_is_root=True,
        lease_identity_valid=True,
    )
    encoded = json.dumps(report)
    assert BOOT not in encoded
    assert "issued_at" not in encoded
    assert "expires_at" not in encoded
    assert report["lease_or_boot_identity_exported"] is False


def test_actual_run_without_root_refuses_without_reading_lease(monkeypatch):
    monkeypatch.setattr(gate.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(gate, "read_root_lease", lambda: pytest.fail(
        "non-root code cannot read a privileged lease"
    ))
    result = gate.run_root_handler()
    assert result["status"] == "no_go_root_owned_lease_not_attested"
    assert result["service_start_attempts"] == 0


def test_systemd_templates_are_unenabled_and_lease_guarded():
    root = Path(__file__).resolve().parents[1]
    folder = root / "deploy" / "systemd"
    service = (folder / "myai-htp-staged-restore.service").read_text()
    timer = (folder / "myai-htp-staged-restore.timer").read_text()
    assert "ConditionPathExists=/run/myai-htp-restore/lease.json" in service
    assert "ExecStart=/usr/bin/python3 -I " in service
    assert "ventuno_htp_system_recovery_staged.py --restore" in service
    assert "NoNewPrivileges=yes" in service
    assert "ProtectHome=yes" in service
    assert "User=root" in service
    assert "OnActiveSec=90s" in timer
    assert "AccuracySec=1s" in timer
    assert "Unit=myai-htp-staged-restore.service" in timer
    assert "WantedBy=" not in service + timer
    assert "ExecStop=" not in service + timer
    assert "myai-geniex.service" not in service + timer
    assert "actions.runner." not in service + timer


def test_mock_handler_command_runner_no_shell_and_bounded_timeout(monkeypatch):
    called = []
    def fake(args, **kw):
        called.append((args, kw))
        return type("Result", (), {"returncode": 0})()
    monkeypatch.setattr(gate.subprocess, "run", fake)
    assert gate.safe_command(("systemctl", "is-active", "--quiet",
                              "myai-geniex.service")) is True
    args, kw = called[0]
    assert kw["timeout"] == 12
    assert kw["check"] is False
    assert kw["env"]["PATH"] == "/usr/bin:/bin"
    assert "shell" not in kw
