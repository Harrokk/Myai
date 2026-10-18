"""Mock-only CI runner boundary preflight; no host probing or service changes."""
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from scripts import ventuno_runner_uid_acl_preflight as gate


def good_systemd_bytes():
    fields = dict.fromkeys(gate.PROPS, "")
    fields.update({
        "User": "myai-ci", "Group": "myai-ci",
        "SupplementaryGroups": "", "DynamicUser": "no",
        "NoNewPrivileges": "yes", "PrivateDevices": "yes",
        "ProtectHome": "yes", "ProtectSystem": "strict",
        "UMask": "0077", "StateDirectory": "myai-ci-runner",
        "LoadState": "loaded", "ActiveState": "inactive",
    })
    return "".join(f"{key}={value}\n" for key, value in fields.items()).encode()


def sample():
    accounts = {
        "arduino": {"uid": 1000, "gid": 1000, "groups": [1000]},
        "myai-ci": {"uid": 23003, "gid": 23003, "groups": [23003]},
        "myai-runtime": {"uid": 23002, "gid": 23002, "groups": [23002]},
        "myai-updater": {"uid": 23001, "gid": 23001, "groups": [23001]},
    }
    paths = {}
    for p in gate.FIXED_PATHS:
        if p == "/var/lib/myai-ci-runner":
            paths[p] = dict(exists=True, regular_directory=True, symlink=False,
                            uid=23003, gid=23003, mode=0o700)
        else:
            paths[p] = dict(exists=True, regular_directory=True, symlink=False,
                            uid=1000, gid=1000, mode=0o750)
    return {
        "properties": gate.parse_systemd_properties(good_systemd_bytes()),
        "accounts": accounts, "sensitive_gids": [4, 27, 29, 44, 999],
        "paths": paths,
    }


def test_complete_synthetic_fixture_only_approves_posix_preliminary_flags():
    result = gate.evaluate(sample())
    assert result["status"] == "candidate_local_dac_checks_passed_production_blocked"
    assert result["bounded_source_metadata_complete"] is True
    assert result["distinct_account_and_group_candidate"] is True
    assert result["source_directories_not_dac_writable_by_ci"] is True
    assert result["runner_state_private_dac_candidate"] is True
    assert result["preliminary_posix_dac_checks_passed"] is True
    assert result["posix_acl_and_capabilities_verified"] is False
    assert result["runner_credentials_and_secrets_access_verified"] is False
    assert result["github_runner_group_and_historical_refs_verified"] is False
    assert result["production_deployment_authorized"] is False
    assert result["main_merge_authorized"] is False
    assert result["runner_service_or_files_modified"] is False


@pytest.mark.parametrize("property,value", [
    ("User", "arduino"), ("User", "root"), ("Group", "arduino"),
    ("SupplementaryGroups", "sudo"), ("DynamicUser", "yes"),
    ("NoNewPrivileges", "no"), ("PrivateDevices", "no"),
    ("ProtectHome", "read-only"), ("ProtectSystem", "full"),
    ("UMask", "0022"), ("StateDirectory", "MyAI"),
    ("LoadState", "not-found"), ("ActiveState", "failed"),
])
def test_unsafe_systemd_properties_fail_closed(property, value):
    snapshot = sample()
    snapshot["properties"][property] = value
    result = gate.evaluate(snapshot)
    assert result["expected_hardened_unit_properties"] is False
    assert result["preliminary_posix_dac_checks_passed"] is False
    assert result["production_deployment_authorized"] is False


@pytest.mark.parametrize("bad", [
    b"", b"SECRET=private\n" + good_systemd_bytes(),
    good_systemd_bytes() + b"User=root\n",
    good_systemd_bytes().replace(b"User=myai-ci\n", b""),
    good_systemd_bytes() + b"Password=123\n",
    b"x" * (gate.MAX_SYSTEMD_BYTES + 1),
    good_systemd_bytes().replace(b"User=myai-ci", b"User=myai-ci\x00evil"),
])
def test_malformed_or_secret_bearing_systemd_output_never_parsed(bad):
    assert gate.parse_systemd_properties(bad) is None


@pytest.mark.parametrize("mutate", [
    "shared-uid", "shared-group", "docker-group", "extra-group",
    "missing-updater", "missing-ci", "root-ci",
])
def test_dangerous_identity_and_group_membership_blocks_preflight(mutate):
    s = sample()
    a = s["accounts"]
    if mutate == "shared-uid":
        a["myai-ci"]["uid"] = a["arduino"]["uid"]
    if mutate == "shared-group":
        a["myai-ci"]["groups"].append(a["arduino"]["gid"])
    if mutate == "docker-group":
        a["myai-ci"]["groups"].append(s["sensitive_gids"][0])
    if mutate == "extra-group":
        a["myai-ci"]["groups"].append(50000)
    if mutate == "missing-updater":
        a["myai-updater"] = None
    if mutate == "missing-ci":
        a["myai-ci"] = None
    if mutate == "root-ci":
        a["myai-ci"]["uid"] = 0
    info = gate.evaluate(s)
    assert info["distinct_account_and_group_candidate"] is False
    assert info["preliminary_posix_dac_checks_passed"] is False


@pytest.mark.parametrize("mutate", [
    "ci-owns-prod", "ci-group-writable", "world-writable", "prod-symlink",
    "missing-release", "ci-unsafe-state-mode", "ci-state-owned-by-arduino",
    "ci-state-symlink", "missing-parent",
])
def test_unsafe_directory_metadata_blocks_preflight(mutate):
    s = sample()
    p = s["paths"]
    if mutate == "ci-owns-prod":
        p["/home/arduino/MyAI"]["uid"] = 23003
    if mutate == "ci-group-writable":
        p["/home/arduino/MyAI"]["gid"] = 23003
        p["/home/arduino/MyAI"]["mode"] = 0o770
    if mutate == "world-writable":
        p["/home/arduino/MyAI"]["mode"] = 0o777
    if mutate == "prod-symlink":
        p["/home/arduino/MyAI"]["symlink"] = True
    if mutate == "missing-release":
        p["/home/arduino/MyAI"]["exists"] = False
    if mutate == "ci-unsafe-state-mode":
        p["/var/lib/myai-ci-runner"]["mode"] = 0o755
    if mutate == "ci-state-owned-by-arduino":
        p["/var/lib/myai-ci-runner"]["uid"] = 1000
    if mutate == "ci-state-symlink":
        p["/var/lib/myai-ci-runner"]["symlink"] = True
    if mutate == "missing-parent":
        p["/home/arduino"]["exists"] = False
    assert gate.evaluate(s)["preliminary_posix_dac_checks_passed"] is False


def test_bounded_collector_uses_fixed_readonly_systemctl_and_only_fixed_paths():
    calls = []
    def executor(command, **kwargs):
        calls.append(("command", command, kwargs))
        return SimpleNamespace(returncode=0, stdout=good_systemd_bytes())
    def passwd(name):
        assert name in gate.ACCOUNTS
        index = {"arduino": 1000, "myai-ci": 23003,
                 "myai-runtime": 23002, "myai-updater": 23001}[name]
        return SimpleNamespace(pw_uid=index, pw_gid=index)
    def groups(name, gid):
        calls.append(("groups", name))
        return [gid]
    def group(name):
        assert name in gate.SENSITIVE_GROUPS
        return SimpleNamespace(gr_gid=8000 + gate.SENSITIVE_GROUPS.index(name))
    def filesystem(path):
        assert path in gate.FIXED_PATHS
        calls.append(("stat", path))
        uid = gid = 23003 if path == "/var/lib/myai-ci-runner" else 1000
        mode = 0o700 if uid == 23003 else 0o750
        return SimpleNamespace(st_uid=uid, st_gid=gid,
                               st_mode=stat.S_IFDIR | mode)
    snapshot = gate.collect_readonly(executor=executor, user_lookup=passwd,
                                      group_members=groups, group_lookup=group,
                                      stat_fn=filesystem)
    result = gate.evaluate(snapshot)
    assert result["preliminary_posix_dac_checks_passed"] is True
    args = calls[0]
    assert args[1] == [
        "/usr/bin/systemctl", "show", gate.UNIT, "--no-pager",
        "--property=" + ",".join(gate.PROPS)
    ]
    assert args[2]["capture_output"] is True
    assert args[2]["timeout"] == 5
    assert args[2]["check"] is False
    assert args[2]["env"] == {"LC_ALL": "C", "PATH": "/usr/bin:/bin"}
    assert len([x for x in calls if x[0] == "stat"]) == len(gate.FIXED_PATHS)
    assert result["production_deployment_authorized"] is False


def test_unavailable_service_and_accounts_fail_without_error_detail_leak():
    def fail(*args, **kwargs):
        raise OSError("/home/arduino/private/secret-data")
    result = gate.evaluate(gate.collect_readonly(
        executor=fail, user_lookup=fail, group_members=fail,
        group_lookup=fail, stat_fn=fail))
    assert result["bounded_source_metadata_complete"] is False
    assert "/home/" not in json.dumps(result)
    assert result["production_deployment_authorized"] is False


def test_default_invocation_does_not_collect_local_info(monkeypatch, capsys):
    def forbidden():
        raise AssertionError("Local probe was unexpectedly invoked")
    monkeypatch.setattr(gate, "collect_readonly", forbidden)
    assert gate.main([]) == 2
    output = capsys.readouterr().out
    assert "blocked_local_runner_privilege_preflight" in output
    assert "production_deployment_authorized" in output


def test_explicit_probe_uses_collector_but_never_authorizes_release(monkeypatch, capsys):
    monkeypatch.setattr(gate, "collect_readonly", sample)
    assert gate.main(["--local-readonly"]) == 0
    assert '"production_deployment_authorized": false' in capsys.readouterr().out
