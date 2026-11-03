"""Disposable hosted ARM64-only download of exactly pinned public STT weights.

No user input, shell, SSH, HF credentials, hidden model config, proxy override
or persistent cache. Every download must match the reviewed public SHA256
and byte count before it can be used. Sources/weights never enter repo.
"""
import os
from pathlib import Path
import subprocess
import sys

from core.voice_candidate_hosted_manifest import validate_hosted_manifest
from scripts.ci_native_model_backed_swedish_smoke import (
    require_hosted_runner, verify_downloaded_artifact,
)


def download_all():
    root = require_hosted_runner()
    parent = root / "myai-native-model-files"
    if parent.exists():
        raise RuntimeError("Cannot reuse preexisting model directory")
    parent.mkdir(mode=0o700)
    for artifact in validate_hosted_manifest():
        dest = parent / artifact.profile
        dest.mkdir(mode=0o700)
        path = dest / artifact.filename
        cmd = [
            "curl", "--fail", "--location", "--silent",
            "--proto", "=https", "--proto-redir", "=https",
            "--show-error", "--retry", "2", "--retry-delay", "3",
            "--connect-timeout", "15", "--max-time", "1400",
            "--max-filesize", str(artifact.byte_size + 512),
            "--output", str(path),
            artifact.url,
        ]
        try:
            subprocess.run(
                cmd, check=True, timeout=1450,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env={
                    "PATH": "/usr/bin:/bin",
                    "HOME": "/",
                    "LANG": "C.UTF-8",
                    "HF_HUB_DISABLE_TELEMETRY": "1",
                },
            )
            verify_downloaded_artifact(artifact, path)
        except Exception:
            # The private model test is DENIED, not downgraded to an
            # unpinned alternative or cached model.
            path.unlink(missing_ok=True)
            raise RuntimeError("Pinned model download/integrity denied") from None
        path.chmod(0o444)
        dest.chmod(0o555)
    parent.chmod(0o555)
    return parent


def main():
    try:
        download_all()
        print("PINNED_PUBLIC_MODEL_FILES: VERIFIED")
        return 0
    except Exception:
        print("PINNED_PUBLIC_MODEL_FILES: DENIED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
