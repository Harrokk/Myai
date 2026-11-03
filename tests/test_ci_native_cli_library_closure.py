"""Synthetic unit tests for recursively checked native ARM64 dependency closure.

No system library is executed; no native inference, weights or recordings.
"""
import pytest

from scripts.ci_native_cli_library_closure import (
    dependency_closure, inspect_system_library,
)


def graph():
    return {
        "transcribe-cli": ["libstdc++.so.6", "libm.so.6", "libc.so.6"],
        "whisper-cli": ["libstdc++.so.6", "libc.so.6"],
        "libstdc++.so.6": ["libm.so.6", "libgcc_s.so.1", "libc.so.6"],
        "libm.so.6": ["libc.so.6", "ld-linux-aarch64.so.1"],
        "libgcc_s.so.1": ["libc.so.6"],
        "libc.so.6": ["ld-linux-aarch64.so.1"],
        "ld-linux-aarch64.so.1": [],
    }


def test_valid_recursive_system_closure():
    result = dependency_closure(
        graph(), entrypoints=("transcribe-cli", "whisper-cli"),
        trusted_loader="ld-linux-aarch64.so.1",
    )
    assert set(result) == set(graph())


def test_direct_allowed_library_is_not_enough_when_transitive_dep_is_unknown():
    cases = graph()
    cases["libstdc++.so.6"].append("libcuda.so.1")
    cases["libcuda.so.1"] = []
    with pytest.raises(ValueError, match="unreviewed-library"):
        dependency_closure(
            cases, entrypoints=("transcribe-cli", "whisper-cli"),
            trusted_loader="ld-linux-aarch64.so.1",
        )


def test_missing_system_library_blocks():
    cases = graph()
    del cases["libgcc_s.so.1"]
    with pytest.raises(ValueError, match="unresolved-library"):
        dependency_closure(
            cases, entrypoints=("transcribe-cli", "whisper-cli"),
            trusted_loader="ld-linux-aarch64.so.1",
        )


def test_wrong_dynamic_loader_cannot_enter_closure():
    cases = graph()
    cases["libc.so.6"] = ["ld-linux-x86-64.so.2"]
    cases["ld-linux-x86-64.so.2"] = []
    with pytest.raises(ValueError, match="unreviewed-library"):
        dependency_closure(
            cases, entrypoints=("transcribe-cli", "whisper-cli"),
            trusted_loader="ld-linux-aarch64.so.1",
        )


def test_duplicate_needed_entries_block_recursive_closure():
    cases = graph()
    cases["libc.so.6"] = ["ld-linux-aarch64.so.1"] * 2
    with pytest.raises(ValueError, match="invalid-library-edges"):
        dependency_closure(
            cases, entrypoints=("transcribe-cli", "whisper-cli"),
            trusted_loader="ld-linux-aarch64.so.1",
        )


def test_recursive_cycles_are_bounded_not_infinite():
    cases = graph()
    cases["libc.so.6"] = ["libstdc++.so.6"]
    result = dependency_closure(
        cases, entrypoints=("transcribe-cli", "whisper-cli"),
        trusted_loader="ld-linux-aarch64.so.1",
    )
    assert set(result) <= set(cases)


@pytest.mark.parametrize("bad", [None, {}, [], "graph", 4])
def test_invalid_graph_is_denied(bad):
    with pytest.raises(ValueError):
        dependency_closure(
            bad, entrypoints=("transcribe-cli",),
            trusted_loader="ld-linux-aarch64.so.1",
        )


def test_alias_or_unreviewed_library_in_graph_is_denied():
    cases = graph()
    cases["libstdc++.so.6"] = ["libevil.so.1"]
    with pytest.raises(ValueError):
        dependency_closure(
            cases, entrypoints=("transcribe-cli", "whisper-cli"),
            trusted_loader="ld-linux-aarch64.so.1",
        )


def test_all_graph_paths_include_both_cli_nodes():
    assert {"transcribe-cli", "whisper-cli"} <= set(
        dependency_closure(
            graph(), entrypoints=("transcribe-cli", "whisper-cli"),
            trusted_loader="ld-linux-aarch64.so.1",
        )
    )


def test_too_many_dependency_nodes_are_rejected():
    cases = graph()
    for i in range(40):
        cases[f"libunused{i}.so"] = []
    with pytest.raises(ValueError):
        dependency_closure(
            cases, entrypoints=("transcribe-cli",),
            trusted_loader="ld-linux-aarch64.so.1",
        )


def test_readelf_parser_rejects_transitive_rpath_and_wrong_isa(monkeypatch):
    import scripts.ci_native_cli_library_closure as module
    header = "Class: ELF64\\nData: 2's complement, little endian\\nMachine: AArch64"
    dynamic = " 0x1 (NEEDED) Shared library: [libc.so.6]\\n"
    monkeypatch.setattr(
        module, "_readelf",
        lambda _path, section: header if section == "-h" else dynamic,
    )
    assert module.inspect_system_library("/synthetic", "libstdc++.so.6") == [
        "libc.so.6",
    ]
    monkeypatch.setattr(
        module, "_readelf",
        lambda _path, section:
            header.replace("AArch64", "X86-64") if section == "-h" else dynamic,
    )
    with pytest.raises(ValueError, match="untrusted-system-isa"):
        module.inspect_system_library("/synthetic", "libstdc++.so.6")
    monkeypatch.setattr(
        module, "_readelf",
        lambda _path, section:
            header if section == "-h" else dynamic +
            " 0x1 (RUNPATH) Library runpath: [/tmp/evil]\\n",
    )
    with pytest.raises(ValueError, match="untrusted-system-dynamic-search"):
        module.inspect_system_library("/synthetic", "libstdc++.so.6")


def test_transitive_native_unknown_dependency_rejected(monkeypatch):
    import scripts.ci_native_cli_library_closure as module
    header = "Class: ELF64\\nData: 2's complement, little endian\\nMachine: AArch64"
    dynamic = " 0x1 (NEEDED) Shared library: [libevil.so.42]\\n"
    monkeypatch.setattr(
        module, "_readelf",
        lambda _path, section: header if section == "-h" else dynamic,
    )
    with pytest.raises(ValueError, match="unreviewed-transitive-library"):
        module.inspect_system_library("/synthetic", "libstdc++.so.6")


def test_transitive_system_library_soname_spoof_blocks(monkeypatch):
    import scripts.ci_native_cli_library_closure as module
    header = "Class: ELF64\\nData: 2's complement, little endian\\nMachine: AArch64"
    dynamic = (
        " 0x1 (SONAME) Library soname: [libevil.so]\\n"
        " 0x1 (NEEDED) Shared library: [libc.so.6]\\n"
    )
    monkeypatch.setattr(
        module, "_readelf",
        lambda _path, section: header if section == "-h" else dynamic,
    )
    with pytest.raises(ValueError, match="system-soname-mismatch"):
        module.inspect_system_library("/synthetic", "libstdc++.so.6")


def test_loader_soname_resolver_rejects_unknown_without_fs_access():
    import scripts.ci_native_cli_library_closure as module
    with pytest.raises(ValueError, match="unreviewed-system-soname"):
        module._system_library("libmyai-custom.so")


def test_one_library_cannot_skip_its_transitive_closure():
    cases = graph()
    del cases["libm.so.6"]
    with pytest.raises(ValueError, match="unresolved-library"):
        dependency_closure(
            cases, entrypoints=("transcribe-cli", "whisper-cli"),
            trusted_loader="ld-linux-aarch64.so.1",
        )
