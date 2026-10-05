import argparse
import json
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
from core.geniex_supervisor import (
    GenieXSupervisor,
)
from core.health_status import (
    write_health_state,
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
    / "geniex_watchdog.jsonl"
)


def _state_path(settings):
    raw = (
        settings.get(
            "geniex_supervisor",
            {},
        )
        .get(
            "state_path",
            "runtime/geniex_health.json",
        )
    )
    path = Path(raw)

    if not path.is_absolute():
        path = (
            PROJECT_ROOT
            / path
        )

    return path


def _arguments():
    parser = argparse.ArgumentParser(
        description=(
            "MyAI GenieX watchdog. "
            "Restart requires explicit profile opt-in."
        )
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=10.0,
    )
    parser.add_argument(
        "--once",
        action="store_true",
    )
    parser.add_argument(
        "--log",
        default=str(
            DEFAULT_LOG_PATH
        ),
    )
    return parser.parse_args()


def _append(path, record):
    target = Path(path)
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with target.open(
        "a",
        encoding="utf-8",
    ) as handle:
        handle.write(
            json.dumps(
                record,
                ensure_ascii=False,
                separators=(
                    ",",
                    ":",
                ),
            )
            + "\n"
        )


def main():
    args = _arguments()
    settings = load_settings(
        PROFILE_PATH
    )
    supervisor = (
        GenieXSupervisor(
            settings
        )
    )

    if not supervisor.enabled:
        print(
            "GenieX supervisor är avstängd "
            "i VENTUNO-profilen."
        )
        return 2

    interval = max(
        1.0,
        float(
            args.interval_seconds
        ),
    )

    print(
        "MyAI GenieX watchdog startad."
    )
    print(
        f"Readiness: "
        f"{supervisor.models_url}"
    )
    print(
        "Automatisk restart: "
        f"{supervisor.restart_enabled}"
    )

    try:
        while True:
            result = (
                supervisor
                .supervise_once()
            )
            record = {
                "unix_time": time.time(),
                **result,
            }
            _append(
                args.log,
                record,
            )
            write_health_state(
                _state_path(
                    settings
                ),
                result,
            )

            check = result[
                "check"
            ]
            restart = result[
                "restart"
            ]

            print(
                "healthy="
                f"{check.get('healthy')} "
                "failures="
                f"{check.get('consecutive_failures')} "
                "restart="
                f"{restart.get('attempted')}"
            )

            if args.once:
                break

            time.sleep(
                interval
            )
    except KeyboardInterrupt:
        print(
            "GenieX watchdog stoppad."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
