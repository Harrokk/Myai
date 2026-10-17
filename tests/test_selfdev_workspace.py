import json

import pytest

from core.selfdev_workspace import (
    SelfDevWorkspace,
)


def make_project(tmp_path):
    root = tmp_path / "project"
    (root / "core").mkdir(
        parents=True
    )
    (root / "runtime").mkdir()
    (root / ".git").mkdir()
    (root / "core" / "example.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )
    (root / "mail.py").write_text(
        "print('hello')\n",
        encoding="utf-8",
    )
    (root / "runtime" / "secret.txt").write_text(
        "runtime",
        encoding="utf-8",
    )
    (root / ".git" / "config").write_text(
        "git",
        encoding="utf-8",
    )
    return root


def test_workspace_copies_only_allowed_project_files(tmp_path):
    project = make_project(
        tmp_path
    )
    workspace = SelfDevWorkspace.create(
        project,
        "session1",
    )

    assert (
        workspace.workspace_root
        / "core"
        / "example.py"
    ).exists()
    assert (
        workspace.workspace_root
        / "mail.py"
    ).exists()
    assert not (
        workspace.workspace_root
        / "runtime"
    ).exists()
    assert not (
        workspace.workspace_root
        / ".git"
    ).exists()

    metadata = workspace.metadata()
    assert "core/example.py" in metadata["baseline"]
    assert "mail.py" in metadata["baseline"]


def test_workspace_blocks_path_traversal_and_runtime_writes(tmp_path):
    project = make_project(
        tmp_path
    )
    workspace = SelfDevWorkspace.create(
        project,
        "session2",
    )

    with pytest.raises(
        PermissionError
    ):
        workspace.write_text(
            "../outside.py",
            "bad",
        )

    with pytest.raises(
        PermissionError
    ):
        workspace.write_text(
            "runtime/unsafe.py",
            "bad",
        )


def test_workspace_tracks_changed_and_added_files(tmp_path):
    project = make_project(
        tmp_path
    )
    workspace = SelfDevWorkspace.create(
        project,
        "session3",
    )

    workspace.write_text(
        "core/example.py",
        "VALUE = 2\n",
    )
    workspace.write_text(
        "tests/test_new.py",
        "def test_ok():\n    assert True\n",
    )

    changes = workspace.changed_files()

    assert changes["changed"] == [
        "core/example.py"
    ]
    assert changes["added"] == [
        "tests/test_new.py"
    ]
    assert changes["deleted"] == []
    assert changes["manifest_digest"]


def test_workspace_write_invalidates_old_verification(tmp_path):
    project = make_project(
        tmp_path
    )
    workspace = SelfDevWorkspace.create(
        project,
        "session4",
    )
    workspace.verification_path.write_text(
        json.dumps(
            {
                "passed": True,
            }
        ),
        encoding="utf-8",
    )

    workspace.write_text(
        "core/example.py",
        "VALUE = 3\n",
    )

    assert not workspace.verification_path.exists()


def test_workspace_detects_source_drift(tmp_path):
    project = make_project(
        tmp_path
    )
    workspace = SelfDevWorkspace.create(
        project,
        "session5",
    )

    (
        project
        / "core"
        / "example.py"
    ).write_text(
        "VALUE = 99\n",
        encoding="utf-8",
    )

    assert workspace.source_drift() == [
        "core/example.py"
    ]


def test_invalid_session_id_is_rejected(tmp_path):
    project = make_project(
        tmp_path
    )

    with pytest.raises(
        ValueError
    ):
        SelfDevWorkspace.create(
            project,
            "../bad",
        )


def test_staging_rejects_dangling_final_symlink(tmp_path):
    project = make_project(tmp_path)
    workspace = SelfDevWorkspace.create(project, "danglinglink")
    outside = tmp_path / "outside.py"
    target = workspace.workspace_root / "core" / "unsafe.py"
    target.symlink_to(outside)

    with pytest.raises(PermissionError, match="Symlänkar"):
        workspace.write_text("core/unsafe.py", "DANGEROUS = True\n")

    assert not outside.exists()
    assert target.is_symlink()


def test_staging_rechecks_target_if_symlink_appears_during_write(tmp_path, monkeypatch):
    project = make_project(tmp_path)
    workspace = SelfDevWorkspace.create(project, "simulatedrace")
    external = tmp_path / "secret.py"
    external.write_text("PROTECTED = True\n", encoding="utf-8")
    target = workspace.workspace_root / "core" / "example.py"
    original = workspace._candidate_path
    calls = [0]

    def swap_after_initial_check(relative):
        resolved = original(relative)
        calls[0] += 1
        if calls[0] == 1:
            resolved.unlink()
            resolved.symlink_to(external)
        return resolved

    monkeypatch.setattr(workspace, "_candidate_path", swap_after_initial_check)
    with pytest.raises(PermissionError, match="Symlänkar"):
        workspace.write_text("core/example.py", "BAD = True\n")

    assert external.read_text(encoding="utf-8") == "PROTECTED = True\n"
    assert target.is_symlink()
    assert sorted(p.name for p in target.parent.iterdir() if p.name.endswith(".tmp")) == []


def test_staging_replace_failure_preserves_original(tmp_path, monkeypatch):
    project = make_project(tmp_path)
    workspace = SelfDevWorkspace.create(project, "replacefail")
    original = (workspace.workspace_root / "core" / "example.py").read_text(
        encoding="utf-8"
    )

    def fail_replace(*args, **kwargs):
        raise OSError("synthetic replace failure")

    monkeypatch.setattr("core.selfdev_workspace.os.replace", fail_replace)
    with pytest.raises(OSError, match="synthetic replace failure"):
        workspace.write_text("core/example.py", "VALUE = 20\n")
    assert (workspace.workspace_root / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == original
    assert not list((workspace.workspace_root / "core").glob(".example.py.*.tmp"))


def test_staging_blocks_parent_symlink_swapped_before_open(
    tmp_path, monkeypatch
):
    import os

    project = make_project(tmp_path)
    workspace = SelfDevWorkspace.create(project, "parentrace")
    inner = workspace.workspace_root / "core"
    outside = tmp_path / "outside"
    outside.mkdir()
    protected = outside / "example.py"
    protected.write_text("SECRET = True\n", encoding="utf-8")

    real_open = os.open
    changed = []

    def swap_before_open(path, flags, *args, **kwargs):
        if path == "core" and kwargs.get("dir_fd") is not None:
            inner.rename(workspace.workspace_root / "core-old")
            inner.symlink_to(outside, target_is_directory=True)
            changed.append(True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("core.selfdev_workspace.os.open", swap_before_open)
    with pytest.raises(OSError):
        workspace.write_text("core/example.py", "BAD = True\n")
    assert changed == [True]
    assert protected.read_text(encoding="utf-8") == "SECRET = True\n"


def test_staging_pins_directory_when_alias_swaps_before_replace(
    tmp_path, monkeypatch
):
    import os

    project = make_project(tmp_path)
    workspace = SelfDevWorkspace.create(project, "pinrace")
    inner = workspace.workspace_root / "core"
    outside = tmp_path / "outside"
    outside.mkdir()
    protected = outside / "example.py"
    protected.write_text("SECRET = True\n", encoding="utf-8")

    real_replace = os.replace
    changed = []

    def swap_after_open(source, dest, **kwargs):
        assert source.endswith(".tmp")
        assert dest == "example.py"
        assert kwargs["src_dir_fd"] == kwargs["dst_dir_fd"]
        inner.rename(workspace.workspace_root / "core-old")
        inner.symlink_to(outside, target_is_directory=True)
        changed.append(True)
        return real_replace(source, dest, **kwargs)

    monkeypatch.setattr("core.selfdev_workspace.os.replace", swap_after_open)
    workspace.write_text("core/example.py", "VALUE = 7\n")
    assert changed == [True]
    assert (workspace.workspace_root / "core-old" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 7\n"
    assert protected.read_text(encoding="utf-8") == "SECRET = True\n"


def test_staging_final_symlink_swap_at_rename_replaces_only_link(
    tmp_path, monkeypatch
):
    import os

    project = make_project(tmp_path)
    workspace = SelfDevWorkspace.create(project, "lastmoment")
    dest = workspace.workspace_root / "core" / "example.py"
    outside = tmp_path / "outside.py"
    outside.write_text("PROTECTED = True\n", encoding="utf-8")
    real_replace = os.replace

    def late_swap(source, target, **kwargs):
        dest.unlink()
        dest.symlink_to(outside)
        return real_replace(source, target, **kwargs)

    monkeypatch.setattr("core.selfdev_workspace.os.replace", late_swap)
    workspace.write_text("core/example.py", "VALUE = 11\n")
    assert dest.read_text(encoding="utf-8") == "VALUE = 11\n"
    assert not dest.is_symlink()
    assert outside.read_text(encoding="utf-8") == "PROTECTED = True\n"


def test_staging_rejects_fifo_and_keeps_existing_verification(
    tmp_path
):
    import os

    if not hasattr(os, "mkfifo"):
        pytest.skip("Unix FIFO required")
    project = make_project(tmp_path)
    workspace = SelfDevWorkspace.create(project, "specialtarget")
    target = workspace.workspace_root / "core" / "pipe.py"
    os.mkfifo(target)
    workspace.verification_path.write_text("old attestation", encoding="utf-8")
    with pytest.raises(PermissionError, match="specialfiler"):
        workspace.write_text("core/pipe.py", "BAD = True\n")
    assert workspace.verification_path.read_text(encoding="utf-8") == "old attestation"
    assert target.is_fifo()


def test_snapshot_baseline_hashes_exact_staged_bytes_without_reopening_source(
    tmp_path, monkeypatch
):
    import hashlib

    project = make_project(tmp_path)

    def disallow_second_hash(path):
        raise AssertionError("create must not reopen a source to hash it")

    monkeypatch.setattr("core.selfdev_workspace._sha256", disallow_second_hash)
    workspace = SelfDevWorkspace.create(project, "single-source-fd")
    staged = (workspace.workspace_root / "core" / "example.py").read_bytes()
    assert staged == b"VALUE = 1\n"
    assert workspace.metadata()["baseline"]["core/example.py"] == (
        hashlib.sha256(staged).hexdigest()
    )


def test_snapshot_rejects_symlink_swapped_before_final_source_open(
    tmp_path, monkeypatch
):
    import os

    project = make_project(tmp_path)
    source = project / "core" / "example.py"
    outside = tmp_path / "sensitive.py"
    outside.write_text("SECRET = True\n", encoding="utf-8")
    real_open = os.open
    swaps = []

    def swap_entry_before_open(path, flags, *args, **kwargs):
        if path == "example.py" and kwargs.get("dir_fd") is not None:
            source.unlink()
            source.symlink_to(outside)
            swaps.append(True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("core.selfdev_workspace.os.open", swap_entry_before_open)
    with pytest.raises(OSError):
        SelfDevWorkspace.create(project, "swap-before-source-open")

    assert swaps == [True]
    assert outside.read_text(encoding="utf-8") == "SECRET = True\n"
    assert not (
        project / "runtime" / "selfdev" / "swap-before-source-open"
        / "workspace" / "core" / "example.py"
    ).exists()


def test_snapshot_reads_open_inode_if_source_name_changes_mid_copy(
    tmp_path, monkeypatch
):
    import hashlib
    import os

    project = make_project(tmp_path)
    source = project / "core" / "example.py"
    outside = tmp_path / "sensitive.py"
    outside.write_text("SECRET = True\n", encoding="utf-8")
    real_open = os.open
    swaps = []

    def rename_after_open(path, flags, *args, **kwargs):
        descriptor = real_open(path, flags, *args, **kwargs)
        if (
            path == "example.py"
            and kwargs.get("dir_fd") is not None
            and (flags & os.O_ACCMODE) == os.O_RDONLY
            and not swaps
        ):
            # Source-only injection: destination staging opens the same
            # basename with O_WRONLY and must not trigger another swap.
            source.rename(project / "core" / "original.py")
            source.symlink_to(outside)
            swaps.append(True)
        return descriptor

    monkeypatch.setattr("core.selfdev_workspace.os.open", rename_after_open)
    workspace = SelfDevWorkspace.create(project, "source-inode-pinned")
    staged = (workspace.workspace_root / "core" / "example.py").read_bytes()
    assert swaps == [True]
    assert staged == b"VALUE = 1\n"
    assert workspace.metadata()["baseline"]["core/example.py"] == (
        hashlib.sha256(staged).hexdigest()
    )
    assert outside.read_text(encoding="utf-8") == "SECRET = True\n"


def test_snapshot_rejects_in_place_source_mutation_during_copy(
    tmp_path, monkeypatch
):
    import os

    project = make_project(tmp_path)
    source = project / "core" / "example.py"
    real_read = os.read
    mutated = []

    def mutate_after_first_source_read(descriptor, count):
        data = real_read(descriptor, count)
        if data == b"VALUE = 1\n" and not mutated:
            source.write_text("VALUE = 50000000\n", encoding="utf-8")
            mutated.append(True)
        return data

    monkeypatch.setattr("core.selfdev_workspace.os.read", mutate_after_first_source_read)
    with pytest.raises(RuntimeError, match="ändrades under selfdev-kopieringen"):
        SelfDevWorkspace.create(project, "mutated-source")

    assert mutated == [True]
    assert not (
        project / "runtime" / "selfdev" / "mutated-source" / "session.json"
    ).exists()


def test_snapshot_never_traverses_preexisting_source_directory_symlink(tmp_path):
    project = make_project(tmp_path)
    outside = tmp_path / "outside-dir"
    outside.mkdir()
    (outside / "private.py").write_text("DO_NOT_COPY = True\n", encoding="utf-8")
    (project / "core" / "shortcut").symlink_to(
        outside, target_is_directory=True
    )
    workspace = SelfDevWorkspace.create(project, "skip-source-dir-link")
    assert not (workspace.workspace_root / "core" / "shortcut").exists()
    assert not any("shortcut" in path for path in workspace.metadata()["baseline"])


def test_snapshot_preserves_safe_executable_bits(tmp_path):
    import stat

    project = make_project(tmp_path)
    script = project / "scripts" / "run.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)

    workspace = SelfDevWorkspace.create(project, "staged-executable")
    staged = workspace.workspace_root / "scripts" / "run.sh"
    assert staged.read_bytes() == script.read_bytes()
    assert stat.S_IMODE(staged.stat().st_mode) == 0o755
