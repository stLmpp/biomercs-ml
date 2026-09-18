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

# The "+XX sec." popup shown next to the timer for both kill bonuses
# (always fixed at "+05" by the game itself, regardless of how many
# simultaneous bonus kills actually happened) and map time-bonus
# pickups (always +30/+60/+90, i.e. the ones digit is always "0"). We
# only need the ones digit to tell the two apart -- "5" means an
# ordinary kill-bonus popup (ignore), "0" means a pickup.
POPUP_ONES_DIGIT_SLOT = (790, 134, 20, 34)
POPUP_LABEL_ROI = (813, 132, 64, 38)

TIMER_DIGITS_DIR = "templates/digits_timer"
COMBO_DIGITS_DIR = "templates/digits_combo"
POPUP_DIGITS_DIR = "templates/digits_popup"
COMBO_LABEL_TEMPLATE_PATH = "templates/combo_label.png"
POPUP_LABEL_TEMPLATE_PATH = "templates/popup_label.png"

DIGIT_MATCH_MIN_CONFIDENCE = 0.6
COMBO_LABEL_MIN_CONFIDENCE = 0.6
POPUP_LABEL_MIN_CONFIDENCE = 0.6
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
# simultaneous-kill group. Per the author's own top-level competitive
# experience: 8 simultaneous kills is a one-in-a-million-type event
# (rare, but has happened) -- anything above that is not a plausible
# real group.
MAX_PLAUSIBLE_GROUP_SIZE = 8

# A larger simultaneous-kill group is real-world rarer than a small one
# (per the author's own top-level competitive experience), so a group's
# reported confidence should reflect that prior on top of its raw
# digit-read confidence, not just a hard yes/no cutoff at
# MAX_PLAUSIBLE_GROUP_SIZE. Purely informational today (nothing filters
# on it automatically) -- it sharpens the signal already shown during
# manual review.
GROUP_SIZE_CONFIDENCE_FACTOR: dict[int, float] = {
    1: 1.0,
    2: 1.0,
    3: 1.0,
    4: 0.9,
    5: 0.75,
    6: 0.55,
    7: 0.35,
    8: 0.15,
}

# A transient single-frame digit misread (e.g. compression noise
# flipping "8"->"0" for one frame) landing exactly on a sample tick can
# look like a real combo/timer change -- voting across a short burst of
# frames per tick absorbs a lone outlier instead of trusting one frame.
SAMPLE_VOTE_FRAMES = 3

SAMPLE_INTERVAL_S = 0.2
SESSION_RESET_DROP_S = 1.0
SESSION_RESET_JUMP_S = 25.0
LABEL_TOLERANCE_S = 1.0

CLIP_BEFORE_S = 2.0
CLIP_AFTER_S = 2.0

# A map pickup's timer contribution animates in gradually over several
# seconds (confirmed on real footage: a ~275s timer took ~15s to fully
# reflect a pickup collected around 156-161s), not on the single 0.2s
# tick where the popup itself is visible -- so a kill-group anywhere in
# this window around a detected pickup popup gets discarded rather than
# guessing how to split the credit.
PICKUP_EXCLUSION_WINDOW_S = 5.0

# The combo counter only ever increases during a session (it can drop
# to near zero on a rare genuine combo break, but never dips by a small
# amount and then climbs back to exactly where it was). A rise that
# reverts to at or below its pre-rise value within this window is a
# digit misread, not a real kill -- see DECISIONS.md, "sixth root
# cause" (combo tens-digit misread surviving majority vote across an
# entire multi-second overexposed stretch). Real footage showed the
# revert sample landing up to ~4s after the phantom rise.
COMBO_REVERSION_CHECK_WINDOW_S = 6.0
