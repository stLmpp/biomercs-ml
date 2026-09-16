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
