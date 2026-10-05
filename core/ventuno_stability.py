from pathlib import Path
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
