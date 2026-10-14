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


def _second_workspace(project):
    workspace = SelfDevWorkspace.create(project, "session2")
    workspace.write_text("core/example.py", "VALUE = 99\n")
    approve_verification(workspace)
    return workspace


def test_global_lock_blocks_a_concurrent_promotion_in_second_session(tmp_path):
    project, first = make_workspace(tmp_path)
    second = _second_workspace(project)
    active1 = manager(first, settings())
    active2 = manager(second, settings())

    with active1._project_mutation_lock():
        with pytest.raises(RuntimeError, match="annan selfdev-uppdatering"):
            active2.promote("PROMOTE session2")

    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert not (
        second.session_root / "rollbacks" / "promo1"
    ).exists()


def test_global_lock_blocks_a_concurrent_rollback_in_second_session(tmp_path):
    project, first = make_workspace(tmp_path)
    active = manager(first, settings())
    approve_verification(first)
    active.promote("PROMOTE session1")
    other_session = _second_workspace(project)
    other = manager(other_session, settings())

    with other._project_mutation_lock():
        with pytest.raises(RuntimeError, match="annan selfdev-uppdatering"):
            active.rollback("promo1", "ROLLBACK session1 promo1")

    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_global_lock_released_after_simulated_critical_interruption(
    tmp_path, monkeypatch,
):
    from core import selfdev_promote as module

    project, first = make_workspace(tmp_path)
    approve_verification(first)
    active = manager(first, settings())
    real_copy = module._atomic_copy

    with monkeypatch.context() as patch:
        patch.setattr(
            module,
            "_atomic_copy",
            lambda *args: (_ for _ in ()).throw(SystemExit("crash")),
        )
        with pytest.raises(SystemExit):
            active.promote("PROMOTE session1")

    # Lock is released on SystemExit, but the durable prepared journal
    # prevents a second session from modifying an inconsistent tree.
    second = _second_workspace(project)
    other = manager(second, settings())
    with pytest.raises(RuntimeError, match="Ofullständig selfdev-promotion"):
        other.promote("PROMOTE session2")

    record = active.recover_interrupted(
        "promo1", "RECOVER session1 promo1"
    )
    assert record["state"] == "recovered"
    # The other session has not drifted and can now promote safely.
    changed = other.promote("PROMOTE session2")
    assert changed["state"] == "completed"
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 99\n"


def test_global_lock_blocks_recovery_during_other_session_operation(
    tmp_path, monkeypatch,
):
    from core import selfdev_promote as module

    project, first = make_workspace(tmp_path)
    approve_verification(first)
    active = manager(first, settings())

    with monkeypatch.context() as patch:
        patch.setattr(
            module,
            "_atomic_copy",
            lambda *args: (_ for _ in ()).throw(SystemExit("crash")),
        )
        with pytest.raises(SystemExit):
            active.promote("PROMOTE session1")

    other = manager(_second_workspace(project), settings())
    with other._project_mutation_lock():
        with pytest.raises(RuntimeError, match="annan selfdev-uppdatering"):
            active.recover_interrupted("promo1", "RECOVER session1 promo1")

    assert active.recover_interrupted(
        "promo1", "RECOVER session1 promo1"
    )["state"] == "recovered"


def test_noncooperating_writer_changes_target_before_replace(tmp_path, monkeypatch):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    original = module._atomic_copy
    edited = [False]

    def externally_edit_before_copy(source, destination, **kwargs):
        if (
            destination == project / "core" / "example.py"
            and not edited[0]
        ):
            edited[0] = True
            destination.write_text("EXTERNAL = True\n", encoding="utf-8")
        return original(source, destination, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_atomic_copy", externally_edit_before_copy)
        with pytest.raises(RuntimeError, match="Extern"):
            active.promote("PROMOTE session1")

    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "EXTERNAL = True\n"
    journal = workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    assert json.loads(journal.read_text(encoding="utf-8"))["state"] == "prepared"


def test_external_change_to_second_target_never_rolls_back_first(tmp_path, monkeypatch):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    original = module._atomic_copy

    def external_edit_second(source, destination, **kwargs):
        if destination == project / "tests" / "test_new.py":
            destination.write_text("EXTERNAL = 1\n", encoding="utf-8")
        return original(source, destination, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_atomic_copy", external_edit_second)
        with pytest.raises(RuntimeError, match="Extern"):
            active.promote("PROMOTE session1")

    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"
    assert (project / "tests" / "test_new.py").read_text(
        encoding="utf-8"
    ) == "EXTERNAL = 1\n"
    assert json.loads((
        workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    ).read_text(encoding="utf-8"))["state"] == "prepared"


def test_external_modification_of_applied_file_not_overwritten_on_failure(
    tmp_path, monkeypatch,
):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    original = module._atomic_copy

    def change_first_then_fail(source, destination, **kwargs):
        if destination == project / "tests" / "test_new.py":
            (project / "core" / "example.py").write_text(
                "EXTERNAL = 2\n", encoding="utf-8"
            )
            raise OSError("synthetic failure after external write")
        return original(source, destination, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_atomic_copy", change_first_then_fail)
        with pytest.raises(RuntimeError, match="Extern"):
            active.promote("PROMOTE session1")

    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "EXTERNAL = 2\n"
    assert json.loads((
        workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    ).read_text(encoding="utf-8"))["state"] == "prepared"


def test_atomic_source_copy_flushes_file_and_parent_directory(tmp_path, monkeypatch):
    from core import selfdev_promote as module

    source = tmp_path / "source.txt"
    destination = tmp_path / "dest.txt"
    source.write_text("new text", encoding="utf-8")
    destination.write_text("old text", encoding="utf-8")
    fsync_calls = []
    original_fsync = module.os.fsync

    def track_fsync(fd):
        fsync_calls.append(fd)
        return original_fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(module.os, "fsync", track_fsync)
        module._atomic_copy(source, destination)

    assert len(fsync_calls) >= (2 if hasattr(module.os, "O_DIRECTORY") else 1)
    assert destination.read_text(encoding="utf-8") == "new text"


def test_backup_copy_failure_happens_before_any_active_code_change(
    tmp_path, monkeypatch,
):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    original = module.shutil.copy2

    def refuse_backup(source, destination, *args, **kwargs):
        if "rollbacks" in str(destination):
            raise OSError("synthetic backup storage failure")
        return original(source, destination, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(module.shutil, "copy2", refuse_backup)
        with pytest.raises(OSError, match="backup storage failure"):
            active.promote("PROMOTE session1")

    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert not (workspace.session_root / "rollbacks" / "promo1").exists()
