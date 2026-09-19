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

# RE5 Mercenaries' enemy pool is fixed -- per the author's own
# top-level competitive experience, the combo counter can never exceed
# 150 in a single run. A reading above this is always a misread, not a
# real value, regardless of confidence -- see DECISIONS.md, real
# footage (video 2, t=124.0s) where a clean, unoccluded "029" was
# confidently misread as "889".
MAX_PLAUSIBLE_COMBO_VALUE = 150

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
# A brute-force search over the full radius is (2*radius+1)^2 = 1681
# cv2.matchTemplate calls per candidate frame -- measured (cProfile) as
# the dominant cost of calibration, ~60s/video (~12% of a full
# pipeline run). find_best_offset() instead does a coarse grid at this
# stride first, then refines at 1px resolution in a window of this
# same size around the coarse winner -- the correlation landscape for
# a fixed HUD label search is smooth/unimodal at this scale, so this
# reliably finds the same exact-pixel optimum as brute force (see
# test_hud_reader_offset.py) for a fraction of the calls.
OFFSET_COARSE_SEARCH_STRIDE_PX = 4
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

# A larger same-kind kill count is real-world rarer than a small one
# (per the author's own top-level competitive experience), so a label's
# reported confidence should reflect that prior on top of its raw
# digit-read confidence, not just a hard yes/no cutoff at
# MAX_PLAUSIBLE_GROUP_SIZE. Purely informational (nothing filters on it
# automatically) -- it sharpens the signal already shown during manual
# review. Bullet kills are strictly rarer than bonus kills at the same
# count in a good run (Wesker's dash-finisher meta makes bullet-only
# kills uncommon -- see DECISIONS.md, manual review found real
# n_bullet=0 in every wrong clip this session), so bonus and bullet get
# separate tables rather than one shared by raw group_size -- see
# auto_labeler.label_kill_group, the only place that knows the
# bonus/bullet split.
BONUS_COUNT_CONFIDENCE_FACTOR: dict[int, float] = {
    1: 1.0,
    2: 1.0,
    3: 1.0,
    4: 0.90,
    5: 0.50,
    6: 0.15,
    7: 0.10,
    8: 0.05,
}
BULLET_COUNT_CONFIDENCE_FACTOR: dict[int, float] = {
    1: 1.0,
    2: 1.0,
    3: 0.80,
    4: 0.60,
    5: 0.40,
    6: 0.20,
    7: 0.10,
    8: 0.05,
}

# A transient single-frame digit misread (e.g. compression noise
# flipping "8"->"0" for one frame) landing exactly on a sample tick can
# look like a real combo/timer change -- voting across a short burst of
# frames per tick absorbs a lone outlier instead of trusting one frame.
# 3 frames isn't always enough: real footage (video 2, ~t=522.0s) shows
# heavy motion-blur/particle noise making a digit flicker among several
# different wrong values almost every frame for under a second, with no
# single dominant wrong reading -- a 3-frame vote reliably lands on
# whichever wrong value happens to fill the window, even though the
# true value is the single most common reading across the full noisy
# stretch. 11 is the minimum burst size that recovers the true value
# for that real case (see DECISIONS.md, "Bug D") -- must stay below the
# per-tick frame count (`round(fps * SAMPLE_INTERVAL_S)`, 12 at the
# 60fps this project's footage uses so far) or the burst would read
# into the next tick's window.
SAMPLE_VOTE_FRAMES = 11

# sample_video has no other visibility into a multi-minute run --
# print progress at most this often (in percent of total video
# duration processed) instead of staying silent until it returns.
PROGRESS_LOG_INTERVAL_PERCENT = 10

SAMPLE_INTERVAL_S = 0.2
# A new round always starts at exactly 2:00 (120s) -- per the author's
# own top-level competitive experience. A real transition is therefore
# always a huge change (banked bonus time regularly exceeds 580s before
# a reset to 120s), while real per-tick digit-read noise during dense
# combat tops out far below these thresholds (real footage: video4,
# t=606.6-649.0s window, noisiest observed drop -12s) -- see
# DECISIONS.md, "timer-noise-session-fragmentation". The prior values
# (1.0 / 25.0) were tight enough to misclassify both this ordinary read
# noise (as a drop) and legitimate stacked bonuses -- a map time-bonus
# pickup (+90) landing in the same tick as a kill bonus (+5), or rarer
# still, per the author's own confirmation, up to ~+105 -- as fake
# session resets.
SESSION_RESET_DROP_S = 30.0
SESSION_RESET_JUMP_S = 120.0
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

# Consecutive "+05 sec." popup ticks closer than this belong to one popup
# episode (one on-screen popup, however many kills it covers). Two ticks
# is SAMPLE_INTERVAL_S * 2: it bridges a single tick whose popup read
# failed, without joining two genuinely separate kills.
POPUP_EPISODE_MAX_GAP_S = 0.5

# How far before/after a popup episode its bonus is measured, as the
# median of the decay-adjusted timer readings in that span. A median (not
# the min/max event_detector's combo-pair logic uses) because single-tick
# timer misreads (see DECISIONS.md, timer-noise-session-fragmentation)
# would otherwise inflate the +5s-per-kill count.
POPUP_TIMER_WINDOW_S = 1.5

# The combo counter only ever increases during a session (it can drop
# to near zero on a rare genuine combo break, but never dips by a small
# amount and then climbs back to exactly where it was). A rise that
# reverts to at or below its pre-rise value within this window is a
# digit misread, not a real kill -- see DECISIONS.md, "sixth root
# cause" (combo tens-digit misread surviving majority vote across an
# entire multi-second overexposed stretch). Real footage showed the
# revert sample landing up to ~4s after the phantom rise.
#
# Also reused as the search window for clamping a kill-group's prev/curr
# combo anchors against their nearest trusted neighbor before computing
# group_size (see event_detector._effective_prev_combo_value /
# _effective_curr_combo_value) -- same underlying phenomenon (a
# per-tick vote landing on a wrong value that a nearby sample
# contradicts), just correcting the value instead of only using it as a
# drop/keep signal.
COMBO_REVERSION_CHECK_WINDOW_S = 6.0

# A digit-shaped concave notch: for each row, the leftmost ink pixel's
# column position, averaged separately for the crop's middle third vs.
# its top+bottom thirds (see hud_reader.waist_notch_score). A real "3"
# has the notch (a positive score); "8"/"9" don't (near-zero or
# negative). Validated against every combo-font template and several
# real-footage crops -- real "3" scored 6.92-11.63 (templates) / 8.42
# (real crop), real "8"/"9" scored -7.0-2.92 (templates and real crops)
# -- see DECISIONS.md, "the waist-notch feature tested against the
# timer font...". This threshold sits at the midpoint of that gap.
# Confirmed NOT to hold for the timer font's different-proportioned
# digits -- do not reuse this constant or match_digit's
# apply_waist_notch_tiebreak for timer/popup digit reading.
WAIST_NOTCH_THREE_THRESHOLD = 5.0

# A different digit-shaped concavity from the one above: "2"'s diagonal
# stroke pulls the *rightmost* ink column inward just above the base
# bar, which then snaps back out to full width (see
# hud_reader.base_widen_score -- rightmost-ink column, base-band average
# minus taper-band minimum, bands relative to the glyph's own ink
# bounding box so read_digit_slots' margin padding doesn't dilute them).
# A real "2" has this jump (a positive score); every other combo-font
# digit doesn't (near-zero or negative). Validated against every
# combo-font template (real "2" scored 11.0-14.5, every other digit
# -4.7-2.9) and real-footage crops, including through a full
# read_digit_slots margin-padded crop (real "2" scored 13.3-13.5, real
# "8"/"3"/"9" scored -2.0-1.0). This threshold sits well below that gap,
# matching WAIST_NOTCH_THREE_THRESHOLD's scale.
BASE_WIDEN_TWO_THRESHOLD = 5.0

# The combo counter's roll/pop animation takes ~350ms for a single kill
# but up to ~2s for a fast multi-kill chain (real footage: video 2,
# t=122.0), while the timer jumps in a single frame -- so the sample
# pair where combo settles into its new value is often not the same
# pair where the timer's own jump landed. Search this far before the
# "before" sample and after the "after" sample for the timer's true
# pre-/post-kill value instead of trusting the combo-based pair
# directly -- see DECISIONS.md, "Bug A".
TIMER_DELTA_SEARCH_WINDOW_S = 3.0
