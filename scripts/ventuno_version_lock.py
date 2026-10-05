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
from core.config_validation import (
    require_valid_settings,
)
from core.deployment_lock import (
    build_lock_candidate,
    collect_ventuno_stack,
    load_lock_manifest,
    resolve_project_path,
    verify_ventuno_stack,
    write_json_atomic,
)


PROFILE_PATH = (
    PROJECT_ROOT
    / "config"
    / "profiles"
    / "ventuno_q.json"
)
DEFAULT_CANDIDATE_PATH = (
    PROJECT_ROOT
    / "runtime"
    / "ventuno_stack_lock_candidate.json"
)


def _arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Fånga eller verifiera VENTUNO-stackens "
            "versionslås. Inga paket installeras och "
            "ingen hårdvara styrs."
        )
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    capture = subparsers.add_parser(
        "capture",
        help=(
            "Skapa en olåst kandidat under runtime/ "
            "från faktiskt observerade versioner."
        ),
    )
    capture.add_argument(
        "--output",
        default=str(
            DEFAULT_CANDIDATE_PATH
        ),
    )

    verify = subparsers.add_parser(
        "verify",
        help=(
            "Verifiera observerad stack mot ett "
            "manuellt granskat lås."
        ),
    )
    verify.add_argument(
        "--lock",
        default="",
    )

    return parser.parse_args()


def _print_mismatches(result):
    for item in result[
        "mismatches"
    ]:
        print(
            "MISMATCH "
            f"{item['path']}: "
            f"expected={item['expected']!r}, "
            f"observed={item['observed']!r}"
        )


def main():
    args = _arguments()
    settings = load_settings(
        PROFILE_PATH
    )
    require_valid_settings(
        settings,
        require_ventuno_profile=True,
    )
    observed = collect_ventuno_stack(
        settings,
        PROJECT_ROOT,
    )

    if args.command == "capture":
        candidate = (
            build_lock_candidate(
                observed
            )
        )
        path = write_json_atomic(
            args.output,
            candidate,
        )
        print(
            "VENTUNO versionslåskandidat sparad:"
        )
        print(
            f" - {path}"
        )
        print(
            "Kandidaten är medvetet locked=false. "
            "Granska den på den fysiska VENTUNO:n "
            "innan ett permanent lås skapas."
        )
        return 0

    configured = settings.get(
        "deployment_lock",
        {},
    )
    raw_lock = (
        args.lock
        or configured.get(
            "lock_path",
            "",
        )
    )
    lock_path = resolve_project_path(
        PROJECT_ROOT,
        raw_lock,
    )

    try:
        manifest = load_lock_manifest(
            lock_path
        )
    except Exception as error:
        print(
            "Versionslåset kunde inte läsas: "
            f"{error}"
        )
        return 2

    result = verify_ventuno_stack(
        manifest,
        observed,
    )

    for error in result[
        "errors"
    ]:
        print(
            f"ERROR {error}"
        )

    _print_mismatches(
        result
    )

    if result["passed"]:
        print(
            "VENTUNO-stack matchar versionslåset."
        )
        return 0

    print(
        "VENTUNO-stack matchar inte ett giltigt "
        "versionslås."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
