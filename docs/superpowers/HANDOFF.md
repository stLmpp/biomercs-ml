# Handoff: biomercs-ml — kill-labeling data pipeline

Paste this whole file as your first message in a new session to continue.
It's short on purpose — read the other docs only when you need their
detail:
- **`KNOWN_BUGS.md`** — open issues, one slug each (e.g.
  `combo-9-vs-8-misread`). Check here before starting any investigation.
- **`FIXED_BUGS.md`** — resolved issues, same slug convention. Check here
  before re-attempting something.
- **`DECISIONS.md`** — full technical reasoning/evidence behind every fix
  (real footage citations, alternatives considered, why). The two bug
  files above point into this one by section title.
- **`HISTORY.md`** — reverse-chronological session narrative (what
  happened, in what order). Archaeology, not a checklist — grep it, don't
  paste it.

## What this project is

`biomercs-ml` (repo: https://github.com/stLmpp/biomercs-ml, public,
cloned at `/Users/stlmpp/projects/biomercs-app/biomercs-ml`) is a
personal ML-learning project: turn Resident Evil 5/6 "The Mercenaries"
gameplay video into a labeled dataset, classifying each kill as
`bullet_kill` (gunfire only), `bonus_kill` (melee/dash finisher, +5s to
the run clock), or `mixed`. The game's own HUD (run timer + combo
counter) gives free, reliable ground truth via per-digit template
matching (not OCR). Sub-project of a bigger, loosely-scoped ambition
(eventually: compare the author's own runs against world-record runs) —
**don't expand scope toward that goal**, stay on the data pipeline.

Read before touching `hud_reader.py`/`event_detector.py`:
1. `docs/knowledge_base/README.md` and what it points to — domain
   knowledge (game mechanics). Treat it as ground truth (the author's own
   top-level competitive experience); don't second-guess it.
2. `AGENTS.md` — Python/coding conventions for this repo.
3. `KNOWN_BUGS.md` — don't re-investigate something already tracked.

## Current status (as of 2026-09-19, an eighth session) — READ THIS FIRST

**Environment is now Windows** (`D:\Projects\biomercs-ml`, PowerShell +
Git Bash). Source videos are already in the repo's gitignored
`tmp\biomercs-footage{,2,3,4,5}\source.mp4`; pipeline outputs in
`tmp\biomercs-run{,2,3,4,5}\`. Use project-relative `tmp\...` paths --
never `/tmp` (see `windows-path-and-shell-gotchas` in KNOWN_BUGS.md).
The user speaks Portuguese; replies in pt-br are welcome.

**Done this session (pushed, commits `5575ae3` + `1119d68`):**
`timer-noise-session-fragmentation` mostly fixed -- `SESSION_RESET_JUMP_S`
120 / `SESSION_RESET_DROP_S` 30 + `_is_spurious_timer_spike` guard; video4
t=480-650s went 52 -> 1 spurious sessions. `review_sample.py` is
cross-platform. See FIXED_BUGS.md `timer-session-thresholds-and-spike-guard`.

**UNCOMMITTED in the working tree:** `dataset_manifest.fetch_unreviewed`
(+ test in `tests/test_dataset_manifest.py`), `review_sample.py`'s new
`unreviewed` mode, and these doc updates. Suite: **127 passing**.
Commit them first (one commit for the code+test, one for docs).

**The real problem (new #1, `low-kill-recall` in KNOWN_BUGS.md):** a run has
~150 kills; the pipeline emits ~7 clips/video (~5% recall; user's bar is
>=140). Cause: combo HUD readable in only 44% of ticks and
`detect_kill_groups` groups by combo rise between adjacent kept samples,
merging kills seconds apart. The `+05 sec.` popup (already computed by
`is_popup_visible`, currently only used to exclude pickups) matched the
user's ground truth with 24 episodes / 0 orphans / 29 of 32 bonus-seconds.
**Simultaneous bonus multi-kills show only ONE popup**, so kill *count*
must come from the timer jump (+5 each).
**Ground truth:** 49 kills in video4 t=480-650s (list + the -3s time
alignment rule in DECISIONS.md § 2026-09-19).

**STRATEGIC DECISION (user, explicit, ninth session): popup-driven
detection is our LAST OCR/template attempt.** If it does not reach usable
recall on the benchmark + real-footage A/B, we STOP HUD/OCR work and return
to the user's original plan: a real ML model trained with reinforcement and
the user's own manual review as the signal. Don't start another round of
OCR heuristics/threshold tuning after this one -- escalate to the user. See
DECISIONS.md § "2026-09-19 (a ninth session)".

**Ninth session -- steps 1-2 below are DONE.** The recall benchmark exists:
`benchmarks/video4_t480-650.json` (49-kill ground truth),
`src/biomercs_ml/benchmark.py` (pure `score_detections`),
`pipeline.label_kill_groups` (shared with `pipeline.run`), and
`uv run python scripts/benchmark_recall.py [--refresh]` (raw samples cached
in `tmp\benchmark\`; ~2 min uncached, `--refresh` after touching
`hud_reader`). **Baseline before any detection change: recall 17/49 kills
(34.7%), precision 9/9 clips (100%), count accuracy 0/9 (0%)**, 416
samples, 1 session. A clip "covers" a kill if the kill falls in its
+-2s window (`CLIP_BEFORE_S`/`CLIP_AFTER_S`); recall is weighted by kill
count. Note recall 34.7% is *generous* (merged multi-kill clips still
cover neighbours) -- count accuracy is the honest failure signal.

**Start here next session:**
1. (done) `git status`, `uv run pytest`, commit pending work.
2. (done) Build the recall benchmark and get the baseline.
3. Then **popup-driven bonus detection** (one event per popup episode,
   bonus count from timer jump, bullet from combo rise minus bonuses).
   Short in-chat design + explicit user approval before implementing.
4. Later: find where the remaining session fragmentation is (clip names
   still show session ids 47/49/55/98); finish reviewing round-2 clips
   (`review_sample.py "tmp\biomercs-runN\manifest.sqlite" unreviewed`,
   runs 2-5 have unreviewed clips); re-measure
   `fabricated-bullet-count-on-bonus-kill` after recall is fixed.

## Previous status (2026-09-18, a seventh session) — superseded, kept for context

The combo font's `3`-vs-`8`/`9` misread is **fixed** (`combo-3-vs-8-9-misread`
in FIXED_BUGS.md — a geometric "waist notch" tie-breaker, TDD'd, 110
tests, verified via full real-footage A/B diff + user manual review, kept).
`combo-2-vs-8-misread` — the project's single biggest confirmed accuracy
driver, 4 prior failed fix attempts — is now also **fixed**
(`hud_reader.base_widen_score`, a second geometric tie-breaker on a
different axis than the "3" one: rightmost-ink jump back out to full
width just above the base bar. See FIXED_BUGS.md). Verified via a full
real-footage A/B diff across all five videos: 93% of all raw combo-tick
changes were exactly the target `_8 -> _2` pattern, manually confirmed
correct against several actual video frames. 117 tests passing.
The timer font's own version of the same confusion
(`timer-3-vs-8-9-misread`) is **still open** — the same fix doesn't
transfer there (see KNOWN_BUGS.md for why).

**(Superseded by the list above) old start-here list:**
1. **`fabricated-bullet-count-on-bonus-kill`** (KNOWN_BUGS.md) — now that
   `combo-2-vs-8-misread` (its main known driver) is fixed, a fresh
   review round would confirm how much it actually improved and whether
   a smaller remaining driver still shows up.
2. **`combo-9-vs-8-misread`** (KNOWN_BUGS.md) — same family, smaller/rarer
   instances, still open; not addressed by either geometric tie-breaker
   so far.
3. **`timer-3-vs-8-9-misread`** (KNOWN_BUGS.md) — needs a genuinely
   different approach (stroke-width profiling, Hu-moment contours, a
   small trained classifier), since the waist-notch geometry doesn't
   generalize to this font.

Full test suite: `uv run pytest -v` — should be 117 passing as of the seventh session (127 now, see the eighth-session status above). Run it first
thing to confirm nothing's broken.

## Ephemeral files — will NOT exist in a new session

**UPDATE (Windows, 2026-09-19): the section below is the old macOS/`/tmp`
flow.** On this machine the videos are already downloaded into the repo's
own gitignored `tmp\biomercs-footage{,2,3,4,5}\source.mp4`, so nothing
needs re-downloading. To regenerate outputs (PowerShell; clear old output
first or stale rows crash the review script):
```powershell
Remove-Item -Recurse -Force tmp\biomercs-run,tmp\biomercs-run2,tmp\biomercs-run3,tmp\biomercs-run4,tmp\biomercs-run5 -ErrorAction SilentlyContinue
uv run python -c "
import time
from pathlib import Path
from biomercs_ml import pipeline
videos = ['', '2', '3', '4', '5']
t0 = time.monotonic()
for i, s in enumerate(videos, start=1):
    out = Path(f'tmp/biomercs-run{s}')
    print(f'\n=== video {i}/{len(videos)} ===')
    pipeline.run(str(Path(f'tmp/biomercs-footage{s}/source.mp4')), out, out / 'manifest.sqlite')
    print(f'--- video {i} done (total elapsed {time.monotonic() - t0:.0f}s) ---')
"
```
Review: `uv run python scripts/review_sample.py "tmp\biomercs-run2\manifest.sqlite" unreviewed`
(or a number for a random sample, or `wrong`). Always sanity-check the
clip count after a run -- 0 clips means a wrong path, not a clean video.
Ground-truth window clip/frames from this session are in
`tmp\biomercs-verify\` (regenerable with ffmpeg from the source video).

Everything under `/tmp` is gone once a session ends, including all
downloaded source videos and pipeline-run manifests/clips. To pick back up:

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
identical `session_id`/`event_timestamp_s` pairs reappear). **Always
`rm -rf` the output dir first** if it might already exist from an earlier
run this session — `dataset_manifest.create_db` doesn't clear existing
rows, only creates missing directories, so re-running into a stale dir
silently mixes old and new clips (see `stale-output-dir-mixes-review-rows`
in KNOWN_BUGS.md):

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

Each `pipeline.run` takes ~2 minutes on a ~10min video (`sample_video` is
parallelized across CPU cores — see `sample-video-sequential-bottleneck`
in FIXED_BUGS.md). Use `hud_reader._sample_range` directly to pull raw
unfiltered per-tick timer/combo/confidence around a specific timestamp
without re-running the whole pipeline — much faster than digging through
the filtered `HudSample` list.

## Decisions already made — do not re-ask

- **Inline execution** (`superpowers:executing-plans`, not
  subagent-driven), chosen at project start. Still the mode.
- **Never use `Agent` with `subagent_type: "fork"`** — the user has
  reacted with real frustration to this across multiple past sessions.
  Regular (non-fork) subagents are fine if truly needed; fork
  specifically is not.
- **Map-pickup handling: detect nearby popup, discard the group** (not
  subtract the exact amount, not a full holistic-window redesign) — see
  `map-pickup-misattributed-as-bonus-kill` in FIXED_BUGS.md.
- **Digit-margin fix: clamp per-slot, never shrink below nominal box** —
  a stricter global clamp was tried first and broke matching entirely for
  tightly-packed slots; see `combo-label-margin-bleed` in FIXED_BUGS.md.
- **`SAMPLE_VOTE_FRAMES` must stay 11** — settled after real-footage
  evidence (`bug-d-vote-burst-too-narrow` in FIXED_BUGS.md), explicitly
  rejected as a performance lever. Don't re-suggest lowering it.
- **GPU acceleration: don't re-raise** without a batching rewrite already
  in progress — benchmarked ~30x *slower* than CPU for these tiny crops
  on this hardware. See `docs/knowledge_base/project-ideas.md`.

## Important behavioral notes

- **Short in-chat design + explicit approval before implementing** —
  works well every session, including catching wrong hypotheses before
  wasting implementation effort, purely by presenting concrete evidence
  and asking before coding. Keep doing this.
- **The user reviews in fine technical detail and pushes back with real
  data.** Domain-knowledge observations from the user ("this combo value
  is physically impossible", "too many bullet kills for those scores")
  have had a 100% hit rate at surfacing real bugs. Take these seriously
  and investigate concretely.
- **TDD throughout, no exceptions** — every fix has a failing test first,
  reproducing the exact real-footage bug (often a checked-in fixture
  frame), watched fail, then the minimal fix.
- **Real-footage A/B diff (stash/run/restore/run) before accepting any
  `hud_reader`/`event_detector` change** — unit tests alone have shipped
  real bugs before (contamination bugs, regressions) that only showed up
  against real noisy data.
- One commit per fix, with a full "why" in the commit message, plus a
  `DECISIONS.md` entry for anything non-obvious.

## Working style notes

- The user (11 years of software engineering experience, new to ML/CV
  specifically, top-5-world Mercenaries player with 2 standing Chris
  STARS world records) wants to actually learn through this — don't
  over-abstract or skip past the "why" when implementing.
- Portuguese/English mixed conversation is normal; match whichever the
  user uses in a given message.
- Follow `AGENTS.md` (guard clauses, type hints everywhere, dataclasses
  for structured data, no filler comments, centralize constants in
  `config.py`, etc).
