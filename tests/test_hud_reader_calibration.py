import numpy as np

from biomercs_ml import config, hud_reader

FRAME_PATH = "tests/fixtures/frames/sample_frame_01.png"


class _FakeCapture:
    def __init__(self, frames):
        self._frames = frames
        self._i = 0

    def read(self):
        if self._i >= len(self._frames):
            return False, None
        frame = self._frames[self._i]
        self._i += 1
        return True, frame


def _shifted(frame, dx, dy):
    return np.roll(frame, shift=(dy, dx), axis=(0, 1))


def test_calibrate_offset_falls_back_when_no_frame_ever_matches():
    blank = np.zeros((720, 1280, 3), dtype=np.uint8)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)

    cap = _FakeCapture([blank] * 10)

    offset = hud_reader._calibrate_offset(cap, combo_label_template, frame_interval=1)

    assert offset == (0, 0)


def test_calibrate_offset_ignores_a_single_confident_outlier():
    # A lone confident-looking frame isn't enough to trust on its own --
    # e.g. a combo-counter "pop" animation on update can transiently
    # render the label at a different position than its static resting
    # offset. One occurrence must not be enough to lock in an offset.
    blank = np.zeros((720, 1280, 3), dtype=np.uint8)
    real_frame = hud_reader.load_image(FRAME_PATH)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)

    outlier_frame = _shifted(real_frame, 6, -3)
    frames = [blank] * 5 + [outlier_frame] + [blank] * 5
    cap = _FakeCapture(frames)

    offset = hud_reader._calibrate_offset(cap, combo_label_template, frame_interval=1)

    assert offset == (0, 0)


def test_calibrate_offset_accepts_an_offset_seen_repeatedly():
    blank = np.zeros((720, 1280, 3), dtype=np.uint8)
    real_frame = hud_reader.load_image(FRAME_PATH)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)

    shift_x, shift_y = 6, -3
    shifted_frame = _shifted(real_frame, shift_x, shift_y)

    frames = [blank] * 5 + [shifted_frame] * config.CALIBRATION_MIN_VOTES + [blank] * 5
    cap = _FakeCapture(frames)

    offset = hud_reader._calibrate_offset(cap, combo_label_template, frame_interval=1)

    assert offset == (shift_x, shift_y)


def test_calibrate_offset_majority_wins_over_a_transient_outlier_seen_first():
    real_frame = hud_reader.load_image(FRAME_PATH)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)

    true_offset = (7, 0)
    outlier_offset = (0, 0)
    true_frame = _shifted(real_frame, *true_offset)
    outlier_frame = _shifted(real_frame, *outlier_offset)

    # The outlier (e.g. a single animation frame) is seen first but only
    # once; the true, static overlay offset repeats afterward. A
    # first-hit strategy would wrongly lock onto the outlier.
    frames = [outlier_frame] + [true_frame] * config.CALIBRATION_MIN_VOTES
    cap = _FakeCapture(frames)

    offset = hud_reader._calibrate_offset(cap, combo_label_template, frame_interval=1)

    assert offset == true_offset
