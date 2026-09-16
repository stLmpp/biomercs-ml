# Handoff: biomercs-ml — kill-labeling data pipeline

Paste this whole file as your first message in a new session to continue.

## What this project is

`biomercs-ml` (repo: https://github.com/stLmpp/biomercs-ml, public,
cloned at `/Users/stlmpp/projects/biomercs-app/biomercs-ml`) is a
personal ML-learning project: turn Resident Evil 5/6 "The Mercenaries"
gameplay video into a labeled dataset, starting with one target —
classifying each kill as `bullet_kill` (gunfire only, no time bonus),
`bonus_kill` (melee/dash finisher, +5s to the run clock), or `mixed`
(a simultaneous group of both). The game's own HUD (run timer + combo
counter) gives free, reliable ground truth for this specific label, via
per-digit template matching (not OCR — the game renders a fixed font,
so classical template matching is more reliable and needs no
dependency).

This is a sub-project of a bigger, only-loosely-scoped ambition
(eventually: compare the author's own runs against world-record runs
and get coaching feedback) — **don't expand scope toward that goal**,
this plan is deliberately narrowed to just the data pipeline.

Read before doing anything else, in this order:
1. `docs/knowledge_base/README.md` and both files it points to — domain
   knowledge (game mechanics) and deferred ideas. Treat the mechanics
   file as ground truth; it comes from the author's own top-level
   competitive experience, don't second-guess it.
2. `docs/superpowers/specs/2026-09-16-kill-labeling-pipeline-design.md`
   — the approved design spec.
3. `docs/superpowers/plans/2026-09-16-kill-labeling-pipeline.md` — the
   approved, fully-detailed 11-task TDD implementation plan. **All 11
   tasks are now implemented, tested, and committed** (see below —
   this plan is DONE as a checklist; what's left is real-footage
   validation, not new tasks from this file).
4. `AGENTS.md` — Python/coding conventions for this repo (added this
   session at the user's request). Follow it.

## Status as of this handoff

**All 11 plan tasks are implemented, tested, and committed on `main`**
(worked directly on `main`, no worktree — user declined isolation when
asked). Full test suite: `uv run pytest -v` → **45 passed**. Run it
first thing to confirm nothing's broken.

Layout note: `uv init` produced a **src-layout**
(`src/biomercs_ml/...`), not the flat `biomercs_ml/...` the plan's
prose implies — this is fine, just don't be surprised by the path.

### What exists
- Full pipeline: `hud_reader` → `event_detector` → `auto_labeler` →
  `clip_extractor` → `dataset_manifest` → `downloader` → `pipeline.py`
  (orchestrates all of them). All in `src/biomercs_ml/`.
- All ten previously-missing digit templates
  (`templates/digits_timer/{4,6,7,9}.png`,
  `templates/digits_combo/{1,2,4,6,8,9}.png`) were sourced this
  session from a **downloaded YouTube video** (see "Ephemeral files"
  below — the user explicitly gave the URL and consented to the
  download, in line with the spec's "downloader" stage and its
  per-video risk-acceptance note). Templates themselves are committed
  to the repo and persist normally.
- `scripts/review_sample.py`: manual review helper, now asks `y/n`
  after each clip and **persists the answer** to a new nullable
  `review_correct` column on the `clips` table (via
  `dataset_manifest.record_review`, auto-migrated in by `create_db`).
  Also auto-closes the QuickTime window between clips (assumes
  QuickTime as default `.mp4` handler — ask the user if that's wrong
  for them).
- `AGENTS.md` at repo root — Python/general coding conventions,
  written at the user's request this session.

### Debugging journey this session (all fixed, all committed — read
this before touching `hud_reader.py` again, it explains *why* the
code looks the way it does)

Validating end-to-end against real (downloaded) footage surfaced a
chain of real bugs, each found and fixed with actual evidence from the
footage, not guesswork:

1. **Per-video HUD offset.** A different capture/encode pipeline than
   the calibration screenshots rendered the "COMBO" label ROI a few
   pixels off, even at the same resolution → `hud_reader.find_best_offset`
   + `_calibrate_offset` search for it once per video.
2. **False-positive calibration from a pre-gameplay intro.** The first
   ~12s of the test video had no HUD at all, but searching
   `(2*radius+1)^2` candidate positions per frame gave enough shots for
   one to clear the ordinary confidence bar by chance → added a much
   stricter `CALIBRATION_MIN_CONFIDENCE` and a longer scan budget
   (`CALIBRATION_MAX_FRAMES`).
3. **Single-frame animation artifact.** A combo-counter "pop" animation
   on update transiently rendered the label at a different offset than
   its static resting position, and that one lucky frame was trusted
   immediately → require the same offset to repeat across
   `CALIBRATION_MIN_VOTES` independent frames (majority vote, not
   first-hit) via `collections.Counter`.
4. **Wrong assumption that the offset applies uniformly.** Applying the
   *label's* calibrated offset to the *digit slots* broke otherwise-
   correct reads — proven on real data: combo digit slots read `141`
   correctly at offset `(0,0)` (conf 0.92) but broke at the label's
   `(7,0)` correction (conf 0.55) on the exact same frame → offset is
   now applied **only** to `is_valid_hud_frame`, never to
   `read_timer`/`read_combo`. Covered by a wiring-contract test in
   `test_hud_reader_video.py` using `unittest.mock.patch`.
5. **Digit misreads from per-frame compression jitter.** Compressed
   video can render a digit a few px off from its calibrated slot
   purely from encoding noise — proven: the same digit template scored
   `0.99` against its own source frame but only `0.20–0.43` against
   *other* frames of the identical digit in the identical slot. Fixed
   by matching against a `DIGIT_SEARCH_MARGIN_PX`-padded crop and
   scoring via `result.max()` instead of `result[0,0]` (OpenCV's own
   sliding correlation does the local search in one call; behavior is
   unchanged when crop size == template size, so this was a safe,
   non-breaking change).
6. **Plausibility guard.** Even after (5), a stray misread can still
   produce a nonsense jump (e.g. combo `026` misread as `886` →
   apparent "100 simultaneous kills," physically impossible given the
   game's fixed enemy pool). `event_detector.detect_kill_groups` now
   drops any group above `config.MAX_PLAUSIBLE_GROUP_SIZE` as a second,
   independent line of defense — this doesn't fix misreads, it just
   stops them from polluting the dataset.

Each of the above has its own test file/case (`test_hud_reader_offset.py`,
`test_hud_reader_calibration.py`, the wiring-contract test in
`test_hud_reader_video.py`, the jitter test in `test_hud_reader_digits.py`,
the plausibility test in `test_event_detector.py`) — read those before
changing related code, they encode *why*, not just *what*.

## Open problem — NOT yet resolved, this is the actual next step

After all the above fixes, the user ran a real manual review (30 clips,
`scripts/review_sample.py` against a fresh pipeline run) and got
**46.7% agreement (14/30 correct) — far below the spec's >98% target.**

The pattern is stark and was confirmed via SQL over the backfilled
`review_correct` column:

```
bonus_kill | correct   | 14
bonus_kill | incorrect | 8
bullet_kill| incorrect | 6   <- 0/6 correct
mixed      | incorrect | 2   <- 0/2 correct
```

**Every single `bullet_kill` and `mixed` label in this sample was
wrong; `bonus_kill` was right ~64% of the time.** Given the knowledge
base's own description of Wesker's meta (2 shots + dash finisher =
*always* a bonus kill, "the dominant character for maximizing score"),
it's very plausible that genuine `bullet_kill`s are rare-to-nonexistent
in this footage, and the pipeline is systematically miscomputing the
timer delta so that real bonus kills look like `bullet_kill` (or
`mixed`) instead. This is **not** a digit-misread problem in the sense
of (5)/(6) above — digit robustness was already improved this session
and confidences on the wrong clips are mostly fine (0.60–0.85). The
likely suspect is somewhere in `auto_labeler.label_kill_group`'s delta
math, or in how `elapsed_s` behaves across a gap of dropped/invalid
samples between two valid ones (a real gap could make genuine bonus
seconds net out to look like ~0 if the decay and bonus partially
cancel over a longer real interval than the nominal 0.2s).

An investigation script finished just as the user asked for this
handoff (it re-runs `sample_video` + `event_detector` and matches the
specific wrong clips' `(session_id, event_timestamp_s)` to their raw
`KillGroup` — `group_size`, `timer_before_s`, `timer_after_s`,
`elapsed_s` — to see the actual delta math for each). **The result is
a strong, concrete lead:**

```
session=9   ts=58.2   group_size=2  timer_before=184.0 timer_after=184.0 elapsed_s=0.60  -> bullet_kill (WRONG per review)
session=17  ts=79.0   group_size=8  timer_before=198.0 timer_after=198.0 elapsed_s=0.20  -> bullet_kill (WRONG)
session=50  ts=132.4  group_size=9  timer_before=200.0 timer_after=200.0 elapsed_s=0.20  -> bullet_kill (WRONG)
session=73  ts=158.8  group_size=9  timer_before=218.0 timer_after=218.0 elapsed_s=0.20  -> bullet_kill (WRONG)
session=94  ts=197.4  group_size=8  timer_before=286.0 timer_after=286.0 elapsed_s=0.20  -> bullet_kill (WRONG)
session=246 ts=450.4  group_size=4  timer_before=489.0 timer_after=497.0 elapsed_s=2.80  -> mixed n_bonus=2 (WRONG)
session=255 ts=463.2  group_size=1  timer_before=494.0 timer_after=494.0 elapsed_s=0.60  -> bullet_kill (WRONG)
session=261 ts=476.4  group_size=11 timer_before=501.0 timer_after=511.0 elapsed_s=0.60  -> mixed n_bonus=2 (WRONG)
```

**In 5 of 8 cases, `timer_before_s == timer_after_s` exactly** — not
just "decayed as expected," genuinely *frozen* — despite `group_size`
being 8 or 9 (a whole room of enemies dying together via chained
dashes, per the Wesker mechanic in the knowledge base). That's the
real lead: this isn't a digit-misread (confidences are fine, values
are internally consistent integers) and it isn't `elapsed_s` being
miscomputed. The most likely explanation is a **display-animation lag**
— recall `tests/fixtures/frames/sample_frame_01.png` shows the timer
with a separate floating "+05 Sec." popup next to it (see the spec's
own "Bonus kills vs. bullet kills" section), implying the bonus time
isn't folded into the base timer number instantly. If a big kill group
queues several +5s additions that animate in one at a time, the very
next 0.2s sample can land before *any* of that animation has applied,
making a real multi-bonus-kill group look like zero-bonus.

If that diagnosis holds, the fix is **not** in `auto_labeler`'s delta
formula — it's that `event_detector`/`auto_labeler` currently compares
the timer at the *immediately adjacent* sample, when the spec's own
wording ("looks at the timer_value delta **shortly after** the event")
implies some deliberate lookahead is needed: sample the timer again a
bit later (e.g. 1-2s after the event) once the bonus animation has had
time to land, rather than using the very next raw sample. This would
be a real design change to how `auto_labeler` gets its `timer_after_s`
— worth a short design confirmation with the user before implementing
(this session's pattern of proposing a short in-chat design and
getting explicit approval worked well throughout, keep doing that).

**Not yet confirmed** — this is a strong hypothesis from real data,
not yet verified by directly watching the corresponding clips frame-
by-frame to confirm the animation-lag theory (e.g. scrub clip
`source_17_79.0.mp4` and watch exactly when the timer visually updates
relative to the kill). Do that confirmation before committing to a
fix.

The wrong clips to investigate (id, label, n_bonus, n_bullet,
session_id, event_timestamp_s, confidence) — same data as above, kept
for cross-reference with the manifest:

```
4 |bullet_kill|0|2|9  |58.2 |0.789
8 |bullet_kill|0|8|17 |79.0 |0.699
14|bullet_kill|0|9|50 |132.4|0.848
19|bullet_kill|0|9|73 |158.8|0.684
24|bullet_kill|0|8|94 |197.4|0.620
40|bullet_kill|0|1|255|463.2|0.604
38|mixed      |2|2|246|450.4|0.682
42|mixed      |2|9|261|476.4|0.644
11|bonus_kill|1|0|45 |122.2|0.600
12|bonus_kill|1|0|46 |124.0|0.751
18|bonus_kill|1|0|69 |154.0|0.782
20|bonus_kill|1|0|81 |173.4|0.804
26|bonus_kill|1|0|100|216.0|0.798
30|bonus_kill|1|0|146|295.4|0.707
39|bonus_kill|1|0|251|455.4|0.713
47|bonus_kill|1|0|306|553.6|0.773
```

(For reference, the ones marked correct: bonus_kill ids 10, 16, 21, 22,
23, 27, 28, 31, 35, 36, 37, 43, 46, 50.)

**Next step:** confirm the animation-lag hypothesis by watching one or
two of the actual wrong clips (paths in the manifest, e.g.
`source_17_79.0.mp4` for the `session=17 ts=79.0` case above) and
checking whether the timer visually updates *after* the clip's visible
kill moment. If confirmed, design (with the user, short design +
approval first) a fix to how `auto_labeler` obtains `timer_after_s` —
likely sampling further ahead of the event rather than using the
immediately-next raw sample — then redo a manual review to check
agreement actually improves toward the spec's >98% target.

## Ephemeral files — will NOT exist in a new session

Everything under the harness's scratchpad directory
(`/private/tmp/claude-501/.../scratchpad/...` — the exact UUID segment
is session-specific and will differ) and under `/tmp` is **gone** once
this session ends. That includes:
- The downloaded source video (`.../scratchpad/footage/source.mp4`).
- All pipeline run outputs (`run_output`, `run_output2` .. `run_output5`
  — only `run_output5` matters, it has the `review_correct` backfill).
- `/tmp/rootcause.txt` (the in-progress investigation's output file).

**To pick this back up**, re-download the same video (the user
explicitly provided this URL and consented; format 298 is the
1280x720 60fps video-only stream that matches the calibration
resolution exactly):

```bash
mkdir -p /tmp/biomercs-footage
uv run yt-dlp -f 298 -o /tmp/biomercs-footage/source.mp4 \
  "https://www.youtube.com/watch?v=6y-6lH7SdJU"
```

Then re-run the pipeline to regenerate a manifest + clips (paths are
illustrative, use whatever local scratch dir your session provides):

```bash
uv run python -c "
from pathlib import Path
from biomercs_ml import pipeline
pipeline.run('/tmp/biomercs-footage/source.mp4', Path('/tmp/biomercs-run'), Path('/tmp/biomercs-run/manifest.sqlite'))
"
```

This is deterministic (same video, same code) so `session_id`/
`event_timestamp_s` pairs for the wrong clips listed above should
reappear identically, letting you pick the investigation back up using
the ids/timestamps already captured.

## Decision already made — do not re-ask

The user chose **inline execution** (`superpowers:executing-plans`,
not subagent-driven) back at the very start of this project, when
explicitly asked. Continue working inline in this session unless the
user says otherwise.

## Important behavioral notes

- **Never use `Agent` with `subagent_type: "fork"`** for anything in
  this project — the user has reacted with frustration to this
  multiple times across sessions ("don't use fork, please" → used
  anyway → "again man", "everytime", "you use forks"). Regular
  (non-fork) subagents are fine if truly needed; fork specifically is
  not.
- When something looks bounded (a well-scoped change to code that
  already exists), the user responds well to a **short in-chat design
  + explicit approval before implementing** (this pattern was used
  repeatedly and successfully this session for the offset fix, the
  calibration fix, and the digit-robustness fix) — keep doing this
  rather than silently redesigning things.
- The user reviews things in fine technical detail and will push back
  with real data when a fix doesn't actually work (e.g. "0 samples"
  after a fix that looked right in isolation) — verify against the
  real video, not just unit tests, before declaring a real-data bug
  fixed. Unit tests + a real end-to-end run both matter here.

## Working style notes

- The user (11 years of software engineering experience, new to ML/CV
  specifically) wants to actually learn ML through this, not just get
  a finished pipeline — don't over-abstract or skip past the
  "why" when implementing.
- Portuguese/English mixed conversation is normal with this user; match
  whichever they use. Most of this session was in Portuguese.
- The user asked for and got an `AGENTS.md` with Python/general coding
  conventions this session — follow it (guard clauses over nested
  ifs, type hints everywhere, dataclasses for structured data, no
  filler comments, etc).
