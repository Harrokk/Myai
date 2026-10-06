import argparse
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


from core.config import load_settings_with_metadata
from core.config_validation import (
    validate_settings,
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
            "Validera MyAI-konfiguration utan "
            "att starta AI eller hårdvara."
        )
    )
    parser.add_argument(
        "--settings",
        default=None,
    )
    parser.add_argument(
        "--ventuno",
        action="store_true",
        help=(
            "Validera den dedikerade VENTUNO-profilen "
            "och VENTUNO-specifika krav."
        ),
    )
    return parser.parse_args()


def main():
    args = _arguments()
    path = (
        VENTUNO_PROFILE
        if args.ventuno
        else args.settings
    )
    loaded = load_settings_with_metadata(
        path
    )
    settings = loaded[
        "settings"
    ]
    metadata = loaded[
        "metadata"
    ]

    if metadata.get(
        "migration_changed",
        False,
    ):
        print(
            "[WARN] config_migrated_in_memory: "
            "Äldre konfiguration migrerades endast i minnet; "
            "källfilen ändrades inte."
        )

    result = validate_settings(
        settings,
        require_ventuno_profile=(
            args.ventuno
        ),
    )

    for item in result[
        "warnings"
    ]:
        print(
            f"[WARN] {item['code']}: "
            f"{item['message']}"
        )

    for item in result[
        "errors"
    ]:
        print(
            f"[FAIL] {item['code']}: "
            f"{item['message']}"
        )

    if result["valid"]:
        print(
            "Konfigurationen är giltig."
        )
        return 0

    print(
        "Konfigurationen har blockerande fel."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
