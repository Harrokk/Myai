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
