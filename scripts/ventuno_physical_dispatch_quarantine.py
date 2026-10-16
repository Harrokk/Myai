"""Fail-closed, source-only quarantine of five legacy on-demand board jobs.

Any later physical experiment must use a newly reviewed, separately
approved workflow. The originals remain available in the Git history.
No device, audio, NPU, service or network access occurs here.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVED = (
    "ventuno-tiny-qnn-htp-once.yml",
    "ventuno-tiny-qnn-htp-adsp-retry-once.yml",
    "ventuno-live-qairt-synthetic-once.yml",
    "ventuno-qnn-tiny-cpu-once.yml",
    "ventuno-htp-local-recovery-canary.yml",
)


def inspect(root=ROOT):
    statuses = []
    for name in ARCHIVED:
        path = Path(root) / ".github/workflows" / name
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 2048:
                statuses.append(False)
                continue
            source = path.read_text(encoding="utf-8")
            valid = all((
                "ARCHIVED - NO HARDWARE EXECUTION" in source,
                "  workflow_dispatch:" in source,
                "    if: false" in source,
                "    runs-on: ubuntu-24.04" in source,
                "  push:" not in source,
                "self-hosted" not in source,
                "MYAI_ALLOW_" not in source,
                "qnn-net-run" not in source,
                "arecord" not in source,
                "aplay" not in source,
                "systemctl" not in source,
                "actions/checkout" not in source,
                "pip install" not in source,
                "permissions:\n  contents: read" in source,
            ))
            statuses.append(valid)
        except (OSError, UnicodeError, ValueError):
            statuses.append(False)
    valid = len(statuses) == len(ARCHIVED) and all(statuses)
    return {
        "status": "five-hardware-dispatches-archived-source-only"
                  if valid else "blocked-legacy-hardware-dispatch-quarantine",
        "archived_expected": len(ARCHIVED),
        "archived_verified": sum(statuses),
        "quarantine_passed": valid,
        "all_other_workflows_released": False,
        "physical_htp_or_audio_test_authorized": False,
        "system_services_changed": False,
        "runner_started_by_this_check": False,
    }


if __name__ == "__main__":
    import json
    print("MYAI_HARDWARE_DISPATCH_QUARANTINE_JSON=" +
          json.dumps(inspect(), sort_keys=True))
    raise SystemExit(0 if inspect()["quarantine_passed"] else 2)
