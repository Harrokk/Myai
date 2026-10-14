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
