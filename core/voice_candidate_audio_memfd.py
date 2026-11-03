"""Private in-memory WAV handoff for future Canary/Whisper native CLIs.

A capped 16-kHz mono PCM16 segment is written into a sealed Linux memfd,
not into a persistent WAV file. The native worker must explicitly pass the
descriptor using subprocess pass_fds and keep the worker in its OWNED process
group. This primitive does not execute native code, start STT, read a mic,
create temporary files, or authorize any voice command.

IMPORTANT: memfd is not an anti-swap guarantee. An operating system that
has swap enabled could write memory-backed pages to swap; the production
audio-privacy policy must separately evaluate swap and process visibility.
"""
from contextlib import contextmanager
import fcntl
import os
import struct


MAX_PCM_BYTES = 30 * 16000 * 2
_SAMPLE_RATE = 16000
_CHANNELS = 1
_BITS_PER_SAMPLE = 16


def _wav_header(pcm_bytes):
    """Standard 44-byte PCM WAV header, no variable metadata chunks."""
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + pcm_bytes, b"WAVE", b"fmt ", 16,
        1, _CHANNELS, _SAMPLE_RATE,
        _SAMPLE_RATE * _CHANNELS * (_BITS_PER_SAMPLE // 8),
        _CHANNELS * (_BITS_PER_SAMPLE // 8),
        _BITS_PER_SAMPLE, b"data", pcm_bytes,
    )


def _write_all(fd, payload):
    offset = 0
    while offset < len(payload):
        written = os.write(fd, memoryview(payload)[offset:])
        if written <= 0:
            raise OSError("Short in-memory audio write")
        offset += written


@contextmanager
def sealed_pcm16_wav_memfd(audio):
    """Yield (fd, /proc/self/fd/N) for a future explicit pass_fds native call.

    The descriptor is CLOEXEC, so it is NOT shared with a subprocess unless
    the audited native worker explicitly opts in. File size is <1 MiB and
    validated before allocating any descriptor. No disk/tempfile fallback.
    """
    if (type(audio) is not bytes or not 0 < len(audio) <= MAX_PCM_BYTES
            or len(audio) % 2):
        raise ValueError("Invalid or oversized in-memory STT audio")
    if (not hasattr(os, "memfd_create")
            or not hasattr(os, "MFD_ALLOW_SEALING")
            or not all(hasattr(fcntl, name) for name in (
                "F_ADD_SEALS", "F_SEAL_WRITE", "F_SEAL_GROW",
                "F_SEAL_SHRINK", "F_SEAL_SEAL",
            ))):
        raise RuntimeError("RAM-only STT audio delivery is unavailable")

    fd = None
    try:
        try:
            fd = os.memfd_create(
                "myai-private-stt-wav",
                os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
            )
            _write_all(fd, _wav_header(len(audio)))
            _write_all(fd, audio)
            if os.fstat(fd).st_size != 44 + len(audio):
                raise OSError("Unexpected in-memory audio length")
            seals = (
                fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW
                | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
            )
            fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
            if fcntl.fcntl(fd, fcntl.F_GET_SEALS) & seals != seals:
                raise OSError("In-memory audio sealing failed")
            os.lseek(fd, 0, os.SEEK_SET)
        except (OSError, ValueError):
            # Never expose OS-provided paths, private PCM or raw error text.
            raise RuntimeError("RAM-only STT audio handoff failed") from None
        yield fd, "/proc/self/fd/" + str(fd)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
