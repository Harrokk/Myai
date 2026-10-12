import json
from pathlib import Path

from scripts.ventuno_qnn_context_metadata import (
    find_context_candidates,
    read_available_kib,
    run_context_probe,
    summarize_context_metadata,
)


def test_context_candidates_choose_smallest_without_following_links(tmp_path: Path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "large.bin").write_bytes(b"a" * 500)
    (cache / "small.bin").write_bytes(b"x" * 100)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "escape.bin").write_bytes(b"z")
    (cache / "link").symlink_to(outside, target_is_directory=True)
    (cache / "linked.bin").symlink_to(outside / "escape.bin")
    found = find_context_candidates((cache,))
    assert [(p.name, size) for p, size in found] == [
        ("small.bin", 100),
        ("large.bin", 500),
    ]


def test_read_available_kib(tmp_path: Path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:   16000000 kB\nMemAvailable:  6240000 kB\n")
    assert read_available_kib(meminfo) == 6240000
    meminfo.write_text("MemTotal: 16000000 kB\n")
    assert read_available_kib(meminfo) == 0


def test_summarize_context_metadata_no_names_or_private_values():
    metadata = {
        "graphs": [
            {"secret_name": "PRIVATE_GRAPH", "tensors": [
                {"secret_name": "PRIVATE_TENSOR", "dimensions": [1, 2048, 128]}
            ]}
        ],
        "private_model_path": "/home/private/file",
    }
    report = summarize_context_metadata(metadata)
    assert report["tensor_shapes_sample"] == [[1, 2048, 128]]
    assert report["graph_related_fields"] >= 1
    assert report["tensor_related_fields"] >= 1
    assert "PRIVATE" not in json.dumps(report)
    assert "/home/private" not in json.dumps(report)


def test_utility_missing_is_skipped(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("scripts.ventuno_qnn_context_metadata.shutil.which", lambda x: None)
    assert run_context_probe(tmp_path / "model.bin", tmp_path) == {
        "status": "skipped", "reason": "utility-not-installed",
    }


def test_schema_preview_reports_types_without_values():
    from scripts.ventuno_qnn_context_metadata import preview_schema

    data = {"info": {"graphs": [{"tensors": [{"dims": [1, 2, 3], "name": "secret-name"}]}]}}
    summary = preview_schema(data)
    assert "$.info.graphs: list(1 items)" in summary
    assert "$.info.graphs[].tensors: list(1 items)" in summary
    assert not any("secret-name" in entry for entry in summary)


def test_graph_io_summary_counts_and_memory_without_names():
    from scripts.ventuno_qnn_context_metadata import graph_io_summary

    data = {"info": {"graphs": [{
        "info": {
            "graphName": "sensitive_name",
            "graphInputs": [{"info": {"name": "private_input", "dimensions": [1, 8]}}],
            "graphOutputs": [{"info": {"name": "private_output", "dimensions": [1, 8]}}],
            "graphBlobInfoV2": {
                "constSize": 2048, "sharedWeightsSize": 4096,
                "badField": "should_not_show",
            },
        }
    }]}}
    report = graph_io_summary(data)
    assert report["graph_count"] == 1
    assert report["graphs"][0]["inputs"] == 1
    assert report["graphs"][0]["outputs"] == 1
    assert report["graphs"][0]["serialized_sizes_bytes"] == {
        "constSize": 2048, "sharedWeightsSize": 4096,
    }
    assert "sensitive_name" not in str(report)
    assert "private_input" not in str(report)
