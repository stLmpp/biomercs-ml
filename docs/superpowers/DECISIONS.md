# Decisions log

Record of non-obvious choices made while building the kill-labeling
pipeline, and the alternatives considered, so a future session can
understand *why* something is built the way it is instead of
re-deriving or second-guessing it. Append to this file as new
decisions come up — don't rewrite past entries except to note when a
decision was later reversed (and why).

## 2026-09-16 — Combo/timer misread robustness (real-footage validation)

**Problem:** manual review of the auto-labeled dataset found ~47-53%
agreement, far below the spec's >98% target. Root-caused via
frame-by-frame tracing (see HANDOFF.md history) to several distinct
misread patterns, not one bug.

- **Transient single/few-frame digit misreads** (e.g. combo's last
  digit briefly flipping "8"->"0" for 1-5 frames) landing exactly on
  the 0.2s sampling grid created phantom kill-groups where the real
  value never changed.
  - Considered: bigger single-frame read only (rejected — no defense
    at all), majority-voting a burst of frames per tick (**chosen**),
    persistence-only check with no voting (rejected as sole fix — see
    below).
  - Implemented: `hud_reader._majority_value` + burst read in
    `sample_video` (`config.SAMPLE_VOTE_FRAMES = 3`).
  - **Known limit:** a misread streak longer than half the burst
    still wins the vote (confirmed on real data: a 5-frame misread
    streak beat a 3-frame burst 2-to-1). Voting alone was not
    sufficient.

- **Misread streaks longer than the vote burst** still slipped
  through as a real-looking dip-then-recovery (the dip is ignored as
  a negative delta, but recovering to the true value right after
  looks like a real rise).
  - Considered: just increase `SAMPLE_VOTE_FRAMES` (rejected — only
    shifts the threshold, any streak longer than half the burst still
    fools it, and costs more decode work per tick), add a persistence
    check in `event_detector` that confirms a rise isn't just recovery
    from the sample two steps back (**chosen**, layered on top of the
    vote as a second, independent defense).
  - Implemented: `event_detector.detect_kill_groups` now checks
    `session_samples[i-1].combo_value >= curr.combo_value` before
    trusting a rise.
  - Verified on real footage: eliminated all 5 confirmed phantom
    `bullet_kill`/`mixed` events from the review sample.

## 2026-09-16 — Manual review script: redo option

Mistyped y/n answers during a review run had no way to correct
without restarting the whole session.
- Considered: just re-run the whole review (rejected — wasteful for
  one mistake), add an `r` command that undoes the previous answer's
  tally + DB write and re-prompts for that clip (**chosen**).
- Implemented: `biomercs_ml.review.ReviewTally` (testable, pure
  bookkeeping) + a thin loop change in `scripts/review_sample.py`.
- **Known limit:** redoing an already-recorded y/n into a skip does
  not clear the previously-written `review_correct` DB value (edge
  case, not implemented — not worth the complexity for how rarely
  this specific sequence would happen).

## 2026-09-16 — Map time-bonus pickups vs. kill bonuses

Manual review surfaced a third distinct failure mode: a map pickup
(+30/+60/+90s, shown as a "+XX sec." popup) is a timer-increase source
`auto_labeler` has no concept of — it attributes any timer increase in
a kill-group's window purely to bonus kills.

Investigated one concrete case (`id=16`, session 89, ts=163.6): traced
the actual popup to ~t=161.7 (an overexposed/flash frame), but the
kill-group `event_detector` flagged is at ~t=163.4-163.6 — a ~2s gap.
The timer's climb from the pickup is *gradual* (~216s at t=156 to
~276s at t=171, over ~15s), not an instant jump — consistent with the
knowledge base's note that queued bonus additions "animate in one at a
time." This means no single adjacent-sample delta cleanly reflects one
kill-group's true bonus during a busy multi-kill-chain-plus-pickup
stretch.

- Considered: detect the popup and subtract its exact value from the
  affected group's `raw_delta` (**initially chosen, then reconsidered**
  once the ~2s timing gap was found — the popup isn't even inside the
  affected group's own tick pair, so a same-tick subtraction wouldn't
  have fixed this case). Also considered a full holistic-window
  redesign (rejected for now — real architecture change, not a quick
  patch, revisit if the simpler fix proves insufficient).
- **Chosen:** detect a pickup popup (value in `{30, 60, 90}`, distinct
  from the kill-bonus popup which the game always fixes at "+05"
  regardless of simultaneous-kill count — so no ambiguity requiring
  that "+05 always means kill bonus" assumption to hold) anywhere
  within a time window of a candidate kill-group, and **discard** the
  group entirely rather than compute a split. Same philosophy as the
  existing implausible-group-size guard: drop unreliable data rather
  than guess. Sacrifices some dataset yield on these rarer, messier
  cases.
- **Implemented.** `hud_reader.is_popup_visible` / `read_popup_ones_digit`
  detect the popup per-tick (majority-voted like combo/timer);
  `event_detector.detect_kill_groups` discards any candidate group
  within `config.PICKUP_EXCLUSION_WINDOW_S` (5s) of a detected pickup.
  Verified on real footage: `id=16` (session 89, ts=163.6) is now
  correctly excluded.
- **Follow-up bug found during implementation:** the pickup-flagged
  sample and the kill-group it should suppress landed in *different*
  sessions, because severe digit misreads in that same chaotic stretch
  (fast kill chain + screen flash) split what should have been one
  session into several spurious ones (`is_new_session` triggered
  repeatedly on bogus timer jumps). Scoping the pickup search to only
  the current session's samples missed it entirely.
  - Considered: fix the underlying session-splitting misreads
    (rejected for now -- separate, deeper root cause, same class as
    the earlier "3"/"8" digit-confusion-under-motion-blur finding, not
    yet investigated), search across *all* samples for a nearby
    pickup regardless of session boundaries (**chosen** -- a pickup
    doesn't care about a session boundary, spurious or not).
  - Implemented: `detect_kill_groups` takes an optional `all_samples`
    param (defaults to `session_samples` for backward compatibility);
    `pipeline.run` passes the full pre-partition sample list.
  - **Known open issue, not yet investigated:** the underlying session
    over-splitting during chaotic/overexposed footage stretches is
    still there and could affect other things that assume session
    continuity (none currently do, besides this pickup search) --
    worth a dedicated investigation if it turns out to matter more.

## 2026-09-16 — Digit jitter-margin bleeding into neighboring HUD elements

Found on a **second** downloaded video during manual review: a
menu-open frame with a rock-solid, clearly-legible combo of `149` was
consistently auto-labeled from a misread of `140`. Root-caused to
`DIGIT_SEARCH_MARGIN_PX` (added earlier for compression-jitter
tolerance) reaching past a digit slot's own nominal box far enough to
match against a *different* real thing next to it, not noise:

- Combo's 3 digit slots are only 32px apart at 34px wide -- already
  touching/slightly overlapping at baseline, before any margin. My
  first hypothesis (margin bleeding into the *previous digit slot*)
  was wrong for this specific case, confirmed by testing left-only vs
  right-only margin extensions in isolation.
- The actual cause: the "COMBO" label text sits just 1px after the
  *last* digit slot. The right-side margin extension reached into it,
  and something there matched the "0" template better than the true
  "9" did in its own tight crop. Same class of risk exists for the
  popup's ones-digit slot (only ~3px from the "sec." label).

This is deterministic (same wrong reading every time this content
renders), not transient per-frame noise -- majority-voting and the
event_detector persistence check both operate on the assumption that
misreads are inconsistent across nearby samples/frames, so neither
could ever have caught this.

- Considered: recalibrate the slot geometry itself (rejected -- risky
  change to well-established, calibrated constants for a problem that
  doesn't require it), reduce `DIGIT_SEARCH_MARGIN_PX` globally
  (rejected -- would reduce genuine jitter tolerance everywhere to fix
  a narrow, specific adjacency case). **Chosen:** clamp each slot's
  margin *extension* (not the slot itself) to the midpoint with its
  immediate neighbor in the same slot list, and let callers pass an
  explicit `right_bound` for a non-slot neighbor like a label —
  applied to `read_combo` (`COMBO_LABEL_ROI`) and
  `read_popup_ones_digit` (`POPUP_LABEL_ROI`).
- Never shrink the crop below the slot's own nominal box: an earlier
  attempt at a strict midpoint clamp broke matching entirely for
  combo's middle digit, because the available space between its two
  neighbors' midpoints (32px pitch) is *less* than its own declared
  width (34px) -- the nominal slots already assume some overlap by
  necessity. Floor/ceiling every clamp at the nominal box, only ever
  clamping the extra margin beyond it.
- **Known follow-on adjustment:** the existing jitter-tolerance test
  used a synthetic ±4px shift; combo's slots can no longer safely
  absorb that much *horizontal* jitter between each other (there's no
  safe margin left once neighbor-bleed is closed off), so the test was
  reduced to ±2px, which still passes. Real-world compression jitter
  this fix protects against is expected to be smaller than 4px anyway
  (per the original fix #5 that introduced the margin).
- Verified on real footage: eliminates the flagged phantom group and
  drops total clip count on that video from 69 to 46 -- this bug was
  generating far more phantom events than just the one instance caught
  in manual review.

## 2026-09-17 — Combo digit "0" losing template match to "8"/"9" (fifth root cause)

**Problem:** the handoff's "too many bullet kills" lead (four `n_bullet=10`
groups in video 2, sessions 161/163/166/167, ids 30/31/32/34) traced to a
new, distinct failure mode -- not digit-margin bleed (fix from
2026-09-16), not map pickups, not transient noise.

Traced the actual `HudSample` sequences the pipeline produced for all
four sessions (via `hud_reader.sample_video` re-run + pickled samples,
see HANDOFF.md for the reproduction recipe). In every case
`timer_before_s == timer_after_s` exactly (no time passed, so no kill of
any kind actually happened) and the *only* thing that "changed" between
adjacent samples was the combo's tens digit flipping between its true
value and a value 10 away, e.g. `188,188,188,188,198,188` or
`184,184,184,194,184,184` -- hundreds and ones digits rock solid
throughout. Pulled the actual frame at one flip (video 2, t=408.8s): it
plainly reads "105 COMBO" with no occlusion, but the tens-digit crop
scores 0.55 against its own "0" template while scoring 0.80-0.81 against
"8"/"9" -- comfortably clearing `DIGIT_MATCH_MIN_CONFIDENCE` (0.6) with
the wrong digit.

**Root cause, confirmed via `git log --follow` on
`templates/digits_combo/*.png`:** the ten combo digit templates were
captured from two different sources in two different commits --
`0.png`/`3.png`/`5.png`/`7.png` from `f00a365` ("Recalibrate HUD ROIs
against higher-quality 1280x720 screenshots", the single canonical
calibration reference frame `sample_frame_01.png`), and
`1.png`/`2.png`/`4.png`/`6.png`/`8.png`/`9.png` from a later, separate
commit `0766483` ("Complete digit template sets... cropped from real
gameplay footage (Wesker STARS run)"). Visually, `0.png` has a dark
background behind the glyph while `8.png`/`9.png` share the bright
olive background of real footage -- exactly the digits that lose are
exactly the ones sourced from the one-off calibration screenshot
instead of real gameplay video. This is a template *data quality/
consistency* problem, not a matching-logic bug: `TM_CCOEFF_NORMED`
correlates pixel patterns, and at a 34x46px crop, the render pipeline
(scaling + alpha blend + H.264 compression) leaves footage-sourced
templates looking systematically different from a template pulled from
one unrelated static screenshot.

- Considered: a top-2-margin ambiguity check in `match_digit`/
  `read_digit_slots` (reject a match if the winner doesn't clearly beat
  the runner-up) -- would generalize to any future digit-confusion case
  and fits the project's existing "drop unreliable data rather than
  guess" philosophy, but treats the symptom, not the template-quality
  root cause. Considered: a symmetric persistence check in
  `event_detector` (extend the existing dip-then-recovery guard to also
  catch spike-then-revert) -- cheaper, but a third layered heuristic
  bolted onto `detect_kill_groups`, and doesn't cover session 166's
  messier case (the "revert" sample is 4s later, past the immediate
  next tick). Considered: use a pristine digit sprite extracted from the
  game's own asset files as the template -- rejected as the sole
  source, because it never goes through the scale/blend/compress
  pipeline the 6 working footage-sourced templates do, risking swapping
  one source-inconsistency for a different one.
- **Chosen (not yet implemented, pending user-supplied screenshots):**
  recapture `0`/`3`/`5`/`7` from real gameplay, matching how the other
  six were sourced, **and** extend the template model from one image per
  digit to *multiple* sample images per digit (`dict[str, list[ndarray]]`,
  best score across a digit's own samples wins) -- applied uniformly
  across all ten digits, not special-cased to the four broken ones. The
  user will supply: several high-quality **1280x720** PNG screenshots
  taken directly in-game across varied HUD backgrounds (to match
  `config.REFERENCE_RESOLUTION` and avoid resize-artifact mismatch), plus
  the digit's original game asset/sprite as a ground-truth reference
  (used to validate the screenshots are unambiguous, and as one of the
  sample images) plus a couple of digit crops pulled directly from the
  already-downloaded YouTube footage (to hedge the templates being
  cleaner than what real analysis video looks like post-compression).
- **Not yet implemented.** Blocked on the user capturing the
  screenshots (next session). When resuming: TDD the multi-sample
  matching change first against the exact real-footage frames that
  proved the bug (video 2, t=399.8/403.4/408.8/414.0s -- see
  `scripts` reproduction recipe below), then populate all ten combo
  digits' template sets, then re-verify the four phantom
  `n_bullet=10` groups disappear and re-review video 2.

**Reproduction recipe for a fresh session** (ephemeral files won't
survive): re-download video 2
(`https://www.youtube.com/watch?v=u9DA7ueGiH0`, format 298) per the
"Ephemeral files" section below, then:
```python
from pathlib import Path
from biomercs_ml import config, hud_reader, event_detector
timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
popup_digit_templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)
samples = hud_reader.sample_video(
    Path("/tmp/biomercs-footage2/source.mp4"), timer_templates, combo_templates,
    combo_label_template, popup_digit_templates, popup_label_template,
)
sessions = {}
for s in samples:
    sessions.setdefault(s.session_id, []).append(s)
for sid in [161, 163, 166, 167]:
    print(sid, event_detector.detect_kill_groups(sessions[sid], sid, all_samples=samples))
```
Each affected session's samples show the tens-digit flip directly (e.g.
`session_id=161` around t=398-400s reads `181,102,188,188,...,198,188`).

### 2026-09-17 follow-up: user supplied source material, still short on 3/5/7

User dropped `resources/Steam Screenshots.zip` (gitignored -- 323MB, not
meant to be committed) containing 105 native 1920x1080 in-game
screenshots plus `COMBO_ORIGINAL_TEXTURE.png` (384x384, RGBA) and
`TIMER_ORIGINAL_TEXTURE.png` (512x512, RGBA) -- the actual bitmap-font
texture atlases RE5 renders the HUD from.

Built a throwaway extraction pipeline (was in the harness scratchpad,
won't survive a new session, recipe below) that:
- Locates the combo HUD by thresholding blue-dominant pixels
  (`b > 120 and b > r + 30`) in the upper-right region of a screenshot,
  then segments individual digit glyphs by finding column gaps in that
  mask (digit bands are consistently ~45-55px wide at native res, vs.
  ~20-40px for the "COMBO" label's letters -- filter on width to tell
  them apart).
- Only **7 of the 105** screenshots are actually Mercenaries-mode
  frames with the combo HUD visible (the rest are other menus/
  cutscenes/inventory screens -- a naive blue-threshold on a desaturated
  grayscale menu can false-positive, e.g. `21690_...212145_1.png` and
  `21690_...212148_1.png` picked up unrelated white UI text; verify
  visually, don't trust the heuristic alone).
- Those 7 read combo `010` or `020` only, across genuinely varied
  backgrounds (dark interior, one overexposed/bright frame, a red-lit
  hallway) -- good real-footage coverage for digits **0, 1, 2**, but
  **zero coverage for 3, 5, 7**, which are exactly the digits that need
  replacing.
- Also fully segmented `COMBO_ORIGINAL_TEXTURE.png`'s digit row (a real
  `0123456789` bitmap-font strip at y=[95,155], see reproduction recipe)
  into 10 individual glyph crops -- genuine ground truth for every
  digit, usable as one sample among several once the multi-sample
  matching change lands, though (being a single static atlas crop, not
  footage) it doesn't by itself solve the background-diversity problem
  discussed in the prior entry.

**Asked the user how to proceed** given the gap: implement now using
the atlas for 3/5/7 (with real footage only for 0/1/2), or wait for more
screenshots reaching higher combos (13, 35, 57+) so every digit gets a
real varied-background sample before any code changes. **User chose to
wait.** Nothing implemented yet -- this is a data-collection pause, not
a technical blocker. When the user returns with more screenshots,
re-run the same extraction approach (recipe below) rather than
re-deriving it.

**Reproduction recipe** (scratchpad won't survive a new session):
```python
import cv2, numpy as np
img = cv2.imread(screenshot_path)  # native 1920x1080
region = img[100:280, 1000:1750]   # combo HUD search window
b, g, r = cv2.split(region.astype(np.int32))
mask = ((b > 120) & (b > r + 30)).astype(np.uint8) * 255
# column-sum the mask, band-split on gaps, keep bands >=45px wide
# (digits) vs narrower bands (COMBO label letters) -- see this
# session's DECISIONS.md entry above for the exact column-band logic.
```
For the atlas: `COMBO_ORIGINAL_TEXTURE.png` is RGBA
(`cv2.IMREAD_UNCHANGED`) -- composite alpha onto black to see the
glyphs (a plain `cv2.imread` drops alpha and shows an almost-blank
image). The big `0123456789` digit row lives at y=[95,155]; column
boundaries per digit (x0,x1): 0=[0,38], 1=[40,69], 2=[69,104],
3=[104,142], 4=[142,179], 5=[179,213], 6=[213,249], 7=[249,282],
8=[282,319], 9=[319,354].

### 2026-09-17 further follow-up: second screenshot batch closes the gap; combo color rule; architecture decided

User supplied a second zip, `resources/21690_20260917222148_1.zip` (159
more native screenshots). Re-ran the extraction with the blue-only
detector from the previous entry and initially still found no 5/7 --
but the user pointed out a screenshot with combo 57 that the detector
had missed entirely. Root cause: **the combo counter renders blue only
when its value is an exact multiple of 10 (10, 20, 30...); every other
value renders white** (confirmed by the user). The extraction script
only had a blue-pixel heuristic, so it silently missed the common case.

Fixed the detector to catch both (`(b>120 & b>r+30) | (b>150 & g>150 &
r>150 & |b-r|<40 & |g-r|<40)`), and had to also make the digit/label
column-width split adaptive (`>= 0.65 * max_band_width`, take the
leftmost contiguous run of such bands) rather than a fixed `>=45px`
threshold, because the white font's rendered stroke width differs from
the blue font's, so a fixed pixel cutoff that worked for one didn't
transfer to the other. This is a distinct lesson from every prior
digit-matching bug in this file: those were all about *misreading* a
rendered digit; this was about a whole **second valid rendering style**
(different color, different apparent glyph width) that a single-style
extraction heuristic simply never saw. Re-running with the adaptive
two-color detector found combo values spanning nearly the full 0-9
range per digit, including every previously-missing one (3, 5, 7),
across real footage with genuinely varied backgrounds.

**Architecture decided for the actual fix** (not yet implemented --
see HANDOFF.md "Update 2026-09-17 (later still)" for the full, current
plan so it doesn't need re-deriving in a new session):
`load_digit_templates` moves from one image per digit
(`dict[str, np.ndarray]`) to multiple sample images per digit
(`dict[str, list[np.ndarray]]`), backed by a directory-per-digit layout
(`templates/<set>/<digit>/<sample>.png`) rather than flat filenames
parsed by convention -- directories were chosen over a filename
convention like `0_a.png` as the less fragile option. `match_digit`
takes the max score across a digit's own samples before comparing
across digits, which is the actual mechanism that fixes the root cause:
a digit only needs to win with *any one* of several real-footage
samples, not with a single all-or-nothing template. This restructuring
necessarily touches all three template sets (`digits_combo`,
`digits_timer`, `digits_popup`) since they share `load_digit_templates`,
but only `digits_combo` gets new sample images -- timer/popup's single
existing templates just move into same-named subdirectories unchanged.
