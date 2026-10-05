import json
from pathlib import Path
import statistics
import time

import psutil

from core.jsonl_log import append_jsonl


def _temperature_snapshot():
    values = []

    try:
        if hasattr(
            psutil,
            "sensors_temperatures",
        ):
            groups = (
                psutil.sensors_temperatures()
                or {}
            )

            for group, entries in (
                groups.items()
            ):
                for entry in entries:
                    current = getattr(
                        entry,
                        "current",
                        None,
                    )

                    if current is None:
                        continue

                    values.append(
                        {
                            "group": group,
                            "label": (
                                getattr(
                                    entry,
                                    "label",
                                    "",
                                )
                                or group
                            ),
                            "celsius": float(
                                current
                            ),
                        }
                    )
    except Exception:
        pass

    return values


def collect_system_sample(
    disk_path="/",
):
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(
        disk_path
    )

    return {
        "cpu_percent": float(
            psutil.cpu_percent(
                interval=None
            )
        ),
        "ram_percent": float(
            memory.percent
        ),
        "ram_used_bytes": int(
            memory.used
        ),
        "ram_total_bytes": int(
            memory.total
        ),
        "disk_percent": float(
            disk.percent
        ),
        "disk_free_bytes": int(
            disk.free
        ),
        "temperatures": (
            _temperature_snapshot()
        ),
    }


def _runtime_metadata(llm):
    status = getattr(
        llm,
        "status",
        None,
    )

    if callable(status):
        return dict(
            status()
        )

    return {
        "enabled": False,
        "active_backend": "primary",
        "primary_provider": getattr(
            llm,
            "provider_name",
            "unknown",
        ),
        "primary_model": getattr(
            llm,
            "model",
            "",
        ),
        "fallback_provider": None,
        "fallback_model": None,
        "last_error": None,
    }


def measure_llm_iteration(
    llm,
    prompt,
    *,
    timeout=300,
    clock=None,
):
    clock = clock or time.monotonic
    messages = [
        {
            "role": "user",
            "content": str(prompt),
        }
    ]
    started = clock()
    first_chunk_seconds = None
    chunks = []
    success = False
    error = None

    try:
        stream = getattr(
            llm,
            "chat_stream",
            None,
        )

        if callable(stream):
            for chunk in stream(
                messages,
                timeout=timeout,
            ):
                value = str(
                    chunk
                    or ""
                )

                if not value:
                    continue

                if (
                    first_chunk_seconds
                    is None
                ):
                    first_chunk_seconds = (
                        clock()
                        - started
                    )

                chunks.append(
                    value
                )
        else:
            value = str(
                llm.chat(
                    messages,
                    timeout=timeout,
                )
                or ""
            )

            if value:
                first_chunk_seconds = (
                    clock()
                    - started
                )
                chunks.append(
                    value
                )

        success = True
    except Exception as exc:
        error = (
            f"{type(exc).__name__}: "
            f"{exc}"
        )

    total_seconds = (
        clock()
        - started
    )
    answer = "".join(
        chunks
    )

    return {
        "success": success,
        "error": error,
        "first_chunk_seconds": (
            round(
                first_chunk_seconds,
                4,
            )
            if first_chunk_seconds
            is not None
            else None
        ),
        "total_seconds": round(
            total_seconds,
            4,
        ),
        "response_chars": len(
            answer
        ),
        "response_chunks": len(
            chunks
        ),
        "llm_runtime": (
            _runtime_metadata(
                llm
            )
        ),
    }


class VentunoStabilityLogger:
    def __init__(
        self,
        path,
        *,
        clock=None,
        wall_clock=None,
        max_bytes=5_000_000,
        backups=5,
    ):
        self.path = Path(path)
        self.clock = (
            clock
            or time.monotonic
        )
        self.wall_clock = (
            wall_clock
            or time.time
        )
        self.started_at = (
            self.clock()
        )
        self.sequence = 0
        self.max_bytes = max(
            0,
            int(
                max_bytes
            ),
        )
        self.backups = max(
            0,
            int(
                backups
            ),
        )

    def append(
        self,
        llm_result,
        system_sample,
    ):
        self.sequence += 1
        now = self.clock()

        record = {
            "sequence": (
                self.sequence
            ),
            "unix_time": float(
                self.wall_clock()
            ),
            "elapsed_seconds": round(
                now
                - self.started_at,
                4,
            ),
            "llm": dict(
                llm_result
            ),
            "system": dict(
                system_sample
            ),
        }

        append_jsonl(
            self.path,
            record,
            max_bytes=self.max_bytes,
            backups=self.backups,
        )

        return record



def _rotated_stability_paths(
    path,
    *,
    backups,
):
    target = Path(
        path
    )
    count = max(
        0,
        int(
            backups
        ),
    )
    paths = []

    for index in range(
        count,
        0,
        -1,
    ):
        paths.append(
            Path(
                str(
                    target
                )
                + f".{index}"
            )
        )

    paths.append(
        target
    )
    return paths


def read_stability_records(
    path,
    *,
    backups=5,
    max_records=10_000,
):
    """Read stability JSONL in chronological order without modifying it."""

    limit = min(
        100_000,
        max(
            1,
            int(
                max_records
            ),
        ),
    )
    records = []
    malformed_count = 0
    source_files = []

    for candidate in _rotated_stability_paths(
        path,
        backups=backups,
    ):
        try:
            handle = candidate.open(
                "r",
                encoding="utf-8",
            )
        except FileNotFoundError:
            continue
        except OSError:
            continue

        source_files.append(
            str(
                candidate
            )
        )

        with handle:
            for line in handle:
                if not line.strip():
                    continue

                try:
                    value = json.loads(
                        line
                    )
                except (
                    json.JSONDecodeError,
                    TypeError,
                ):
                    malformed_count += 1
                    continue

                if not isinstance(
                    value,
                    dict,
                ):
                    malformed_count += 1
                    continue

                records.append(
                    value
                )

                if len(
                    records
                ) > limit:
                    records.pop(
                        0
                    )

    truncated = False

    if records:
        valid_seen = len(
            records
        )
        # If the retained list exactly reached the cap we cannot infer
        # truncation without tracking all valid rows, so count them explicitly
        # during a second lightweight condition below.
        total_valid = 0

        for candidate in _rotated_stability_paths(
            path,
            backups=backups,
        ):
            try:
                with candidate.open(
                    "r",
                    encoding="utf-8",
                ) as handle:
                    for line in handle:
                        if not line.strip():
                            continue
                        try:
                            value = json.loads(
                                line
                            )
                        except (
                            json.JSONDecodeError,
                            TypeError,
                        ):
                            continue
                        if isinstance(
                            value,
                            dict,
                        ):
                            total_valid += 1
                            if total_valid > limit:
                                truncated = True
                                break
            except (
                FileNotFoundError,
                OSError,
            ):
                continue

            if truncated:
                break

        if not truncated:
            total_valid = valid_seen
    else:
        total_valid = 0

    return {
        "records": records,
        "count": len(
            records
        ),
        "total_valid_records": (
            total_valid
        ),
        "malformed_count": (
            malformed_count
        ),
        "truncated": bool(
            truncated
        ),
        "source_files": source_files,
    }


def _numeric(
    value,
):
    try:
        number = float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if number != number:
        return None

    return number


def _percentile(
    values,
    percentile,
):
    clean = sorted(
        value
        for value in (
            _numeric(
                item
            )
            for item in values
        )
        if value is not None
    )

    if not clean:
        return None

    if len(
        clean
    ) == 1:
        return round(
            clean[0],
            4,
        )

    rank = (
        max(
            0.0,
            min(
                100.0,
                float(
                    percentile
                ),
            ),
        )
        / 100.0
        * (
            len(
                clean
            )
            - 1
        )
    )
    lower = int(
        rank
    )
    upper = min(
        len(
            clean
        )
        - 1,
        lower + 1,
    )
    fraction = (
        rank
        - lower
    )
    value = (
        clean[lower]
        + (
            clean[upper]
            - clean[lower]
        )
        * fraction
    )
    return round(
        value,
        4,
    )


def _mean(
    values,
):
    clean = [
        value
        for value in (
            _numeric(
                item
            )
            for item in values
        )
        if value is not None
    ]

    if not clean:
        return None

    return round(
        statistics.fmean(
            clean
        ),
        4,
    )


def _max_numeric(
    values,
):
    clean = [
        value
        for value in (
            _numeric(
                item
            )
            for item in values
        )
        if value is not None
    ]

    if not clean:
        return None

    return round(
        max(
            clean
        ),
        4,
    )


def _min_numeric(
    values,
):
    clean = [
        value
        for value in (
            _numeric(
                item
            )
            for item in values
        )
        if value is not None
    ]

    if not clean:
        return None

    return round(
        min(
            clean
        ),
        4,
    )


def _latency_summary(
    values,
):
    clean = [
        value
        for value in (
            _numeric(
                item
            )
            for item in values
        )
        if value is not None
    ]

    return {
        "samples": len(
            clean
        ),
        "p50_seconds": _percentile(
            clean,
            50,
        ),
        "p95_seconds": _percentile(
            clean,
            95,
        ),
        "max_seconds": _max_numeric(
            clean
        ),
    }


def _longest_failure_streak(
    records,
):
    longest = 0
    current = 0

    for record in records:
        success = bool(
            (
                record.get(
                    "llm",
                    {},
                )
                or {}
            ).get(
                "success",
                False,
            )
        )

        if success:
            current = 0
        else:
            current += 1
            longest = max(
                longest,
                current,
            )

    return longest


def _backend_summary(
    records,
):
    counts = {}
    switches = 0
    previous = None

    for record in records:
        runtime = (
            (
                record.get(
                    "llm",
                    {},
                )
                or {}
            ).get(
                "llm_runtime",
                {},
            )
            or {}
        )
        backend = str(
            runtime.get(
                "active_backend",
                "unknown",
            )
            or "unknown"
        )
        counts[
            backend
        ] = (
            counts.get(
                backend,
                0,
            )
            + 1
        )

        if (
            previous is not None
            and backend != previous
        ):
            switches += 1

        previous = backend

    return {
        "counts": counts,
        "switches": switches,
    }


def _temperature_values(
    records,
):
    values = []

    for record in records:
        system = (
            record.get(
                "system",
                {},
            )
            or {}
        )
        temperatures = (
            system.get(
                "temperatures",
                []
            )
            or []
        )

        for item in temperatures:
            if not isinstance(
                item,
                dict,
            ):
                continue

            value = _numeric(
                item.get(
                    "celsius"
                )
            )

            if value is not None:
                values.append(
                    value
                )

    return values


def _duration_seconds(
    records,
):
    timestamps = [
        value
        for value in (
            _numeric(
                record.get(
                    "unix_time"
                )
            )
            for record in records
        )
        if value is not None
    ]

    if len(
        timestamps
    ) < 2:
        return 0.0

    return max(
        0.0,
        max(
            timestamps
        )
        - min(
            timestamps
        ),
    )


def _trend_ratio(
    values,
    *,
    fraction,
):
    clean = [
        value
        for value in (
            _numeric(
                item
            )
            for item in values
        )
        if value is not None
    ]

    if len(
        clean
    ) < 4:
        return None

    window = max(
        1,
        int(
            len(
                clean
            )
            * fraction
        ),
    )
    window = min(
        window,
        len(
            clean
        )
        // 2,
    )

    if window <= 0:
        return None

    first = _percentile(
        clean[
            :window
        ],
        50,
    )
    last = _percentile(
        clean[
            -window:
        ],
        50,
    )

    if (
        first is None
        or last is None
        or first <= 0
    ):
        return None

    return round(
        last
        / first,
        4,
    )


def analyze_stability_records(
    records,
    *,
    malformed_count=0,
    truncated=False,
    target_hours=72.0,
    trend_fraction=0.25,
    latency_degradation_ratio=1.25,
):
    """Summarize stability data without declaring physical hardware approval."""

    usable = [
        record
        for record in records
        if isinstance(
            record,
            dict,
        )
    ]
    total = len(
        usable
    )
    llm_values = [
        (
            record.get(
                "llm",
                {},
            )
            or {}
        )
        for record in usable
    ]
    system_values = [
        (
            record.get(
                "system",
                {},
            )
            or {}
        )
        for record in usable
    ]
    successes = sum(
        1
        for item in llm_values
        if bool(
            item.get(
                "success",
                False,
            )
        )
    )
    failures = (
        total
        - successes
    )
    first_chunk = [
        item.get(
            "first_chunk_seconds"
        )
        for item in llm_values
    ]
    total_latency = [
        item.get(
            "total_seconds"
        )
        for item in llm_values
    ]
    duration = _duration_seconds(
        usable
    )
    target_seconds = max(
        0.0,
        float(
            target_hours
        )
        * 3600.0,
    )
    trend_fraction = min(
        0.5,
        max(
            0.1,
            float(
                trend_fraction
            ),
        ),
    )
    degradation_ratio = max(
        1.0,
        float(
            latency_degradation_ratio
        ),
    )
    first_ratio = _trend_ratio(
        first_chunk,
        fraction=trend_fraction,
    )
    total_ratio = _trend_ratio(
        total_latency,
        fraction=trend_fraction,
    )

    observations = []

    if total == 0:
        observations.append(
            "Ingen giltig stabilitetsdata hittades."
        )
    elif failures:
        observations.append(
            (
                f"{failures} av {total} "
                "LLM-iterationer misslyckades."
            )
        )

    longest = _longest_failure_streak(
        usable
    )

    if longest > 1:
        observations.append(
            (
                "Längsta sammanhängande felserie: "
                f"{longest} iterationer."
            )
        )

    backend = _backend_summary(
        usable
    )

    if backend[
        "switches"
    ]:
        observations.append(
            (
                "Backend växlade "
                f"{backend['switches']} gånger."
            )
        )

    if malformed_count:
        observations.append(
            (
                f"{int(malformed_count)} ogiltiga "
                "JSONL-rader ignorerades."
            )
        )

    if truncated:
        observations.append(
            (
                "Analysen använder endast den senast "
                "tillåtna delen av loggen eftersom "
                "record-gränsen nåddes."
            )
        )

    if (
        total > 0
        and target_seconds > 0
        and duration < target_seconds
    ):
        observations.append(
            (
                "Loggens observerade tidsomfång når inte "
                f"målperioden {float(target_hours):.1f} h."
            )
        )

    if (
        first_ratio is not None
        and first_ratio
        >= degradation_ratio
    ):
        observations.append(
            (
                "Median first-token-latens i slutet är "
                f"{first_ratio:.2f}× startnivån."
            )
        )

    if (
        total_ratio is not None
        and total_ratio
        >= degradation_ratio
    ):
        observations.append(
            (
                "Median total svarstid i slutet är "
                f"{total_ratio:.2f}× startnivån."
            )
        )

    cpu = [
        item.get(
            "cpu_percent"
        )
        for item in system_values
    ]
    ram = [
        item.get(
            "ram_percent"
        )
        for item in system_values
    ]
    disk = [
        item.get(
            "disk_percent"
        )
        for item in system_values
    ]
    disk_free = [
        item.get(
            "disk_free_bytes"
        )
        for item in system_values
    ]
    temperatures = _temperature_values(
        usable
    )

    return {
        "schema_version": 1,
        "physical_hardware_approval": False,
        "physical_hardware_approval_reason": (
            "Rapporten analyserar endast loggdata; "
            "fysisk VENTUNO-verifiering bedöms separat enligt project_spec."
        ),
        "records": total,
        "successes": successes,
        "failures": failures,
        "success_rate_percent": (
            round(
                (
                    successes
                    / total
                    * 100.0
                ),
                4,
            )
            if total
            else None
        ),
        "longest_failure_streak": longest,
        "duration_seconds": round(
            duration,
            4,
        ),
        "duration_hours": round(
            duration
            / 3600.0,
            4,
        ),
        "target_hours": float(
            target_hours
        ),
        "target_duration_reached": bool(
            total
            and duration
            >= target_seconds
        ),
        "latency": {
            "first_chunk": _latency_summary(
                first_chunk
            ),
            "total": _latency_summary(
                total_latency
            ),
        },
        "relative_trends": {
            "window_fraction": round(
                trend_fraction,
                4,
            ),
            "first_chunk_end_vs_start_median_ratio": (
                first_ratio
            ),
            "total_end_vs_start_median_ratio": (
                total_ratio
            ),
            "degradation_flag_ratio": round(
                degradation_ratio,
                4,
            ),
        },
        "backend": backend,
        "system": {
            "cpu_mean_percent": _mean(
                cpu
            ),
            "cpu_max_percent": _max_numeric(
                cpu
            ),
            "ram_mean_percent": _mean(
                ram
            ),
            "ram_max_percent": _max_numeric(
                ram
            ),
            "disk_max_percent": _max_numeric(
                disk
            ),
            "disk_min_free_bytes": _min_numeric(
                disk_free
            ),
            "temperature_max_celsius": _max_numeric(
                temperatures
            ),
            "temperature_samples": len(
                temperatures
            ),
        },
        "log_quality": {
            "malformed_count": int(
                malformed_count
            ),
            "truncated": bool(
                truncated
            ),
        },
        "observations": observations,
    }


def analyze_stability_log(
    path,
    *,
    backups=5,
    max_records=10_000,
    target_hours=72.0,
    trend_fraction=0.25,
    latency_degradation_ratio=1.25,
):
    loaded = read_stability_records(
        path,
        backups=backups,
        max_records=max_records,
    )
    report = analyze_stability_records(
        loaded[
            "records"
        ],
        malformed_count=loaded[
            "malformed_count"
        ],
        truncated=loaded[
            "truncated"
        ],
        target_hours=target_hours,
        trend_fraction=trend_fraction,
        latency_degradation_ratio=(
            latency_degradation_ratio
        ),
    )
    report[
        "source_files"
    ] = loaded[
        "source_files"
    ]
    report[
        "total_valid_records"
    ] = loaded[
        "total_valid_records"
    ]
    return report



def _format_optional(
    value,
    *,
    suffix="",
    digits=2,
):
    number = _numeric(
        value
    )

    if number is None:
        return "saknas"

    return (
        f"{number:.{int(digits)}f}"
        + suffix
    )


def format_stability_report(
    report,
):
    """Human-readable Swedish summary; never declares hardware approval."""

    records = int(
        report.get(
            "records",
            0,
        )
        or 0
    )

    if records <= 0:
        return (
            "VENTUNO stabilitetsrapport: ingen giltig data.\n"
            "Fysisk VENTUNO-verifiering: inte bedömd av rapporten."
        )

    latency = report.get(
        "latency",
        {},
    )
    first = latency.get(
        "first_chunk",
        {},
    )
    total = latency.get(
        "total",
        {},
    )
    system = report.get(
        "system",
        {},
    )
    backend = report.get(
        "backend",
        {},
    )
    target_reached = bool(
        report.get(
            "target_duration_reached",
            False,
        )
    )
    lines = [
        "VENTUNO stabilitetsrapport",
        (
            f"Poster: {records} | "
            f"lyckade: {int(report.get('successes', 0) or 0)} | "
            f"fel: {int(report.get('failures', 0) or 0)}"
        ),
        (
            "Lyckandegrad: "
            + _format_optional(
                report.get(
                    "success_rate_percent"
                ),
                suffix="%",
            )
        ),
        (
            "Observerad tid: "
            + _format_optional(
                report.get(
                    "duration_hours"
                ),
                suffix=" h",
            )
            + " | målperiod nådd: "
            + (
                "ja"
                if target_reached
                else "nej"
            )
        ),
        (
            "First-token-latens p50/p95/max: "
            + "/".join(
                [
                    _format_optional(
                        first.get(
                            "p50_seconds"
                        ),
                        suffix=" s",
                    ),
                    _format_optional(
                        first.get(
                            "p95_seconds"
                        ),
                        suffix=" s",
                    ),
                    _format_optional(
                        first.get(
                            "max_seconds"
                        ),
                        suffix=" s",
                    ),
                ]
            )
        ),
        (
            "Total svarstid p50/p95/max: "
            + "/".join(
                [
                    _format_optional(
                        total.get(
                            "p50_seconds"
                        ),
                        suffix=" s",
                    ),
                    _format_optional(
                        total.get(
                            "p95_seconds"
                        ),
                        suffix=" s",
                    ),
                    _format_optional(
                        total.get(
                            "max_seconds"
                        ),
                        suffix=" s",
                    ),
                ]
            )
        ),
        (
            "Längsta felserie: "
            f"{int(report.get('longest_failure_streak', 0) or 0)}"
        ),
        (
            "Backendbyten: "
            f"{int(backend.get('switches', 0) or 0)} | "
            f"fördelning: {backend.get('counts', {})}"
        ),
        (
            "CPU medel/max: "
            + _format_optional(
                system.get(
                    "cpu_mean_percent"
                ),
                suffix="%",
            )
            + "/"
            + _format_optional(
                system.get(
                    "cpu_max_percent"
                ),
                suffix="%",
            )
        ),
        (
            "RAM medel/max: "
            + _format_optional(
                system.get(
                    "ram_mean_percent"
                ),
                suffix="%",
            )
            + "/"
            + _format_optional(
                system.get(
                    "ram_max_percent"
                ),
                suffix="%",
            )
        ),
        (
            "Max temperatur: "
            + _format_optional(
                system.get(
                    "temperature_max_celsius"
                ),
                suffix=" °C",
            )
        ),
    ]

    observations = report.get(
        "observations",
        [],
    )

    if observations:
        lines.append(
            "Observationer:"
        )

        for item in observations:
            lines.append(
                f"- {item}"
            )

    lines.append(
        (
            "Fysisk VENTUNO-verifiering: inte bedömd av rapporten; "
            "den följer separat enligt project_spec §21.2."
        )
    )

    return "\n".join(
        lines
    )
