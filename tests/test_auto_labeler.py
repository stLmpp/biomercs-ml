from biomercs_ml import auto_labeler
from biomercs_ml.models import KillGroup


def _group(group_size, timer_before, timer_after, elapsed_s=0.2):
    return KillGroup(
        session_id=0,
        timestamp_s=elapsed_s,
        group_size=group_size,
        timer_before_s=timer_before,
        timer_after_s=timer_after,
        elapsed_s=elapsed_s,
        confidence=0.9,
    )


def test_labels_single_bullet_kill():
    # delta = -0.2 (just normal decay, no bonus) -> bonus_seconds = 0
    group = _group(group_size=1, timer_before=100.0, timer_after=99.8)
    label = auto_labeler.label_kill_group(group)
    assert label.kind == "bullet_kill"
    assert label.n_bonus == 0
    assert label.n_bullet == 1


def test_labels_single_bonus_kill():
    # delta = +4.8 (=5 - 0.2 decay) -> bonus_seconds = 5.0
    group = _group(group_size=1, timer_before=100.0, timer_after=104.8)
    label = auto_labeler.label_kill_group(group)
    assert label.kind == "bonus_kill"
    assert label.n_bonus == 1
    assert label.n_bullet == 0


def test_labels_simultaneous_triple_bonus_kill():
    # delta = +14.8 (=15 - 0.2 decay) -> bonus_seconds = 15.0 -> 3 bonus
    group = _group(group_size=3, timer_before=100.0, timer_after=114.8)
    label = auto_labeler.label_kill_group(group)
    assert label.kind == "bonus_kill"
    assert label.n_bonus == 3
    assert label.n_bullet == 0


def test_labels_mixed_group():
    # delta = +9.8 (=10 - 0.2 decay) -> bonus_seconds = 10.0 -> 2 bonus, 1 bullet, of 3
    group = _group(group_size=3, timer_before=100.0, timer_after=109.8)
    label = auto_labeler.label_kill_group(group)
    assert label.kind == "mixed"
    assert label.n_bonus == 2
    assert label.n_bullet == 1


def test_returns_none_when_delta_does_not_fit_any_composition():
    # delta doesn't land near any multiple of 5 within tolerance
    group = _group(group_size=1, timer_before=100.0, timer_after=102.5)
    label = auto_labeler.label_kill_group(group)
    assert label is None
