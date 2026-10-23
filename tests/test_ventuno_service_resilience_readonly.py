"""All test data synthetic; never contacts systemd, the real board or an LLM."""
from types import SimpleNamespace

from scripts import ventuno_service_resilience_readonly as audit


def raw(*, active="active", restart="on-failure",
        nrestarts="1", start="1000", result="success",
        enabled="enabled"):
    return (
        "LoadState=loaded\n"
        f"ActiveState={active}\n"
        f"UnitFileState={enabled}\n"
        f"Restart={restart}\n"
        f"NRestarts={nrestarts}\n"
        f"ExecMainStartTimestampMonotonic={start}\n"
        f"Result={result}\n"
    )


def fixture(*, start="1000", nr=1, active="active", mem=11.1, free=24):
    return {
        "units": {
            k: audit.unit_properties(raw(
                active=active, nrestarts=str(nr), start=start
            )) for k in audit.UNITS
        },
        "cgroups": {
            k: {"oom": 0, "oom_kill": 0, "high": 0}
            for k in ("myai", "geniex")
        },
        "pressure": {
            k: {"some_avg10": 0.3, "some_total_us": 12345}
            for k in ("cpu", "memory", "io")
        },
        "mem_gib": mem,
        "disk": {"root_free_gib": free, "root_free_inode_percent": 98.6},
    }


def test_valid_service_properties_are_only_allowlisted():
    out = audit.unit_properties(raw())
    assert out["loaded"] and out["active"] and out["enabled_on_boot"]
    assert out["restart_policy"] == "configured"
    assert out["restart_counter"] == 1
    assert out["main_start_us"] == 1000
    assert out["last_result"] == "success"


def test_adversarial_systemctl_properties_fail_closed():
    for bad in (
        raw() + "Environment=SECRET_KEY\n",
        raw() + "NRestarts=9\n",
        raw().replace("Restart=on-failure\n", ""),
        raw().replace("NRestarts=1\n", "NRestarts=-2\n"),
        "SECRET_KEY=/private\n",
        "x" * 4000,
    ):
        x = audit.unit_properties(bad)
        assert x["metadata_valid"] is False or x["restart_counter"] is None
        assert "SECRET" not in repr(x)


def test_systemctl_read_is_exact_no_restart_command():
    calls = []
    def fake(args, **kwargs):
        calls.append(args)
        assert args == [
            "systemctl", "show", "myai-ventuno.service", "--no-pager",
            "--property=" + ",".join(audit.PROPS),
        ]
        assert kwargs["check"] is False and kwargs["timeout"] == 5
        assert kwargs["env"]["PATH"] == "/usr/bin:/bin"
        return SimpleNamespace(returncode=0, stdout=raw().encode())
    assert audit.unit_read("myai", runner=fake)["active"]
    assert len(calls) == 1


def test_stable_snapshot_is_only_short_window_not_reboot_proof():
    out = audit.summarize(fixture(), fixture())
    assert out["status"] == "passive-service-health-observed"
    assert out["services"]["geniex"]["same_main_start_and_no_restart_observed"] is True
    assert out["services"]["geniex"]["restart_count_delta"] == 0
    assert out["reboot_and_auto_reconnect_tested"] is False
    assert out["multi_day_availability_tested"] is False
    assert out["automatic_recovery_tested"] is False
    assert out["service_restarted_or_reloaded"] is False
    assert out["raw_systemd_logs_or_secrets_exported"] is False


def test_restart_count_increase_and_pid_start_change_never_green_in_stability_field():
    out = audit.summarize(fixture(), fixture(nr=2, start="2222"))
    assert out["services"]["geniex"]["same_main_start_and_no_restart_observed"] is False
    assert out["services"]["geniex"]["restart_count_delta"] == 1
    # Active alone is not evidence of recovery from an injected failure.
    assert out["automatic_recovery_tested"] is False


def test_unavailable_metadata_retains_unknown_and_warning():
    out = audit.summarize({}, {})
    assert out["status"] == "passive-health-warning-or-incomplete"
    assert out["services"]["myai"]["same_main_start_and_no_restart_observed"] is None
    assert out["cgroup_memory_events"]["myai"]["oom_kill_delta"] is None
    assert out["host_pressure"]["memory"]["some_avg10_percent"] is None
    assert out["mem_available_gib"] is None


def test_missing_root_free_and_memory_is_not_success():
    assert audit.summarize(fixture(), fixture(mem=None))["status"] != "passive-service-health-observed"
    assert audit.summarize(fixture(), fixture(free=3))["status"] != "passive-service-health-observed"
    assert audit.summarize(fixture(), fixture(active="inactive"))["status"] != "passive-service-health-observed"


def test_psi_parser_accepts_bounded_proc_record(monkeypatch):
    monkeypatch.setattr(
        audit, "bounded_file",
        lambda *args, **kwargs:
        "some avg10=2.50 avg60=1.00 avg300=0.10 total=100\n"
        "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
    )
    assert audit.psi("/proc/pressure/memory") == {
        "some_avg10": 2.5, "some_total_us": 100
    }


def test_no_raw_journal_secret_service_paths_emitted():
    f = fixture()
    f["units"]["myai"]["SECRET_COMMANDLINE"] = "/home/private/secret"
    f["EXTRA_MAC"] = "AA:BB:CC:DD:EE:FF"
    out = audit.summarize(f, f)
    data = repr(out)
    assert "SECRET_COMMANDLINE" not in data
    assert "/home/private" not in data and "AA:BB" not in data
    assert out["microphone_camera_speaker_bluetooth_opened"] is False
    assert out["production_write_performed"] is False


def test_non_monotonic_counter_no_false_delta():
    assert audit.delta(9, 4) is None
    assert audit.delta(4, 9) == 5
    assert audit.delta(None, 9) is None
    assert audit.delta(True, 2) is None
