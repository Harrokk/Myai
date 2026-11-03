"""Run complete pinned native STT CLI *without* models on hosted ARM64.

This probes startup, help flags and Canary's model-free WAV path. It is NOT
a model-backed transcription test or a trusted runtime release certificate.
Actual spoken content is NEVER used or logged.
"""
import os
from pathlib import Path
import subprocess
import sys

from core.voice_candidate_audio_memfd import sealed_pcm16_wav_memfd


def _run(argv, *, pass_fds=()):
    return subprocess.run(
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, pass_fds=pass_fds,
        cwd="/",
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
             "LC_ALL": "C.UTF-8", "HOME": "/",
             "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
        timeout=8, check=False, start_new_session=True,
    )


def main(argv):
    if (len(argv) != 3
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or os.uname().machine != "aarch64"):
        return 2
    try:
        root = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
        binaries = [Path(x).resolve(strict=True) for x in argv[1:]]
        if any(root not in b.parents or not b.is_file() or b.is_symlink()
               for b in binaries):
            return 3
        canary, whisper = binaries
        if canary.name != "transcribe-cli" or whisper.name != "whisper-cli":
            return 3
        # After readelf checks, verify real whole-CLI binaries can start.
        for binary in binaries:
            help_result = _run([str(binary), "--help"])
            if (help_result.returncode != 0
                    or len(help_result.stdout) + len(help_result.stderr) > 65536):
                return 4

        # transcribe.cpp explicitly supports a model-free WAV decode path.
        # It is NOT evidence that Canary weights can be loaded on this host.
        with sealed_pcm16_wav_memfd(b"\x00\x00" * 8) as (fd, audio_path):
            args = [str(canary), "-q", audio_path]
            denied = _run(args)
            if denied.returncode == 0:
                return 5
            admitted = _run(args, pass_fds=(fd,))
            if admitted.returncode != 0:
                return 6
            if (len(admitted.stdout) > 32768
                    or b"samples:    8" not in admitted.stdout
                    or b"model: (none specified, skipping load)" not in admitted.stdout):
                return 7
        return 0
    except (OSError, KeyError, ValueError, subprocess.SubprocessError):
        return 8


if __name__ == "__main__":
    sys.exit(main(sys.argv))
