from core.selfdev_review import (
    build_selfdev_review,
)
from core.selfdev_workspace import (
    SelfDevWorkspace,
)


def make_workspace(tmp_path):
    project = (
        tmp_path
        / "project"
    )
    (project / "core").mkdir(
        parents=True
    )
    (
        project
        / "core"
        / "example.py"
    ).write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    workspace = (
        SelfDevWorkspace.create(
            project,
            "review1",
        )
    )
    workspace.write_text(
        "core/example.py",
        "VALUE = 2\n",
    )
    workspace.write_text(
        "tests/test_new.py",
        "def test_ok():\n    assert True\n",
    )
    return project, workspace


def test_review_shows_changed_and_added_files(tmp_path):
    _, workspace = make_workspace(
        tmp_path
    )

    review = build_selfdev_review(
        workspace
    )

    assert review["changed"] == [
        "core/example.py"
    ]
    assert review["added"] == [
        "tests/test_new.py"
    ]
    assert review["deleted"] == []
    assert "active/core/example.py" in review["diff"]
    assert "staging/core/example.py" in review["diff"]
    assert "-VALUE = 1" in review["diff"]
    assert "+VALUE = 2" in review["diff"]


def test_review_reports_source_drift(tmp_path):
    project, workspace = (
        make_workspace(
            tmp_path
        )
    )
    (
        project
        / "core"
        / "example.py"
    ).write_text(
        "VALUE = 9\n",
        encoding="utf-8",
    )

    review = build_selfdev_review(
        workspace
    )

    assert review["source_drift"] == [
        "core/example.py"
    ]


def test_review_reports_verification_status(tmp_path):
    _, workspace = make_workspace(
        tmp_path
    )
    workspace.verification_path.write_text(
        '{"passed": true}',
        encoding="utf-8",
    )

    review = build_selfdev_review(
        workspace
    )

    assert review["verification"][
        "passed"
    ] is True


def test_review_truncates_large_diff(tmp_path):
    _, workspace = make_workspace(
        tmp_path
    )
    workspace.write_text(
        "core/example.py",
        "X" * 1000,
    )

    review = build_selfdev_review(
        workspace,
        max_diff_chars=100,
    )

    assert review["diff_truncated"] is True
    assert "[diff trunkerad]" in review["diff"]


def test_review_never_accepts_verification_symlink(tmp_path):
    _, workspace = make_workspace(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text('{"passed":true}', encoding="utf-8")
    workspace.verification_path.symlink_to(outside)

    review = build_selfdev_review(workspace)
    assert review["verification"]["passed"] is False
    assert "kunde inte läsas" in review["verification"]["error"]




def test_review_rejects_swapped_active_file_symlink(tmp_path, monkeypatch):
    import os
    import pytest

    project, workspace = make_workspace(tmp_path)
    before = workspace.changed_files()
    monkeypatch.setattr(workspace, "changed_files", lambda: before)
    original = project / "core" / "example.py"
    secret = tmp_path / "secret.py"
    secret.write_text("DO_NOT_DISCLOSE = True\n", encoding="utf-8")
    real_open = os.open
    swaps = []

    def swap_before_open(path, flags, *args, **kwargs):
        if path == "example.py" and kwargs.get("dir_fd") is not None:
            original.unlink()
            original.symlink_to(secret)
            swaps.append(True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("core.selfdev_review.os.open", swap_before_open)
    with pytest.raises(OSError):
        build_selfdev_review(workspace)

    assert swaps == [True]
    assert secret.read_text(encoding="utf-8") == "DO_NOT_DISCLOSE = True\n"


def test_review_rejects_swapped_parent_symlink(tmp_path, monkeypatch):
    import os
    import pytest

    project, workspace = make_workspace(tmp_path)
    before = workspace.changed_files()
    monkeypatch.setattr(workspace, "changed_files", lambda: before)
    original = project / "core"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "example.py").write_text("PRIVATE = 1\n", encoding="utf-8")
    real_open = os.open
    swapped = []

    def swap_before_directory_open(path, flags, *args, **kwargs):
        if path == "core" and kwargs.get("dir_fd") is not None:
            original.rename(project / "core-original")
            original.symlink_to(outside, target_is_directory=True)
            swapped.append(True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("core.selfdev_review.os.open", swap_before_directory_open)
    with pytest.raises(OSError):
        build_selfdev_review(workspace)
    assert swapped == [True]
    assert (outside / "example.py").read_text(encoding="utf-8") == "PRIVATE = 1\n"


def test_review_rejects_oversized_changed_file(tmp_path):
    import pytest

    _, workspace = make_workspace(tmp_path)
    workspace.write_text("core/example.py", "X" * (2 * 1024 * 1024 + 1))

    with pytest.raises(ValueError, match="filstorleksgräns"):
        build_selfdev_review(workspace)


def test_review_rejects_total_source_budget_before_diff(tmp_path, monkeypatch):
    import pytest
    from core import selfdev_review as module

    _, workspace = make_workspace(tmp_path)

    def synthetic_read(*args, **kwargs):
        return [], 5 * 1024 * 1024

    monkeypatch.setattr(module, "_read_lines", synthetic_read)
    with pytest.raises(ValueError, match="totala datagräns"):
        build_selfdev_review(workspace)


def test_review_refuses_expected_changed_file_disappearing_after_manifest(
    tmp_path, monkeypatch
):
    import os
    import pytest

    project, workspace = make_workspace(tmp_path)
    before = workspace.changed_files()
    monkeypatch.setattr(workspace, "changed_files", lambda: before)
    target = project / "core" / "example.py"
    real_open = os.open

    def disappear_before_review_open(path, flags, *args, **kwargs):
        if path == "example.py" and kwargs.get("dir_fd") is not None:
            target.unlink()
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("core.selfdev_review.os.open", disappear_before_review_open)
    with pytest.raises(FileNotFoundError):
        build_selfdev_review(workspace)


def test_review_rejects_invalid_diff_limit(tmp_path):
    import pytest

    _, workspace = make_workspace(tmp_path)
    with pytest.raises(ValueError, match="max_diff_chars"):
        build_selfdev_review(workspace, max_diff_chars=0)
