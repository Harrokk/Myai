"""Source-only regression tests for the hosted ARM64 CLI dependency gate."""
import pytest

from scripts.ci_native_cli_elf_audit import inspect_readelf


HEADER = """
ELF Header:
  Class:                             ELF64
  Data:                              2's complement, little endian
  Machine:                           AArch64
"""
PROGRAM = "      [Requesting program interpreter: /lib/ld-linux-aarch64.so.1]\n"
DYNAMIC = """
 0x0000000000000001 (NEEDED)             Shared library: [libstdc++.so.6]
 0x0000000000000001 (NEEDED)             Shared library: [libm.so.6]
 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]
"""


def test_allowed_direct_system_libraries_are_planning_pass_only():
    result = inspect_readelf(HEADER, PROGRAM, DYNAMIC)
    assert result["safe"] is True
    assert result["reason"] == "direct_needed_allowlist_only"
    assert result["needed"] == sorted([
        "libstdc++.so.6", "libm.so.6", "libc.so.6",
    ])


@pytest.mark.parametrize("change", [
    "Machine:                           Advanced Micro Devices X86-64",
    "Machine:                           ARM",
    "Machine:                           RISC-V",
])
def test_wrong_isa_fails_even_with_allowed_libs(change):
    header = HEADER.replace("Machine:                           AArch64", change)
    assert inspect_readelf(header, PROGRAM, DYNAMIC)["safe"] is False


@pytest.mark.parametrize("program", [
    "",
    "      [Requesting program interpreter: /tmp/loader]\n",
    "      [Requesting program interpreter: /bin/sh]\n",
])
def test_bad_or_missing_loader_fails(program):
    assert inspect_readelf(HEADER, program, DYNAMIC)["safe"] is False


@pytest.mark.parametrize("tag", [
    "RPATH", "RUNPATH", "AUDIT", "DEPAUDIT", "FILTER", "AUXILIARY",
])
def test_native_search_paths_or_audit_hooks_fail(tag):
    dynamic = DYNAMIC + f" 0x1 ({tag}) Library {tag}: [/tmp/lib]\n"
    result = inspect_readelf(HEADER, PROGRAM, dynamic)
    assert result["safe"] is False
    assert result["reason"] == "native_runtime_search_or_audit_hook"


def test_unreviewed_gpu_or_network_libraries_fail():
    dynamic = DYNAMIC + """
 0x0000000000000001 (NEEDED)             Shared library: [libcuda.so.1]
"""
    result = inspect_readelf(HEADER, PROGRAM, dynamic)
    assert result["safe"] is False
    assert result["unexpected"] == ["libcuda.so.1"]


def test_empty_or_duplicate_needed_entries_fail():
    assert inspect_readelf(HEADER, PROGRAM, "")["safe"] is False
    double = DYNAMIC + " 0x1 (NEEDED) Shared library: [libm.so.6]\n"
    assert inspect_readelf(HEADER, PROGRAM, double)["safe"] is False


def test_none_and_nontext_sections_fail_closed():
    for value in (None, 3, [], b"ELF"):
        assert inspect_readelf(value, PROGRAM, DYNAMIC)["safe"] is False
        assert inspect_readelf(HEADER, value, DYNAMIC)["safe"] is False
        assert inspect_readelf(HEADER, PROGRAM, value)["safe"] is False
