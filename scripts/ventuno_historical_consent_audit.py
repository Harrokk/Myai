"""Source-only audit: historical consent text NEVER reauthorizes hardware.

These 12 old workflow jobs have real microphone, playback, model inference,
installation or possible DSP effects. They remain in history for review but
must be inert in the candidate. No workflow, native library or audio is run.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BOARD_JOBS = {
    "ventuno-geniex-lazy-htp-once.yml": "board-one-existing-request",
    "ventuno-microphone-consent-once.yml": "microphone",
    "ventuno-microphone-plughw-once.yml": "microphone",
    "ventuno-ollama-installed-voice-reply-once.yml": "local_reply",
    "ventuno-ollama-user-install-once.yml": "provision",
    "ventuno-usb-dialog-consent-once.yml": "one_turn",
    "ventuno-usb-live-dialog-consent-once.yml": "dialogue",
    "ventuno-usb-microphone-consent-once.yml": "usb_microphone",
    "ventuno-usb-microphone-corrected-once.yml": "usb_microphone",
    "ventuno-usb-ollama-headphones-retry-once.yml": "dialogue",
    "ventuno-usb-ollama-voice-consent-once.yml": "dialogue",
    "ventuno-usb-speaker-consent-once.yml": "speaker",
}
HEADER = re.compile(r"(?m)^  ([a-z][a-z0-9_-]*):[ \t]*$")


def audit(root=ROOT):
    verdicts = {}
    for filename, board_job in BOARD_JOBS.items():
        ok = False
        file = Path(root) / ".github/workflows" / filename
        try:
            if file.is_symlink() or not file.is_file():
                raise ValueError("missing")
            text = file.read_text(encoding="utf-8")
            if text.count("\njobs:\n") != 1:
                raise ValueError("unexpected-jobs")
            body = text.split("\njobs:\n", 1)[1]
            headers = list(HEADER.finditer(body))
            matches = [i for i, h in enumerate(headers) if h.group(1) == board_job]
            if len(matches) != 1:
                raise ValueError("missing-or-duplicate")
            i = matches[0]
            section = body[headers[i].end():(
                headers[i+1].start() if i+1 < len(headers) else len(body)
            )]
            first = next((
                line.strip() for line in section.splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ), "")
            # This specifically gates the job, not a nested step/permission,
            # and verifies no extra non-mocked device job was introduced.
            other_board = [
                body[h.end():(headers[k+1].start()
                             if k+1 < len(headers) else len(body))]
                for k, h in enumerate(headers) if k != i
            ]
            other_board_suspicious = any(
                "self-hosted" in block or "qnn-net-run" in block
                or "arecord" in block or "aplay" in block
                for block in other_board
            )
            ok = (first == "if: false" and not other_board_suspicious
                  and re.search(r"(?m)^    runs-on: \[self-hosted, Linux, ARM64, ventuno-q\]$", section) is not None)
        except (OSError, UnicodeError, ValueError):
            ok = False
        verdicts[filename] = ok
    return {
        "status": "historical-physical-jobs-quarantined" if all(verdicts.values())
                  else "blocked-historical-physical-job-reachable",
        "files": len(BOARD_JOBS),
        "confirmed_job_disabled": sum(verdicts.values()),
        "results": verdicts,
        "actual_audio_or_model_executed": False,
        "old_consent_reused": False,
        "release_authorized": False,
    }


def main():
    report = audit()
    print("MYAI_HISTORICAL_PHYSICAL_JOBS_JSON=" + json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "historical-physical-jobs-quarantined" else 2


if __name__ == "__main__":
    raise SystemExit(main())
