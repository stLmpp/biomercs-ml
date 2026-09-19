# Known Bugs

Open issues in the biomercs-ml pipeline, one entry per distinct problem. Each
has a short kebab-case **slug** so we can reference it in conversation/commits
without re-describing it ("that's `combo-2-vs-8-misread`" instead of "the
thing from video5 id=6").

This file is an **index**, not the detailed evidence — full reasoning, real
footage citations, and failed-attempt history live in `DECISIONS.md`; each
entry below points at the section title to search for. When a bug gets fixed,
move its entry to `FIXED_BUGS.md` (keep the same slug).

Status values: **OPEN** (confirmed, unfixed) · **UNCONFIRMED** (single
instance, not yet proven as a pattern) · **LATENT** (a quality gap, not yet
an observed failure) · **ACCEPTED** (deliberately not fixing — caught
downstream, or not worth the complexity).

★ = currently one of the highest-leverage items (biggest effect on dataset
accuracy).

## Digit-matching / templates

### `combo-9-vs-8-misread`
**OPEN.** Smaller/rarer instances of the same family as
`combo-2-vs-8-misread`: adding real "8" curation samples once broke a
"149" read into "148"; a separate real case misread `119` as `118`
(t=473.0). **A geometric tiebreak attempt (`bottom_loop_closure_score`,
9's tail never closing into a second loop) was tried and reverted** --
real-footage A/B verification on video1 found it doesn't discriminate a
real 9 at all; it fires on almost any real digit (confirmed real `0`,
`2`, `3`) whenever raw matching already mismatches that digit as "8"
under real degraded footage (dark lighting, motion blur), because those
same conditions also erase/shrink the bottom hole this feature measures
-- see DECISIONS.md § "a third geometric tie-breaker... reverted after
real-footage verification found it doesn't hold".
- DECISIONS.md § "video5 id=6's overcount root-caused...", lines ~1738-1745

### `combo-6-vs-0-tens-misread`
**OPEN, partial improvement.** video1 t=252.4, true `064` — tens digit
"6" used to misread as "0" on every frame in the tick's 11-frame vote
burst. After removing `6/a` (see `combo-template-defects` in
FIXED_BUGS.md) and adding 5 new real-footage "6" samples (one per
video), the single frame at t=252.400 itself now reads `064` correctly
(0.821 confidence). **But the tick's majority vote still fails** — 4 of
11 frames in the burst now read `_84` (tens misread as "8", not "0"
anymore) vs. only 1 reading the correct `_64`. Progress (one real
confusion axis closed), not a fix (the vote still lands wrong, just via
a different wrong digit).
- DECISIONS.md § "a systematic crop-bleed audit... and the fixture
  alignment bug it uncovered"

### `combo-8-clean-frame-overmatch`
**UNCONFIRMED / possibly ACCEPTED.** t=124.0: a completely clean,
non-chaotic frame ("029 COMBO", Wesker standing still) confidently
misreads as "889" — even after curation added real samples for
1/2/4/6/9 (no real "8" footage was ever found in either video; "8" uses
one atlas-sourced sample). Caught downstream by
`config.MAX_PLAUSIBLE_COMBO_VALUE=150`, not corrected at the pixel level.
Not conclusively determined whether this is a permanent pixel-level limit
(like the timer's t=408.8 overexposed frame) or just needs more sample
diversity.
- DECISIONS.md § "Re-review surfaces a second, distinct bug...", § "then a
  much bigger finding..."

### `combo-motion-blur-digit-flicker` (formerly "Bug B")
**OPEN.** A *sustained* (not transient), high-confidence (0.75-0.83)
misread of combo's hundreds digit ("8"/"9") and ones digit ("5"/"6"/"9")
during chaotic/motion-blurred combat, lasting ~1s — long enough that no
neighbor-clamping guard can catch it (the neighbors are wrong too). Same
underlying family as `combo-2-vs-8-misread` / `combo-9-vs-8-misread`, just
first documented under a different name.
- DECISIONS.md § "Frame-by-frame tracing of the 8 wrong video-2 clips
  finds THREE distinct root causes, not one"

### `timer-3-vs-8-9-misread`
**OPEN.** The timer font (different visual style, orange digital-clock)
has its own "3"-vs-"8"/"9" confusion. The `waist-notch` geometric fix that
resolved this for the combo font (see `combo-3-vs-8-9-misread` in
FIXED_BUGS.md) does **not** transfer — real "3" scores overlap real "8"
directly, no margin. Root cause: the timer glyph doesn't fill its 40×76
bounding box the way combo's tight crops do, so equal-thirds banding
straddles the real notch instead of isolating it. Two follow-up variants
(bbox-relative thirds, peak-recession) also failed. Needs a genuinely
different approach: stroke-width profiling, Hu-moment contour descriptors,
or a small trained classifier — none attempted yet.
**2026-09-19 reframe:** at least the worst instance (video4 t=641.8, tens-
of-minutes "0" -> "8", value `5364`) is *not* font-shape ambiguity: the
timer digits are translucent and a background beam sweeps across the "0"
for several consecutive frames, so the glyph genuinely looks like an "8"
(defeats the 11-frame vote too). Better shape features won't fix that
class; its *symptom* (spurious sessions) is now handled by the spike
guard (see `timer-noise-session-fragmentation`), but the misread itself
still happens. Images: `tmp\biomercs-verify\video4_burst_641\`.
- DECISIONS.md § "the waist-notch feature tested against the timer font on
  real footage and found NOT to hold..."

### `timer-single-sample-templates`
**LATENT.** `templates/digits_timer/*` still has exactly 1 sample per
digit, 0-9 — never got the multi-sample curation the combo digits got.
Won't by itself fix `timer-3-vs-8-9-misread` (already shown to be more
than a coverage gap), but is a latent risk across every timer digit pair,
not just 3-vs-8/9.
- DECISIONS.md § "the timer-cross-check idea investigated and found NOT
  independent..."

### `combo-template-defects` (partially fixed, see FIXED_BUGS.md)
**LATENT, residual.** `digits_combo/0/e.png` is still outright corrupted
(not a real "0"), but scores low enough (0.30-0.34) to be currently
harmless — left as-is. The left-edge crop-bleed defect on `4/a`, `6/a`,
`8/a`, `9/a` is now fixed (removed + backfilled with real-footage
samples); see `combo-template-defects` in FIXED_BUGS.md for that part.
- DECISIONS.md § "a systematic crop-bleed audit... and the fixture
  alignment bug it uncovered"

## Event detection / kill-grouping

### `low-kill-recall` ★★ (biggest problem in the project)
> **Ninth session, user decision:** the popup-driven fix is the LAST
> OCR/template attempt. If it fails the benchmark/A-B, abandon HUD-OCR and
> go to the user's original plan (real ML with reinforcement + the user's
> manual review). See DECISIONS.md § 2026-09-19 (a ninth session).

**OPEN.** A run has **~150 kills**; the pipeline emits ~7 clips/video
(36 clips across all 5 videos post-session-fix, 16 before) -- roughly 5%
recall. The user's bar: detect at least ~140 for it to start being good.
Review rounds only score clips that exist, so they hide this. Ground
truth for video4 t=480-650s: **49 real kills (36 bonus + 13 bullet)**
(times/list in DECISIONS.md § 2026-09-19; absolute time ~= 480 + clip
seconds - 3).
Measured causes: the combo HUD is readable in only **44%** of ticks (the
game hides it between kills), and `detect_kill_groups` groups by combo
rise between *adjacent kept samples*, so kills seconds apart merge into
one group (e.g. combo 104@497.7s -> 108@503.9s = 4 kills, 1 clip). Meanwhile
the `+05 sec.` popup -- already computed each tick by `is_popup_visible`,
but only used to exclude map pickups -- gave 24 episodes with **0 orphans**
and matched 29/32 truth bonus-seconds. **Constraint:** simultaneous bonus
multi-kills show only ONE popup, so the count must come from the timer
jump (+5 each). **Agreed direction (not implemented):** build a recall
benchmark from the 49-kill truth first, then popup-driven bonus detection
with combo as the secondary (bullet) signal.
- DECISIONS.md § "2026-09-19 (an eighth session)" -> "THE BIG FINDING"

### `fabricated-bullet-count-on-bonus-kill` ★
**OPEN** (umbrella/symptom). `auto_labeler.label_kill_group` computes
`n_bullet = group_size - n_bonus` as a pure, never-independently-verified
remainder. Across every review round in the project (23-clip statistical
baseline), 14/15 wrong clips had true `n_bullet=0` — a real bonus kill
getting a fabricated bullet count is the dominant error class. Several
past contributors are now fixed (`bug-a-timer-delta-desync`,
`group-size-overestimation-anchors`, `combo-2-vs-8-misread` in
FIXED_BUGS.md); needs a fresh review round to confirm whether a smaller
remaining driver still shows up now that `combo-2-vs-8-misread` is fixed.
**2026-09-19 fresh rounds:** round 1 (pre-session-fix) 3/16 correct; all 5
wrong clips outside video4 had true `n_bullet=0` (so `combo-2-vs-8` did
not visibly help). Round 2 (post-session-fix, partial): 5/17 correct, 7 of
12 wrong with true `n_bullet=0`, 5 with true `n_bullet>0`. The dominant
underlying driver is now understood to be `low-kill-recall` (adjacent-
sample grouping merges kills seconds apart into one group whose bullet
count is just `group_size - n_bonus`), not a digit misread -- fix that
first, then re-measure this.
- DECISIONS.md § "Re-review surfaces a second, distinct bug...", § "the
  timer-cross-check idea investigated..." (23-clip baseline table)

### `total-phantom-kill-events`
**UNCONFIRMED.** A detected clip with a real-looking label but true
ground truth `(0,0)` — no kill happened at all. Seen twice project-wide
(video5 `id=3` t=341.8: `mixed(1,6)` vs. true `(0,0)`, confidence 0.139;
one earlier, much-older instance). Root cause never traced. Working
theory: `MAX_PLAUSIBLE_COMBO_VALUE` rejecting more readings thinned sample
density enough to open gaps in the dip/reversion guards.
- DECISIONS.md § "a fifth video, cross-validation"

### `video4-undercount-id2`
**UNCONFIRMED**, single instance. t=490.7: detected `(1,0)`, true
`(3,0)` — the first-ever *undercount* project-wide (every other wrong
clip has been an overcount). Didn't recur in video5's review round.
Plausible unconfirmed hypothesis: denser sampling now splits a real
multi-kill chain across a spurious session boundary
(`timer-noise-session-fragmentation`).
- DECISIONS.md § "video4's post-calibration-fix clips reviewed"

### `video4-wrong-kind-id5`
**UNCONFIRMED**, single instance. t=547.5: detected `bonus_kill(1,0)`,
true `(0,1)` — a genuine bullet kill misclassified as pure bonus. The only
instance project-wide that breaks the otherwise-universal "every
correction has true n_bullet=0" pattern. Didn't recur in video5.
- DECISIONS.md § "video4's post-calibration-fix clips reviewed"

### `group-size-video3-overshoot`
**OPEN**, minor. video3 t=536.5: a group that used to be silently dropped
entirely (implausible-jump cap) is now recovered, but overshoots by one
spurious bullet kill (`mixed(1,1)` detected, true `(1,0)`). Net
improvement over losing the event outright, not a full fix. Same
fabricated-bullet-count family.
- DECISIONS.md § "Manual review of the fix's clips"

### `multi-kill-adjacent-pair-gap-fragility`
**OPEN, promoted from LATENT 2026-09-19 -- this is the mechanism behind
`low-kill-recall`** (combo readable only 44% of ticks, so "adjacent" kept
samples are often seconds apart). Original description: `detect_kill_groups` only ever compares *adjacent* samples
within a session; any long stretch with zero valid samples between two
individually-correct reads gets treated as one simultaneous group,
however many real separate kills happened inside it. The one observed
instance's actual root cause (`hud-offset-calibration-...`, see
FIXED_BUGS.md) is fixed, but the general structural assumption itself was
never hardened and could resurface under a different gap-inducing cause.
- DECISIONS.md § "a fourth video, cross-validation"

## Session / timer noise

### `timer-noise-session-fragmentation` ★
**MOSTLY FIXED for the tested window (2026-09-19); residual OPEN.** Real
cause turned out to be (1) `SESSION_RESET_DROP_S`/`SESSION_RESET_JUMP_S`
(1s/25s) being far tighter than real read noise and real stacked bonuses
-> now 30s/120s (a round always restarts at 2:00, so real transitions are
hundreds of seconds), plus (2) isolated single-tick garbage timer values
caused by background scenery bleeding through the timer's translucent
digits (e.g. tens-of-minutes "0" read as "8" -> `5364`) -> now suppressed
by `hud_reader._is_spurious_timer_spike` (two-directional neighbor check).
Video4 t=480-650s went from 52 spurious session splits to **1** (truth:
1). **Residual:** clip filenames from the post-fix run still carry
`session_id`s of 47/49/55/98, so fragmentation remains elsewhere in the
videos -- not yet investigated (find where, using the raw-tick method in
DECISIONS.md § 2026-09-19). Full fix details in FIXED_BUGS.md
(`timer-session-thresholds-and-spike-guard`).

**Original description (pre-fix):** Timer readings go to garbage
4-digit values in specific chaotic windows (not just a wrong-but-plausible
digit). `is_new_session`'s jump/drop detection fires on this noise
constantly, fragmenting one continuous real sequence into many spurious
single-tick sessions — which directly undermines `detect_kill_groups`
(only ever compares samples within one session). First flagged
2026-09-16, re-flagged across nearly every session since. Later
understood to be *driven by the same digit-8 confusion corrupting the
timer font* — its ultimate fix is coupled to `timer-3-vs-8-9-misread`.
One specific symptom (the dip-guard's blindness exactly at spurious
session boundaries) is fixed (`bug-c-session-boundary-blind-guard`), but
the over-eager splitting itself was never hardened.
- DECISIONS.md § "Map time-bonus pickups vs. kill bonuses" (first flagged),
  § "Re-review surfaces a second, distinct bug..." (most fully
  characterized), § "the timer-cross-check idea investigated..." (root
  cause link to digit-8)

## Process / tooling (not correctness bugs, but worth tracking)

### `stale-output-dir-mixes-review-rows`
**ACCEPTED**, operational gotcha. Re-running `pipeline.run` into an
existing output dir within the same session does not clear prior rows
(`dataset_manifest.create_db` only creates missing directories). Bit the
project twice. Always `rm -rf` the output dir before re-running.
- DECISIONS.md § "Re-ran the fixed pipeline, re-reviewed..."

### `windows-path-and-shell-gotchas`
**ACCEPTED**, operational (the project now runs on Windows; older docs
assume macOS). (1) Git Bash's `/tmp` is `C:\Users\<u>\AppData\Local\Temp`,
but a native-Windows Python `Path('/tmp/x')` resolves to `D:\tmp\x` (drive
root) -- so a script run via `uv run python` silently reads/writes a
different directory than bash `ls /tmp` shows. Use project-relative
`tmp\...` paths (the videos live in `tmp\biomercs-footage*\`). (2)
`cv2.VideoCapture` on a missing file returns no frames instead of raising,
so `pipeline.run` on a wrong path "succeeds" with 0 clips and an empty
manifest -- check the clip count. (3) `rm -rf` doesn't work in PowerShell;
use `Remove-Item -Recurse -Force`. Skipping it re-triggered
`stale-output-dir-mixes-review-rows` (stale rows with dead paths crashed
`review_sample.py`; fixed by deleting rows whose file is missing, with
`.bak` copies; `review_sample.py ... unreviewed` resumes a pass).
- DECISIONS.md § "2026-09-19 (an eighth session)"

### `review-redo-does-not-clear-db-value`
**ACCEPTED.** Using the review script's redo (`r`) option to walk back an
already-recorded y/n into a skip does not clear the previously-written
`review_correct` DB value. Judged not worth the complexity for how rarely
this sequence happens.
- DECISIONS.md § "Manual review script: redo option"

### `frame-math-vs-watching-clip-discrepancy`
Methodology caveat, not a confirmed code bug. Frame-by-frame timer/combo
math from still frames suggested a 2-bonus-kill group (t=124.0) — watching
the actual clip showed it was really only 1. Recorded so pure numeric
tracing isn't trusted blindly again.
- DECISIONS.md § "Manual review of all 10 post-Bug-A clips..."
