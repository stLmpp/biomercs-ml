from biomercs_ml import config, hud_reader

THREE_MISREAD_AS_8_PATH = "tests/fixtures/digits/combo_3_real_misread_as_8.png"
REAL_8_PATH = "tests/fixtures/digits/combo_8_real.png"
REAL_9_FRAME_PATH = "tests/fixtures/frames/combo_ones_digit_real_9_frame.png"


def test_waist_notch_score_scores_a_real_3_above_the_threshold():
    crop = hud_reader.load_image(THREE_MISREAD_AS_8_PATH)
    assert hud_reader.waist_notch_score(crop) > config.WAIST_NOTCH_THREE_THRESHOLD


def test_waist_notch_score_scores_a_real_8_below_the_threshold():
    crop = hud_reader.load_image(REAL_8_PATH)
    assert hud_reader.waist_notch_score(crop) < config.WAIST_NOTCH_THREE_THRESHOLD


def test_match_digit_without_tiebreak_misreads_the_real_3_as_8():
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    crop = hud_reader.load_image(THREE_MISREAD_AS_8_PATH)

    digit, _ = hud_reader.match_digit(crop, templates)

    assert digit == "8"


def test_match_digit_waist_notch_tiebreak_fixes_the_real_3_misread_as_8():
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    crop = hud_reader.load_image(THREE_MISREAD_AS_8_PATH)

    digit, _ = hud_reader.match_digit(crop, templates, apply_waist_notch_tiebreak=True)

    assert digit == "3"


def test_match_digit_waist_notch_tiebreak_does_not_flip_a_real_8():
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    crop = hud_reader.load_image(REAL_8_PATH)

    digit, _ = hud_reader.match_digit(crop, templates, apply_waist_notch_tiebreak=True)

    assert digit == "8"


def test_read_digit_slots_without_tiebreak_still_misreads_the_real_3_as_8():
    # A single slot sized exactly to the crop leaves read_digit_slots'
    # own margin logic zero room to extend (see its px0/px1 clamping),
    # so this exercises the exact same tight-crop conditions as
    # test_match_digit_without_tiebreak_misreads_the_real_3_as_8, but
    # through read_digit_slots itself -- proving the parameter actually
    # has to reach match_digit, not just that match_digit works alone.
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    crop = hud_reader.load_image(THREE_MISREAD_AS_8_PATH)
    h, w = crop.shape[:2]

    value, _ = hud_reader.read_digit_slots(crop, [(0, 0, w, h)], templates)

    assert value == 8


def test_read_digit_slots_waist_notch_tiebreak_fixes_the_real_3_misread_as_8():
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    crop = hud_reader.load_image(THREE_MISREAD_AS_8_PATH)
    h, w = crop.shape[:2]

    value, _ = hud_reader.read_digit_slots(
        crop, [(0, 0, w, h)], templates, apply_waist_notch_tiebreak=True
    )

    assert value == 3


def test_read_combo_applies_the_tiebreak_and_leaves_a_real_9_unaffected():
    # Real footage (video 1, t=158.0s): combo genuinely reads "039". The
    # waist-notch tiebreak must not flip a correctly-read "9" to "3" --
    # see docs/superpowers/DECISIONS.md, "the waist-notch feature
    # tested against the timer font..." for why this guard matters (the
    # raw score gap between a genuine 9 and 3's own score can be small).
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    frame = hud_reader.load_image(REAL_9_FRAME_PATH)

    value, confidence = hud_reader.read_combo(frame, templates)

    assert value == 39
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE
