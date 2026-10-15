"""Fail-closed, read-only maintenance + recovery rehearsal for VENTUNO HTP.

DOES NOT stop, start, restart, kill, mask, edit or install any service.
It reads only a bounded installed systemd property set and the 2 booleans
needed from the installed GenieX supervisor profile. All service-manager
actions below are STRING EVENTS inside an offline simulator: there is NO
execution adapter for real operations and no elevated-permission path.

A true exclusive QNN-HTP maintenance trial requires a separate reviewed
operational decision, a watchdog/runner-independent timed recovery design,
an approved HTP command with known-good native inputs and profile reader,
and recovery verification. This module cannot authorize that trial.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

UNITS = (
    "myai-geniex.service",
    "myai-ventuno.service",
    "myai-geniex-watchdog.service",
)
RUNNER_UNIT = "actions.runner.Harrokk-Myai.ventuno-q.service"
OBSERVED = UNITS + (RUNNER_UNIT,)
STOP_ORDER = (
    "myai-geniex-watchdog.service",
    "myai-ventuno.service",
    "myai-geniex.service",
)
RESTORE_ORDER = (
    "myai-geniex.service",
    "myai-ventuno.service",
    "myai-geniex-watchdog.service",
)
# Installed file path is read only; never export any profile settings,
# environment values, model IDs, error messages, credentials or file paths.
INSTALLED_PROFILE = Path("/home/arduino/MyAI/config/profiles/ventuno_q.json")
MAX_PROFILE_BYTES = 65536
MAX_SYSTEMCTL_BYTES = 8192
PROPERTIES = (
    "LoadState", "ActiveState", "SubState", "Restart",
    "CanStop", "CanStart", "PartOf", "BindsTo", "TriggeredBy",
    "OnFailure", "Requires", "Wants",
)
# Normal implicit systemd requirements are safe to RECOGNIZE, not a
# license to stop system targets. Unexpected requirements remain NO-GO.
BUILTIN_BASE = frozenset({
    "sysinit.target", "basic.target", "system.slice", "-.mount",
})
KNOWN_DEPENDENCIES = frozenset(
    (*UNITS, "network-online.target", *BUILTIN_BASE)
)
SAFE_RESTART_SETTINGS = frozenset({"no", "on-failure"})
ACTIVE = "active"


def parse_unit(raw):
    """Accept one unique, complete set of known systemd properties."""
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_SYSTEMCTL_BYTES:
        return None
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError:
        return None
    values = {}
    for line in lines:
        key, sep, value = line.partition("=")
        if not sep or key not in PROPERTIES or key in values:
            return None
        if len(value) > 1024:
            return None
        values[key] = value
    if set(values) != set(PROPERTIES):
        return None
    if values["LoadState"] != "loaded" or values["ActiveState"] not in {
        "active", "inactive", "failed",
    }:
        return None
    if values["CanStart"] not in {"yes", "no"} or values["CanStop"] not in {
        "yes", "no",
    }:
        return None
    # Never export raw dependency names. Reject unknown dependencies
    # instead of assuming they are safe to manipulate in maintenance.
    dependencies = {}
    core_requirements = []
    unknown_requires = 0
    for key in ("PartOf", "BindsTo", "TriggeredBy", "OnFailure", "Requires", "Wants"):
        tokens = values[key].split() if values[key] else []
        if key == "Requires":
            core_requirements = sorted(
                name for name in BUILTIN_BASE if name in tokens
            )
            unknown_requires = sum(
                name not in KNOWN_DEPENDENCIES for name in tokens
            )
        dependencies[key] = (
            "known" if set(tokens) <= KNOWN_DEPENDENCIES else "unknown"
        )
        if key in {"PartOf", "BindsTo", "TriggeredBy", "OnFailure"} and tokens:
            dependencies[key] = "nonempty"
    return {
        "state": values["ActiveState"],
        "service_appears_running": (
            values["ActiveState"] == "active"
            and values["SubState"] == "running"
        ),
        "restart_policy": (
            values["Restart"] if values["Restart"] in SAFE_RESTART_SETTINGS
            else "unexpected"
        ),
        "can_start": values["CanStart"] == "yes",
        "can_stop": values["CanStop"] == "yes",
        "dependencies": dependencies,
        "standard_base_requirements_observed": core_requirements,
        "unrecognized_requirements_count": min(unknown_requires, 128),
    }


def read_unit(unit, executor=subprocess.run):
    if unit not in OBSERVED:
        return None
    args = [
        "systemctl", "show", unit, "--no-pager",
        "--property=" + ",".join(PROPERTIES),
    ]
    try:
        result = executor(
            args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=5, check=False, env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
        if result.returncode != 0:
            return None
        return parse_unit(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def classify_supervisor(profile_bytes):
    """Do not expose anything except two exact boolean config fields."""
    baseline = {
        "installed_profile_parseable": False,
        "supervisor_enabled": None,
        "automatic_geniex_restart_enabled": None,
    }
    if (type(profile_bytes) is not bytes or
            not 1 <= len(profile_bytes) <= MAX_PROFILE_BYTES):
        return baseline
    try:
        data = json.loads(profile_bytes)
    except (ValueError, UnicodeError, TypeError):
        return baseline
    if not isinstance(data, dict):
        return baseline
    sup = data.get("geniex_supervisor")
    if not isinstance(sup, dict):
        return baseline
    enabled, restart = sup.get("enabled"), sup.get("restart_enabled")
    if type(enabled) is not bool or type(restart) is not bool:
        return baseline
    return {
        "installed_profile_parseable": True,
        "supervisor_enabled": enabled,
        "automatic_geniex_restart_enabled": enabled and restart,
    }


def read_installed_supervisor(path=INSTALLED_PROFILE):
    try:
        if path.is_symlink() or not path.is_file():
            return classify_supervisor(None)
        with path.open("rb") as handle:
            raw = handle.read(MAX_PROFILE_BYTES + 1)
    except OSError:
        return classify_supervisor(None)
    return classify_supervisor(raw)


def decide(units, supervisor):
    """Pure policy: even a clean baseline NEVER grants permission to stop."""
    units = units if isinstance(units, dict) else {}
    supervisor = supervisor if isinstance(supervisor, dict) else {}
    reasons = []
    # Unit identifiers are a fixed allowlist, not device- or user-derived.
    # Reveal which dependency *category* needs review, never raw targets.
    dependency_review = {}
    for name in OBSERVED:
        row = units.get(name)
        if not isinstance(row, dict):
            reasons.append("installed_unit_metadata_unavailable")
            break
        if row.get("state") != "active" or row.get("service_appears_running") is not True:
            reasons.append("required_unit_not_running")
            break
        if row.get("restart_policy") not in SAFE_RESTART_SETTINGS:
            reasons.append("unexpected_service_restart_policy")
            break
        if row.get("can_stop") is not True or row.get("can_start") is not True:
            reasons.append("unit_not_safely_controllable")
            break
        deps = row.get("dependencies")
        relevant = (
            "PartOf", "BindsTo", "TriggeredBy", "OnFailure",
            "Requires", "Wants",
        )
        review = [
            key for key in relevant
            if not isinstance(deps, dict) or deps.get(key) != "known"
        ]
        if review:
            dependency_review[name] = review
            reasons.append("service_dependency_or_activation_unverified")
        # Do not break here: safe, bounded reporting should cover all
        # four units to identify the real source of the false-positive.
        # None of these observations grants actual stop permission.
    if supervisor.get("installed_profile_parseable") is not True:
        reasons.append("installed_supervisor_config_unverified")
    if supervisor.get("automatic_geniex_restart_enabled") is not False:
        reasons.append("watchdog_restart_policy_not_confirmed_disabled")
    # Plan is safe to DISCUSS even when no active operations can occur.
    reasons.extend((
        "independent_out_of_band_recovery_not_armed_or_attested",
        "executable_tiny_htp_profile_and_native_output_not_validated",
        "vendor_approved_exclusive_maintenance_and_operator_authorization_missing",
    ))
    return {
        "status": "no_go_dry_run_only",
        "blockers": sorted(set(reasons)),
        "observed_units_count": sum(
            isinstance(units.get(n), dict) for n in OBSERVED
        ),
        "dependency_review_needed": dependency_review,
        "baseline_base_requirements_observed": {
            name: units[name].get("standard_base_requirements_observed", [])
            for name in OBSERVED if isinstance(units.get(name), dict)
        },
        "baseline_unrecognized_requirements_count": {
            name: units[name].get("unrecognized_requirements_count", 0)
            for name in OBSERVED if isinstance(units.get(name), dict)
        },
        "required_unit_states_all_active": all(
            isinstance(units.get(n), dict)
            and units[n].get("service_appears_running") is True
            for n in OBSERVED
        ),
        "restart_enabled_by_myai_supervisor": supervisor.get(
            "automatic_geniex_restart_enabled"
        ) if type(supervisor.get("automatic_geniex_restart_enabled")) is bool else None,
        "requires_runner_online_during_preflight": True,
        "runner_must_never_be_stopped": True,
        "stop_order_for_review_only": list(STOP_ORDER),
        "restore_order_for_review_only": list(RESTORE_ORDER),
        "service_changes_authorized": False,
        "automatic_rollback_armed": False,
        "out_of_band_recovery_verified": False,
        "qnn_htp_executed": False,
        "npu_profile_measured": False,
        "service_control_commands_executed": False,
        "private_unit_or_profile_values_exported": False,
    }


def simulate_recovery(*, fail_at=None):
    """Pure event emulator, NO systemctl or real file/system access.

    Inject failure at any of the 3 stop, 1 profile or 3 restore steps.
    The recovery phase always tries to restore every initially-active
    unit in fixed dependency order; a failed restore is surfaced rather
    than claiming successful rollback.
    """
    steps = [
        *("stop:" + name for name in STOP_ORDER),
        "profile:synthetic_fixture_only",
    ]
    events = []
    failure = False
    for step in steps:
        events.append("attempt:" + step)
        if step == fail_at:
            events.append("injected_failure")
            failure = True
            break
        events.append("simulation_only_completed")
    # Restoring all three original active services is idempotent in the
    # emulator even when the fault happened before any simulated stop.
    recovery_errors = False
    for name in RESTORE_ORDER:
        event = "restore:" + name
        events.append("attempt:" + event)
        if event == fail_at:
            events.append("injected_recovery_failure")
            recovery_errors = True
        else:
            events.append("simulation_only_completed")
    events.append("verify:geniex_model_catalog")
    events.append("verify:myai_runtime_heartbeat")
    events.append("verify:watchdog_original_state")
    return {
        "probe": "ventuno_htp_maintenance_recovery_simulation",
        "status": (
            "simulated_recovery_failure" if recovery_errors else
            "simulated_interrupted_and_restored" if failure else
            "simulated_recovered_after_trial"
        ),
        "events": events,
        "all_restore_actions_attempted": True,
        "restored_services_verified_in_real_system": False,
        "simulated_profile_is_not_actual_htp": True,
        "service_control_commands_executed": False,
        "npu_profile_measured": False,
        "out_of_band_rollback_armed": False,
    }


def report():
    status = {
        name: read_unit(name)
        for name in OBSERVED
    }
    return decide(status, read_installed_supervisor())


if __name__ == "__main__":
    try:
        value = report()
    except Exception:
        value = {
            "status": "no_go_metadata_exception",
            "service_control_commands_executed": False,
            "npu_profile_measured": False,
            "automatic_rollback_armed": False,
        }
    print("MYAI_HTP_MAINTENANCE_DRYRUN_JSON=" + json.dumps(
        value, sort_keys=True,
    ))
