from types import SimpleNamespace

from modules.pi import diagnostics


def test_network_status_is_safe_on_non_linux(monkeypatch):
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Windows")

    result = diagnostics.collect_network_status()

    assert result["supported"] is False
    assert result["platform"] == "Windows"


def test_network_status_normalizes_ipv4_and_ipv6(monkeypatch):
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        diagnostics.psutil,
        "net_if_stats",
        lambda: {
            "eth0": SimpleNamespace(isup=True, speed=1000),
        },
    )
    monkeypatch.setattr(
        diagnostics.psutil,
        "net_if_addrs",
        lambda: {
            "eth0": [
                SimpleNamespace(
                    family=diagnostics.socket.AF_INET,
                    address="192.168.1.10",
                ),
                SimpleNamespace(
                    family=diagnostics.socket.AF_INET6,
                    address="fe80::1%eth0",
                ),
            ]
        },
    )

    result = diagnostics.collect_network_status()

    assert result["interfaces"][0]["name"] == "eth0"
    assert result["interfaces"][0]["up"] is True
    assert result["interfaces"][0]["speed_mbps"] == 1000
    assert result["interfaces"][0]["addresses"] == [
        {"type": "ipv4", "address": "192.168.1.10"},
        {"type": "ipv6", "address": "fe80::1"},
    ]


def test_process_status_sorts_by_memory(monkeypatch):
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Linux")

    class FakeProcess:
        def __init__(self, info):
            self.info = info

    monkeypatch.setattr(
        diagnostics.psutil,
        "process_iter",
        lambda attrs: [
            FakeProcess(
                {
                    "pid": 1,
                    "name": "small",
                    "cpu_percent": 30,
                    "memory_percent": 1,
                    "username": "pi",
                }
            ),
            FakeProcess(
                {
                    "pid": 2,
                    "name": "large",
                    "cpu_percent": 2,
                    "memory_percent": 20,
                    "username": "pi",
                }
            ),
        ],
    )

    result = diagnostics.collect_process_status(limit=1)

    assert [item["name"] for item in result["processes"]] == ["large"]


def test_services_status_handles_missing_systemctl(monkeypatch):
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Linux")
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: None)

    result = diagnostics.collect_services_status()

    assert result["supported"] is True
    assert result["available"] is False
    assert "systemctl" in result["reason"]


def test_services_status_parses_running_units(monkeypatch):
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        diagnostics.shutil,
        "which",
        lambda name: "/usr/bin/systemctl",
    )
    monkeypatch.setattr(
        diagnostics,
        "_run",
        lambda command: SimpleNamespace(
            returncode=0,
            stdout=(
                "ssh.service loaded active running OpenBSD Secure Shell server\n"
                "cron.service loaded active running Regular background program\n"
            ),
            stderr="",
        ),
    )

    result = diagnostics.collect_services_status()

    assert result["available"] is True
    assert result["services"][0]["unit"] == "ssh.service"
    assert result["services"][0]["active"] == "active"


def test_system_logs_handles_missing_journalctl(monkeypatch):
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Linux")
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: None)

    result = diagnostics.collect_system_logs()

    assert result["available"] is False
    assert "journalctl" in result["reason"]


def test_system_logs_keeps_recent_warning_entries(monkeypatch):
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        diagnostics.shutil,
        "which",
        lambda name: "/usr/bin/journalctl",
    )
    monkeypatch.setattr(
        diagnostics,
        "_run",
        lambda command: SimpleNamespace(
            returncode=0,
            stdout=(
                "-- Boot 1 --\n"
                "2026-10-02T10:00:00+02:00 host kernel: warning one\n"
                "2026-10-02T10:01:00+02:00 host service: warning two\n"
            ),
            stderr="",
        ),
    )

    result = diagnostics.collect_system_logs(limit=2)

    assert result["available"] is True
    assert len(result["entries"]) == 2
    assert "warning two" in result["entries"][-1]


def test_formatters_explain_non_linux():
    unsupported = {
        "supported": False,
        "platform": "Windows",
    }

    assert "Windows" in diagnostics.format_network_status(unsupported)
    assert "Windows" in diagnostics.format_process_status(unsupported)
    assert "Windows" in diagnostics.format_services_status(unsupported)
    assert "Windows" in diagnostics.format_system_logs(unsupported)
