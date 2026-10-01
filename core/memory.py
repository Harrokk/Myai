import sqlite3
from datetime import datetime
from pathlib import Path


IGNORED_WORDS = {
    "jag", "du", "det", "den", "är", "och", "att",
    "har", "kan", "vill", "med", "som", "för",
    "på", "en", "ett", "vad", "hur", "min", "mitt",
    "din", "ditt",
}


class MemoryStore:
    def __init__(self, database_path, max_search_results=10):
        self.database_path = str(Path(database_path))
        self.max_search_results = max_search_results

    def init(self):
        with sqlite3.connect(self.database_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    content TEXT,
                    created_at TEXT
                )
                """
            )

    def save(self, category, content):
        content = content.strip()

        if not content:
            raise ValueError("Minnesinnehållet får inte vara tomt.")

        with sqlite3.connect(self.database_path) as conn:
            conn.execute(
                """
                INSERT INTO memories
                (category, content, created_at)
                VALUES (?, ?, ?)
                """,
                (category, content, datetime.now().isoformat()),
            )

    def get_all(self):
        with sqlite3.connect(self.database_path) as conn:
            return conn.execute(
                """
                SELECT id, category, content, created_at
                FROM memories
                ORDER BY id DESC
                """
            ).fetchall()

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
                    ORDER BY id DESC
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
