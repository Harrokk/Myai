"""Read-only gate: historical board systemd-user timer canaries stay disabled.

Neither target is a real rollback verification. Its hosted mocked safety job
remains enabled. This checker never executes a service, timer, hardware or sudo.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
JOBS = {
    "ventuno-system-manager-timer-canary.yml": (
        "ventuno-system-timer-canary",
        ("mock-safety", "ventuno-system-timer-canary"),
        "mock-safety",
    ),
    "ventuno-htp-local-recovery-canary.yml": (
        "ventuno-sandbox-user-timer",
        ("offline-safety", "ventuno-sandbox-user-timer"),
        "offline-safety",
    ),
}
HEADER = re.compile(r"(?m)^  ([a-zA-Z][\w-]*):[ \t]*$")


def check(root=ROOT):
    results = {}
    for name, (disabled_job, expected, mocked) in JOBS.items():
        good = False
        path = root / ".github/workflows" / name
        try:
            if not path.is_file() or path.is_symlink():
                raise ValueError("missing-or-linked")
            source = path.read_text(encoding="utf-8")
            if source.count("\njobs:\n") != 1:
                raise ValueError("invalid-jobs")
            body = source.split("\njobs:\n", 1)[1]
            headers = list(HEADER.finditer(body))
            if tuple(m.group(1) for m in headers) != expected:
                raise ValueError("unexpected-jobs")
            blocks = {
                m.group(1): body[m.end():(
                    headers[i + 1].start() if i + 1 < len(headers)
                    else len(body)
                )]
                for i, m in enumerate(headers)
            }
            active = next((l.strip() for l in blocks[disabled_job].splitlines()
                           if l.strip() and not l.lstrip().startswith("#")), None)
            safe_mock = blocks[mocked]
            good = (
                active == "if: false"
                and "runs-on: ubuntu-24.04" in safe_mock
                and re.search(r"(?m)^    if: false[ \t]*$", safe_mock) is None
            )
        except (OSError, UnicodeError, ValueError, KeyError, StopIteration):
            good = False
        results[name] = good
    return {
        "status": "two-board-timer-jobs-inert" if all(results.values())
                  else "blocked-board-timer-job-still-reachable",
        "expected": 2,
        "disabled_verified": sum(results.values()),
        "results": results,
        "actual_timers_exercised": False,
        "out_of_band_recovery_verified": False,
        "production_restart_allowed": False,
        "physical_test_authorized": False,
    }


def main():
    report = check()
    print("MYAI_BOARD_TIMER_QUARANTINE_JSON=" + json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "two-board-timer-jobs-inert" else 2


if __name__ == "__main__":
    raise SystemExit(main())
