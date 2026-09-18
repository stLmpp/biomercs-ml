from biomercs_ml import config
from biomercs_ml.models import HudSample, KillGroup


def _pickup_nearby(session_samples: list[HudSample], timestamp_s: float) -> bool:
    return any(
        sample.pickup_popup
        and abs(sample.timestamp_s - timestamp_s) <= config.PICKUP_EXCLUSION_WINDOW_S
        for sample in session_samples
    )


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
        # sample before `prev` already matched (or exceeded) `curr`,
        # this is just recovery from that dip, not a new kill group.
        if i > 0 and session_samples[i - 1].combo_value >= curr.combo_value:
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
        groups.append(
            KillGroup(
                session_id=session_id,
                timestamp_s=curr.timestamp_s,
                group_size=group_size,
                timer_before_s=prev.timer_value_s,
                timer_after_s=curr.timer_value_s,
                elapsed_s=curr.timestamp_s - prev.timestamp_s,
                confidence=min(prev.confidence, curr.confidence)
                * config.GROUP_SIZE_CONFIDENCE_FACTOR[group_size],
            )
        )
    return groups
