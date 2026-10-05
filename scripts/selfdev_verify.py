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
from core.selfdev_verify import (
    SelfDevVerifier,
)
from core.selfdev_workspace import (
    SelfDevWorkspace,
)


def _arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Verifiera en MyAI selfdev-session i Bubblewrap."
        )
    )
    parser.add_argument(
        "session",
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

    workspace = _workspace(
        settings,
        args.session,
    )

    if not workspace.metadata_path.exists():
        print(
            "Selfdev-sessionen finns inte."
        )
        return 2

    verifier = SelfDevVerifier(
        workspace,
        timeout_seconds=config.get(
            "verification_timeout_seconds",
            300,
        ),
    )

    try:
        result = verifier.verify()
    except Exception as error:
        print(
            f"Verifieringen kunde inte köras: {error}"
        )
        return 2

    print(
        f"Sandbox: {result['sandbox']}"
    )
    print(
        f"Passed: {result['passed']}"
    )
    print(
        f"Return code: {result['returncode']}"
    )
    print(
        f"Changed: {len(result['changed'])}"
    )
    print(
        f"Added: {len(result['added'])}"
    )

    if result[
        "source_drift"
    ]:
        print(
            "VARNING: aktiv källkod har driftat sedan sessionen skapades."
        )

    return (
        0
        if result[
            "passed"
        ]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
