import argparse
import getpass
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


from core.systemd_units import (
    write_ventuno_units,
)


DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "runtime"
    / "systemd"
)


def _arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Generera systemd-enheter för MyAI VENTUNO. "
            "Skriptet installerar eller aktiverar ingenting."
        )
    )
    parser.add_argument(
        "--output-dir",
        default=str(
            DEFAULT_OUTPUT
        ),
    )
    parser.add_argument(
        "--user",
        default=getpass.getuser(),
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
    )
    return parser.parse_args()


def main():
    args = _arguments()
    written = write_ventuno_units(
        args.output_dir,
        PROJECT_ROOT,
        args.python,
        args.user,
    )

    print(
        "Systemd-enheter genererade:"
    )

    for path in written:
        print(
            f" - {path}"
        )

    print()
    print(
        "Inga filer installerades i /etc/systemd/system "
        "och inga tjänster aktiverades."
    )
    print(
        "Inspektera enheterna på den riktiga VENTUNO:n "
        "innan eventuell installation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
