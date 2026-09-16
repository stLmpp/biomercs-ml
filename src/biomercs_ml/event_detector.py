from biomercs_ml.models import HudSample, KillGroup


def detect_kill_groups(session_samples: list[HudSample], session_id: int) -> list[KillGroup]:
    groups = []
    for prev, curr in zip(session_samples, session_samples[1:]):
        group_size = curr.combo_value - prev.combo_value
        if group_size > 0:
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
