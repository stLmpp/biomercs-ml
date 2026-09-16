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
