import math
from dataclasses import replace
from statistics import median

from biomercs_ml import config
from biomercs_ml.models import HudSample, KillGroup


def _pickup_nearby(session_samples: list[HudSample], timestamp_s: float) -> bool:
    return any(
        sample.pickup_popup
        and abs(sample.timestamp_s - timestamp_s) <= config.PICKUP_EXCLUSION_WINDOW_S
        for sample in session_samples
    )


def _preceding_combo_value(all_samples: list[HudSample], timestamp_s: float) -> int | None:
    preceding = [sample for sample in all_samples if sample.timestamp_s < timestamp_s]
    if not preceding:
        return None
    return max(preceding, key=lambda sample: sample.timestamp_s).combo_value


def _effective_prev_combo_value(all_samples: list[HudSample], prev: HudSample, window_s: float) -> int:
    # The combo's roll/pop animation (see "Bug A") can transiently render
    # an intermediate value low enough to win a tick's own majority vote,
    # landing directly on `prev`. Since the combo counter never decreases
    # during a session, a nearby (within `window_s`) earlier sample
    # reading higher than `prev` proves `prev` undershot -- clamp up to
    # that established value instead of trusting `prev` outright.
    candidates = [
        sample
        for sample in all_samples
        if prev.timestamp_s - window_s <= sample.timestamp_s < prev.timestamp_s
    ]
    if not candidates:
        return prev.combo_value
    nearest = max(candidates, key=lambda sample: sample.timestamp_s)
    return max(prev.combo_value, nearest.combo_value)


def _effective_curr_combo_value(all_samples: list[HudSample], curr: HudSample, window_s: float) -> int:
    # Symmetric to _effective_prev_combo_value: a tick's own vote can be
    # won by a single lone-frame fluke with zero corroboration when the
    # rest of its burst is unreadable, landing directly on `curr`. A
    # nearby (within `window_s`) later sample reading lower than `curr`
    # proves `curr` overshot -- clamp down to that value instead.
    candidates = [
        sample
        for sample in all_samples
        if curr.timestamp_s < sample.timestamp_s <= curr.timestamp_s + window_s
    ]
    if not candidates:
        return curr.combo_value
    nearest = min(candidates, key=lambda sample: sample.timestamp_s)
    return min(curr.combo_value, nearest.combo_value)


def _decay_adjusted_timer(sample: HudSample, reference_ts: float) -> float:
    # The timer decays 1s per elapsed real second when no bonus lands --
    # project a sample's reading to what it would read at `reference_ts`
    # under that same decay, so readings from different ticks become
    # directly comparable.
    return sample.timer_value_s + (sample.timestamp_s - reference_ts)


# Unlike combo, a raw timer reading has no plausibility cap of its own,
# so the window search below needs one: a candidate whose raw value is
# further from the anchor (prev/curr) than any real kill group could
# plausibly account for is a misread unrelated to this group, not
# evidence of one -- exclude it rather than let it win the min/max.
# Bounded by the already-trusted group-size cap (the largest bonus any
# real group can contribute) plus the window's own normal decay.
_MAX_PLAUSIBLE_TIMER_SWING_S = config.MAX_PLAUSIBLE_GROUP_SIZE * 5 + config.TIMER_DELTA_SEARCH_WINDOW_S


def _timer_before(all_samples: list[HudSample], prev: HudSample, window_s: float) -> float:
    candidates = [
        sample
        for sample in all_samples
        if prev.timestamp_s - window_s <= sample.timestamp_s <= prev.timestamp_s
        and sample.timer_value_s is not None
        and abs(sample.timer_value_s - prev.timer_value_s) <= _MAX_PLAUSIBLE_TIMER_SWING_S
    ]
    # A candidate whose own jump already landed within the window reads
    # *higher* once decay-adjusted than one still from before the jump
    # -- the minimum is the one the jump hasn't reached yet.
    return min(_decay_adjusted_timer(sample, prev.timestamp_s) for sample in candidates)


def _timer_after(all_samples: list[HudSample], curr: HudSample, window_s: float) -> float:
    candidates = [
        sample
        for sample in all_samples
        if curr.timestamp_s <= sample.timestamp_s <= curr.timestamp_s + window_s
        and sample.timer_value_s is not None
        and abs(sample.timer_value_s - curr.timer_value_s) <= _MAX_PLAUSIBLE_TIMER_SWING_S
    ]
    # Symmetric to _timer_before: the maximum is the reading that has
    # already caught up to the jump, not one still mid-animation.
    return max(_decay_adjusted_timer(sample, curr.timestamp_s) for sample in candidates)


def _reverts_to_pre_rise_value(
    all_samples: list[HudSample], after_timestamp_s: float, pre_rise_value: int
) -> bool:
    return any(
        after_timestamp_s < sample.timestamp_s
        <= after_timestamp_s + config.COMBO_REVERSION_CHECK_WINDOW_S
        and sample.combo_value <= pre_rise_value
        for sample in all_samples
    )


def detect_kill_groups(
    session_samples: list[HudSample],
    session_id: int,
    all_samples: list[HudSample] | None = None,
) -> list[KillGroup]:
    # A pickup and the kill-group it affects can land in different
    # (possibly spurious) sessions when severe misreads split a session
    # that should have been one -- search the whole video's samples for
    # nearby pickups, not just this session's, unless the caller has
    # nothing broader to offer.
    pickup_search_samples = all_samples if all_samples is not None else session_samples
    groups = []
    for i in range(len(session_samples) - 1):
        prev = session_samples[i]
        curr = session_samples[i + 1]
        # Compute group_size from each anchor's *effective* combo value,
        # not its raw per-tick vote -- see _effective_prev_combo_value /
        # _effective_curr_combo_value for why a raw vote can under- or
        # overshoot the truth even after per-tick majority voting.
        effective_prev_combo = _effective_prev_combo_value(
            pickup_search_samples, prev, config.COMBO_REVERSION_CHECK_WINDOW_S
        )
        effective_curr_combo = _effective_curr_combo_value(
            pickup_search_samples, curr, config.COMBO_REVERSION_CHECK_WINDOW_S
        )
        group_size = effective_curr_combo - effective_prev_combo
        if not (0 < group_size <= config.MAX_PLAUSIBLE_GROUP_SIZE):
            continue
        # A transient misread dip in `prev` (hud_reader's per-tick vote
        # doesn't always catch a misread streak longer than its burst)
        # is ignored as a drop, but the next sample recovering to the
        # true, unchanged value then looks like a real rise. If the
        # sample immediately before `prev` already matched (or
        # exceeded) `curr`, this is just recovery from that dip, not a
        # new kill group. Looked up via `pickup_search_samples` (the
        # full, session-agnostic timeline), not `session_samples[i-1]`
        # -- a misread severe enough to also trigger a spurious session
        # split lands at `i=0` of the new session, where there is no
        # in-session predecessor to check, even though the same dip
        # pattern is present one step further back across the session
        # boundary. See DECISIONS.md, "bug C".
        preceding_combo_value = _preceding_combo_value(pickup_search_samples, prev.timestamp_s)
        if preceding_combo_value is not None and preceding_combo_value >= curr.combo_value:
            continue
        # The combo counter only ever increases during a session (a
        # rare genuine reset drops toward zero, it doesn't dip and
        # climb back to exactly its pre-rise value) -- a rise that
        # reverts shortly after is a digit misread that survived both
        # the per-tick vote and the transient-dip check above (real
        # footage: an entire multi-second overexposed stretch misread
        # one digit), not a real kill. See DECISIONS.md, "sixth root
        # cause".
        if _reverts_to_pre_rise_value(pickup_search_samples, curr.timestamp_s, prev.combo_value):
            continue
        # A map pickup's timer contribution animates in gradually over
        # several seconds rather than landing on this group's own tick
        # pair (confirmed on real footage), so there's no reliable way
        # to split real kill-bonus time from pickup time here.
        if _pickup_nearby(pickup_search_samples, curr.timestamp_s):
            continue
        # The combo-based pair above isn't necessarily where the
        # timer's own jump landed -- its roll/pop animation can lag the
        # timer's single-frame jump by up to ~2s for a fast multi-kill
        # chain. Search a window around the pair for the timer's real
        # pre-/post-kill value instead of trusting prev/curr directly.
        # See DECISIONS.md, "Bug A".
        timer_before_s = _timer_before(pickup_search_samples, prev, config.TIMER_DELTA_SEARCH_WINDOW_S)
        timer_after_s = _timer_after(pickup_search_samples, curr, config.TIMER_DELTA_SEARCH_WINDOW_S)
        groups.append(
            KillGroup(
                session_id=session_id,
                timestamp_s=curr.timestamp_s,
                group_size=group_size,
                timer_before_s=timer_before_s,
                timer_after_s=timer_after_s,
                elapsed_s=curr.timestamp_s - prev.timestamp_s,
                # Undiscounted raw digit-read confidence -- a same-kind-count
                # rarity discount belongs to auto_labeler, the only place
                # that knows the bonus/bullet split.
                confidence=min(prev.confidence, curr.confidence),
            )
        )
    return groups


def _combo_readable(samples: list[HudSample]) -> list[HudSample]:
    return [s for s in samples if s.timer_value_s is not None and s.combo_value is not None]


def _timer_shows_no_bonus(group: KillGroup) -> bool:
    return group.timer_after_s - group.timer_before_s + group.elapsed_s < 5.0 / 2


def _bonus_popup_episodes(samples: list[HudSample]) -> list[list[HudSample]]:
    episodes: list[list[HudSample]] = []
    for sample in samples:
        if not sample.bonus_popup:
            continue
        if episodes and sample.timestamp_s - episodes[-1][-1].timestamp_s <= config.POPUP_EPISODE_MAX_GAP_S:
            episodes[-1].append(sample)
            continue
        episodes.append([sample])
    return episodes


def _bonus_episode_group(
    episode: list[HudSample],
    all_samples: list[HudSample],
    session_id: int,
    previous_end_s: float,
    next_start_s: float,
) -> KillGroup | None:
    start_s = episode[0].timestamp_s
    end_s = episode[-1].timestamp_s
    if _pickup_nearby(all_samples, start_s) or _pickup_nearby(all_samples, end_s):
        return None
    # The timer windows must not reach into a neighboring episode (or its
    # lead), or its own +5s jump would be counted as this episode's.
    before = [
        s for s in all_samples
        if max(previous_end_s, start_s - config.POPUP_TIMER_WINDOW_S) <= s.timestamp_s <= start_s - config.POPUP_TIMER_LEAD_S
        and s.timer_value_s is not None
    ]
    after = [
        s for s in all_samples
        if end_s <= s.timestamp_s <= min(end_s + config.POPUP_TIMER_WINDOW_S, next_start_s - config.POPUP_TIMER_LEAD_S)
        and s.timer_value_s is not None
    ]
    if not before or not after:
        return None

    timer_before_s = median(_decay_adjusted_timer(s, start_s) for s in before)
    timer_after_s = median(_decay_adjusted_timer(s, end_s) for s in after)
    elapsed_s = end_s - start_s
    # A simultaneous multi-kill shows a single popup, so the kill count
    # can only come from the timer jump (+5s each).
    n_bonus = round((timer_after_s - timer_before_s + elapsed_s) / 5.0)
    if n_bonus < 1:
        return None
    return KillGroup(
        session_id=session_id,
        timestamp_s=start_s,
        group_size=n_bonus,
        timer_before_s=timer_before_s,
        timer_after_s=timer_after_s,
        elapsed_s=elapsed_s,
        confidence=min(before[-1].confidence, after[-1].confidence),
    )


def detect_popup_kill_groups(
    session_samples: list[HudSample],
    session_id: int,
    all_samples: list[HudSample] | None = None,
) -> list[KillGroup]:
    search_samples = all_samples if all_samples is not None else session_samples
    episodes = _bonus_popup_episodes(session_samples)
    previous_ends_s = [-math.inf] + [e[-1].timestamp_s for e in episodes[:-1]]
    next_starts_s = [e[0].timestamp_s for e in episodes[1:]] + [math.inf]
    bonus_groups = [
        bonus
        for episode, previous_end_s, next_start_s in zip(episodes, previous_ends_s, next_starts_s)
        if (bonus := _bonus_episode_group(episode, search_samples, session_id, previous_end_s, next_start_s))
        is not None
    ]
    # A combo-rise pair with no popup near it and no timer jump is kept as
    # its own group (bullet kills). One that has popups near it is fully
    # explained by them: the combo is too sparse to also say how many
    # extra bullet kills hide in the pair.
    combo_groups = detect_kill_groups(
        _combo_readable(session_samples), session_id, all_samples=_combo_readable(search_samples)
    )

    groups: list[KillGroup] = []
    unattached = bonus_groups
    for combo_group in combo_groups:
        window_start_s = combo_group.timestamp_s - combo_group.elapsed_s - config.TIMER_DELTA_SEARCH_WINDOW_S
        window_end_s = combo_group.timestamp_s + config.POPUP_COMBO_ATTACH_LAG_S
        attached = [b for b in unattached if window_start_s <= b.timestamp_s <= window_end_s]
        if not attached:
            # Every bonus kill shows a popup, so a timer jump with none
            # near this pair is unreliable evidence (see config).
            if not _timer_shows_no_bonus(combo_group):
                combo_group = replace(
                    combo_group,
                    confidence=combo_group.confidence * config.UNCORROBORATED_BONUS_CONFIDENCE_FACTOR,
                )
            groups.append(combo_group)
            continue
        unattached = [b for b in unattached if b not in attached]
        groups.extend(attached)
    groups.extend(unattached)
    return sorted(groups, key=lambda g: g.timestamp_s)
