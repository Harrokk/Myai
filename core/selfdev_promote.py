import json
import hmac
import hashlib
import stat
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import time
from contextlib import contextmanager

try:
    import fcntl
except ImportError:  # Windows development can still use msvcrt byte locks.
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

from core.audit_log import (
    AuditLogger,
    audit_outcome_for_exception,
)
from core.selfdev_workspace import (
    SelfDevWorkspace,
    _sha256,
    _allowed_relative_path,
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


def _sync_directory(path):
    """Best-effort durable directory entry flush on POSIX filesystems."""
    if not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = os.open(
        str(path),
        os.O_RDONLY | os.O_DIRECTORY,
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _source_matches_before_replace(destination, expected):
    """Fail closed if a non-cooperating process modified a target."""
    if expected is _NO_EXPECTED_SOURCE:
        return
    if destination.is_symlink():
        raise RuntimeError("Extern ändring av källkodsfil (symlink).")
    if expected is None:
        if os.path.lexists(destination):
            raise RuntimeError("Extern ändring: ny målkodsfil finns redan.")
    elif not destination.is_file() or _sha256(destination) != expected:
        raise RuntimeError(
            "Extern ändring av källkodsfil; promotion avbröts."
        )


_NO_EXPECTED_SOURCE = object()


def _atomic_copy(source, destination, *, expected_old=_NO_EXPECTED_SOURCE):
    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=destination.name + ".",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    os.close(descriptor)
    temp = Path(temp_name)
    try:
        shutil.copy2(source, temp)
        # A power cut after rename must not expose an unsynced new file.
        with temp.open("rb") as handle:
            os.fsync(handle.fileno())
        # Check again immediately before replace, not only during preflight.
        # This narrows but cannot eliminate races with non-cooperating writers.
        _source_matches_before_replace(destination, expected_old)
        os.replace(temp, destination)
        _sync_directory(destination.parent)
    except BaseException:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise


def _atomic_write_record(path, record):
    """Durably stage the recovery record before replacing source files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temporary)
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

    @contextmanager
    def _project_mutation_lock(self):
        """Nonblocking OS lock shared by all selfdev sessions for a project.

        The kernel releases advisory locks if the process crashes. Other
        non-cooperating filesystem writers are outside this protection.
        """
        lock_dir = self.workspace.project_root / "runtime" / "selfdev"
        if lock_dir.is_symlink():
            raise PermissionError("Selfdev-låskatalogen får inte vara symlink.")
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / ".promotion.lock"
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        descriptor = os.open(str(lock_path), flags, 0o600)
        acquired = False
        try:
            if fcntl is not None:
                try:
                    fcntl.flock(
                        descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB
                    )
                except BlockingIOError as error:
                    raise RuntimeError(
                        "En annan selfdev-uppdatering pågår i projektet."
                    ) from error
            elif msvcrt is not None:
                try:
                    if os.fstat(descriptor).st_size == 0:
                        os.write(descriptor, b"0")
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                except OSError as error:
                    raise RuntimeError(
                        "En annan selfdev-uppdatering pågår i projektet."
                    ) from error
            else:
                raise RuntimeError("Operativsystemet saknar säkert selfdev-lås.")
            acquired = True
            yield
        finally:
            if acquired:
                if fcntl is not None:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                else:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            os.close(descriptor)

    def _journal_integrity_key(self, *, create=False):
        """Detect altered journal data using a local private project key."""
        directory = self.workspace.project_root / "runtime" / "selfdev"
        if directory.is_symlink():
            raise RuntimeError("Selfdev-nyckelkatalogen är en symlink.")
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        path = directory / ".journal-integrity-key"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if create:
            try:
                fd = os.open(str(path), flags, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(secrets.token_bytes(32))
                    handle.flush()
                    os.fsync(handle.fileno())
                _sync_directory(directory)
        if path.is_symlink():
            raise RuntimeError("Selfdev-integritetsnyckeln är en symlink.")
        read_flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            read_flags |= os.O_NOFOLLOW
        try:
            fd = os.open(str(path), read_flags)
        except OSError as error:
            raise RuntimeError(
                "Selfdev-integritetsnyckeln saknas eller kan inte läsas."
            ) from error
        with os.fdopen(fd, "rb") as handle:
            metadata = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or (os.name == "posix" and metadata.st_mode & 0o077)
            ):
                raise RuntimeError("Osäker selfdev-integritetsnyckel.")
            secret = handle.read(33)
        if len(secret) != 32:
            raise RuntimeError("Ogiltig selfdev-integritetsnyckel.")
        return secret

    def _write_journal(self, path, record):
        if not isinstance(record, dict):
            raise RuntimeError("Ogiltig återställningsjournal.")
        copy = dict(record)
        copy.pop("journal_hmac", None)
        copy["journal_version"] = 1
        payload = json.dumps(
            copy, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        copy["journal_hmac"] = hmac.new(
            self._journal_integrity_key(create=True),
            payload, hashlib.sha256,
        ).hexdigest()
        _atomic_write_record(path, copy)

    def _read_journal(self, path):
        if Path(path).is_symlink():
            raise RuntimeError("Återställningsjournalen är en symlink.")
        record = _read_json(path)
        if not isinstance(record, dict) or record.get("journal_version") != 1:
            raise RuntimeError("Återställningsjournal saknar integritetsskydd.")
        signature = record.get("journal_hmac")
        if not isinstance(signature, str) or len(signature) != 64:
            raise RuntimeError("Återställningsjournalens integritet är ogiltig.")
        unsigned = dict(record)
        unsigned.pop("journal_hmac")
        try:
            payload = json.dumps(
                unsigned, sort_keys=True, ensure_ascii=False,
                separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                "Återställningsjournalens innehåll är ogiltigt."
            ) from error
        computed = hmac.new(
            self._journal_integrity_key(), payload, hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, computed):
            raise RuntimeError(
                "Återställningsjournalens integritet kunde inte verifieras."
            )
        return record

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
        relative = Path(relative)
        if not _allowed_relative_path(relative):
            raise PermissionError("Otillåten källkodsfil i promotion-journalen.")
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

            if current.is_symlink():
                raise PermissionError(
                    "Promotion genom symlink är inte tillåten."
                )

        if target.is_symlink():
            raise PermissionError(
                "Promotion till symlink är inte tillåten."
            )

        return target

    def _require_no_interrupted_promotion(self):
        # An interrupted update in *any* known session cannot be covered
        # by a new update in another session.
        sources = {
            self.workspace.project_root / "runtime" / "selfdev",
            self.workspace.session_root.parent,
        }
        for sessions_root in sources:
            if not sessions_root.exists():
                continue
            if sessions_root.is_symlink():
                raise RuntimeError("Selfdev-sessionkatalogen är en symlink.")
            for session_root in sessions_root.iterdir():
                if session_root.is_symlink():
                    raise RuntimeError("Otillåten selfdev-sessionsymlink.")
                if not session_root.is_dir():
                    continue
                journal_dir = session_root / "rollbacks"
                if journal_dir.is_symlink():
                    raise RuntimeError("Otillåten selfdev-rollbacksymlink.")
                if not journal_dir.exists():
                    continue
                for candidate in journal_dir.iterdir():
                    if candidate.is_symlink():
                        raise RuntimeError("Otillåten selfdev-journalsymlink.")
                    if not candidate.is_dir():
                        continue
                    record_path = candidate / "promotion.json"
                    if not record_path.is_file() or record_path.is_symlink():
                        raise RuntimeError(
                            "Ofullständig selfdev-promotion saknar återställningsjournal."
                        )
                    try:
                        record = self._read_journal(record_path)
                    except (OSError, ValueError, TypeError, RuntimeError) as error:
                        raise RuntimeError(
                            "Selfdev-promotion har en skadad återställningsjournal."
                        ) from error
                    if not isinstance(record, dict):
                        raise RuntimeError("Ogiltig återställningsjournal.")
                    status = record.get("state")
                    if status in {"completed", "recovered", "reverted"}:
                        continue
                    if status is None and record.get("promoted_unix_time"):
                        continue
                    raise RuntimeError(
                        "Ofullständig selfdev-promotion måste återställas manuellt."
                    )

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
            with self._project_mutation_lock():
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

    def _promote_impl(self, approval_phrase):
        self._require_promotion_enabled()
        expected = "PROMOTE " + self.workspace.session_id
        if str(approval_phrase) != expected:
            raise PermissionError("Fel manuell promotion-frase.")

        self._require_no_interrupted_promotion()
        verification, changes, paths = self._preflight_promotion()
        promotion_id = _safe_identifier(self.promotion_id_factory())
        rollback_root = (
            self.workspace.session_root / "rollbacks" / promotion_id
        )
        if rollback_root.exists():
            raise FileExistsError("Promotion-ID finns redan.")
        rollback_root.mkdir(parents=True, exist_ok=False)

        # Make parent directory entries durable before relying on a
        # journal stored under this newly created promotion directory.
        _sync_directory(rollback_root.parent)
        _sync_directory(rollback_root.parent.parent)
        backups = {}
        planned_hashes = {}
        try:
            for relative in paths:
                source = self.workspace.workspace_root / relative
                target = self._safe_project_target(relative)
                planned_hashes[relative] = changes["manifest"][relative]
                if _sha256(source) != planned_hashes[relative]:
                    raise RuntimeError(
                        "Källfil i staging har ändrats efter verifiering."
                    )
                if target.exists():
                    old_digest = _sha256(target)
                    backup = self._safe_backup_path(rollback_root, relative)
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    # Backups are not source promotions; copy and sync them
                    # separately so source-replace fault injection remains
                    # precise and backups stay durable before PREPARED.
                    shutil.copy2(target, backup)
                    with backup.open("rb") as handle:
                        os.fsync(handle.fileno())
                    _sync_directory(backup.parent)
                    # The source may have changed while backup was copied.
                    if (
                        _sha256(backup) != old_digest
                        or _sha256(target) != old_digest
                    ):
                        raise RuntimeError(
                            "Extern ändring under säkerhetskopiering."
                        )
                    backups[relative] = {
                        "existed": True,
                        "sha256": old_digest,
                    }
                else:
                    backups[relative] = {"existed": False, "sha256": None}
            # Ensure nested backup directory entries reach stable storage.
            for current_dir in sorted(
                {parent for parent in (rollback_root / "files").rglob("*")
                 if parent.is_dir()},
                key=lambda p: len(p.parts),
                reverse=True,
            ) if (rollback_root / "files").exists() else ():
                _sync_directory(current_dir)
            _sync_directory(rollback_root)
        except BaseException:
            # No active file has been modified before the journal is
            # prepared; remove an unusable partial backup safely.
            shutil.rmtree(rollback_root)
            _sync_directory(rollback_root.parent)
            raise

        journal = {
            "session_id": self.workspace.session_id,
            "promotion_id": promotion_id,
            "state": "prepared",
            "verification_manifest_digest": verification[
                "workspace_manifest_digest"
            ],
            "changed": changes["changed"],
            "added": changes["added"],
            "backups": backups,
            "planned_hashes": planned_hashes,
            "after_hashes": {},
            "rolled_back": False,
        }
        record_path = rollback_root / "promotion.json"
        # Power loss after this write can be recovered via the backups and
        # intended content hashes. No active file is touched before this.
        self._write_journal(record_path, journal)

        applied = []
        after_hashes = {}
        try:
            for relative in paths:
                source = self.workspace.workspace_root / relative
                target = self._safe_project_target(relative)
                if _sha256(source) != planned_hashes[relative]:
                    raise RuntimeError(
                        "Källfil i staging har ändrats efter verifiering."
                    )
                # Include current target before copying so a rename followed
                # by a failed fsync still leaves a recoverable PREPARED record.
                applied.append(relative)
                _atomic_copy(
                    source, target,
                    expected_old=backups[relative]["sha256"],
                )
                after_hashes[relative] = _sha256(target)
                if after_hashes[relative] != planned_hashes[relative]:
                    raise RuntimeError(
                        "Promoterad kodfil matchar inte verifierad version."
                    )

            record = {
                **journal,
                "state": "completed",
                "promoted_unix_time": time.time(),
                "after_hashes": after_hashes,
            }
            self._write_journal(record_path, record)
        except Exception:
            # Restore only known before/after versions. If an external
            # writer changed *any* touched file, leave PREPARED for
            # explicit manual recovery rather than clobber their work.
            to_restore = []
            for relative in applied:
                target = self._safe_project_target(relative)
                original = backups[relative]["sha256"]
                desired = planned_hashes[relative]
                if target.is_symlink():
                    raise RuntimeError(
                        "Extern filändring under promotion; manuell återställning krävs."
                    )
                if not os.path.lexists(target):
                    if original is not None:
                        raise RuntimeError(
                            "Extern filändring under promotion; manuell återställning krävs."
                        )
                    continue
                observed = _sha256(target)
                if observed not in {original, desired}:
                    raise RuntimeError(
                        "Extern filändring under promotion; manuell återställning krävs."
                    )
                if observed != original:
                    to_restore.append(relative)
            self._restore_from_backup(rollback_root, backups, to_restore)
            self._write_journal(
                record_path,
                {
                    **journal,
                    "state": "reverted",
                    "rolled_back": True,
                    "reverted_unix_time": time.time(),
                },
            )
            raise

        return record

    def _safe_backup_path(
        self,
        rollback_root,
        relative,
    ):
        if not _allowed_relative_path(relative):
            raise PermissionError("Otillåten backup-sökväg.")
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
                    _sync_directory(target.parent)
                except FileNotFoundError:
                    pass

    def recover_interrupted(self, promotion_id, approval_phrase):
        """Explicit, idempotent recovery; never triggered automatically."""
        identifier = _safe_identifier(promotion_id)
        expected = (
            "RECOVER " + self.workspace.session_id + " " + identifier
        )
        target_label = "selfdev/" + self.workspace.session_id
        self.audit_logger.write_attempt(
            action="selfdev_recover",
            component="selfdev",
            target=target_label,
            details={"promotion_id": identifier},
        )
        try:
            if str(approval_phrase) != expected:
                raise PermissionError("Fel manuell recovery-frase.")
            with self._project_mutation_lock():
                record = self._recover_interrupted_impl(identifier)
        except Exception as error:
            self.audit_logger.write_result(
                action="selfdev_recover",
                component="selfdev",
                outcome=audit_outcome_for_exception(error),
                target=target_label,
                details={
                    "promotion_id": identifier,
                    "error_type": type(error).__name__,
                },
            )
            raise
        self.audit_logger.write_result(
            action="selfdev_recover",
            component="selfdev",
            outcome="success",
            target=target_label,
            details={"promotion_id": identifier},
        )
        return record

    def _recover_interrupted_impl(self, identifier):
        rollback_root = self.workspace.session_root / "rollbacks" / identifier
        record_path = rollback_root / "promotion.json"
        record = self._read_journal(record_path)
        if not isinstance(record, dict) or record.get("state") != "prepared":
            raise RuntimeError(
                "Återställning kräver en ofullständig prepared-journal."
            )
        if (
            record.get("promotion_id") != identifier
            or record.get("session_id") != self.workspace.session_id
        ):
            raise PermissionError("Återställningsjournalen gäller fel session.")

        backups = record.get("backups")
        planned = record.get("planned_hashes")
        if (
            not isinstance(backups, dict)
            or not isinstance(planned, dict)
            or not backups
            or set(backups) != set(planned)
        ):
            raise RuntimeError("Ofullständiga återställningsuppgifter.")

        # Complete validation before the first write, so a later, unrelated
        # change to one file cannot cause a partially restored project.
        need_restore = []
        for relative, before in backups.items():
            if not isinstance(relative, str) or not isinstance(before, dict):
                raise RuntimeError("Ogiltiga återställningsuppgifter.")
            if (
                not relative
                or Path(relative).is_absolute()
                or ".." in Path(relative).parts
            ):
                raise PermissionError("Otillåten återställningssökväg.")
            target = self._safe_project_target(relative)
            after_sha = planned[relative]
            if not isinstance(after_sha, str) or len(after_sha) != 64:
                raise RuntimeError("Ogiltigt SHA256 i journalen.")
            existed = before.get("existed")
            if type(existed) is not bool:
                raise RuntimeError("Ogiltigt backupstatus i journalen.")
            expected_original = before.get("sha256")
            if existed:
                backup = self._safe_backup_path(rollback_root, relative)
                if not backup.is_file() or _sha256(backup) != expected_original:
                    raise RuntimeError("Backup är skadad eller saknas.")
                if not target.is_file():
                    raise RuntimeError(
                        "Aktiv fil saknas eller har ändrats efter avbrottet."
                    )
                current_sha = _sha256(target)
                if current_sha not in {expected_original, after_sha}:
                    raise RuntimeError(
                        "Aktiv källkod har nyare arbete; återställning stoppades."
                    )
                if current_sha != expected_original:
                    need_restore.append(relative)
            else:
                if expected_original is not None:
                    raise RuntimeError("Ogiltig backupmetadata.")
                if target.exists():
                    if not target.is_file() or _sha256(target) != after_sha:
                        raise RuntimeError(
                            "Aktiv källkod har nyare arbete; återställning stoppades."
                        )
                    need_restore.append(relative)

        self._restore_from_backup(rollback_root, backups, need_restore)
        record["state"] = "recovered"
        record["rolled_back"] = True
        record["recovered_unix_time"] = time.time()
        self._write_journal(record_path, record)
        return record

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
            with self._project_mutation_lock():
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

        record = self._read_journal(record_path)
        if not isinstance(record, dict):
            raise RuntimeError("Ogiltig återställningsjournal.")
        state = record.get("state")
        if state == "prepared":
            raise RuntimeError(
                "Ofullständig promotion kräver RECOVER, inte vanlig ROLLBACK."
            )
        if state in {"reverted", "recovered"}:
            raise RuntimeError("Promotionen är redan återställd.")
        if state not in {"completed", None}:
            raise RuntimeError("Okänt promotion-läge; rollback avböjs.")
        if state is None and not record.get("promoted_unix_time"):
            raise RuntimeError("Äldre rollback-record saknar slutförd promotion.")

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

        backups = record.get("backups", {})
        if not isinstance(backups, dict) or set(backups) != set(after_hashes):
            raise RuntimeError("Ofullständig rollback-metadata.")
        paths = sorted(backups)
        for relative, information in backups.items():
            if not isinstance(information, dict):
                raise RuntimeError("Ogiltig rollback-backup.")
            if information.get("existed"):
                backup = self._safe_backup_path(rollback_root, relative)
                if (
                    not backup.is_file()
                    or _sha256(backup) != information.get("sha256")
                ):
                    raise RuntimeError("Rollback-backup har ändrats eller saknas.")
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
        self._write_journal(record_path, record)

        return record
