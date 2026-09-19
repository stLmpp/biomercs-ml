import pytest

from biomercs_ml import config, event_detector
from biomercs_ml.models import HudSample


def _ticks(
    end_s: float,
    timer_jumps_s: tuple[float, ...] = (),
    popup_ranges: tuple[tuple[float, float], ...] = (),
    combo_at: dict[float, int] | None = None,
    pickup_at: tuple[float, ...] = (),
) -> list[HudSample]:
    combo_at = combo_at or {}
    samples = []
    for i in range(int(round(end_s / 0.2)) + 1):
        t = round(i * 0.2, 1)
        timer = 100.0 - t + 5.0 * sum(1 for jump in timer_jumps_s if t >= jump)
        samples.append(
            HudSample(
                timestamp_s=t,
                session_id=0,
                timer_value_s=timer,
                combo_value=combo_at.get(t),
                confidence=0.9,
                pickup_popup=t in pickup_at,
                bonus_popup=any(start <= t <= end for start, end in popup_ranges),
            )
        )
    return samples


def test_popup_episode_becomes_one_bonus_group_starting_at_the_popup_onset():
    samples = _ticks(6.0, timer_jumps_s=(3.0,), popup_ranges=((3.0, 3.4),))

    groups = event_detector.detect_popup_kill_groups(samples, session_id=0)

    assert len(groups) == 1
    assert groups[0].timestamp_s == 3.0
    assert groups[0].group_size == 1
    assert groups[0].timer_after_s - groups[0].timer_before_s + groups[0].elapsed_s == pytest.approx(5.0)


def test_simultaneous_multi_kill_with_a_single_popup_is_counted_from_the_timer_jump():
    samples = _ticks(6.0, timer_jumps_s=(3.0,), popup_ranges=((3.0, 3.2),))
    for sample in samples:
        if sample.timestamp_s >= 3.0:
            sample.timer_value_s += 10.0  # two more +5s landing with the same popup

    groups = event_detector.detect_popup_kill_groups(samples, session_id=0)

    assert [g.group_size for g in groups] == [3]


def test_popup_ticks_one_missed_tick_apart_stay_one_episode():
    samples = _ticks(6.0, timer_jumps_s=(3.0,), popup_ranges=((3.0, 3.2), (3.6, 3.8)))

    assert len(event_detector.detect_popup_kill_groups(samples, session_id=0)) == 1


def test_popup_ticks_further_apart_than_the_episode_gap_are_separate_episodes():
    far_apart_s = 8.0
    assert far_apart_s - 3.2 > config.POPUP_EPISODE_MAX_GAP_S
    samples = _ticks(12.0, timer_jumps_s=(3.0, far_apart_s), popup_ranges=((3.0, 3.2), (far_apart_s, far_apart_s + 0.2)))

    groups = event_detector.detect_popup_kill_groups(samples, session_id=0)

    assert [g.timestamp_s for g in groups] == [3.0, far_apart_s]


def test_popup_episode_near_a_map_pickup_popup_is_dropped():
    samples = _ticks(6.0, timer_jumps_s=(3.0,), popup_ranges=((3.0, 3.4),), pickup_at=(2.4,))

    assert event_detector.detect_popup_kill_groups(samples, session_id=0) == []


def test_popup_episode_whose_timer_never_jumped_is_dropped():
    samples = _ticks(6.0, popup_ranges=((3.0, 3.4),))

    assert event_detector.detect_popup_kill_groups(samples, session_id=0) == []


def test_combo_rise_beyond_the_popup_bonuses_is_added_as_bullet_kills_on_the_popup_group():
    samples = _ticks(
        6.0, timer_jumps_s=(3.0,), popup_ranges=((3.0, 3.4),), combo_at={0.0: 10, 4.0: 12}
    )

    groups = event_detector.detect_popup_kill_groups(samples, session_id=0)

    assert [(g.timestamp_s, g.group_size) for g in groups] == [(3.0, 2)]


def test_combo_rise_fully_explained_by_the_popup_adds_no_extra_group():
    samples = _ticks(
        6.0, timer_jumps_s=(3.0,), popup_ranges=((3.0, 3.4),), combo_at={0.0: 10, 4.0: 11}
    )

    groups = event_detector.detect_popup_kill_groups(samples, session_id=0)

    assert [(g.timestamp_s, g.group_size) for g in groups] == [(3.0, 1)]


def test_two_popups_inside_one_sparse_combo_pair_stay_two_separate_groups():
    # combo readable only at 0s and 10s (+2): the old adjacent-pair logic
    # merges both kills into one clip; each popup must keep its own.
    samples = _ticks(
        12.0,
        timer_jumps_s=(3.0, 7.0),
        popup_ranges=((3.0, 3.2), (7.0, 7.2)),
        combo_at={0.0: 10, 10.0: 12},
    )

    groups = event_detector.detect_popup_kill_groups(samples, session_id=0)

    assert [(g.timestamp_s, g.group_size) for g in groups] == [(3.0, 1), (7.0, 1)]


def test_combo_rise_without_any_popup_falls_back_to_the_combo_pair_group():
    samples = _ticks(6.0, timer_jumps_s=(3.0,), combo_at={0.0: 10, 4.0: 11})

    groups = event_detector.detect_popup_kill_groups(samples, session_id=0)

    assert [(g.timestamp_s, g.group_size) for g in groups] == [(4.0, 1)]


def test_one_misread_timer_tick_before_the_popup_does_not_inflate_the_bonus_count():
    samples = _ticks(6.0, timer_jumps_s=(3.0,), popup_ranges=((3.0, 3.4),))
    next(s for s in samples if s.timestamp_s == 0.8).timer_value_s -= 20.0

    groups = event_detector.detect_popup_kill_groups(samples, session_id=0)

    assert [g.group_size for g in groups] == [1]


def test_one_misread_timer_tick_after_the_popup_does_not_inflate_the_bonus_count():
    samples = _ticks(6.0, timer_jumps_s=(3.0,), popup_ranges=((3.0, 3.4),))
    next(s for s in samples if s.timestamp_s == 4.0).timer_value_s += 20.0

    groups = event_detector.detect_popup_kill_groups(samples, session_id=0)

    assert [g.group_size for g in groups] == [1]


def test_popup_that_starts_just_after_the_combo_tick_is_attached_to_that_combo_group():
    samples = _ticks(
        6.0, timer_jumps_s=(3.2,), popup_ranges=((3.2, 3.6),), combo_at={0.0: 10, 3.0: 11}
    )

    groups = event_detector.detect_popup_kill_groups(samples, session_id=0)

    assert [(g.timestamp_s, g.group_size) for g in groups] == [(3.2, 1)]


def test_timer_jump_landing_before_the_popup_onset_is_still_counted():
    # Real footage: the +5s can land ~1s before its "+05" popup appears.
    samples = _ticks(6.0, timer_jumps_s=(2.0,), popup_ranges=((3.0, 3.4),))

    groups = event_detector.detect_popup_kill_groups(samples, session_id=0)

    assert [(g.timestamp_s, g.group_size) for g in groups] == [(3.0, 1)]


def test_baseline_timer_is_taken_from_earlier_ticks_when_the_hud_was_hidden_just_before_the_popup():
    samples = _ticks(6.0, timer_jumps_s=(3.0,), popup_ranges=((3.0, 3.4),))
    samples = [s for s in samples if not 0.6 < s.timestamp_s < 3.0]

    groups = event_detector.detect_popup_kill_groups(samples, session_id=0)

    assert [(g.timestamp_s, g.group_size) for g in groups] == [(3.0, 1)]


def test_popups_closer_than_the_timer_lead_merge_into_one_group_counting_both_jumps():
    samples = _ticks(8.0, timer_jumps_s=(3.0, 4.0), popup_ranges=((3.0, 3.2), (4.0, 4.2)))

    groups = event_detector.detect_popup_kill_groups(samples, session_id=0)

    assert [(g.timestamp_s, g.group_size) for g in groups] == [(3.0, 2)]
