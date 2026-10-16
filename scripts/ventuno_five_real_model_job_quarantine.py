"""Verify five independently reviewed real-model jobs are inert on DRAFT.

Read-only repository source verification: no calls to GitHub Actions, board,
audio, device models, systemd, or external services. A job-level if:false is
necessary but not sufficient to authorize a future release.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent

# A separate mocked-only x86 sibling must remain available in the first file.
REQUIRED = {
    "ventuno-existing-geniex-one-shot-check.yml": (
        "board-single-existing-request",
        ("synthetic-safety", "board-single-existing-request"),
    ),
    "ventuno-piper-alma-swedish-stt.yml": ("compare", ("compare",)),
    "ventuno-public-dynamic-transcript.yml": ("verify", ("verify",)),
    "ventuno-synthetic-swedish-question-stt.yml": ("verify", ("verify",)),
    "ventuno-whisper-base-swedish-comparison.yml": ("compare", ("compare",)),
}
JOB_HEADER = re.compile(r"(?m)^  ([a-zA-Z][a-zA-Z0-9_-]*):[ \t]*$")


def verify(root=ROOT):
    results = {}
    for filename, (blocked, expected) in REQUIRED.items():
        safe = False
        path = root / ".github" / "workflows" / filename
        try:
            if path.is_file() and not path.is_symlink():
                source = path.read_text(encoding="utf-8")
                if source.count("\njobs:\n") != 1:
                    raise ValueError("ambiguous-job-section")
                jobs_text = source.split("\njobs:\n", 1)[1]
                headers = list(JOB_HEADER.finditer(jobs_text))
                if tuple(match.group(1) for match in headers) != expected:
                    raise ValueError("unexpected-job-set")
                blocks = {
                    match.group(1): jobs_text[
                        match.end(): headers[i + 1].start()
                        if i + 1 < len(headers) else len(jobs_text)
                    ]
                    for i, match in enumerate(headers)
                }
                first = next((
                    line.strip()
                    for line in blocks[blocked].splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                ), None)
                safe = first == "if: false"
                # Ensure only the physical board job in this mixed workflow
                # is archived, leaving synthetic mock-only CI operational.
                if filename == "ventuno-existing-geniex-one-shot-check.yml":
                    mock = blocks["synthetic-safety"]
                    safe = safe and "runs-on: ubuntu-24.04" in mock
                    safe = safe and not re.search(r"(?m)^    if: false[ \t]*$", mock)
        except (OSError, UnicodeError, ValueError, KeyError, StopIteration):
            safe = False
        results[filename] = bool(safe)
    return {
        "status": "five-real-inference-jobs-quarantined" if all(results.values())
                  else "blocked-real-inference-job-reachable",
        "checked_files": len(REQUIRED),
        "confirmed_inert": sum(results.values()),
        "results": results,
        "real_model_inference_performed": False,
        "release_authorized": False,
        "remainder_of_manual_workflows_automatically_approved": False,
    }


def main():
    report = verify()
    print("MYAI_FIVE_MODEL_JOB_QUARANTINE_JSON=" + json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "five-real-inference-jobs-quarantined" else 2


if __name__ == "__main__":
    raise SystemExit(main())
