"""Fixed child-only native Canary/Whisper runner, NEVER registered by factory.

Called by Python -I with a strictly bounded configuration and inherited
sealed audio memfd. Applies child limits *before* verifying full native
weights and executing the pinned native CLI. No shell, network, logging or
disk-backed WAV, and no fallback to unpinned binaries.

This is a staging adapter. Native dynamic libraries, ARM64 ABI and actual
model behavior remain unverified until independently audited.
"""
import fcntl
import json
import os
from pathlib import Path
import stat
import sys
import struct

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


_KEYS = frozenset((
    "profile", "model_root", "model_sha256",
    "runtime_root", "runtime_sha256", "threads",
))


def parse_worker_config(raw, fd_arg):
    if type(raw) is not str or len(raw) > 2048 or type(fd_arg) is not str:
        raise ValueError("Invalid native candidate child configuration")
    if not fd_arg.isascii() or not fd_arg.isdecimal() or len(fd_arg) > 6:
        raise ValueError("Invalid private audio descriptor")
    fd = int(fd_arg)
    if not 3 <= fd <= 1048575:
        raise ValueError("Invalid private audio descriptor")
    data = json.loads(raw)
    if type(data) is not dict or set(data) != _KEYS:
        raise ValueError("Invalid native candidate child configuration")
    if type(data.get("threads")) is not int or not 1 <= data["threads"] <= 4:
        raise ValueError("Invalid native candidate threads")
    if data.get("profile") not in (
        "canary-1b-v2-q8", "whisper-large-v3-turbo",
    ):
        raise ValueError("Invalid native candidate profile")
    for name in ("model_root", "runtime_root", "model_sha256",
                 "runtime_sha256"):
        if type(data[name]) is not str or not 0 < len(data[name]) <= 1024:
            raise ValueError("Invalid native candidate child configuration")
    return data, fd


def require_sealed_audio(fd):
    from core.voice_candidate_audio_memfd import MAX_PCM_BYTES
    info = os.fstat(fd)
    seals = (
        fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW
        | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
    )
    if (not stat.S_ISREG(info.st_mode)
            or not 44 < info.st_size <= 44 + MAX_PCM_BYTES
            or (info.st_size - 44) % 2
            or fcntl.fcntl(fd, fcntl.F_GET_SEALS) & seals != seals):
        raise ValueError("Invalid sealed private speech audio")
    wav = os.pread(fd, 44, 0)
    if len(wav) != 44:
        raise ValueError("Invalid private WAV header")
    fields = struct.unpack("<4sI4s4sIHHIIHH4sI", wav)
    if fields != (
        b"RIFF", info.st_size - 8, b"WAVE", b"fmt ", 16,
        1, 1, 16000, 32000, 2, 16, b"data", info.st_size - 44,
    ):
        raise ValueError("Invalid private WAV header")
    return "/proc/self/fd/" + str(fd)


def main():
    try:
        if len(sys.argv) != 3:
            return 2
        config, fd = parse_worker_config(sys.argv[1], sys.argv[2])
        from core.voice_stt_child_limits import apply_child_limits
        apply_child_limits()

        audio_path = require_sealed_audio(fd)
        from core.voice_candidate_preflight import verify_candidate_profile
        profile = verify_candidate_profile(
            config["profile"],
            model_root=config["model_root"],
            model_sha256=config["model_sha256"],
            runtime_root=config["runtime_root"],
            runtime_sha256=config["runtime_sha256"],
        )
        from core.voice_candidate_cli_contract import candidate_cli_argv
        argv = candidate_cli_argv(profile, audio_path, config["threads"])
        if not profile.is_current():
            return 2
        # pass_fds authorizes inheritance for the *Python* worker; make the
        # same exact descriptor survive execve into the pinned native ELF.
        os.set_inheritable(fd, True)
        env = dict(os.environ)
        # env is supplied by the parent as a fixed allowlist; no shell or
        # arbitrary native loader paths come from the LLM or speech.
        os.execve(argv[0], argv, env)
        return 2
    except Exception:
        # Never include native loader details, private paths or PCM.
        return 2


if __name__ == "__main__":
    sys.exit(main())
