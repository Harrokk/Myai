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
