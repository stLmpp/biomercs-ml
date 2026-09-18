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
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(SCHEMA)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(clips)")}
        if "review_correct" not in columns:
            conn.execute("ALTER TABLE clips ADD COLUMN review_correct INTEGER")
        if "review_true_n_bonus" not in columns:
            conn.execute("ALTER TABLE clips ADD COLUMN review_true_n_bonus INTEGER")
        if "review_true_n_bullet" not in columns:
            conn.execute("ALTER TABLE clips ADD COLUMN review_true_n_bullet INTEGER")
        conn.commit()
    finally:
        conn.close()


def record_review(
    db_path: Path,
    clip_id: int,
    correct: bool,
    true_n_bonus: int | None = None,
    true_n_bullet: int | None = None,
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """UPDATE clips
               SET review_correct = ?, review_true_n_bonus = ?, review_true_n_bullet = ?
               WHERE id = ?""",
            (1 if correct else 0, true_n_bonus, true_n_bullet, clip_id),
        )
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


def fetch_reviewed_incorrect(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT * FROM clips WHERE review_correct = 0 ORDER BY event_timestamp_s"
        )
        return cursor.fetchall()
    finally:
        conn.close()
