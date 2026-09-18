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
    # 2 bonus and 1 bullet are both plausible counts (factor 1.0 each in
    # config.BONUS_COUNT_CONFIDENCE_FACTOR/BULLET_COUNT_CONFIDENCE_FACTOR)
    # -- confidence passes through the group's raw confidence undiscounted.
    assert label.confidence == 0.9


def test_returns_none_when_delta_does_not_fit_any_composition():
    # delta doesn't land near any multiple of 5 within tolerance
    group = _group(group_size=1, timer_before=100.0, timer_after=102.5)
    label = auto_labeler.label_kill_group(group)
    assert label is None


def test_discounts_confidence_for_a_rare_bonus_count():
    # 6 simultaneous bonus kills is rare -- per the author's own domain
    # knowledge, bullet kills are rarer still at the same count in a good
    # run (Wesker's dash-finisher meta), so bonus and bullet counts are
    # discounted by separate tables, not one shared by raw group_size.
    # delta = +29.8 (=30 - 0.2 decay) -> bonus_seconds = 30.0 -> 6 bonus, 0 bullet
    group = _group(group_size=6, timer_before=100.0, timer_after=129.8)
    label = auto_labeler.label_kill_group(group)
    assert label.n_bonus == 6
    assert label.n_bullet == 0
    assert label.confidence == 0.9 * 0.15


def test_discounts_confidence_more_steeply_for_a_rare_bullet_count():
    # Same count (6) as the bonus case above, but pure bullet -- bullet
    # kills are rarer at this count than bonus kills, so the discount is
    # steeper (0.20 vs bonus's 0.15 would be backwards; bullet's table
    # drops faster at the low end -- see config.py for the exact values).
    # delta = -0.2 (just normal decay, no bonus at all) -> 0 bonus, 6 bullet
    group = _group(group_size=6, timer_before=100.0, timer_after=99.8)
    label = auto_labeler.label_kill_group(group)
    assert label.n_bonus == 0
    assert label.n_bullet == 6
    assert label.confidence == 0.9 * 0.20


def test_combines_both_discounts_for_a_mixed_group_at_the_group_size_ceiling():
    # delta = +19.8 (=20 - 0.2 decay) -> bonus_seconds = 20.0 -> 4 bonus, 4 bullet, of 8
    group = _group(group_size=8, timer_before=100.0, timer_after=119.8)
    label = auto_labeler.label_kill_group(group)
    assert label.n_bonus == 4
    assert label.n_bullet == 4
    assert label.confidence == 0.9 * 0.90 * 0.60
