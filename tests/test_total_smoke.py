"""Hardware-independent final smoke checks for MyAI.

This suite complements scripts/smoke_test.py. It deliberately avoids physical
hardware access so it can run in CI before the real VENTUNO Q hardware test.
"""

import json
from concurrent.futures import ThreadPoolExecutor

from core.jsonl_log import append_jsonl
from core.memory import MemoryStore
from core import public_web_client


def _public_resolver(host, port, type=None):
    return [
        (
            public_web_client.socket.AF_INET,
            public_web_client.socket.SOCK_STREAM,
            6,
            "",
            ("8.8.8.8", port),
        )
    ]


def _private_resolver(host, port, type=None):
    return [
        (
            public_web_client.socket.AF_INET,
            public_web_client.socket.SOCK_STREAM,
            6,
            "",
            ("127.0.0.1", port),
        )
    ]


def test_total_smoke_memory_roundtrip(tmp_path):
    memory = MemoryStore(tmp_path / "memory.db")
    memory.init()
    assert memory.save_if_new("smoke", "total smoke memory") is True
    results = memory.search("total smoke memory")
    assert results
    assert "total smoke memory" in results[0][2]


def test_total_smoke_jsonl_concurrency(tmp_path):
    path = tmp_path / "smoke.jsonl"
    count = 64

    def write(index):
        append_jsonl(
            path,
            {"index": index, "payload": "x" * 12},
            max_bytes=180,
            backups=20,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(count)))

    records = []
    files = [path] + [
        tmp_path / f"smoke.jsonl.{index}"
        for index in range(1, 21)
    ]
    for item in files:
        if not item.exists():
            continue
        for line in item.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))

    indexes = {record["index"] for record in records}
    assert indexes == set(range(count))


def test_total_smoke_public_web_blocks_private_dns():
    client = public_web_client.PublicWebClient(
        resolver=_private_resolver,
    )

    try:
        client.validate_url("http://localhost/smoke")
    except ValueError:
        return

    raise AssertionError("Private network URL was not blocked.")


def test_total_smoke_public_web_accepts_public_dns():
    client = public_web_client.PublicWebClient(
        resolver=_public_resolver,
    )
    assert client.validate_url("https://example.com/smoke") == (
        "https://example.com/smoke"
    )
