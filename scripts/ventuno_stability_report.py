import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(
    __file__
).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


from core.config import load_settings
from core.ventuno_stability import (
    analyze_stability_log,
    format_stability_report,
)


PROFILE_PATH = (
    PROJECT_ROOT
    / "config"
    / "profiles"
    / "ventuno_q.json"
)


def _arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Read-only report for MyAI VENTUNO stability JSONL."
        )
    )
    parser.add_argument(
        "--log",
        default="",
        help=(
            "Valfri loggfil. Standard tas från stability_analysis.log_path."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Skriv maskinläsbar JSON i stället för text.",
    )
    return parser.parse_args()


def _resolve_path(
    raw,
):
    path = Path(
        raw
    )

    if not path.is_absolute():
        path = (
            PROJECT_ROOT
            / path
        )

    return path


def main():
    args = _arguments()
    settings = load_settings(
        PROFILE_PATH
    )
    config = settings.get(
        "stability_analysis",
        {},
    )
    logging_config = settings.get(
        "logging",
        {},
    )
    raw_path = (
        args.log.strip()
        or str(
            config.get(
                "log_path",
                "runtime/ventuno_stability.jsonl",
            )
        )
    )

    report = analyze_stability_log(
        _resolve_path(
            raw_path
        ),
        backups=logging_config.get(
            "jsonl_backups",
            5,
        ),
        max_records=config.get(
            "max_records",
            10_000,
        ),
        target_hours=config.get(
            "target_hours",
            72.0,
        ),
        trend_fraction=config.get(
            "trend_fraction",
            0.25,
        ),
        latency_degradation_ratio=config.get(
            "latency_degradation_ratio",
            1.25,
        ),
    )

    if args.json:
        print(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(
            format_stability_report(
                report
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
