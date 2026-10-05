import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parent.parent


def main():
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_fault_injection.py",
    ]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
    )
    return int(
        result.returncode
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
