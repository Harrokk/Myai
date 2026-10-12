"""Download a tiny licensed public Swedish pronunciation fixture, NOT user audio.

Attribution: 'Sv-svenska.ogg', native speaker Peter Isotalo, Wikimedia
Commons, GFDL / CC BY-SA 3.0. https://commons.wikimedia.org/wiki/File:Sv-svenska.ogg
Fixed Commons canonical upload URL, exact SHA1/length and Ogg magic.
Only writes a fixed basename within the disposable GitHub RUNNER_TEMP.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

SOURCE = "https://upload.wikimedia.org/wikipedia/commons/e/e3/Sv-svenska.ogg"
CREDIT = "Peter Isotalo; Wikimedia Commons; CC BY-SA 3.0 / GFDL"
EXPECTED_SHA1 = "817c8f149e5f3b53c0e8200de5a38bfa42756b5a"
EXPECTED_BYTES = 22879
MAX_BYTES = 30_000


def validate_swedish_sample(raw: bytes) -> bool:
    return (
        len(raw) == EXPECTED_BYTES and raw.startswith(b"OggS")
        and hashlib.sha1(raw).hexdigest() == EXPECTED_SHA1
    )


def download_fixture(root: Path) -> dict[str, object]:
    out: dict[str, object] = {
        "status": "no-go-public-swedish-audio",
        "license_attribution": CREDIT,
        "origin": "Wikimedia Commons Sv-svenska.ogg",
        "sample_verified": False,
        "bytes_downloaded": 0,
        "microphone_opened": False,
        "user_audio_uploaded": False,
    }
    try:
        if root.is_symlink() or not root.is_dir():
            return out
        target = root / "myai-whisper-swedish-word.ogg"
        if target.exists() or target.is_symlink():
            out["status"] = "reject-existing-swedish-audio"
            return out
        request = urllib.request.Request(
            SOURCE, headers={"User-Agent": "MyAI-Whisper-ReproTest/1.0"}
        )
        with urllib.request.urlopen(request, timeout=20) as connection:
            # No alternative source hosts or arbitrary redirect chains.
            if connection.geturl() != SOURCE:
                out["status"] = "reject-audio-redirect"
                return out
            raw = connection.read(MAX_BYTES + 1)
    except (OSError, ValueError):
        out["status"] = "public-sample-download-unavailable"
        return out
    out["bytes_downloaded"] = len(raw)
    if not validate_swedish_sample(raw):
        out["status"] = "public-sample-integrity-mismatch"
        return out
    try:
        with target.open("xb") as handle:
            handle.write(raw)
    except OSError:
        out["status"] = "public-sample-write-unavailable"
        return out
    out["sample_verified"] = True
    out["status"] = "licensed-swedish-word-sample-verified"
    return out


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp", type=Path, required=True)
    args = parser.parse_args()
    result = download_fixture(args.runner_temp)
    print("Pinned Swedish reference pronunciation:", json.dumps(result, sort_keys=True))
    return 0 if result["sample_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
