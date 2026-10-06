import json
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import time

from core.audit_log import (
    AuditLogger,
    audit_outcome_for_exception,
)
from core.selfdev_workspace import (
    SelfDevWorkspace,
    _sha256,
)


def _safe_identifier(
    value,
):
    identifier = str(
        value
    )

    if (
        not identifier
        or len(
            identifier
        ) > 96
        or any(
            character
            not in (
                "abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "0123456789_-"
            )
            for character
            in identifier
        )
    ):
        raise ValueError(
            "Ogiltigt promotion-ID."
        )

    return identifier


def _read_json(path):
    return json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )


def _atomic_copy(
    source,
    destination,
):
    source = Path(
        source
    )
    destination = Path(
        destination
    )
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    descriptor, temp_name = (
        tempfile.mkstemp(
            prefix=(
                destination.name
                + "."
            ),
            suffix=".tmp",
            dir=str(
                destination.parent
            ),
        )
    )
    os.close(
        descriptor
    )
    temp = Path(
        temp_name
    )

    try:
        shutil.copy2(
            source,
            temp,
        )
        os.replace(
            temp,
            destination,
        )
    except Exception:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise


class SelfDevPromotionManager:
    def __init__(
        self,
        workspace,
        settings,
        *,
        promotion_id_factory=None,
        audit_logger=None,
    ):
        if not isinstance(
            workspace,
            SelfDevWorkspace,
        ):
            raise TypeError(
                "workspace måste vara en SelfDevWorkspace."
            )

        self.workspace = workspace
        self.settings = settings
        self.config = settings.get(
            "selfdev",
            {},
        )
        self.promotion_id_factory = (
            promotion_id_factory
            or (
                lambda: (
                    time.strftime(
                        "%Y%m%dT%H%M%SZ",
                        time.gmtime(),
                    )
                    + "-"
                    + secrets.token_hex(
                        4
                    )
                )
            )
        )
        self.audit_logger = (
            audit_logger
            or AuditLogger(
                settings,
                workspace.project_root,
            )
        )

    def _require_promotion_enabled(self):
        if not self.config.get(
            "enabled",
            False,
        ):
            raise PermissionError(
                "Selfdev är avstängt i konfigurationen."
            )

        if not self.config.get(
            "promotion_enabled",
            False,
        ):
            raise PermissionError(
                "Selfdev-promotion är avstängd i konfigurationen."
            )

    def _verification(self):
        path = (
            self.workspace
            .verification_path
        )

        if not path.exists():
            raise RuntimeError(
                "Selfdev-sessionen saknar verifieringsresultat."
            )

        data = _read_json(
            path
        )

        if not data.get(
            "passed",
            False,
        ):
            raise RuntimeError(
                "Selfdev-verifieringen är inte godkänd."
            )

        if data.get(
            "sandbox"
        ) != "bubblewrap":
            raise RuntimeError(
                "Promotion kräver Bubblewrap-verifiering."
            )

        if not data.get(
            "network_isolated",
            False,
        ):
            raise RuntimeError(
                "Promotion kräver nätverksisolerad verifiering."
            )

        if data.get(
            "host_devices_exposed",
            True,
        ):
            raise RuntimeError(
                "Promotion kräver verifiering utan host-enheter."
            )

        return data

    def _safe_project_target(
        self,
        relative,
    ):
        root = (
            self.workspace
            .project_root
        )
        target = (
            root
            / relative
        )

        try:
            target.resolve(
                strict=False
            ).relative_to(
                root.resolve()
            )
        except ValueError as error:
            raise PermissionError(
                "Promotion försökte lämna projektroten."
            ) from error

        current = root

        for part in Path(
            relative
        ).parts[:-1]:
            current = (
                current
                / part
            )

            if (
                current.exists()
                and current.is_symlink()
            ):
                raise PermissionError(
                    "Promotion genom symlink är inte tillåten."
                )

        if (
            target.exists()
            and target.is_symlink()
        ):
            raise PermissionError(
                "Promotion till symlink är inte tillåten."
            )

        return target

    def _preflight_promotion(
        self,
    ):
        verification = (
            self._verification()
        )
        changes = (
            self.workspace
            .changed_files()
        )

        if changes[
            "deleted"
        ]:
            raise RuntimeError(
                "Filradering stöds inte i selfdev-promotion."
            )

        if (
            changes[
                "manifest_digest"
            ]
            != verification.get(
                "workspace_manifest_digest"
            )
        ):
            raise RuntimeError(
                "Selfdev-workspacen har ändrats efter verifieringen."
            )

        drift = (
            self.workspace
            .source_drift()
        )

        if drift:
            raise RuntimeError(
                "Aktiv källkod har ändrats sedan selfdev-sessionen skapades: "
                + ", ".join(
                    drift
                )
            )

        changed = (
            changes[
                "changed"
            ]
            + changes[
                "added"
            ]
        )

        if not changed:
            raise RuntimeError(
                "Selfdev-sessionen innehåller inga ändringar."
            )

        return (
            verification,
            changes,
            sorted(
                changed
            ),
        )

    def promote(
        self,
        approval_phrase,
    ):
        target = (
            "selfdev/"
            + self.workspace.session_id
        )
        self.audit_logger.write_attempt(
            action="selfdev_promote",
            component="selfdev",
            target=target,
            details={
                "session_id": (
                    self.workspace.session_id
                ),
            },
        )

        try:
            record = self._promote_impl(
                approval_phrase
            )
        except Exception as error:
            self.audit_logger.write_result(
                action="selfdev_promote",
                component="selfdev",
                outcome=(
                    audit_outcome_for_exception(
                        error
                    )
                ),
                target=target,
                details={
                    "session_id": (
                        self.workspace.session_id
                    ),
                    "error_type": type(
                        error
                    ).__name__,
                },
            )
            raise

        self.audit_logger.write_result(
            action="selfdev_promote",
            component="selfdev",
            outcome="success",
            target=target,
            details={
                "session_id": (
                    self.workspace.session_id
                ),
                "promotion_id": record.get(
                    "promotion_id"
                ),
                "changed_count": len(
                    record.get(
                        "changed",
                        [],
                    )
                ),
                "added_count": len(
                    record.get(
                        "added",
                        [],
                    )
                ),
            },
        )
        return record

    def _promote_impl(
        self,
        approval_phrase,
    ):
        self._require_promotion_enabled()
        expected = (
            "PROMOTE "
            + self.workspace.session_id
        )

        if str(
            approval_phrase
        ) != expected:
            raise PermissionError(
                "Fel manuell promotion-frase."
            )

        (
            verification,
            changes,
            paths,
        ) = (
            self._preflight_promotion()
        )

        promotion_id = _safe_identifier(
            self.promotion_id_factory()
        )

        rollback_root = (
            self.workspace
            .session_root
            / "rollbacks"
            / promotion_id
        )

        if rollback_root.exists():
            raise FileExistsError(
                "Promotion-ID finns redan."
            )

        rollback_root.mkdir(
            parents=True,
            exist_ok=False,
        )
        backups = {}
        after_hashes = {}

        for relative in paths:
            target = (
                self._safe_project_target(
                    relative
                )
            )

            if target.exists():
                backup = self._safe_backup_path(
                    rollback_root,
                    relative,
                )
                backup.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                shutil.copy2(
                    target,
                    backup,
                )
                backups[
                    relative
                ] = {
                    "existed": True,
                    "sha256": (
                        _sha256(
                            target
                        )
                    ),
                }
            else:
                backups[
                    relative
                ] = {
                    "existed": False,
                    "sha256": None,
                }

        applied = []

        try:
            for relative in paths:
                source = (
                    self.workspace
                    .workspace_root
                    / relative
                )
                target = (
                    self._safe_project_target(
                        relative
                    )
                )
                _atomic_copy(
                    source,
                    target,
                )
                applied.append(
                    relative
                )
                after_hashes[
                    relative
                ] = (
                    _sha256(
                        target
                    )
                )
        except Exception:
            self._restore_from_backup(
                rollback_root,
                backups,
                applied,
            )
            raise

        record = {
            "session_id": (
                self.workspace
                .session_id
            ),
            "promotion_id": (
                promotion_id
            ),
            "promoted_unix_time": (
                time.time()
            ),
            "verification_manifest_digest": (
                verification[
                    "workspace_manifest_digest"
                ]
            ),
            "changed": (
                changes[
                    "changed"
                ]
            ),
            "added": (
                changes[
                    "added"
                ]
            ),
            "backups": backups,
            "after_hashes": (
                after_hashes
            ),
            "rolled_back": False,
        }
        (
            rollback_root
            / "promotion.json"
        ).write_text(
            json.dumps(
                record,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        return record

    def _safe_backup_path(
        self,
        rollback_root,
        relative,
    ):
        base = (
            Path(
                rollback_root
            )
            / "files"
        ).resolve(
            strict=False
        )
        candidate = (
            base
            / relative
        ).resolve(
            strict=False
        )

        try:
            candidate.relative_to(
                base
            )
        except ValueError as error:
            raise PermissionError(
                "Rollback-backup försökte lämna backup-roten."
            ) from error

        return candidate

    def _restore_from_backup(
        self,
        rollback_root,
        backups,
        paths,
    ):
        for relative in reversed(
            list(
                paths
            )
        ):
            info = backups[
                relative
            ]
            target = (
                self._safe_project_target(
                    relative
                )
            )

            if info[
                "existed"
            ]:
                backup = self._safe_backup_path(
                    rollback_root,
                    relative,
                )
                _atomic_copy(
                    backup,
                    target,
                )
            else:
                try:
                    target.unlink()
                except FileNotFoundError:
                    pass

    def rollback(
        self,
        promotion_id,
        approval_phrase,
    ):
        target = (
            "selfdev/"
            + self.workspace.session_id
        )
        self.audit_logger.write_attempt(
            action="selfdev_rollback",
            component="selfdev",
            target=target,
            details={
                "session_id": (
                    self.workspace.session_id
                ),
                "promotion_id": str(
                    promotion_id
                ),
            },
        )

        try:
            record = self._rollback_impl(
                promotion_id,
                approval_phrase,
            )
        except Exception as error:
            self.audit_logger.write_result(
                action="selfdev_rollback",
                component="selfdev",
                outcome=(
                    audit_outcome_for_exception(
                        error
                    )
                ),
                target=target,
                details={
                    "session_id": (
                        self.workspace.session_id
                    ),
                    "promotion_id": str(
                        promotion_id
                    ),
                    "error_type": type(
                        error
                    ).__name__,
                },
            )
            raise

        self.audit_logger.write_result(
            action="selfdev_rollback",
            component="selfdev",
            outcome="success",
            target=target,
            details={
                "session_id": (
                    self.workspace.session_id
                ),
                "promotion_id": record.get(
                    "promotion_id"
                ),
            },
        )
        return record

    def _rollback_impl(
        self,
        promotion_id,
        approval_phrase,
    ):
        identifier = _safe_identifier(
            promotion_id
        )
        expected = (
            "ROLLBACK "
            + self.workspace.session_id
            + " "
            + identifier
        )

        if str(
            approval_phrase
        ) != expected:
            raise PermissionError(
                "Fel manuell rollback-frase."
            )

        rollback_root = (
            self.workspace
            .session_root
            / "rollbacks"
            / identifier
        )
        record_path = (
            rollback_root
            / "promotion.json"
        )

        if not record_path.exists():
            raise FileNotFoundError(
                "Promotion-record saknas."
            )

        record = _read_json(
            record_path
        )

        if record.get(
            "rolled_back",
            False,
        ):
            raise RuntimeError(
                "Promotionen är redan rollbackad."
            )

        after_hashes = record.get(
            "after_hashes",
            {},
        )

        for relative, expected_hash in (
            after_hashes.items()
        ):
            target = (
                self._safe_project_target(
                    relative
                )
            )

            if (
                not target.exists()
                or _sha256(
                    target
                )
                != expected_hash
            ):
                raise RuntimeError(
                    "Aktiv källkod har ändrats efter promotion; "
                    "automatisk rollback vägrar skriva över nyare arbete: "
                    + relative
                )

        backups = record.get(
            "backups",
            {},
        )
        paths = sorted(
            backups
        )
        self._restore_from_backup(
            rollback_root,
            backups,
            paths,
        )

        record[
            "rolled_back"
        ] = True
        record[
            "rolled_back_unix_time"
        ] = time.time()
        record_path.write_text(
            json.dumps(
                record,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        return record
