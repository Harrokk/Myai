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

    def interrupt_on_second_copy(source, target, **kwargs):
        calls[0] += 1
        if calls[0] == 2:
            raise SystemExit("synthetic power loss")
        return original_copy(source, target, **kwargs)

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

    def interrupt_after_first(source, target, **kwargs):
        calls[0] += 1
        if calls[0] == 2:
            raise SystemExit("synthetic interruption")
        return original_copy(source, target, **kwargs)

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
            lambda *args, **kwargs: (_ for _ in ()).throw(SystemExit("interrupted")),
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
            lambda *args, **kwargs: (_ for _ in ()).throw(SystemExit("power loss")),
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
    with pytest.raises(RuntimeError, match="Backup är skadad"):
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

    def interrupt_second_copy(source, target, **kwargs):
        copies[0] += 1
        if copies[0] == 2:
            raise SystemExit("simulated crash")
        return original_copy(source, target, **kwargs)

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
            lambda *args, **kwargs: (_ for _ in ()).throw(SystemExit("crash")),
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
            lambda *args, **kwargs: (_ for _ in ()).throw(SystemExit("crash")),
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


def test_staging_mutation_after_preflight_is_rejected(tmp_path, monkeypatch):
    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    original_preflight = active._preflight_promotion

    def mutate_after_validated_snapshot():
        result = original_preflight()
        (workspace.workspace_root / "core" / "example.py").write_text(
            "UNVERIFIED = True\n", encoding="utf-8"
        )
        return result

    monkeypatch.setattr(active, "_preflight_promotion", mutate_after_validated_snapshot)
    with pytest.raises(RuntimeError, match="staging har ändrats"):
        active.promote("PROMOTE session1")

    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert not (workspace.session_root / "rollbacks" / "promo1").exists()


def test_directory_fsync_failure_after_rename_restores_original(tmp_path, monkeypatch):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    real_sync = module._sync_directory
    injected = [False]

    def fail_first_source_directory_sync(path):
        if path == project / "core" and not injected[0]:
            injected[0] = True
            raise OSError("simulated source directory fsync failure")
        return real_sync(path)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_sync_directory", fail_first_source_directory_sync)
        with pytest.raises(OSError, match="directory fsync failure"):
            active.promote("PROMOTE session1")

    assert injected[0]
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    record = json.loads((
        workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    ).read_text(encoding="utf-8"))
    assert record["state"] == "reverted"


def _journal_test_crash_before_second_copy(tmp_path, monkeypatch):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    real_copy = module._atomic_copy
    calls = [0]

    def interrupt(source, target, **kwargs):
        calls[0] += 1
        if calls[0] == 2:
            raise SystemExit("synthetic power loss")
        return real_copy(source, target, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_atomic_copy", interrupt)
        with pytest.raises(SystemExit, match="synthetic power loss"):
            active.promote("PROMOTE session1")
    return project, workspace, active


def test_tampered_prepared_journal_is_rejected_without_recovery_writes(
    tmp_path, monkeypatch,
):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    path = workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["planned_hashes"]["core/example.py"] = "0" * 64
    path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(RuntimeError, match="integritet"):
        active.recover_interrupted("promo1", "RECOVER session1 promo1")
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_tampering_state_cannot_hide_pending_journal_from_new_session(
    tmp_path, monkeypatch,
):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    path = workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["state"] = "completed"
    record["promoted_unix_time"] = 100.0
    path.write_text(json.dumps(record), encoding="utf-8")
    other = manager(_second_workspace(project), settings())

    with pytest.raises(RuntimeError, match="skadad återställningsjournal"):
        other.promote("PROMOTE session2")
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_deleted_journal_integrity_key_refuses_recovery(tmp_path, monkeypatch):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    key = project / "runtime" / "selfdev" / ".journal-integrity-key"
    assert key.is_file()
    key.unlink()
    with pytest.raises(RuntimeError, match="integritetsnyckeln"):
        active.recover_interrupted("promo1", "RECOVER session1 promo1")
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_signed_journal_rejects_forbidden_target_inside_project(
    tmp_path, monkeypatch,
):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    forbidden = project / "runtime" / "secret.txt"
    forbidden.parent.mkdir(parents=True, exist_ok=True)
    forbidden.write_text("SAFE\n", encoding="utf-8")
    path = workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    record = active._read_journal(path)
    old = "core/example.py"
    bad = "runtime/secret.txt"
    record["backups"][bad] = record["backups"].pop(old)
    record["planned_hashes"][bad] = record["planned_hashes"].pop(old)
    active._write_journal(path, record)

    with pytest.raises(PermissionError, match="Otillåten källkodsfil"):
        active.recover_interrupted("promo1", "RECOVER session1 promo1")
    assert forbidden.read_text(encoding="utf-8") == "SAFE\n"


def test_signed_journal_roundtrip_allows_normal_rollback(tmp_path):
    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    result = active.promote("PROMOTE session1")
    path = workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    signed = json.loads(path.read_text(encoding="utf-8"))
    assert signed["journal_version"] == 1
    assert len(signed["journal_hmac"]) == 64
    assert result["state"] == "completed"
    assert active.rollback("promo1", "ROLLBACK session1 promo1")[
        "rolled_back"
    ]
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_symlinked_journal_refuses_recovery(tmp_path, monkeypatch):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    path = workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    other = tmp_path / "other-journal.json"
    other.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(other)

    with pytest.raises(RuntimeError, match="symlink"):
        active.recover_interrupted("promo1", "RECOVER session1 promo1")
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_rollback_crash_mid_restore_is_manually_recoverable(tmp_path, monkeypatch):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    old_copy = module._atomic_copy

    def interrupt_during_restore(source, destination, **kwargs):
        if "rollbacks" in str(source):
            raise SystemExit("power loss during rollback")
        return old_copy(source, destination, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_atomic_copy", interrupt_during_restore)
        with pytest.raises(SystemExit, match="power loss during rollback"):
            active.rollback("promo1", "ROLLBACK session1 promo1")

    journal = workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    assert active._read_journal(journal)["state"] == "rollback_prepared"
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"
    assert not (project / "tests" / "test_new.py").exists()

    recovery = active.recover_interrupted(
        "promo1", "RECOVER session1 promo1"
    )
    assert recovery["state"] == "recovered"
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_crash_after_rollback_restored_everything_can_finish_recovery(
    tmp_path, monkeypatch,
):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    real_write = module._atomic_write_record

    def interrupt_when_marking_complete(path, record):
        if record.get("state") == "recovered":
            raise SystemExit("power loss before rollback completion journal")
        return real_write(path, record)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_atomic_write_record", interrupt_when_marking_complete)
        with pytest.raises(SystemExit, match="power loss before rollback completion"):
            active.rollback("promo1", "ROLLBACK session1 promo1")

    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert not (project / "tests" / "test_new.py").exists()
    assert active.recover_interrupted(
        "promo1", "RECOVER session1 promo1"
    )["state"] == "recovered"


def test_interrupted_rollback_journal_blocks_new_promotion_across_sessions(
    tmp_path, monkeypatch,
):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    old_copy = module._atomic_copy

    def abort_during_restore(source, target, **kwargs):
        if "rollbacks" in str(source):
            raise SystemExit("rollback interrupted")
        return old_copy(source, target, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_atomic_copy", abort_during_restore)
        with pytest.raises(SystemExit):
            active.rollback("promo1", "ROLLBACK session1 promo1")

    other = manager(_second_workspace(project), settings())
    with pytest.raises(RuntimeError, match="Ofullständig selfdev-promotion"):
        other.promote("PROMOTE session2")
    assert active.recover_interrupted(
        "promo1", "RECOVER session1 promo1"
    )["state"] == "recovered"


def _legacy_completed_record(tmp_path):
    import json
    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    path = workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy.pop("journal_hmac")
    legacy.pop("journal_version")
    original = json.dumps(legacy, indent=2).encode("utf-8")
    path.write_bytes(original)
    return project, workspace, active, path, original


def test_unsigned_legacy_completed_requires_manual_migration(tmp_path):
    project, workspace, active, path, original = _legacy_completed_record(tmp_path)
    with pytest.raises(RuntimeError, match="saknar integritetsskydd"):
        active.rollback("promo1", "ROLLBACK session1 promo1")
    with pytest.raises(PermissionError, match="migreringsfras"):
        active.migrate_legacy_completed("promo1", "yes")
    assert path.read_bytes() == original
    assert not (path.parent / "promotion.legacy-unsigned.json").exists()
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"

    result = active.migrate_legacy_completed(
        "promo1", "MIGRATE LEGACY session1 promo1"
    )
    assert result["journal_version"] == 1
    assert len(result["journal_hmac"]) == 64
    assert (path.parent / "promotion.legacy-unsigned.json").read_bytes() == original
    assert active.rollback("promo1", "ROLLBACK session1 promo1")[
        "rolled_back"
    ]
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_manual_migration_refuses_unsigned_interrupted_update(
    tmp_path, monkeypatch,
):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    path = workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    journal = json.loads(path.read_text(encoding="utf-8"))
    journal.pop("journal_hmac")
    journal.pop("journal_version")
    path.write_text(json.dumps(journal), encoding="utf-8")
    before = path.read_bytes()

    with pytest.raises(RuntimeError, match="Endast slutförda"):
        active.migrate_legacy_completed(
            "promo1", "MIGRATE LEGACY session1 promo1"
        )
    assert path.read_bytes() == before
    assert not (path.parent / "promotion.legacy-unsigned.json").exists()
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_migration_refuses_forged_source_hashes_and_newer_user_edits(tmp_path):
    project, workspace, active, path, original = _legacy_completed_record(tmp_path)
    raw = json.loads(original)
    raw["after_hashes"]["core/example.py"] = "0" * 64
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Aktiv kod skiljer"):
        active.migrate_legacy_completed(
            "promo1", "MIGRATE LEGACY session1 promo1"
        )
    path.write_bytes(original)
    (project / "core" / "example.py").write_text(
        "USER = 123\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="Aktiv kod skiljer"):
        active.migrate_legacy_completed(
            "promo1", "MIGRATE LEGACY session1 promo1"
        )
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "USER = 123\n"


def test_migration_refuses_backup_symlink_and_hardlink(tmp_path):
    import os
    project, workspace, active, path, original = _legacy_completed_record(tmp_path)
    backup = workspace.session_root / "rollbacks" / "promo1" / "files" / "core" / "example.py"
    safe_content = backup.read_bytes()
    outside = tmp_path / "separate-backup.py"
    outside.write_bytes(safe_content)
    backup.unlink()
    backup.symlink_to(outside)
    with pytest.raises(PermissionError, match="symlink"):
        active.migrate_legacy_completed(
            "promo1", "MIGRATE LEGACY session1 promo1"
        )
    backup.unlink()
    os.link(outside, backup)
    with pytest.raises(RuntimeError, match="hårdlänk"):
        active.migrate_legacy_completed(
            "promo1", "MIGRATE LEGACY session1 promo1"
        )
    assert path.read_bytes() == original


def test_signed_normal_rollback_refuses_linked_backup_before_any_write(tmp_path):
    import os
    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    backup = workspace.session_root / "rollbacks" / "promo1" / "files" / "core" / "example.py"
    external = tmp_path / "shared-backup.py"
    external.write_bytes(backup.read_bytes())
    backup.unlink()
    os.link(external, backup)

    with pytest.raises(RuntimeError, match="hårdlänk"):
        active.rollback("promo1", "ROLLBACK session1 promo1")
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_manual_migration_can_retry_after_signature_write_is_interrupted(
    tmp_path, monkeypatch,
):
    from core import selfdev_promote as module
    project, workspace, active, path, original = _legacy_completed_record(tmp_path)
    real = module._atomic_write_record
    calls = [0]

    def failed_signature_write(filename, record):
        calls[0] += 1
        if calls[0] == 1:
            raise SystemExit("crash before signing")
        return real(filename, record)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_atomic_write_record", failed_signature_write)
        with pytest.raises(SystemExit, match="before signing"):
            active.migrate_legacy_completed(
                "promo1", "MIGRATE LEGACY session1 promo1"
            )
    archive = path.parent / "promotion.legacy-unsigned.json"
    assert archive.read_bytes() == original
    assert path.read_bytes() == original

    result = active.migrate_legacy_completed(
        "promo1", "MIGRATE LEGACY session1 promo1"
    )
    assert result["journal_version"] == 1
    assert archive.read_bytes() == original
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_repeat_recovery_after_second_process_interruption(tmp_path, monkeypatch):
    from core import selfdev_promote as module
    project, workspace = make_workspace(tmp_path)
    workspace.write_text(
        "tests/test_existing.py", "def test_old():\n    assert 2 == 2\n"
    )
    approve_verification(workspace)
    active = manager(workspace, settings())
    real_write = module._atomic_write_record

    def crash_before_completion(path, record):
        if record.get("state") == "completed":
            raise SystemExit("power cut before completion")
        return real_write(path, record)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_atomic_write_record", crash_before_completion)
        with pytest.raises(SystemExit):
            active.promote("PROMOTE session1")

    original_copy = module._atomic_copy
    calls = [0]

    def crash_during_recovery(source, destination, **kwargs):
        calls[0] += 1
        if calls[0] == 2:
            raise SystemExit("second power cut")
        return original_copy(source, destination, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_atomic_copy", crash_during_recovery)
        with pytest.raises(SystemExit, match="second power cut"):
            active.recover_interrupted(
                "promo1", "RECOVER session1 promo1"
            )

    record = active.recover_interrupted(
        "promo1", "RECOVER session1 promo1"
    )
    assert record["state"] == "recovered"
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert (project / "tests" / "test_existing.py").read_text(
        encoding="utf-8"
    ) == "def test_ok():\n    assert True\n"
    assert not (project / "tests" / "test_new.py").exists()


def test_journal_duplicate_state_fields_are_rejected_before_recovery(tmp_path, monkeypatch):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    path = workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    raw = path.read_text(encoding="utf-8")
    path.write_text(raw.replace(
        '"state": "prepared",',
        '"state": "completed", "state": "prepared",',
        1,
    ), encoding="utf-8")

    with pytest.raises(RuntimeError, match="JSON är ogiltig"):
        active.recover_interrupted("promo1", "RECOVER session1 promo1")
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_journal_rejects_hardlink_and_nonregular_record(tmp_path, monkeypatch):
    import os
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    path = workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    alias = tmp_path / "duplicate-journal.json"
    os.link(path, alias)
    with pytest.raises(RuntimeError, match="Osäker"):
        active.recover_interrupted("promo1", "RECOVER session1 promo1")
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_large_journal_is_rejected_before_parsing(tmp_path, monkeypatch):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    path = workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    path.write_bytes(b"x" * (1024 * 1024 + 1))
    with pytest.raises(RuntimeError, match="för stor"):
        active.recover_interrupted("promo1", "RECOVER session1 promo1")
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_journal_rejects_nonfinite_json_number(tmp_path, monkeypatch):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    path = workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    raw = path.read_text(encoding="utf-8")
    path.write_text(raw.replace(
        '"rolled_back": false', '"rolled_back": NaN', 1
    ), encoding="utf-8")
    with pytest.raises(RuntimeError, match="JSON är ogiltig"):
        active.recover_interrupted("promo1", "RECOVER session1 promo1")
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_new_integrity_key_is_complete_private_and_hardlink_free(tmp_path):
    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    directory = project / "runtime" / "selfdev"
    key = directory / ".journal-integrity-key"
    import stat
    info = key.lstat()
    assert info.st_size == 32
    assert info.st_nlink == 1
    assert stat.S_ISREG(info.st_mode)
    assert info.st_mode & 0o077 == 0
    assert not list(directory.glob(".journal-key.*"))


def test_corrupt_existing_integrity_key_is_never_regenerated(tmp_path):
    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    key = project / "runtime" / "selfdev" / ".journal-integrity-key"
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_bytes(b"short")
    with pytest.raises(RuntimeError, match="integritetsnyckel"):
        active.promote("PROMOTE session1")
    assert key.read_bytes() == b"short"
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_legacy_migration_uses_exact_examined_journal_snapshot(
    tmp_path, monkeypatch,
):
    from pathlib import Path
    project, workspace, active, path, original = _legacy_completed_record(tmp_path)
    existing_read = Path.read_bytes

    def reject_second_journal_read(self):
        if self == path:
            raise AssertionError("Legacy journal must not be reread after validation")
        return existing_read(self)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", reject_second_journal_read)
        signed = active.migrate_legacy_completed(
            "promo1", "MIGRATE LEGACY session1 promo1"
        )
    assert signed["journal_version"] == 1
    assert (path.parent / "promotion.legacy-unsigned.json").read_bytes() == original
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_key_publication_failure_does_not_leave_partial_private_key(
    tmp_path, monkeypatch,
):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    old_link = module.os.link

    def fail_key_publication(source, target, **kwargs):
        if str(target).endswith(".journal-integrity-key"):
            raise OSError("synthetic key publish failure")
        return old_link(source, target, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(module.os, "link", fail_key_publication)
        with pytest.raises(OSError, match="key publish failure"):
            active.promote("PROMOTE session1")

    folder = project / "runtime" / "selfdev"
    assert not (folder / ".journal-integrity-key").exists()
    assert not list(folder.glob(".journal-key.*"))
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def _read_only_project_snapshot(project):
    return sorted(
        (str(path.relative_to(project)), path.read_bytes())
        for path in project.rglob("*")
        if path.is_file()
    )


def test_inspect_recovery_is_readonly_and_shows_preflight_status(
    tmp_path, monkeypatch,
):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    before = _read_only_project_snapshot(project)
    result = active.inspect_recovery("promo1")
    after = _read_only_project_snapshot(project)
    assert before == after
    assert result["read_only"] is True
    assert result["status"] == "preflight_ok_requires_manual_approval"
    assert result["journal_state"] == "prepared"
    assert result["file_count"] == 2
    assert result["would_restore"] == 1


def test_inspect_recovery_blocks_newer_user_code_without_writes(
    tmp_path, monkeypatch,
):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    (project / "core" / "example.py").write_text(
        "NEWER_USER_WORK = True\n", encoding="utf-8"
    )
    before = _read_only_project_snapshot(project)
    result = active.inspect_recovery("promo1")
    assert result["status"] == "blocked"
    assert "Extern kodändring" in result["reason"]
    assert _read_only_project_snapshot(project) == before


def test_inspect_recovery_blocks_tampered_journal_readonly(
    tmp_path, monkeypatch,
):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    journal = workspace.session_root / "rollbacks" / "promo1" / "promotion.json"
    record = json.loads(journal.read_text(encoding="utf-8"))
    record["state"] = "completed"
    journal.write_text(json.dumps(record), encoding="utf-8")
    before = _read_only_project_snapshot(project)
    result = active.inspect_recovery("promo1")
    assert result["status"] == "blocked"
    assert "integritet" in result["reason"]
    assert _read_only_project_snapshot(project) == before


def test_inspect_recovery_blocks_corrupted_backup_readonly(tmp_path, monkeypatch):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    backup = workspace.session_root / "rollbacks" / "promo1" / "files" / "core" / "example.py"
    backup.write_text("BROKEN_BACKUP\n", encoding="utf-8")
    before = _read_only_project_snapshot(project)
    result = active.inspect_recovery("promo1")
    assert result["status"] == "blocked"
    assert "Backup" in result["reason"]
    assert _read_only_project_snapshot(project) == before


def test_inspect_recovery_reports_completed_without_mutations(tmp_path):
    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    before = _read_only_project_snapshot(project)
    result = active.inspect_recovery("promo1")
    assert result["status"] == "completed_or_resolved"
    assert result["journal_state"] == "completed"
    assert _read_only_project_snapshot(project) == before


def test_inspect_recovery_does_not_create_missing_key_or_journal(tmp_path):
    project, workspace = make_workspace(tmp_path)
    active = manager(workspace, settings())
    before = _read_only_project_snapshot(project)
    result = active.inspect_recovery("missing-promotion")
    assert result["status"] == "blocked"
    assert not (project / "runtime" / "selfdev" / ".journal-integrity-key").exists()
    assert _read_only_project_snapshot(project) == before


def test_private_project_lock_rejects_world_writable_lock_file(tmp_path):
    import os
    project, workspace = make_workspace(tmp_path)
    active = manager(workspace, settings())
    lock_dir = project / "runtime" / "selfdev"
    lock = lock_dir / ".promotion.lock"
    with active._project_mutation_lock():
        assert lock.exists()
    os.chmod(lock, 0o666)
    with pytest.raises(PermissionError, match="låsfil"):
        with active._project_mutation_lock():
            pass
    os.chmod(lock, 0o600)
    with active._project_mutation_lock():
        pass


def test_private_project_lock_rejects_hardlinked_lock(tmp_path):
    import os
    project, workspace = make_workspace(tmp_path)
    active = manager(workspace, settings())
    with active._project_mutation_lock():
        pass
    lock = project / "runtime" / "selfdev" / ".promotion.lock"
    os.link(lock, tmp_path / "alias-lock")
    with pytest.raises(PermissionError, match="låsfil"):
        with active._project_mutation_lock():
            pass


def test_private_selfdev_directory_refuses_symlinked_runtime_parent(tmp_path):
    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    old_runtime = project / "runtime"
    # A workspace fixture creates this directory; replace it with a link.
    outside = tmp_path / "runtime-outside"
    old_runtime.rename(outside)
    old_runtime.symlink_to(outside, target_is_directory=True)
    # Required audit logging now fails closed before selfdev's own check.
    with pytest.raises(RuntimeError, match="Audit-loggen kunde inte skrivas"):
        active.promote("PROMOTE session1")
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_new_rollback_backup_directory_is_private(tmp_path):
    import stat
    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    folder = workspace.session_root / "rollbacks" / "promo1"
    assert stat.S_IMODE(folder.stat().st_mode) & 0o077 == 0
    assert (folder / "promotion.json").is_file()


def test_private_selfdev_directory_rejects_group_writable_metadata(tmp_path):
    import os
    project, workspace = make_workspace(tmp_path)
    active = manager(workspace, settings())
    with active._project_mutation_lock():
        pass
    directory = project / "runtime" / "selfdev"
    os.chmod(directory, 0o775)
    with pytest.raises(PermissionError, match="osäkra behörigheter"):
        with active._project_mutation_lock():
            pass


def test_swap_backup_to_external_symlink_after_first_validation(
    tmp_path, monkeypatch,
):
    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    backup = (
        workspace.session_root / "rollbacks" / "promo1"
        / "files" / "core" / "example.py"
    )
    external = tmp_path / "external-backup.py"
    external.write_bytes(backup.read_bytes())
    original_check = active._verified_backup
    calls = [0]

    def swap_after_validation(root, relative, expected):
        verified = original_check(root, relative, expected)
        calls[0] += 1
        if calls[0] == 2:
            verified.unlink()
            verified.symlink_to(external)
        return verified

    monkeypatch.setattr(active, "_verified_backup", swap_after_validation)
    with pytest.raises(RuntimeError, match="Backup kan inte öppnas säkert"):
        active.rollback("promo1", "ROLLBACK session1 promo1")

    assert external.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_backup_mutates_inside_snapshot_read_and_never_restores(
    tmp_path, monkeypatch,
):
    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    backup = (
        workspace.session_root / "rollbacks" / "promo1"
        / "files" / "core" / "example.py"
    )
    original = active._verified_backup
    calls = [0]

    def mutate_after_first_verification(root, relative, expected):
        verified = original(root, relative, expected)
        calls[0] += 1
        if calls[0] == 2:
            verified.write_text("CORRUPT\n", encoding="utf-8")
        return verified

    monkeypatch.setattr(active, "_verified_backup", mutate_after_first_verification)
    with pytest.raises(RuntimeError, match="Backup ändrades efter verifiering"):
        active.rollback("promo1", "ROLLBACK session1 promo1")

    assert (project / "core" / "example.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"
    assert not list(backup.parent.glob(".verified-backup-*"))


def test_verified_backup_snapshot_preserves_original_permissions(tmp_path):
    import stat

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    original = project / "core" / "example.py"
    original.chmod(0o640)
    active.promote("PROMOTE session1")
    assert active.rollback("promo1", "ROLLBACK session1 promo1")[
        "rolled_back"
    ]
    assert stat.S_IMODE(original.stat().st_mode) == 0o640
    assert not list(
        (workspace.session_root / "rollbacks" / "promo1" / "files" / "core")
        .glob(".verified-backup-*")
    )


def test_orphan_snapshot_inventory_reports_without_changes(tmp_path, monkeypatch):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    backup = (
        workspace.session_root / "rollbacks" / "promo1"
        / "files" / "core"
    )
    orphan = backup / ".verified-backup-simulated.tmp"
    orphan.write_text("LEFT AFTER CRASH\n", encoding="utf-8")
    before = _read_only_project_snapshot(project)
    report = active.inspect_recovery_artifacts("promo1")
    assert report == {
        "promotion_id": "promo1",
        "read_only": True,
        "status": "orphan_snapshots_detected",
        "orphan_snapshot_count": 1,
    }
    assert _read_only_project_snapshot(project) == before
    assert orphan.read_text(encoding="utf-8") == "LEFT AFTER CRASH\n"


def test_orphan_snapshot_inventory_reports_clean_without_mutations(tmp_path):
    project, workspace = make_workspace(tmp_path)
    active = manager(workspace, settings())
    before = _read_only_project_snapshot(project)
    report = active.inspect_recovery_artifacts("missing")
    assert report["status"] == "no_artifacts"
    assert report["orphan_snapshot_count"] == 0
    assert report["read_only"]
    assert _read_only_project_snapshot(project) == before


def test_orphan_snapshot_inventory_never_follows_untrusted_symlink(
    tmp_path, monkeypatch,
):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    external = tmp_path / "outside-copy.txt"
    external.write_text("PRIVATE CONTENT", encoding="utf-8")
    backup_dir = (
        workspace.session_root / "rollbacks" / "promo1"
        / "files" / "core"
    )
    (backup_dir / ".verified-backup-malicious.tmp").symlink_to(external)
    before = _read_only_project_snapshot(project)
    result = active.inspect_recovery_artifacts("promo1")
    assert result["status"] == "blocked"
    assert "Symlink" in result["reason"]
    assert _read_only_project_snapshot(project) == before
    assert external.read_text(encoding="utf-8") == "PRIVATE CONTENT"


def test_orphan_snapshot_inventory_rejects_symlinked_backup_directory(
    tmp_path, monkeypatch,
):
    project, workspace, active = _journal_test_crash_before_second_copy(
        tmp_path, monkeypatch
    )
    external = tmp_path / "outside-folder"
    external.mkdir()
    (external / ".verified-backup-outside.tmp").write_text(
        "OUTSIDE", encoding="utf-8"
    )
    backup_root = (
        workspace.session_root / "rollbacks" / "promo1" / "files"
    )
    (backup_root / "untrusted").symlink_to(
        external, target_is_directory=True
    )
    report = active.inspect_recovery_artifacts("promo1")
    assert report["status"] == "blocked"
    assert "Symlink" in report["reason"]
    assert (external / ".verified-backup-outside.tmp").read_text(
        encoding="utf-8"
    ) == "OUTSIDE"


def test_promotion_verification_reader_rejects_linked_approved_record(tmp_path):
    _, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    outside = tmp_path / "forged-approval.json"
    outside.write_bytes(workspace.verification_path.read_bytes())
    workspace.verification_path.unlink()
    workspace.verification_path.symlink_to(outside)

    with pytest.raises(OSError):
        manager(workspace, settings())._verification()
    assert outside.exists()


