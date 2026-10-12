from pathlib import Path

from scripts.ventuno_qairt_profile_preflight import (
    catalog_models,
    geniex_rss_kib,
    parse_memory_kib,
)


def test_parse_memory_kib():
    assert parse_memory_kib(
        "MemTotal:       16384000 kB\nMemAvailable:    4086000 kB\nSwapFree: 5 kB\n"
    ) == {"MemTotal": 16384000, "MemAvailable": 4086000}


def test_catalog_models_does_not_follow_symlinks(tmp_path: Path):
    inside = tmp_path / "cache"
    inside.mkdir()
    (inside / "model.bin").write_bytes(b"x" * 1024)
    nested = inside / "nested"
    nested.mkdir()
    (nested / "model.gguf").write_bytes(b"y" * 2048)
    external = tmp_path / "outside"
    external.mkdir()
    (external / "dont_include.bin").write_bytes(b"z" * 9999)
    (inside / "external_link").symlink_to(external, target_is_directory=True)

    report = catalog_models((inside,))
    assert report["model_file_counts"][".bin"] == 1
    assert report["model_file_counts"][".gguf"] == 1
    assert report["largest_model_file_mib"] == [0.0, 0.0]
    assert report["scan_capped"] is False


def test_catalog_models_bounds(tmp_path: Path):
    for index in range(12):
        (tmp_path / f"f{index}.bin").write_bytes(b"x")
    report = catalog_models((tmp_path,), max_files=5)
    assert report["files_checked"] == 5
    assert report["scan_capped"] is True


def test_geniex_rss_kib(tmp_path: Path):
    first = tmp_path / "101"
    first.mkdir()
    (first / "comm").write_text("geniex\n")
    (first / "status").write_text("Name: geniex\nVmRSS:\t2048 kB\n")
    second = tmp_path / "102"
    second.mkdir()
    (second / "comm").write_text("python\n")
    (second / "status").write_text("VmRSS: 4096 kB\n")
    assert geniex_rss_kib(tmp_path) == ([101], 2048)
