import json
import os
import stat
import threading
from pathlib import Path


_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS = {}


def _path_lock(path):
    key = os.path.abspath(os.fspath(path))
    with _LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock



def _check_parent_path(target):
    # Path.resolve() would hide symlinked ancestors. Inspect lexical paths.
    for parent in target.parents:
        if parent.is_symlink():
            raise PermissionError("Loggens katalog får inte vara en symlink.")


def _check_existing_regular(target):
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise PermissionError("Loggfilen är en symlink eller en osäker filtyp.")
    if os.name == "posix" and (
        metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
    ):
        raise PermissionError("Loggfilen har osäkra behörigheter.")
    return metadata


def _open_append_regular(target):
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    descriptor = os.open(str(target), flags, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PermissionError("Osäker loggfil vid skrivning.")
        if os.name == "posix" and (
            info.st_uid != os.geteuid() or info.st_mode & 0o022
        ):
            raise PermissionError("Osäkra loggfilbehörigheter vid skrivning.")
        return os.fdopen(descriptor, "a", encoding="utf-8")
    except BaseException:
        os.close(descriptor)
        raise


def read_log_text(path):
    """Read a log using no-follow and inode validation, without mutations."""
    target = Path(path)
    _check_parent_path(target)
    _check_existing_regular(target)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    descriptor = os.open(str(target), flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PermissionError("Osäker loggfil vid läsning.")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = None
            return handle.read()
    finally:
        if descriptor is not None:
            os.close(descriptor)

def _rotated_path(
    path,
    index,
):
    return Path(
        str(path)
        + f".{index}"
    )


def _rotate_file_unlocked(
    target,
    *,
    backups,
):
    count = max(0, int(backups))
    _check_parent_path(target)
    # Validate *all* destinations before any unlink or rename. Otherwise a
    # tampered rotation entry could be silently overwritten or skipped.
    for item in [target] + [
        _rotated_path(target, index) for index in range(1, count + 1)
    ]:
        _check_existing_regular(item)

    if count <= 0:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        return

    oldest = _rotated_path(target, count)
    try:
        oldest.unlink()
    except FileNotFoundError:
        pass

    for index in range(count - 1, 0, -1):
        source = _rotated_path(target, index)
        if source.exists():
            source.replace(_rotated_path(target, index + 1))

    if target.exists():
        target.replace(_rotated_path(target, 1))


def rotate_file(
    path,
    *,
    backups,
):
    target = Path(path)
    with _path_lock(target):
        _rotate_file_unlocked(target, backups=backups)


def append_jsonl(
    path,
    record,
    *,
    max_bytes=5_000_000,
    backups=5,
):
    target = Path(path)
    _check_parent_path(target)
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    _check_parent_path(target)

    line = (
        json.dumps(
            record,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
        )
        + "\n"
    )
    encoded_size = len(
        line.encode(
            "utf-8"
        )
    )
    limit = max(
        0,
        int(
            max_bytes
        ),
    )

    with _path_lock(target):
        _check_parent_path(target)
        # Never treat dangling symlinks as absent files.
        meta = _check_existing_regular(target)
        if (
            limit > 0
            and meta is not None
            and meta.st_size + encoded_size > limit
        ):
            _rotate_file_unlocked(target, backups=backups)

        with _open_append_regular(target) as handle:
            handle.write(line)

    return target
