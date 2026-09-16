from pathlib import Path
from unittest.mock import patch

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


def test_sample_video_applies_calibrated_offset_only_to_validity_check():
    # The label ROI used to find a per-video offset can find a better
    # score at a shifted position (e.g. font self-similarity in "COMBO")
    # even when the digit slots are already correctly calibrated --
    # applying that same offset to digit reads breaks otherwise-correct
    # matches. Only the validity check should receive it.
    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)

    fake_offset = (7, 3)
    with (
        patch("biomercs_ml.hud_reader._calibrate_offset", return_value=fake_offset),
        patch("biomercs_ml.hud_reader.is_valid_hud_frame", return_value=(True, 1.0)) as mock_valid,
        patch("biomercs_ml.hud_reader.read_timer", return_value=(148.0, 1.0)) as mock_timer,
        patch("biomercs_ml.hud_reader.read_combo", return_value=(3, 1.0)) as mock_combo,
    ):
        hud_reader.sample_video(
            Path(VIDEO_PATH), timer_templates, combo_templates, combo_label_template
        )

    def _received_fake_offset(call) -> bool:
        if call.kwargs.get("offset") == fake_offset:
            return True
        return len(call.args) >= 3 and call.args[2] == fake_offset

    assert mock_valid.call_args_list
    assert all(_received_fake_offset(call) for call in mock_valid.call_args_list)

    assert mock_timer.call_args_list
    assert not any(_received_fake_offset(call) for call in mock_timer.call_args_list)

    assert mock_combo.call_args_list
    assert not any(_received_fake_offset(call) for call in mock_combo.call_args_list)


def test_sample_video_majority_votes_combo_within_each_tick():
    # A transient single-frame digit misread (e.g. compression noise
    # flipping "8"->"0" for one frame) landing exactly on the 0.2s
    # sampling grid creates a phantom combo jump and a fake kill-group
    # downstream -- found via real downloaded footage. Voting across a
    # short burst of frames per tick absorbs a lone outlier instead of
    # trusting a single frame.
    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)

    true_reading = (3, 0.9)
    outlier_reading = (10, 0.85)
    burst_readings = [true_reading] * (config.SAMPLE_VOTE_FRAMES - 1) + [outlier_reading]
    with (
        patch("biomercs_ml.hud_reader.is_valid_hud_frame", return_value=(True, 1.0)),
        patch("biomercs_ml.hud_reader.read_timer", return_value=(148.0, 0.9)),
        patch("biomercs_ml.hud_reader.read_combo", side_effect=burst_readings * 10),
    ):
        samples = hud_reader.sample_video(
            Path(VIDEO_PATH), timer_templates, combo_templates, combo_label_template
        )

    assert samples
    for sample in samples:
        assert sample.combo_value == 3
