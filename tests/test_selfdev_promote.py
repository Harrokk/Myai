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


def test_workspace_api_change_invalidates_verification(
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
        match="saknar verifieringsresultat",
    ):
        manager(
            workspace,
            settings(),
        ).promote(
            "PROMOTE session1"
        )


def test_promotion_rejects_out_of_band_workspace_change_after_verification(
    tmp_path,
):
    _, workspace = make_workspace(
        tmp_path
    )
    approve_verification(
        workspace
    )
    (
        workspace.workspace_root
        / "core"
        / "example.py"
    ).write_text(
        "VALUE = 7\n",
        encoding="utf-8",
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


def test_selfdev_promotion_is_audited_without_approval_phrase(
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

    audit_text = (
        project
        / "runtime"
        / "audit.jsonl"
    ).read_text(
        encoding="utf-8"
    )

    assert "selfdev_promote" in audit_text
    assert '"outcome":"attempt"' in audit_text
    assert '"outcome":"success"' in audit_text
    assert "PROMOTE session1" not in audit_text


def test_denied_selfdev_promotion_is_audited(
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

    with pytest.raises(
        PermissionError,
        match="promotion-frase",
    ):
        active.promote(
            "wrong phrase"
        )

    audit_text = (
        project
        / "runtime"
        / "audit.jsonl"
    ).read_text(
        encoding="utf-8"
    )

    assert '"outcome":"attempt"' in audit_text
    assert '"outcome":"denied"' in audit_text
    assert "wrong phrase" not in audit_text


def test_required_audit_blocks_selfdev_before_source_write(
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
    value = settings()
    value["audit_logging"][
        "enabled"
    ] = False
    value["audit_logging"][
        "require_for_writes"
    ] = True
    active = manager(
        workspace,
        value,
    )

    with pytest.raises(
        RuntimeError,
        match="Audit-loggning krävs",
    ):
        active.promote(
            "PROMOTE session1"
        )

    assert (
        project
        / "core"
        / "example.py"
    ).read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_selfdev_rollback_is_audited(
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
    active.rollback(
        "promo1",
        "ROLLBACK session1 promo1",
    )

    audit_text = (
        project
        / "runtime"
        / "audit.jsonl"
    ).read_text(
        encoding="utf-8"
    )

    assert "selfdev_rollback" in audit_text
    assert '"outcome":"success"' in audit_text
    assert "ROLLBACK session1 promo1" not in audit_text


def test_interrupted_promotion_writes_recovery_journal_before_source_change(
    tmp_path, monkeypatch,
):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    original_copy = module._atomic_copy
    calls = [0]

    def interrupt_on_second_copy(source, target):
        calls[0] += 1
        if calls[0] == 2:
            raise SystemExit("synthetic power loss")
        return original_copy(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_atomic_copy", interrupt_on_second_copy)
        with pytest.raises(SystemExit, match="synthetic power loss"):
            active.promote("PROMOTE session1")

    journal = workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    saved = json.loads(journal.read_text(encoding="utf-8"))
    assert saved["state"] == "prepared"
    assert saved["backups"]
    assert saved["planned_hashes"]
    assert (project / "core" / "example.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert not (project / "tests" / "test_new.py").exists()

    with pytest.raises(RuntimeError, match="Ofullständig"):
        active.promote("PROMOTE session1")

    with pytest.raises(PermissionError, match="recovery-frase"):
        active.recover_interrupted("promo1", "yes")

    record = active.recover_interrupted(
        "promo1", "RECOVER session1 promo1"
    )
    assert record["state"] == "recovered"
    assert record["rolled_back"] is True
    assert (project / "core" / "example.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert not (project / "tests" / "test_new.py").exists()


def test_recovery_refuses_to_overwrite_external_change_without_partial_restore(
    tmp_path, monkeypatch,
):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    original_copy = module._atomic_copy
    calls = [0]

    def interrupt_after_first(source, target):
        calls[0] += 1
        if calls[0] == 2:
            raise SystemExit("synthetic interruption")
        return original_copy(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_atomic_copy", interrupt_after_first)
        with pytest.raises(SystemExit):
            active.promote("PROMOTE session1")

    (project / "tests" / "test_new.py").write_text(
        "unrelated user change", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="nyare arbete"):
        active.recover_interrupted("promo1", "RECOVER session1 promo1")

    assert (project / "core" / "example.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert (project / "tests" / "test_new.py").read_text(encoding="utf-8") == "unrelated user change"


def test_successful_promotion_has_complete_record_and_disallows_recovery(tmp_path):
    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    record = active.promote("PROMOTE session1")
    assert record["state"] == "completed"
    assert record["planned_hashes"]
    assert record["after_hashes"]
    with pytest.raises(RuntimeError, match="ofullständig prepared-journal"):
        active.recover_interrupted("promo1", "RECOVER session1 promo1")
    assert (project / "core" / "example.py").read_text(encoding="utf-8") == "VALUE = 2\n"


def test_recovery_is_idempotent_and_refuses_second_restore(tmp_path, monkeypatch):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    original_copy = module._atomic_copy
    with monkeypatch.context() as patch:
        patch.setattr(
            module,
            "_atomic_copy",
            lambda *args: (_ for _ in ()).throw(SystemExit("interrupted")),
        )
        with pytest.raises(SystemExit):
            active.promote("PROMOTE session1")

    saved = active.recover_interrupted("promo1", "RECOVER session1 promo1")
    assert saved["state"] == "recovered"
    with pytest.raises(RuntimeError, match="ofullständig prepared-journal"):
        active.recover_interrupted("promo1", "RECOVER session1 promo1")


def test_incomplete_promotion_cannot_bypass_recovery_using_rollback(
    tmp_path, monkeypatch,
):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())

    with monkeypatch.context() as patch:
        patch.setattr(
            module, "_atomic_copy",
            lambda *args: (_ for _ in ()).throw(SystemExit("power loss")),
        )
        with pytest.raises(SystemExit):
            active.promote("PROMOTE session1")

    with pytest.raises(RuntimeError, match="kräver RECOVER"):
        active.rollback("promo1", "ROLLBACK session1 promo1")
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_modified_backup_refuses_rollback_without_mutating_sources(tmp_path):
    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")

    backup = (
        workspace.session_root / "rollbacks" / "promo1"
        / "files" / "core" / "example.py"
    )
    backup.write_text("MALICIOUS = True\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="backup har ändrats"):
        active.rollback("promo1", "ROLLBACK session1 promo1")

    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_full_file_application_without_final_journal_is_recoverable(
    tmp_path, monkeypatch,
):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    real_write_record = module._atomic_write_record

    def crash_at_final_journal(path, record):
        if record.get("state") == "completed":
            raise SystemExit("crashed just before commit record")
        return real_write_record(path, record)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_atomic_write_record", crash_at_final_journal)
        with pytest.raises(SystemExit, match="commit record"):
            active.promote("PROMOTE session1")

    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"
    assert (project / "tests" / "test_new.py").is_file()

    state = active.recover_interrupted("promo1", "RECOVER session1 promo1")
    assert state["state"] == "recovered"
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert not (project / "tests" / "test_new.py").exists()


def test_corrupt_backup_blocks_recovery_before_any_source_mutation(
    tmp_path, monkeypatch,
):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    original_copy = module._atomic_copy
    copies = [0]

    def interrupt_second_copy(source, target):
        copies[0] += 1
        if copies[0] == 2:
            raise SystemExit("simulated crash")
        return original_copy(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_atomic_copy", interrupt_second_copy)
        with pytest.raises(SystemExit):
            active.promote("PROMOTE session1")

    backup = workspace.session_root / "rollbacks" / "promo1" / "files" / "core" / "example.py"
    backup.write_text("CORRUPTED = True\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Backup är skadad"):
        active.recover_interrupted("promo1", "RECOVER session1 promo1")

    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"
    assert not (project / "tests" / "test_new.py").exists()
