import argparse
from pathlib import Path
import signal
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
from core.config_validation import (
    require_valid_settings,
)
from core.runtime_service import (
    MyAIRuntimeService,
)
from core.ventuno_preflight import (
    run_ventuno_preflight,
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
            "Headless MyAI runtime for "
            "Arduino VENTUNO Q."
        )
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help=(
            "Hoppa över fysisk VENTUNO-preflight. "
            "Endast för utveckling/felsökning."
        ),
    )
    return parser.parse_args()


def main():
    args = _arguments()
    settings = load_settings(
        PROFILE_PATH
    )
    require_valid_settings(
        settings,
        require_ventuno_profile=True,
    )

    if (
        settings.get(
            "runtime",
            {},
        ).get(
            "require_preflight",
            True,
        )
        and not args.skip_preflight
    ):
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
                "Headless runtime startades inte."
            )
            return 2

    service = MyAIRuntimeService(
        settings,
        PROJECT_ROOT,
    )

    def stop_handler(
        signum,
        frame,
    ):
        service.stop()

    signal.signal(
        signal.SIGTERM,
        stop_handler,
    )
    signal.signal(
        signal.SIGINT,
        stop_handler,
    )

    service.start()
    print(
        "MyAI VENTUNO headless runtime startad."
    )

    try:
        service.wait()
    finally:
        service.stop()

    print(
        "MyAI VENTUNO headless runtime stoppad."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
