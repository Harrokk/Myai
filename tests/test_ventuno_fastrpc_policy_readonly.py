"""All vendor-policy tests use synthetic data; no FastRPC/QNN hardware."""
import json
import stat
from types import SimpleNamespace

from scripts import ventuno_fastrpc_policy_readonly as policy


def test_udev_policy_inventory_reads_only_small_rules(tmp_path):
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "fast.rules").write_text(
        'SUBSYSTEM=="fastrpc", GROUP="fastrpc", MODE="0640"\n'
        'SUBSYSTEM=="dma_heap", GROUP="fastrpc", MODE="0660"\n',
        encoding="ascii",
    )
    (rules / "ignored.txt").write_text("do not scan", encoding="ascii")
    result = policy.bounded_rules_inventory((rules,))
    assert result["scan_complete"] is True
    assert result["scanned_rule_files"] == 1
    assert result["fastrpc_mention_files"] == 1
    assert result["dma_heap_mention_files"] == 1
    assert result["fastrpc_group_assignment_seen"] is True
    assert result["mode_0640_assignment_seen"] is True
    assert "SUBSYSTEM" not in json.dumps(result)


def test_unreadable_or_symlinked_rules_cannot_be_trusted(tmp_path):
    rules = tmp_path / "rules"
    rules.mkdir()
    source = tmp_path / "private.rules"
    source.write_text("TOKEN=never-exported", encoding="ascii")
    (rules / "external.rules").symlink_to(source)
    result = policy.bounded_rules_inventory((rules,))
    assert result["scan_complete"] is False
    assert "never-exported" not in json.dumps(result)


def test_policy_scan_budget_is_explicit(tmp_path):
    rules = tmp_path / "rules"
    rules.mkdir()
    for index in range(policy.MAX_RULE_ENTRIES + 1):
        (rules / f"r{index:03}.rules").write_bytes(b"")
    result = policy.bounded_rules_inventory((rules,))
    assert result["scan_complete"] is False
    assert result["scanned_rule_files"] <= policy.MAX_RULE_ENTRIES


def test_secure_node_read_only_can_match_vendor_style_permissions(monkeypatch):
    class FakeNode:
        def lstat(self):
            return SimpleNamespace(
                st_mode=stat.S_IFCHR | 0o640,
                st_uid=0,
                st_gid=122,
            )
    monkeypatch.setattr(policy.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(policy.os, "getegid", lambda: 1000)
    monkeypatch.setattr(policy.os, "getgroups", lambda: [122])
    monkeypatch.setattr(
        policy.os, "access",
        lambda _path, flag, effective_ids: flag == policy.os.R_OK,
    )
    observed = policy.metadata_for_device(
        FakeNode(), 122,
        {"fsuid": 1000, "fsgid": 1000, "groups": frozenset({122})},
    )
    assert observed["character_device"] is True
    assert observed["device_group_is_fastrpc"] is True
    assert observed["runner_effective_read_access"] is True
    assert observed["runner_effective_write_access"] is False
    assert observed["geniex_has_classic_dac_read"] is True
    assert observed["geniex_has_classic_dac_write"] is False


def test_regular_or_missing_node_not_mistaken_for_rpc(monkeypatch, tmp_path):
    regular = tmp_path / "not-a-device"
    regular.write_text("safe", encoding="ascii")
    def forbid_device_open(*args, **kwargs):
        raise AssertionError("Hardware must not be opened")
    monkeypatch.setattr(policy.os, "access", forbid_device_open)
    for target in (regular, tmp_path / "missing"):
        data = policy.metadata_for_device(target, None, None)
        assert data["character_device"] is False
        assert data["runner_effective_read_access"] is None


def test_report_emits_no_private_identity_paths_or_raw_rule_lines(monkeypatch, tmp_path):
    monkeypatch.setattr(policy, "fastrpc_gid", lambda: 122)
    monkeypatch.setattr(policy, "one_geniex_identity", lambda: {
        "fsuid": 1001, "fsgid": 1001, "groups": frozenset({122}),
    })
    monkeypatch.setattr(policy.os, "getegid", lambda: 1001)
    monkeypatch.setattr(policy.os, "getgroups", lambda: [122])
    rules = tmp_path / "private"
    rules.mkdir()
    (rules / "private-data.rules").write_text("KEY=important-secret", encoding="ascii")
    result = policy.report(dev_root=tmp_path / "empty", rule_roots=(rules,))
    encoded = json.dumps(result)
    for secret in ("important-secret", "private-data", "/dev/", "/proc/", "/home/"):
        assert secret not in encoded
    assert result["one_geniex_identity_readable"] is True
    assert result["geniex_in_fastrpc_group"] is True
    assert result["node_or_service_modified"] is False
    assert result["qnn_htp_backend_attempted"] is False
    assert result["actual_device_open_verified"] is False


def test_symlinked_rules_directory_is_reported_as_partial(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "valid.rules").write_text('GROUP="fastrpc"', encoding="ascii")
    alias = tmp_path / "alias"
    alias.symlink_to(source, target_is_directory=True)
    report = policy.bounded_rules_inventory((alias,))
    assert report["scan_complete"] is False
    assert report["scanned_rule_files"] == 0


def test_fifo_rule_is_rejected_without_blocking(tmp_path):
    rules = tmp_path / "rules"
    rules.mkdir()
    import os
    os.mkfifo(rules / "untrusted.rules")
    result = policy.bounded_rules_inventory((rules,))
    assert result["scan_complete"] is False
    assert result["scanned_rule_files"] == 0


def test_total_directory_entry_budget_is_enforced(tmp_path, monkeypatch):
    rules = tmp_path / "rules"
    rules.mkdir()
    monkeypatch.setattr(policy, "MAX_DIRECTORY_ENTRIES", 2)
    for i in range(3):
        (rules / f"unrelated-{i}.txt").write_bytes(b"")
    result = policy.bounded_rules_inventory((rules,))
    assert result["scan_complete"] is False
    assert result["scanned_rule_files"] == 0


def test_policy_files_are_opened_relative_to_pinned_directory(tmp_path, monkeypatch):
    import os
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "fast.rules").write_text('GROUP="fastrpc"', encoding="ascii")
    original_open = policy.os.open
    observations = []

    def inspected_open(path, flags, *args, **kwargs):
        if path == "fast.rules":
            observations.append({
                "dir_fd": kwargs.get("dir_fd"),
                "no_follow": bool(flags & os.O_NOFOLLOW),
                "nonblock": bool(flags & os.O_NONBLOCK),
            })
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(policy.os, "open", inspected_open)
    result = policy.bounded_rules_inventory((rules,))
    assert result["scan_complete"] is True
    assert result["scanned_rule_files"] == 1
    assert len(observations) == 1
    assert isinstance(observations[0]["dir_fd"], int)
    assert observations[0]["no_follow"] is True
    assert observations[0]["nonblock"] is True
