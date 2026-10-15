"""Mock-only runner boot policy test; never reboot or touch service."""
from types import SimpleNamespace

from scripts import ventuno_runner_boot_policy_readonly as runner


def raw(load="loaded", active="active", enabled="enabled",
        restart="always"):
    return (
        f"LoadState={load}\nActiveState={active}\n"
        f"UnitFileState={enabled}\nRestart={restart}\n"
    ).encode()


def test_enabled_active_runner_policy_is_not_actual_reboot_proof():
    result = runner.classify(raw())
    assert result["status"] == "boot_autostart_configured_not_reboot_verified"
    assert result["runner_unit_loaded"] is True
    assert result["runner_service_currently_active"] is True
    assert result["runner_persistently_enabled_on_boot"] is True
    assert result["runner_systemd_restart_policy_enabled"] is True
    assert result["runner_reconnect_after_actual_reboot_verified"] is False
    assert result["runner_credentials_or_unit_paths_exported"] is False


def test_disabled_or_runtime_only_enabled_does_not_prove_persistence():
    for state in ("disabled", "enabled-runtime", "static", "masked", "indirect"):
        result = runner.classify(raw(enabled=state))
        assert result["runner_persistently_enabled_on_boot"] is False
        assert result["status"] == "no_go_boot_autostart_not_verified"


def test_runner_restart_no_can_still_autostart_after_boot():
    result = runner.classify(raw(restart="no"))
    assert result["runner_persistently_enabled_on_boot"] is True
    assert result["runner_systemd_restart_policy_enabled"] is False


def test_invalid_or_leaking_systemd_output_is_not_exported():
    for bad in (
        b"SECRET_KEY=/home/arduino/private\n",
        raw() + b"Environment=SECRET_USER_KEY\n",
        raw() + b"Restart=always\n",
        raw().replace(b"UnitFileState=enabled\n", b""),
        b"x" * (runner.MAX_BYTES + 1),
    ):
        result = runner.classify(bad)
        assert result["status"] == "no_go_runner_service_metadata_unverified"
        assert result["runner_credentials_or_unit_paths_exported"] is False


def test_executor_reads_only_exact_unit_properties():
    calls = []
    def fake(args, **kwargs):
        calls.append(args)
        assert args == [
            "systemctl", "show", runner.UNIT, "--no-pager",
            "--property=" + ",".join(runner.PROPS),
        ]
        assert kwargs["timeout"] == 5
        assert kwargs["check"] is False
        assert kwargs["env"]["PATH"] == "/usr/bin:/bin"
        return SimpleNamespace(stdout=raw(), returncode=0)
    assert runner.report(executor=fake)["runner_persistently_enabled_on_boot"] is True
    assert len(calls) == 1


def test_service_absent_no_secret_error_emitted():
    def fail(args, **kw):
        raise RuntimeError("SECRET")  # ignored? unexpected exceptions intentionally bubble
    # The allowed failclosed exceptions are OS-related:
    def os_failure(args, **kw):
        raise OSError("/private/user/network bus missing")
    r = runner.report(executor=os_failure)
    assert r["status"] == "no_go_runner_service_metadata_unverified"
    assert r["runner_service_or_network_modified"] is False
