import json
import threading
from pathlib import Path


_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS = {}


def _path_lock(path):
    key = str(Path(path).resolve())
    with _LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


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
    target = Path(
        path
    )
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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
        if (
            limit > 0
            and target.exists()
            and target.stat().st_size
            + encoded_size
            > limit
        ):
            _rotate_file_unlocked(
                target,
                backups=backups,
            )

        with target.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(line)

    return target
