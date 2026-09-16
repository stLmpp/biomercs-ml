from biomercs_ml import config
from biomercs_ml.models import KillGroup, KillLabel


def label_kill_group(
    group: KillGroup, tolerance_s: float = config.LABEL_TOLERANCE_S
) -> KillLabel | None:
    raw_delta = group.timer_after_s - group.timer_before_s
    # The timer counts down ~1s per elapsed second even with no kill, so
    # cancel that decay out before checking for clean multiples of 5.
    bonus_seconds = raw_delta + group.elapsed_s

    n_bonus = round(bonus_seconds / 5.0)
    n_bonus = max(0, min(n_bonus, group.group_size))
    residual = abs(bonus_seconds - 5.0 * n_bonus)
    if residual > tolerance_s:
        return None

    n_bullet = group.group_size - n_bonus
    if n_bonus == group.group_size:
        kind = "bonus_kill"
    elif n_bonus == 0:
        kind = "bullet_kill"
    else:
        kind = "mixed"
    return KillLabel(kind=kind, n_bonus=n_bonus, n_bullet=n_bullet)
