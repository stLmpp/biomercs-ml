import cv2
import numpy as np

from biomercs_ml import config, hud_reader

FRAME_PATH = "tests/fixtures/frames/sample_frame_01.png"


def _load_frame():
    return hud_reader.load_image(FRAME_PATH)


def test_load_digit_templates_loads_available_timer_digits():
    templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    for digit in "0123456789":
        assert digit in templates


def test_match_digit_identifies_correct_digit():
    templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    frame = _load_frame()
    x, y, w, h = config.TIMER_MINUTES_SLOTS[0]  # known to show "0"
    crop = frame[y : y + h, x : x + w]
    digit, score = hud_reader.match_digit(crop, templates)
    assert digit == "0"
    assert score > config.DIGIT_MATCH_MIN_CONFIDENCE


def test_read_digit_slots_reads_timer_minutes_as_02():
    templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    frame = _load_frame()
    value, confidence = hud_reader.read_digit_slots(
        frame, config.TIMER_MINUTES_SLOTS, templates
    )
    assert value == 2
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE


def test_read_digit_slots_reads_timer_seconds_as_28():
    templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    frame = _load_frame()
    value, confidence = hud_reader.read_digit_slots(
        frame, config.TIMER_SECONDS_SLOTS, templates
    )
    assert value == 28
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE


def test_read_digit_slots_reads_combo_as_003():
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    frame = _load_frame()
    value, confidence = hud_reader.read_digit_slots(
        frame, config.COMBO_DIGIT_SLOTS, templates
    )
    assert value == 3
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE


def test_read_digit_slots_tolerates_small_pixel_misalignment():
    # Real compressed video can shift a digit's rendering a few pixels
    # from where it was calibrated, purely from compression/encoding
    # noise (not a real HUD position change) -- found by validating
    # against a downloaded YouTube video, where this caused wrong digit
    # reads at otherwise-good confidence. A read within a small margin
    # of the nominal slot should still resolve correctly.
    #
    # Combo's slots are only 32px apart at 34px wide (already touching
    # at baseline), so horizontal tolerance here is necessarily smaller
    # than the full DIGIT_SEARCH_MARGIN_PX -- read_digit_slots clamps
    # the margin to never cross into a neighboring slot's ink (see
    # test_read_digit_slots_does_not_bleed_into_a_neighboring_slots_ink),
    # which caps how much horizontal jitter these specific slots can
    # absorb.
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    frame = _load_frame()
    jittered = np.roll(frame, shift=(3, 2), axis=(0, 1))

    value, confidence = hud_reader.read_digit_slots(
        jittered, config.COMBO_DIGIT_SLOTS, templates
    )

    assert value == 3
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE


def test_read_digit_slots_does_not_bleed_into_a_neighboring_slots_ink():
    # Real footage (a second, different video): a menu-open frame
    # reading a rock-solid "149" combo was consistently misread as
    # "140". Root cause: the "COMBO" label sits only 1px after the last
    # digit slot, and the jitter-tolerance margin's right-side
    # extension reached into it, matching against something there
    # better than against the true "9" in its own tight box. This is
    # deterministic, not transient noise, so majority-voting or
    # persistence checks can't catch it -- the margin itself must not
    # cross into a neighboring slot OR a nearby label/element.
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    frame = hud_reader.load_image(
        "tests/fixtures/frames/combo_149_adjacent_digit_bleed_frame.png"
    )

    value, confidence = hud_reader.read_combo(frame, templates)

    assert value == 149
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE
