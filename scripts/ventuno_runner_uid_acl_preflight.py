"""Optional read-only local preflight for future separated VENTUNO GitHub runner.

Default invocation never queries the host. Explicit --local-readonly reads a
FIXED systemd property allowlist, fixed Unix account/group names, and fixed
file metadata only. Never changes users, credentials, services, files or runner
registration. Reports no credentials or raw service command/environment.

POSIX DAC checks cannot prove ACLs, sudo rules, capabilities, namespace mounts
or GitHub runner group policy. This script can NEVER authorize deployment.
"""
from __future__ import annotations

import argparse
import grp
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess

LEGACY_UNIT = "actions.runner.Harrokk-Myai.ventuno-q.service"
UNIT = "myai-ci-runner-isolated.service"
LEGACY_PROPS = ("LoadState", "ActiveState", "UnitFileState")
PROPS = (
    "User", "Group", "SupplementaryGroups", "DynamicUser", "NoNewPrivileges",
    "PrivateDevices", "ProtectHome", "ProtectSystem", "UMask", "StateDirectory",
    "LoadState", "ActiveState",
)
ACCOUNTS = ("arduino", "myai-ci", "myai-runtime", "myai-updater")
SENSITIVE_GROUPS = (
    "sudo", "docker", "audio", "video", "render", "dialout", "input",
    "gpio", "i2c", "adm", "systemd-journal",
)
FIXED_PATHS = (
    "/home/arduino",
    "/home/arduino/MyAI",
    "/home/arduino/MyAI/.venv",
    "/home/arduino/actions-runner",
    "/var/lib/myai-ci-runner",
)
MAX_SYSTEMD_BYTES = 4096


def parse_systemd_properties(raw, *, expected=PROPS):
    """Strict bounded property map; duplicate or extra keys fail closed."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_SYSTEMD_BYTES:
        return None
    try:
        result = {}
        for line in raw.decode("utf-8").splitlines():
            if "=" not in line:
                return None
            key, value = line.split("=", 1)
            if key not in expected or key in result or any(
                ord(ch) < 32 or ord(ch) > 126 for ch in value
            ):
                return None
            result[key] = value
        return result if set(result) == set(expected) else None
    except UnicodeError:
        return None


def _metadata(path, *, stat_fn=os.lstat):
    try:
        details = stat_fn(path)
        return {
            "exists": True,
            "regular_directory": stat.S_ISDIR(details.st_mode),
            "symlink": stat.S_ISLNK(details.st_mode),
            "uid": details.st_uid,
            "gid": details.st_gid,
            "mode": stat.S_IMODE(details.st_mode),
        }
    except (OSError, ValueError):
        return {"exists": False}


def collect_readonly(*, executor=subprocess.run, user_lookup=pwd.getpwnam,
                     group_members=os.getgrouplist, group_lookup=grp.getgrnam,
                     stat_fn=os.lstat):
    """Explicit operator-invoked inspection; no arbitrary paths or shell."""
    snapshot = {"properties": None, "legacy_properties": None, "accounts": {}, "sensitive_gids": [],
                "paths": {}}
    try:
        result = executor(
            ["/usr/bin/systemctl", "show", UNIT, "--no-pager",
             "--property=" + ",".join(PROPS)],
            capture_output=True, check=False, timeout=5,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
        if result.returncode == 0:
            snapshot["properties"] = parse_systemd_properties(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    try:
        old = executor(
            ["/usr/bin/systemctl", "show", LEGACY_UNIT, "--no-pager",
             "--property=" + ",".join(LEGACY_PROPS)],
            capture_output=True, check=False, timeout=5,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
        if old.returncode == 0:
            snapshot["legacy_properties"] = parse_systemd_properties(
                old.stdout, expected=LEGACY_PROPS
            )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    for user in ACCOUNTS:
        try:
            account = user_lookup(user)
            groups = sorted(set(group_members(user, account.pw_gid)))
            snapshot["accounts"][user] = {
                "uid": account.pw_uid, "gid": account.pw_gid, "groups": groups
            }
        except (KeyError, OSError, ValueError):
            snapshot["accounts"][user] = None
    gids = []
    for name in SENSITIVE_GROUPS:
        try:
            gids.append(group_lookup(name).gr_gid)
        except (KeyError, OSError, ValueError):
            pass
    snapshot["sensitive_gids"] = sorted(set(gids))
    for path in FIXED_PATHS:
        snapshot["paths"][path] = _metadata(path, stat_fn=stat_fn)
    return snapshot


def _account_valid(item):
    return (
        isinstance(item, dict) and type(item.get("uid")) is int
        and type(item.get("gid")) is int
        and item["uid"] > 0 and item["gid"] > 0
        and isinstance(item.get("groups"), list)
        and len(item["groups"]) <= 64
        and all(type(g) is int and g >= 0 for g in item["groups"])
        and len(set(item["groups"])) == len(item["groups"])
        and item["gid"] in item["groups"]
    )


def _directory_valid(item):
    return (
        isinstance(item, dict)
        and item.get("exists") is True
        and item.get("regular_directory") is True
        and item.get("symlink") is False
        and all(type(item.get(k)) is int for k in ("uid", "gid", "mode"))
        and item["uid"] >= 0 and item["gid"] >= 0
        and 0 <= item["mode"] <= 0o7777
    )


def evaluate(snapshot):
    """Positive checks are PRELIMINARY only; release flags always fail closed."""
    if not isinstance(snapshot, dict):
        snapshot = {}
    properties = snapshot.get("properties")
    properties_valid = (
        isinstance(properties, dict) and set(properties) == set(PROPS)
        and all(type(v) is str and len(v) <= 128 for v in properties.values())
    )
    legacy = snapshot.get("legacy_properties")
    legacy_valid = (
        isinstance(legacy, dict) and set(legacy) == set(LEGACY_PROPS)
        and all(type(v) is str and len(v) <= 128 for v in legacy.values())
    )
    legacy_quarantined = bool(
        legacy_valid and legacy["ActiveState"] == "inactive"
        and (
            (legacy["LoadState"] == "loaded"
             and legacy["UnitFileState"] in {"disabled", "masked"})
            or (legacy["LoadState"] == "not-found"
                and legacy["UnitFileState"] in {"", "not-found"})
        )
    )
    account_map = snapshot.get("accounts")
    valid_accounts = (
        isinstance(account_map, dict)
        and set(account_map) == set(ACCOUNTS)
        and all(_account_valid(account_map[x]) for x in ACCOUNTS)
    )
    sensitive = snapshot.get("sensitive_gids")
    valid_sensitive = (
        isinstance(sensitive, list) and len(sensitive) <= 64
        and all(type(g) is int and g >= 0 for g in sensitive)
        and len(set(sensitive)) == len(sensitive)
    )
    uid_ok = False
    if valid_accounts and valid_sensitive:
        uid_map = [account_map[name]["uid"] for name in ACCOUNTS]
        ci = account_map["myai-ci"]
        others = [account_map[name] for name in ACCOUNTS if name != "myai-ci"]
        ci_groups = set(ci["groups"])
        uid_ok = (
            len(set(uid_map)) == len(uid_map)
            and ci["gid"] not in set(sensitive)
            and not ci_groups.intersection(sensitive)
            and not any(ci_groups.intersection(user["groups"]) for user in others)
            and ci["groups"] == [ci["gid"]]
        )
    required_props = {
        "User": "myai-ci", "Group": "myai-ci",
        "SupplementaryGroups": "", "DynamicUser": "no",
        "NoNewPrivileges": "yes", "PrivateDevices": "yes",
        "ProtectHome": "yes", "ProtectSystem": "strict",
        "UMask": "0077", "StateDirectory": "myai-ci-runner",
        "LoadState": "loaded",
    }
    unit_ok = properties_valid and all(
        properties[k] == v for k, v in required_props.items()
    ) and properties["ActiveState"] in {"active", "inactive"}
    paths = snapshot.get("paths")
    valid_paths = isinstance(paths, dict) and set(paths) == set(FIXED_PATHS)
    if valid_paths:
        valid_paths = all(_directory_valid(paths[p]) for p in FIXED_PATHS)
    source_dac_denied = False
    runner_state_private = False
    if valid_paths and valid_accounts and uid_ok:
        ci = account_map["myai-ci"]
        ci_groups = set(ci["groups"])
        production = [paths[p] for p in FIXED_PATHS if p != "/var/lib/myai-ci-runner"]
        source_dac_denied = all(
            item["uid"] != ci["uid"]
            and not (item["mode"] & 0o002)
            and not (item["gid"] in ci_groups and item["mode"] & 0o020)
            for item in production
        )
        state_dir = paths["/var/lib/myai-ci-runner"]
        runner_state_private = (
            state_dir["uid"] == ci["uid"]
            and state_dir["gid"] == ci["gid"]
            and state_dir["mode"] == 0o700
        )
    metadata_complete = bool(
        properties_valid and legacy_valid and valid_accounts and valid_sensitive and valid_paths
    )
    candidate_ok = bool(
        metadata_complete and legacy_quarantined and uid_ok and unit_ok and source_dac_denied
        and runner_state_private
    )
    return {
        "status": ("candidate_local_dac_checks_passed_production_blocked"
                   if candidate_ok else "blocked_local_runner_privilege_preflight"),
        "bounded_source_metadata_complete": metadata_complete,
        "distinct_account_and_group_candidate": uid_ok,
        "expected_hardened_unit_properties": bool(unit_ok),
        "legacy_runner_unit_inactive_disabled_candidate": bool(legacy_quarantined),
        "source_directories_not_dac_writable_by_ci": bool(source_dac_denied),
        "runner_state_private_dac_candidate": bool(runner_state_private),
        "preliminary_posix_dac_checks_passed": candidate_ok,
        "posix_acl_and_capabilities_verified": False,
        "sudo_and_nested_group_privileges_verified": False,
        "systemd_mount_namespace_and_real_access_verified": False,
        "runner_credentials_and_secrets_access_verified": False,
        "github_runner_group_and_historical_refs_verified": False,
        "updater_signing_key_acl_verified": False,
        "runner_service_or_files_modified": False,
        "physical_hardware_execution_authorized": False,
        "production_deployment_authorized": False,
        "main_merge_authorized": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-readonly", action="store_true",
                        help="Explicitly inspect fixed local service, UID/group and directory metadata.")
    opts = parser.parse_args(argv)
    result = evaluate(collect_readonly() if opts.local_readonly else None)
    print("MYAI_RUNNER_UID_LOCAL_PREFLIGHT_JSON=" + json.dumps(result, sort_keys=True))
    # A candidate PASS is never complete ACL/credential/GitHub authorization.
    return 0 if result["bounded_source_metadata_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
