from pathlib import Path

from biomercs_ml import config, hud_reader

VIDEO_PATH = "tests/fixtures/synthetic_static.mp4"


def test_sample_video_reads_consistent_samples_from_static_video():
    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)

    samples = hud_reader.sample_video(
        Path(VIDEO_PATH), timer_templates, combo_templates, combo_label_template
    )

    # 1s video sampled every 0.2s -> ~5 samples; the frame never changes,
    # so every sample should read the same known values and stay in one
    # session (no timer discontinuity to split on).
    assert 4 <= len(samples) <= 6
    for sample in samples:
        assert sample.timer_value_s == 148.0
        assert sample.combo_value == 3
        assert sample.session_id == 0
