from biomercs_ml import config, hud_reader

TWO_MISREAD_AS_8_PATH = "tests/fixtures/digits/combo_2_real_misread_as_8.png"
REAL_8_PATH = "tests/fixtures/digits/combo_8_real.png"
THREE_MISREAD_AS_8_PATH = "tests/fixtures/digits/combo_3_real_misread_as_8.png"
REAL_2_MISREAD_AS_118_FRAME_PATH = "tests/fixtures/frames/combo_112_misread_as_118_frame.png"


def test_base_widen_score_scores_a_real_2_above_the_threshold():
    crop = hud_reader.load_image(TWO_MISREAD_AS_8_PATH)
    assert hud_reader.base_widen_score(crop) > config.BASE_WIDEN_TWO_THRESHOLD


def test_base_widen_score_scores_a_real_8_below_the_threshold():
    crop = hud_reader.load_image(REAL_8_PATH)
    assert hud_reader.base_widen_score(crop) < config.BASE_WIDEN_TWO_THRESHOLD


def test_base_widen_score_scores_a_real_3_below_the_threshold():
    # The waist-notch and base-widen tiebreaks target different digits
    # via different geometric axes -- a real "3" must not accidentally
    # clear the "2" threshold too.
    crop = hud_reader.load_image(THREE_MISREAD_AS_8_PATH)
    assert hud_reader.base_widen_score(crop) < config.BASE_WIDEN_TWO_THRESHOLD


def test_match_digit_without_tiebreak_now_correctly_reads_the_real_2():
    # This fixture used to reproduce the raw 2-vs-8 misread on its own
    # (hence its filename) -- it stopped doing so once two unrelated bugs
    # in this session were fixed: the fixture itself was cropped 6px off
    # from every template's own alignment (a bug in the one-time recovery
    # process that made it, not in read_digit_slots), and `8/a` (the
    # template that used to win here) had a real crop-bleed defect (see
    # `combo-template-defects`) that got removed. The tiebreak below is
    # still exercised and still holds -- this just confirms raw matching
    # alone no longer needs it for this specific fixture.
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    crop = hud_reader.load_image(TWO_MISREAD_AS_8_PATH)

    digit, _ = hud_reader.match_digit(crop, templates)

    assert digit == "2"


def test_match_digit_waist_notch_tiebreak_fixes_the_real_2_misread_as_8():
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    crop = hud_reader.load_image(TWO_MISREAD_AS_8_PATH)

    digit, _ = hud_reader.match_digit(crop, templates, apply_waist_notch_tiebreak=True)

    assert digit == "2"


def test_match_digit_waist_notch_tiebreak_still_does_not_flip_a_real_8():
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    crop = hud_reader.load_image(REAL_8_PATH)

    digit, _ = hud_reader.match_digit(crop, templates, apply_waist_notch_tiebreak=True)

    assert digit == "8"


def test_read_combo_fixes_the_real_112_misread_as_118():
    # Real footage (video 5, id=6, t=576.0s): combo genuinely reads
    # "112" but the raw matcher misreads it as "118" -- see
    # `combo-2-vs-8-misread` in docs/superpowers/KNOWN_BUGS.md.
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    frame = hud_reader.load_image(REAL_2_MISREAD_AS_118_FRAME_PATH)

    value, confidence = hud_reader.read_combo(frame, templates)

    assert value == 112
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE
