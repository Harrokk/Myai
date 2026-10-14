"""Prototype persistent deduplication for OFFLINE inspection requests only.

Not connected to MyAI promotion/recovery and never represents authorization.
The database path MUST be owned and protected by the future updater identity.
This prototype does not establish that OS separation.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sqlite3
import stat

from core.selfdev_request_protocol import InspectionRequest


_HEX_32 = re.compile(r"^[0-9a-f]{32}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class InspectionClaim:
    status: str
    authorizes_mutation: bool = False
    requires_human_approval: bool = True


class InspectionReplayLedger:
    """Keep all seen IDs to avoid silently re-admitting old requests.

    Operations use SQLite BEGIN IMMEDIATE and unique request_id constraints,
    permitting cooperating separate processes to safely serialize claims.
    No automated pruning, no actual approval and no updater integration.
    """

    def __init__(self, database_path):
        self.path = Path(database_path)

    def _check_location(self):
        parent = self.path.parent
        if parent.is_symlink() or not parent.is_dir():
            raise PermissionError("Inspection ledger parent is unsafe.")
        if self.path.is_symlink():
            raise PermissionError("Inspection ledger cannot be a symlink.")
        if os.name == "posix":
            info = parent.lstat()
            if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise PermissionError("Inspection ledger parent permissions unsafe.")
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PermissionError("Inspection ledger inode is unsafe.")
        if os.name == "posix" and (
            info.st_uid != os.geteuid() or info.st_mode & 0o077
        ):
            raise PermissionError("Inspection ledger must be owner-private.")

    def _ensure_private_file(self):
        # Do not ever truncate or silently repair an existing ledger.
        self._check_location()
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(str(self.path), flags, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        self._check_location()

    def claim(self, request, *, now_unix):
        """Record inspection once. All statuses explicitly deny mutation."""
        if type(request) is not InspectionRequest:
            raise TypeError("A validated inspection request is required.")
        if (
            type(now_unix) is not int or now_unix < 0
            or type(request.expires_unix) is not int
            or type(request.request_id) is not str
            or not _HEX_32.fullmatch(request.request_id)
            or type(request.request_digest) is not str
            or not _HEX_64.fullmatch(request.request_digest)
            or request.action != "inspect_candidate"
            or request.authorizes_mutation is not False
        ):
            raise ValueError("Unsafe inspection ledger claim.")
        if request.expires_unix <= now_unix:
            return InspectionClaim("expired")
        if request.expires_unix > now_unix + 300:
            raise ValueError("Inspection expiry exceeds allowed horizon.")
        self._ensure_private_file()
        with sqlite3.connect(str(self.path), timeout=15.0) as connection:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS inspected_requests (
                  request_id TEXT PRIMARY KEY,
                  request_digest TEXT NOT NULL,
                  first_seen_unix INTEGER NOT NULL,
                  expires_unix INTEGER NOT NULL
                )
                """
            )
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT request_digest FROM inspected_requests WHERE request_id=?",
                (request.request_id,),
            ).fetchone()
            if previous is not None:
                result = (
                    "already_seen"
                    if previous[0] == request.request_digest
                    else "request_id_conflict"
                )
                return InspectionClaim(result)
            connection.execute(
                "INSERT INTO inspected_requests VALUES (?, ?, ?, ?)",
                (request.request_id, request.request_digest,
                 now_unix, request.expires_unix),
            )
        return InspectionClaim("recorded_for_inspection")
