import numpy as np

from biomercs_ml import config, hud_reader

FRAME_PATH = "tests/fixtures/frames/sample_frame_01.png"


def test_find_best_offset_returns_zero_for_already_aligned_frame():
    frame = hud_reader.load_image(FRAME_PATH)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)

    offset, score = hud_reader.find_best_offset(frame, combo_label_template, search_radius_px=20)

    assert offset == (0, 0)
    assert score > 0.99


def test_find_best_offset_recovers_known_shift():
    frame = hud_reader.load_image(FRAME_PATH)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)

    shift_x, shift_y = 6, -3
    shifted_frame = np.roll(frame, shift=(shift_y, shift_x), axis=(0, 1))

    offset, score = hud_reader.find_best_offset(
        shifted_frame, combo_label_template, search_radius_px=20
    )

    assert offset == (shift_x, shift_y)
    assert score > config.COMBO_LABEL_MIN_CONFIDENCE


def test_find_best_offset_falls_back_when_nothing_matches():
    blank = np.zeros((720, 1280, 3), dtype=np.uint8)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)

    offset, score = hud_reader.find_best_offset(blank, combo_label_template, search_radius_px=20)

    assert score < config.COMBO_LABEL_MIN_CONFIDENCE
