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


from core.config import (
    DEFAULT_SETTINGS_PATH,
    load_settings,
)
from core.config_schema import (
    compare_config_profiles,
)


VENTUNO_PROFILE = (
    PROJECT_ROOT
    / "config"
    / "profiles"
    / "ventuno_q.json"
)


def _arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Read-only comparison of two MyAI configuration profiles."
        )
    )
    parser.add_argument(
        "--left",
        default=str(
            DEFAULT_SETTINGS_PATH
        ),
    )
    parser.add_argument(
        "--right",
        default=str(
            VENTUNO_PROFILE
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
    )
    return parser.parse_args()


def main():
    args = _arguments()
    left = load_settings(
        args.left
    )
    right = load_settings(
        args.right
    )
    result = compare_config_profiles(
        left,
        right,
    )

    if args.json:
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(
            "MyAI config profile comparison"
        )
        print(
            "Skillnader: "
            f"{result['difference_count']}"
        )

        for item in result[
            "differences"
        ]:
            print(
                f"- {item['path']}: "
                f"{item['left']} -> "
                f"{item['right']}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
