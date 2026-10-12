from pathlib import Path

from scripts.ventuno_qnn_profile_feasibility import inspect_manifests, parse_help_flags


def test_help_exposes_profile_options_only():
    flags = parse_help_flags("""
    [ --profiling_level=<val> ] Enable profiling
    --profiling_option=optrace
    [ --retrieve_context=<file> ] Get context
    --input_list=<file> A list of model input files
    --unrelated=abc No relation
    """)
    assert flags == [
        "--input_list", "--profiling_level", "--profiling_option", "--retrieve_context",
    ]


def test_manifest_inventory_only_prints_keys(tmp_path: Path):
    (tmp_path / "geniex.json").write_text(
        '{"model": "user-secret-model.bin", "backend": "npu", "token": "private"}',
        encoding="utf-8",
    )
    (tmp_path / "weights.bin").write_bytes(b"x")
    report = inspect_manifests((tmp_path,))
    assert report["context_or_weight_bin_count"] == 1
    assert report["manifests"] == [{
        "filename": "geniex.json",
        "json_valid": True,
        "top_level_keys": ["backend", "model", "token"],
    }]
    assert "private" not in str(report)
    assert "user-secret-model.bin" not in str(report)


def test_scan_restricts_symlink_and_size(tmp_path: Path):
    cache = tmp_path / "cache"
    cache.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "config.json").write_text('{"outside": true}')
    (cache / "external").symlink_to(outside, target_is_directory=True)
    (cache / "model.json").write_bytes(b"x" * 131073)
    report = inspect_manifests((cache,))
    assert report["manifests"] == []
    assert report["capped"] is False
