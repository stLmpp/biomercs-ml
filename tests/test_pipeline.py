from pathlib import Path

from biomercs_ml import dataset_manifest, pipeline

VIDEO_PATH = "tests/fixtures/synthetic_static.mp4"


def test_resolve_video_passes_through_local_paths(tmp_path):
    result = pipeline.resolve_video(VIDEO_PATH, tmp_path)
    assert result == Path(VIDEO_PATH)


def test_run_on_static_video_produces_no_clips(tmp_path):
    # The synthetic static video never changes combo, so no kill groups
    # exist and the manifest should end up empty — this still proves the
    # whole pipeline runs end to end without erroring.
    db_path = tmp_path / "manifest.sqlite"
    pipeline.run(VIDEO_PATH, output_dir=tmp_path, db_path=db_path)

    rows = dataset_manifest.fetch_random_sample(db_path, n=10)
    assert rows == []
