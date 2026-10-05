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


from core.config import DEFAULT_SETTINGS
from core.config_schema import (
    find_unknown_config_keys,
    migrate_config_document,
)


def _arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Read-only preview of MyAI config schema migration. "
            "Never rewrites the source file."
        )
    )
    parser.add_argument(
        "settings",
        help="Config/profile JSON to inspect.",
    )
    return parser.parse_args()


def main():
    args = _arguments()
    path = Path(
        args.settings
    )

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        raw = json.load(
            handle
        )

    migration = migrate_config_document(
        raw
    )
    unknown = find_unknown_config_keys(
        migration[
            "document"
        ],
        DEFAULT_SETTINGS,
    )

    output = {
        "source_path": str(
            path
        ),
        "source_version": migration[
            "source_version"
        ],
        "effective_version": migration[
            "effective_version"
        ],
        "changed": migration[
            "changed"
        ],
        "steps": migration[
            "steps"
        ],
        "unknown_keys": unknown,
        "candidate": migration[
            "document"
        ],
        "source_file_modified": False,
    }

    print(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return (
        0
        if not unknown
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
