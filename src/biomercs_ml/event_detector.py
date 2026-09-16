from biomercs_ml import config
from biomercs_ml.models import HudSample, KillGroup


def detect_kill_groups(session_samples: list[HudSample], session_id: int) -> list[KillGroup]:
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
        groups.append(
            KillGroup(
                session_id=session_id,
                timestamp_s=curr.timestamp_s,
                group_size=group_size,
                timer_before_s=prev.timer_value_s,
                timer_after_s=curr.timer_value_s,
                elapsed_s=curr.timestamp_s - prev.timestamp_s,
                confidence=min(prev.confidence, curr.confidence),
            )
        )
    return groups
