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
