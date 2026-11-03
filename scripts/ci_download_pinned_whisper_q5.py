"""GitHub-hosted-only public Q5 model fetch; exact SHA256 required.

No HF credentials, shell, caches, private audio, or device side effects.
"""
import os
from pathlib import Path
import subprocess
import sys

from core.voice_candidate_quantized_manifest import (
    FILENAME, MAX_BYTES, PROFILE, quantized_release_url,
    verify_quantized_file,
)
from scripts.ci_native_model_backed_swedish_smoke import require_hosted_runner


def main():
    try:
        root = require_hosted_runner()
        parent = root / "myai-whisper-q5-test-weights"
        if parent.exists():
            raise RuntimeError("Unexpected model cache")
        parent.mkdir(mode=0o700)
        directory = parent / PROFILE
        directory.mkdir(mode=0o700)
        target = directory / FILENAME
        command = [
            "curl", "--fail", "--location", "--silent",
            "--proto", "=https", "--proto-redir", "=https",
            "--retry", "2", "--retry-delay", "3",
            "--connect-timeout", "15", "--max-time", "1000",
            "--max-filesize", str(MAX_BYTES),
            "--output", str(target), quantized_release_url(),
        ]
        subprocess.run(
            command, check=True, timeout=1040, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "HOME": "/", "LANG": "C.UTF-8"},
        )
        verify_quantized_file(target)
        target.chmod(0o444)
        directory.chmod(0o555)
        parent.chmod(0o555)
        print("HOSTED_PINNED_WHISPER_Q5: VERIFIED")
        return 0
    except Exception:
        print("HOSTED_PINNED_WHISPER_Q5: DENIED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
