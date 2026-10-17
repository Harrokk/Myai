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
    original = module._copy_verified_backup

    def refuse_backup(source, destination, *args, **kwargs):
        if "rollbacks" in str(destination):
            raise OSError("synthetic backup storage failure")
        return original(source, destination, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_copy_verified_backup", refuse_backup)
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




def test_atomic_promotion_copy_rejects_unverified_source_before_replace(
    tmp_path,
):
    import hashlib
    from core import selfdev_promote as module

    source = tmp_path / "candidate.py"
    target = tmp_path / "active.py"
    source.write_text("UNVERIFIED = True\n", encoding="utf-8")
    target.write_text("CURRENT = True\n", encoding="utf-8")
    expected = hashlib.sha256(b"EXPECTED = True\n").hexdigest()

    with pytest.raises(RuntimeError, match="staging har ändrats"):
        module._atomic_copy(
            source, target, expected_source=expected
        )
    assert target.read_text(encoding="utf-8") == "CURRENT = True\n"
    assert not list(tmp_path.glob(".active.py.*.tmp"))


def test_atomic_promotion_copy_ignores_source_name_symlink_swap_after_open(
    tmp_path, monkeypatch
):
    import hashlib
    import os
    from core import selfdev_promote as module

    source = tmp_path / "candidate.py"
    target = tmp_path / "active.py"
    outside = tmp_path / "confidential.py"
    contents = b"SAFE = True\n"
    source.write_bytes(contents)
    outside.write_text("SECRET = True\n", encoding="utf-8")
    real_open = os.open
    swaps = []

    def swap_source_after_open(path, flags, *args, **kwargs):
        descriptor = real_open(path, flags, *args, **kwargs)
        if path == "candidate.py" and kwargs.get("dir_fd") is not None:
            source.rename(tmp_path / "candidate-old.py")
            source.symlink_to(outside)
            swaps.append(True)
        return descriptor

    monkeypatch.setattr(module.os, "open", swap_source_after_open)
    module._atomic_copy(
        source, target,
        expected_source=hashlib.sha256(contents).hexdigest(),
    )
    assert swaps == [True]
    assert target.read_bytes() == contents
    assert outside.read_text(encoding="utf-8") == "SECRET = True\n"


def test_atomic_promotion_copy_rejects_parent_link_before_open(
    tmp_path, monkeypatch
):
    import os
    from core import selfdev_promote as module

    source = tmp_path / "candidate.py"
    source.write_text("VALUE = 2\n", encoding="utf-8")
    inside = tmp_path / "active"
    inside.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "dest.py").write_text("PRIVATE = True\n", encoding="utf-8")
    real_open = os.open
    changed = []

    def swap_before_dir_open(path, flags, *args, **kwargs):
        if path == "active" and kwargs.get("dir_fd") is not None:
            inside.rename(tmp_path / "active-original")
            inside.symlink_to(outside, target_is_directory=True)
            changed.append(True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", swap_before_dir_open)
    with pytest.raises(OSError):
        module._atomic_copy(source, inside / "dest.py")

    assert changed == [True]
    assert (outside / "dest.py").read_text(encoding="utf-8") == "PRIVATE = True\n"


def test_atomic_promotion_copy_targets_pinned_parent_if_alias_swaps(
    tmp_path, monkeypatch
):
    import os
    from core import selfdev_promote as module

    source = tmp_path / "candidate.py"
    source.write_text("SAFE = True\n", encoding="utf-8")
    inside = tmp_path / "active"
    inside.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    protected = outside / "dest.py"
    protected.write_text("PRIVATE = True\n", encoding="utf-8")
    real_replace = os.replace
    did_swap = []

    def swap_at_replace(temp, name, **kwargs):
        if name == "dest.py" and kwargs.get("dst_dir_fd") is not None:
            inside.rename(tmp_path / "active-original")
            inside.symlink_to(outside, target_is_directory=True)
            did_swap.append(True)
        return real_replace(temp, name, **kwargs)

    monkeypatch.setattr(module.os, "replace", swap_at_replace)
    module._atomic_copy(source, inside / "dest.py")
    assert did_swap == [True]
    assert (tmp_path / "active-original" / "dest.py").read_text(
        encoding="utf-8"
    ) == "SAFE = True\n"
    assert protected.read_text(encoding="utf-8") == "PRIVATE = True\n"


def test_atomic_promotion_copy_replaces_final_symlink_without_following(
    tmp_path, monkeypatch
):
    import os
    from core import selfdev_promote as module

    source = tmp_path / "candidate.py"
    source.write_text("STAGED = True\n", encoding="utf-8")
    target = tmp_path / "active.py"
    target.write_text("OLD = True\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("DO_NOT_CHANGE = True\n", encoding="utf-8")
    real_replace = os.replace

    def swap_final_before_rename(temp, name, **kwargs):
        if name == "active.py" and kwargs.get("dst_dir_fd") is not None:
            target.unlink()
            target.symlink_to(outside)
        return real_replace(temp, name, **kwargs)

    monkeypatch.setattr(module.os, "replace", swap_final_before_rename)
    module._atomic_copy(source, target)
    assert target.read_text(encoding="utf-8") == "STAGED = True\n"
    assert not target.is_symlink()
    assert outside.read_text(encoding="utf-8") == "DO_NOT_CHANGE = True\n"


def test_atomic_promotion_copy_preserves_safe_source_permissions(tmp_path):
    import stat
    from core import selfdev_promote as module

    source = tmp_path / "script.sh"
    source.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    source.chmod(0o751)
    target = tmp_path / "script-active.sh"
    module._atomic_copy(source, target)
    assert stat.S_IMODE(target.stat().st_mode) == 0o751


def test_rollback_added_file_delete_refuses_replaced_symlink(tmp_path):
    import hashlib

    from core.selfdev_promote import SelfDevPromotionManager

    inside = tmp_path / "source"
    inside.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET = True\n", encoding="utf-8")
    target = inside / "new.py"
    content = b"SAFE = True\n"
    target.write_bytes(content)
    target.unlink()
    target.symlink_to(outside)

    with pytest.raises(RuntimeError, match="Ny fil saknas eller har ändrats"):
        SelfDevPromotionManager._unlink_verified_added(
            target, hashlib.sha256(content).hexdigest()
        )

    assert target.is_symlink()
    assert outside.read_text(encoding="utf-8") == "SECRET = True\n"


def test_rollback_added_file_delete_refuses_external_content_change(tmp_path):
    import hashlib

    from core.selfdev_promote import SelfDevPromotionManager

    target = tmp_path / "new.py"
    before = b"APPROVED = True\n"
    target.write_bytes(b"EXTERNAL = True\n")

    with pytest.raises(RuntimeError, match="ändrats"):
        SelfDevPromotionManager._unlink_verified_added(
            target, hashlib.sha256(before).hexdigest()
        )
    assert target.read_bytes() == b"EXTERNAL = True\n"


def test_rollback_added_file_delete_uses_pinned_parent_after_alias_swap(
    tmp_path, monkeypatch
):
    import hashlib
    import os

    from core.selfdev_promote import SelfDevPromotionManager

    inside = tmp_path / "inside"
    inside.mkdir()
    new_file = inside / "new.py"
    new_file.write_text("STAGED = True\n", encoding="utf-8")
    content_hash = hashlib.sha256(new_file.read_bytes()).hexdigest()

    outside = tmp_path / "outside"
    outside.mkdir()
    protected = outside / "new.py"
    protected.write_text("PROTECTED = True\n", encoding="utf-8")

    original_unlink = os.unlink
    swapped = []

    def swap_before_unlink(path, *args, **kwargs):
        if path == "new.py" and kwargs.get("dir_fd") is not None:
            inside.rename(tmp_path / "inside-old")
            inside.symlink_to(outside, target_is_directory=True)
            swapped.append(True)
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr("core.selfdev_promote.os.unlink", swap_before_unlink)
    SelfDevPromotionManager._unlink_verified_added(new_file, content_hash)

    assert swapped == [True]
    assert not (tmp_path / "inside-old" / "new.py").exists()
    assert protected.read_text(encoding="utf-8") == "PROTECTED = True\n"


def test_rollback_added_file_delete_detects_file_alias_swap_after_hash(
    tmp_path, monkeypatch
):
    import hashlib
    import os

    from core.selfdev_promote import SelfDevPromotionManager

    target = tmp_path / "new.py"
    content = b"STAGED = True\n"
    target.write_bytes(content)
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET = 1\n", encoding="utf-8")
    original_stat = os.stat
    swapped = []

    def swap_during_recheck(path, *args, **kwargs):
        if (
            path == "new.py"
            and kwargs.get("dir_fd") is not None
            and kwargs.get("follow_symlinks") is False
        ):
            target.rename(tmp_path / "old.py")
            target.symlink_to(outside)
            swapped.append(True)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr("core.selfdev_promote.os.stat", swap_during_recheck)
    with pytest.raises(RuntimeError, match="ändrades före"):
        SelfDevPromotionManager._unlink_verified_added(
            target, hashlib.sha256(content).hexdigest()
        )

    assert swapped == [True]
    assert target.is_symlink()
    assert outside.read_text(encoding="utf-8") == "SECRET = 1\n"


def test_rollback_added_file_delete_requires_signed_expected_hash(tmp_path):
    from core.selfdev_promote import SelfDevPromotionManager

    target = tmp_path / "new.py"
    target.write_text("SAFE = True\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="giltig hash"):
        SelfDevPromotionManager._unlink_verified_added(target, None)
    assert target.read_text(encoding="utf-8") == "SAFE = True\n"


def test_journal_atomic_writer_rejects_symlinked_approved_record(tmp_path):
    from core import selfdev_promote as module

    directory = tmp_path / "journal"
    directory.mkdir()
    outside = tmp_path / "external.json"
    outside.write_text('{"state":"PRIVATE"}', encoding="utf-8")
    (directory / "promotion.json").symlink_to(outside)

    with pytest.raises(PermissionError, match="Osäker journalfil"):
        module._atomic_write_record(
            directory / "promotion.json", {"state": "prepared"}
        )
    assert outside.read_text(encoding="utf-8") == '{"state":"PRIVATE"}'
    assert not list(directory.glob(".promotion.json.*.tmp"))


def test_journal_atomic_writer_rejects_hardlinked_target(tmp_path):
    from core import selfdev_promote as module

    directory = tmp_path / "journal"
    directory.mkdir()
    protected = tmp_path / "protected.json"
    protected.write_text('{"protected":true}', encoding="utf-8")
    os = module.os
    os.link(protected, directory / "promotion.json")

    with pytest.raises(PermissionError, match="Osäker journalfil"):
        module._atomic_write_record(
            directory / "promotion.json", {"state": "prepared"}
        )
    assert protected.read_text(encoding="utf-8") == '{"protected":true}'


def test_journal_atomic_writer_pins_parent_during_symlink_swap(
    tmp_path, monkeypatch
):
    import os
    from core import selfdev_promote as module

    journal = tmp_path / "journal"
    journal.mkdir()
    outside = tmp_path / "external"
    outside.mkdir()
    protected = outside / "promotion.json"
    protected.write_text("PRIVATE", encoding="utf-8")
    real_replace = os.replace
    swaps = []

    def switch_alias(src, dst, *args, **kwargs):
        if dst == "promotion.json" and kwargs.get("dst_dir_fd") is not None:
            journal.rename(tmp_path / "journal-old")
            journal.symlink_to(outside, target_is_directory=True)
            swaps.append(True)
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(module.os, "replace", switch_alias)
    module._atomic_write_record(journal / "promotion.json", {"state": "prepared"})
    assert swaps == [True]
    assert (tmp_path / "journal-old" / "promotion.json").is_file()
    assert protected.read_text(encoding="utf-8") == "PRIVATE"


def test_journal_atomic_writer_failure_preserves_old_and_removes_temp(
    tmp_path, monkeypatch
):
    import os
    from core import selfdev_promote as module

    journal = tmp_path / "journal"
    journal.mkdir()
    target = journal / "promotion.json"
    target.write_text('{"state":"old"}', encoding="utf-8")
    real_replace = os.replace

    def fail_rename(src, dst, *args, **kwargs):
        if dst == "promotion.json" and kwargs.get("dst_dir_fd") is not None:
            raise OSError("synthetic journal rename failure")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(module.os, "replace", fail_rename)
    with pytest.raises(OSError, match="synthetic journal rename failure"):
        module._atomic_write_record(target, {"state": "completed"})
    assert target.read_text(encoding="utf-8") == '{"state":"old"}'
    assert not list(journal.glob(".promotion.json.*.tmp"))


def test_journal_atomic_writer_limits_record_size_before_io(tmp_path):
    from core import selfdev_promote as module

    journal = tmp_path / "journal"
    with pytest.raises(ValueError, match="för stor"):
        module._atomic_write_record(
            journal / "promotion.json", {"blob": "X" * (1024 * 1024)}
        )
    assert not journal.exists()


def test_journal_reader_refuses_parent_symlink_swapped_before_open(
    tmp_path, monkeypatch
):
    import os
    from core import selfdev_promote as module

    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    journal_path = journal_dir / "promotion.json"
    journal_path.write_text('{"state":"prepared"}', encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "promotion.json").write_text(
        '{"state":"FORGED"}', encoding="utf-8"
    )
    real_open = os.open
    changes = []

    def swap_parent(path, flags, *args, **kwargs):
        if path == "journal" and kwargs.get("dir_fd") is not None:
            journal_dir.rename(tmp_path / "journal-old")
            journal_dir.symlink_to(outside, target_is_directory=True)
            changes.append(True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", swap_parent)
    with pytest.raises(RuntimeError, match="kan inte läsas"):
        module.SelfDevPromotionManager._read_recovery_json(journal_path)
    assert changes == [True]
    assert (outside / "promotion.json").read_text(
        encoding="utf-8"
    ) == '{"state":"FORGED"}'


def test_journal_reader_uses_pinned_original_inode_when_alias_swaps(
    tmp_path, monkeypatch
):
    import os
    from core import selfdev_promote as module

    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    journal_path = journal_dir / "promotion.json"
    journal_path.write_text('{"state":"prepared"}', encoding="utf-8")
    outside = tmp_path / "outside.json"
    outside.write_text('{"state":"FORGED"}', encoding="utf-8")
    real_open = os.open
    swaps = []

    def swap_after_open(path, flags, *args, **kwargs):
        descriptor = real_open(path, flags, *args, **kwargs)
        if path == "promotion.json" and kwargs.get("dir_fd") is not None:
            journal_path.rename(journal_dir / "old-promotion.json")
            journal_path.symlink_to(outside)
            swaps.append(True)
        return descriptor

    monkeypatch.setattr(module.os, "open", swap_after_open)
    found = module.SelfDevPromotionManager._read_recovery_json(journal_path)
    assert swaps == [True]
    assert found == {"state": "prepared"}
    assert outside.read_text(encoding="utf-8") == '{"state":"FORGED"}'


def test_journal_reader_detects_concurrent_mutation_of_open_record(
    tmp_path, monkeypatch
):
    import os
    from core import selfdev_promote as module

    journal = tmp_path / "promotion.json"
    journal.write_text('{"state":"prepared"}', encoding="utf-8")
    original = os.fstat
    seen = []

    def change_on_second_fstat(fd):
        if seen:
            journal.write_text('{"state":"changed-now"}', encoding="utf-8")
        seen.append(True)
        return original(fd)

    monkeypatch.setattr(module.os, "fstat", change_on_second_fstat)
    with pytest.raises(RuntimeError, match="ändrades under läsning"):
        module.SelfDevPromotionManager._read_recovery_json(journal)
    assert len(seen) >= 2


def test_journal_reader_rejects_preexisting_parent_symlink(tmp_path):
    from core import selfdev_promote as module

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "promotion.json").write_text(
        '{"state":"FORGED"}', encoding="utf-8"
    )
    (tmp_path / "journal").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="kan inte läsas"):
        module.SelfDevPromotionManager._read_recovery_json(
            tmp_path / "journal" / "promotion.json"
        )


def test_backup_copy_uses_same_pinned_source_for_bytes_and_digest(
    tmp_path, monkeypatch,
):
    import hashlib
    import os
    from core import selfdev_promote as module

    source = tmp_path / "original.py"
    private = tmp_path / "private.py"
    destination = tmp_path / "backup" / "source.py"
    source.write_text("SOURCE = True\n", encoding="utf-8")
    private.write_text("SECRET = True\n", encoding="utf-8")
    real_open = os.open
    swapped = []

    def rename_after_source_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if path == "original.py" and kwargs.get("dir_fd") is not None:
            source.rename(tmp_path / "original-saved.py")
            source.symlink_to(private)
            swapped.append(True)
        return fd

    monkeypatch.setattr(module.os, "open", rename_after_source_open)
    digest = module._copy_verified_backup(source, destination)
    assert swapped == [True]
    assert destination.read_bytes() == b"SOURCE = True\n"
    assert digest == hashlib.sha256(destination.read_bytes()).hexdigest()
    assert private.read_text(encoding="utf-8") == "SECRET = True\n"


def test_backup_copy_fails_closed_when_parent_is_swapped_before_open(
    tmp_path, monkeypatch,
):
    import os
    from core import selfdev_promote as module

    inside = tmp_path / "source"
    inside.mkdir()
    original = inside / "file.py"
    original.write_text("ACTIVE = True\n", encoding="utf-8")
    private = tmp_path / "private"
    private.mkdir()
    (private / "file.py").write_text("SECRET = True\n", encoding="utf-8")
    real_open = os.open
    swapped = []

    def swap_before_open(path, flags, *args, **kwargs):
        if path == "source" and kwargs.get("dir_fd") is not None:
            inside.rename(tmp_path / "original-dir")
            inside.symlink_to(private, target_is_directory=True)
            swapped.append(True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", swap_before_open)
    with pytest.raises(OSError):
        module._copy_verified_backup(original, tmp_path / "backup" / "file.py")
    assert swapped == [True]
    assert not (tmp_path / "backup").exists()


def test_backup_copy_stages_in_pinned_backup_directory_after_alias_swap(
    tmp_path, monkeypatch,
):
    import os
    from core import selfdev_promote as module

    source = tmp_path / "active.py"
    source.write_text("ACTIVE = True\n", encoding="utf-8")
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    destination = backup_dir / "active.py"
    private = tmp_path / "private"
    private.mkdir()
    protected = private / "active.py"
    protected.write_text("DO_NOT_COPY = True\n", encoding="utf-8")
    real_open = os.open
    switched = []

    def switch_after_destination_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if path == "active.py" and kwargs.get("dir_fd") is not None and (
            flags & os.O_CREAT
        ):
            backup_dir.rename(tmp_path / "backup-old")
            backup_dir.symlink_to(private, target_is_directory=True)
            switched.append(True)
        return fd

    monkeypatch.setattr(module.os, "open", switch_after_destination_open)
    digest = module._copy_verified_backup(source, destination)
    assert switched == [True]
    assert (tmp_path / "backup-old" / "active.py").read_text(
        encoding="utf-8"
    ) == "ACTIVE = True\n"
    assert protected.read_text(encoding="utf-8") == "DO_NOT_COPY = True\n"
    assert len(digest) == 64


def test_backup_copy_rejects_source_changed_during_read_and_cleans_file(
    tmp_path, monkeypatch,
):
    import os
    from core import selfdev_promote as module

    source = tmp_path / "active.py"
    destination = tmp_path / "backup" / "active.py"
    source.write_bytes(b"VALUE = 1\n")
    real_read = os.read
    mutated = []

    def rewrite_during_read(fd, length):
        chunk = real_read(fd, length)
        if chunk == b"VALUE = 1\n" and not mutated:
            source.write_bytes(b"VALUE = 1234567\n")
            mutated.append(True)
        return chunk

    monkeypatch.setattr(module.os, "read", rewrite_during_read)
    with pytest.raises(RuntimeError, match="ändring under säkerhetskopiering"):
        module._copy_verified_backup(source, destination)
    assert mutated == [True]
    assert not destination.exists()


def test_backup_copy_rejects_source_symlink_before_read(tmp_path):
    from core import selfdev_promote as module

    private = tmp_path / "private.py"
    private.write_text("CONFIDENTIAL = True\n", encoding="utf-8")
    source = tmp_path / "active.py"
    source.symlink_to(private)
    with pytest.raises(OSError):
        module._copy_verified_backup(source, tmp_path / "backup" / "active.py")
    assert not (tmp_path / "backup").exists()


def test_verified_backup_rejects_parent_symlink_swap_before_directory_open(
    tmp_path, monkeypatch
):
    import os
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    rollback_root = workspace.session_root / "rollbacks" / "promo1"
    backup_dir = rollback_root / "files" / "core"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "example.py").write_text("SECRET = True\n", encoding="utf-8")
    expected = workspace.metadata()["baseline"]["core/example.py"]
    real_open = os.open
    switches = []

    def switch_before_open(name, flags, *args, **kwargs):
        if name == "core" and kwargs.get("dir_fd") is not None:
            backup_dir.rename(rollback_root / "files" / "core-old")
            backup_dir.symlink_to(outside, target_is_directory=True)
            switches.append(True)
        return real_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", switch_before_open)
    with pytest.raises(RuntimeError, match="Osäker backupfil"):
        active._verified_backup(rollback_root, "core/example.py", expected)
    assert switches == [True]
    assert (outside / "example.py").read_text(encoding="utf-8") == (
        "SECRET = True\n"
    )


def test_backup_snapshot_rejects_symlink_swap_between_verify_and_open(
    tmp_path, monkeypatch
):
    import os
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    rollback_root = workspace.session_root / "rollbacks" / "promo1"
    backup_path = rollback_root / "files" / "core" / "example.py"
    external = tmp_path / "private.py"
    external.write_text("SECRET = True\n", encoding="utf-8")
    expected = workspace.metadata()["baseline"]["core/example.py"]
    real_open = os.open
    opens = []

    def swap_between_opens(name, flags, *args, **kwargs):
        if name == "example.py" and kwargs.get("dir_fd") is not None:
            opens.append(True)
            if len(opens) == 2:
                backup_path.unlink()
                backup_path.symlink_to(external)
        return real_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", swap_between_opens)
    with pytest.raises(RuntimeError, match="Backup kan inte öppnas säkert"):
        with active._backup_verified_snapshot(
            rollback_root, "core/example.py", expected
        ):
            pytest.fail("should not enter unsafe backup snapshot")

    assert opens == [True, True]
    assert external.read_text(encoding="utf-8") == "SECRET = True\n"


def test_verified_backup_rejects_external_content_change(tmp_path):
    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    rollback_root = workspace.session_root / "rollbacks" / "promo1"
    backup_path = rollback_root / "files" / "core" / "example.py"
    backup_path.write_text("TAMPERED = True\n", encoding="utf-8")
    original_hash = workspace.metadata()["baseline"]["core/example.py"]

    with pytest.raises(RuntimeError, match="Backup är skadad"):
        active._verified_backup(rollback_root, "core/example.py", original_hash)


def test_backup_snapshot_temp_and_cleanup_stay_in_pinned_directory(
    tmp_path, monkeypatch
):
    import os
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    rollback_root = workspace.session_root / "rollbacks" / "promo1"
    parent = rollback_root / "files" / "core"
    outside = tmp_path / "outside"
    outside.mkdir()
    protected = outside / "example.py"
    protected.write_text("PRIVATE = True\n", encoding="utf-8")
    original_open = os.open
    swaps = []

    def swap_after_snapshot_open(path, flags, *args, **kwargs):
        descriptor = original_open(path, flags, *args, **kwargs)
        if (
            isinstance(path, str)
            and path.startswith(".verified-backup-")
            and kwargs.get("dir_fd") is not None
            and flags & os.O_EXCL
        ):
            parent.rename(rollback_root / "files" / "core-old")
            parent.symlink_to(outside, target_is_directory=True)
            swaps.append(True)
        return descriptor

    monkeypatch.setattr(module.os, "open", swap_after_snapshot_open)
    expected = workspace.metadata()["baseline"]["core/example.py"]
    with active._backup_verified_snapshot(
        rollback_root, "core/example.py", expected
    ) as snapshot:
        assert snapshot.name.startswith(".verified-backup-")

    assert swaps == [True]
    assert not list(
        (rollback_root / "files" / "core-old").glob(".verified-backup-*")
    )
    assert protected.read_text(encoding="utf-8") == "PRIVATE = True\n"
    assert not list(outside.glob(".verified-backup-*"))


def test_backup_snapshot_cleanup_after_consumer_error(tmp_path):
    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    rollback_root = workspace.session_root / "rollbacks" / "promo1"
    expected = workspace.metadata()["baseline"]["core/example.py"]
    parent = rollback_root / "files" / "core"

    with pytest.raises(OSError, match="simulated restore error"):
        with active._backup_verified_snapshot(
            rollback_root, "core/example.py", expected
        ):
            raise OSError("simulated restore error")

    assert not list(parent.glob(".verified-backup-*"))


def test_backup_snapshot_refuses_preexisting_temporary_symlink(
    tmp_path, monkeypatch
):
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    approve_verification(workspace)
    active = manager(workspace, settings())
    active.promote("PROMOTE session1")
    rollback_root = workspace.session_root / "rollbacks" / "promo1"
    parent = rollback_root / "files" / "core"
    target = tmp_path / "private.py"
    target.write_text("SECRET = True\n", encoding="utf-8")
    alias = parent / (".verified-backup-" + "a" * 24 + ".tmp")
    alias.symlink_to(target)
    monkeypatch.setattr(module.secrets, "token_hex", lambda length: "a" * (length * 2))
    expected = workspace.metadata()["baseline"]["core/example.py"]

    with pytest.raises(FileExistsError):
        with active._backup_verified_snapshot(
            rollback_root, "core/example.py", expected
        ):
            pytest.fail("must not use preexisting temporary file")

    assert alias.is_symlink()
    assert target.read_text(encoding="utf-8") == "SECRET = True\n"


def test_journal_key_refuses_parent_link_swapped_before_directory_open(
    tmp_path, monkeypatch,
):
    import os
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    active = manager(workspace, settings())
    private = project / "runtime" / "selfdev"
    outside = tmp_path / "outside-key-dir"
    outside.mkdir()
    protected = outside / ".journal-integrity-key"
    protected.write_bytes(b"X" * 32)
    real_open = os.open
    swapped = []

    def swap_parent_before_open(path, flags, *args, **kwargs):
        if path == "selfdev" and kwargs.get("dir_fd") is not None:
            private.rename(private.with_name("selfdev-old"))
            private.symlink_to(outside, target_is_directory=True)
            swapped.append(True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", swap_parent_before_open)
    with pytest.raises(OSError):
        active._journal_integrity_key(create=True)
    assert swapped == [True]
    assert protected.read_bytes() == b"X" * 32


def test_journal_key_publication_stays_inside_pinned_directory_if_alias_swaps(
    tmp_path, monkeypatch,
):
    import os
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    active = manager(workspace, settings())
    original_dir = project / "runtime" / "selfdev"
    outside = tmp_path / "outside-key-dir"
    outside.mkdir()
    protected = outside / ".journal-integrity-key"
    protected.write_bytes(b"Y" * 32)
    real_link = os.link
    switched = []

    def redirect_alias_before_publish(source, target, **kwargs):
        if target == ".journal-integrity-key":
            original_dir.rename(original_dir.with_name("selfdev-old"))
            original_dir.symlink_to(outside, target_is_directory=True)
            switched.append(True)
        return real_link(source, target, **kwargs)

    monkeypatch.setattr(module.os, "link", redirect_alias_before_publish)
    secret = active._journal_integrity_key(create=True)

    assert switched == [True]
    assert len(secret) == 32
    assert (project / "runtime" / "selfdev-old" / ".journal-integrity-key").read_bytes() == secret
    assert protected.read_bytes() == b"Y" * 32
    assert not list((project / "runtime" / "selfdev-old").glob(".journal-key.*"))


def test_journal_key_reader_rejects_final_symlink_swapped_before_open(
    tmp_path, monkeypatch,
):
    import os
    from core import selfdev_promote as module

    project, workspace = make_workspace(tmp_path)
    active = manager(workspace, settings())
    valid = active._journal_integrity_key(create=True)
    key = project / "runtime" / "selfdev" / ".journal-integrity-key"
    external = tmp_path / "external-key"
    external.write_bytes(b"Z" * 32)
    real_open = os.open
    swapped = []

    def swap_key_before_open(path, flags, *args, **kwargs):
        if path == ".journal-integrity-key" and kwargs.get("dir_fd") is not None:
            key.rename(key.with_name(".journal-integrity-key-old"))
            key.symlink_to(external)
            swapped.append(True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", swap_key_before_open)
    with pytest.raises(RuntimeError, match="integritetsnyckeln"):
        active._journal_integrity_key()
    assert swapped == [True]
    assert external.read_bytes() == b"Z" * 32
    assert key.with_name(".journal-integrity-key-old").read_bytes() == valid


def test_journal_key_fails_closed_when_existing_key_is_hardlinked(
    tmp_path,
):
    import os

    project, workspace = make_workspace(tmp_path)
    active = manager(workspace, settings())
    key = project / "runtime" / "selfdev" / ".journal-integrity-key"
    original = active._journal_integrity_key(create=True)
    alias = tmp_path / "duplicate-key"
    os.link(key, alias)

    with pytest.raises(RuntimeError, match="integritetsnyckel"):
        active._journal_integrity_key(create=True)
    assert key.read_bytes() == original
    assert alias.read_bytes() == original


def test_journal_key_reader_rejects_modified_key_permissions(tmp_path):
    import os

    project, workspace = make_workspace(tmp_path)
    active = manager(workspace, settings())
    key = project / "runtime" / "selfdev" / ".journal-integrity-key"
    original = active._journal_integrity_key(create=True)
    os.chmod(key, 0o644)
    with pytest.raises(RuntimeError, match="integritetsnyckel"):
        active._journal_integrity_key(create=False)
    assert key.read_bytes() == original
