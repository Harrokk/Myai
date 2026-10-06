from types import SimpleNamespace

from modules.system import system


def test_gpu_status_degrades_cleanly_without_nvidia(monkeypatch):
    monkeypatch.setattr(
        system.shutil,
        "which",
        lambda name: None,
    )

    result = system.gpu_status()

    assert "NVIDIA GPU-status" in result
    assert "acceleratorer" in result


def test_disk_status_uses_project_filesystem_root(monkeypatch):
    seen = {}

    monkeypatch.setattr(
        system,
        "_project_disk_root",
        lambda: "/",
    )

    def fake_disk_usage(path):
        seen["path"] = path
        gib = 1024 ** 3
        return SimpleNamespace(
            used=4 * gib,
            free=12 * gib,
            total=16 * gib,
            percent=25.0,
        )

    monkeypatch.setattr(
        system.psutil,
        "disk_usage",
        fake_disk_usage,
    )

    result = system.disk_status()

    assert seen["path"] == "/"
    assert "Disk /" in result
    assert "Ledigt: 12.0 GB" in result


def test_linux_thermal_zone_reader_converts_millicelsius(tmp_path):
    thermal = tmp_path / "thermal"
    zone = thermal / "thermal_zone0"
    zone.mkdir(parents=True)
    (zone / "type").write_text(
        "soc\n",
        encoding="utf-8",
    )
    (zone / "temp").write_text(
        "52375\n",
        encoding="utf-8",
    )

    result = system._linux_thermal_zones(
        thermal
    )

    assert result == [
        ("soc", 52.375),
    ]


def test_temperature_status_falls_back_to_linux_thermal_zones(
    monkeypatch,
):
    monkeypatch.setattr(
        system.shutil,
        "which",
        lambda name: None,
    )
    monkeypatch.setattr(
        system.psutil,
        "sensors_temperatures",
        lambda: {},
        raising=False,
    )
    monkeypatch.setattr(
        system,
        "_linux_thermal_zones",
        lambda: [
            ("soc", 48.5),
            ("cpu", 50.0),
        ],
    )

    result = system.temperature_status()

    assert "soc: 48.5 °C" in result
    assert "cpu: 50.0 °C" in result


def test_cpu_status_uses_short_bounded_sample_interval(
    monkeypatch,
):
    seen = {}

    def fake_cpu_percent(
        interval,
    ):
        seen[
            "interval"
        ] = interval
        return 12.5

    monkeypatch.setattr(
        system.psutil,
        "cpu_percent",
        fake_cpu_percent,
    )
    monkeypatch.setattr(
        system.psutil,
        "cpu_count",
        lambda logical=True: 8,
    )

    result = system.cpu_status()

    assert seen[
        "interval"
    ] == system.CPU_SAMPLE_SECONDS
    assert system.CPU_SAMPLE_SECONDS == 0.2
    assert "12.5%" in result
