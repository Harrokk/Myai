import json
from copy import deepcopy

from core import ventuno_stability
from core.config import DEFAULT_SETTINGS
from modules.ventuno import stability


def record(
    unix_time,
    *,
    success=True,
    first=0.5,
    total=1.0,
    backend="primary",
    cpu=20.0,
    ram=40.0,
    disk=30.0,
    free=1000,
    temp=55.0,
):
    return {
        "unix_time": float(
            unix_time
        ),
        "llm": {
            "success": bool(
                success
            ),
            "first_chunk_seconds": (
                first
            ),
            "total_seconds": total,
            "llm_runtime": {
                "active_backend": backend,
            },
        },
        "system": {
            "cpu_percent": cpu,
            "ram_percent": ram,
            "disk_percent": disk,
            "disk_free_bytes": free,
            "temperatures": [
                {
                    "group": "soc",
                    "label": "soc",
                    "celsius": temp,
                }
            ],
        },
    }


def test_analyzer_summarizes_failures_latency_backends_and_resources():
    records = [
        record(
            0,
            first=0.4,
            total=1.0,
            cpu=10,
            ram=30,
            temp=50,
        ),
        record(
            3600,
            success=False,
            first=None,
            total=3.0,
            cpu=90,
            ram=70,
            temp=75,
        ),
        record(
            7200,
            success=False,
            first=None,
            total=4.0,
            backend="fallback",
            cpu=80,
            ram=75,
            temp=80,
        ),
        record(
            10800,
            first=0.8,
            total=2.0,
            backend="primary",
            cpu=30,
            ram=50,
            temp=60,
        ),
    ]

    report = (
        ventuno_stability
        .analyze_stability_records(
            records,
            target_hours=3,
        )
    )

    assert report["records"] == 4
    assert report["successes"] == 2
    assert report["failures"] == 2
    assert (
        report["success_rate_percent"]
        == 50.0
    )
    assert (
        report[
            "longest_failure_streak"
        ]
        == 2
    )
    assert report["duration_hours"] == 3.0
    assert (
        report[
            "target_duration_reached"
        ]
        is True
    )
    assert report["backend"][
        "switches"
    ] == 2
    assert report["backend"][
        "counts"
    ] == {
        "primary": 3,
        "fallback": 1,
    }
    assert report["system"][
        "cpu_max_percent"
    ] == 90.0
    assert report["system"][
        "ram_max_percent"
    ] == 75.0
    assert report["system"][
        "temperature_max_celsius"
    ] == 80.0
    assert report[
        "physical_hardware_approval"
    ] is False


def test_analyzer_flags_relative_latency_degradation_only_as_observation():
    records = [
        record(
            0,
            first=0.4,
            total=1.0,
        ),
        record(
            60,
            first=0.4,
            total=1.0,
        ),
        record(
            120,
            first=0.8,
            total=2.0,
        ),
        record(
            180,
            first=0.8,
            total=2.0,
        ),
    ]

    report = (
        ventuno_stability
        .analyze_stability_records(
            records,
            target_hours=72,
            trend_fraction=0.5,
            latency_degradation_ratio=1.25,
        )
    )

    assert report[
        "relative_trends"
    ][
        "first_chunk_end_vs_start_median_ratio"
    ] == 2.0
    assert any(
        "first-token-latens" in item
        for item in report[
            "observations"
        ]
    )
    assert any(
        "når inte målperioden" in item
        for item in report[
            "observations"
        ]
    )
    assert report[
        "physical_hardware_approval"
    ] is False


def test_read_stability_records_uses_rotated_files_and_keeps_newest_when_bounded(
    tmp_path,
):
    path = (
        tmp_path
        / "stability.jsonl"
    )
    (
        tmp_path
        / "stability.jsonl.1"
    ).write_text(
        json.dumps(
            record(
                1
            )
        )
        + "\n"
        + "broken-json\n",
        encoding="utf-8",
    )
    path.write_text(
        json.dumps(
            record(
                2
            )
        )
        + "\n"
        + json.dumps(
            record(
                3
            )
        )
        + "\n",
        encoding="utf-8",
    )

    result = (
        ventuno_stability
        .read_stability_records(
            path,
            backups=2,
            max_records=2,
        )
    )

    assert result[
        "total_valid_records"
    ] == 3
    assert result[
        "malformed_count"
    ] == 1
    assert result[
        "truncated"
    ] is True
    assert [
        item["unix_time"]
        for item in result[
            "records"
        ]
    ] == [
        2.0,
        3.0,
    ]


def test_format_report_never_claims_physical_approval():
    report = (
        ventuno_stability
        .analyze_stability_records(
            [
                record(
                    0
                ),
                record(
                    72 * 3600
                ),
            ],
            target_hours=72,
        )
    )

    text = (
        ventuno_stability
        .format_stability_report(
            report
        )
    )

    assert "målperiod nådd: ja" in text
    assert (
        "Fysisk VENTUNO-verifiering: inte bedömd"
        in text
    )
    assert "godkänd" not in text.lower()


def test_stability_module_reads_configured_log_read_only(
    tmp_path,
    monkeypatch,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings[
        "stability_analysis"
    ][
        "log_path"
    ] = "runtime/test-stability.jsonl"
    monkeypatch.setattr(
        stability,
        "PROJECT_ROOT",
        tmp_path,
    )
    path = (
        tmp_path
        / "runtime"
        / "test-stability.jsonl"
    )
    path.parent.mkdir(
        parents=True,
    )
    path.write_text(
        json.dumps(
            record(
                100
            )
        )
        + "\n",
        encoding="utf-8",
    )
    before = path.read_bytes()

    report = (
        stability
        .read_ventuno_stability_report(
            settings
        )
    )

    assert report[
        "records"
    ] == 1
    assert path.read_bytes() == before


def test_stability_tool_exposes_only_read_only_report():
    assert set(
        stability.TOOLS
    ) == {
        "ventuno_stability_report",
    }
