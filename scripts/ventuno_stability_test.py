import argparse
from pathlib import Path
import sys
import time


PROJECT_ROOT = Path(
    __file__
).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


from core.config import load_settings
from core.llm_factory import build_llm_client
from core.ventuno_preflight import (
    run_ventuno_preflight,
)
from core.ventuno_stability import (
    VentunoStabilityLogger,
    collect_system_sample,
    measure_llm_iteration,
)


PROFILE_PATH = (
    PROJECT_ROOT
    / "config"
    / "profiles"
    / "ventuno_q.json"
)
DEFAULT_LOG_PATH = (
    PROJECT_ROOT
    / "runtime"
    / "ventuno_stability.jsonl"
)
DEFAULT_PROMPT = (
    "Svara exakt med texten: "
    "MyAI VENTUNO stability OK"
)


def _arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Read-mostly stability harness for "
            "MyAI on VENTUNO Q."
        )
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=72.0,
        help="Total testtid i timmar.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=60.0,
        help=(
            "Tid mellan iterationernas start."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=300.0,
        help="Timeout per LLM-anrop.",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="Ofarlig stabilitetsprompt.",
    )
    parser.add_argument(
        "--log",
        default=str(
            DEFAULT_LOG_PATH
        ),
        help="JSONL-loggfil.",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help=(
            "Hoppa över preflight. "
            "Använd endast vid felsökning."
        ),
    )
    return parser.parse_args()


def main():
    args = _arguments()
    settings = load_settings(
        PROFILE_PATH
    )

    if not args.skip_preflight:
        preflight = (
            run_ventuno_preflight(
                settings
            )
        )

        if not preflight[
            "passed"
        ]:
            print(
                "VENTUNO preflight har "
                "blockerande fel. "
                "Stabilitetstestet startades inte."
            )
            return 2

    duration_seconds = max(
        1.0,
        float(args.hours)
        * 3600.0,
    )
    interval_seconds = max(
        1.0,
        float(
            args.interval_seconds
        ),
    )
    timeout_seconds = max(
        1.0,
        float(
            args.timeout_seconds
        ),
    )

    llm = build_llm_client(
        settings
    )
    logging_config = settings.get(
        "logging",
        {},
    )
    logger = VentunoStabilityLogger(
        args.log,
        max_bytes=logging_config.get(
            "jsonl_max_bytes",
            5_000_000,
        ),
        backups=logging_config.get(
            "jsonl_backups",
            5,
        ),
    )

    started = time.monotonic()
    iterations = 0
    failures = 0

    print(
        "MyAI VENTUNO stability test"
    )
    print(
        f"Planerad tid: "
        f"{duration_seconds / 3600:.2f} h"
    )
    print(
        f"Intervall: "
        f"{interval_seconds:.1f} s"
    )
    print(
        f"Logg: {args.log}"
    )
    print(
        "Inga STM32/GPIO-skrivningar "
        "utförs av detta test."
    )

    try:
        while (
            time.monotonic()
            - started
            < duration_seconds
        ):
            iteration_started = (
                time.monotonic()
            )
            llm_result = (
                measure_llm_iteration(
                    llm,
                    args.prompt,
                    timeout=(
                        timeout_seconds
                    ),
                )
            )
            system_sample = (
                collect_system_sample()
            )
            record = logger.append(
                llm_result,
                system_sample,
            )

            iterations += 1

            if not llm_result[
                "success"
            ]:
                failures += 1

            backend = (
                llm_result[
                    "llm_runtime"
                ].get(
                    "active_backend",
                    "primary",
                )
            )
            print(
                f"#{record['sequence']} "
                f"ok={llm_result['success']} "
                f"backend={backend} "
                f"first={llm_result['first_chunk_seconds']} "
                f"total={llm_result['total_seconds']} "
                f"ram={system_sample['ram_percent']}%"
            )

            elapsed = (
                time.monotonic()
                - iteration_started
            )
            remaining = (
                interval_seconds
                - elapsed
            )

            if remaining > 0:
                time.sleep(
                    remaining
                )
    except KeyboardInterrupt:
        print(
            "Stabilitetstestet avbröts "
            "med Ctrl+C."
        )

    print(
        f"Iterationer: {iterations}, "
        f"fel: {failures}"
    )

    return (
        0
        if failures == 0
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
