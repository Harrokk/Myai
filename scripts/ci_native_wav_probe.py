"""Hosted-only model-free native decoder probe; never call on VENTUNO.

Runs two pinned upstream C++ *audio decoder* harnesses against the same tiny
synthetic 16-kHz mono PCM16 sealed Linux memfd. No models or audio recording.
Exit status alone counts as evidence, not CLI/inference readiness.
"""
import os
from pathlib import Path
import subprocess
import sys


def main(argv):
    if len(argv) != 3 or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        return 2
    if os.uname().machine != "aarch64":
        return 2
    # The fixed binaries must reside inside the disposable GitHub runner.
    root = Path(os.environ.get("RUNNER_TEMP", "/nonexistent")).resolve()
    if not root.is_dir():
        return 2
    binaries = [Path(value).resolve(strict=True) for value in argv[1:]]
    if any(root not in binary.parents or not binary.is_file() for binary in binaries):
        return 2

    from core.voice_candidate_audio_memfd import sealed_pcm16_wav_memfd

    synthetic_pcm = b"\x00\x00" * 8
    for binary in binaries:
        with sealed_pcm16_wav_memfd(synthetic_pcm) as (fd, path):
            args = [str(binary), path]
            options = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "cwd": "/",
                "env": {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                "timeout": 8,
                "check": False,
                "start_new_session": True,
            }
            # The private fd must NOT be inherited by default.
            unshared = subprocess.run(args, **options)
            if unshared.returncode == 0:
                return 3
            shared = subprocess.run(args, pass_fds=(fd,), **options)
            if shared.returncode != 0:
                return 4
    return 0


if __name__ == "__main__":
    try:
        code = main(sys.argv)
    except Exception:
        # No private native filesystem paths or audio are printed.
        code = 5
    sys.exit(code)
