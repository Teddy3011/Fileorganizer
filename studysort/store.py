"""SQLite history of every detected file, plus the student profile."""

import json
import sqlite3
import threading

COLUMNS = [
    "id", "name", "source_path", "detected_at", "size", "course", "type", "confidence", "reason",
    "analysis", "planned_destination", "actual_destination", "status", "error", "completed_at",
]


class Store:
    def __init__(self, path):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._db:
            self._db.execute(f"CREATE TABLE IF NOT EXISTS files ({', '.join(COLUMNS)}, PRIMARY KEY (id))")
            self._db.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)")

    def add(self, record):
        with self._lock, self._db:
            cols = [c for c in COLUMNS if c in record]
            self._db.execute(
                f"INSERT INTO files ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                [record[c] for c in cols],
            )
        return self.get(record["id"])

    def update(self, file_id, **fields):
        unknown = set(fields) - set(COLUMNS)
        if unknown:
            raise ValueError(f"unknown fields {unknown}")
        with self._lock, self._db:
            self._db.execute(
                f"UPDATE files SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                [*fields.values(), file_id],
            )
        return self.get(file_id)

    def get(self, file_id):
        with self._lock:
            row = self._db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return dict(row) if row else None

    def latest_for_path(self, source_path):
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM files WHERE source_path = ? ORDER BY detected_at DESC LIMIT 1", (source_path,)
            ).fetchone()
        return dict(row) if row else None

    def list(self, limit=500):
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM files ORDER BY detected_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def clear(self):
        """Forget history. Never touches files on disk."""
        with self._lock, self._db:
            self._db.execute("DELETE FROM files")

    def get_json(self, key, default=None):
        with self._lock:
            row = self._db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_json(self, key, value):
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, json.dumps(value)))
