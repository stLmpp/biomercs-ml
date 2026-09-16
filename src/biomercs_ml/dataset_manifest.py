import sqlite3
from pathlib import Path

from biomercs_ml.models import ClipRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_path TEXT NOT NULL,
    label_kind TEXT NOT NULL,
    n_bonus INTEGER NOT NULL,
    n_bullet INTEGER NOT NULL,
    source_video TEXT NOT NULL,
    session_id INTEGER NOT NULL,
    event_timestamp_s REAL NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def create_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def insert_clip(db_path: Path, record: ClipRecord) -> int:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO clips
               (clip_path, label_kind, n_bonus, n_bullet, source_video,
                session_id, event_timestamp_s, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.clip_path,
                record.label_kind,
                record.n_bonus,
                record.n_bullet,
                record.source_video,
                record.session_id,
                record.event_timestamp_s,
                record.confidence,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def fetch_random_sample(db_path: Path, n: int) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("SELECT * FROM clips ORDER BY RANDOM() LIMIT ?", (n,))
        return cursor.fetchall()
    finally:
        conn.close()
