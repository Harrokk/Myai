import json
import os
import stat
import threading
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:
    fcntl = None


_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS = {}

_MAX_READ_BYTES = 8 * 1024 * 1024
_MAX_BACKUPS = 128

_ANCHORED = (
    os.name == "posix" and fcntl is not None
    and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY")
    and all(f in os.supports_dir_fd
            for f in (os.open, os.stat, os.mkdir, os.rename, os.unlink))
)


@contextmanager
def _parent_fd(target, *, create=False):
    absolute = os.path.abspath(os.fspath(target))
    pieces = Path(absolute).parts
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(pieces[0], flags)
    try:
        for part in pieces[1:-1]:
            if create:
                try:
                    os.mkdir(part, dir_fd=fd)
                except FileExistsError:
                    pass
            new_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = new_fd
        info = os.fstat(fd)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o022
        ):
            raise PermissionError(
                "Loggkatalogen har osäkert ägarskap eller skrivrättigheter."
            )
        yield fd, pieces[-1]
    finally:
        os.close(fd)


def _slot(fd, name):
    try:
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise PermissionError("Osäker roterad loggfil.")
    if info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise PermissionError("Osäkra rättigheter för loggfil.")
    return info


@contextmanager
def _process_log_lock(parent_fd, name):
    """Shared across cooperating processes; never replace an existing lock.

    The descriptor is held for the full rotate + append transaction. The
    kernel releases flock when a crashed process closes its descriptors.
    """
    if fcntl is None:
        raise RuntimeError("Processgemensamt logglås saknas på denna plattform.")
    lock_name = "." + name + ".rotation.lock"
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    lock_fd = os.open(lock_name, flags, 0o600, dir_fd=parent_fd)
    locked = False
    try:
        info = os.fstat(lock_fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
        ):
            raise PermissionError("Osäkert processgemensamt revisionslogglås.")
        # Bounded wait rather than indefinitely blocking a required audit.
        deadline = time.monotonic() + 10.0
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Revisionslogglåset är upptaget.")
                time.sleep(0.01)
        slot = _slot(parent_fd, lock_name)
        if slot is None or (slot.st_dev, slot.st_ino) != (
            info.st_dev, info.st_ino
        ):
            raise PermissionError("Revisionslogglåset har bytts ut.")
        yield
        slot = _slot(parent_fd, lock_name)
        if slot is None or (slot.st_dev, slot.st_ino) != (
            info.st_dev, info.st_ino
        ):
            raise PermissionError("Revisionslogglåset har bytts ut.")
    finally:
        if locked:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _validated_backup_count(backups):
    count = max(0, int(backups))
    if count > _MAX_BACKUPS:
        raise ValueError("För många rotationskopior har begärts.")
    return count


def _rotate_fd(fd, name, backups):
    count = _validated_backup_count(backups)
    for candidate in [name] + [f"{name}.{i}" for i in range(1, count + 1)]:
        _slot(fd, candidate)
    if count == 0:
        if _slot(fd, name) is not None:
            os.unlink(name, dir_fd=fd)
        return
    if _slot(fd, f"{name}.{count}") is not None:
        os.unlink(f"{name}.{count}", dir_fd=fd)
    for index in range(count - 1, 0, -1):
        source, dest = f"{name}.{index}", f"{name}.{index + 1}"
        if _slot(fd, source) is not None:
            _slot(fd, dest)
            os.rename(source, dest, src_dir_fd=fd, dst_dir_fd=fd)
    if _slot(fd, name) is not None:
        _slot(fd, f"{name}.1")
        os.rename(name, f"{name}.1", src_dir_fd=fd, dst_dir_fd=fd)


def _same_leaf(fd, name, opened):
    """Detect a swapped/unlinked audit leaf before returning success."""
    current = _slot(fd, name)
    if current is None or (
        current.st_dev, current.st_ino
    ) != (opened.st_dev, opened.st_ino):
        raise PermissionError("Loggfilen byttes ut under skrivning.")


def _parent_unchanged(fd, target):
    expected = os.fstat(fd)
    current = os.stat(
        os.path.abspath(os.fspath(Path(target).parent)),
        follow_symlinks=False,
    )
    if not stat.S_ISDIR(current.st_mode) or (
        current.st_dev, current.st_ino
    ) != (expected.st_dev, expected.st_ino):
        raise PermissionError("Loggkatalogen byttes ut under skrivning.")



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
    if _ANCHORED:
        with _parent_fd(target) as (fd, name):
            if _slot(fd, name) is None:
                raise FileNotFoundError(str(target))
            flags = os.O_RDONLY | os.O_NOFOLLOW
            if hasattr(os, "O_NONBLOCK"):
                flags |= os.O_NONBLOCK
            descriptor = os.open(name, flags, dir_fd=fd)
            try:
                info = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                ):
                    raise PermissionError("Osäker loggfil vid läsning.")
                if info.st_size > _MAX_READ_BYTES:
                    raise ValueError("Audit-loggen är för stor för säker läsning.")
                with os.fdopen(descriptor, "rb") as handle:
                    descriptor = None
                    data = handle.read(_MAX_READ_BYTES + 1)
                if len(data) > _MAX_READ_BYTES:
                    raise ValueError("Audit-loggen är för stor för säker läsning.")
                _parent_unchanged(fd, target)
                return data.decode("utf-8")
            finally:
                if descriptor is not None:
                    os.close(descriptor)
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
        if info.st_size > _MAX_READ_BYTES:
            raise ValueError("Audit-loggen är för stor för säker läsning.")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            data = handle.read(_MAX_READ_BYTES + 1)
        if len(data) > _MAX_READ_BYTES:
            raise ValueError("Audit-loggen är för stor för säker läsning.")
        return data.decode("utf-8")
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
    count = _validated_backup_count(backups)
    if _ANCHORED:
        with _parent_fd(target) as (fd, name):
            with _process_log_lock(fd, name):
                _rotate_fd(fd, name, count)
                _parent_unchanged(fd, target)
        return
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
    durable=False,
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
    backups = _validated_backup_count(backups)

    with _path_lock(target):
        if _ANCHORED:
            with _parent_fd(target, create=True) as (fd, name):
                with _process_log_lock(fd, name):
                    meta = _slot(fd, name)
                    if (
                        limit > 0 and meta is not None
                        and meta.st_size + encoded_size > limit
                    ):
                        _rotate_fd(fd, name, backups)
                    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW
                    if hasattr(os, "O_NONBLOCK"):
                        flags |= os.O_NONBLOCK
                    descriptor = os.open(name, flags, 0o600, dir_fd=fd)
                    try:
                        info = os.fstat(descriptor)
                        if (
                            not stat.S_ISREG(info.st_mode)
                            or info.st_nlink != 1
                            or info.st_uid != os.geteuid()
                            or info.st_mode & 0o022
                        ):
                            raise PermissionError("Osäker loggfil vid append.")
                        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                            descriptor = None
                            _same_leaf(fd, name, info)
                            handle.write(line)
                            handle.flush()
                            if durable:
                                os.fsync(handle.fileno())
                            _same_leaf(fd, name, info)
                    finally:
                        if descriptor is not None:
                            os.close(descriptor)
                    if durable:
                        os.fsync(fd)
                    _parent_unchanged(fd, target)
            return target
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
            info = os.fstat(handle.fileno())
            handle.write(line)
            handle.flush()
            if durable:
                os.fsync(handle.fileno())
            current = _check_existing_regular(target)
            if current is None or (
                current.st_dev, current.st_ino
            ) != (info.st_dev, info.st_ino):
                raise PermissionError("Loggfilen byttes ut under skrivning.")

    return target
