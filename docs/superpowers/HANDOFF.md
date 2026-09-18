# Handoff: biomercs-ml — kill-labeling data pipeline

Paste this whole file as your first message in a new session to continue.

## Status as of 2026-09-17 (read this first, it supersedes the "Open
## problem" section below for the immediate next step)

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
```

Then regenerate manifests (deterministic — same code + same video means
identical `session_id`/`event_timestamp_s` pairs reappear, so the ids
referenced above will line up again):

```bash
uv run python -c "
from pathlib import Path
from biomercs_ml import pipeline
pipeline.run('/tmp/biomercs-footage/source.mp4', Path('/tmp/biomercs-run'), Path('/tmp/biomercs-run/manifest.sqlite'))
pipeline.run('/tmp/biomercs-footage2/source.mp4', Path('/tmp/biomercs-run2'), Path('/tmp/biomercs-run2/manifest.sqlite'))
"
```

Each `pipeline.run` takes ~2.5-3 minutes (majority-voting reads 3
frames per tick now, up from 1, so this is slower than early-session
runs — expected, not a regression).

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
