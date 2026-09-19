from pathlib import Path
from unittest.mock import patch

import cv2

from biomercs_ml import config, hud_reader
from biomercs_ml.models import RawHudSample

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
        max_workers=1,
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


def test_sample_video_logs_progress(capsys):
    # Real runs take several minutes with no visibility at all
    # otherwise (the user had to ask "is this still running?" -- see
    # DECISIONS.md). Print periodic progress instead of staying silent
    # until the very end.
    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
    popup_digit_templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
    popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)

    hud_reader.sample_video(
        Path(VIDEO_PATH),
        timer_templates,
        combo_templates,
        combo_label_template,
        popup_digit_templates,
        popup_label_template,
        max_workers=1,
    )

    captured = capsys.readouterr()
    assert "%" in captured.out


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
            max_workers=1,
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


def test_sample_video_starts_calibration_from_the_middle_of_the_video():
    # Real footage (video 4, t=585.8-606.4): a long pre-gameplay stretch
    # -- loading/menus, or, per the game's own run structure, a
    # "preparation lap" collecting time bonuses before the first kill --
    # can run past calibration's whole scan budget (config.
    # CALIBRATION_MAX_FRAMES candidates, spaced by frame_interval) if it
    # starts from frame 0, locking in the wrong (0, 0) fallback offset
    # for the entire rest of the video: is_valid_hud_frame then scores
    # just under threshold almost everywhere, starving sample_video of
    # ticks and letting detect_kill_groups lump many real, separate
    # kills spread across the resulting gaps into one fabricated group.
    # Starting from the middle sidesteps this -- by a run's midpoint,
    # real gameplay HUD is almost certainly on screen, regardless of how
    # long the pre-gameplay stretch was.
    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
    popup_digit_templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
    popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)

    seek_positions = []

    def _fake_calibrate(cap, *args, **kwargs):
        seek_positions.append(cap.get(cv2.CAP_PROP_POS_FRAMES))
        return (0, 0)

    with patch("biomercs_ml.hud_reader._calibrate_offset", side_effect=_fake_calibrate):
        hud_reader.sample_video(
            Path(VIDEO_PATH),
            timer_templates,
            combo_templates,
            combo_label_template,
            popup_digit_templates,
            popup_label_template,
            max_workers=1,
        )

    reference_cap = cv2.VideoCapture(VIDEO_PATH)
    total_frames = int(reference_cap.get(cv2.CAP_PROP_FRAME_COUNT))
    reference_cap.release()

    assert seek_positions == [total_frames // 2]


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
            max_workers=1,
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
            max_workers=1,
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
            max_workers=1,
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
            max_workers=1,
        )

    assert samples
    for sample in samples:
        assert sample.pickup_popup is False


def test_sample_range_chunking_produces_same_raw_samples_as_one_full_range():
    # #6 (parallelization) splits sample_video's work into chunks aligned
    # to tick multiples so no chunk ever needs a frame from a neighboring
    # chunk's range for its own burst reads. Prove that directly: reading
    # the same video as one chunk vs. as two adjacent chunks must produce
    # identical concatenated raw samples.
    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
    popup_digit_templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
    popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)

    cap = cv2.VideoCapture(VIDEO_PATH)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    frame_interval = max(1, round(fps * config.SAMPLE_INTERVAL_S))
    duration_s = total_frames / fps
    total_ticks = (total_frames + frame_interval - 1) // frame_interval

    def sample_range(start_tick: int, end_tick: int):
        return hud_reader._sample_range(
            Path(VIDEO_PATH),
            timer_templates,
            combo_templates,
            combo_label_template,
            popup_digit_templates,
            popup_label_template,
            (0, 0),
            fps,
            frame_interval,
            duration_s,
            start_tick * frame_interval,
            end_tick * frame_interval,
        )

    full = sample_range(0, total_ticks)

    mid = total_ticks // 2
    assert 0 < mid < total_ticks
    part1 = sample_range(0, mid)
    part2 = sample_range(mid, total_ticks)

    assert part1 + part2 == full


def test_sample_video_parallel_matches_sequential_output():
    # The real point of #6: running with multiple workers must produce
    # byte-for-byte identical HudSamples to the single-worker (in-process)
    # path -- chunk order is preserved on concatenation, and the
    # session_id assignment pass runs once, sequentially, over the merged
    # result.
    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
    popup_digit_templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
    popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)

    sequential = hud_reader.sample_video(
        Path(VIDEO_PATH),
        timer_templates,
        combo_templates,
        combo_label_template,
        popup_digit_templates,
        popup_label_template,
        max_workers=1,
    )
    parallel = hud_reader.sample_video(
        Path(VIDEO_PATH),
        timer_templates,
        combo_templates,
        combo_label_template,
        popup_digit_templates,
        popup_label_template,
        max_workers=2,
    )

    assert sequential
    assert parallel == sequential


def test_is_spurious_timer_spike_true_for_a_lone_reverting_outlier():
    # video4, t=641.6s -> 641.8s -> 642.0s: background scene geometry (a
    # wooden support beam) sweeping across the timer's translucent "0"
    # digit for a few frames within one tick's burst misreads it as "8",
    # then reverts on the very next tick -- see DECISIONS.md,
    # "timer-noise-session-fragmentation".
    assert hud_reader._is_spurious_timer_spike(
        prev_timer_s=568.0, curr_timer_s=5364.0, next_timer_s=564.0
    ) is True


def test_is_spurious_timer_spike_false_for_normal_countdown():
    assert hud_reader._is_spurious_timer_spike(
        prev_timer_s=100.0, curr_timer_s=99.8, next_timer_s=99.6
    ) is False


def test_is_spurious_timer_spike_true_for_a_moderate_outlier_within_the_loosened_jump_tolerance():
    # video4, t=499.1s -> 499.3s -> 499.5s: a misread (627) landing only
    # ~50s above the true value doesn't cross SESSION_RESET_JUMP_S on its
    # own (loosened to tolerate real rare +105s stacked bonuses -- see
    # config.py), but reverting from it on the very next tick looks like
    # an oversized drop against the much tighter SESSION_RESET_DROP_S.
    # prev and next agree with each other here, so curr is still the
    # outlier regardless of which single pairwise comparison happens to
    # cross a threshold -- see DECISIONS.md,
    # "timer-noise-session-fragmentation".
    assert hud_reader._is_spurious_timer_spike(
        prev_timer_s=577.0, curr_timer_s=627.0, next_timer_s=577.0
    ) is True


def test_is_spurious_timer_spike_false_for_a_real_sustained_new_round_reset():
    # A real new-round reset persists (the fresh 2:00 keeps counting down
    # from there) rather than reverting on the next tick -- must not be
    # suppressed just because it also crosses is_new_session's
    # jump/drop thresholds.
    assert hud_reader._is_spurious_timer_spike(
        prev_timer_s=580.0, curr_timer_s=120.0, next_timer_s=119.8
    ) is False


def test_assign_session_ids_suppresses_a_lone_reverting_timer_spike():
    raw_samples = [
        RawHudSample(timestamp_s=641.4, timer_value_s=568.0, combo_value=149, confidence=0.7),
        RawHudSample(timestamp_s=641.6, timer_value_s=568.0, combo_value=149, confidence=0.7),
        RawHudSample(timestamp_s=641.8, timer_value_s=5364.0, combo_value=149, confidence=0.68),
        RawHudSample(timestamp_s=642.0, timer_value_s=564.0, combo_value=149, confidence=0.71),
        RawHudSample(timestamp_s=642.2, timer_value_s=564.0, combo_value=149, confidence=0.74),
    ]
    samples = hud_reader._assign_session_ids(raw_samples)
    # The spike tick's timer reading is untrustworthy and dropped
    # entirely (the final sample_video filter already drops any sample
    # with a None timer_value_s).
    assert [s.timestamp_s for s in samples] == [641.4, 641.6, 642.0, 642.2]
    assert {s.session_id for s in samples} == {0}


def test_assign_session_ids_still_splits_on_a_real_session_change():
    raw_samples = [
        RawHudSample(timestamp_s=10.0, timer_value_s=580.0, combo_value=140, confidence=0.8),
        RawHudSample(timestamp_s=10.2, timer_value_s=120.0, combo_value=0, confidence=0.8),
        RawHudSample(timestamp_s=10.4, timer_value_s=119.8, combo_value=0, confidence=0.8),
    ]
    samples = hud_reader._assign_session_ids(raw_samples)
    assert [s.session_id for s in samples] == [0, 1, 1]
