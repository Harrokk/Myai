import json
import sqlite3
from datetime import datetime
from pathlib import Path


IGNORED_WORDS = {
    "jag", "du", "det", "den", "är", "och", "att",
    "har", "kan", "vill", "med", "som", "för",
    "på", "en", "ett", "vad", "hur", "min", "mitt",
    "din", "ditt",
}


_LIFECYCLE_COLUMNS = {
    "status": "TEXT NOT NULL DEFAULT 'active'",
    "updated_at": "TEXT",
    "superseded_by": "INTEGER",
    "superseded_at": "TEXT",
}


class MemoryStore:
    def __init__(self, database_path, max_search_results=10):
        self.database_path = str(Path(database_path))
        self.max_search_results = max_search_results

    @staticmethod
    def _now():
        return datetime.now().isoformat()

    @staticmethod
    def _column_names(conn):
        return {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(memories)"
            ).fetchall()
        }

    def _ensure_lifecycle_schema(self, conn):
        columns = self._column_names(conn)

        for name, definition in _LIFECYCLE_COLUMNS.items():
            if name in columns:
                continue

            conn.execute(
                f"ALTER TABLE memories "
                f"ADD COLUMN {name} {definition}"
            )

        conn.execute(
            """
            UPDATE memories
            SET status = 'active'
            WHERE status IS NULL
               OR trim(status) = ''
            """
        )

    def init(self):
        with sqlite3.connect(self.database_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    content TEXT,
                    created_at TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    updated_at TEXT,
                    superseded_by INTEGER,
                    superseded_at TEXT
                )
                """
            )
            self._ensure_lifecycle_schema(
                conn
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    reason TEXT,
                    conflicts_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    resolved_at TEXT,
                    resolution TEXT,
                    memory_id INTEGER,
                    target_memory_id INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_memory_reviews_status_id
                ON memory_reviews(status, id)
                """
            )

    def save(self, category, content):
        value = (content or "").strip()

        if not value:
            raise ValueError("Minnesinnehållet får inte vara tomt.")

        timestamp = self._now()

        with sqlite3.connect(self.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO memories
                (
                    category,
                    content,
                    created_at,
                    status,
                    updated_at
                )
                VALUES (?, ?, ?, 'active', ?)
                """,
                (
                    category,
                    value,
                    timestamp,
                    timestamp,
                ),
            )
            return int(
                cursor.lastrowid
            )

    def contains(self, category, content):
        value = (content or "").strip()

        if not value:
            return False

        with sqlite3.connect(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM memories
                WHERE lower(category) = lower(?)
                  AND lower(trim(content)) = lower(trim(?))
                  AND COALESCE(status, 'active') = 'active'
                LIMIT 1
                """,
                (category, value),
            ).fetchone()

        return row is not None

    def save_if_new(self, category, content):
        value = (content or "").strip()

        if not value:
            raise ValueError("Minnesinnehållet får inte vara tomt.")

        if self.contains(category, value):
            return False

        self.save(category, value)
        return True

    def get_all(self, include_inactive=False):
        where = (
            ""
            if include_inactive
            else "WHERE COALESCE(status, 'active') = 'active'"
        )

        with sqlite3.connect(self.database_path) as conn:
            return conn.execute(
                f"""
                SELECT id, category, content, created_at
                FROM memories
                {where}
                ORDER BY id DESC
                """
            ).fetchall()

    def get_history(self, limit=100):
        count = max(
            1,
            min(
                int(limit),
                1000,
            ),
        )

        with sqlite3.connect(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    category,
                    content,
                    created_at,
                    COALESCE(status, 'active'),
                    updated_at,
                    superseded_by,
                    superseded_at
                FROM memories
                ORDER BY id DESC
                LIMIT ?
                """,
                (count,),
            ).fetchall()

        return [
            {
                "id": row[0],
                "category": row[1],
                "content": row[2],
                "created_at": row[3],
                "status": row[4],
                "updated_at": row[5],
                "superseded_by": row[6],
                "superseded_at": row[7],
            }
            for row in rows
        ]

    def list_active_records(
        self,
        *,
        category=None,
        limit=200,
    ):
        count = max(
            1,
            min(
                int(limit),
                1000,
            ),
        )
        params = []
        category_filter = ""

        if category is not None:
            category_filter = (
                "AND lower(category) = lower(?)"
            )
            params.append(
                str(category)
            )

        params.append(
            count
        )

        with sqlite3.connect(self.database_path) as conn:
            rows = conn.execute(
                f"""
                SELECT
                    id,
                    category,
                    content,
                    created_at,
                    updated_at
                FROM memories
                WHERE COALESCE(status, 'active') = 'active'
                {category_filter}
                ORDER BY
                    COALESCE(updated_at, created_at) DESC,
                    id DESC
                LIMIT ?
                """,
                tuple(
                    params
                ),
            ).fetchall()

        return [
            {
                "id": row[0],
                "category": row[1],
                "content": row[2],
                "created_at": row[3],
                "updated_at": row[4],
                "status": "active",
            }
            for row in rows
        ]

    def supersede(
        self,
        memory_id,
        category,
        content,
    ):
        value = (content or "").strip()

        if not value:
            raise ValueError(
                "Nytt minnesinnehåll får inte vara tomt."
            )

        timestamp = self._now()

        with sqlite3.connect(self.database_path) as conn:
            conn.execute(
                "BEGIN IMMEDIATE"
            )
            old = conn.execute(
                """
                SELECT id, status
                FROM memories
                WHERE id = ?
                """,
                (int(memory_id),),
            ).fetchone()

            if old is None:
                raise ValueError(
                    "Minnet som ska ersättas finns inte."
                )

            if (
                str(
                    old[1]
                    or "active"
                )
                != "active"
            ):
                raise ValueError(
                    "Minnet som ska ersättas är inte aktivt."
                )

            cursor = conn.execute(
                """
                INSERT INTO memories
                (
                    category,
                    content,
                    created_at,
                    status,
                    updated_at
                )
                VALUES (?, ?, ?, 'active', ?)
                """,
                (
                    category,
                    value,
                    timestamp,
                    timestamp,
                ),
            )
            new_id = int(
                cursor.lastrowid
            )

            conn.execute(
                """
                UPDATE memories
                SET
                    status = 'superseded',
                    updated_at = ?,
                    superseded_by = ?,
                    superseded_at = ?
                WHERE id = ?
                """,
                (
                    timestamp,
                    new_id,
                    timestamp,
                    int(memory_id),
                ),
            )

        return new_id

    def list_stale(
        self,
        *,
        max_age_days,
        now=None,
        limit=100,
    ):
        days = float(
            max_age_days
        )

        if days <= 0:
            return []

        reference = (
            now
            if isinstance(
                now,
                datetime,
            )
            else datetime.now()
        )
        stale = []

        for item in self.list_active_records(
            limit=limit
        ):
            raw = (
                item.get(
                    "updated_at"
                )
                or item.get(
                    "created_at"
                )
            )

            try:
                timestamp = datetime.fromisoformat(
                    str(raw)
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            age_days = (
                reference
                - timestamp
            ).total_seconds() / 86400.0

            if age_days >= days:
                value = dict(
                    item
                )
                value[
                    "age_days"
                ] = round(
                    age_days,
                    3,
                )
                stale.append(
                    value
                )

        return stale

    @staticmethod
    def _normalize_conflict_ids(
        conflict_ids,
    ):
        values = []

        for item in (
            conflict_ids
            or []
        ):
            try:
                identifier = int(
                    item
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            if (
                identifier > 0
                and identifier not in values
            ):
                values.append(
                    identifier
                )

        return values[
            :20
        ]

    def enqueue_review(
        self,
        category,
        content,
        *,
        reason="",
        conflict_ids=None,
    ):
        value = str(
            content
            or ""
        ).strip()
        category_value = str(
            category
            or "other"
        ).strip() or "other"

        if not value:
            raise ValueError(
                "Minneskandidaten får inte vara tom."
            )

        conflicts = self._normalize_conflict_ids(
            conflict_ids
        )
        conflicts_json = json.dumps(
            conflicts,
            separators=(
                ",",
                ":",
            ),
        )
        timestamp = self._now()

        with sqlite3.connect(
            self.database_path
        ) as conn:
            existing = conn.execute(
                """
                SELECT id
                FROM memory_reviews
                WHERE status = 'pending'
                  AND lower(category) = lower(?)
                  AND lower(trim(content)) = lower(trim(?))
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    category_value,
                    value,
                ),
            ).fetchone()

            if existing is not None:
                return {
                    "review_id": int(
                        existing[
                            0
                        ]
                    ),
                    "created": False,
                }

            cursor = conn.execute(
                """
                INSERT INTO memory_reviews
                (
                    category,
                    content,
                    reason,
                    conflicts_json,
                    created_at,
                    status
                )
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (
                    category_value,
                    value,
                    str(
                        reason
                        or ""
                    ).strip(),
                    conflicts_json,
                    timestamp,
                ),
            )

        return {
            "review_id": int(
                cursor.lastrowid
            ),
            "created": True,
        }

    @staticmethod
    def _review_row(
        row,
    ):
        try:
            conflicts = json.loads(
                row[
                    4
                ]
                or "[]"
            )
        except (
            TypeError,
            json.JSONDecodeError,
        ):
            conflicts = []

        return {
            "id": int(
                row[
                    0
                ]
            ),
            "category": row[
                1
            ],
            "content": row[
                2
            ],
            "reason": row[
                3
            ],
            "conflict_ids": (
                conflicts
                if isinstance(
                    conflicts,
                    list,
                )
                else []
            ),
            "created_at": row[
                5
            ],
            "status": row[
                6
            ],
            "resolved_at": row[
                7
            ],
            "resolution": row[
                8
            ],
            "memory_id": row[
                9
            ],
            "target_memory_id": row[
                10
            ],
        }

    def list_reviews(
        self,
        *,
        status="pending",
        limit=50,
        conflicts_only=False,
    ):
        count = max(
            1,
            min(
                int(
                    limit
                ),
                200,
            ),
        )
        status_value = str(
            status
            or "pending"
        ).strip().lower()
        params = [
            status_value,
            count,
        ]

        with sqlite3.connect(
            self.database_path
        ) as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    category,
                    content,
                    reason,
                    conflicts_json,
                    created_at,
                    status,
                    resolved_at,
                    resolution,
                    memory_id,
                    target_memory_id
                FROM memory_reviews
                WHERE status = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                tuple(
                    params
                ),
            ).fetchall()

        values = [
            self._review_row(
                row
            )
            for row in rows
        ]

        if conflicts_only:
            values = [
                item
                for item in values
                if item[
                    "conflict_ids"
                ]
            ]

        return values

    def get_review(
        self,
        review_id,
    ):
        with sqlite3.connect(
            self.database_path
        ) as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    category,
                    content,
                    reason,
                    conflicts_json,
                    created_at,
                    status,
                    resolved_at,
                    resolution,
                    memory_id,
                    target_memory_id
                FROM memory_reviews
                WHERE id = ?
                """,
                (
                    int(
                        review_id
                    ),
                ),
            ).fetchone()

        if row is None:
            return None

        return self._review_row(
            row
        )

    def reject_review(
        self,
        review_id,
    ):
        timestamp = self._now()

        with sqlite3.connect(
            self.database_path
        ) as conn:
            cursor = conn.execute(
                """
                UPDATE memory_reviews
                SET
                    status = 'rejected',
                    resolved_at = ?,
                    resolution = 'rejected'
                WHERE id = ?
                  AND status = 'pending'
                """,
                (
                    timestamp,
                    int(
                        review_id
                    ),
                ),
            )

            if cursor.rowcount != 1:
                raise ValueError(
                    "Minnesgranskningen finns inte eller är redan avslutad."
                )

        return True

    def approve_review(
        self,
        review_id,
    ):
        identifier = int(
            review_id
        )
        timestamp = self._now()

        with sqlite3.connect(
            self.database_path
        ) as conn:
            conn.execute(
                "BEGIN IMMEDIATE"
            )
            row = conn.execute(
                """
                SELECT
                    category,
                    content,
                    conflicts_json,
                    status
                FROM memory_reviews
                WHERE id = ?
                """,
                (
                    identifier,
                ),
            ).fetchone()

            if row is None:
                raise ValueError(
                    "Minnesgranskningen finns inte."
                )

            if row[
                3
            ] != "pending":
                raise ValueError(
                    "Minnesgranskningen är redan avslutad."
                )

            try:
                conflicts = json.loads(
                    row[
                        2
                    ]
                    or "[]"
                )
            except (
                TypeError,
                json.JSONDecodeError,
            ):
                conflicts = []

            if conflicts:
                raise PermissionError(
                    (
                        "Minnesgranskningen har konflikter och måste "
                        "ersätta ett uttryckligt målminne eller avvisas."
                    )
                )

            existing = conn.execute(
                """
                SELECT id
                FROM memories
                WHERE lower(category) = lower(?)
                  AND lower(trim(content)) = lower(trim(?))
                  AND COALESCE(status, 'active') = 'active'
                LIMIT 1
                """,
                (
                    row[
                        0
                    ],
                    row[
                        1
                    ],
                ),
            ).fetchone()

            if existing is not None:
                memory_id = int(
                    existing[
                        0
                    ]
                )
                resolution = (
                    "approved_existing_duplicate"
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO memories
                    (
                        category,
                        content,
                        created_at,
                        status,
                        updated_at
                    )
                    VALUES (?, ?, ?, 'active', ?)
                    """,
                    (
                        row[
                            0
                        ],
                        row[
                            1
                        ],
                        timestamp,
                        timestamp,
                    ),
                )
                memory_id = int(
                    cursor.lastrowid
                )
                resolution = "approved"

            conn.execute(
                """
                UPDATE memory_reviews
                SET
                    status = 'approved',
                    resolved_at = ?,
                    resolution = ?,
                    memory_id = ?
                WHERE id = ?
                """,
                (
                    timestamp,
                    resolution,
                    memory_id,
                    identifier,
                ),
            )

        return memory_id

    def replace_from_review(
        self,
        review_id,
        target_memory_id,
    ):
        review_identifier = int(
            review_id
        )
        target_identifier = int(
            target_memory_id
        )
        timestamp = self._now()

        with sqlite3.connect(
            self.database_path
        ) as conn:
            conn.execute(
                "BEGIN IMMEDIATE"
            )
            review = conn.execute(
                """
                SELECT
                    category,
                    content,
                    conflicts_json,
                    status
                FROM memory_reviews
                WHERE id = ?
                """,
                (
                    review_identifier,
                ),
            ).fetchone()

            if review is None:
                raise ValueError(
                    "Minnesgranskningen finns inte."
                )

            if review[
                3
            ] != "pending":
                raise ValueError(
                    "Minnesgranskningen är redan avslutad."
                )

            target = conn.execute(
                """
                SELECT id, status
                FROM memories
                WHERE id = ?
                """,
                (
                    target_identifier,
                ),
            ).fetchone()

            if target is None:
                raise ValueError(
                    "Målminnet finns inte."
                )

            if str(
                target[
                    1
                ]
                or "active"
            ) != "active":
                raise ValueError(
                    "Målminnet är inte aktivt."
                )

            try:
                conflicts = json.loads(
                    review[
                        2
                    ]
                    or "[]"
                )
            except (
                TypeError,
                json.JSONDecodeError,
            ):
                conflicts = []

            normalized_conflicts = self._normalize_conflict_ids(
                conflicts
            )

            if (
                normalized_conflicts
                and target_identifier
                not in normalized_conflicts
            ):
                raise PermissionError(
                    (
                        "Målminnet finns inte bland granskningens "
                        "registrerade konflikter."
                    )
                )

            cursor = conn.execute(
                """
                INSERT INTO memories
                (
                    category,
                    content,
                    created_at,
                    status,
                    updated_at
                )
                VALUES (?, ?, ?, 'active', ?)
                """,
                (
                    review[
                        0
                    ],
                    review[
                        1
                    ],
                    timestamp,
                    timestamp,
                ),
            )
            new_id = int(
                cursor.lastrowid
            )

            conn.execute(
                """
                UPDATE memories
                SET
                    status = 'superseded',
                    updated_at = ?,
                    superseded_by = ?,
                    superseded_at = ?
                WHERE id = ?
                """,
                (
                    timestamp,
                    new_id,
                    timestamp,
                    target_identifier,
                ),
            )
            conn.execute(
                """
                UPDATE memory_reviews
                SET
                    status = 'replaced',
                    resolved_at = ?,
                    resolution = 'replaced',
                    memory_id = ?,
                    target_memory_id = ?
                WHERE id = ?
                """,
                (
                    timestamp,
                    new_id,
                    target_identifier,
                    review_identifier,
                ),
            )

        return new_id

    def delete_memory_permanently(
        self,
        memory_id,
    ):
        identifier = int(
            memory_id
        )

        with sqlite3.connect(
            self.database_path
        ) as conn:
            conn.execute(
                "BEGIN IMMEDIATE"
            )
            row = conn.execute(
                """
                SELECT id
                FROM memories
                WHERE id = ?
                """,
                (
                    identifier,
                ),
            ).fetchone()

            if row is None:
                raise ValueError(
                    "Minnet finns inte."
                )

            conn.execute(
                """
                UPDATE memories
                SET superseded_by = NULL
                WHERE superseded_by = ?
                """,
                (
                    identifier,
                ),
            )
            conn.execute(
                """
                DELETE FROM memories
                WHERE id = ?
                """,
                (
                    identifier,
                ),
            )

        return True

    def search(self, user_message):
        words = user_message.lower().split()

        keywords = [
            word.strip(".,!?")
            for word in words
            if len(word) >= 3 and word not in IGNORED_WORDS
        ]

        if not keywords:
            return []

        results = []

        with sqlite3.connect(self.database_path) as conn:
            for keyword in keywords:
                rows = conn.execute(
                    """
                    SELECT id, category, content, created_at
                    FROM memories
                    WHERE content LIKE ?
                      AND COALESCE(status, 'active') = 'active'
                    ORDER BY
                        COALESCE(updated_at, created_at) DESC,
                        id DESC
                    LIMIT 5
                    """,
                    (f"%{keyword}%",),
                ).fetchall()

                for row in rows:
                    if row not in results:
                        results.append(row)

        return results[: self.max_search_results]

    @staticmethod
    def format(memories):
        if not memories:
            return "Ingen relevant information hittades i långtidsminnet."

        return "".join(
            f"- [{category}] {content}\n"
            for _, category, content, _ in memories
        )
