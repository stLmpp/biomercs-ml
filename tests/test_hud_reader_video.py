from pathlib import Path
from unittest.mock import patch

from biomercs_ml import config, hud_reader

VIDEO_PATH = "tests/fixtures/synthetic_static.mp4"


def test_sample_video_reads_consistent_samples_from_static_video():
    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
    popup_digit_templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
    popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)

    samples = hud_reader.sample_video(
        Path(VIDEO_PATH),
        timer_templates,
        combo_templates,
        combo_label_template,
        popup_digit_templates,
        popup_label_template,
    )

    # 1s video sampled every 0.2s -> ~5 samples; the frame never changes,
    # so every sample should read the same known values and stay in one
    # session (no timer discontinuity to split on).
    assert 4 <= len(samples) <= 6
    for sample in samples:
        assert sample.timer_value_s == 148.0
        assert sample.combo_value == 3
        assert sample.session_id == 0
        assert sample.pickup_popup is False


def test_sample_video_applies_calibrated_offset_only_to_validity_check():
    # The label ROI used to find a per-video offset can find a better
    # score at a shifted position (e.g. font self-similarity in "COMBO")
    # even when the digit slots are already correctly calibrated --
    # applying that same offset to digit reads breaks otherwise-correct
    # matches. Only the validity check should receive it.
    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
    popup_digit_templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
    popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)

    fake_offset = (7, 3)
    with (
        patch("biomercs_ml.hud_reader._calibrate_offset", return_value=fake_offset),
        patch("biomercs_ml.hud_reader.is_valid_hud_frame", return_value=(True, 1.0)) as mock_valid,
        patch("biomercs_ml.hud_reader.read_timer", return_value=(148.0, 1.0)) as mock_timer,
        patch("biomercs_ml.hud_reader.read_combo", return_value=(3, 1.0)) as mock_combo,
        patch("biomercs_ml.hud_reader.is_popup_visible", return_value=(False, 1.0)) as mock_popup_visible,
    ):
        hud_reader.sample_video(
            Path(VIDEO_PATH),
            timer_templates,
            combo_templates,
            combo_label_template,
            popup_digit_templates,
            popup_label_template,
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

    assert mock_popup_visible.call_args_list
    assert all(_received_fake_offset(call) for call in mock_popup_visible.call_args_list)


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
    popup_digit_templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
    popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)

    true_reading = (3, 0.9)
    outlier_reading = (10, 0.85)
    burst_readings = [true_reading] * (config.SAMPLE_VOTE_FRAMES - 1) + [outlier_reading]
    with (
        patch("biomercs_ml.hud_reader.is_valid_hud_frame", return_value=(True, 1.0)),
        patch("biomercs_ml.hud_reader.read_timer", return_value=(148.0, 0.9)),
        patch("biomercs_ml.hud_reader.read_combo", side_effect=burst_readings * 10),
        patch("biomercs_ml.hud_reader.is_popup_visible", return_value=(False, 1.0)),
    ):
        samples = hud_reader.sample_video(
            Path(VIDEO_PATH),
            timer_templates,
            combo_templates,
            combo_label_template,
            popup_digit_templates,
            popup_label_template,
        )

    assert samples
    for sample in samples:
        assert sample.combo_value == 3


def test_sample_video_widens_the_vote_when_a_short_burst_picks_the_wrong_majority():
    # Real footage (video 2, ~t=522.0s): heavy motion-blur/particle
    # noise makes the combo's ones digit flicker among several
    # different wrong values almost every frame for under a second.
    # The original 3-frame vote reliably lands on a wrong plurality
    # (frames read 189, 189, 199 -> majority "189"), even though the
    # true value (185) is the single most common reading across the
    # full ~11-frame window the noise actually spans -- the vote
    # window just wasn't wide enough to see that. See DECISIONS.md,
    # "Bug D". Sequence below is the real per-frame combo readings
    # starting at the sampling tick, in order.
    true_reading = (185, 0.78)
    burst_readings = [
        (189, 0.785),
        (189, 0.781),
        (199, 0.797),
        (196, 0.814),
        (195, 0.802),
        true_reading,
        (195, 0.753),
        true_reading,
        (189, 0.781),
        true_reading,
        true_reading,
    ]
    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
    popup_digit_templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
    popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)

    with (
        patch("biomercs_ml.hud_reader.is_valid_hud_frame", return_value=(True, 1.0)),
        patch("biomercs_ml.hud_reader.read_timer", return_value=(148.0, 0.9)),
        patch("biomercs_ml.hud_reader.read_combo", side_effect=burst_readings * 10),
        patch("biomercs_ml.hud_reader.is_popup_visible", return_value=(False, 1.0)),
    ):
        samples = hud_reader.sample_video(
            Path(VIDEO_PATH),
            timer_templates,
            combo_templates,
            combo_label_template,
            popup_digit_templates,
            popup_label_template,
        )

    assert samples
    for sample in samples:
        assert sample.combo_value == 185


def test_sample_video_flags_pickup_popup_when_ones_digit_is_zero():
    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
    popup_digit_templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
    popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)

    with (
        patch("biomercs_ml.hud_reader.is_valid_hud_frame", return_value=(True, 1.0)),
        patch("biomercs_ml.hud_reader.read_timer", return_value=(148.0, 0.9)),
        patch("biomercs_ml.hud_reader.read_combo", return_value=(3, 0.9)),
        patch("biomercs_ml.hud_reader.is_popup_visible", return_value=(True, 1.0)),
        patch("biomercs_ml.hud_reader.read_popup_ones_digit", return_value=(0, 0.9)),
    ):
        samples = hud_reader.sample_video(
            Path(VIDEO_PATH),
            timer_templates,
            combo_templates,
            combo_label_template,
            popup_digit_templates,
            popup_label_template,
        )

    assert samples
    for sample in samples:
        assert sample.pickup_popup is True


def test_sample_video_does_not_flag_the_fixed_kill_bonus_popup():
    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
    popup_digit_templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
    popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)

    with (
        patch("biomercs_ml.hud_reader.is_valid_hud_frame", return_value=(True, 1.0)),
        patch("biomercs_ml.hud_reader.read_timer", return_value=(148.0, 0.9)),
        patch("biomercs_ml.hud_reader.read_combo", return_value=(3, 0.9)),
        patch("biomercs_ml.hud_reader.is_popup_visible", return_value=(True, 1.0)),
        patch("biomercs_ml.hud_reader.read_popup_ones_digit", return_value=(5, 0.9)),
    ):
        samples = hud_reader.sample_video(
            Path(VIDEO_PATH),
            timer_templates,
            combo_templates,
            combo_label_template,
            popup_digit_templates,
            popup_label_template,
        )

    assert samples
    for sample in samples:
        assert sample.pickup_popup is False
