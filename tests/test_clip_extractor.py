from pathlib import Path

from biomercs_ml import clip_extractor

VIDEO_PATH = Path("tests/fixtures/synthetic_static.mp4")


def test_extract_clip_creates_a_playable_file(tmp_path):
    output_path = tmp_path / "clip.mp4"
    result = clip_extractor.extract_clip(
        VIDEO_PATH, timestamp_s=0.5, output_path=output_path, before_s=0.2, after_s=0.2
    )
    assert result == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_extract_clip_clamps_start_to_zero_near_beginning(tmp_path):
    output_path = tmp_path / "clip_start.mp4"
    # timestamp - before_s would be negative; must not error, must clamp to 0
    result = clip_extractor.extract_clip(
        VIDEO_PATH, timestamp_s=0.1, output_path=output_path, before_s=2.0, after_s=0.2
    )
    assert result.exists()
