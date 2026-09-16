# Kill-Labeling Data Pipeline — Design

**Date:** 2026-09-16
**Status:** Approved for planning

## Context

biomercs-ml is a personal project to apply ML/computer vision to Resident
Evil 5/6 "The Mercenaries" gameplay footage. The author is an experienced
software engineer (11 years) with no prior ML/CV experience, and one of the
world's top competitive players of this game mode (top 5 world solo score
ranking, two standing world records on Chris STARS). The primary goals are
personal use and learning ML; a public release is explicitly not a goal
right now.

### The domain mechanic this project starts with

In Mercenaries, killing an enemy can grant a time bonus to the run clock.
A kill via a melee/dash finisher grants **+5 seconds** ("bonus kill"); a
kill via gunfire alone grants no time ("bullet kill", the community's own
term). When multiple enemies die in the same instant, the on-screen "+5"
popup text renders only once regardless of how many bonus kills occurred,
but the actual clock increases by 5 seconds per bonus kill in that group
(e.g. 3 simultaneous bonus kills = clock +15s, one popup shown).

This is the first labeling target because the game's own HUD (the run
timer and the kill counter) gives a reliable, nearly-free ground-truth
signal for it — no manual clip-by-clip labeling is required to get started,
unlike most other techniques discussed for this project (movement quality,
positioning, stun-window reads), which are deferred to later phases.

## Goal of this sub-project

Turn raw gameplay video into a dataset of short, labeled video clips
(`bullet_kill` / `bonus_kill` / `mixed`), suitable as training data for a
future classifier. **Model training is explicitly out of scope for this
spec** — it is a separate, later sub-project once this dataset exists.

## Language and environment

- **Python** for the entire pipeline. This is a near-mandatory choice given
  the stated goal of learning ML: the ML/CV ecosystem (OpenCV, PyTorch,
  the ROCm build for the author's AMD GPU, and virtually all learning
  material) is Python-first. Using another language would fight the
  learning goal, not serve it.
- **Development/runtime split across two machines:**
  - **MacBook Pro (Apple M2 Pro, 10 core, 16GB unified memory)** — primary
    day-to-day dev machine and where this pipeline (stages below) runs day
    to day. All stages are CPU-bound image processing; no GPU is required
    for this sub-project.
  - **Desktop (AMD Ryzen 9700X, Radeon RX 9070 XT, 32GB RAM, Windows,
    author open to WSL2 or a Linux dual-boot)** — reserved for the future
    model-training sub-project, since PyTorch's CUDA-first ecosystem means
    the AMD GPU needs ROCm, whose consumer-GPU support is more mature on
    native Linux than on Windows/WSL2. Not used by this sub-project.
- Video source: ~360 of the author's own recorded runs, plus a large,
  legally-accessible community video library, both already organized by
  character/stage (organization will need review/cleanup as part of this
  work, but a cataloging system is assumed to exist, not built from
  scratch here).

## Pipeline architecture

Five independent stages/scripts, not a monolith — each has one clear input
and output and can be run, tested, and understood on its own:

```
raw video (.mp4)
  → [1] hud_reader        → per-sampled-frame (timestamp, timer_value, kill_count, confidence)
  → [2] event_detector    → grouped kill events (timestamp, group_size)
  → [3] auto_labeler      → labeled groups (timestamp, group_size, label)
  → [4] clip_extractor    → short clip file per labeled group
  → [5] dataset_manifest  → SQLite table: one row per labeled clip
```

### 1. `hud_reader`

Reads the run timer and kill counter from the HUD, once per sampled frame,
sampling every 0.2s (5 samples/second) rather than every native frame.
This is a starting parameter: frequent enough that two kill events are
very unlikely to land in the same sampling gap, cheap enough to not be the
pipeline's bottleneck. If validation (see below) turns up missed events,
this is the first knob to tighten.

Uses **per-digit template matching**, not general-purpose OCR (e.g.
Tesseract). The game renders the HUD font identically every time (a
deterministic, closed system), so a small reference template per digit
(0-9, cropped once) matched against each frame's HUD region is expected to
be faster and far more reliable than a general OCR engine, and needs no
external OCR dependency.

Before attempting a digit read, checks that the HUD region actually looks
like a HUD (matches a reference background template above a confidence
threshold) — this guards against non-gameplay frames (menus, pause,
loading, post-death replay) producing garbage reads. Frames that fail this
check, or whose digit-match confidence falls below a threshold, are
dropped from the time series rather than recorded with a guessed value.

**Output:** a time series of `(timestamp, timer_value, kill_count,
confidence)`, with a `session_id` boundary inserted whenever the timer
value drops sharply (indicating a new stage/round/segment started, since
the timer resets between segments within the same recording).

### 2. `event_detector`

Scans the kill_count column of the time series (within a session) for
increases. Consecutive/simultaneous kills that increment the counter at
the same sampled timestamp are treated as one **group** (not N separate
events), since they cannot currently be individually distinguished (see
Label taxonomy below).

**Output:** list of `(session_id, timestamp, group_size)`.

### 3. `auto_labeler`

For each detected group, looks at the timer_value delta shortly after the
event and classifies it:

- `delta == 0` → **all** kills in the group are `bullet_kill`
- `delta == 5 * group_size` → **all** kills in the group are `bonus_kill`
- any other value → **mixed**: exactly `delta / 5` of the group's kills
  were bonus kills, and `group_size - delta/5` were bullet kills — the
  *count* is fully determined by this arithmetic, but *which* specific
  enemy in the group was which type is not recoverable from timer/counter
  data alone, and is explicitly deferred (see Label taxonomy).

**Output:** each group now carries a label: `bullet_kill`, `bonus_kill`,
or `mixed(n_bonus, n_bullet)`.

### 4. `clip_extractor`

For each labeled group, cuts a short clip from the source video using
`ffmpeg` — 2 seconds before the event timestamp to 2 seconds after — and
saves it to a clips directory. This starting window is intentionally
generous (a future classifier only needs to see the finishing
blow/animation, well within this range); it can be narrowed later once
real clips are being reviewed, without needing to change any earlier
stage.

### 5. `dataset_manifest`

A SQLite database with one row per labeled clip: clip file path, label
(including group composition for `mixed`), source video, event timestamp,
session id, and the HUD-read confidence score for that event's window.
This is the pipeline's single source of truth for anything downstream
(a future training script, or manual spot-review).

## Label taxonomy

`bullet_kill`, `bonus_kill`, `mixed(n_bonus, n_bullet)` — a group-level
label, not a per-enemy label. Determining *which* enemy within a mixed
group was which kill type is explicitly **out of scope** for this
sub-project; it would need a visual/spatial signal this pipeline doesn't
attempt to extract yet (e.g. matching each enemy's death-animation start
frame against sub-frame timer increments, if the game processes
simultaneous kills as discrete internal ticks — a possible future
investigation, not planned work).

## Error handling / edge cases

- **Non-gameplay frames** (menus, pause, loading, post-death replay):
  guarded by the HUD-background confidence check in `hud_reader`; such
  frames are excluded from the time series rather than misread.
- **Low-confidence digit reads** (motion blur, HUD partially obscured by a
  visual effect): the confidence score lets `event_detector` /
  `auto_labeler` ignore or flag affected windows instead of propagating a
  wrong reading into a label.
- **Timer resets mid-video** (a single recording spanning multiple
  stages/rounds): detected as a sharp downward jump in timer_value, which
  starts a new `session_id`; deltas are never computed across a session
  boundary.

## Validation approach

There's no external ground truth to check against automatically, so
validation is manual sampling: after a run of the pipeline, pull a random
sample of ~100-200 labeled groups and manually verify each against the
source video. This produces an observed accuracy rate for the pipeline.
The target bar is high (aiming for >98% agreement) since incorrect labels
propagate directly into any future model trained on this data. If the
observed rate falls short, the sample itself is the debugging set — errors
should trace back to one of the edge cases above (confidence thresholds
too loose, a session boundary missed, etc.).

## Out of scope for this spec

- Training any classifier on the resulting dataset (separate future spec).
- Per-enemy attribution within `mixed` groups.
- Any other labeling target (movement quality, stun-window success,
  positioning) — this spec covers only the bullet-kill/bonus-kill target.
- A labeling review UI/tool — deliberately deferred; the plan is to
  validate the labeling approach with the crudest possible tooling first
  (manual spot-checks against raw video) and only build tooling once a
  concrete, felt need for it shows up.
- Public release, packaging, or documentation for other users.
- RAG/knowledge-base or natural-language coaching layers discussed
  earlier in this project's exploration — unrelated to this specific data
  pipeline and not needed for it.
