from pathlib import Path

from biomercs_ml import dataset_manifest
from biomercs_ml.models import ClipRecord


def _record(clip_path="clip1.mp4"):
    return ClipRecord(
        clip_path=clip_path,
        label_kind="bonus_kill",
        n_bonus=1,
        n_bullet=0,
        source_video="video1.mp4",
        session_id=0,
        event_timestamp_s=12.4,
        confidence=0.95,
    )


def test_create_db_then_insert_and_read_back(tmp_path):
    db_path = tmp_path / "manifest.sqlite"
    dataset_manifest.create_db(db_path)

    row_id = dataset_manifest.insert_clip(db_path, _record())
    assert row_id == 1

    rows = dataset_manifest.fetch_random_sample(db_path, n=10)
    assert len(rows) == 1
    assert rows[0][1] == "clip1.mp4"  # clip_path column


def test_fetch_random_sample_respects_limit(tmp_path):
    db_path = tmp_path / "manifest.sqlite"
    dataset_manifest.create_db(db_path)
    for i in range(5):
        dataset_manifest.insert_clip(db_path, _record(clip_path=f"clip{i}.mp4"))

    rows = dataset_manifest.fetch_random_sample(db_path, n=3)
    assert len(rows) == 3


def test_record_review_sets_correct_flag(tmp_path):
    db_path = tmp_path / "manifest.sqlite"
    dataset_manifest.create_db(db_path)
    clip_id = dataset_manifest.insert_clip(db_path, _record())

    dataset_manifest.record_review(db_path, clip_id, correct=False)

    rows = dataset_manifest.fetch_random_sample(db_path, n=10)
    assert rows[0][-3] == 0  # review_correct column


def test_record_review_stores_a_correction_when_the_label_was_wrong(tmp_path):
    db_path = tmp_path / "manifest.sqlite"
    dataset_manifest.create_db(db_path)
    clip_id = dataset_manifest.insert_clip(db_path, _record())

    dataset_manifest.record_review(db_path, clip_id, correct=False, true_n_bonus=1, true_n_bullet=2)

    rows = dataset_manifest.fetch_random_sample(db_path, n=10)
    assert rows[0][-3] == 0  # review_correct
    assert rows[0][-2] == 1  # review_true_n_bonus
    assert rows[0][-1] == 2  # review_true_n_bullet


def test_record_review_leaves_correction_columns_null_when_correct(tmp_path):
    db_path = tmp_path / "manifest.sqlite"
    dataset_manifest.create_db(db_path)
    clip_id = dataset_manifest.insert_clip(db_path, _record())

    dataset_manifest.record_review(db_path, clip_id, correct=True)

    rows = dataset_manifest.fetch_random_sample(db_path, n=10)
    assert rows[0][-3] == 1  # review_correct
    assert rows[0][-2] is None
    assert rows[0][-1] is None


def test_create_db_adds_review_correct_column_to_existing_table(tmp_path):
    import sqlite3

    db_path = tmp_path / "manifest.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE clips (
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
        )"""
    )
    conn.commit()
    conn.close()

    dataset_manifest.create_db(db_path)  # should migrate, not error
    clip_id = dataset_manifest.insert_clip(db_path, _record())
    dataset_manifest.record_review(db_path, clip_id, correct=True)

    rows = dataset_manifest.fetch_random_sample(db_path, n=10)
    assert rows[0][-3] == 1


def test_fetch_reviewed_incorrect_returns_only_clips_marked_wrong(tmp_path):
    db_path = tmp_path / "manifest.sqlite"
    dataset_manifest.create_db(db_path)
    correct_id = dataset_manifest.insert_clip(db_path, _record(clip_path="correct.mp4"))
    wrong_id = dataset_manifest.insert_clip(db_path, _record(clip_path="wrong.mp4"))
    dataset_manifest.insert_clip(db_path, _record(clip_path="unreviewed.mp4"))
    dataset_manifest.record_review(db_path, correct_id, correct=True)
    dataset_manifest.record_review(db_path, wrong_id, correct=False)

    rows = dataset_manifest.fetch_reviewed_incorrect(db_path)

    assert [row[0] for row in rows] == [wrong_id]
