"""No native model or physical audio: synthetic sealed Linux memfd tests."""
import fcntl
import io
import os
import struct
import subprocess
import sys
import wave

import pytest

from core.voice_candidate_audio_memfd import (
    MAX_PCM_BYTES, sealed_pcm16_wav_memfd,
)


def test_pcm16_is_stored_only_as_valid_16k_mono_wav_memfd(tmp_path):
    pcm = struct.pack("<4h", 0, 16384, -16384, -32768)
    with sealed_pcm16_wav_memfd(pcm) as (fd, path):
        assert path == "/proc/self/fd/" + str(fd)
        assert not list(tmp_path.iterdir())
        with os.fdopen(os.dup(fd), "rb") as reader:
            with wave.open(reader, "rb") as audio:
                assert audio.getframerate() == 16000
                assert audio.getnchannels() == 1
                assert audio.getsampwidth() == 2
                assert audio.getnframes() == 4
                assert audio.readframes(4) == pcm
        assert os.fstat(fd).st_size == 44 + len(pcm)
        assert not list(tmp_path.iterdir())


def test_sealed_fd_is_immutable_and_short_lived():
    with sealed_pcm16_wav_memfd(b"\x00\x00") as (fd, path):
        needed = (
            fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
        )
        assert fcntl.fcntl(fd, fcntl.F_GET_SEALS) & needed == needed
        with pytest.raises(OSError):
            os.write(fd, b"bad")
        oldfd = fd
    with pytest.raises(OSError):
        os.fstat(oldfd)


def test_descriptor_is_not_inherited_without_explicit_pass_fds():
    with sealed_pcm16_wav_memfd(b"\x00\x00") as (fd, path):
        cmd = [sys.executable, "-I", "-c",
               "import os,sys;"
               "p=sys.argv[1];"
               "sys.exit(0 if not os.path.exists(p) else 5)", path]
        p = subprocess.run(cmd, capture_output=True, check=False)
        assert p.returncode == 0
        assert p.stdout == b""


def test_explicit_single_fd_handoff_to_disposable_child_is_possible():
    """Checks file descriptor mechanics, not a candidate native STT CLI."""
    pcm = b"\x02\x00" * 16
    with sealed_pcm16_wav_memfd(pcm) as (fd, path):
        child = [
            sys.executable, "-I", "-c",
            "import os,sys,wave;"
            "p=sys.argv[1];"
            "h=wave.open(p,'rb');"
            "data=h.readframes(h.getnframes());"
            "sys.stdout.write('OK' if data==bytes.fromhex(sys.argv[2]) else 'BAD');"
            "h.close()",
            path, pcm.hex(),
        ]
        completed = subprocess.run(
            child, capture_output=True, check=False,
            pass_fds=(fd,), timeout=5,
        )
        assert completed.returncode == 0
        assert completed.stdout == b"OK"
        assert completed.stderr == b""


@pytest.mark.parametrize("bad", [
    None, False, "", b"", b"\x00",
    bytearray(b"\x00\x00"), b"x" * (MAX_PCM_BYTES + 2),
])
def test_invalid_audio_rejected_without_creating_fd(monkeypatch, bad):
    def forbidden(*_a, **_k):
        pytest.fail("memfd created for invalid PCM")
    monkeypatch.setattr(os, "memfd_create", forbidden)
    with pytest.raises(ValueError, match="Invalid or oversized"):
        with sealed_pcm16_wav_memfd(bad):
            pass


def test_no_disk_audio_fallback_if_memfd_missing(monkeypatch, tmp_path):
    monkeypatch.delattr(os, "memfd_create")
    with pytest.raises(RuntimeError, match="unavailable"):
        with sealed_pcm16_wav_memfd(b"\x00\x00"):
            pass
    assert not list(tmp_path.iterdir())


def test_maximum_pcm_segment_is_capped_and_correctly_headered():
    pcm = b"\x00\x00" * (30 * 16000)
    with sealed_pcm16_wav_memfd(pcm) as (fd, path):
        assert os.fstat(fd).st_size == len(pcm) + 44
        header = os.read(fd, 44)
        assert header[:4] == b"RIFF"
        assert header[8:12] == b"WAVE"


def test_bytes_content_never_leaks_into_exception(monkeypatch):
    def broken(*_a, **_k):
        raise OSError("PRIVATE_AUDIO_SECRET_PATH")
    monkeypatch.setattr(os, "memfd_create", broken)
    with pytest.raises(RuntimeError) as exc:
        with sealed_pcm16_wav_memfd(b"\x00\x00"):
            pass
    assert "PRIVATE_AUDIO" not in str(exc.value)
    assert "SECRET" not in str(exc.value)
    assert exc.value.__cause__ is None
