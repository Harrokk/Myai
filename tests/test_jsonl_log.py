import json
from concurrent.futures import ThreadPoolExecutor

from core.jsonl_log import (
    append_jsonl,
    rotate_file,
)


def read_lines(path):
    return [
        json.loads(line)
        for line in path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def test_append_jsonl_writes_compact_record(tmp_path):
    path = tmp_path / "events.jsonl"

    append_jsonl(
        path,
        {
            "event": "ok",
            "value": 1,
        },
        max_bytes=1000,
        backups=2,
    )

    assert read_lines(path) == [
        {
            "event": "ok",
            "value": 1,
        }
    ]


def test_append_jsonl_rotates_before_limit_is_exceeded(tmp_path):
    path = tmp_path / "events.jsonl"

    append_jsonl(
        path,
        {
            "event": "first",
            "payload": "x" * 20,
        },
        max_bytes=45,
        backups=2,
    )
    append_jsonl(
        path,
        {
            "event": "second",
            "payload": "y" * 20,
        },
        max_bytes=45,
        backups=2,
    )

    rotated = tmp_path / "events.jsonl.1"

    assert rotated.exists()
    assert read_lines(rotated)[0][
        "event"
    ] == "first"
    assert read_lines(path)[0][
        "event"
    ] == "second"


def test_rotation_shifts_existing_backups(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(
        "current\n",
        encoding="utf-8",
    )
    (
        tmp_path
        / "events.jsonl.1"
    ).write_text(
        "one\n",
        encoding="utf-8",
    )
    (
        tmp_path
        / "events.jsonl.2"
    ).write_text(
        "two\n",
        encoding="utf-8",
    )

    rotate_file(
        path,
        backups=2,
    )

    assert (
        tmp_path
        / "events.jsonl.1"
    ).read_text(
        encoding="utf-8"
    ) == "current\n"
    assert (
        tmp_path
        / "events.jsonl.2"
    ).read_text(
        encoding="utf-8"
    ) == "one\n"


def test_zero_backups_discards_old_log(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(
        "old\n",
        encoding="utf-8",
    )

    rotate_file(
        path,
        backups=0,
    )

    assert path.exists() is False


def test_concurrent_appends_do_not_lose_records(tmp_path):
    path = tmp_path / "events.jsonl"
    count = 100

    def write(index):
        append_jsonl(
            path,
            {"index": index},
            max_bytes=1_000_000,
            backups=2,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(count)))

    records = read_lines(path)
    assert len(records) == count
    assert {record["index"] for record in records} == set(range(count))


def test_concurrent_rotation_keeps_jsonl_files_parseable(tmp_path):
    path = tmp_path / "events.jsonl"

    def write(index):
        append_jsonl(
            path,
            {"index": index, "payload": "x" * 20},
            max_bytes=120,
            backups=4,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(80)))

    files = [path] + [
        tmp_path / f"events.jsonl.{index}"
        for index in range(1, 5)
    ]
    existing = [item for item in files if item.exists()]

    assert existing
    for item in existing:
        assert read_lines(item)


def test_log_append_refuses_symlink_without_touching_external_file(tmp_path):
    import pytest
    external = tmp_path / "external.txt"
    external.write_text("ORIGINAL", encoding="utf-8")
    target = tmp_path / "events.jsonl"
    target.symlink_to(external)
    with pytest.raises((OSError, PermissionError)):
        append_jsonl(target, {"private": True})
    assert external.read_text(encoding="utf-8") == "ORIGINAL"


def test_log_append_refuses_dangling_symlink(tmp_path):
    import pytest
    target = tmp_path / "events.jsonl"
    missing = tmp_path / "missing.txt"
    target.symlink_to(missing)
    with pytest.raises((OSError, PermissionError)):
        append_jsonl(target, {"event": "must-not-write"})
    assert target.is_symlink()
    assert not missing.exists()


def test_log_rotation_refuses_symlinked_rotated_slot_without_changes(tmp_path):
    import pytest
    target = tmp_path / "events.jsonl"
    target.write_text("CURRENT" * 6, encoding="utf-8")
    external = tmp_path / "external.txt"
    external.write_text("KEEP", encoding="utf-8")
    (tmp_path / "events.jsonl.1").symlink_to(external)
    with pytest.raises((OSError, PermissionError)):
        append_jsonl(target, {"more": "data"}, max_bytes=15, backups=2)
    assert target.read_text(encoding="utf-8") == "CURRENT" * 6
    assert external.read_text(encoding="utf-8") == "KEEP"
    assert (tmp_path / "events.jsonl.1").is_symlink()


def test_log_append_refuses_hardlinked_existing_target(tmp_path):
    import os
    import pytest
    target = tmp_path / "events.jsonl"
    target.write_text("original", encoding="utf-8")
    twin = tmp_path / "twin"
    os.link(target, twin)
    with pytest.raises(PermissionError):
        append_jsonl(target, {"event": "no"})
    assert twin.read_text(encoding="utf-8") == "original"


def test_log_append_refuses_symlinked_parent_directory(tmp_path):
    import pytest
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "redirected"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(PermissionError):
        append_jsonl(link / "events.jsonl", {"event": "no"})
    assert not (outside / "events.jsonl").exists()


def test_append_uses_original_directory_fd_after_parent_swap(tmp_path, monkeypatch):
    import pytest
    from core import jsonl_log as module

    if not module._ANCHORED:
        pytest.skip("POSIX directory descriptors required")

    folder = tmp_path / "audit"
    folder.mkdir()
    (folder / "events.jsonl").write_text("OLD" * 30, encoding="utf-8")
    moved = tmp_path / "original"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "events.jsonl").write_text("EXTERNAL", encoding="utf-8")
    real_rotate = module._rotate_fd

    def swap_while_rotating(fd, name, count):
        folder.rename(moved)
        folder.symlink_to(outside, target_is_directory=True)
        return real_rotate(fd, name, count)

    monkeypatch.setattr(module, "_rotate_fd", swap_while_rotating)
    with pytest.raises(PermissionError, match="byttes ut"):
        append_jsonl(
            folder / "events.jsonl",
            {"event": "after-swap"},
            max_bytes=20,
            backups=2,
        )
    assert (outside / "events.jsonl").read_text(
        encoding="utf-8"
    ) == "EXTERNAL"
    assert not (outside / "events.jsonl.1").exists()
    assert (moved / "events.jsonl.1").is_file()


def test_append_detects_parent_swap_without_rotation(tmp_path, monkeypatch):
    import pytest
    from core import jsonl_log as module

    if not module._ANCHORED:
        pytest.skip("POSIX directory descriptors required")

    folder = tmp_path / "logs"
    folder.mkdir()
    moved = tmp_path / "displaced"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "audit.jsonl").write_text("KEEP", encoding="utf-8")
    real_append = module.os.fdopen

    def swap_before_fd_write(fd, *args, **kwargs):
        if not moved.exists():
            folder.rename(moved)
            folder.symlink_to(outside, target_is_directory=True)
        return real_append(fd, *args, **kwargs)

    monkeypatch.setattr(module.os, "fdopen", swap_before_fd_write)
    with pytest.raises(PermissionError, match="byttes ut"):
        append_jsonl(folder / "audit.jsonl", {"event": "safe"})
    assert (outside / "audit.jsonl").read_text(
        encoding="utf-8"
    ) == "KEEP"
    assert (moved / "audit.jsonl").is_file()


def test_reader_stays_anchored_after_parent_swap(tmp_path, monkeypatch):
    import pytest
    from core import jsonl_log as module

    if not module._ANCHORED:
        pytest.skip("POSIX directory descriptors required")

    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / "audit.jsonl").write_text("KNOWN", encoding="utf-8")
    moved = tmp_path / "moved"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "audit.jsonl").write_text("PRIVATE", encoding="utf-8")
    original = module._slot

    def swap_during_stat(fd, name):
        if name == "audit.jsonl" and not moved.exists():
            folder.rename(moved)
            folder.symlink_to(outside, target_is_directory=True)
        return original(fd, name)

    monkeypatch.setattr(module, "_slot", swap_during_stat)
    with pytest.raises(PermissionError, match="byttes ut"):
        module.read_log_text(folder / "audit.jsonl")
    assert (outside / "audit.jsonl").read_text(encoding="utf-8") == "PRIVATE"


def test_direct_rotate_file_rejects_swapped_parent_directory(
    tmp_path, monkeypatch,
):
    import pytest
    from core import jsonl_log as module

    if not module._ANCHORED:
        pytest.skip("POSIX directory descriptors required")

    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / "audit.jsonl").write_text("OLD", encoding="utf-8")
    moved = tmp_path / "moved"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "audit.jsonl").write_text("EXTERNAL", encoding="utf-8")
    real_rotate = module._rotate_fd

    def swap_during_rotate(fd, name, count):
        folder.rename(moved)
        folder.symlink_to(outside, target_is_directory=True)
        return real_rotate(fd, name, count)

    monkeypatch.setattr(module, "_rotate_fd", swap_during_rotate)
    with pytest.raises(PermissionError, match="byttes ut"):
        rotate_file(folder / "audit.jsonl", backups=1)
    assert (outside / "audit.jsonl").read_text(
        encoding="utf-8"
    ) == "EXTERNAL"
    assert not (outside / "audit.jsonl.1").exists()
    assert (moved / "audit.jsonl.1").is_file()


def _multiprocess_write_case(parameters):
    path, index, size, generations = parameters
    append_jsonl(
        path, {"index": index, "payload": "x" * 10},
        max_bytes=size, backups=generations,
    )
    return index


def test_multiple_os_processes_append_without_losing_records(tmp_path):
    import multiprocessing
    import pytest
    from concurrent.futures import ProcessPoolExecutor
    from core import jsonl_log as module

    if not module._ANCHORED:
        pytest.skip("POSIX process-shared flock required")
    path = tmp_path / "events.jsonl"
    ctx = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=4, mp_context=ctx) as pool:
        result = list(pool.map(
            _multiprocess_write_case,
            [(path, i, 1_000_000, 4) for i in range(120)],
        ))
    assert result == list(range(120))
    assert {entry["index"] for entry in read_lines(path)} == set(range(120))
    lock = tmp_path / ".events.jsonl.rotation.lock"
    assert lock.is_file()
    assert lock.stat().st_mode & 0o077 == 0


def test_multiple_os_processes_rotate_without_losing_retained_entries(
    tmp_path,
):
    import multiprocessing
    import pytest
    from concurrent.futures import ProcessPoolExecutor
    from core import jsonl_log as module

    if not module._ANCHORED:
        pytest.skip("POSIX process-shared flock required")
    path = tmp_path / "rotating.jsonl"
    ctx = multiprocessing.get_context("fork")
    total = 56
    with ProcessPoolExecutor(max_workers=4, mp_context=ctx) as pool:
        list(pool.map(
            _multiprocess_write_case,
            [(path, i, 140, 40) for i in range(total)],
        ))
    files = [path] + [
        tmp_path / f"rotating.jsonl.{i}" for i in range(1, 41)
    ]
    records = [
        item for candidate in files if candidate.is_file()
        for item in read_lines(candidate)
    ]
    assert len(records) == total
    assert {record["index"] for record in records} == set(range(total))


def test_symlinked_cross_process_lock_fails_closed(tmp_path):
    import pytest
    from core import jsonl_log as module

    if not module._ANCHORED:
        pytest.skip("POSIX process-shared flock required")
    path = tmp_path / "audit.jsonl"
    other = tmp_path / "outside.txt"
    other.write_text("NO MODIFICATION", encoding="utf-8")
    (tmp_path / ".audit.jsonl.rotation.lock").symlink_to(other)
    with pytest.raises((PermissionError, OSError)):
        append_jsonl(path, {"event": "must-not-append"})
    assert not path.exists()
    assert other.read_text(encoding="utf-8") == "NO MODIFICATION"


def test_world_writable_cross_process_lock_is_rejected(tmp_path):
    import os
    import pytest
    from core import jsonl_log as module

    if not module._ANCHORED:
        pytest.skip("POSIX process-shared flock required")
    lock = tmp_path / ".audit.jsonl.rotation.lock"
    lock.write_text("", encoding="utf-8")
    os.chmod(lock, 0o666)
    with pytest.raises(PermissionError, match="processgemensamt"):
        append_jsonl(tmp_path / "audit.jsonl", {"event": "no"})
    assert not (tmp_path / "audit.jsonl").exists()


def test_direct_rotation_uses_same_process_lock_as_append(tmp_path):
    import pytest
    from core import jsonl_log as module

    if not module._ANCHORED:
        pytest.skip("POSIX process-shared flock required")
    path = tmp_path / "rotate.jsonl"
    append_jsonl(path, {"old": True}, backups=2)
    rotate_file(path, backups=2)
    assert read_lines(tmp_path / "rotate.jsonl.1") == [{"old": True}]
    append_jsonl(path, {"new": True}, backups=2)
    assert read_lines(path) == [{"new": True}]


def test_leaf_swap_before_append_is_detected_and_never_writes_replacement(
    tmp_path, monkeypatch,
):
    import os
    import pytest
    from core import jsonl_log as module

    if not module._ANCHORED:
        pytest.skip("POSIX anchored audit required")
    path = tmp_path / "audit.jsonl"
    path.write_text("OLD", encoding="utf-8")
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("PRIVATE", encoding="utf-8")
    real_same = module._same_leaf
    swapped = [False]

    def swap_before_check(fd, name, info):
        if not swapped[0]:
            swapped[0] = True
            os.replace(replacement, path)
        return real_same(fd, name, info)

    monkeypatch.setattr(module, "_same_leaf", swap_before_check)
    with pytest.raises(PermissionError, match="byttes ut"):
        append_jsonl(path, {"record": "must-not-touch-replacement"})
    assert path.read_text(encoding="utf-8") == "PRIVATE"


def test_leaf_swap_after_write_causes_fail_closed_result(tmp_path, monkeypatch):
    import os
    import pytest
    from core import jsonl_log as module

    if not module._ANCHORED:
        pytest.skip("POSIX anchored audit required")
    path = tmp_path / "audit.jsonl"
    path.write_text("OLD", encoding="utf-8")
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("EXTERNAL", encoding="utf-8")
    original = module._same_leaf
    seen = [0]

    def replace_on_second_check(fd, name, info):
        seen[0] += 1
        if seen[0] == 2:
            os.replace(replacement, path)
        return original(fd, name, info)

    monkeypatch.setattr(module, "_same_leaf", replace_on_second_check)
    with pytest.raises(PermissionError, match="byttes ut"):
        append_jsonl(path, {"record": "must-fail"})
    assert seen[0] == 2
    assert path.read_text(encoding="utf-8") == "EXTERNAL"


def test_durable_append_fsyncs_data_and_directory(tmp_path, monkeypatch):
    from core import jsonl_log as module
    if not module._ANCHORED:
        import pytest
        pytest.skip("POSIX anchored audit required")

    path = tmp_path / "audit.jsonl"
    real_fsync = module.os.fsync
    modes = []

    def observe_fsync(fd):
        info = module.os.fstat(fd)
        modes.append(info.st_mode)
        return real_fsync(fd)

    monkeypatch.setattr(module.os, "fsync", observe_fsync)
    append_jsonl(path, {"important": True}, durable=True)
    import stat
    assert any(stat.S_ISREG(mode) for mode in modes)
    assert any(stat.S_ISDIR(mode) for mode in modes)
    assert read_lines(path) == [{"important": True}]


def test_parent_log_directory_group_writable_fails_closed(tmp_path):
    import os
    import pytest
    from core import jsonl_log as module
    if not module._ANCHORED:
        pytest.skip("POSIX anchored I/O required")
    directory = tmp_path / "group-shared"
    directory.mkdir()
    os.chmod(directory, 0o775)
    with pytest.raises(PermissionError, match="Loggkatalogen"):
        append_jsonl(directory / "audit.jsonl", {"action": "deny"})
    assert not (directory / "audit.jsonl").exists()


def test_excessive_log_rotation_count_is_rejected(tmp_path):
    import pytest
    path = tmp_path / "audit.jsonl"
    with pytest.raises(ValueError, match="rotationskopior"):
        append_jsonl(path, {"a": 1}, backups=1000000)
    assert not path.exists()
    path.write_text("CURRENT", encoding="utf-8")
    with pytest.raises(ValueError, match="rotationskopior"):
        rotate_file(path, backups=1000000)
    assert path.read_text(encoding="utf-8") == "CURRENT"


def test_bounded_log_reader_rejects_oversized_file(tmp_path):
    import pytest
    from core import jsonl_log as module

    path = tmp_path / "audit.jsonl"
    path.write_bytes(b"X" * (module._MAX_READ_BYTES + 1))
    with pytest.raises(ValueError, match="för stor"):
        module.read_log_text(path)


def test_bounded_log_reader_allows_small_valid_unicode(tmp_path):
    from core import jsonl_log as module

    path = tmp_path / "audit.jsonl"
    path.write_text("åäö\n", encoding="utf-8")
    assert module.read_log_text(path) == "åäö\n"


def test_fallback_jsonl_append_and_rotation_preserve_records(tmp_path, monkeypatch):
    from core import jsonl_log as module

    monkeypatch.setattr(module, "_ANCHORED", False)
    path = tmp_path / "fallback.jsonl"
    append_jsonl(
        path, {"source": "first", "text": "åäö"},
        max_bytes=35, backups=2,
    )
    append_jsonl(
        path, {"source": "second", "text": "åäö"},
        max_bytes=35, backups=2,
    )
    assert read_lines(tmp_path / "fallback.jsonl.1") == [
        {"source": "first", "text": "åäö"}
    ]
    assert read_lines(path) == [
        {"source": "second", "text": "åäö"}
    ]
    assert module.read_log_text(path).endswith("\n")


def test_fallback_jsonl_refuses_symlink_and_hardlink_without_modifying_them(
    tmp_path, monkeypatch,
):
    import os
    import pytest
    from core import jsonl_log as module

    monkeypatch.setattr(module, "_ANCHORED", False)
    target = tmp_path / "fallback.jsonl"
    other = tmp_path / "unrelated-data.txt"
    other.write_text("DO NOT TOUCH", encoding="utf-8")
    target.symlink_to(other)
    with pytest.raises((PermissionError, OSError)):
        append_jsonl(target, {"event": "no"})
    assert other.read_text(encoding="utf-8") == "DO NOT TOUCH"
    target.unlink()
    os.link(other, target)
    with pytest.raises((PermissionError, OSError)):
        append_jsonl(target, {"event": "no"})
    assert other.read_text(encoding="utf-8") == "DO NOT TOUCH"


def test_fallback_rotation_rejects_unsafe_rotated_entry(
    tmp_path, monkeypatch,
):
    import pytest
    from core import jsonl_log as module

    monkeypatch.setattr(module, "_ANCHORED", False)
    path = tmp_path / "fallback.jsonl"
    path.write_text("ORIGINAL", encoding="utf-8")
    external = tmp_path / "external.txt"
    external.write_text("EXTERNAL", encoding="utf-8")
    (tmp_path / "fallback.jsonl.1").symlink_to(external)
    with pytest.raises((PermissionError, OSError)):
        rotate_file(path, backups=2)
    assert path.read_text(encoding="utf-8") == "ORIGINAL"
    assert external.read_text(encoding="utf-8") == "EXTERNAL"


def test_fallback_required_audit_append_flushes_data_and_fail_closes_on_fsync(
    tmp_path, monkeypatch,
):
    import pytest
    from core import jsonl_log as module

    monkeypatch.setattr(module, "_ANCHORED", False)
    real_fsync = module.os.fsync
    calls = [0]
    def count_fsync(fd):
        calls[0] += 1
        return real_fsync(fd)

    monkeypatch.setattr(module.os, "fsync", count_fsync)
    path = tmp_path / "fallback.jsonl"
    append_jsonl(path, {"event": "required"}, durable=True)
    assert calls[0] >= 1
    assert read_lines(path) == [{"event": "required"}]

    def broken_fsync(fd):
        raise OSError("simulated durable flush failure")

    monkeypatch.setattr(module.os, "fsync", broken_fsync)
    with pytest.raises(OSError, match="durable flush failure"):
        append_jsonl(path, {"event": "must-fail"}, durable=True)
