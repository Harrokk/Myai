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


from core.config import load_settings
from core.selfdev_workspace import (
    SelfDevWorkspace,
)


def _arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Skapa en isolerad MyAI selfdev-staging-session. "
            "Ingen aktiv källkod ändras."
        )
    )
    parser.add_argument(
        "--session",
        default=None,
    )
    return parser.parse_args()


def _selfdev_root(
    settings,
):
    raw = settings.get(
        "selfdev",
        {},
    ).get(
        "workspace_root",
        "runtime/selfdev",
    )
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
    settings = load_settings()
    config = settings.get(
        "selfdev",
        {},
    )

    if not config.get(
        "enabled",
        False,
    ):
        print(
            "Selfdev är avstängt i konfigurationen."
        )
        return 2

    workspace = SelfDevWorkspace.create(
        PROJECT_ROOT,
        args.session,
        selfdev_root=_selfdev_root(
            settings
        ),
    )

    print(
        f"Session: {workspace.session_id}"
    )
    print(
        f"Staging: {workspace.workspace_root}"
    )
    print(
        "Aktiv källkod har inte ändrats."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
