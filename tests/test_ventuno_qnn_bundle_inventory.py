"""Fail-closed tests for read-only multi-context metadata mapping."""
import json
from pathlib import Path

import pytest

from scripts.ventuno_qnn_bundle_inventory import (
    find_bundle, graph_info, manifest_reference_summary, manifest_refs,
    overlap_counts, summarize_graphs,
)


def make_cache(tmp_path: Path):
    model = tmp_path / "m" / "cache"
    model.mkdir(parents=True)
    for index in range(4):
        (model / f"context-{index}.bin").write_bytes(b"abcd" * (index + 1))
    (model / "geniex.json").write_text(json.dumps({
        "ModelFile": "context-2.bin",
        "ExtraFiles": ["context-0.bin", "context-1.bin", "context-3.bin"],
    }))
    return model


def tensor(name, dtype="QNN_DATATYPE_UFIXED_POINT_8", dims=None):
    return {"info": {"name": name, "dataType": dtype, "dimensions": dims or [1, 16]}}


def graph(name, in_names=("input",), out_names=("output",)):
    return {"info": {"graphName": name, "graphInputs": [tensor(n) for n in in_names],
                     "graphOutputs": [tensor(n) for n in out_names]}}


def test_discovery_finds_four_and_one_without_assuming_load_order(tmp_path):
    model = make_cache(tmp_path)
    paths, manifests, status = find_bundle((tmp_path,))
    assert status == "bundle-candidates-found"
    assert len(paths) == 4
    assert len(manifests) == 1
    assert [p.stat().st_size for p in paths] == [4, 8, 12, 16]


def test_discovery_rejects_an_extra_context(tmp_path):
    model = make_cache(tmp_path)
    (model / "context-4.bin").write_bytes(b"abcd")
    paths, manifests, status = find_bundle((tmp_path,))
    assert (paths, manifests, status) == ([], [], "inconclusive-bundle-count")


def test_discovery_rejects_missing_manifest(tmp_path):
    model = make_cache(tmp_path)
    (model / "geniex.json").unlink()
    assert find_bundle((tmp_path,))[2] == "inconclusive-bundle-count"


def test_discovery_rejects_oversize_context_without_reading_it(tmp_path):
    model = make_cache(tmp_path)
    (model / "context-1.bin").unlink()
    with (model / "context-1.bin").open("wb") as f:
        f.truncate(1100 * 1024 * 1024 + 1)
    assert find_bundle((tmp_path,))[2] == "no-go-unbounded-binary"


def test_symbolic_context_is_not_followed(tmp_path):
    model = make_cache(tmp_path)
    (model / "context-3.bin").unlink()
    target = tmp_path / "other"
    target.write_bytes(b"abc")
    try:
        (model / "context-3.bin").symlink_to(target)
    except OSError:
        pytest.skip("symlinks unsupported")
    assert find_bundle((tmp_path,))[2] == "inconclusive-bundle-count"


def test_manifest_positions_are_only_references_not_runtime_order(tmp_path):
    model = make_cache(tmp_path)
    files, _, _ = find_bundle((tmp_path,))
    content = json.loads((model / "geniex.json").read_text())
    report = manifest_reference_summary(content, files)
    assert report["matched_candidate_slots"] == [2, 0, 1, 3]
    assert report["covers_all_contexts"] is True
    assert report["runtime_order_proven"] is False


def test_manifest_unknown_and_duplicate_entries_do_not_prove_coverage(tmp_path):
    model = make_cache(tmp_path)
    files, _, _ = find_bundle((tmp_path,))
    report = manifest_reference_summary(
        {"ModelFile": "context-0.bin", "ExtraFiles": ["context-0.bin", "missing.bin"]},
        files,
    )
    assert report["covers_all_contexts"] is False
    assert report["matched_candidate_slots"] == [0]


def test_manifest_does_not_recurse_unbounded_or_include_unrelated_values():
    report = manifest_refs({"ModelFile": "some.gguf",
                            "ExtraFiles": [["context.bin", "http://a/b.bin"]],
                            "password": "secret.bin"})
    assert report == ["context.bin"]


def test_graph_fingerprint_omits_names_and_marks_order_unverified():
    context = {"info": {"graphs": [graph("secret-name", ["private-in"], ["private-out"])]}}
    report, signature_pairs = summarize_graphs(context)
    serialized = json.dumps(report)
    for private in ("secret-name", "private-in", "private-out"):
        assert private not in serialized
    assert report["graphs"][0]["graph_token"] is not None
    assert report["metadata_order_not_runtime_order"] is True
    assert len(signature_pairs[0][0]) == 1


def test_cross_context_matching_io_is_only_possible_edge():
    one, p = summarize_graphs({"info": {"graphs": [graph("g1", ["x"], ["match"])]}})
    two, q = summarize_graphs({"info": {"graphs": [graph("g2", ["match"], ["y"])]}})
    result = overlap_counts([p, q])
    assert result == [{"source_inventory_slot": 0, "target_inventory_slot": 1,
                       "matching_io_signatures": 1}]
    assert one["metadata_order_not_runtime_order"]
    assert two["metadata_order_not_runtime_order"]


def test_invalid_metadata_is_inconclusive():
    assert summarize_graphs(None)[0]["status"] == "inconclusive-graph-list"
    assert summarize_graphs({"info": {"graphs": [None] * 25}})[0]["status"] == "inconclusive-graph-list"


def test_invalid_graph_returns_safe_empty_signature_pair():
    report, signatures = graph_info({"bad": True}, 0)
    assert report["status"] == "invalid"
    assert signatures == (set(), set())
