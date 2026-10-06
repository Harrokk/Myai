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
