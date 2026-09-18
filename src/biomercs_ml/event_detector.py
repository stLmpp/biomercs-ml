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
        group_size = curr.combo_value - prev.combo_value
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
                confidence=min(prev.confidence, curr.confidence)
                * config.GROUP_SIZE_CONFIDENCE_FACTOR[group_size],
            )
        )
    return groups
