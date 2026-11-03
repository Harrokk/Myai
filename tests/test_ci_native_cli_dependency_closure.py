"""Pure offline tests: native dependency closure must fail closed."""
import pytest

from scripts.ci_native_cli_dependency_closure import (
    parse_arm64_ldconfig, parse_library_deps,
)


CACHE = """
4 libs found in cache '/etc/ld.so.cache'
 libstdc++.so.6 (libc6,AArch64) => /lib/aarch64-linux-gnu/libstdc++.so.6
 libc.so.6 (libc6,AArch64) => /lib/aarch64-linux-gnu/libc.so.6
 libc.so.6 (libc6,x86-64) => /usr/local/lib/libc.so.6
 libm.so.6 (libc6,AArch64) => /lib/aarch64-linux-gnu/libm.so.6
"""
DYNAMIC = """
 0x0000000000000001 (NEEDED) Shared library: [libc.so.6]
 0x0000000000000001 (NEEDED) Shared library: [libm.so.6]
 0x000000000000000e (SONAME) Library soname: [libsample.so.1]
"""


def test_cache_keeps_only_arm64_matches_without_executing_libraries():
    entries = parse_arm64_ldconfig(CACHE)
    assert entries["libc.so.6"] == {"/lib/aarch64-linux-gnu/libc.so.6"}
    assert entries["libm.so.6"] == {"/lib/aarch64-linux-gnu/libm.so.6"}
    assert "libatomic.so.1" not in entries


def test_duplicate_arm64_ldconfig_path_is_recorded_for_rejection():
    data = CACHE + """
 libc.so.6 (libc6,AArch64) => /opt/unknown/libc.so.6
"""
    entries = parse_arm64_ldconfig(data)
    assert len(entries["libc.so.6"]) == 2


@pytest.mark.parametrize("bad", [None, b"bytes", 3, [], "x" * 2_000_001])
def test_invalid_cache_format_fails(bad):
    with pytest.raises(ValueError):
        parse_arm64_ldconfig(bad)


def test_standard_elf_dependencies_require_exact_library_soname():
    assert parse_library_deps(
        DYNAMIC, expected_soname="libsample.so.1",
    ) == ["libc.so.6", "libm.so.6"]


@pytest.mark.parametrize("tag", [
    "RPATH", "RUNPATH", "AUDIT", "DEPAUDIT", "FILTER", "AUXILIARY",
])
def test_recursive_library_loader_overrides_are_denied(tag):
    dynamic = DYNAMIC + f"0x1 ({tag}) Library {tag}: [/tmp/lib]\n"
    with pytest.raises(ValueError, match="runtime_search_or_audit_hook"):
        parse_library_deps(dynamic, expected_soname="libsample.so.1")


def test_unexpected_lib_soname_fails_even_if_needed_is_permitted():
    with pytest.raises(ValueError, match="unexpected_library_soname"):
        parse_library_deps(DYNAMIC, expected_soname="other.so.1")


def test_missing_soname_is_not_accepted_as_verified_dependency():
    data = DYNAMIC.replace(" 0x000000000000000e (SONAME) Library soname: [libsample.so.1]", "")
    with pytest.raises(ValueError):
        parse_library_deps(data, expected_soname="libsample.so.1")


def test_duplicate_soname_raises():
    with pytest.raises(ValueError):
        parse_library_deps(
            DYNAMIC + " 0x2 (SONAME) Library soname: [libsample.so.1]\n",
            expected_soname="libsample.so.1",
        )


def test_duplicate_direct_needed_library_is_denied():
    with pytest.raises(ValueError, match="invalid_needed_sonames"):
        parse_library_deps(
            DYNAMIC + "0x2 (NEEDED) Shared library: [libm.so.6]\n",
            expected_soname="libsample.so.1",
        )


def test_untrusted_slash_name_never_becomes_dependency():
    with pytest.raises(ValueError, match="invalid_needed_sonames"):
        parse_library_deps(
            DYNAMIC + "0x2 (NEEDED) Shared library: [../../payload.so]\n",
            expected_soname="libsample.so.1",
        )


def test_system_loader_can_have_no_children_if_soname_matches():
    text = "0x1 (SONAME) Library soname: [ld-linux-aarch64.so.1]\n"
    assert parse_library_deps(
        text, expected_soname="ld-linux-aarch64.so.1",
    ) == []
