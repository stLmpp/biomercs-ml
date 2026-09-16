from biomercs_ml import config, hud_reader

KILL_BONUS_FRAME = "tests/fixtures/frames/popup_kill_bonus_frame.png"
PICKUP_FRAME = "tests/fixtures/frames/popup_pickup_frame.png"
NO_POPUP_FRAME = "tests/fixtures/frames/sample_frame_01.png"


def test_is_popup_visible_true_when_a_bonus_popup_is_showing():
    frame = hud_reader.load_image(KILL_BONUS_FRAME)
    popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)

    visible, confidence = hud_reader.is_popup_visible(frame, popup_label_template)

    assert visible is True
    assert confidence >= config.POPUP_LABEL_MIN_CONFIDENCE


def test_is_popup_visible_false_when_no_popup_is_showing():
    frame = hud_reader.load_image(NO_POPUP_FRAME)
    popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)

    visible, confidence = hud_reader.is_popup_visible(frame, popup_label_template)

    assert visible is False


def test_read_popup_ones_digit_reads_5_for_the_fixed_kill_bonus_popup():
    templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
    frame = hud_reader.load_image(KILL_BONUS_FRAME)

    value, confidence = hud_reader.read_popup_ones_digit(frame, templates)

    assert value == 5
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE


def test_read_popup_ones_digit_reads_0_for_a_map_pickup_popup():
    # Map pickups are always +30/+60/+90 -- the ones digit is always
    # "0", unlike the kill-bonus popup which is always fixed at "+05".
    templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
    frame = hud_reader.load_image(PICKUP_FRAME)

    value, confidence = hud_reader.read_popup_ones_digit(frame, templates)

    assert value == 0
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE
