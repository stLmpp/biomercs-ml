"""Tunable constants for the HUD-reading pipeline.

All pixel coordinates below were calibrated against
tests/fixtures/frames/sample_frame_01.png at 1280x720 resolution, using
the crop recipe documented in Task 2 of
docs/superpowers/plans/2026-09-16-kill-labeling-pipeline.md. Recalibrate
every ROI/slot value here if source footage has a different resolution
or HUD layout.
"""

REFERENCE_RESOLUTION = (1280, 720)  # (width, height)

# Each slot/ROI below is (x, y, width, height) in pixels.
TIMER_MINUTES_SLOTS = [(525, 93, 40, 76), (555, 93, 40, 76)]
TIMER_SECONDS_SLOTS = [(605, 93, 40, 76), (635, 93, 40, 76)]
COMBO_DIGIT_SLOTS = [(916, 113, 34, 46), (948, 113, 34, 46), (980, 113, 34, 46)]
COMBO_LABEL_ROI = (1015, 113, 110, 46)

TIMER_DIGITS_DIR = "templates/digits_timer"
COMBO_DIGITS_DIR = "templates/digits_combo"
COMBO_LABEL_TEMPLATE_PATH = "templates/combo_label.png"

DIGIT_MATCH_MIN_CONFIDENCE = 0.6
COMBO_LABEL_MIN_CONFIDENCE = 0.6
# Real (especially re-encoded/compressed) video can render a digit a
# few pixels off from its calibrated slot purely from
# compression/encoding noise, not a real position change. Matching
# against a slightly padded crop (and taking the best-aligned score
# within it) tolerates this without needing a per-video correction.
DIGIT_SEARCH_MARGIN_PX = 6

# Per-video HUD alignment: some sources (e.g. re-encoded/re-uploaded
# footage) render the HUD a few pixels off from the reference frames
# above, even at the same resolution. find_best_offset() searches this
# radius once per video to compensate.
OFFSET_SEARCH_RADIUS_PX = 20
# Calibration checks many more candidate positions per frame than a
# normal validity check (a (2*radius+1)^2 grid vs. one fixed ROI), so a
# frame with no real HUD at all (e.g. a pre-gameplay intro) has a much
# higher chance of a spurious position clearing the ordinary
# confidence bar by luck. Require a much stronger match before locking
# in an offset for the whole video, and scan enough candidates to get
# past a typical intro before giving up.
CALIBRATION_MIN_CONFIDENCE = 0.85
CALIBRATION_MAX_FRAMES = 600
# A single confident-looking frame isn't enough on its own -- a combo
# counter's "pop" animation on update can transiently render the label
# at a different position than its static resting offset. Require the
# same offset to repeat across this many independent frames before
# trusting it.
CALIBRATION_MIN_VOTES = 3

# A jump this large between two adjacent samples is definitionally a
# read error (digit misread, missed session boundary), not a real
# simultaneous-kill group -- the game's enemy pool per stage is a few
# hundred at most, and the spec's own examples top out around 3
# simultaneous kills.
MAX_PLAUSIBLE_GROUP_SIZE = 20

SAMPLE_INTERVAL_S = 0.2
SESSION_RESET_DROP_S = 1.0
SESSION_RESET_JUMP_S = 25.0
LABEL_TOLERANCE_S = 1.0

CLIP_BEFORE_S = 2.0
CLIP_AFTER_S = 2.0
