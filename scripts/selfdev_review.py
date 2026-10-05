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
from core.selfdev_review import (
    build_selfdev_review,
)
from core.selfdev_workspace import (
    SelfDevWorkspace,
)


def _arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Visa exakt selfdev-diff, verifieringsstatus "
            "och source-drift före eventuell promotion."
        )
    )
    parser.add_argument(
        "session",
    )
    return parser.parse_args()


def main():
    args = _arguments()
    settings = load_settings()
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

    workspace = SelfDevWorkspace(
        PROJECT_ROOT,
        args.session,
        selfdev_root=root,
    )

    if not workspace.metadata_path.exists():
        print(
            "Selfdev-sessionen finns inte."
        )
        return 2

    review = build_selfdev_review(
        workspace
    )
    verification = (
        review[
            "verification"
        ]
        or {}
    )

    print(
        f"Session: {review['session_id']}"
    )
    print(
        f"Changed: {len(review['changed'])}"
    )
    print(
        f"Added: {len(review['added'])}"
    )
    print(
        f"Deleted: {len(review['deleted'])}"
    )
    print(
        "Verification passed: "
        f"{verification.get('passed', False)}"
    )
    print(
        "Source drift: "
        f"{len(review['source_drift'])}"
    )
    print()
    print(
        review["diff"]
        or "(ingen diff)"
    )

    if review[
        "diff_truncated"
    ]:
        print()
        print(
            "VARNING: diffen trunkerades."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
