import json
from copy import deepcopy

import pytest

from core.config import DEFAULT_SETTINGS
from core.selfdev_promote import (
    SelfDevPromotionManager,
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
    (project / "tests").mkdir()
    (
        project
        / "core"
        / "example.py"
    ).write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )
    (
        project
        / "tests"
        / "test_existing.py"
    ).write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )

    workspace = (
        SelfDevWorkspace.create(
            project,
            "session1",
        )
    )
    workspace.write_text(
        "core/example.py",
        "VALUE = 2\n",
    )
    workspace.write_text(
        "tests/test_new.py",
        "def test_new():\n    assert True\n",
    )
    return project, workspace


def approve_verification(
    workspace,
):
    changes = (
        workspace
        .changed_files()
    )
    workspace.verification_path.write_text(
        json.dumps(
            {
                "passed": True,
                "sandbox": "bubblewrap",
                "network_isolated": True,
                "host_devices_exposed": False,
                "workspace_manifest_digest": (
                    changes[
                        "manifest_digest"
                    ]
                ),
            }
        ),
        encoding="utf-8",
    )


def settings(
    *,
    enabled=True,
    promotion_enabled=True,
):
    value = deepcopy(
        DEFAULT_SETTINGS
    )
    value["selfdev"]["enabled"] = enabled
    value["selfdev"][
        "promotion_enabled"
    ] = promotion_enabled
    return value


def manager(
    workspace,
    value,
):
    return SelfDevPromotionManager(
        workspace,
        value,
        promotion_id_factory=(
            lambda: "promo1"
        ),
    )


def test_promotion_requires_feature_and_explicit_promotion_enable(
    tmp_path,
):
    _, workspace = make_workspace(
        tmp_path
    )
    approve_verification(
        workspace
    )

    with pytest.raises(
        PermissionError,
        match="Selfdev är avstängt",
    ):
        manager(
            workspace,
            settings(
                enabled=False,
            ),
        ).promote(
            "PROMOTE session1"
        )

    with pytest.raises(
        PermissionError,
        match="promotion är avstängd",
    ):
        manager(
            workspace,
            settings(
                promotion_enabled=False,
            ),
        ).promote(
            "PROMOTE session1"
        )


def test_promotion_requires_exact_manual_phrase(
    tmp_path,
):
    _, workspace = make_workspace(
        tmp_path
    )
    approve_verification(
        workspace
    )

    with pytest.raises(
        PermissionError,
        match="promotion-frase",
    ):
        manager(
            workspace,
            settings(),
        ).promote(
            "yes"
        )


def test_verified_promotion_backs_up_and_applies_changes(
    tmp_path,
):
    project, workspace = (
        make_workspace(
            tmp_path
        )
    )
    approve_verification(
        workspace
    )
    active = manager(
        workspace,
        settings(),
    )

    record = active.promote(
        "PROMOTE session1"
    )

    assert record[
        "promotion_id"
    ] == "promo1"
    assert (
        project
        / "core"
        / "example.py"
    ).read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"
    assert (
        project
        / "tests"
        / "test_new.py"
    ).exists()

    backup = (
        workspace.session_root
        / "rollbacks"
        / "promo1"
        / "files"
        / "core"
        / "example.py"
    )
    assert backup.read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_promotion_rejects_workspace_change_after_verification(
    tmp_path,
):
    _, workspace = make_workspace(
        tmp_path
    )
    approve_verification(
        workspace
    )
    workspace.write_text(
        "core/example.py",
        "VALUE = 3\n",
    )

    with pytest.raises(
        RuntimeError,
        match="ändrats efter verifieringen",
    ):
        manager(
            workspace,
            settings(),
        ).promote(
            "PROMOTE session1"
        )


def test_promotion_rejects_source_drift(
    tmp_path,
):
    project, workspace = (
        make_workspace(
            tmp_path
        )
    )
    approve_verification(
        workspace
    )
    (
        project
        / "core"
        / "example.py"
    ).write_text(
        "VALUE = 99\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RuntimeError,
        match="Aktiv källkod har ändrats",
    ):
        manager(
            workspace,
            settings(),
        ).promote(
            "PROMOTE session1"
        )


def test_rollback_restores_modified_and_removes_added_files(
    tmp_path,
):
    project, workspace = (
        make_workspace(
            tmp_path
        )
    )
    approve_verification(
        workspace
    )
    active = manager(
        workspace,
        settings(),
    )
    active.promote(
        "PROMOTE session1"
    )

    record = active.rollback(
        "promo1",
        "ROLLBACK session1 promo1",
    )

    assert record[
        "rolled_back"
    ] is True
    assert (
        project
        / "core"
        / "example.py"
    ).read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert not (
        project
        / "tests"
        / "test_new.py"
    ).exists()


def test_rollback_refuses_to_overwrite_post_promotion_changes(
    tmp_path,
):
    project, workspace = (
        make_workspace(
            tmp_path
        )
    )
    approve_verification(
        workspace
    )
    active = manager(
        workspace,
        settings(),
    )
    active.promote(
        "PROMOTE session1"
    )
    (
        project
        / "core"
        / "example.py"
    ).write_text(
        "VALUE = 123\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RuntimeError,
        match="nyare arbete",
    ):
        active.rollback(
            "promo1",
            "ROLLBACK session1 promo1",
        )
