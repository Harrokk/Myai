"""Operator-only local voice marker reconciliation; never a MyAI tool.

Run explicitly outside MyAI:
  python -m scripts.voice_write_reconcile --project-root /trusted/MyAI inspect
  python -m scripts.voice_write_reconcile --project-root /trusted/MyAI prepare
  python -m scripts.voice_write_reconcile --project-root /trusted/MyAI release TOKEN

For prepare/release a human must have the local controlling TTY and
must have independently inspected external effects and stopped all writers.
"""
import argparse
from pathlib import Path
import sys

from core.voice_write_recovery import (
    ATTESTATION_PREFIX,
    VoiceWriteReconciliation,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline human-only MyAI voice write reconciliation"
    )
    parser.add_argument("--project-root", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("inspect")
    sub.add_parser("prepare")
    release = sub.add_parser("release")
    release.add_argument("token", help="32-character review ticket identifier")
    arguments = parser.parse_args(argv)

    if arguments.action != "inspect" and not sys.stdin.isatty():
        print("Interactive local terminal required; marker unchanged.")
        return 2

    recovery = VoiceWriteReconciliation(arguments.project_root)
    try:
        if arguments.action == "inspect":
            state = recovery.inspect()
            print("Voice write review:", state["status"])
            return 0

        if arguments.action == "prepare":
            print("Only proceed after inspecting actual external effects.")
            if input("Type PREPARE REVIEW TICKET: ") != "PREPARE REVIEW TICKET":
                print("Review not prepared; marker unchanged.")
                return 2
            ticket = recovery.prepare()
            print("Private review ticket:", ticket)
            print("Marker remains locked. Stop ALL MyAI writers before release.")
            return 0

        assert arguments.action == "release"
        print("Verify actual side effects and stop ALL writers first.")
        expected = ATTESTATION_PREFIX + arguments.token
        if input("Type exact review attestation: ") != expected:
            print("Approval mismatch; marker unchanged.")
            return 2
        if not recovery.finalize(arguments.token, expected):
            print("Release denied; marker remains locked.")
            return 2
        print("Review receipt stored. Restart MyAI deliberately if appropriate.")
        return 0
    except (OSError, ValueError, TypeError):
        # A storage error can occur AFTER the old marker has been
        # unlinked. Do not falsely assert it is still present.
        print(
            "Reconciliation outcome uncertain. Inspect marker and "
            "receipt before any further action; do not retry the write."
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
