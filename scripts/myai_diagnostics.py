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
        str(
            PROJECT_ROOT
        ),
    )


from core.config import load_settings
from core.diagnostics import (
    build_diagnostic_report,
    format_diagnostic_report,
)


def _arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Read-only combined MyAI diagnostics."
        )
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Skriv maskinläsbar JSON.",
    )
    parser.add_argument(
        "--settings",
        default="",
        help=(
            "Valfri settings/profile-fil. "
            "Ingen fysisk preflight körs."
        ),
    )
    return parser.parse_args()


def main():
    args = _arguments()
    settings = load_settings(
        args.settings
        if args.settings
        else None
    )
    report = build_diagnostic_report(
        settings,
        PROJECT_ROOT,
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
            format_diagnostic_report(
                report
            )
        )

    return (
        0
        if report[
            "configuration"
        ][
            "valid"
        ]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
