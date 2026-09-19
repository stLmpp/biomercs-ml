from pathlib import Path

from biomercs_ml import dataset_manifest, pipeline
from biomercs_ml.models import HudSample

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


def _hud_sample(t, timer, combo, session_id=0):
    return HudSample(t, session_id, timer, combo, confidence=0.9)


def test_label_kill_groups_pairs_each_group_with_its_label():
    samples = [_hud_sample(0.0, 100.0, 5), _hud_sample(0.2, 99.8, 5), _hud_sample(0.4, 104.6, 6)]

    labeled = pipeline.label_kill_groups(samples)

    assert [(group.timestamp_s, label.kind) for group, label in labeled] == [(0.4, "bonus_kill")]


def test_label_kill_groups_drops_groups_the_labeler_rejects():
    # combo +1 but the timer gained 2.3s -- not a clean multiple of 5, so
    # the labeler returns None and the group must not be emitted.
    samples = [_hud_sample(0.0, 100.0, 5), _hud_sample(0.2, 99.8, 5), _hud_sample(0.4, 102.1, 6)]

    assert pipeline.label_kill_groups(samples) == []


def test_label_kill_groups_never_mixes_combo_across_sessions():
    samples = [_hud_sample(0.0, 100.0, 5), _hud_sample(0.2, 99.8, 9, session_id=1)]

    assert pipeline.label_kill_groups(samples) == []
