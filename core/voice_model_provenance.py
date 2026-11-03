"""Pinned, offline model-file provenance for opt-in voice security.

Only a trusted factory should supply the expected per-file SHA-256 values.
Hash verification precedes model loading. This is not remote attestation:
the same-process loader must consume exactly the validated local paths, and
production still requires OS permissions preventing post-verification writes.
"""
import hashlib
import os
from pathlib import Path
import re
import stat


_FILE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}\Z")
_FAMILY = re.compile(r"[a-z][a-z0-9_-]{1,63}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_MAX_FILES = 20
_MAX_FILE_SIZE = 2 * 1024**3
_MAX_TOTAL_SIZE = 4 * 1024**3
_BUFFER_SIZE = 1024**2
_ISSUER = object()


def _snapshot(info):
    return (
        info.st_dev, info.st_ino, info.st_size, info.st_mode,
        info.st_mtime_ns, info.st_ctime_ns, info.st_nlink,
    )


class VerifiedSTTModel:
    """Immutable record issued only after hashing exact local model bytes."""
    __slots__ = ("root", "family", "revision", "_states", "_issuer_tag")

    def __init__(self, *, token, root, family, revision, states):
        if token is not _ISSUER or not states:
            raise ValueError("untrusted-model-identity")
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "family", family)
        object.__setattr__(self, "revision", revision)
        object.__setattr__(self, "_states", tuple(states))
        object.__setattr__(self, "_issuer_tag", _ISSUER)

    def __setattr__(self, key, value):
        raise AttributeError("verified-model-identity-is-immutable")

    def is_current(self):
        """Cheap post-load metadata check; not a replacement for file hash."""
        try:
            if self._issuer_tag is not _ISSUER or not self._states:
                return False
            root = Path(self.root)
            if (str(root.resolve(strict=True)) != self.root
                    or root.is_symlink() or not root.is_dir()):
                return False
            root_stat = os.stat(root, follow_symlinks=False)
            if root_stat.st_mode & 0o222:
                return False
            for name, expected in self._states:
                path = root / name
                info = os.stat(path, follow_symlinks=False)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or info.st_mode & 0o222
                    or _snapshot(info) != expected
                ):
                    return False
            return True
        except (OSError, ValueError):
            return False


def verify_stt_model_files(root, *, family, expected_sha256):
    """Hash exact, non-symlink, read-only files against trusted fixed digests.

    No network or inference. This is a one-time factory/loading gate, not a
    per-utterance full-file hash. Raises a generic error without file paths.
    """
    try:
        if not isinstance(root, (str, Path)) or not isinstance(family, str):
            raise ValueError
        if not _FAMILY.fullmatch(family):
            raise ValueError
        path = Path(root)
        if not path.is_absolute() or len(str(path)) > 1024:
            raise ValueError
        # Refuse symlink redirection, including intermediate path components.
        if str(path.resolve(strict=True)) != str(path):
            raise ValueError
        root_stat = os.stat(path, follow_symlinks=False)
        if (not stat.S_ISDIR(root_stat.st_mode)
                or root_stat.st_mode & 0o222):
            raise ValueError
        if (not isinstance(expected_sha256, dict)
                or not 1 <= len(expected_sha256) <= _MAX_FILES):
            raise ValueError
        for name, digest in expected_sha256.items():
            if (not isinstance(name, str) or name in (".", "..")
                    or not _FILE.fullmatch(name)
                    or not isinstance(digest, str)
                    or not _SHA.fullmatch(digest)):
                raise ValueError
        states = []
        total = 0
        manifest_digest = hashlib.sha256()
        for name in sorted(expected_sha256):
            model_path = path / name
            info = os.stat(model_path, follow_symlinks=False)
            if (not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or info.st_mode & 0o222
                    or not 0 < info.st_size <= _MAX_FILE_SIZE):
                raise ValueError
            total += info.st_size
            if total > _MAX_TOTAL_SIZE:
                raise ValueError
            if not hasattr(os, "O_NOFOLLOW"):
                raise ValueError
            fd = os.open(
                model_path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
            )
            try:
                before = os.fstat(fd)
                if _snapshot(before) != _snapshot(info):
                    raise ValueError
                checksum = hashlib.sha256()
                with os.fdopen(fd, "rb", closefd=False) as f:
                    while True:
                        chunk = f.read(_BUFFER_SIZE)
                        if not chunk:
                            break
                        checksum.update(chunk)
                after = os.fstat(fd)
                later = os.stat(model_path, follow_symlinks=False)
                if (_snapshot(before) != _snapshot(after)
                        or _snapshot(after) != _snapshot(later)
                        or checksum.hexdigest() != expected_sha256[name]):
                    raise ValueError
                states.append((name, _snapshot(after)))
                manifest_digest.update(name.encode("ascii"))
                manifest_digest.update(b"\x00")
                manifest_digest.update(bytes.fromhex(expected_sha256[name]))
                manifest_digest.update(after.st_size.to_bytes(8, "big"))
            finally:
                os.close(fd)
        result = VerifiedSTTModel(
            token=_ISSUER, root=str(path), family=family,
            revision="sha256:" + manifest_digest.hexdigest(), states=states,
        )
        if not result.is_current():
            raise ValueError
        return result
    except (OSError, RuntimeError, ValueError, TypeError, OverflowError):
        # Do not expose model filesystem paths or internal model metadata.
        raise ValueError("stt-model-integrity-failed") from None
