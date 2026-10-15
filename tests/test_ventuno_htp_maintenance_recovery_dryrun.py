"""Synthetic-only dry-run systemd maintenance and rollback fault injections."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from scripts import ventuno_htp_maintenance_recovery_dryrun as gate


def unit_bytes(*, state="active", sub="running", restart="on-failure",
               canstart="yes", canstop="yes", requires="",
               partof="", binds="", triggered="", onfailure="", wants=""):
    data = {
        "LoadState": "loaded",
        "ActiveState": state,
        "SubState": sub,
        "Restart": restart,
        "CanStop": canstop,
        "CanStart": canstart,
        "PartOf": partof,
        "BindsTo": binds,
        "TriggeredBy": triggered,
        "OnFailure": onfailure,
        "Requires": requires,
        "Wants": wants,
    }
    return "".join(f"{key}={value}\n" for key, value in data.items()).encode()


def good():
    return {
        key: gate.parse_unit(unit_bytes(
            requires="myai-geniex.service" if key == "myai-ventuno.service"
            else "",
            wants="network-online.target",
        ))
        for key in gate.OBSERVED
    }


def supervisor(*, enabled=True, restart=False):
    return gate.classify_supervisor(
        json.dumps({"geniex_supervisor": {
            "enabled": enabled, "restart_enabled": restart,
            "private_token": "NEVER_EXPORT",
        }}).encode()
    )


def test_healthy_baseline_still_cannot_stop_any_service():
    r = gate.decide(good(), supervisor())
    assert r["status"] == "no_go_dry_run_only"
    assert r["observed_units_count"] == 4
    assert r["required_unit_states_all_active"] is True
    assert r["restart_enabled_by_myai_supervisor"] is False
    assert r["stop_order_for_review_only"] == list(gate.STOP_ORDER)
    assert r["restore_order_for_review_only"] == list(gate.RESTORE_ORDER)
    assert r["runner_must_never_be_stopped"] is True
    assert r["service_changes_authorized"] is False
    assert r["automatic_rollback_armed"] is False
    assert r["out_of_band_recovery_verified"] is False
    assert r["service_control_commands_executed"] is False
    assert r["npu_profile_measured"] is False
    assert "NEVER_EXPORT" not in json.dumps(r)
    assert "vendor_approved_exclusive_maintenance_and_operator_authorization_missing" in r["blockers"]


@pytest.mark.parametrize("name", list(gate.OBSERVED))
def test_any_missing_live_unit_is_no_go(name):
    state = good()
    state[name] = None
    report = gate.decide(state, supervisor())
    assert report["status"] == "no_go_dry_run_only"
    assert "installed_unit_metadata_unavailable" in report["blockers"]
    assert report["service_control_commands_executed"] is False


@pytest.mark.parametrize("param,value,blocker", [
    ("state", "inactive", "required_unit_not_running"),
    ("state", "failed", "required_unit_not_running"),
    ("restart", "always", "unexpected_service_restart_policy"),
    ("canstart", "no", "unit_not_safely_controllable"),
    ("canstop", "no", "unit_not_safely_controllable"),
    ("partof", "myai-ventuno.target", "service_dependency_or_activation_unverified"),
    ("binds", "myai-geniex.service", "service_dependency_or_activation_unverified"),
    ("triggered", "unreviewed.timer", "service_dependency_or_activation_unverified"),
    ("onfailure", "alert.service", "service_dependency_or_activation_unverified"),
    ("requires", "unreviewed.service", "service_dependency_or_activation_unverified"),
    ("wants", "network-online.target unexpected.unit", "service_dependency_or_activation_unverified"),
])
def test_systemd_unsafe_state_refused(param, value, blocker):
    fields = {
        "state": "active", "sub": "running", "restart": "on-failure",
        "canstart": "yes", "canstop": "yes", "requires": "",
        "partof": "", "binds": "", "triggered": "", "onfailure": "",
        "wants": "",
    }
    fields[param] = value
    units = good()
    units["myai-geniex.service"] = gate.parse_unit(unit_bytes(**fields))
    report = gate.decide(units, supervisor())
    assert blocker in report["blockers"]
    assert report["service_changes_authorized"] is False


def test_non_running_substate_is_not_accepted_for_active_unit():
    u = good()
    u[gate.UNITS[0]] = gate.parse_unit(unit_bytes(sub="exited"))
    assert "required_unit_not_running" in gate.decide(u, supervisor())["blockers"]


@pytest.mark.parametrize("fixture", [
    b"",
    b"SECRET_RAW_DATA",
    unit_bytes() + b"ActiveState=active\n",
    unit_bytes() + b"OneUnexpectedField=sensitive\n",
    unit_bytes().replace(b"LoadState=loaded\n", b""),
    b"x" * (gate.MAX_SYSTEMCTL_BYTES + 1),
    unit_bytes().replace(b"CanStart=yes", b"CanStart=maybe"),
    unit_bytes().replace(b"LoadState=loaded", b"LoadState=masked"),
    unit_bytes().replace(b"ActiveState=active", b"ActiveState=deactivating"),
])
def test_untrusted_systemd_status_fails_closed(fixture):
    assert gate.parse_unit(fixture) is None


def test_systemd_inspection_exact_allowed_unit_and_no_service_action():
    calls = []
    def fake(args, **kw):
        calls.append(args)
        assert args[:3] == ["systemctl", "show", gate.UNITS[0]]
        assert args[-1].startswith("--property=")
        assert kw["timeout"] == 5
        assert kw["check"] is False
        assert kw["env"] == {"LC_ALL": "C", "PATH": "/usr/bin:/bin"}
        return SimpleNamespace(returncode=0, stdout=unit_bytes())
    r = gate.read_unit(gate.UNITS[0], executor=fake)
    assert r["state"] == "active"
    assert calls and calls[0][1] == "show"
    assert gate.read_unit("anything.service", executor=fake) is None
    assert len(calls) == 1


def test_nonzero_systemctl_and_oversized_result_refused():
    assert gate.read_unit(gate.UNITS[0], executor=lambda *a, **kw:
                          SimpleNamespace(returncode=1, stdout=b"SECRET")) is None
    assert gate.read_unit(gate.UNITS[0], executor=lambda *a, **kw:
                          SimpleNamespace(returncode=0, stdout=b"x"*9000)) is None


@pytest.mark.parametrize("value", [None, b"", b"not json", b"{}", b"[]",
                                  b'{"geniex_supervisor":null}',
                                  b"x" * (gate.MAX_PROFILE_BYTES + 1)])
def test_corrupt_or_missing_profile_refuses_maintenance(value):
    p = gate.classify_supervisor(value)
    assert p["installed_profile_parseable"] is False
    assert "installed_supervisor_config_unverified" in gate.decide(
        good(), p)["blockers"]


def test_watchdog_auto_restart_fails_closed_and_leaks_no_config():
    policy = supervisor(restart=True)
    r = gate.decide(good(), policy)
    assert r["restart_enabled_by_myai_supervisor"] is True
    assert "watchdog_restart_policy_not_confirmed_disabled" in r["blockers"]
    assert "NEVER_EXPORT" not in json.dumps(r)


def test_watchdog_disabled_is_allowed_as_metadata_not_stop_permission():
    r = gate.decide(good(), supervisor(enabled=False, restart=True))
    assert r["restart_enabled_by_myai_supervisor"] is False
    assert r["service_changes_authorized"] is False


def test_real_profile_reader_never_uses_symlink(tmp_path):
    p = tmp_path / "profile"
    p.symlink_to(tmp_path / "target")
    assert gate.read_installed_supervisor(p)["installed_profile_parseable"] is False


def test_readonly_report_combines_injected_metadata(monkeypatch):
    monkeypatch.setattr(gate, "read_unit", lambda name: good()[name])
    monkeypatch.setattr(gate, "read_installed_supervisor", supervisor)
    report = gate.report()
    assert report["status"] == "no_go_dry_run_only"
    assert report["required_unit_states_all_active"]
    assert not report["npu_profile_measured"]


@pytest.mark.parametrize("failure", [
    *("stop:" + name for name in gate.STOP_ORDER),
    "profile:synthetic_fixture_only",
    *("restore:" + name for name in gate.RESTORE_ORDER),
    None,
])
def test_fault_injection_attempts_every_restoration_action(failure):
    result = gate.simulate_recovery(fail_at=failure)
    for name in gate.RESTORE_ORDER:
        assert "attempt:restore:" + name in result["events"]
    assert result["all_restore_actions_attempted"] is True
    assert result["restored_services_verified_in_real_system"] is False
    assert result["out_of_band_rollback_armed"] is False
    assert result["service_control_commands_executed"] is False
    assert result["npu_profile_measured"] is False
    assert "verify:geniex_model_catalog" in result["events"]
    assert "verify:myai_runtime_heartbeat" in result["events"]


def test_emulator_profiles_synthetic_only_and_never_calls_systemctl(monkeypatch):
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **kw:
                        pytest.fail("simulation cannot spawn systemctl"))
    res = gate.simulate_recovery(fail_at="profile:synthetic_fixture_only")
    assert res["status"] == "simulated_interrupted_and_restored"
    assert res["simulated_profile_is_not_actual_htp"] is True


def test_simulated_restore_failure_is_explicit_not_false_success():
    result = gate.simulate_recovery(
        fail_at="restore:myai-geniex.service"
    )
    assert result["status"] == "simulated_recovery_failure"
    assert "injected_recovery_failure" in result["events"]


def test_dependency_trouble_exposes_only_fixed_unit_and_property_labels():
    units = good()
    units["myai-geniex-watchdog.service"] = gate.parse_unit(
        unit_bytes(partof="HIDDEN_SECRET.private.service",
                   triggered="HIDDEN_ACTIVATION.timer"))
    units[gate.RUNNER_UNIT] = gate.parse_unit(
        unit_bytes(wants="HIDDEN_INTEGRATION.target"))
    report = gate.decide(units, supervisor())
    assert report["dependency_review_needed"] == {
        "myai-geniex-watchdog.service": ["PartOf", "TriggeredBy"],
        gate.RUNNER_UNIT: ["Wants"],
    }
    encoded = json.dumps(report)
    assert "HIDDEN_SECRET" not in encoded
    assert "HIDDEN_ACTIVATION" not in encoded
    assert "HIDDEN_INTEGRATION" not in encoded
    assert report["service_control_commands_executed"] is False


def test_normal_known_dependencies_need_no_review():
    report = gate.decide(good(), supervisor())
    assert report["dependency_review_needed"] == {}
