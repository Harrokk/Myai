"""Test static QNN ELF classification without running vendor binaries."""
from scripts.ventuno_qnn_static_loader_probe import (
    parse_dynamic, library_exists, readelf_needed,
)


def test_extracts_only_safe_sonames_not_absolute_paths():
    output = """
    0x0000000000000001 (NEEDED) Shared library: [libQnnSystem.so]
    0x0000000000000001 (NEEDED) Shared library: [libc.so.6]
    0x000000000000001d (RUNPATH) Library runpath: [$ORIGIN/../../../lib]
    0x0000000000000001 (NEEDED) Shared library: [../../private/key.so]
    """
    parsed = parse_dynamic(output)
    assert parsed["needed"] == ["libQnnSystem.so", "libc.so.6"]
    assert parsed["has_runpath"] is True
    assert parsed["valid"] is True
    assert "$ORIGIN" not in str(parsed)


def test_no_dependency_on_empty_dynamic_output():
    assert parse_dynamic("") == {
        "valid": True, "needed": [], "has_runpath": False, "truncated": False,
    }


def test_absent_or_bad_library_does_not_exec_any_loader(tmp_path):
    assert readelf_needed(tmp_path / "missing")["status"] == "unavailable"
    libdir = tmp_path / "lib"
    libdir.mkdir()
    (libdir / "libQnnHtp.so").write_bytes(b"ELF-not-run")
    assert library_exists("libQnnHtp.so", {libdir}) is True
    assert library_exists("../../private/libQnnHtp.so", {libdir}) is False
    assert library_exists("libQnnSystem.so", {libdir}) is False


def test_rejects_unbounded_needed_array():
    line = ' (NEEDED) Shared library: [libQnnHtp.so]\n'
    # Unique basenames exceed the capped metadata report.
    huge = "".join(
        f" (NEEDED) Shared library: [libtest{n}.so]\n"
        for n in range(70)
    )
    data = parse_dynamic(huge)
    assert data["valid"] is False
    assert data["needed"] == []
