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
