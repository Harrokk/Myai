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
from core.ventuno_preflight import (
    run_ventuno_preflight,
)


PROFILE_PATH = (
    PROJECT_ROOT
    / "config"
    / "profiles"
    / "ventuno_q.json"
)
REPORT_PATH = (
    PROJECT_ROOT
    / "runtime"
    / "ventuno_preflight_report.json"
)


def main():
    settings = load_settings(
        PROFILE_PATH
    )
    result = run_ventuno_preflight(
        settings
    )

    print("=" * 60)
    print("MyAI VENTUNO Q preflight")
    print("=" * 60)
    print(
        "Detta test är read-only: "
        "ingen STM32-anslutning, GPIO-skrivning "
        "eller AI-inference utförs."
    )
    print()

    for item in result["checks"]:
        print(
            f"[{item['status']}] "
            f"{item['name']} - "
            f"{item['details']}"
        )

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    REPORT_PATH.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        f"Rapport sparad: "
        f"{REPORT_PATH}"
    )

    if result["passed"]:
        print(
            "Grundläggande VENTUNO-preflight är godkänd."
        )
        return 0

    print(
        f"Preflight har "
        f"{result['failure_count']} blockerande fel."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
