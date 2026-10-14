"""DAC comparison tests never touch production process/hardware."""
import stat

from scripts.ventuno_geniex_fastrpc_dac_compare import (
    dac_mode_permits, _ids_from_status, summarize,
)


def test_owner_group_and_other_mode_bits(tmp_path):
    m = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP
    assert dac_mode_permits(m, 100, 200, 100, 999, frozenset()) == {
        "read": True, "write": True,
    }
    assert dac_mode_permits(m, 100, 200, 101, 200, frozenset()) == {
        "read": True, "write": False,
    }
    assert dac_mode_permits(m, 100, 200, 101, 888, frozenset({200})) == {
        "read": True, "write": False,
    }
    assert dac_mode_permits(m, 100, 200, 101, 888, frozenset()) == {
        "read": False, "write": False,
    }


def test_proc_status_reports_fs_credential_column_only(tmp_path):
    p = tmp_path / "status"
    p.write_text("Uid:\t1000\t1000\t1000\t1001\n"
                 "Gid:\t1100\t1100\t1100\t1101\n"
                 "Groups:\t11 22 33\n", encoding="ascii")
    data = _ids_from_status(p)
    assert data == {
        "fsuid": 1001, "fsgid": 1101, "groups": frozenset({11, 22, 33}),
    }
    p.write_text("Uid:\tunknown\n", encoding="ascii")
    assert _ids_from_status(p) is None


def test_missing_device_yields_unknown_without_open(monkeypatch):
    from scripts import ventuno_geniex_fastrpc_dac_compare as m
    def no_dev(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr(m.Path, "lstat", no_dev)
    output = summarize()
    assert output["device_opened"] is False
    assert output["secure_rpc_character_device_present"] is False
    assert output["geniex_different_fsuid_from_runner"] is None
    assert output["service_modified"] is False
