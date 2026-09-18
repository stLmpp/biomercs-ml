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

## 2026-09-18 — Multi-sample architecture implemented; the fifth root
## cause's remaining case is accepted as a pixel-level limit, caught
## downstream instead

Implemented the architecture from the previous entry
(`load_digit_templates`/`match_digit` now take `dict[str, list[ndarray]]`,
directory-per-digit layout, max score across a digit's own samples wins
-- commit `85186fa`). Curating the actual sample images surfaced a
second, nested version of the same root cause:

- **First attempt (screenshots as templates) reproduced the original
  bug, one level deeper.** Cropped 0/3/5/7 samples from the user's
  native 1920x1080 Steam screenshots (crisp, uncompressed). Tested
  against the real bug frame (video 2, t=408.8s, "105 COMBO"): every
  screenshot-sourced sample scored *worse* than the original bad
  calibration-screenshot template (max ~0.45-0.55 vs. the real "9"
  confusion's 0.80+). Root cause: `cv2.matchTemplate`'s
  `TM_CCOEFF_NORMED` compares raw pixel intensities, so a crisp,
  uncompressed template correlates poorly against a frame that went
  through YouTube's H.264 compression -- the exact same
  clean-source-vs-compressed-target mismatch as the original bug, just
  with a different clean source. **Lesson: template samples must come
  from the same capture/compression pipeline as what they'll be
  matched against**, not just "real gameplay" in the abstract.
- **Fix: re-sourced 0/3/5/7 samples directly from the two
  already-downloaded YouTube videos** (real early-session combo climbs
  like "057", "053", "085", "034", "054", "027" naturally show every
  digit 0-9 at low combo values), keeping one calibration-frame sample
  (for compatibility with `sample_frame_01.png`-based fixtures/tests)
  and one Steam-screenshot sample (background diversity) as
  supplementary, not primary, sources.
- **The original adversarial frame (t=408.8s) still cannot be read
  correctly, and this is now an accepted limit, not an open bug.**
  Investigated three approaches in sequence, all against this exact
  frame's tens-digit crop (true "0"):
  1. Raw pixel matching with the new real-video-sourced "0" samples:
     best score 0.754, still loses to "9"'s 0.816.
  2. Binarizing both crop and template into black/white ink masks
     (using the same blue/white color heuristic the screenshot
     extraction script uses) before matching, to remove
     compression-blur as a confound: best "0" score 0.624, "9" still
     wins at 0.686.
  3. Topology (counting enclosed background regions/holes after tight
     ink-cropping, since this font's 0 has one full-height hole, 8 has
     two, 9 has one upper-half hole): unreliable at this resolution --
     compression noise both falsely closes real holes (the true "0"
     crop showed *zero* holes) and falsely splits others, making hole
     count as noisy as raw pixels.
  Visual inspection explains why: this specific frame is genuinely
  **overexposed** (bright sun/foliage lighting), and a "0"'s only
  distinguishing feature -- its dark hollow center -- is blown out to
  nearly the same brightness as the ring itself. The information needed
  to tell 0 from 9 was destroyed by lighting at capture time, before
  any code ever sees the frame. No template, preprocessing, or
  classifier can recover information that isn't in the source pixels.
  Confirmed this isn't a one-frame fluke: scanning every native-60fps
  frame across the full ~18s window this bug spans found the wrong
  reading dominant by roughly 980-to-44 over the correct one, so even
  much wider neighbor-frame voting (beyond the existing
  `SAMPLE_VOTE_FRAMES` burst) would not have rescued it.
- **Decision: accept the pixel-level loss for this class of frame, and
  catch its effect at `event_detector` instead** (see next entry). The
  regression test for this frame moved from asserting `read_combo`
  returns the correct value (impossible to guarantee) to asserting the
  resulting bogus kill-group gets discarded downstream regardless of
  what the digit reader returns for it
  (`test_detect_kill_groups_drops_a_real_overexposed_frames_misread`).

## 2026-09-18 — event_detector domain-knowledge safeguards (group-size
## ceiling, reversion check, rarity-scaled confidence)

Three independent checks added to `event_detector.detect_kill_groups`
(commit `dbf7231`), all from the author's own top-level competitive
Mercenaries experience, layered on top of (not instead of) the
digit-matching fix above -- because some misreads (like the overexposed
frame) genuinely cannot be fixed at the pixel level:

- **`MAX_PLAUSIBLE_GROUP_SIZE`: 20 -> 8.** The old value's reasoning
  ("the enemy pool is a few hundred, so 100 is impossible") was too
  loose to be useful -- it let real bugs like `n_bullet=19` and
  `n_bullet=9` through untouched. Per the user: 8 simultaneous kills is
  roughly a one-in-a-million event (rare, but has genuinely happened);
  anything above that is not a plausible real group. Considered keeping
  a looser cap and relying only on the reversion check below -- rejected
  because the reversion check requires a later sample to expose the
  problem, while an implausible size is self-evidently wrong from a
  single pair of samples alone, no lookahead needed.
- **Reversion check: a combo rise that reverts to at or below its
  pre-rise value within `COMBO_REVERSION_CHECK_WINDOW_S` (6.0s) is
  discarded.** The combo counter only ever increases during a session
  (a rare genuine reset drops toward zero; it never dips by a small
  amount and climbs back to exactly its pre-rise value). Real footage
  (the four original `n_bullet=10` phantom groups) showed exactly this
  pattern: e.g. `184,184,184,194,184,184` with the timer never
  changing. This generalizes the existing transient-dip check (which
  only looks one sample *back*) to also look *forward* -- needed
  because DECISIONS.md's earlier-rejected "symmetric persistence check"
  proposal only looked at the immediate next tick, but real footage
  showed the revert sample landing up to ~4s later, past several
  intervening ticks. The search scope matches the pickup-search
  precedent (searches `all_samples`, not just the current session's),
  since the same chaotic misread stretches that produce this pattern
  also fragment sessions.
- **`GROUP_SIZE_CONFIDENCE_FACTOR`: reported group confidence is now
  multiplied by a per-group-size rarity prior** (1.0 for size 1-3, down
  to 0.15 at size 8), rather than added as a new hard gate. `KillGroup.
  confidence` was already purely informational (shown during manual
  review, never auto-filtered anywhere in the pipeline), so sharpening
  that existing signal was lower-risk than introducing new filtering
  logic. Values are the user's own judgment call translating rarity
  words (ok/possible/rare/very rare/one-in-a-million) into numbers, not
  derived from data.

**Combined result:** video 2 (the phantom-group video) went from 46
clips to 17, with the four originally-flagged phantom `n_bullet=10`
groups completely gone from the timeline. Video 1 went from 40 clips to
17. `bonus_kill` is now the dominant label on both (11/17 and 9/17
respectively), consistent with the Wesker dash-finisher meta instead of
contradicting it.

## 2026-09-18 — Re-review surfaces a second, distinct bug: `n_bullet` is
## fabricated, not just occasionally miscounted

Manually reviewed all 17 of video 2's post-fix clips (methodology: full
review, not a sample, since the set is now small enough). Result: only
**52.9% agreement (9/17)** -- **`bonus_kill` 9/9 correct, `bullet_kill`
0/4 correct, `mixed` 1/4 correct.** This is nearly the identical
per-category pattern the previous session found *before* any of this
session's fixes (`bonus_kill` 15/16, `bullet_kill` 1/9, `mixed` 0/5) --
today's fixes cut total clip *count* substantially but did not touch
whatever is actually mislabeling `bullet_kill`/`mixed` events. That bug
lives elsewhere.

**The review process itself was upgraded first** to capture *what the
label should have been*, not just whether it was wrong (see
`review.parse_review_answer`, `dataset_manifest.
review_true_n_bonus`/`review_true_n_bullet` columns, `fetch_reviewed_
incorrect`, and `scripts/review_sample.py <db> wrong` to re-review only
previously-wrong clips). Typing `<bonus>/<bullet>` (e.g. `1/2`) during
review now records the actual counts the reviewer saw, not just a
correct/incorrect flag.

Re-reviewing all 8 wrong video-2 clips with this new capability gave a
striking, uniform result -- **every single one had a true `n_bullet` of
0.** All eight were pure `bonus_kill` events that the pipeline split
into a bogus bonus/bullet mix (or pure `bullet_kill`):

```
id | detected (bonus,bullet) | actual (bonus,bullet) | timestamp
 1 | (1,1)                   | (1,0)                  | 37.0
 4 | (1,6)                   | (1,0)                  | 69.0
 5 | (0,2)                   | (2,0)                  | 122.0
 6 | (0,4)                   | (1,0)                  | 181.2
 8 | (0,1)                   | (1,0)                  | 193.0
10 | (0,6)                   | (2,0)                  | 492.4
11 | (1,4)                   | (1,0)                  | 522.0
15 | (1,6)                   | (1,0)                  | 549.2
```

Since `auto_labeler.label_kill_group` computes `n_bullet =
group.group_size - n_bonus` (a pure remainder, never independently
verified), a true `n_bullet` of 0 in every case means the bug is
upstream of labeling, in either (or both) of: `group_size` (the combo
delta computed by `event_detector`) being inflated beyond the real kill
count, or `n_bonus` (the timer-delta-derived count) being undercounted
because the timer read didn't register a real bonus jump. Re-checked
the mechanics doc (`docs/knowledge_base/mercenaries-mechanics.md`) to
rule out a scaling-assumption bug first -- confirmed each bonus kill
really does add a full independent +5s (not diluted across a
simultaneous group), so `auto_labeler`'s `n_bonus = round(bonus_seconds
/ 5.0)` math itself is correct; the bad inputs feeding it are the
problem, not the formula.

**Traced raw per-tick `HudSample`s around all 8 events (video 2) and
found something more severe than expected, not yet root-caused:**
- **Timer readings are badly unstable in these specific windows**,
  independent of the combo bug this session already fixed: e.g. around
  t=181s one tick reads `timer=2660.0` and another nearby window (t=
  520s) reads `timer=2889.0` -- four-digit garbage values, not just a
  wrong digit within a plausible range.
- **`session_id` increments on nearly every tick** in these windows
  (e.g. 79->80->81 within 2 seconds at t=179-182s; 237->238->239 within
  2 seconds at t=490-494s) -- `is_new_session`'s timer-jump/drop
  detection is firing constantly because the timer readings themselves
  are too noisy in these stretches, fragmenting what's very likely one
  continuous fast-kill sequence into many spurious single-tick
  "sessions." This directly undermines `detect_kill_groups`, which only
  ever compares *adjacent* samples within what it's told is one
  session.
- **A likely new, distinct combo-digit confusion, separate from the
  0-vs-8/9 case fixed this session:** clip id=1 (t=37.0) detected combo
  `884 -> 886` (group_size 2) where the real group_size was 1 (884 ->
  885) -- consistent with a "5" ones-digit misread as "6", not yet
  investigated the way 0-vs-8/9 was.
- All 8 events cluster in fast, chaotic combat moments (rapid
  consecutive kills, likely screen-flash/particle effects), the same
  kind of footage that has produced the majority of hard bugs this
  project has found so far (per `test_read_digit_slots_does_not_bleed_
  into_a_neighboring_slots_ink`'s 149-combo case and others).

**Not yet root-caused.** Deliberately stopped here to log findings
rather than start a new multi-session investigation immediately -- see
HANDOFF.md for the reproduction recipe and concrete next steps.

## 2026-09-18 (later) — Frame-by-frame tracing of the 8 wrong video-2
## clips finds THREE distinct root causes, not one

Followed the previous entry's "start here" pointer: traced clip id=8
(t=193.0, detected `(0,1)` vs actual `(1,0)`, group_size already
correct at 1) frame-by-frame at native 60fps (not just the 0.2s
sampling grid) using `hud_reader.read_timer`/`read_combo` directly.
Result was clean and conclusive, and tracing two more of the eight
wrong clips this way surfaced two further, independent bugs. All three
are real, evidenced, and none is the "session fragmentation" story the
previous entry speculated as the likely single cause -- that
speculation was wrong, or at best only one contributor among three.

**Bug A -- the combo counter animates for ~350ms after a kill; the
timer changes in a single frame. `detect_kill_groups`'s core
assumption (a kill's combo delta and timer delta land in the same
adjacent-sample-pair) is false whenever the two are more than one
sample tick apart.** Confirmed on id=8 at frame granularity: the timer
jumps instantly 262->267 at frame 11557 (t=192.617). The combo digits
enter a visible roll/pop animation at the same frame, rendering a
sequence of transient values over the next ~21 frames (`None, None, 0,
0, 10, 10, 40, 40, ...`) before settling on the true 849 at frame
11578 (t=192.967) -- a real on-screen animation, not compression
noise (values like `10`/`40` are plausible odometer-style intermediate
frames, not the digit-confusion pairs seen elsewhere in this file). The
0.2s sampling grid's tick at t=192.6 lands one frame after the timer's
jump but before the combo animation starts, so that tick reads
`timer=267, combo=848` (stale combo). The next tick at t=193.0 is where
the combo animation has settled, reading `timer=267, combo=849` (timer
unchanged since the previous tick, because it only ticks down once per
real second and 0.4s hasn't elapsed). `detect_kill_groups` pairs these
two ticks, sees a correct `group_size=1` but a *zero* timer delta,
and hands `auto_labeler` a `bonus_kill` that looks like a pure
`bullet_kill` -- exactly id=8's `(0,1)` vs `(1,0)` mismatch. This
generalizes to any case where `timer_before_s == timer_after_s` despite
a real bonus kill (also seen at id=10, t=492.4, before bug C below is
even considered).

**Bug B -- persistent (not transient) high-confidence digit misreads
during chaotic combat, on digit pairs beyond the already-fixed "0 vs
8/9".** Frame-by-frame trace of id=6 (t=181.2, detected group_size=4,
`timer_before_s=259 > timer_after_s=258` -- a *decreasing* timer
supposedly co-occurring with a kill, itself a red flag) shows the
combo's hundreds digit flickering between "8" and "9" and its ones
digit flickering among "5"/"6"/"9" for nearly a full second
(t=180.8-181.7s) at confidence 0.75-0.83 -- comfortably over
`DIGIT_MATCH_MIN_CONFIDENCE` -- while the true value (845) never
actually changes and the timer counts down normally with no bonus.
Unlike the already-fixed fifth root cause (a data-quality problem
in the "0" template specifically) or bug A above (an animation, over
in ~350ms), this is a *sustained*, multi-tick, high-confidence
misread under what's visibly motion-blur/particle-heavy footage --
same chaotic-combat class noted in every hard bug this project has
found, but not yet template-fixed for this digit pair.

**Bug C -- a session split defeats the existing transient-misread
persistence guard, because the guard only ever looks at
`session_samples[i-1]` (the previous sample *within the same
session_id*).** Traced id=10 (t=492.4): at t=491.8 (still session 238)
combo is a stable, correct 187. A timer misread (`488 -> 482`, a
6-second drop) triggers `is_new_session` and starts session 239. That
new session's *first* sample (t=492.2) reads `combo=181` -- itself a
transient misread, since the very next sample (t=492.4, still session
239) reads the correct 187 again, with no real kill in between. This
is exactly the kind of dip the existing "transient-dip" guard in
`detect_kill_groups` (`session_samples[i-1].combo_value >= curr.
combo_value`) was built to catch -- but that guard requires `i > 0`,
and this misread landed at `i=0` of a newly-split session, so there is
no `session_samples[-1]` to check against. The `181 -> 187` "rise" is
then reported as a fabricated `group_size=6` kill group. This is a
structural gap, not a tuning issue: *any* misread severe enough to
trigger a spurious session split will, by construction, land at index
0 of the new session and automatically evade the i>0-only guard,
regardless of how good the guard's threshold is.

**Not yet decided how to fix any of these -- three different problems,
three different candidate fixes, needs the user's steer on scope/order
before implementing anything:**
- Bug A points at `event_detector`/`auto_labeler` needing to look
  beyond a single adjacent-sample pair for the timer delta (e.g. search
  a short forward/backward window around the combo-rise tick for the
  timer's own delta, mirroring how the reversion/pickup checks already
  search a window instead of one tick).
- Bug B needs the same template-curation treatment as the fifth root
  cause (more/better real-footage samples for the "8"/"9" hundreds
  digit and the "5"/"6"/"9" ones digit under motion blur), not a
  logic change.
- Bug C needs the transient-dip guard to look at the *global* sample
  sequence (like the pickup and reversion checks already do via
  `all_samples`) instead of `session_samples[i-1]`, so it isn't blind
  at session boundaries.
None of the three explains 100% of the 8 wrong clips alone -- worth
re-classifying all 8 (and video 1, still unreviewed with the
correction-capable script) against these three buckets before deciding
what to implement first, rather than assuming they're evenly split.

## 2026-09-18 (later still) — Bug C fixed: transient-dip guard now
## looks across session boundaries

User picked Bug C to fix first (smallest, most self-contained of the
three, TDD-able directly against the real id=10 case). Root cause was
exactly as diagnosed above: the guard compared `curr` against
`session_samples[i - 1]`, which only exists for `i > 0`. Fixed by
introducing `_preceding_combo_value(all_samples, timestamp_s)` -- finds
the combo value of the chronologically-nearest sample strictly before a
given timestamp across the *full* sample list (like the existing
pickup/reversion checks already do), not just within the current
session's own list -- and using that in place of
`session_samples[i - 1]`.

- Considered: special-casing `i == 0` to look up the last sample of
  the previous session_id specifically (rejected -- more code, and
  redundant: since a session's samples are always a contiguous
  chronological block of `all_samples` by construction, "nearest
  sample strictly before `prev.timestamp_s`, globally" is *exactly*
  equal to `session_samples[i - 1]` whenever `i > 0` anyway, so one
  general helper replaces the special case instead of sitting next to
  it).
- Falls back to the old i>0-only behavior automatically when a caller
  doesn't pass `all_samples` (defaults to `session_samples`, so with no
  broader context there's nothing before session_samples[0] to find).
- Verified against real footage: re-ran `detect_kill_groups` over all
  of video 2's cached real samples before and after the fix and diffed
  the two full group lists. Exactly one group was removed --
  `(session=239, t=492.4, group_size=6)`, the exact phantom this fix
  targeted -- and nothing else changed, confirming the fix is
  surgical, not just passing its own unit tests.
- Two new tests in `test_event_detector.py`: one reproducing the real
  id=10 dip-at-a-session-boundary pattern (must be dropped), one
  proving a genuine rise at the start of a new session is still kept
  when the prior session's last value is genuinely lower (must not
  regress into over-dropping every session's first group).

Bugs A and B (combo-animation/instant-timer desync, and the
sustained 8-vs-9/5-vs-6-vs-9 digit misread under chaotic footage) are
still open -- see the previous entry.

## 2026-09-18 (later still) — Re-ran the fixed pipeline, re-reviewed;
## classified the remaining wrong clips, found a fourth distinct pattern

Regenerated video 2's manifest with Bug C's fix in place and did a
full manual review. **Caveat that cost real review time:** the output
directory (`/tmp/biomercs-run2`) had leftover rows from a 2026-09-16
session that were never cleared, so the first review pass mixed 51
stale rows with 16 fresh ones -- always `rm -rf` the output dir (or use
a new one) before re-running the pipeline in an existing session, ephemeral
`/tmp` guidance notwithstanding (it only reliably clears between
*sessions*, not within one). Filtering to just the fresh
(`created_at`-dated 2026-09-18) rows: **16 clips, 9/16 correct (56%)**.
The `t=492.4` phantom group Bug C targeted is confirmed gone. All 7
remaining wrong clips are the same 7 (of the original 8) that Bug C
was never expected to fix, every one still showing `review_true_
n_bullet=0` (a true pure `bonus_kill` split into a bogus mix).

Frame-by-frame traced the 5 of those 7 not already classified (id=8's
t=193.0 was already Bug A; id=6's t=181.2 was already Bug B). Result:
**neither Bug A nor Bug B alone explains the rest -- there's a fourth,
distinct pattern.**

- **t=37.0 and t=69.0: a variant of Bug B.** In both, the timer's own
  bump lands correctly within the same adjacent-sample pair (ruling out
  Bug A), but the combo's ones digit settles into a *sustained*,
  high-confidence wrong reading for 2+ seconds afterward ("5"
  misread as "6" at t=37.0; true ones-digit "2" misread as "8" at
  t=69.0). At t=37.0 specifically, native-frame tracing shows the
  correct value (`885`) actually renders for exactly one frame right
  as the counter's pop animation finishes (frame 2218, t=36.967)
  before immediately flipping to the sustained wrong `886` for every
  frame after -- i.e. the misread isn't random chaotic-footage noise
  like the t=181.2 case, it kicks in at the exact moment the animation
  settles and then persists. Worth keeping in mind if Bug B's fix ends
  up being template curation: samples right after an animation settle
  may be a specific hard case worth its own template coverage, not
  just "more real footage" in general.
- **t=122.0: an extreme version of Bug A.** Two near-simultaneous
  bonus kills land as a real `+9s` timer jump (`180->189`) at
  t=119.8-120.2, but the combo counter's visible update doesn't settle
  until t=121.0-122.0 -- a ~1.8-2s lag, roughly 5-6x longer than the
  ~350ms lag measured for the single-kill case at t=193.0 (id=8).
  Whatever fix Bug A gets needs a search window sized for multi-kill
  chains, not just a single sample tick or two.
- **t=522.0: a new, fourth pattern -- rapid, unsettled frame-to-frame
  flicker that the existing 3-frame majority vote is too short to
  filter.** Native-frame trace (t=521.7-522.5) shows the combo's ones
  digit flickering among at least 5 different values (`185, 189, 195,
  196, 199, 186`) essentially every frame, with no dominant "wrong"
  reading the way t=181.2 or t=37.0 have -- and critically, the *true*
  value (`185`) is actually one of the more common individual-frame
  readings across the whole window, just not the plurality within the
  specific 3-frame window `sample_video`'s burst happened to land on
  for this tick. This isn't Bug B (no single stable wrong value to
  fix templates against) and isn't Bug A (no animation-style
  unreadable gap, no clean before/after settle) -- it's closer to the
  original transient-misread problem `SAMPLE_VOTE_FRAMES=3` was built
  to solve, just under noise heavy enough that a 3-frame window isn't
  wide enough. **Not yet named "Bug D" formally or scoped -- needs the
  user's read on whether this is worth solving separately (e.g. a
  wider vote burst, at the cost of more decode work per tick) or is
  rare/rare-adjacent enough to accept.**
- **t=549.2: likely the same flicker pattern as t=522.0**, over a
  longer, messier window (values `141/148/143/149` recurring across
  ~4s with a mid-window sample gap, probably the kill-bonus popup
  itself interfering with `is_valid_hud_frame`) -- not independently
  frame-traced this session, inferred from the 0.2s-grid pattern
  looking structurally the same as t=522.0's confirmed case.

**Updated tally across all 8 originally-wrong video 2 clips:** 1 fixed
by Bug C (t=492.4), 2 are Bug A (t=193.0 confirmed, t=122.0 an extreme
variant), 3 are Bug B or a Bug-B variant (t=181.2, t=37.0, t=69.0), 2
are the new flicker pattern (t=522.0 confirmed, t=549.2 inferred). No
single fix covers the majority -- all three (or four) real causes need
addressing to get video 2 close to the spec's >98% target.

## 2026-09-18 (later still) — Bug D fixed (widened majority vote);
## then a much bigger finding: most combo digits still have only one
## template sample, and the game has a hard combo ceiling we weren't
## enforcing

**Bug D fixed first, as planned:** widened `SAMPLE_VOTE_FRAMES` from 3
to 11. TDD'd against the real t=522.0 per-frame sequence (see
`test_sample_video_widens_the_vote_when_a_short_burst_picks_the_wrong_
majority`); 11 is the minimum burst size that flips that real case's
majority to the true value. This required regenerating
`tests/fixtures/synthetic_static.mp4` at 60fps (it was 30fps, too low
for an 11-frame burst to fit within one 0.2s sampling tick without
overrunning into the next) -- real production footage is already
60fps, so this also makes the fixture more representative, not just a
technical workaround.

**Verifying Bug D's fix led to a much bigger finding.** Checking the
real t=549.2 case (originally guessed to be the same flicker pattern
as t=522.0) with the new 11-frame vote showed the vote settling
*consistently* on `148` across 5+ seconds -- not flicker at all, so
the earlier "likely the same pattern" guess in the previous entry was
wrong; t=549.2 is actually a Bug-B-style sustained ones-digit "2 read
as 8" misread (same confusion pair independently found at t=69.0).

While investigating, **the user pointed out that a combo value like
185 is physically impossible in RE5 Mercenaries** -- the enemy pool is
fixed at a maximum of 150, so the combo counter can never exceed that
(see the new "Combo counter maximum" entry in
`docs/knowledge_base/mercenaries-mechanics.md`). This is a domain fact
the pipeline never enforced, and checking it against real footage
exposed something much worse than any of Bugs A-D: at t=124.0s (a
completely clean, unoccluded, non-chaotic frame -- Wesker standing
still) the combo plainly reads **"029 COMBO"**, but
`hud_reader.read_combo` confidently (0.80) misreads it as **"889"**.
Dumping per-digit match scores for that frame showed why:
`load_digit_templates(COMBO_DIGITS_DIR)` reports only **1 sample each**
for digits `1, 2, 4, 6, 8, 9` -- the original multi-sample
architecture decision (2026-09-17 entries above) explicitly said to
curate new samples "uniformly across all ten digits, not special-cased
to the four broken ones," but in practice only `0/3/5/7` (the digits
originally proven bad) ever got curated. The single old "8" sample
apparently over-matches broadly (won or nearly won every slot in the
t=124.0 scores, including slots whose true digit was "0" and "2"), and
digit "2"'s single sample scored *worst of all ten digits* even
against its own true crop -- a strong sign that sample itself is a bad
template, the same class of problem as the original "0" root cause,
just never caught because 1/2/4/6/8/9 were assumed fine after the
four-digit fix landed.

**This means a meaningful fraction of this session's Bug
A/B/C/D-classified "wrong" clips were likely misclassified** -- what
looked like "chaotic footage causing sustained digit confusion" (Bug
B) may often just be this same single-bad-sample problem showing up on
ordinary, non-chaotic frames. The classifications aren't being thrown
out, but should be treated as provisional until re-checked after
proper multi-sample curation for the remaining six digits.

**Fixed immediately (TDD, real-footage fixture):**
`config.MAX_PLAUSIBLE_COMBO_VALUE = 150`; `hud_reader.read_combo` now
returns `None` (matching the existing invalid-reading convention)
whenever the three-digit value exceeds it, regardless of confidence.
New fixture `tests/fixtures/frames/combo_029_misread_as_889_frame.png`
(the real t=124.0 frame) proves this. As a side effect, this cap also
now catches the fifth root cause's previously-accepted-as-permanent
overexposed-frame case (t=408.8s, misread `105 -> 195`, and 195 > 150)
two layers earlier than the `event_detector` safeguards that were
built to catch it -- `test_detect_kill_groups_drops_a_real_
overexposed_frames_misread` was updated to hardcode a misread value
instead of deriving it from that fixture (since `read_combo` no longer
returns the misread for that frame at all), keeping the downstream
defense-in-depth test meaningful on its own.

**Not yet done:** extend the multi-sample template curation to
`1, 2, 4, 6, 8, 9` the same way `0/3/5/7` were done -- both
`resources/Steam Screenshots.zip` and
`resources/21690_20260917222148_1.zip` (both still on disk, gitignored)
plus the original-texture atlases inside them are still available, so
this doesn't need new material from the user, just re-running the
already-documented extraction recipe (see the "2026-09-17 follow-up"
and "further follow-up" entries above) for the six under-curated
digits. This is very likely the highest-leverage remaining fix in the
whole project at this point -- worth doing before trusting any further
Bug A/B/C/D classification work.

## 2026-09-18 (later still) — Extended multi-sample curation to the
## six under-curated digits; real but partial improvement, diminishing
## returns without more source material

Scanned both already-downloaded YouTube videos (not the screenshot
zips -- see below for why) for real, low-combo frames covering digits
`1, 2, 4, 6, 8, 9`, visually verified each candidate against the
actual frame before accepting it (several of `read_combo`'s own
"low-confidence-looking-plausible" readings during the search turned
out to themselves be misreads, e.g. a frame the old code would've
called `120` was actually `129`; `104` was actually `134`) -- a
reminder that even a value under 150 isn't automatically trustworthy,
just plausible. Added real-footage samples: `1` (+2), `2` (+3), `4`
(+1), `6` (+1), `9` (+1). **No real-footage "8" occurrence was found
in either full video** even at a very low confidence threshold (0.55)
-- "8" genuinely seems rare in the sampled stretches, or is
compensated for as some other misread wherever it does appear.
Fell back to one supplementary sample cropped from
`COMBO_ORIGINAL_TEXTURE.png` (the atlas, same as the earlier 0/3/5/7
work used as one-of-several) for `8` only.

**Why videos, not the crisp screenshot zips, as the primary source
again:** same lesson as the 2026-09-18 "second, nested version"
entry above -- template samples must come from the same
capture/compression pipeline as what they're matched against, and
crisp 1920x1080 screenshots don't.

**Verified real, if partial, improvement:** an independent (not used
as a template source) frame at video 2 t=409.2s reads a correct
`106` post-curation (both the "1" and "6" digits right). But another
independent frame (video 1, t=252.4s, true value `064`) still
misreads its tens digit ("6" read as "0") -- with only 2 samples for
`6` (vs. 4-5 for the fully-curated `0/3/5/7`), coverage is thinner and
not yet as robust. The original adversarial frame that surfaced this
whole finding (t=124.0s, true `029`) **still misreads as `889`** even
with the new samples added -- the new `0`/`2` samples score *worse*
against this specific frame than the existing ones already did, so
the per-digit max never changes. This may be the same class of
one-off "accepted pixel-level limit" as the t=408.8s overexposed frame
from the fifth root cause, or may just need yet more sample diversity
-- not conclusively determined either way. Either way it's caught
downstream by `MAX_PLAUSIBLE_COMBO_VALUE` regardless of the raw match.

**Stopping here rather than continuing to hunt for more samples**:
diminishing returns without new source material (both zips are now
fully mined for this video pair's low-combo stretches), and the
existing safety nets (`MAX_PLAUSIBLE_COMBO_VALUE`, the group-size cap,
the reversion check) already catch what curation alone couldn't fix
this round. **Next step: re-run the pipeline on both videos and
re-review from scratch** -- that's the real test of how much all of
this session's fixes (Bug C, Bug D, the combo cap, and this partial
curation) moved the needle together, rather than continuing to
chase individual frames in isolation.

## 2026-09-18 (performance track, #6) — Parallelized `sample_video`
## across CPU cores; ~4.3x real speedup, output verified identical to
## the sequential path

Implemented the design agreed in-chat (see HANDOFF.md for the full
agreed design, kept there rather than duplicated here): split
`sample_video` into a worker function, `_sample_range(video_path,
templates..., offset, fps, frame_interval, duration_s, start_frame_idx,
end_frame_idx)`, and an orchestrator. Each worker opens its own
`cv2.VideoCapture`, seeks to its own start frame, and does the
existing per-tick logic (validity check, burst read, majority vote)
for its range, returning a new `RawHudSample` (timestamp, timer,
combo, confidence, popup -- no `session_id`). `sample_video` runs
calibration once, dispatches chunks via `ProcessPoolExecutor` (or
calls `_sample_range` directly in-process when `max_workers=1`, no
subprocess spawn at all), concatenates results in chunk-submission
order (not completion order), then runs the `is_new_session`/
`last_timer_value` bookkeeping pass once, sequentially, over the
merged list -- exactly like the original single-pass loop did.

**Why `max_workers=1` skips `ProcessPoolExecutor` entirely, not just
defaults to one worker:** most of the existing test suite mocks
`hud_reader.read_timer`/`read_combo`/etc. via `unittest.mock.patch` in
the test process. Those patches don't apply inside a real subprocess,
so a literal "always go through the executor, just with 1 worker"
implementation would've silently broken every mocking-based test. All
7 existing `sample_video(...)` call sites in
`test_hud_reader_video.py` now explicitly pass `max_workers=1` for
this reason.

**New tests, not mocked, run against the real digit-matching code
path:**
- `test_sample_range_chunking_produces_same_raw_samples_as_one_full_range`
  calls `_sample_range` directly with one full range vs. two adjacent
  sub-ranges on the real `synthetic_static.mp4` fixture and asserts the
  concatenated result is identical -- proves chunk boundaries (aligned
  to tick multiples, i.e. frame-index multiples of `frame_interval`)
  never need a neighboring chunk's frames for a burst read.
- `test_sample_video_parallel_matches_sequential_output` runs
  `sample_video` end-to-end with `max_workers=1` vs `max_workers=2` on
  the same fixture (5 ticks total, so `max_workers=2` genuinely
  exercises 2 non-empty chunks through a real `ProcessPoolExecutor`,
  not a no-op) and asserts the full `HudSample` lists match exactly.

**Verified against real downloaded footage this session** (video 1,
`/tmp/biomercs-footage/source.mp4`, still on disk from a prior
session -- not re-downloaded):
- A real 30s clip (`ffmpeg`-trimmed from video 1 at t=60s, not
  synthetic) sampled with `max_workers=1` vs `max_workers=8`:
  **identical output** (`seq == par`), 25.88s -> 7.65s (3.4x).
- A full `pipeline.run` on the entire video (10 cores available on
  this machine, default `max_workers=os.cpu_count()`): **115.2s**,
  down from the ~500s baseline this profiling track started from
  (`hud_reader.sample_video`'s own docstring/handoff note) --
  **~4.3x real end-to-end speedup**. Didn't re-run the full sequential
  path a second time for a byte-for-byte full-video diff (would cost
  another ~8-9 minutes for marginal additional confidence beyond the
  real-footage 30s clip's exact-match result); the 30s real-clip test
  above plus this run completing cleanly with a plausible clip count
  is the verification bar this session judged sufficient.
- Clip count on this run was lower than earlier sessions' historical
  "17" figures for video 1 -- expected and unrelated to
  parallelization: those older counts predate this session's starting
  point (Bug C, Bug D, the combo cap, and partial digit curation were
  already landed before this session began). Not a regression signal;
  the paused accuracy thread (Bug A, the phantom-event pattern) is
  still the open item, untouched by this change.

**Not done, deliberately out of scope for #6:** re-timed and
re-verified only; did not touch the paused accuracy investigation
(Bug A, the new phantom-event pattern) -- see HANDOFF.md for why and
what's next there.

## 2026-09-18 (accuracy, resumed) — Phantom-event pattern root-caused
## (not fixed, folds into Bug B); Bug A fixed via a timer-delta search
## window, with a contamination guard found and fixed by real-footage
## A/B testing

**Phantom-event pattern (video 1, id=1, t=62.2) root-caused, not a new
bug.** Frame-traced at native resolution: ground truth combo sits at
`012` for the entire 58.4s-65.4s window -- no kill happens near t=62.2
at all. Two compounding, already-catalogued causes, not a new
mechanism:
1. A mossy rock wall directly behind the (semi-transparent) combo
   counter in this camera framing bleeds into the `DIGIT_SEARCH_MARGIN_PX`
   crop for slots 0 and 2, and `cv2.matchTemplate`'s max-score search
   occasionally prefers "8" over the true "0"/"2" -- confidence
   0.62-0.75, past `DIGIT_MATCH_MIN_CONFIDENCE` but under the ~0.889
   real-footage median. Sustained across several ticks (same wrong "18"
   recurs), not transient -- this is **Bug B** (persistent high-confidence
   misread under chaotic footage), just triggered by a static busy
   background instead of motion blur/particles.
2. Timer noise in the same window (`186->184->188->183->188->None->187...`
   tick to tick) fires `is_new_session` repeatedly, fragmenting what
   should be one session into many 1-tick sessions -- the
   previously-flagged-but-never-fixed "session_id increments on nearly
   every tick" issue from two sessions ago. It isolates the misread tick
   from the correctly-read `012` samples right next to it, so the
   reversion guard's lookback has nothing valid nearby to catch it
   against.

Bug B's known fix (template curation) was already tried once this
project with diminishing returns, and this instance (arbitrary game
background, not a fixed HUD neighbor) has no fixed midpoint to clamp
against like the earlier neighbor-bleed fix did. **Treated as a rare
residual case, not worth chasing right now** -- still present in this
session's final video 1 clip list (`t=62.2`, low confidence 0.465).
The timer-noise session-fragmentation piece is a separate, purely
timer-based issue and might be the better-leveraged fix if revisited,
since it's unrelated to any digit template quality.

**Bug A fixed.** Root cause confirmed exactly as diagnosed two sessions
ago (id=8, t=193.0): the timer jumps in a single frame but the combo
counter's roll/pop animation takes ~350ms (up to ~2s for a fast
multi-kill chain, see t=122.0) to settle, so the sample pair
`detect_kill_groups` picks based on where *combo* stabilizes often
isn't the same pair where the *timer's own jump* landed -- making a
real bonus kill's timer delta read as ~0.

Fix: `event_detector._timer_before`/`_timer_after` search a window
(`config.TIMER_DELTA_SEARCH_WINDOW_S = 3.0`, sized past the ~2s
worst-case lag) before `prev` and after `curr` respectively, for the
timer's true pre-/post-kill value, decay-adjusting every candidate to a
common reference point (`sample.timer_value_s + (sample.timestamp_s -
reference_ts)`) so readings from different ticks become directly
comparable. `_timer_before` takes the minimum decay-adjusted value
(the reading the jump hasn't reached yet); `_timer_after` takes the
maximum (the reading that has already caught up). With only prev/curr
in range this reduces to exactly the old `prev.timer_value_s`/
`curr.timer_value_s` behavior -- verified algebraically and by the
full existing test suite passing unmodified. Two new tests reproduce
the real single-kill (id=8) and multi-kill (t=122.0) lag patterns
directly with synthetic samples.

**A/B tested against real footage before trusting it (not just unit
tests) -- this surfaced a second, real bug the design didn't
anticipate:** stashed the fix, re-ran video 2's full pipeline for a
clean baseline (7 clips), restored the fix, re-ran again (4 clips) --
diffing found 2 clips correctly improved (`bullet_kill` -> `mixed`,
now correctly attributing some bonus kills) but **3 clips vanished
entirely.** Traced all three to the same cause: the timer-delta window
has no plausibility cap of its own (unlike combo's
`MAX_PLAUSIBLE_COMBO_VALUE`), so a wild misread elsewhere in the window
(e.g. `5227.0` or `257.0` next to a cluster of legitimate ~500s
readings, from the same kind of extreme timer noise the "second,
distinct bug" investigation flagged two sessions ago) could win the
min/max and produce an implausible delta that then fails
`auto_labeler`'s tolerance check -- fails safe (drops the clip) rather
than mislabeling, but real, unintended data loss.

**Fixed:** bound window candidates by
`_MAX_PLAUSIBLE_TIMER_SWING_S = config.MAX_PLAUSIBLE_GROUP_SIZE * 5 +
config.TIMER_DELTA_SEARCH_WINDOW_S` (the largest bonus any real group
could plausibly contribute, plus decay slack for the window itself) --
a candidate whose raw timer value is further from `prev`/`curr`'s own
value than that is excluded before the min/max runs. Uses only an
already-trusted existing constant, no new domain fact needed. New test
(`test_detect_kill_groups_ignores_an_implausible_timer_misread_inside_the_search_window`)
reproduces the exact real pattern (a `257.0` outlier next to a `496.0`/
`500.0` cluster) directly. Re-ran the video 2 A/B a third time with the
guard in place: the `t=549.0` clip came back (now `mixed(bonus=2,
bullet=5)`, previously `mixed(bonus=1, bullet=6)` in the un-windowed
baseline); two clips (`t=451.8`, `t=575.2`) are still dropped --
traced `t=451.8` specifically and confirmed the whole surrounding
window is chaotic enough (timer bouncing across a ~150s range within a
few ticks, session id incrementing almost every tick) that even
non-extreme nearby readings are themselves noise the swing bound
doesn't catch -- judged this the correct, honest outcome (drop an
unrecoverable read rather than guess) rather than a residual bug,
consistent with this project's established "safe to skip rather than
mislabel" pattern everywhere else.

**Verified on all three videos this session** (fresh manifests, all
fixes -- #6, Bug A, the contamination guard -- in place): video 1 down
to 4 clips (the t=62.2 phantom/Bug-B case still present as expected,
untouched by this fix), video 2 at 5 clips, video 3 at 1 clip. **Not
yet manually re-reviewed** -- clip counts and label composition changed
substantially enough (video 2: 7 -> 5 clips, several label changes)
that a fresh manual review pass is the real test of whether this
actually moved agreement, not just clip counts. See HANDOFF.md.

## 2026-09-18 (accuracy, resumed further) — Manual review of all 10
## post-Bug-A clips: 3/10 correct; found the real dominant bug is
## `group_size` overestimation, not anything Bug A touches. Also split
## the group-size confidence discount by bonus/bullet count.

**Manually reviewed all 10 clips across all three videos**
(`scripts/review_sample.py`) with Bug A and the contamination guard in
place. **3/10 correct (30%)** -- not better than session-start baseline
in raw agreement, but the *pattern* of what's wrong is now very clean:

- **Every single true correction has `n_bullet=0`.** Not one real
  bullet kill was found across all 7 wrong clips this round -- matches
  the user's own read from an earlier session ("too much bullet kills
  for those scores," Wesker's dash-finisher meta). Every bullet
  component in every wrong label so far looks fabricated.
- **`group_size` (the raw combo delta) is consistently and drastically
  overestimated** on the wrong clips: detected 8/7/6/5/5/2 vs. true
  1/1/1/2/2/2. The 3 correct clips all had small, clean `group_size`
  (1-2) with confidence 0.66-0.74. The wrong ones are the large-group,
  low-confidence-*ish* clips -- see the confidence-split entry below
  for why "low-confidence-ish" isn't a reliable enough signal by
  itself.
- One specific correction worth flagging: `id=2 (t=124.0)`, a 2-bonus-kill
  group, was manually traced frame-by-frame via screenshots (combo
  `027->028` visible, but the `+05 sec` popup already showing at the
  clip's very start suggested a second, earlier `026->027` kill just
  off-screen) -- the timer-delta math suggested 2 real kills, but the
  user's own review after actually watching the full clip found it was
  really only **1**. Worth remembering: frame-by-frame timer/combo
  math from stills is a good *hypothesis* generator, not a substitute
  for actually watching the clip play.

Bug A's fix is doing its job where it applies (`t=455.8` and `t=399.2`
now show *some* bonus attribution instead of pure `bullet_kill`), but
it can't fix a wrong `group_size` -- that's upstream of anything Bug A
touches, in the combo digit-read/detection path itself (same class as
Bug B: a confidently wrong digit match, not a low-confidence one).
**This is now the single biggest lever on accuracy**, bigger than Bug A
was.

**Also this session: split the group-size confidence discount by
bonus/bullet count instead of raw group_size.** User supplied two
separate rarity tables (own domain knowledge: bullet kills are much
rarer than bonus kills at the same count in a good run) --
`config.BONUS_COUNT_CONFIDENCE_FACTOR` / `BULLET_COUNT_CONFIDENCE_FACTOR`
replace the old single `GROUP_SIZE_CONFIDENCE_FACTOR`. Moved the
discount from `event_detector.detect_kill_groups` (which only knows
raw `group_size`) to `auto_labeler.label_kill_group` (the only place
that knows the bonus/bullet split) -- `KillLabel` gained a `confidence`
field, `event_detector`'s `KillGroup.confidence` is now just the raw
undiscounted `min(prev.confidence, curr.confidence)`.

**Before implementing, simulated a proposed 20%-auto-reject threshold
against this session's actual review data (not hypothetically) --
good thing, because it barely helps:** only 1 of the 7 wrong clips
(the most extreme, `1/7` at confidence 0.06) would get caught; the
other 6 wrong clips score 0.25-0.75, fully overlapping the *correct*
clips' 0.66-0.75 range. **Stayed informational-only, no auto-reject** --
the wrong labels aren't low-confidence, they're confidently wrong
(the same "Bug B: a wrong digit that scores well" pattern), so no
single global threshold can separate them from the good clips.
6 new/updated tests across `test_event_detector.py`/`test_auto_labeler.py`,
**96 tests total**. Re-verified on real footage: same 10 clips/labels
as before (as designed -- this change only touches reported confidence,
not detection), confidence numbers now match hand-simulation exactly
(e.g. the `1/7` clip: 0.09 -> 0.06).

**Start here next session:** root-cause the `group_size` overestimation
directly, the same frame-by-frame methodology as every fix in this
project -- pick the worst offender first. Video 1 `id=3` (`t=196.2`,
detected `1 bonus/7 bullet` = group_size 8, true `1/0`) is the biggest
gap in this round's review (7-kill overcount) and the most likely to
have a clean, traceable root cause. See HANDOFF.md for the exact
reproduction recipe and clip ids from this session (all ephemeral,
`/tmp` won't survive a new session).

## 2026-09-18 (accuracy, resumed yet further) — `group_size`
## overestimation root-caused and fixed: prev/curr combo anchors are now
## clamped against their nearest trusted neighbor before computing
## group_size

**Root-caused by frame-by-frame tracing two of the worst offenders**
(video 1 `id=3` t=196.2 and `id=4` t=526.2), same methodology as every
fix in this project. Both traced to `detect_kill_groups` trusting each
tick's own per-tick majority-voted `combo_value` for `prev`/`curr`
outright -- two distinct mechanisms corrupt that per-tick vote, neither
caught by the existing dip/reversion guards (which only catch a *full*
revert back to at-or-below the pre-rise value; both cases here are
*partial* corruptions where the anchor's error is smaller than the real
kill's own magnitude, so the pair still looks like a directionally
plausible, just inflated, rise):

- **`id=3` (detected group_size=8, true 1):** `prev`'s tick (`t=193.4`)
  landed squarely inside the combo's roll/pop animation (the same
  phenomenon already catalogued for Bug A -- transient intermediate
  digit values before the counter settles). Native 60fps trace: combo
  reads a solid `47` at `t=192.967`, a ~300ms screen-flash gap
  (`is_valid_hud_frame` score drops to -0.17), then `40` at **high
  confidence (0.77-0.93) for 8 of the tick's 11 vote-burst frames**,
  then `48` for the last 2 -- the animation artifact wins the majority
  vote outright and becomes `prev`. Real change was `47->48` (1 kill).
- **`id=4` (detected group_size=5, true 2):** the opposite mechanism --
  `curr`'s burst (`t=526.2`) was almost entirely unreadable (10 of 11
  frames returned no reading at all), and the **one lone frame** that
  cleared the confidence bar (`138`, conf 0.73) won "majority" by
  default, since `_majority_value` doesn't require any minimum vote
  count. The next trusted sample shortly after (in a later,
  spuriously-split session -- same session-fragmentation noise as
  "bug C") reads `134`.

**Considered and rejected: a minimum-vote-count floor in
`_majority_value`** (e.g. reject a winning value with <2 votes) --
would have cleanly fixed `id=4` alone, but simulating it against real
per-tick vote-count data across all three videos first (before
implementing, per this project's established practice) found a winning
value backed by exactly 1 vote is **20-30% of all successful combo
reads across all three videos** (video1 23.7%, video2 20.9%, video3
30.1%), not rare at all -- most bursts in this project's chaotic
footage have only 1-4 readable frames out of 11. A blanket vote-count
floor would have silently discarded a large fraction of genuinely
correct reads in exactly the busy/chaotic windows this project already
struggles to sample densely. Dropped this approach entirely once the
data came back.

**Chosen fix, structurally mirroring Bug A's timer-window search but
using combo's own domain constraint (monotonic non-decreasing within a
session) instead of timer's decay constraint:**
`event_detector._effective_prev_combo_value` /
`_effective_curr_combo_value` search a bounded window
(reusing `config.COMBO_REVERSION_CHECK_WINDOW_S`, since it's the same
underlying phenomenon as the existing reversion check -- a per-tick
vote landing on a wrong value that a nearby sample contradicts, just
correcting the value instead of only using it as a drop/keep signal)
around `prev`/`curr` for the nearest trusted neighboring sample:

- If a sample shortly *before* `prev` reads *higher* than `prev`'s own
  raw value, `prev` is impossible on its own terms (combo can't
  decrease) -- clamp up to that established value.
- If a sample shortly *after* `curr` reads *lower* than `curr`'s own
  raw value, `curr` overshot -- clamp down to that value.

`group_size` is now computed from these effective values, not the raw
per-tick votes. The existing dip-check, reversion-check, pickup-check,
and timer-window logic are all left untouched, operating on the raw
`prev`/`curr` samples exactly as before -- this is a new, independent
layer inserted before them, not a replacement.

TDD'd directly against both real sequences (`test_event_detector.py`,
`test_detect_kill_groups_clamps_prev_when_it_undershoots_the_
established_preceding_value` / `..._clamps_curr_when_a_lone_vote_
overshoots_the_next_trusted_value`). Verified the whole existing test
suite (96 prior tests) needed zero changes -- every existing scenario
either doesn't touch the clamp (single, already-correct pairs) or hits
the *same* drop outcome via an earlier gate now instead of a later one
(traced by hand for `test_detect_kill_groups_keeps_a_rise_reverted_
only_after_the_check_window` in particular, since an unbounded
forward/backward search would have wrongly clamped that test's
legitimate later-and-unrelated combo break -- confirming the window
bound, not just the clamp direction, is load-bearing). **98 tests
total.**

**Verified against real footage with a full stash/restore A/B diff
across all three videos** (same methodology Bug A's contamination bug
was caught by -- unit tests alone were not trusted as sufficient):
- Video 1: both target clips fixed exactly as predicted -- `id=3`
  (`t=196.2`) `mixed(1,7)` conf 0.062 -> `bonus_kill(1,0)` conf 0.624;
  `id=4` (`t=526.2`) `mixed(1,4)` conf 0.42 -> `bonus_kill(1,0)` conf
  0.70. (`id=4`'s reconstructed group_size is 1, not the human-reviewed
  ground truth of 2 -- the available samples alone don't recover the
  second kill, which would need the actual clip video to see; still a
  large, real improvement over the raw 5.)
- Video 2: **zero clips changed** -- this video's wrong clips are Bug
  A/B-class digit-pair misreads, not group_size fabrication, so no
  regression and no false-positive change, as expected.
- Video 3: **one new clip appeared** (`session=257`, `t=536.5`,
  `mixed(1,1)`) that wasn't detected before at all. Investigated before
  trusting it (surprising result, verify don't assume): native
  frame trace confirmed a real ~4-frame misread dip to `combo=0`
  (conf 0.87-0.89, so not low-confidence noise either) sandwiched
  between solid `98`/`99` reads on both sides -- the old code's own
  `MAX_PLAUSIBLE_GROUP_SIZE` cap was silently dropping this whole
  stretch as an implausible 99-kill jump (never recovering the real,
  smaller rise hiding behind the misread), which this fix now
  recovers as a real `group_size=2` instead of losing it entirely. No
  clips disappeared in the diff on any video (no new data loss).

**Not done, deliberately out of scope for this fix:** a full manual
review pass of the fresh clips across all three videos -- that's the
real test of whether this closes the accuracy gap the way Bug A's fix
was meant to, and needs the user actually watching clips, not something
to attempt unattended. See HANDOFF.md.

## 2026-09-18 (accuracy, resumed once more) — Manual review of the fix's
## clips: id=3 fixed exactly as intended; found and fixed a real data-entry
## gap in the review tooling itself

**User reviewed all 11 fresh clips** (`scripts/review_sample.py` against
the `after` A/B manifests) -- **3/11 correct (27.3%)**, roughly flat vs.
the prior 3/10 baseline, which is expected: this fix only targeted
`group_size` fabrication, not every bug class in the dataset.

- **`id=3` (the fix's primary target): now correct.** Confirms the fix
  works exactly as designed.
- **`id=4`: still wrong, but meaningfully closer** -- true `(2,0)`,
  detected now `(1,0)` (was `(1,4)` before the fix). Exactly the
  known limitation flagged in the fix's own test comment: the
  reconstructed value from available samples is 1, not the true 2,
  which needs the actual clip video to fully recover.
- **video1 `id=1`/`id=2`, all of video2: unchanged, as the A/B diff
  predicted** -- different bug classes (the already-catalogued t=62.2
  phantom/Bug-B residual, and the already-documented t=124.0
  frame-math-vs-actually-watching-the-clip discrepancy from a prior
  session), untouched by this fix, not new.
- **video3's newly-recovered clip (`id=1`, t=536.5): wrong, true
  `(1,0)` vs. detected `mixed(1,1)`** -- the fix correctly recovered
  a previously-*entirely-dropped* group (the old code silently lost
  it to the implausible-jump cap), but overshot by one spurious
  bullet kill. Recovering real-but-imperfect data is still a net
  improvement over losing the event outright, but not a full fix.

**Found and fixed a distinct, real bug in the review tooling itself
during this pass:** the user typed a `<bonus>/<bullet>` correction
(`1/0`) meaning to type `y` -- the values happened to exactly match
what was already detected. `parse_review_answer` had no way to notice
this: it always treats a numeric correction as `outcome="n"`
regardless of whether the numbers match the record's own detection,
so this silently recorded an *actually-correct* clip as incorrect.
Confirmed via `auto_labeler.label_kill_group` that `label_kind` is
fully deterministic from `(n_bonus, n_bullet)`, so a correction that
numerically matches the detection is unambiguous -- not a real
correction, and safe to normalize to "y" automatically. **Fixed:**
`review.normalize_review_answer(answer, detected_n_bonus,
detected_n_bullet)` collapses this case; wired into
`scripts/review_sample.py`'s call site (`normalize_review_answer(
parse_review_answer(answer), record["n_bonus"], record["n_bullet"])`).
TDD'd (3 new tests), **101 tests total**. The one already-bad row from
this session (video3 `id=2`, t=557.8) was hand-corrected directly in
the manifest (`review_correct=1`, true fields cleared) since it
predates this fix and the interactive session that produced it had
already ended.

## 2026-09-18 (a fourth video, cross-validation) — new root cause found:
## calibration's scan budget can be entirely consumed by a pre-gameplay
## stretch, locking in the wrong offset for the whole video; fixed by
## starting the scan from the video's midpoint

**A fourth video was added this session**
(`https://www.youtube.com/watch?v=zIMN3UNyo2s`, format 298, same
1280x720@60fps) specifically for cross-validation, per the user's own
call after the group_size fix's review results showed too little data
(11 clips total across 3 videos) to tell whether the remaining gaps
were systematic or one-off. First pipeline run: 8 clips, 6
`bonus_kill`/2 `mixed`, no `bullet_kill` at all (matches the Wesker
meta). User reviewed all 8: **4/8 correct (50%)** -- better than the
prior 27.3%, but **every single wrong clip was an overcount**, and
every true correction again had `n_bullet=0` -- the same
group_size-overestimation signature, on fresh footage, that the
group_size fix (previous entry) was supposed to already address.

**Root-caused the worst offender** (`id=7`, t=606.4, detected
group_size 6, true 1) with the same frame-by-frame methodology as
every fix in this project -- and it turned out to be a **completely
different bug**, not a gap in the group_size clamp fix. The clamp fix
only helps when a *nearby* trusted sample can correct a corrupted
anchor; here, `prev` (combo=125, t=585.8) and `curr` (combo=131,
t=606.4) are both individually solid, confidently-read, genuinely
correct samples -- the problem is a **20.6-second gap with zero valid
samples in between them**, so however many separate real kills
happened across that gap get treated as one simultaneous group by
`detect_kill_groups`'s core adjacent-pair assumption. The same
signature explained `id=3` (24.7s gap) and `id=4` (16s gap) too.

**Traced the gap itself** (`find_best_offset` run directly against the
"invalid" frames inside it) and found the *true* offset there is
`(7, 0)` at **0.98-0.99 confidence** -- a near-perfect match -- while
`sample_video`'s own calibration had locked in `(0, 0)` for the whole
video, which only scores ~0.46-0.48 on these frames (just under the
0.6 validity threshold). **Root cause:** `_calibrate_offset` scans
candidates sequentially from frame 0 and gives up after
`config.CALIBRATION_MAX_FRAMES` (600) candidates -- spaced by the 0.2s
tick interval, that's **~120 seconds of video**. This video's actual
gameplay doesn't start until `t=146.9s`: the pre-gameplay stretch runs
past the entire scan budget, so calibration never sees a single real
gameplay frame before falling back to the wrong `(0, 0)`. This single
wrong offset explains not just `id=3/4/7`'s overcounts but the video's
overall sparse sampling: only **36 total valid samples across 670s**
(videos 1-3 had 2000+ each), since `is_valid_hud_frame` fails almost
everywhere at the wrong offset.

**User's own domain knowledge shaped the fix:** many real runs have a
"preparation lap" collecting time-bonus pickups before the first kill
-- a pre-gameplay stretch isn't just loading screens/menus, it's a
normal, common part of run structure, so raising
`CALIBRATION_MAX_FRAMES` further would only push the same failure mode
to a longer prep lap, not eliminate the class of bug. **User proposed
starting the calibration scan from the video's midpoint instead**
(rather than my own first idea, evenly spreading candidates across the
whole duration) -- simpler, and directly targeted at the actual domain
pattern: by a run's midpoint, real combat is almost certainly
happening, regardless of how long the prep lap or intro was.

**Implemented as a one-line change at the call site, not inside
`_calibrate_offset` itself:** `_calibrate_offset` already just scans
forward from wherever its `cap` argument is currently positioned, so
`sample_video` now does `cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames
// 2)` immediately before calling it -- `_calibrate_offset`'s own
internal voting logic (and its existing test suite) needed zero
changes. TDD'd via `test_sample_video_starts_calibration_from_the_
middle_of_the_video`, which patches `_calibrate_offset` to record the
real `cap`'s position at call time (using the real fixture video's own
frame count as ground truth) rather than constructing a bespoke
two-offset video fixture. **102 tests total.**

**Verified against real footage with a full stash/restore A/B diff
across all four videos** (this change touches every video's
calibration, not just video4's, so all four needed re-checking, not
just the one that surfaced the bug): video4 went from 36 to **327
total samples (9x)**, and its clip count changed from 8 to 6 clips (all
in a different part of the video -- the previously-fabricated `id=7`
group at t=606.4 is gone entirely, replaced by whatever the much denser
real sampling actually supports there). **Videos 1-3 produced
byte-identical clip lists before and after** -- their calibration was
already converging correctly within the old frame-0 scan budget, so
starting from the midpoint instead just finds the same correct offset
by a different path. Confirms the fix is surgical: it only changes
behavior for the specific failure case (intro/prep-lap longer than the
scan budget), zero effect otherwise.

**Not yet done:** manual review of video4's fresh 6-clip set (post
calibration fix) -- the previous review round's data is now stale
since the clip set itself changed substantially. There's also a
known, separate, already-documented issue visible in video4's denser
sample stream (rapid session-id churn from timer noise in chaotic
stretches, e.g. session ids 401/406/408/409 within a 30s window) --
this is the pre-existing "timer-noise session-fragmentation" thread
flagged (but never fixed) in earlier sessions, not something this fix
touches or caused.

## 2026-09-18 (a fourth video, later) — video4's post-calibration-fix
## clips reviewed: 2/6 correct; two failure modes not seen before,
## neither root-caused yet

**User reviewed all 6 of video4's fresh clips** (post calibration fix)
-- **2/6 correct (33.3%)**. Not a clean win over the pre-fix round's
4/8 (50%), but the clip set changed completely (different timestamps,
different underlying samples), so it isn't a like-for-like comparison
-- the calibration fix's own real effect (9x sample density, byte-
identical output on videos 1-3) is already independently verified, see
the previous entry.

Per-clip breakdown:

```
id | detected        | true   | note
 1 | bonus_kill(1,0) | --     | correct
 6 | bonus_kill(1,0) | --     | correct
 2 | bonus_kill(1,0) | (3,0)  | undercount (opposite direction from every prior wrong clip)
 3 | mixed(1,6)      | (2,0)  | overcount, group_size 7 vs true 2 -- same family as before
 4 | mixed(4,1)      | (2,0)  | overcount, group_size 5 vs true 2 -- same family as before
 5 | bonus_kill(1,0) | (0,1)  | wrong kind entirely -- true n_bullet=1
```

**Two things here are genuinely new, not repeats of an already-fixed
pattern:**
- **`id=2` is an undercount** (detected 1, true 3) -- every wrong clip
  in every previous review round (this session and prior ones) has
  been an *overcount*. Not yet investigated; a plausible hypothesis
  (not confirmed) is that the much denser post-calibration-fix sampling
  now splits a real multi-kill chain across a session boundary, losing
  part of it -- the timer-noise session-fragmentation issue flagged in
  the previous entry is a candidate mechanism, but this is speculation
  until frame-traced.
- **`id=5` breaks the "every true correction has n_bullet=0" pattern**
  that has held across every review round in this project so far
  (first noted 2026-09-18 earlier this session, and in every prior
  session's review data) -- true here is `(0,1)`, a genuine bullet
  kill (or a bonus/bullet mislabeling in the *other* direction). None
  of this session's fixes (group_size clamping, calibration) address
  this failure mode; it may need its own investigation.

`id=3`/`id=4` still look like the same group_size-overestimation
family already investigated this session, but worth checking whether
the calibration fix's much denser sampling has introduced a *new*
variant of it (not yet checked) rather than assuming it's identical to
the already-fixed mechanisms.

**Not root-caused, deliberately paused here** -- these are new leads,
not yet investigated with the frame-by-frame methodology. See
HANDOFF.md for the concrete next-step options.
