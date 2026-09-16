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

Read these before doing anything else, in this order:
1. `docs/knowledge_base/README.md` and both files it points to — domain
   knowledge (game mechanics) and deferred ideas. Treat the mechanics
   file as ground truth; it comes from the author's own top-level
   competitive experience, don't second-guess it.
2. `docs/superpowers/specs/2026-09-16-kill-labeling-pipeline-design.md`
   — the approved design spec.
3. `docs/superpowers/plans/2026-09-16-kill-labeling-pipeline.md` — the
   approved, fully-detailed 11-task TDD implementation plan. This is
   the actual work queue.

## Status as of this handoff

- Spec: approved, committed.
- Plan: approved, committed, self-reviewed (no placeholders, spec
  coverage checked, type-consistency checked).
- **Calibration already done for real** — this isn't placeholder data.
  All HUD ROI/slot pixel coordinates in the plan's `config.py` were
  derived from three real 1280x720 screenshots the author provided,
  using pixel-level color/brightness column analysis (not eyeballed),
  and cross-validated against all three (different characters/scenes,
  same coordinates read correctly in every one). These screenshots and
  partial digit templates are already committed:
  - `tests/fixtures/frames/sample_frame_01.png` (+ `02`, `03`)
  - `tests/fixtures/synthetic_static.mp4` (synthetic 1s video for
    testing `sample_video`'s frame-stepping without needing real
    gameplay footage yet)
  - `templates/digits_timer/{0,1,2,3,5,8}.png`,
    `templates/digits_combo/{0,3,5,7}.png`, `templates/combo_label.png`
- **Not started yet:** no Python code exists — `biomercs_ml/` package,
  `pyproject.toml`, everything in the plan's Task 1 onward is still to
  be written.
- **Open item inside the plan itself:** Task 2 requires the remaining
  digit templates (timer needs `4,6,7,9`; combo needs `1,2,4,6,8,9`),
  sourced from the author's own footage — this can't be done without
  them supplying frames. Don't skip or fake this step.

## Decision pending from the user

Before starting Task 1, ask which execution mode they want:
1. **Subagent-driven** (recommended) — invoke
   `superpowers:subagent-driven-development`, fresh subagent per task,
   two-stage review between tasks.
2. **Inline** — invoke `superpowers:executing-plans`, batch execution
   with checkpoints in this session.

Do not assume — this was asked and not yet answered when this handoff
was written.

## Important behavioral note

The user explicitly reacted with frustration to the `fork` subagent
type being used for exploration/research earlier in this project
("don't use fork, please" → it was used anyway → "again man",
"everytime", "you use forks"). Do not use `Agent` with
`subagent_type: "fork"` for anything in this project. Regular
(non-fork) subagents — like the ones `subagent-driven-development`
dispatches per task — are a different thing and are fine; this is
specifically about `fork`.

## Working style notes

- The user (11 years of software engineering experience, new to ML/CV
  specifically) wants to actually learn ML through this, not just get
  a finished pipeline — don't over-abstract or skip past the
  "why" when implementing.
- Portuguese/English mixed conversation is normal with this user; match
  whichever they use.
