# Fixed Bugs

Resolved issues in the biomercs-ml pipeline, kept for reference (what broke,
why, how it was fixed) so a fix never needs to be re-derived or accidentally
re-broken. Same slug convention as `KNOWN_BUGS.md` — if you're looking for an
open issue instead, check there.

Full evidence and reasoning lives in `DECISIONS.md`; each entry below points
at the section title to search for.

## Digit-matching / templates

### `combo-label-margin-bleed`
`DIGIT_SEARCH_MARGIN_PX` (added for compression-jitter tolerance) could
reach past a digit slot's own box into the adjacent "COMBO" label text,
deterministically misreading a solid `149` as `140`.
**Fix:** clamp each slot's margin *extension* (never the slot itself) to
the midpoint with its neighbor, or an explicit `right_bound` for
non-slot neighbors (`COMBO_LABEL_ROI`, `POPUP_LABEL_ROI`).
- DECISIONS.md § "Digit jitter-margin bleeding into neighboring HUD
  elements"

### `combo-0-vs-8-9-template-mismatch` ("the fifth root cause")
Combo templates `0/3/5/7` were sourced from one calibration screenshot
while the rest came from real footage; the mismatched "0" template lost
confidently to "8"/"9" against real, compressed footage, producing
phantom `n_bullet=10` groups.
**Fix:** multi-sample template architecture (`dict[str, list[ndarray]]`,
directory-per-digit, max score across a digit's own samples wins) +
real-footage samples curated for 0/3/5/7 (commit `85186fa`).
**Residual accepted limit:** video2 t=408.8s is genuinely overexposed (the
"0"'s hollow center is blown out) — no template can recover this; caught
downstream instead.
- DECISIONS.md § "Combo digit '0' losing template match to '8'/'9' (fifth
  root cause)" and follow-ups

### `combo-extraction-tool-missed-white-digits`
The screenshot-curation tool (data prep, not the pipeline itself) only
detected blue-rendered combo digits; combo actually renders white except
at exact multiples of 10, so the common case was silently missed.
**Fix:** adaptive two-color detector (blue OR white) + adaptive
column-width band split.
- DECISIONS.md § "second screenshot batch closes the gap; combo color
  rule; architecture decided"

### `under-curated-digits-1-2-4-6-9`
Only 0/3/5/7 got real-footage multi-sample curation as originally
planned; 1/2/4/6/8/9 kept a single sample each, and the lone "8" sample
over-matched broadly, even on clean frames.
**Fix:** `config.MAX_PLAUSIBLE_COMBO_VALUE=150` (RE5's enemy pool caps
combo at 150 — any higher reading is always a misread) + real-footage
samples added for 1/2/4/6/9 (no real "8" occurrence was ever found; "8"
uses one atlas-sourced sample instead). See `combo-6-vs-0-tens-misread`
and `combo-8-clean-frame-overmatch` in KNOWN_BUGS.md for residuals this
didn't fully close.
- DECISIONS.md § "Extended multi-sample curation to the six under-curated
  digits...", § "then a much bigger finding..."

### `combo-3-vs-8-9-misread`
Digit "8"'s shape structurally overlaps "3" under raw-pixel correlation —
a real "3" has a visible concave notch on its left side (mid-height) that
"8"/"9" don't. Validated: real "3" scored 8.65-12.02 vs. real "8"/"9"
-0.03 to 2.92, a clean ~5.7-point margin.
**Fix:** `hud_reader.waist_notch_score` (per-row leftmost-ink position,
HSV-Value+Otsu binarized; middle-band average vs. top+bottom-band
average) as a **scoped** tie-breaker in `match_digit(...,
apply_waist_notch_tiebreak=True)` — only fires when the raw winner is "8"
or "9". `read_combo` passes the flag; `read_timer`/
`read_popup_ones_digit` don't (see `timer-3-vs-8-9-misread` in
KNOWN_BUGS.md — doesn't transfer to that font). TDD'd with real footage
crops, 110 tests. Verified via full real-footage A/B diff + user manual
review on video 1: fixed a known phantom (`combo-static-background-bleed`
below) and correctly split a previously-merged kill pair in a
known-chaotic stretch. **Does not cover `combo-2-vs-8-misread`** (fixed
separately below).
- DECISIONS.md § "a new, promising lead found (a geometric 'waist notch'
  feature...)", § "the waist-notch tie-breaker implemented for the combo
  font..."

### `combo-2-vs-8-misread` ★
The project's single biggest confirmed accuracy driver. video5 `id=6`
(t=576.0): combo genuinely went `111→112` (one bonus kill, confirmed by
an on-screen "+05 sec." popup) but read as `118` for ~2.5s straight.
Since `n_bullet = group_size - n_bonus` is an unverified remainder, this
one misread alone explained most of `fabricated-bullet-count-on-bonus-kill`.
Four earlier independent fix attempts failed (raw-BGR add/remove samples,
HSV-Value+Otsu binarize + re-curation, binarize + 4x upscale) —
conclusion: digit "8"'s shape structurally overlaps "2"/"3"/"9" under
raw-pixel correlation at 34×46px, not a template-quality gap. **Not
covered by `combo-3-vs-8-9-misread`'s fix** (waist-notch only redirects
toward "3") — "2"'s concavity sits on a different axis from "3"'s: the
diagonal stroke pulls the *rightmost* ink column in just above the base
bar, which then snaps back out to full width, vs. "3"'s left-side waist
notch.
**Fix:** `hud_reader.base_widen_score` (rightmost-ink column, HSV-Value
+Otsu binarized, bands relative to the glyph's own ink bounding box —
excluding any row that spans edge-to-edge, since `read_digit_slots`'
margin padding can pull in a HUD border line) as a second **scoped**
tie-breaker alongside `waist_notch_score` in `match_digit(...,
apply_waist_notch_tiebreak=True)` — only fires when the raw winner is "8"
or "9". Validated against every combo-font template (real "2" scored
11.0-14.5, every other digit -4.7-2.9) and real-footage crops, including
through a full `read_digit_slots` margin-padded crop (real "2" scored
13.3-13.5, real "8"/"3"/"9" scored -2.0-1.0). TDD'd
(`tests/test_hud_reader_base_widen.py`), including a `read_combo`
regression test on the real video5 frame that fixes `112` misread as
`118`. **Verified via a full real-footage A/B diff across all five
videos** (stash/run/restore, `sample_video` re-run before/after on each):
93% of all 279 raw combo-tick changes were exactly the target `_8 -> _2`
pattern (e.g. `138->132` x106, `118->112` x72, `148->142` x68), clustered
in long session-consistent bursts, not isolated flickers. Manually
confirmed against the actual video frames (not just crops) for four
distinct changes across three videos, including the original video5
t=576.0 instance — every one showed the *fixed* reading was the visibly
correct on-screen value. One rare tens-digit case (video2 t=479.2,
`133->123`) turned out to be a bonus fix: the old waist-notch check had
been misfiring "3" over the true "2" there too. No new implausible
values, no new low-confidence drops, across any video.
- DECISIONS.md § "video5 id=6's overcount root-caused...", § "tried option
  2 (binarize...)"

### `combo-static-background-bleed` (the video1 t=62.2 "phantom event")
A busy static background (a mossy rock wall texture behind the
semi-transparent combo counter) bled into the digit search margin,
occasionally winning "8" over the true "0"/"2" — ground truth: combo
never moved from `012` in the whole window, no kill happened there.
**Fix:** disappeared as a side effect of `combo-3-vs-8-9-misread`'s fix
(confirmed via A/B diff, not separately targeted).
- DECISIONS.md § "Phantom-event pattern root-caused..." (root cause), §
  "the waist-notch tie-breaker implemented..." (disappearance confirmed)

## Event detection / kill-grouping

### `transient-digit-misread-vote-burst`
A single/few-frame digit misread landing exactly on the 0.2s sample grid
created phantom kill-groups where the real value never changed.
**Fix:** majority-vote a burst of frames per tick
(`hud_reader._majority_value`, `config.SAMPLE_VOTE_FRAMES`). See
`bug-d-vote-burst-too-narrow` below — the initial burst size (3) wasn't
big enough for all cases, widened later.
- DECISIONS.md § "Combo/timer misread robustness (real-footage
  validation)"

### `map-pickup-misattributed-as-bonus-kill`
A map time-bonus pickup (+30/+60/+90s popup) is a timer-increase source
`auto_labeler` had no concept of, wrongly attributed entirely to bonus
kills. The popup's effect animates in gradually (~15s), so it doesn't
land on one clean tick.
**Fix:** detect the pickup popup (ones digit "0", vs. the fixed "+05"
kill-bonus popup) within `config.PICKUP_EXCLUSION_WINDOW_S` (5s) of a
candidate group and discard the group entirely. Follow-on fix in the same
commit: search across all samples, not just the current session (severe
misreads in the same chaotic stretch were fragmenting sessions).
- DECISIONS.md § "Map time-bonus pickups vs. kill bonuses"

### `bug-a-timer-delta-adjacent-pair-desync`
The combo counter animates ~350ms-2s after a kill, but the timer changes
in a single frame — `detect_kill_groups` assumed both land on the same
adjacent-sample pair, so a real bonus kill could read as a `bullet_kill`
when the combo animation and timer jump straddled different ticks.
**Fix:** `_timer_before`/`_timer_after` search a window
(`config.TIMER_DELTA_SEARCH_WINDOW_S=3.0`) for the timer's own jump,
decay-adjusted to a common reference point. **Contamination guard added
after A/B testing found a second bug:** the window had no plausibility
cap, so a wild misread elsewhere could win the min/max search — fixed
with a swing bound derived from `MAX_PLAUSIBLE_GROUP_SIZE`.
- DECISIONS.md § "Phantom-event pattern root-caused... Bug A fixed via a
  timer-delta search window"

### `bug-c-session-boundary-blind-dip-guard`
The transient-dip guard (`session_samples[i-1].combo_value >=
curr.combo_value`) only checked the previous sample *within the same
session* — a misread severe enough to also trigger a spurious session
split landed at index 0 of the new session, where there's no `i-1`, so
the guard was structurally blind exactly when session-splitting misreads
happen.
**Fix:** `_preceding_combo_value(all_samples, timestamp_s)` finds the
chronologically-nearest sample before a timestamp across the *full*
sample list, not just the current session.
- DECISIONS.md § "Bug C fixed: transient-dip guard now looks across
  session boundaries"

### `bug-d-vote-burst-too-narrow`
Rapid frame-to-frame flicker (combo bouncing among 5+ values every frame)
was too fast/noisy for the original 3-frame majority vote — the true
value was the overall plurality, just not within the specific 3-frame
window a tick happened to land on.
**Fix:** widened `config.SAMPLE_VOTE_FRAMES` from 3 to 11 (TDD'd as the
minimum that flips the real t=522.0 case). **Settled, don't re-litigate**
— lowering it back down for performance was explicitly rejected by the
user ("SAMPLE_VOTE_FRAMES must be 11").
- DECISIONS.md § "Bug D fixed (widened majority vote); then a much bigger
  finding..."

### `group-size-overestimation-uncorroborated-anchors`
`detect_kill_groups` trusted each tick's raw per-tick majority-voted
`combo_value` for `prev`/`curr` outright. Two *partial*-corruption
mechanisms (smaller than a real kill's own magnitude, so invisible to the
dip/reversion guards) inflated `group_size`: a combo roll/pop animation's
transient intermediate value winning the vote, and a near-unreadable
burst where one lone uncorroborated frame wins "majority" by default.
**Considered and rejected:** a minimum-vote-count floor — simulated
first, found a 1-vote winner is 20-30% of *all* successful combo reads
project-wide, so a blanket floor would discard many genuinely correct
reads.
**Fix:** `_effective_prev_combo_value`/`_effective_curr_combo_value`
clamp `prev`/`curr` against the nearest trusted neighboring sample within
`COMBO_REVERSION_CHECK_WINDOW_S`, using combo's monotonic-non-decreasing
domain constraint (mirrors Bug A's timer-window search).
**Residual accepted limit:** one case's reconstructed group_size from
available samples is 1, not the true 2 — recovering it needs the actual
clip video, not just per-tick HUD samples. See
`group-size-video3-overshoot` in KNOWN_BUGS.md for a related residual
this didn't fully close.
- DECISIONS.md § "Manual review of all 10 post-Bug-A clips...", § "
  `group_size` overestimation root-caused and fixed..."

### `max-plausible-group-size-too-loose`
`MAX_PLAUSIBLE_GROUP_SIZE=20` let real bugs (n_bullet=19, n_bullet=9
groups) through untouched.
**Fix:** tightened to 8 (per the author's own domain judgment: 8
simultaneous kills is roughly a one-in-a-million event, rare but real).
- DECISIONS.md § "event_detector domain-knowledge safeguards..."

### `combo-reversion-guard-missing`
No check existed for a combo rise that reverts to at-or-below its
pre-rise value shortly after (combo can only ever increase in a real
session) — this pattern produced the original four `n_bullet=10` phantom
groups.
**Fix:** reversion check with `COMBO_REVERSION_CHECK_WINDOW_S=6.0s`,
searching all samples globally (same precedent as the pickup search,
since chaotic stretches fragment sessions too).
- DECISIONS.md § "event_detector domain-knowledge safeguards..."

### `review-correction-not-normalized-to-correct`
The review script always recorded a typed `<bonus>/<bullet>` correction
as incorrect, even when the numbers exactly matched what was already
detected (an easy mistake when meaning to type `y`).
**Fix:** `review.normalize_review_answer` collapses a numerically-matching
correction to "y".
- DECISIONS.md § "Manual review of the fix's clips: id=3 fixed exactly as
  intended; found and fixed a real data-entry gap in the review tooling
  itself"

## Calibration / performance

### `hud-offset-calibration-pregame-stretch-exhausts-budget`
`_calibrate_offset` scans sequentially from frame 0 and gives up after
`CALIBRATION_MAX_FRAMES` (~120s of video). A video whose real gameplay
didn't start until t=146.9s (a normal "preparation lap") never saw a real
gameplay frame during calibration and locked in the wrong `(0,0)` offset
for the *entire* video — starving `is_valid_hud_frame` almost everywhere.
**Fix:** start the calibration scan from the video's midpoint instead of
frame 0 (by a run's midpoint, real gameplay is almost certainly on
screen). Verified via full A/B diff across 4 videos: the target video
went from 36→327 samples; the other 3 were byte-identical before/after.
- DECISIONS.md § "a fourth video, cross-validation — new root cause
  found: calibration's scan budget..."

### `offset-search-brute-force-slow` (performance)
`find_best_offset` did a brute-force 1681-position grid search per
candidate frame — ~60s/video, ~12% of a full pipeline run.
**Fix:** coarse-to-fine search (a coarse grid pass, then 1px refinement
around the winner). Measured: 59.5s → 6.9s (8.6x), same exact offset
found, no accuracy regression.
- DECISIONS.md, the performance-track entries (search "matchTemplate" or
  "calibration")

### `sample-video-sequential-bottleneck` (performance)
`sample_video`'s per-tick digit-matching loop was ~84% of a full pipeline
run (97.9% of that inside `cv2.matchTemplate` itself — a call-count
problem, not Python overhead).
**Fix:** `ProcessPoolExecutor`-based chunking (`_sample_range` worker,
`max_workers` param; `max_workers=1` skips the executor entirely so
`unittest.mock.patch`-based tests keep working). Verified byte-identical
output between `max_workers=1` and parallel; ~4.3x real end-to-end
speedup (500s → 115s on a 10-core machine).
- DECISIONS.md § "Parallelized `sample_video` across CPU cores"
