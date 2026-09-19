from biomercs_ml import config, hud_reader

FRAME_PATH = "tests/fixtures/frames/sample_frame_01.png"


def test_read_timer_returns_148_seconds():
    frame = hud_reader.load_image(FRAME_PATH)
    templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    value, confidence = hud_reader.read_timer(frame, templates)
    assert value == 2 * 60 + 28
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE


def test_read_combo_returns_3():
    frame = hud_reader.load_image(FRAME_PATH)
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    value, confidence = hud_reader.read_combo(frame, templates)
    assert value == 3
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE


def test_read_combo_rejects_a_value_above_the_real_game_maximum():
    # RE5 Mercenaries' enemy pool is fixed, so the combo counter can
    # never exceed it -- per the author's own top-level competitive
    # experience, 150 is the hard maximum. This isn't just a
    # theoretical bound: this exact real frame (video 2, t=124.0s)
    # plainly reads "029 COMBO" with no occlusion or motion blur, but
    # raw template matching confidently misreads it as "889" -- most
    # combo digit templates still have only one real-footage sample
    # each (only 0/3/5/7 were multi-sample curated so far), so a
    # single bad "8" sample wins broadly. See DECISIONS.md.
    frame = hud_reader.load_image("tests/fixtures/frames/combo_029_misread_as_889_frame.png")
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    value, _ = hud_reader.read_combo(frame, templates)
    assert value is None


def test_is_valid_hud_frame_true_on_gameplay_frame():
    frame = hud_reader.load_image(FRAME_PATH)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
    is_valid, score = hud_reader.is_valid_hud_frame(frame, combo_label_template)
    assert is_valid is True
    assert score > config.COMBO_LABEL_MIN_CONFIDENCE


def test_is_valid_hud_frame_false_on_blank_frame():
    import numpy as np

    blank = np.zeros((720, 1280, 3), dtype=np.uint8)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
    is_valid, _ = hud_reader.is_valid_hud_frame(blank, combo_label_template)
    assert is_valid is False


def test_is_new_session_false_for_normal_countdown():
    assert hud_reader.is_new_session(prev_timer_s=100.0, curr_timer_s=99.8) is False


def test_is_new_session_false_for_plausible_bonus_jump():
    # 3 simultaneous bonus kills (+15s) minus 0.2s decay
    assert hud_reader.is_new_session(prev_timer_s=100.0, curr_timer_s=114.8) is False


def test_is_new_session_false_for_a_large_stacked_bonus_jump():
    # A map time-bonus pickup (+90) landing in the same tick as a kill
    # bonus (+5) -- rare but real per the author's own top-level
    # competitive experience, and well below a real new-round reset
    # (always a fresh 2:00 / 120s, see
    # test_is_new_session_true_for_a_real_new_round_reset).
    assert hud_reader.is_new_session(prev_timer_s=100.0, curr_timer_s=205.0) is False


def test_is_new_session_true_for_backward_jump():
    assert hud_reader.is_new_session(prev_timer_s=100.0, curr_timer_s=30.0) is True


def test_is_new_session_false_for_real_footage_drop_noise():
    # video4, t=606.6s -> t=607.0s: a real, noisy (but not misread-level
    # implausible) digit-read dip during dense combat, not a real new
    # round -- see DECISIONS.md, "timer-noise-session-fragmentation".
    assert hud_reader.is_new_session(prev_timer_s=586.0, curr_timer_s=574.0) is False


def test_is_new_session_true_for_a_real_new_round_reset():
    # A new round always starts at exactly 2:00 (120s) -- per the
    # author's own top-level competitive experience. A prior round
    # ending with substantial banked bonus time (real footage regularly
    # exceeds 580s here) resetting to 120s is a drop far larger than any
    # real per-tick read noise or plausible bonus stack.
    assert hud_reader.is_new_session(prev_timer_s=580.0, curr_timer_s=120.0) is True


def test_is_new_session_true_for_implausibly_large_jump():
    assert hud_reader.is_new_session(prev_timer_s=10.0, curr_timer_s=300.0) is True
