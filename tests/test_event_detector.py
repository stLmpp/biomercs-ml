from biomercs_ml import event_detector
from biomercs_ml.models import HudSample


def _sample(t, timer, combo, session_id=0, conf=0.9):
    return HudSample(
        timestamp_s=t, session_id=session_id, timer_value_s=timer, combo_value=combo, confidence=conf
    )


def test_detect_kill_groups_finds_single_kill():
    session = [_sample(0.0, 100.0, 5), _sample(0.2, 99.8, 5), _sample(0.4, 104.6, 6)]
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert len(groups) == 1
    group = groups[0]
    assert group.session_id == 0
    assert group.group_size == 1
    assert group.timer_before_s == 99.8
    assert group.timer_after_s == 104.6
    assert group.elapsed_s == 0.2


def test_detect_kill_groups_ignores_combo_reset():
    session = [_sample(0.0, 100.0, 12), _sample(0.2, 99.8, 0)]  # combo dropped, not a kill
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert groups == []


def test_detect_kill_groups_finds_simultaneous_triple_kill():
    session = [_sample(0.0, 100.0, 5), _sample(0.2, 114.8, 8)]  # +3 combo, +15s bonus
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert len(groups) == 1
    assert groups[0].group_size == 3
