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


def test_detect_kill_groups_drops_implausibly_large_jumps():
    # A single-frame digit misread (e.g. combo momentarily read as 886
    # instead of 26) can look like a 100-kill group between two
    # samples -- physically impossible given the game's fixed enemy
    # pool, so it's a read error, not a real event.
    session = [_sample(0.0, 100.0, 26), _sample(0.2, 99.8, 126)]
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert groups == []


def test_detect_kill_groups_drops_a_rise_that_is_just_recovery_from_a_transient_dip():
    # Real footage: a transient misread dip (e.g. "18" briefly read as
    # "10" for a tick, even after hud_reader's per-tick majority vote --
    # found when the misread streak outlasts the vote burst) is ignored
    # as a drop, but the very next sample recovering to the true,
    # unchanged value looks like a real kill group. It isn't: the
    # sample before the dip already matched the "after" value.
    session = [
        _sample(0.0, 198.0, 18),
        _sample(0.2, 198.0, 10),
        _sample(0.4, 198.0, 18),
    ]
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert groups == []
