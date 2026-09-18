# Handoff: biomercs-ml — kill-labeling data pipeline

Paste this whole file as your first message in a new session to continue.

## Status as of 2026-09-18 (a sixth session, continued) — the
## waist-notch tie-breaker **implemented for the combo font, TDD'd (110
## tests), A/B-verified, and now also user-reviewed: KEEP.** One new
## clip confirmed correct, one new clip wrong but in the project's
## already-known "fabricated bullet count" way (not a new failure mode
## this fix introduced). **Start here next session: pick a lead --
## either root-cause the dominant fabricated-bullet-count-on-bonus-kill
## bug (now has one more real data point: video 1, t=520.2,
## `mixed(1,6)` vs true `(1,0)`), or start a genuinely different
## feature/model for the still-unfixed timer font's `3`-vs-`8`/`9`
## confusion (see below). No strong opinion yet, worth a short
## discussion, same as every other fork in this project** (read this
## first -- supersedes everything below, including the timer-font
## section right after, kept for its own detail since the timer font is
## still closed/unfixed)

**What happened this session, part 2 (after the timer-font section
below):** the user confirmed the combo font's own waist-notch result
(validated two sessions ago, not affected by the timer-font failure
above) -- implemented it as `match_digit(..., apply_waist_notch_tiebreak=True)`,
scoped to combo only (`read_combo` passes the flag; `read_timer`/
`read_popup_ones_digit` don't). TDD'd with real footage crops (no
synthetic digit shapes) -- 8 new tests, 110 total. Full detail:
`docs/superpowers/DECISIONS.md`, entry "the waist-notch tie-breaker
implemented for the combo font...".

**Verified via a full real-footage A/B diff on video 1** (stash/run/
restore/run, diff the `clips` table): clip count unchanged (4 -> 4),
but 2 of 4 shifted. **Investigated both, not just noted them:**
- `t=62.2`'s old phantom event disappeared -- confirmed this is the
  already-documented Bug-B false positive (ground truth: no kill
  happens there). A genuine improvement.
- `t=526.2` became two clips (`t=500.6`, `t=520.2`). Frame-traced the
  raw combo sequence in `t=480-530` (deliberately the exact stretch
  `SAMPLE_VOTE_FRAMES` was tuned against, "Bug D") to understand why:
  combo's *tens* digit is genuinely `3` throughout this stretch, so the
  same fix legitimately stabilizes it there too (not scope creep -- the
  fix is digit-shape-based, applies to every combo slot by design).
  Instrumented `match_digit` directly: 104 of 753 calls in this window
  had their digit flipped by the tiebreak, but only 1 was on the ones
  digit specifically, and that one's resulting confidence was too low
  to have passed the read anyway -- ruled out spurious firing under
  motion blur as the explanation for the big sample-count jump (5 -> 89
  samples survive the confidence gate in this window now).

**User then reviewed all 4 clips in the `after` manifest**
(`scripts/review_sample.py /tmp/biomercs-waistnotch-after/manifest.sqlite 4`):
- `t=500.6` (new): **correct** -- `bonus_kill(1,0)` confirmed.
- `t=520.2` (new): **wrong** -- `mixed(1,6)` detected, true `(1,0)`.
  This is the project's dominant, still-unsolved "fabricated bullet
  count on a real bonus kill" pattern (true `n_bullet=0`), not a new
  failure mode -- the combo delta itself (131->138) is real (frame-traced
  above); the bonus/bullet split comes from `auto_labeler`'s
  timer-based arithmetic, which this session never touched.
- `t=124.0`/`t=196.2` (both byte-identical before/after, unaffected by
  this fix): reviewed too -- one wrong (`bonus_kill(2,0)` vs true
  `(1,0)`, pre-existing), one correct. Unrelated to this session.

**Net: real improvement, not a wash.** Before this fix, `t=480-530`
produced exactly one (never-reviewed, but necessarily wrong) clip that
silently merged two separate real bonus kills into one. After: one of
those two is now correctly, separately detected; the other is captured
but mislabeled in the same already-known way. **Decision: keep the
fix.** `t=520.2` is a fresh data point for the fabricated-bullet-count
investigation (still the single biggest unsolved lever on accuracy
project-wide), not a reason to revert this session's work.

**What happened earlier this session (the timer font):** picked up the
previous handoff's exact next step -- test the waist-notch feature (a
geometric concave-notch signature that cleanly separates `3` from
`8`/`9` in the *combo* font) against the *timer* font's digits. **It
doesn't hold.** Full evidence,
root cause, and the two follow-up variants tried: `docs/superpowers/
DECISIONS.md`, entry "the waist-notch feature tested against the timer
font on real footage and found NOT to hold." Short version:

- The lone single-sample timer templates looked promising (`3`: 1.62 vs
  `8`: -5.17, `9`: -9.72) but that data isn't trustworthy on its own --
  same class of unreliable single-template data that caused the
  original digit-`8` root cause.
- **Pulled and visually confirmed 5 real footage crops** (`3`x2, `8`x1,
  `9`x2, across 2 videos, saved to `tmp/timer_digit_{3,8,9}_real_*.png`)
  using monotonically-descending countdown stretches as ground truth,
  the same rigor as prior sessions' visual-confirmation steps. **Real
  `3` scores (-3.04, 0.12) directly overlap real `8`'s score (-2.01)**
  -- no margin, unlike the combo font's clean ~5.7-point gap.
- **Root-caused why** (not just observed the failure): the timer font's
  glyph doesn't fill its 40x76 bounding box the way the combo font's
  tightly-cropped templates do (empty padding top/bottom), so the naive
  "equal thirds of the box" banding straddles the real notch instead of
  isolating it -- confirmed via the raw per-row leftmost-ink profile.
- **Tried two targeted variants, not just the one naive port**:
  bbox-relative thirds (ink-range-only, not raw-box) and peak-recession
  instead of average-recession within the middle band. **Neither
  separated the real crops either.**

**Nothing was integrated -- the tie-breaker plan's own precondition
("if it holds") was not met, so no code or template changes were made.**
This closes the waist-notch lead for the timer font specifically (it
may still hold for the combo font alone, which was never in question
here and isn't affected by this session's finding).

**Quick orientation if picking this up fresh:** the project's dominant
remaining bug is a digit `8` that gets confused with `2`/`3`/`9` via
raw-pixel template matching, in **both** the combo-counter font and the
timer font (two different visual styles) -- this single weakness
explains most of the "fabricated bullet count" errors that have shown
up across every review round this session (14 of 15 wrong clips, see
below). Four fix attempts already failed (see "four failed attempts"
section below for full detail) -- **do not re-attempt sample curation
or binarization alone, both already tried and shown insufficient.**
The live lead is a new geometric feature (below), not yet finished.

### The 23-clip statistical baseline (from real review data, not
### assumption)

Pulled every review verdict still cached in this session's manifests
(`/tmp/biomercs-ab-after{1,2,3}`, `/tmp/biomercs-run4-fixed`,
`/tmp/biomercs-run5-new` -- all 5 videos, several fix eras, 23 clips
total). Of 15 wrong clips: **14 have true `n_bullet=0`** (fabricated
bullet is almost the entire error surface); only 1 has a real
`n_bullet=1` misclassified the *other* way (bonus mistaken for
bullet); **2 clips have a genuine `n_bullet=1` and are already
correctly detected** -- bullet kills aren't impossible, just rare, and
already handled fine when the read is clean. Full table and per-video
breakdown: `docs/superpowers/DECISIONS.md`, entry "the timer-cross-check
idea investigated and found NOT independent...".

### Why "cross-check against the timer" doesn't work (investigated,
### not assumed)

The timer's own math already computes `n_bonus` independently of the
combo digit (this already exists in `auto_labeler`) -- the idea was to
trust that and treat the combo-derived total as suspect when it
implies an unlikely bullet count. **But checked: of the 15 wrong
clips, 12 also have the timer-derived `n_bonus` wrong**, not just the
combo-derived total. Traced two to actual pixels (video5 t=576.0,
video4 t=522.5) and found the **same digit-`8` confusion also
corrupting the timer's own reading** (a real "06:43"/403s frame
misread as "408" in video5; video4's window is far more chaotic,
combo and timer both unstable together, same underlying weakness).
**Conclusion: the timer is not an independent signal** -- it's read
via the same kind of digit-template matching, just a different font,
and shares the exact same weakness. Don't pursue "timer validates
combo" further without first fixing the underlying digit-matching
problem.

**Side finding, not yet acted on:** `templates/digits_timer/*` has
exactly 1 sample per digit -- it never got the multi-sample curation
the combo digits got. Worth doing with the same proven methodology
regardless of the `3`-vs-`8` outcome, but alone won't fix the
structural confusion (already shown to be more than a coverage gap).

### Domain knowledge gathered from the user this round (now also in
### `docs/knowledge_base/mercenaries-mechanics.md`)

1. A bullet kill *can* take out multiple enemies at once (shotgun
   spread, sniper/magnum penetration) -- rare in "good" runs because it
   hurts score, players often restart if it happens by accident.
2. Combo only ever increases from a kill, nothing else.
3. No "silent" time pickup exists -- only map time-items and bonus
   kills change the clock, both already accounted for in the code.
4. A genuine bonus+bullet mix in the *same* group is rarer still, and
   in the user's experience always traces to an external cause
   (another NPC's molotov/dynamite), not the player's own single
   action -- useful for telling a real mixed group apart from a
   misread.

### The new lead: a geometric "waist notch" feature (the user's idea,
### not mine -- partially validated, not yet finished or integrated)

The user looked at a real `3` that had been misread as `8` next to a
real `8`, and pointed out the `3` has a visible concave notch on its
left side around mid-height that the `8` doesn't have. Quantified it:
per row, find the leftmost ink pixel (on the HSV-Value-binarized
crop); compare the average leftmost position in the vertical *middle*
band against the top/bottom bands. **Tested against every combo
template sample and 10 real-footage crops:** real `3`s measured
8.65-12.02, real `8`/`9`s measured -0.03 to 2.92 -- a clean ~5.7-point
margin, no overlap. `2`, `5`, `7` also show some positive
(concave-left) signature but distinctly smaller than `3`'s. Full
numbers: DECISIONS.md, same entry as above.

**Not yet done:**
1. Test this same feature against the **timer font's** digits (visibly
   different style -- orange, digital-clock look) -- this was the very
   next step when the session paused for this handoff. If it holds
   there too, it's likely a genuine font-independent property of how
   `3` vs `8`/`9` render, not a combo-font coincidence.
2. If it holds: integrate as a **scoped tie-breaker**, not a blanket
   filter -- only invoked when raw correlation's top candidate is `8`
   or `9` and the runner-up is `3` (or vice versa) within some
   closeness threshold. This is a deliberate lesson from the earlier
   hole-area-ratio attempt (see "four failed attempts" below), which
   applied globally and caused its own `2`-vs-`3` collision -- keep
   this new check narrow, only firing on the specific ambiguity it's
   proven to resolve.
3. TDD + full 5-video A/B replay before accepting, same standard as
   every other fix this project has ever shipped.

**Ephemeral state note:** all of this round's cached data
(`/tmp/video4_samples.pkl`, `/tmp/video5_samples.pkl`, the manifest
dirs above, `/tmp/test_waist_notch.py` and friends) will NOT survive a
new session -- see "Ephemeral files" far below for the video
download/pipeline-run recipe. The waist-notch test script is short
(~40 lines, in this handoff's own conversation history) and easy to
recreate: binarize via HSV-Value+Otsu, then for each row find the
leftmost lit pixel, compare the vertical-middle band's average against
top+bottom bands' average.

## Status as of 2026-09-18 (a fifth video, later still) — video5
## `id=6`'s overcount root-caused (a sustained digit `8`-vs-`2` misread
## that, via `n_bullet = group_size - n_bonus`, explains the dominant
## fabricated-bullet-count bug); four independent mitigation attempts
## failed (raw-BGR sample add, raw-BGR sample removal, binarize +
## proper re-curation, binarize + upscale) (superseded by the section
## above -- kept for its own per-clip detail, which the section above
## didn't repeat)

**Frame-traced video5 `id=6`** (t=576.0, detected group_size 7, true
1) down to actual pixels: the combo genuinely went `111 -> 112` (one
real bonus kill, confirmed by a "+05 sec." popup on screen), but
`hud_reader.read_combo` confidently misread it as `118` and **stayed
wrong for ~2.5 seconds straight** -- not a one-tick fluke, so none of
this session's neighbor-clamping fixes (Bug A/C/D, the group_size
clamps) could ever have caught it. Since `auto_labeler` computes
`n_bullet = group.group_size - n_bonus` (not independently), this one
digit misread is *sufficient by itself* to explain the dominant
"fabricated bullet count on a real bonus kill" pattern that's shown up
in 7 of the last 8 wrong clips across two review rounds. Root cause:
digit `8` had only 2 template samples (one blurry, one atlas-sourced,
never a proper real-footage capture) and one of them scored 0.71
against this "2" crop, beating all of "2"'s own samples (best 0.51).
Full detail: `docs/superpowers/DECISIONS.md`, entry "video5 id=6's
overcount root-caused... this is now an open architectural question".

**The obvious fix -- curate real "8" samples from the already-
downloaded footage, same method as every prior digit-curation fix --
was tried, TDD'd, and then reverted after real-footage verification
showed it net harmful, not just incomplete:**
- Found and visually confirmed 4 genuine real-footage "8" instances
  across 4 videos, added them, wrote a failing-then-passing test.
- First pass broke an existing regression test (`149`->`148`, a new
  `9`-vs-`8` confusion from one of the new samples) -- fixed by
  dropping that one sample.
- **A full 5-video before/after A/B replay (this project's standard
  verification bar for any event_detector-adjacent change) found 61 of
  263 overlapping per-tick combo reads changed on video1 alone.**
  Spot-checked three against actual frame pixels: all three were *new*
  regressions (true `113`/`119`/`143` now misread as `118`/`118`/`148`
  -- new `3`-vs-`8` and `9`-vs-`8` confusions), none were corrections
  of previously-wrong reads.
- **Reverted all new template samples and the dependent test.** Full
  suite back to 102 passing, working tree clean except for a kept
  fixture frame (`tests/fixtures/frames/combo_112_misread_as_118_frame.png`,
  for whoever picks this up) and this session's doc updates.

**Why sample curation alone can't fix this (confirmed across four
separate attempts, not assumed):**
1. Raw-BGR matching + add 4 real "8" samples -> broke an existing
   regression test (`9`-vs-`8`), fixed by dropping one sample.
2. Raw-BGR, that reduced set -> full 5-video A/B replay found new
   `3`-vs-`8`/`9`-vs-`8` regressions elsewhere on video1. Reverted
   everything.
3. **Binarize before matching** (HSV Value channel + Otsu threshold --
   a real, literature-backed technique for exactly this game-HUD-OCR
   problem, found via web research) **+ properly re-curated real
   footage for both `8` and `9`** (8 diverse new samples across 4-5
   videos, all self-identify at 0.92-1.00). This is a genuine partial
   win -- it fixes the original target case (video5 `id=6`) cleanly,
   `2` now wins 1.0000 vs `8`'s 0.6671 -- **but all three fresh, clean
   real "8" samples individually still score 0.73-0.85 against two
   known `3` crops**, nearly identical to each other. Not one bad
   sample this time -- every real "8" capture over-matches "3" at this
   resolution.
4. **Binarize + 4x upscale before thresholding** (also suggested by
   the same research, in case 34x46px itself was destroying
   discriminating detail) -- made things *worse*, broke the
   already-fixed target case too.

**Conclusion: digit `8`'s shape structurally overlaps with `3` and `9`
under raw-pixel correlation at this font/resolution, with or without
binarization or upscaling.** This is not a "find better samples"
problem any more -- per this project's own debugging discipline, 3+
failed fix attempts on the same symptom means change the *kind* of
fix, not iterate again. **No code or template changes were kept --
working tree only has doc updates and `tmp/` reference images**
(`combo_digit_templates_binarized_grid.png` and others, useful context
for whoever picks this up: they show `0/e` is corrupted but empirically
harmless, and `4/a`/`6/a`/`8/a`/`9/a` share a left-edge crop-bleed
defect, neither of which is the actual cause of the `3`/`9`/`8`
confusion found here).

**Start here next session:** needs a real strategy change, not more
curation. Options, roughly in order of effort:
1. **Accept as a documented, unfixed limit** (like the earlier t=408.8
   overexposed-frame case) and move to a different lead instead --
   video4's undercount (`id=2`, t=490.7), video4's wrong-kind result
   (`id=5`, t=547.5), or video5's total phantom (`id=3`, t=341.8).
2. **Cross-check the combo delta against independent evidence** --
   e.g. the timer's own bonus-jump math or the "+05 sec." popup (which
   is exactly what let us establish ground truth in this
   investigation) -- instead of trusting the combo digit read alone.
   Doesn't need `8` vs `3`/`9` to ever be perfectly disambiguated by
   pixels; sidesteps the problem instead of solving it head-on.
3. **A genuinely different feature/model just for the `3`/`8`/`9`
   family** -- e.g. stroke-width profiling, contour-based shape
   descriptors (Hu moments), or a small trained classifier -- rather
   than raw-pixel correlation. Bigger effort, no guarantee it fares
   better than correlation did.
4. **A confidence-margin mechanism** (winning digit must beat the
   runner-up by some margin) -- weakest option now: already looked
   shaky before this session's evidence, and the new data (three
   different real "8" samples all scoring within 0.1 of each other
   against the same wrong crop) suggests the margin would need to be
   large enough to also reject genuine "8" reads.
No strong opinion yet on which has the best return -- worth a short
discussion before picking, same as every other fork in this project.

## Status as of 2026-09-18 (a fifth video, cross-validation) — a fifth
## video added and reviewed: 2/6 correct, same rate as video4's
## post-fix round; neither of video4's two new failure modes repeated,
## but a new total-phantom-event instance appeared (superseded by the
## section above -- kept for its own per-clip detail, which the
## section above didn't repeat)

**User reviewed a fifth video's fresh 6-clip set**
(`https://www.youtube.com/watch?v=HYXLHArtq1I`, format 298,
1280x720@60fps, added this session purely for more cross-validation
data after video4's round left no strong signal) -- **2/6 correct
(33.3%), matching video4's post-fix rate exactly.** Full per-clip
breakdown: `docs/superpowers/DECISIONS.md`, entry "a fifth video,
cross-validation". Key results:

- **Neither of video4's two brand-new failure modes repeated.** No
  undercount this round (video4's `id=2` still the only one
  project-wide), and no "wrong kind with true n_bullet>0" (video4's
  `id=5` still the project's only counterexample to the n_bullet=0
  pattern). Both remain unconfirmed as real patterns vs. one-offs --
  this round doesn't settle it either way.
- **The dominant, long-standing bug (fabricated bullet count on a real
  bonus kill, true n_bullet=0) is still the main story**: 3 of this
  round's 4 wrong clips fit it exactly (`id=1`, `id=4`, `id=6`).
  Combined with video4's round, **7 of 8 wrong clips across both
  post-fix rounds have true n_bullet=0** -- strong, consistent signal,
  still not root-caused.
- **New: a total phantom event** (`id=3`, t=341.8: detected
  `mixed(1,6)`, true `(0,0)` -- no kill happened at all). Not a new
  mechanism -- this pattern was flagged once, much earlier in the
  project, and never confirmed or re-seen until now. Its confidence
  (0.139) is the lowest in the batch, well under the previously-
  rejected 20%-auto-reject threshold -- worth checking whether a
  low-confidence filter catches phantom-class errors specifically,
  even though earlier analysis showed it doesn't help the dominant
  fabricated-bullet-count class.

**Start here next session:** four candidate leads now, still no clear
winner -- pick between:
1. Frame-trace video4 `id=2`'s undercount (t=490.7, video4) -- still
   unconfirmed as a real pattern (zero repeats in video5).
2. Frame-trace video4 `id=5`'s wrong-kind result (t=547.5, video4) --
   also still a single instance, no repeat in video5.
3. Frame-trace video5 `id=3`'s total phantom (t=341.8, video5) -- ties
   back to an old, never-confirmed hypothesis about
   `MAX_PLAUSIBLE_COMBO_VALUE` thinning sample density; its very low
   confidence (0.139) might make it easier to trace than the others.
4. Root-cause the dominant fabricated-bullet-count-on-bonus-kill bug
   itself (7/8 wrong clips across the last two rounds) -- the single
   biggest lever by volume, even though it's the least "new" of the
   four and has resisted every fix so far this session.
No strong opinion yet on which has the best return -- worth a short
discussion before picking, same as every other fork in this project.

## Status as of 2026-09-18 (a fourth video, later) — video4's
## post-calibration-fix clips reviewed: 2/6 correct, with two failure
## modes never seen before (an undercount, and the first-ever true
## n_bullet>0) (superseded by the section above -- kept for its own
## per-clip detail, which the section above didn't repeat)

**User reviewed video4's fresh 6-clip set (post calibration fix): 2/6
correct (33.3%).** Not a clean comparison to the pre-fix round's 4/8
(50%) since the clip set changed completely -- the calibration fix's
own effect is independently verified already (9x sample density,
byte-identical output on videos 1-3, see the section right below).
Full per-clip breakdown: `docs/superpowers/DECISIONS.md`, entry
"video4's post-calibration-fix clips reviewed". Two things are
genuinely new, not repeats of anything already fixed this session:

- **`id=2` (t=490.7): an undercount** (detected `(1,0)`, true `(3,0)`)
  -- every wrong clip in every review round so far, this session and
  every prior one, has been an *overcount*. Not investigated --
  a plausible but unconfirmed hypothesis is the denser
  post-calibration-fix sampling now splits a real multi-kill chain
  across a session boundary (the pre-existing, already-documented
  "timer-noise session-fragmentation" issue is a candidate mechanism,
  visible in this same video's sample stream -- see below).
- **`id=5` (t=547.5): wrong kind entirely** -- detected `bonus_kill
  (1,0)`, true `(0,1)`, a genuine bullet kill. This breaks the "every
  true correction has n_bullet=0" pattern that has held across every
  review round in this entire project until now. Neither this
  session's group_size fix nor the calibration fix addresses this.

`id=3`/`id=4` (still overcounts, group_size 7 vs true 2 and 5 vs true
2) look like the same group_size-overestimation family already
investigated this session, but haven't been re-checked against the
denser post-calibration-fix samples -- worth confirming this is really
the same mechanism, not a new variant, before assuming it needs no
further work.

**Start here next session:** no strong signal on which lead to chase
first -- pick between:
1. Frame-trace `id=2`'s undercount (t=490.7) -- a genuinely new
   failure direction, worth understanding before assuming it's rare.
2. Frame-trace `id=5`'s wrong-kind result (t=547.5) -- also new, and a
   different class of bug (mislabeling bonus vs. bullet, not a count
   error) from everything fixed this session.
3. Re-check `id=3`/`id=4` specifically to confirm they're still the
   already-understood group_size-overestimation mechanism post-
   calibration-fix, not a new variant.
4. Keep adding cross-validation videos / reviewing more clips before
   committing to any one investigation -- the sample sizes are still
   small enough (6 clips per video) that a single review round's
   pattern could easily be noise.
No strong opinion yet on which has the best return -- worth a short
discussion before picking, same as every other fork in this project.

## Status as of 2026-09-18 (a fourth video) — new root cause found and
## fixed: HUD offset calibration could lock onto the wrong offset for
## an entire video if the pre-gameplay stretch outlasted its scan
## budget. Verified via A/B diff on all four videos (videos 1-3
## byte-identical, video4 went from 36->327 samples). (superseded by
## the section above -- kept for the calibration fix's own
## implementation/verification detail, which the section above didn't
## repeat)

A fourth video was added this session for cross-validation (user's own
call, after the group_size fix's review showed too little data --11
clips across 3 videos -- to tell whether its remaining gaps were
systematic). First run: 8 clips, 4/8 correct (50%, better than the
prior 27.3%) but **every wrong clip was an overcount** -- the same
group_size-overestimation signature, on fresh footage, that the
previous fix was supposed to cover.

**Root-caused the worst offender (`id=7`, t=606.4, detected 6, true
1) and found a completely different bug**, not a gap in the group_size
clamp fix: `prev` and `curr` were both individually correct, solid
reads -- the problem was a **20.6-second gap with zero valid samples in
between**, so however many real kills happened across it got lumped
into one fabricated group. Traced further: `_calibrate_offset` scans
sequentially from frame 0 and gives up after ~120s of video, but this
video's gameplay doesn't start until t=146.9s (a "preparation lap"
collecting time bonuses, per the user's own domain knowledge about run
structure -- not just a menu/loading intro) -- calibration never saw a
real gameplay frame and locked in the wrong `(0,0)` offset for the
*entire* video, starving `is_valid_hud_frame` almost everywhere (only
36 valid samples across 670s, vs. 2000+ on other videos).

**Fixed on the user's own suggestion:** start the calibration scan
from the video's midpoint instead of frame 0 (simpler than raising the
scan budget, which would just push the same failure to a longer prep
lap) -- by a run's midpoint, real combat is almost certainly
happening. One-line change (`_calibrate_offset` itself scans forward
from wherever its `cap` is positioned already, so `sample_video` just
seeks first). TDD'd, **102 tests total**. Full detail:
`docs/superpowers/DECISIONS.md`, entry "a fourth video,
cross-validation".

**Verified via a full stash/restore A/B diff across all four videos**
(this touches every video's calibration, not just video4's): video4
went from 36 to 327 samples (9x), clip count 8->6, composition changed
substantially (the previously-fabricated `id=7` group at t=606.4 is
gone). **Videos 1-3 produced byte-identical clip lists before and
after** -- confirms the fix is surgical, zero effect outside the
specific failure case.

**This clip set has since been reviewed** -- see the section above
("video4's post-calibration-fix clips reviewed") for the results and
current next step; this pointer is stale, kept for history only. Video
4's URL is `https://www.youtube.com/watch?v=zIMN3UNyo2s` (re-download
per "Ephemeral files" below if this session's `/tmp` state is gone).
Also worth knowing about, but not investigated this session: video4's
denser sample stream shows rapid session-id churn from timer noise in
some chaotic stretches (e.g. sessions 401/406/408/409 within 30s) --
this is the pre-existing, already-documented "timer-noise
session-fragmentation" issue from much earlier sessions, not caused by
or related to this session's fix.

## Status as of 2026-09-18 (accuracy, resumed once more) — the
## group_size fix reviewed: id=3 (its primary target) is now correct;
## id=4 improved but still short (true 2, detected 1); video3's
## (superseded by the section above -- kept for the group_size fix's
## own review-result detail, which the section above didn't repeat)
## newly-recovered clip is real but overshoots by one. Also found and
## fixed a real bug in the review tooling itself (a matching correction
## wasn't normalized to "y"). **Start here next session: root-cause
## id=4's undercount or video3's overcount (see below), OR move on to a
## different bug class (video2's Bug A/B-class wrong clips, or the
## t=62.2 phantom) -- your call, no single obvious next lever this
## time** (read this first -- supersedes everything below)

**User manually reviewed all 11 fresh clips** across all three videos
(`scripts/review_sample.py` against the `after` A/B manifests from the
group_size fix) -- **3/11 correct (27.3%)**, roughly flat vs. the prior
3/10 baseline, which is expected: the group_size fix only targeted one
specific bug class, not every wrong clip in the dataset. Full per-clip
breakdown and reasoning: `docs/superpowers/DECISIONS.md`, entry
"Manual review of the fix's clips". Key results:

- **`id=3` (t=196.2, the fix's primary target): now correct.** Confirms
  the fix works exactly as designed.
- **`id=4` (t=526.2): still wrong but meaningfully closer** -- true
  `(2,0)`, detected now `(1,0)` (was `(1,4)` before the fix). This is
  the known limitation flagged in the fix's own test/DECISIONS.md
  entry: the reconstructed value from the available samples is 1, not
  the true 2 -- would need the actual clip video (not just per-tick
  HUD samples) to fully recover the second kill.
- **video3's newly-recovered clip (t=536.5): wrong, true `(1,0)` vs.
  detected `mixed(1,1)`** -- the fix correctly recovered a previously
  *entirely-dropped* group (the old code silently lost it to the
  implausible-jump cap), but overshoots by one spurious bullet kill.
  Net improvement over losing the event outright, but not a full fix.
- **video1 `id=1`/`id=2`, all of video2: unchanged, as the A/B diff
  predicted** -- different, already-catalogued bug classes (the t=62.2
  phantom/Bug-B residual, and the t=124.0 frame-math-vs-watching-the-
  clip discrepancy from a prior session), untouched by this fix.

**Also found and fixed, mid-review:** the review tooling itself had a
real bug -- typing a `<bonus>/<bullet>` correction that happens to
match what was already detected (an easy mistake when meaning to type
`y`) used to always record the clip as incorrect. Fixed via
`review.normalize_review_answer` (see DECISIONS.md, same entry). Not
relevant to the pipeline's actual detection accuracy, just a data-entry
integrity fix for the review process itself.

**Start here next session:** no single obvious next lever this
time -- pick between:
1. Root-cause `id=4`'s remaining undercount or video3's overcount with
   the usual frame-by-frame methodology (both are now much smaller,
   more tractable gaps than before this session's fix -- 1-off, not
   4-7 off).
2. Move to a different bug class entirely: video2's wrong clips are
   confirmed Bug A/B-class (digit-pair misreads under chaotic footage),
   not group_size fabrication -- template curation or a fresh
   frame-trace investigation, not more event_detector work.
3. The t=62.2 phantom/Bug-B residual (already flagged as low-priority,
   diminishing returns from template curation) -- probably still not
   worth chasing without new material.
No strong signal yet on which of these has the best return -- worth a
short discussion before picking, same as every other fork in this
project.

## Status as of 2026-09-18 (accuracy, resumed yet further) —
## `group_size` overestimation root-caused and fixed (prev/curr combo
## anchors now clamped against their nearest trusted neighbor); verified
## on real footage via a full A/B diff across all three videos.
## (superseded by the section above -- kept for the fix's own
## implementation/verification detail, which the section above didn't
## repeat)

**Root cause and fix:** see `docs/superpowers/DECISIONS.md`, entry
"`group_size` overestimation root-caused and fixed" for full detail.
Short version: `event_detector.detect_kill_groups` was trusting each
tick's own raw per-tick majority-voted `combo_value` for `prev`/`curr`
outright. Two distinct mechanisms could corrupt that single-tick vote
(neither caught by the existing dip/reversion guards, since both are
*partial* corruptions smaller than the real kill's own magnitude):
a combo roll/pop animation transiently rendering a low intermediate
value that wins a strong majority (video 1 `id=3`, detected group_size
8, true 1), and a near-unreadable burst where one lone corroboration-free
frame wins "majority" by default (video 1 `id=4`, detected group_size
5). **Considered and rejected a minimum-vote-count floor in
`_majority_value`** after simulating it against real vote-count data
first -- a winning value backed by exactly 1 vote turned out to be
20-30% of all successful combo reads across all three videos, so a
blanket floor would have discarded a large fraction of genuinely
correct reads. Chose instead: `_effective_prev_combo_value`/
`_effective_curr_combo_value` clamp `prev`/`curr` against the nearest
trusted neighboring sample within a bounded window
(`config.COMBO_REVERSION_CHECK_WINDOW_S`, reused) before computing
`group_size`, using combo's own monotonic-non-decreasing domain
constraint -- structurally the same idea as Bug A's timer-window
search, just for combo instead of timer. TDD'd against both real
sequences, **98 tests total**, zero changes needed to the 96 prior
tests.

**Verified via a full stash/restore A/B diff across all three videos**
(not just unit tests -- same methodology Bug A's contamination bug was
caught by): video 1's two target clips both fixed as predicted
(`mixed(1,7)`->`bonus_kill(1,0)` and `mixed(1,4)`->`bonus_kill(1,0)`);
video 2 had **zero clips changed** (its wrong clips are a different bug
class, unaffected as expected, no regression); video 3 gained **one
new clip** (`session=257`, `t=536.5`, group_size 2) that the old
`MAX_PLAUSIBLE_GROUP_SIZE` cap was silently dropping entirely as an
implausible 99-kill jump -- investigated and confirmed real (a genuine
~4-frame misread dip to `combo=0` sandwiched between solid `98`/`99`
reads, not a fluke). No clips disappeared on any video (no new data
loss).

**Start here next session: a full manual review pass of the fresh
clips on all three videos** (`scripts/review_sample.py`) -- this is the
real test of whether the fix actually moved agreement, the same
"regenerate manifests, review from scratch, look at the aggregate rate"
pattern used after every other fix in this project. Ephemeral `/tmp`
footage/run dirs from this session may not survive into a new session
(see "Ephemeral files" below) -- re-download and re-run per that
section if gone. If `bullet_kill`/`mixed` agreement improved
meaningfully, that confirms this was the right lever; if not, the
`bonus_kill` count vs. the Wesker dash-finisher-meta expectation is
still the strongest signal to re-check next (see the "3/10 correct"
section below for the baseline this is measured against).

## Status as of 2026-09-18 (accuracy, resumed even further) — manual
## review done: 3/10 correct, found `group_size` overestimation is the
## real dominant bug (not anything Bug A touches); confidence discount
## also split by bonus/bullet count. (superseded by the section above --
## kept for the review-baseline detail and per-clip table it still has,
## which the section above didn't repeat)

**Manually reviewed all 10 clips across all three videos** with Bug A
and its contamination guard in place -- **3/10 correct (30%)**. Not a
raw-agreement improvement over session-start baseline, but the pattern
of what's wrong is now very clean and points past Bug A entirely. Full
per-clip table and reasoning: `docs/superpowers/DECISIONS.md`, entry
"Manual review of all 10 post-Bug-A clips". Short version:

- **Every true correction found `n_bullet=0`.** All 7 wrong clips this
  round had zero real bullet kills -- every bullet component detected
  so far looks fabricated. Matches the user's own read from an earlier
  session (Wesker's dash-finisher meta should make bullet kills rare).
- **`group_size` (the raw combo delta) is consistently and drastically
  overestimated**: detected 8/7/6/5/5/2 vs. true 1/1/1/2/2/2 across the
  wrong clips. This is upstream of anything Bug A touches (Bug A only
  fixes *timer-delta attribution* once `group_size` is already right) --
  it's a combo digit-read problem, same class as Bug B (a confidently
  wrong digit match), not a new mechanism. **This is now the single
  biggest lever on accuracy.**

**Also fixed this session: confidence discount split by bonus/bullet
count**, not raw `group_size` -- `config.BONUS_COUNT_CONFIDENCE_FACTOR`/
`BULLET_COUNT_CONFIDENCE_FACTOR`, applied in `auto_labeler.label_kill_group`
(`KillLabel` gained a `confidence` field). **Before implementing, a
proposed 20%-auto-reject threshold was simulated against the actual
review data above and found to barely help** (catches only 1 of 7
wrong clips, since the wrong labels are *confidently* wrong, not
low-confidence) -- stayed informational-only, no auto-reject added.
**96 tests total.** Full detail: DECISIONS.md, same entry as above.

**Start here next session: root-cause the `group_size` overestimation**
-- same frame-by-frame methodology as every fix in this project (pull
raw frames, look at actual pixels, don't trust confidence numbers
alone). **Pick video 1's `id=3` first** (`source_120_196.2.mp4` in this
session's run, `t=196.2`, detected `1 bonus/7 bullet` = group_size 8,
true `1/0`) -- the biggest single gap in this round's review (7-kill
overcount), most likely to have a clean, traceable root cause. Other
candidates from the same review round if that one doesn't pan out
cleanly: video 1 `id=4` (t=526.2, detected 5, true 2), video 2 `id=2`
(t=399.2, detected 6, true 1), video 2 `id=4` (t=549.0, detected 7,
true 1).

**Reproduction (all ephemeral, `/tmp` won't survive a new session --
see "Ephemeral files" below to re-download/re-run):**
```
rm -rf /tmp/biomercs-run /tmp/biomercs-run2 /tmp/biomercs-run3
uv run python -c "
from pathlib import Path
from biomercs_ml import pipeline
pipeline.run('/tmp/biomercs-footage/source.mp4', Path('/tmp/biomercs-run'), Path('/tmp/biomercs-run/manifest.sqlite'))
pipeline.run('/tmp/biomercs-footage2/source.mp4', Path('/tmp/biomercs-run2'), Path('/tmp/biomercs-run2/manifest.sqlite'))
pipeline.run('/tmp/biomercs-footage3/source.mp4', Path('/tmp/biomercs-run3'), Path('/tmp/biomercs-run3/manifest.sqlite'))
"
```
This reproduces the same manifest ids/timestamps deterministically
(same code + same video). Use `hud_reader._sample_range` directly (see
`docs/superpowers/DECISIONS.md`, "#6" entry, and this session's own use
of it while debugging Bug A) to pull raw unfiltered per-tick
timer/combo/confidence around a specific timestamp without re-running
the whole pipeline -- much faster than digging through the filtered
`HudSample` list, and it survives across sub-investigations within one
session.

## Status as of 2026-09-18 (accuracy, resumed) — Bug A fixed (plus a
## contamination guard the A/B testing found along the way); the
## phantom-event pattern is root-caused (folds into Bug B, not a new
## bug, left unfixed) (superseded by the section above -- kept for the
## Bug A implementation detail it still has, which the section above
## didn't repeat)

**Bug A is fixed** -- see `docs/superpowers/DECISIONS.md`, entry
"Phantom-event pattern root-caused... Bug A fixed via a timer-delta
search window" for full technical detail. Short version:
`event_detector.detect_kill_groups` now searches a window
(`config.TIMER_DELTA_SEARCH_WINDOW_S = 3.0`) around each detected
combo-rise for the timer's *own* jump, instead of trusting the
timer values of the exact two samples the combo-rise landed on --
fixes the case where the combo counter's ~350ms-2s roll animation lags
the timer's single-frame jump enough that they land on different
sample ticks. 3 new tests in `test_event_detector.py`, all passing
(**94 tests total**).

**Real-footage A/B testing (stash the fix, run video 2, restore, run
again, diff) is what caught a second bug the design didn't
anticipate:** the timer-delta window has no plausibility cap of its
own (unlike combo), so a wild misread elsewhere in the window (e.g.
`5227.0` next to a cluster of legitimate `~500s` readings) could win
the min/max search and tank 3 real clips that should have stayed.
Fixed with a swing bound derived from the already-trusted
`MAX_PLAUSIBLE_GROUP_SIZE` constant (no new domain fact needed) --
see DECISIONS.md for the exact formula and the real-footage
verification. **Don't skip the real-footage A/B step for logic changes
here again** -- unit tests alone would have shipped the contamination
bug; it only showed up against real noisy timer data.

**The "new phantom-event pattern" flagged two sessions ago is
root-caused, not fixed** (video 1, id=1, t=62.2): ground truth combo
never moves from `012` in that whole window -- it's not a new
mechanism, it's Bug B (a busy background -- here a static rock wall
texture, not motion blur -- bleeding into the digit search margin)
compounded by the still-unfixed timer-noise session-fragmentation
issue from an earlier session. **Deliberately left unfixed this
session** -- Bug B's known fix (template curation) already hit
diminishing returns once this project, and this instance has no fixed
neighbor to clamp against like the earlier neighbor-bleed fix did.
Still present in this session's final video 1 clips, low confidence
(0.465). Don't re-chase this without new material (more real-footage
samples for the affected digit pairs) or a specific reason to revisit
the session-fragmentation issue instead.

**Regenerated all three videos' manifests this session with every
current fix in place (#6 parallelization, Bug A, the contamination
guard):** video 1 -> 4 clips, video 2 -> 5 clips, video 3 -> 1 clip.
Clip counts and label composition (bullet_kill/mixed/bonus_kill splits)
changed substantially from prior sessions' numbers -- expected, given
how much has landed since those were last measured (Bug C, Bug D, the
combo cap, digit curation, and now Bug A). **Old `id=N`/timestamp
references from before this session (e.g. "id=8, t=193.0") no longer
line up with anything -- so much has changed upstream that those exact
ticks often don't even produce a sample anymore.** Don't try to
re-locate them; treat every fresh manifest as the current ground truth
to review against.

**Start here next session: manually review the fresh clips on all
three videos** (`scripts/review_sample.py`, same as every previous
review round) -- this is the real test of whether Bug A's fix actually
moved agreement, not just clip counts. Ephemeral `/tmp` footage/run
dirs from this session may or may not survive into a new session (see
"Ephemeral files" below) -- re-download and re-run per that section if
gone. After review: if `bullet_kill`/`mixed` agreement improved
meaningfully, that confirms Bug A was the right lever; if not, revisit
the phantom-event/session-fragmentation thread instead of re-tuning
Bug A further.

## Status as of 2026-09-18 (newest) — #6 (parallelize `sample_video`)
## is DONE and verified; performance track is complete for now
## (superseded by the section above -- kept for the #6 implementation
## detail it still has, which the section above didn't repeat)

**#6 is implemented, TDD'd, and verified against real footage --
see `docs/superpowers/DECISIONS.md`, entry "Parallelized `sample_video`
across CPU cores" for full detail. Short version:**

- `sample_video` now takes a `max_workers` parameter (default
  `os.cpu_count()`); a new `_sample_range` worker function does the
  per-tick digit-matching work for a `[start_frame_idx, end_frame_idx)`
  range in its own `cv2.VideoCapture` / subprocess, `sample_video`
  dispatches chunks via `ProcessPoolExecutor`, concatenates in chunk
  order, then runs the `session_id`/`last_timer_value` bookkeeping pass
  once, sequentially, over the merged list. `max_workers=1` skips
  `ProcessPoolExecutor` entirely (calls `_sample_range` in-process) so
  the existing `unittest.mock.patch`-based test suite keeps working
  unmodified -- all 7 pre-existing `sample_video(...)` test call sites
  now explicitly pass `max_workers=1`.
- Two new tests added, both real (not mocked): chunk-boundary
  correctness (`_sample_range` split into two adjacent sub-ranges ==
  one full range, concatenated) and parallel-vs-sequential equivalence
  (`max_workers=1` vs `max_workers=2` on the real fixture, exact
  `HudSample` list match). **91 tests pass** (`uv run pytest -v`).
- **Real-footage verification, not just unit tests:** a real 30s clip
  ffmpeg-trimmed from video 1 gave byte-identical output between
  `max_workers=1` and `max_workers=8` (25.88s -> 7.65s, 3.4x). A full
  `pipeline.run` on the entire ~10min video 1 (10 cores on this
  machine) went from the ~500s baseline that started this performance
  track to **115.2s -- ~4.3x real end-to-end speedup**. Did not re-run
  the full sequential path a second time on the whole video (would cost
  another ~8-9 minutes for marginal confidence beyond the exact-match
  30s real-clip result) -- see DECISIONS.md for the full reasoning on
  why that verification bar was judged sufficient.
- The lower clip count seen in this run (10, vs. earlier sessions'
  "17") is **expected and unrelated to parallelization** -- this
  session started from wherever Bug C/D + the combo cap + partial
  digit curation had already left things, and only touched performance,
  not accuracy. Don't read anything into that number changing.

**GPU acceleration remains deferred, not reconsidered** -- nothing in
this session's real numbers (4.3x from CPU parallelism alone) changes
the earlier verdict in `docs/knowledge_base/project-ideas.md`. Still
don't re-raise it without a batching rewrite already in progress.

**Start here next session: go back to the paused accuracy thread.**
Performance is no longer the excuse -- a full pipeline run now takes
~2 minutes instead of ~8-9, so iterating on accuracy fixes is cheap
again. Pick up exactly where the accuracy work was paused (see the
"even later" section right below, which is otherwise fully superseded
by this one): **Bug A is still not fixed** (the architectural change --
search a window for the timer delta instead of trusting one
adjacent-sample pair -- was deliberately not attempted yet, see below
for why it's the single biggest lever), and there's an unconfirmed
phantom-event pattern worth frame-tracing (e.g. video 1 id=1, t=62.2)
before resuming Bug A itself.

## Status as of 2026-09-18 (even later) — mid-implementation of a
## performance track (#6, parallelizing `sample_video`); accuracy work
## is paused, not abandoned (superseded by the section above -- kept
## for the accuracy-thread detail it still has, which the section
## above intentionally didn't repeat)

**What happened, in order:** re-ran the full pipeline on video 2 with
Bug C + Bug D + the combo cap + partial digit curation all in place
(see the section below for what those are), full-reviewed it, then
downloaded and ran a **third video**
(`https://www.youtube.com/watch?v=8ilpJYjIRtQ`, format 298, same
1280x720@60fps) for cross-validation, full-reviewed that too. **All
three videos now reviewed. Combined result: 6/17 (video 1+2) + 1/3
(video 3) correct — roughly 30-35% agreement, not meaningfully better
than session start**, and the fixes so far haven't closed the gap:

- `bonus_kill` stays solid (6/7 correct across the reviewed sample).
- **Every single `bullet_kill`/`mixed` clip is wrong** across all three
  videos. The dominant pattern (`review_true_n_bullet=0` in nearly
  every wrong clip) is Bug A's signature: a real `bonus_kill` getting a
  fabricated bullet count. **Bug A is still not fixed** — it needs the
  architectural change flagged when it was found (search a window for
  the timer delta instead of trusting one adjacent-sample pair), which
  was deliberately not attempted yet.
- One new wrinkle: a couple of wrong clips this round were **total
  phantom events** (`review_true=(0,0)`, no kill happened at all) —
  a pattern not seen in earlier rounds. Working theory, not yet
  confirmed: `MAX_PLAUSIBLE_COMBO_VALUE` rejecting more readings
  thinned sample density enough that the dip/reversion guards (which
  need nearby samples to catch a correction) now have gaps. **Not
  investigated further this session** — got sidetracked into
  performance work instead (see below). Worth frame-tracing one of
  these (e.g. video 1 id=1, t=62.2) before resuming Bug A.

**Accuracy work was paused here, mid-investigation, in favor of a
performance track** — not because it's done, but because the user
asked "why is this taking so long" after the third video's pipeline
run and the conversation went there instead. **Do not lose the thread
above** — Bug A is still the single biggest lever on accuracy, and the
new phantom-event pattern needs its own root-cause trace.

### Performance track (started this session, mid-implementation)

Profiled `sample_video` with `cProfile` (real evidence, not
assumption): of a ~500s pipeline run on a ~615s video, **~84% is the
per-tick digit-matching loop, ~12% is HUD-offset calibration, ~4% is
raw frame decode**. 97.9% of all time is inside `cv2.matchTemplate`
itself (native OpenCV C++), not Python overhead — the problem is *call
count*, not language speed. Full numbers and reasoning: DECISIONS.md,
whichever entry covers the performance investigation (search for
"matchTemplate" or "calibration").

The user asked for a ranked list of candidate optimizations (with
expected gain / confidence-it's-the-problem / confidence-the-fix-works
for each) before committing to any of them. Decisions made, in the
user's own words:

1. **Coarse-to-fine search for HUD offset calibration — DONE.**
   `find_best_offset` did a brute-force 1681-position grid search per
   candidate frame; replaced with a coarse pass at
   `config.OFFSET_COARSE_SEARCH_STRIDE_PX` then a 1px refinement
   around the winner. TDD'd (a new test asserts far fewer
   `matchTemplate` calls; existing exact-offset-recovery tests prove
   no accuracy regression). **Measured real result: calibration
   59.5s -> 6.9s (8.6x), same exact offset found.** Side effect: the
   whole test suite also dropped from ~22s to ~6s wall time.
2. **Lower `SAMPLE_VOTE_FRAMES` back down from 11 — REJECTED, do not
   re-suggest.** User's own words: "SAMPLE_VOTE_FRAMES must be 11."
   11 is the proven minimum for the real Bug D case (t=522.0); this is
   settled, not open for re-litigation.
3. **Early-exit in `match_digit`** (stop scanning once a sample clears
   a confidence threshold) — **investigated, then explicitly
   rejected by the user ("skip 3"), do not re-suggest without new
   information.** Real-footage score-distribution check found the
   median winning score is only 0.889 (p75=0.926) — any threshold low
   enough to matter would risk letting an over-matching digit (like
   "8", per the earlier finding) win *before* the true digit's own
   sample is even checked, since dict iteration order is `0..9` and
   `match_digit` currently finds the true global max across all
   digits/samples, not a first-match. A safe near-1.0 threshold would
   almost never fire (p95=0.984), so the risk/reward doesn't work.
4. **Batched/vectorized correlation** (replace many small
   `cv2.matchTemplate` calls with one large batched op, e.g. via
   PyTorch) — **on hold, user's own words: "hold."** Not started.
5. **Downscale crops/templates further** — **rejected as not worth
   it**, crops are already tiny (34x46px), per-call overhead already
   dominates over pixel count.
6. **Parallelize `sample_video`'s per-tick loop across CPU cores —
   the user's stated top pick ("this is the best one I think"),
   design agreed in chat, implementation not yet started.** This is
   where to resume:

**Agreed design for #6 (from in-chat discussion, do not re-derive):**
- Split into two phases. Phase 1 (parallel): a new worker function,
  something like `_sample_range(video_path, start_tick, end_tick,
  frame_interval, templates..., offset)`, where each worker opens its
  *own* `cv2.VideoCapture`, seeks to its assigned start tick, and does
  today's per-tick logic (validity check, burst read, majority-voted
  timer/combo/popup) for its range -- but does **not** touch
  `session_id`/`last_timer_value` at all. Returns a plain list of raw
  per-tick results (timestamp, timer_value, combo_value, confidence,
  pickup_popup).
- Phase 2 (sequential, cheap, no `matchTemplate` calls): `sample_video`
  concatenates all workers' results *in chunk order* (chunks are
  naturally time-ordered, so this is just concatenation, not a merge
  sort), then runs the existing `is_new_session`/`last_timer_value`
  assignment pass over the merged, ordered list -- this is the *only*
  part that's inherently sequential, and it's fast bookkeeping, not
  the expensive part.
- Chunk boundaries must align to tick multiples (not arbitrary frame
  counts) so no worker ever needs a frame from a neighboring chunk's
  range for its own burst reads.
- Use `ProcessPoolExecutor` (CPU-bound work; threads don't help, GIL).
- **New `max_workers` parameter on `sample_video`, defaulting to
  `os.cpu_count()`.** Critically: **tests must pass `max_workers=1`**,
  which should skip subprocess spawning entirely and just call the
  chunk function in-process -- this is *why* `max_workers=1` matters,
  not just a default choice: a lot of existing tests
  (`test_sample_video_majority_votes_combo_within_each_tick` and
  others) work by `unittest.mock.patch`-ing `hud_reader.read_timer`/
  `read_combo`/etc. in the test process. Those patches do **not**
  apply inside a real subprocess -- moving the digit-matching work
  into subprocesses would silently break that whole mocking-based test
  suite unless `max_workers=1` keeps everything in-process for tests.
- TDD as always: write the failing tests first (existing mocking-based
  tests should keep passing unmodified once they pass `max_workers=1`;
  new tests should cover chunk-boundary correctness and that
  parallel vs. sequential produce identical `HudSample` lists on a
  real small fixture).

**GPU acceleration was investigated and explicitly deferred, not
rejected** -- documented in
`docs/knowledge_base/project-ideas.md` ("GPU acceleration for
digit-template matching"). Benchmarked directly on this Mac (M2 Pro,
OpenCL available): `cv2.UMat` GPU dispatch measured **~30x slower**
than CPU for this workload (3.2ms/call vs 0.11ms/call) -- tiny 34x46px
crops mean per-call GPU dispatch overhead dominates completely. The
user also has a second PC (AMD 9700X + Radeon 9070 XT) -- its CPU
would help #6 proportionally to core count, but the GPU would very
likely hit the same overhead problem (possibly worse, discrete PCIe
transfer latency vs. Apple Silicon's unified memory) unless paired
with the same big batching rewrite as item 4 above. **Don't re-raise
GPU acceleration without a batching rewrite already in progress.**

**Start here next session:** implement #6 per the agreed design above,
TDD first. After that lands and is verified (re-time a real pipeline
run, confirm identical output to the sequential path on at least one
real video), circle back to the paused accuracy thread: root-cause the
new phantom-event pattern, then tackle Bug A's architectural fix
(still the single biggest remaining lever on the actual dataset
quality, independent of how fast the pipeline runs).

## Status as of 2026-09-18 (later) (superseded by the above --
## kept for history)

Picked up exactly where the previous status left off ("Start here next
session: pick... id=8"). Frame-by-frame traced id=8 plus two more of
the 8 wrong video-2 clips and found **three distinct, independently
confirmed root causes** — not the single "session fragmentation" story
the previous status speculated. Full evidence and reasoning for each:
`docs/superpowers/DECISIONS.md`, entry "Frame-by-frame tracing of the
8 wrong video-2 clips finds THREE distinct root causes, not one".
**Nothing has been implemented yet** — this is investigation-only,
same "stop and get explicit approval before implementing" pattern as
every previous fix in this project.

- **Bug A (confirmed via native-60fps frame trace, id=8):** the combo
  counter has a ~350ms roll/pop animation after a kill, but the timer
  changes in a single frame. `detect_kill_groups` assumes both land in
  the same adjacent-sample-pair; when they don't, the timer delta
  reads as zero even though a real bonus happened, mislabeling
  `bonus_kill` as `bullet_kill`.
- **Bug B (confirmed via native-60fps frame trace, id=6):** a
  *sustained* (near-1-second), high-confidence (0.75-0.83) misread of
  the combo's hundreds digit ("8"/"9") and ones digit ("5"/"6"/"9")
  during chaotic/motion-blurred combat — a template-quality gap like
  the already-fixed fifth root cause, but a different digit pair, and
  long enough that no existing transient/voting guard could catch it.
- **Bug C (confirmed via 0.2s-grid trace, id=10 at t=492.4):** the
  existing transient-dip guard in `detect_kill_groups`
  (`session_samples[i-1].combo_value >= curr.combo_value`) only checks
  the previous sample *within the same session*. A misread severe
  enough to also trigger a spurious session split lands at index 0 of
  the new session, where there is no `i-1` — so the guard is
  structurally blind at exactly the moments session-splitting misreads
  happen.

**Bug C is now fixed** (`_preceding_combo_value` looks across session
boundaries instead of `session_samples[i-1]` — see DECISIONS.md, "Bug
C fixed" entry). Verified against real footage: re-running
`detect_kill_groups` over all of video 2's cached samples removed
exactly the one phantom group this fix targeted (`session=239,
t=492.4`) and nothing else. Tests not yet re-run through the full
pipeline / re-reviewed end to end this session — see "Start here next
session" below.

**Re-ran and re-reviewed video 2 with Bug C's fix in place.** 16 fresh
clips, 9/16 correct (56%). The `t=492.4` phantom is confirmed gone.
Frame-tracing the other 7 wrong clips found a fourth pattern (Bug D:
rapid frame-to-frame flicker, too fast/noisy for the 3-frame majority
vote) alongside Bug A and Bug B variants. **Bug D is now fixed**
(`SAMPLE_VOTE_FRAMES` 3 -> 11, TDD'd against the real t=522.0
sequence; required regenerating `tests/fixtures/synthetic_static.mp4`
at 60fps to match real footage). Full classification is in
DECISIONS.md.

**Then a much bigger finding, which supersedes the Bug A/B/C/D framing
as the top priority:** the user pointed out a combo value of 185 is
physically impossible (RE5's fixed enemy pool caps combo at 150 —
now documented in `docs/knowledge_base/mercenaries-mechanics.md`).
Checking this against real footage found `hud_reader.read_combo`
confidently misreading a **completely clean, non-chaotic** frame
("029 COMBO", Wesker standing still) as "889". Root cause: **only
digits 0/3/5/7 ever got the multi-sample template curation** the
2026-09-17 architecture decision called for — digits `1, 2, 4, 6, 8,
9` still have just **one sample each**, and that lone "8" sample
over-matches broadly even on ordinary frames. **A meaningful fraction
of this session's Bug A/B/C/D clip classifications may be
misclassified** as a result — treat them as provisional.

**Fixed immediately:** `config.MAX_PLAUSIBLE_COMBO_VALUE = 150`;
`read_combo` now returns `None` above it regardless of confidence
(TDD'd against the real t=124.0 frame, now a checked-in fixture). This
also incidentally fixes the fifth root cause's previously
"permanent, accepted" overexposed-frame case one layer earlier.

**Template curation for `1, 2, 4, 6, 8, 9` is now done, but only
partially effective — see DECISIONS.md for full detail.** Real-footage
samples added for `1/2/4/6/9` (visually verified against the actual
frame each time, since several plausible-looking `read_combo` outputs
during the search turned out to themselves be misreads). No real "8"
occurrence was found in either full video even at a very low
confidence threshold — `8` got one atlas-sourced supplementary sample
instead. **Verified real but incomplete improvement:** an independent
frame (video 2, t=409.2s) now reads correctly; another (video 1,
t=252.4s) still misreads its tens digit "6" (only 2 samples for that
digit, thinner coverage than `0/3/5/7`'s 4-5). The original
adversarial t=124.0 frame that surfaced this whole finding still
misreads even with new samples — may be its own "accepted pixel-level
limit" like the fifth root cause's t=408.8s frame, not conclusively
determined. Stopped curating further (diminishing returns without new
screenshot material; both zips are now fully mined for this video
pair's low-combo stretches) — the `MAX_PLAUSIBLE_COMBO_VALUE` cap and
`event_detector`'s existing safeguards catch what curation alone
couldn't.

**Start here next session:** re-run the pipeline on both videos and
re-review from scratch. This is the real test of how much this whole
session's work (Bug C, Bug D, the combo cap, and the partial digit
curation) moved the needle together — stop chasing individual frames
in isolation and look at the aggregate agreement rate instead. Video 1
still hasn't been reviewed with the correction-capable script at all.
Remember to use a fresh output directory (see the gotcha below).

**Gotcha to remember:** `/tmp` output directories are *not* reliably
cleared within a single ongoing session (only between sessions) —
`/tmp/biomercs-run2` had 2026-09-16 rows still in it when re-run today,
which silently mixed stale pre-fix clips into the first review pass.
Always `rm -rf` the output dir (or use a fresh one) before re-running
`pipeline.run` a second time in the same session.

**Reproduction:** same recipe as below (video 2, `/tmp/biomercs-footage2/source.mp4`).
This session additionally used raw frame-by-frame reads (bypassing
`sample_video`'s 0.2s grid and majority vote entirely) via
`hud_reader.read_timer`/`read_combo` called directly per-frame with
`cv2.VideoCapture` stepping one frame at a time — needed to see bug A's
animation, which a 0.2s-grid trace alone would never reveal. Recreate
with `cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)` then loop
`cap.read()` once per frame, matching the frame-by-frame scripts
mentioned lower in this file.

## Status as of 2026-09-18, earlier (superseded by the above -- kept
## for history)

**The fifth root cause (combo digit "0" losing to "8"/"9") is now
fixed** (multi-sample template architecture implemented, real
video-sourced samples curated for combo 0/3/5/7 -- commit `85186fa`),
**plus three new `event_detector` safeguards** (group-size ceiling
20->8, a combo-reversion check, rarity-scaled confidence -- commit
`dbf7231`). One specific frame (video 2, t=408.8s) remains an accepted,
permanent pixel-level limit -- it's genuinely overexposed, not just
compressed, so no digit reader can recover it; this is caught downstream
by the safeguards instead. Full technical writeup for both:
`docs/superpowers/DECISIONS.md`, entries "Multi-sample architecture
implemented..." and "event_detector domain-knowledge safeguards...".

**Result: video 2 went from 46 clips to 17 (the four original phantom
`n_bullet=10` groups are gone), video 1 went from 40 to 17.**
`bonus_kill` is now the dominant label on both, matching the Wesker
dash-finisher meta.

**But manually re-reviewing video 2's new 17 clips found a second,
separate bug, not yet root-caused -- this is the actual next step, not
the (now fixed) combo-0-vs-8/9 issue:**

- Agreement is only 52.9% (9/17): `bonus_kill` 9/9 correct, `bullet_kill`
  0/4 correct, `mixed` 1/4 correct -- almost the exact same broken
  pattern the *previous* session found before any of today's fixes.
- The review script now captures corrections (type `<bonus>/<bullet>`
  e.g. `1/2` instead of just `n` when a label is wrong -- see
  `review.parse_review_answer`; re-review only previously-wrong clips
  with `uv run python scripts/review_sample.py <db> wrong`). Using it on
  all 8 wrong video-2 clips found **every single one had a true
  `n_bullet` of 0** -- they were all pure `bonus_kill` events. Full
  table (detected vs. actual bonus/bullet counts, per clip id and
  timestamp) is in the DECISIONS.md entry "Re-review surfaces a second,
  distinct bug".
- Traced raw per-tick `HudSample`s around all 8 events and found the
  likely cause is **not** a labeling-math bug (`auto_labeler`'s
  `n_bonus = round(bonus_seconds / 5.0)` math is correct per
  `docs/knowledge_base/mercenaries-mechanics.md` -- each bonus kill adds
  a full independent +5s). Instead:
  - **Timer readings are badly unstable in these specific windows** --
    e.g. one tick reads `timer=2660.0`, another `timer=2889.0` (garbage
    four-digit values, not just a wrong-but-plausible digit).
  - **`session_id` increments on nearly every tick** in these windows
    (e.g. 3 different session ids within 2 seconds), because
    `is_new_session`'s timer-jump detection fires constantly on this
    noise -- fragmenting what's very likely one continuous fast-kill
    sequence into many spurious single-tick sessions, which directly
    breaks `detect_kill_groups` (it only ever compares samples it's
    told are in the same session).
  - A likely **new, distinct combo-digit confusion** separate from the
    now-fixed 0-vs-8/9 case: clip id=1 (t=37.0s) detected combo
    `884->886` (group_size 2) where the real value was `884->885`
    (group_size 1) -- consistent with ones-digit "5" misread as "6",
    not yet investigated.
  - All 8 events cluster in fast, chaotic combat moments (rapid
    consecutive kills, likely screen-flash/particle effects) -- the
    same kind of footage that has produced most of this project's hard
    bugs so far.

**Start here next session:** pick one of the 8 wrong clips (id=8,
t=193.0s, is the simplest -- detected `(0,1)` vs actual `(1,0)`, and the
group_size already matched at 1, so it isolates the timer-read failure
without also debugging a combo-count discrepancy) and apply the same
frame-by-frame methodology used for every fix in this project: pull raw
frames around the event with `cv2.imwrite`, look at the actual pixels,
don't trust confidence numbers alone. The timer-instability and
session-fragmentation problem likely needs fixing before or alongside
whatever's happening with the combo digit, since it may be corrupting
more than just these 8 flagged clips (video 2 has 17 clips total but
only these 8 were manually checked in detail this way -- video 1 hasn't
been re-reviewed with the correction-capable script at all yet).

**Reproduction recipe** (the cached per-tick samples used for this
session's tracing were in `/tmp/video2_samples.pkl`, gone in a new
session -- re-download video 2 per "Ephemeral files" below, then):
```python
from pathlib import Path
from biomercs_ml import config, hud_reader

timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
popup_digit_templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)
samples = hud_reader.sample_video(
    Path("/tmp/biomercs-footage2/source.mp4"), timer_templates, combo_templates,
    combo_label_template, popup_digit_templates, popup_label_template,
)
# then filter `samples` for timestamp_s within a couple seconds of each
# wrong clip's timestamp (37.0, 69.0, 122.0, 181.2, 193.0, 492.4, 522.0,
# 549.2) and inspect timer_value_s/combo_value/session_id directly.
```
Re-running the full pipeline (`pipeline.run(...)`) reproduces the same
manifest ids/timestamps deterministically, same as always.

## Status as of 2026-09-17 (superseded by the above -- kept for history)

The handoff's "concrete lead" (four `n_bullet=10` groups in video 2) has
been **root-caused, not yet fixed**. Full writeup with evidence:
`docs/superpowers/DECISIONS.md`, entry "Combo digit '0' losing template
match to '8'/'9' (fifth root cause)". Short version: the combo digit
templates `0.png`/`3.png`/`5.png`/`7.png` were captured from a different,
inconsistent source (a one-off calibration screenshot) than the other
six (real gameplay footage), and "0" loses template-match confidence to
"8"/"9" against real footage as a result -- producing phantom ±10 combo
deltas with no actual timer change.

**Agreed fix (discussed and approved in-chat, not yet implemented):**
1. Extend the digit-matching architecture from one template image per
   digit to *multiple* sample images per digit (best score across a
   digit's own samples wins) -- applied uniformly to all ten digits.
2. The user is supplying, next session: several high-quality **1280x720
   PNG** screenshots taken directly in-game across varied HUD
   backgrounds, the digit's original in-game sprite asset as ground
   truth, and a couple of crops pulled directly from the already-
   downloaded YouTube footage.
3. TDD the multi-sample change against the real bug (video 2 frames at
   t=399.8/403.4/408.8/414.0s), then populate all ten combo digits, then
   re-verify the four phantom groups disappear, then re-review video 2.

**Do not re-litigate:** a top-2-confidence-margin heuristic and a
symmetric event_detector persistence check were both considered and
rejected in favor of fixing the actual template-quality root cause --
see DECISIONS.md for why. Don't suggest using a pristine game sprite as
the sole template source either -- also discussed and rejected (it skips
the scale/blend/compress pipeline the working templates are consistent
with); the sprite is a validation reference and one sample among several,
not a replacement for footage-sourced samples.

This is currently blocked on the user, not on investigation -- if they
haven't brought screenshots yet, ask for them rather than guessing at a
codebase-only fix.

**Update 2026-09-17 (later same day):** user provided
`resources/Steam Screenshots.zip` (gitignored, not committed -- 105
native 1920x1080 screenshots + the real `COMBO_ORIGINAL_TEXTURE.png`/
`TIMER_ORIGINAL_TEXTURE.png` bitmap-font atlases). Extraction pipeline
built and run (see DECISIONS.md "2026-09-17 follow-up" entry for the
full recipe) -- only 7 of 105 screenshots actually show the Mercenaries
combo HUD, and all 7 read `010` or `020`: good real-footage coverage for
digits 0/1/2, **none for 3/5/7**. The atlas has clean ground-truth crops
for all ten digits already segmented (recipe in DECISIONS.md) but no
background diversity by itself.

**User's call: wait for more screenshots** (asked to reach higher
combos like 13/35/57+ so 3/5/7 get real-footage samples too) rather
than implementing now with the atlas standing in for those three. This
is a data-collection pause, not a technical blocker -- don't re-ask the
same question next session, just check whether new screenshots showed
up in `resources/` and pick up from there. If they have, re-run the
extraction recipe rather than re-deriving it.

## Update 2026-09-17 (later still) -- data collection DONE, implementation not started yet

**Do not re-ask about screenshots or re-run the data-collection
question. This part is finished.** User provided a second, larger batch:
`resources/21690_20260917222148_1.zip` (gitignored, not committed --
159 more native 1920x1080 screenshots). Combined with the first zip,
extraction now has **real gameplay-footage samples for every digit
0-9**, across genuinely varied backgrounds (dark interiors, blown-out
bright shots, gold-toned lighting, foliage occlusion, wood-plank walls).
The previously-missing 3/5/7 are now well covered: `003, 030, 034, 037,
038, 039` / `005, 045, 052, 054, 056, 057` / `007` (x4 different
backgrounds), `027, 037, 057`.

**Key fact learned from the user, not previously known:** the combo
counter is **blue only when the value is an exact multiple of 10** (10,
20, 30...); **every other value renders in white**. The first
screenshot batch only found blue hits because the extraction script's
color heuristic was blue-only at that point -- it missed all the (more
common) white-rendered combos entirely, including the `057` moment the
user explicitly pointed out. The extraction script was fixed
mid-session to detect both colors (see recipe below). **White is the
primary/common case, blue is the rare milestone case** -- when curating
templates, prioritize white samples; blue is a secondary variant worth
having per digit but not the main coverage.

### Where this was cut off

The user said "wait" and asked for this handoff mid-implementation --
**no code changes have been made yet**, only investigation/extraction
(all in the harness scratchpad, which will NOT survive a new session --
see "Ephemeral files" section, same caveat applies to this round's
screenshot crops too). The architecture design was in progress when
cut off; here's the exact plan, so it doesn't need re-deriving:

**Decided but not yet implemented:**
1. `hud_reader.load_digit_templates` changes from
   `dict[str, np.ndarray]` (one image per digit) to
   `dict[str, list[np.ndarray]]` (multiple sample images per digit).
2. Directory layout changes from flat `templates/<set>/<digit>.png` to
   per-digit subdirectories: `templates/<set>/<digit>/<sample_name>.png`
   -- e.g. `templates/digits_combo/0/a.png`,
   `templates/digits_combo/0/b.png`, etc. (Considered flat filenames
   like `0_a.png` parsed by splitting on `_` -- rejected as more fragile
   than just using real directories.) This restructuring applies to
   **all three** template sets (`digits_combo`, `digits_timer`,
   `digits_popup`), not just combo, because `load_digit_templates` is
   shared code and its signature must change for every caller --
   but only `digits_combo` needs *new* sample images; timer/popup's
   existing single template each just moves into a same-named
   subdirectory unchanged (e.g. `digits_timer/0.png` ->
   `digits_timer/0/a.png`), no functional change for them.
3. `hud_reader.match_digit` changes to take the new
   `dict[str, list[np.ndarray]]` type: for each digit, score against
   *all* of that digit's sample images (resizing each to `target_size`
   as it already does), take the **max score across that digit's own
   samples**, then pick the digit with the highest per-digit max. This
   is the actual fix for the root-caused bug -- a digit no longer loses
   just because its one template happened to be a bad match; it only
   has to win with *any one* of several real-footage samples.
4. `read_digit_slots` needs no logic change, just the type threading
   through.

**Call sites that need updating** (found via
`grep -rn "load_digit_templates\|match_digit\|templates\s*=\s*{"
tests/ src/` -- re-run this if the codebase has moved on):
- `src/biomercs_ml/hud_reader.py` -- `load_digit_templates`,
  `match_digit` themselves (the two functions to actually change).
- `src/biomercs_ml/pipeline.py` -- three call sites, just pass templates
  through, no logic change needed.
- Tests: `test_hud_reader_digits.py`, `test_hud_reader_popup.py`,
  `test_hud_reader_video.py`, `test_hud_reader_fields.py` -- all of
  these call `load_digit_templates` and use the result opaquely (none
  construct a template dict inline as a literal), so **they should not
  need logic changes**, only to keep passing once the directory
  restructuring is done. Verify this assumption before trusting it.
- `tests/test_templates_complete.py` **does** need a real change -- it
  currently asserts `{p.stem for p in Path(dir).glob("*.png")} ==
  ALL_DIGITS`, which checks flat filenames. Update it to check
  subdirectory names instead (`{p.name for p in Path(dir).iterdir() if
  p.is_dir()}`).

**Not yet decided / do next:**
- Pick a checked-in TDD fixture frame reproducing the real bug (a
  "105"-reading frame from video 2 where the tens digit reads "9"
  instead of "0" -- e.g. around t=408.8s, session 166, see the "fifth
  root cause" DECISIONS.md entry for exact timestamps). Save it as
  `tests/fixtures/frames/combo_105_zero_misread_frame.png` following
  the existing pattern (`combo_149_adjacent_digit_bleed_frame.png`).
  The video isn't downloaded in a fresh session -- re-download per the
  "Ephemeral files" section, seek to the right frame, `cv2.imwrite` it.
- Curate the actual template sample images from the two screenshot
  zips (both still on disk under `resources/`, gitignored -- unzip
  them again, don't re-ask the user for anything). Crop tightly to each
  digit glyph (similar aspect ratio to the existing ~34x46 nominal box,
  doesn't need to be exact since `match_digit` resizes to
  `target_size` anyway). Aim for 2-4 diverse-background samples per
  digit, prioritizing white (the common case) with at least one blue
  sample where convenient (blue only shows up at multiples of 10, so
  e.g. reuse a `10`/`20`/`30`/`40` screenshot's "0" for that).
  Good source screenshots identified this session (filenames from
  `resources/21690_20260917222148_1.zip` unless noted, batch 1 =
  `resources/Steam Screenshots.zip`):
  - 0: extremely abundant, nearly every screenshot list entry has a
    solo "0" (round-start reading) -- pick any handful with visibly
    different backgrounds.
  - 3: `21690_20260917222053_1.png` (`030`, bright/overexposed),
    `21690_20260917222104_1.png` (`034`), `21690_20260917222112_1.png`
    (`037`), `21690_20260917222113_1.png` (`038`).
  - 5: `21690_20260917222149_1.png` (`045`), `21690_20260917222224_1.png`
    (`052`), `21690_20260917222231_1.png` (`054`, bright gold), `.../
    222239_1.png` (`056`, bright gold with foliage), `.../222241_1.png`
    (`057`).
  - 7: `21690_20260917211945_1.png` through `.../211957_1.png` (several
    `007` frames, batch 1, varied lighting incl. one gold/overexposed),
    `21690_20260917222030_1.png` (`027`), `21690_20260917222112_1.png`
    (`037`), `21690_20260917222241_1.png` (`057`).
  - 1/2/4/6/8/9: also well covered, see the `combo4_grid_*` review
    (was in scratchpad, gone now) -- re-run the extraction recipe below
    and eyeball results again rather than trying to recall exact
    filenames for these.
- After the architecture + templates land, re-verify: the four phantom
  `n_bullet=10` groups (sessions 161/163/166/167 in video 2) should
  disappear, then re-review video 2's full clip set.

### Extraction recipe (rebuild if scratchpad is gone)

```python
import glob, os, cv2, numpy as np

SHOTS_DIRS = ["resources/Steam Screenshots.zip", "resources/21690_20260917222148_1.zip"]
# unzip both into working dirs first, then:

SEARCH_Y0, SEARCH_Y1, SEARCH_X0, SEARCH_X1 = 100, 280, 1000, 1750

def find_bands(mask_cols, min_width=10):
    ...  # column-gap segmentation, see DECISIONS.md "2026-09-17 follow-up"

for path in screenshots:
    img = cv2.imread(path)
    region = img[SEARCH_Y0:SEARCH_Y1, SEARCH_X0:SEARCH_X1]
    b, g, r = cv2.split(region.astype(np.int32))
    blue_mask = (b > 120) & (b > r + 30)
    white_mask = (b > 150) & (g > 150) & (r > 150) & (np.abs(b-r) < 40) & (np.abs(g-r) < 40)
    mask = (blue_mask | white_mask).astype(np.uint8) * 255
    # column-sum -> bands -> keep the leftmost run of bands whose width
    # is >=0.65x the max band width (digits are wide, "COMBO" letters
    # are narrower) -- 1 to 3 such bands -> that's the combo digits.
    # glyph height must be 40-100px to reject false positives (menus,
    # other white UI text elsewhere on screen).
```
Full working version was `extract_combo_digits4.py` in this session's
scratchpad -- gone in a new session, but short enough (~90 lines) to
recreate from the description above and DECISIONS.md.

## What this project is

`biomercs-ml` (repo: https://github.com/stLmpp/biomercs-ml, public,
cloned at `/Users/stlmpp/projects/biomercs-app/biomercs-ml`) is a
personal ML-learning project: turn Resident Evil 5/6 "The Mercenaries"
gameplay video into a labeled dataset, starting with one target —
classifying each kill as `bullet_kill` (gunfire only, no time bonus),
`bonus_kill` (melee/dash finisher, +5s to the run clock), or `mixed`
(a simultaneous group of both). The game's own HUD (run timer + combo
counter) gives free, reliable ground truth for this specific label, via
per-digit template matching (not OCR).

This is a sub-project of a bigger, only-loosely-scoped ambition
(eventually: compare the author's own runs against world-record runs
and get coaching feedback) — **don't expand scope toward that goal**,
this plan is deliberately narrowed to just the data pipeline.

Read before doing anything else, in this order:
1. `docs/knowledge_base/README.md` and both files it points to — domain
   knowledge (game mechanics) and deferred ideas. Treat the mechanics
   file as ground truth; it comes from the author's own top-level
   competitive experience, don't second-guess it.
2. `docs/superpowers/DECISIONS.md` — **read this in full.** It's the
   record of every non-obvious fix, the alternatives considered, and
   *why* each one was chosen, across all sessions. Essential context
   before touching `hud_reader.py` or `event_detector.py` again.
3. `docs/superpowers/specs/2026-09-16-kill-labeling-pipeline-design.md`
   and `docs/superpowers/plans/2026-09-16-kill-labeling-pipeline.md` —
   the original approved design/plan. All 11 tasks are done; this is
   historical context now, not a checklist.
4. `AGENTS.md` — Python/coding conventions for this repo. Follow it.

## Status as of this handoff

All code is committed on `main` (worked directly on `main` again this
session, no worktree, per the user's standing preference). **64 tests
pass** (`uv run pytest -v`). Run it first thing to confirm nothing's
broken.

### What happened this session (continuing from the previous handoff)

The previous session's manual review found ~47% agreement against the
spec's >98% target. This session found and fixed **four distinct root
causes**, each verified against real downloaded footage (not just unit
tests), each with its own commit and its own entry in
`docs/superpowers/DECISIONS.md` with full reasoning:

1. **Majority-vote combo/timer reads per tick** (`c9fb02e`) — a
   transient single/few-frame digit misread landing on the 0.2s
   sampling grid created phantom kill-groups where the real value
   never changed. Fixed by voting a burst of frames per tick.
2. **event_detector persistence check** (`cdee5f0`) — misread streaks
   longer than the vote burst still slipped through as a
   dip-then-recovery pattern. Fixed by checking the sample *before*
   the dip isn't already at the recovered value.
3. **Map pickup detection + discard** (`4c022fd`) — a map time-bonus
   pickup (+30/+60/+90s, popup text) is a timer-increase source
   `auto_labeler` has no concept of, and its effect animates in over
   many seconds rather than landing on one tick. Fixed by detecting
   the popup (only need to distinguish ones-digit "5" vs "0" — kill
   bonus is always fixed at "+05") and discarding any kill-group within
   5s of one. Found and fixed a follow-on bug in the same commit:
   severe misreads in that chaotic stretch were splitting one session
   into several spurious ones, so the pickup search now covers all
   samples, not just the current session's.
4. **Digit jitter-margin neighbor-bleed** (`7b3dedf`) — the biggest one.
   `DIGIT_SEARCH_MARGIN_PX` (added last session for compression-jitter
   tolerance) could reach past a digit slot's own box far enough to
   match against a *different* real HUD element next to it (the
   "COMBO" label, 1px after the last combo digit) — a **deterministic**
   misread, not noise, so nothing frame-level or sample-level could
   ever have caught it. Fixed by clamping each slot's margin extension
   to the midpoint with its neighbor (or an explicit `right_bound` for
   a non-slot neighbor like a label), never shrinking below the slot's
   own nominal box. This one turned out to be generating far more
   phantom events than the single instance that surfaced it — fixing
   it dropped total clip count on one video from 69 to 46.

Also shipped: a `redo` option (`r`) in `scripts/review_sample.py`
(`2d04463`) so a mistyped review answer doesn't require restarting the
whole session — implemented as a tested `ReviewTally` class in
`src/biomercs_ml/review.py`.

**A second source video was added this session** for cross-video
validation: `https://www.youtube.com/watch?v=u9DA7ueGiH0` (format 298,
same 1280x720@60fps as the first). This is how fix #4 above was found —
it didn't show up in the first video's review sample the same way.

### Review results after all four fixes (this session)

Both videos were regenerated and manually reviewed after all fixes
landed:

- **Video 1** (`6y-6lH7SdJU`): 40 clips (17 `bonus_kill`, 17
  `bullet_kill`, 6 `mixed`). Not re-reviewed after the final fix
  (#4) — the user switched to reviewing video 2 instead. Worth a
  fresh review pass.
- **Video 2** (`u9DA7ueGiH0`): 46 clips (23 `bonus_kill`, 17
  `bullet_kill`, 6 `mixed`). Manually reviewed (30 clips): **53.3%
  agreement** (16/30) — `bonus_kill` 15/16 correct, `bullet_kill` 1/9
  correct, `mixed` 0/5 correct.

## Open problem — NOT yet resolved, this is the actual next step

**`bullet_kill` and `mixed` are still heavily wrong** even after all
four fixes (`bonus_kill` is solid at 15/16). The user's own expert
read, unprompted: *"too much bullet kills for those scores"* —
Wesker's dash-finisher meta (see knowledge base) should make pure
bullet kills rare, not ~37-40% of the dataset. This is a strong signal
there's at least one more systematic bug, not just noise.

**Concrete lead, not yet investigated:** four separate `bullet_kill`
groups in video 2 all have **exactly `n_bullet=10`**, spaced ~5-6s
apart, at very close session ids (161, 163, 166, 167) and timestamps
(399.8, 403.4, 408.8, 414.0) — `id=30,31,32,34` in
`/tmp/biomercs-run-video2b/manifest.sqlite`. An identical group size
recurring this precisely, this close together, looks far more like a
systematic bug than four independent coincidences. **Start here** —
trace these with the same frame-by-frame methodology used for every
fix this session (see below), before looking at anything else.

Other wrong clips from this session's video 2 review, for
cross-reference (id, label, n_bonus, n_bullet, session, ts, confidence
— same manifest):

```
5 |mixed      |1|6 |17 |69.0  |0.627
6 |mixed      |1|8 |29 |91.6  |0.609
9 |bullet_kill|0|2 |55 |122.0 |0.623
10|mixed      |1|9 |64 |140.2 |0.627
18|mixed      |2|5 |97 |252.0 |0.720
21|bullet_kill|0|9 |101|265.2 |0.615
23|bullet_kill|0|1 |111|286.8 |0.688
27|mixed      |5|4 |130|360.8 |0.730
28|bullet_kill|0|1 |135|369.2 |0.649
29|bullet_kill|0|19|151|386.6 |0.637
31|bullet_kill|0|10|163|403.4 |0.769
35|bullet_kill|0|1 |188|441.8 |0.628
37|bonus_kill |1|0 |202|458.2 |0.615  <- a bonus_kill marked wrong too
39|bullet_kill|0|10|254|522.2 |0.736
```

Note `id=37` is a `bonus_kill` marked wrong — worth checking too, don't
assume every remaining bug is bullet_kill-shaped.

### Methodology that worked all session — reuse it

For each suspicious clip: don't just eyeball the exported clip video.
Trace the *raw* per-tick combo/timer values around the event directly
from the source video using `hud_reader.sample_video`'s building
blocks (`read_combo`, `read_timer`, `is_valid_hud_frame`,
`is_popup_visible`) at fine granularity (every frame, not just every
0.2s tick), and look for run-length patterns (stable value vs. a
genuine transition vs. a suspiciously short blip). This is exactly how
all four fixes above were found — confidence numbers alone are not
enough; pull actual frame images (`cv2.imwrite` a crop, then view it)
when the numeric trace doesn't make sense, the same way the map-pickup
popup and the "COMBO"-label bleed were both found by looking at pixels,
not just re-reading code.

Standalone investigation scripts from this session (ad hoc, not part
of the test suite, safe to delete or ignore if starting fresh — they
lived in the harness's scratchpad, likely gone in a new session, but
the pattern is worth recreating): a frame-by-frame HUD dumper and a
run-length-encoded combo/timer tracer, both taking a video path and a
center timestamp. Recreate them if useful; they're short (~40 lines).

## Ephemeral files — will NOT exist in a new session

Everything under `/tmp` is gone once this session ends, including both
downloaded source videos and all manifests/clips from every pipeline
run this session. **To pick this back up:**

```bash
mkdir -p /tmp/biomercs-footage
uv run yt-dlp -f 298 -o /tmp/biomercs-footage/source.mp4 \
  "https://www.youtube.com/watch?v=6y-6lH7SdJU"

mkdir -p /tmp/biomercs-footage2
uv run yt-dlp -f 298 -o /tmp/biomercs-footage2/source.mp4 \
  "https://www.youtube.com/watch?v=u9DA7ueGiH0"

mkdir -p /tmp/biomercs-footage3
uv run yt-dlp -f 298 -o /tmp/biomercs-footage3/source.mp4 \
  "https://www.youtube.com/watch?v=8ilpJYjIRtQ"

mkdir -p /tmp/biomercs-footage4
uv run yt-dlp -f 298 -o /tmp/biomercs-footage4/source.mp4 \
  "https://www.youtube.com/watch?v=zIMN3UNyo2s"

mkdir -p /tmp/biomercs-footage5
uv run yt-dlp -f 298 -o /tmp/biomercs-footage5/source.mp4 \
  "https://www.youtube.com/watch?v=HYXLHArtq1I"
```

Then regenerate manifests (deterministic — same code + same video means
identical `session_id`/`event_timestamp_s` pairs reappear, so the ids
referenced above will line up again). **Always `rm -rf` the output dir
first** if it might already exist from an earlier run this session —
`dataset_manifest.create_db` doesn't clear existing rows, only creates
missing directories, so re-running into a stale dir silently mixes old
and new clips (bit the previous session once already):

```bash
rm -rf /tmp/biomercs-run /tmp/biomercs-run2 /tmp/biomercs-run3 /tmp/biomercs-run4 /tmp/biomercs-run5-new
uv run python -c "
from pathlib import Path
from biomercs_ml import pipeline
pipeline.run('/tmp/biomercs-footage/source.mp4', Path('/tmp/biomercs-run'), Path('/tmp/biomercs-run/manifest.sqlite'))
pipeline.run('/tmp/biomercs-footage2/source.mp4', Path('/tmp/biomercs-run2'), Path('/tmp/biomercs-run2/manifest.sqlite'))
pipeline.run('/tmp/biomercs-footage3/source.mp4', Path('/tmp/biomercs-run3'), Path('/tmp/biomercs-run3/manifest.sqlite'))
pipeline.run('/tmp/biomercs-footage4/source.mp4', Path('/tmp/biomercs-run4'), Path('/tmp/biomercs-run4/manifest.sqlite'))
pipeline.run('/tmp/biomercs-footage5/source.mp4', Path('/tmp/biomercs-run5-new'), Path('/tmp/biomercs-run5-new/manifest.sqlite'))
"
```

Note: `/tmp/biomercs-run5` (no suffix) was an old, unrelated stale
run from a much earlier session -- the fifth cross-validation video
added this session uses `/tmp/biomercs-run5-new` to avoid colliding
with it. Don't reuse the plain `biomercs-run5` name for this video.

Each `pipeline.run` now takes **~2 minutes** on a ~10min video (#6's
CPU parallelization across `sample_video`, landed a few sessions ago --
this paragraph is historical, kept for the older `SAMPLE_VOTE_FRAMES`/
calibration-speedup context, not the current timing). Progress
prints every ~10% of video duration processed (`hud_reader.
sample_video`'s own logging, added a few sessions ago so a run is never
silent) — this
runtime should drop substantially; re-measure and update this note
once it does.

## Decisions already made — do not re-ask

- **Inline execution** (`superpowers:executing-plans`, not
  subagent-driven), chosen at project start. Still the mode.
- **Never use `Agent` with `subagent_type: "fork"`** — the user has
  reacted with real frustration to this across multiple past sessions.
  Regular (non-fork) subagents are fine if truly needed; fork
  specifically is not.
- **Map-pickup handling: detect nearby popup, discard the group** (not
  subtract the exact amount, not a full holistic-window redesign) — see
  `docs/superpowers/DECISIONS.md` for the full reasoning and the
  ~2-second timing-gap evidence that ruled out the subtract approach.
- **Digit-margin fix: clamp per-slot, never shrink below nominal box**
  — a stricter global clamp was tried first and broke matching
  entirely for tightly-packed slots; see DECISIONS.md.

## Important behavioral notes

- **Short in-chat design + explicit approval before implementing**
  worked well again this session for every fix — including catching a
  wrong initial hypothesis (map-pickup "subtract" approach) before
  wasting implementation effort on it, purely by presenting concrete
  timing evidence and asking before coding. Keep doing this.
- **The user reviews in fine technical detail and pushes back with
  real data.** This session's biggest fix (`7b3dedf`) came directly
  from the user manually reviewing a clip and immediately spotting
  "this is impossible" from raw domain knowledge (150 enemies total,
  9 simultaneous kills at combo 149 doesn't add up) — before any
  numeric investigation happened. Take these observations seriously
  and investigate them concretely; they've had a 100% hit rate at
  surfacing real bugs so far, including ones automated review missed
  (the mistyped-review-answer report and the "too many bullet kills"
  observation that opens this handoff's next step).
- **TDD throughout, no exceptions** — every fix this session had a
  failing test written first, reproducing the exact real-footage bug
  (often as a checked-in fixture frame, e.g.
  `tests/fixtures/frames/combo_149_adjacent_digit_bleed_frame.png`),
  watched fail, then the minimal fix. Keep doing this — it's what made
  it possible to verify each fix in isolation before moving to the
  next.
- One commit per fix, with a full "why" in the commit message, plus a
  `docs/superpowers/DECISIONS.md` entry for anything non-obvious.
  Continue this pattern.

## Working style notes

- The user (11 years of software engineering experience, new to
  ML/CV specifically, top-5-world Mercenaries player with 2 standing
  Chris STARS world records) wants to actually learn through this —
  don't over-abstract or skip past the "why" when implementing.
- Portuguese/English mixed conversation is normal; match whichever the
  user uses in a given message.
- Follow `AGENTS.md` (guard clauses, type hints everywhere, dataclasses
  for structured data, no filler comments, centralize constants in
  `config.py`, etc).
