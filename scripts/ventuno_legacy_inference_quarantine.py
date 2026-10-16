"""Source-only static verification of four disabled historical device jobs.

The files retain their bodies for review but no job can execute on this DRAFT.
This does not prove the other historical workflows are harmless.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
DISABLED = {
    "ventuno-diagnostics.yml": "diagnostics",
    "ventuno-live-qairt-synthetic-once.yml": "single-synthetic",
    "ventuno-tiny-qnn-htp-once.yml": "tiny-htp-once",
    "ventuno-qnn-tiny-cpu-once.yml": "one-cpu-fixture",
}


def verify(root=ROOT):
    per_file = {}
    for filename, job in DISABLED.items():
        path = root / ".github/workflows" / filename
        valid = False
        try:
            if path.is_file() and not path.is_symlink():
                contents = path.read_text(encoding="utf-8")
                # A job-level if:false must be the FIRST non-comment key in
                # the exact job block, not a disabled inner step or a comment.
                pattern = (r"(?m)^jobs:\s*\n  " + re.escape(job) +
                           r":\s*\n(?:    #[^\n]*\n)*    if: false\s*$")
                valid = len(re.findall(pattern, contents)) == 1
                # Expected single job in each historical file.
                jobs = re.findall(r"(?m)^  ([a-zA-Z][a-zA-Z0-9_-]*):\s*$",
                                  contents.split("\njobs:\n", 1)[-1])
                valid = valid and jobs == [job]
        except (OSError, UnicodeError):
            pass
        per_file[filename] = bool(valid)
    success = all(per_file.values())
    return {
        "status": "four-legacy-device-jobs-inert" if success
                  else "blocked-legacy-device-job-enabled",
        "checked_jobs": len(DISABLED),
        "confirmed_disabled": sum(per_file.values()),
        "results": per_file,
        "device_used": False,
        "release_authorized": False,
        "manual_dispatch_consent_inferred": False,
    }


def main():
    report = verify()
    print("MYAI_LEGACY_DEVICE_JOB_QUARANTINE_JSON=" +
          json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "four-legacy-device-jobs-inert" else 2


if __name__ == "__main__":
    raise SystemExit(main())
