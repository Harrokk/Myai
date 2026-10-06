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
from core.selfdev_promote import (
    SelfDevPromotionManager,
)
from core.selfdev_workspace import (
    SelfDevWorkspace,
)


def _arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Promota en verifierad MyAI selfdev-session. "
            "Kräver exakt manuell approval-frase."
        )
    )
    parser.add_argument(
        "session",
    )
    parser.add_argument(
        "--approve",
        required=True,
    )
    return parser.parse_args()


def _workspace(
    settings,
    session,
):
    raw = settings.get(
        "selfdev",
        {},
    ).get(
        "workspace_root",
        "runtime/selfdev",
    )
    root = Path(
        raw
    )

    if not root.is_absolute():
        root = (
            PROJECT_ROOT
            / root
        )

    return SelfDevWorkspace(
        PROJECT_ROOT,
        session,
        selfdev_root=root,
    )


def main():
    args = _arguments()
    settings = load_settings()
    workspace = _workspace(
        settings,
        args.session,
    )
    manager = (
        SelfDevPromotionManager(
            workspace,
            settings,
        )
    )

    try:
        record = manager.promote(
            args.approve
        )
    except Exception as error:
        print(
            f"Promotion nekad/misslyckad: {error}"
        )
        return 2

    print(
        f"Promotion: {record['promotion_id']}"
    )
    print(
        f"Changed: {len(record['changed'])}"
    )
    print(
        f"Added: {len(record['added'])}"
    )
    print(
        "Rollback-backup skapades före aktiv filskrivning."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
