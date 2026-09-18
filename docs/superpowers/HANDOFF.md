# Handoff: biomercs-ml — kill-labeling data pipeline

Paste this whole file as your first message in a new session to continue.
It's short on purpose — read the other docs only when you need their
detail:
- **`KNOWN_BUGS.md`** — open issues, one slug each (e.g.
  `combo-2-vs-8-misread`). Check here before starting any investigation.
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

## Current status (as of 2026-09-18, a sixth session)

The combo font's `3`-vs-`8`/`9` misread is **fixed** (`combo-3-vs-8-9-misread`
in FIXED_BUGS.md — a geometric "waist notch" tie-breaker, TDD'd, 110
tests, verified via full real-footage A/B diff + user manual review, kept).
The timer font's own version of the same confusion
(`timer-3-vs-8-9-misread`) is **still open** — the same fix doesn't
transfer there (see KNOWN_BUGS.md for why).

**Start here next session** — two candidate leads, no strong opinion
recorded yet, worth a short discussion before picking:
1. **`combo-2-vs-8-misread`** (KNOWN_BUGS.md) — the project's single
   biggest confirmed accuracy driver, still open, 4 failed fix attempts.
   Fresh data point: video 1, t=520.2, `mixed(1,6)` vs true `(1,0)`. A
   promising untested lead: extend the already-built
   `apply_waist_notch_tiebreak` to also redirect toward "2" (not just
   "3") when the winner is "8"/"9" — the feature's own data shows real
   "2" clears the same separating margin, just not yet wired in.
2. **`timer-3-vs-8-9-misread`** (KNOWN_BUGS.md) — needs a genuinely
   different approach (stroke-width profiling, Hu-moment contours, a
   small trained classifier), since the waist-notch geometry doesn't
   generalize to this font.

Full test suite: `uv run pytest -v` — should be 110 passing. Run it first
thing to confirm nothing's broken.

## Ephemeral files — will NOT exist in a new session

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
