from biomercs_ml import event_detector
from biomercs_ml.models import HudSample


def _sample(t, timer, combo, session_id=0, conf=0.9, pickup_popup=False):
    return HudSample(
        timestamp_s=t,
        session_id=session_id,
        timer_value_s=timer,
        combo_value=combo,
        confidence=conf,
        pickup_popup=pickup_popup,
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


def test_detect_kill_groups_drops_a_group_larger_than_the_one_in_a_million_ceiling():
    # Per the author's own top-level competitive experience: 8
    # simultaneous kills is roughly a one-in-a-million event (rare, but
    # real); anything above that is not plausible and is a read error.
    session = [_sample(0.0, 100.0, 26), _sample(0.2, 95.0, 35)]  # +9
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert groups == []


def test_detect_kill_groups_keeps_a_group_at_the_one_in_a_million_ceiling():
    session = [_sample(0.0, 100.0, 26), _sample(0.2, 95.0, 34)]  # +8
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert len(groups) == 1


def test_detect_kill_groups_does_not_discount_confidence_for_a_plausible_group_size():
    session = [_sample(0.0, 100.0, 5, conf=0.8), _sample(0.2, 99.8, 8, conf=0.7)]  # +3
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert groups[0].confidence == 0.7


def test_detect_kill_groups_discounts_confidence_for_a_rare_group_size():
    # 6 simultaneous kills is rare -- the reported confidence should
    # reflect that prior, not just the raw digit-read confidence.
    session = [_sample(0.0, 100.0, 5, conf=0.8), _sample(0.2, 95.0, 11, conf=0.8)]  # +6
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert groups[0].confidence == 0.8 * 0.55


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


def test_detect_kill_groups_drops_a_group_near_a_map_pickup_popup():
    # A map pickup's timer contribution animates in over several
    # seconds rather than landing on this group's own tick pair, so
    # there's no reliable way to split real kill-bonus time from
    # pickup time -- discard the group instead of mislabeling it.
    session = [
        _sample(0.0, 200.0, 5, pickup_popup=True),
        _sample(0.2, 200.0, 6),
        _sample(0.4, 210.0, 14),
    ]
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert groups == []


def test_detect_kill_groups_keeps_a_group_far_from_any_pickup_popup():
    session = [
        _sample(0.0, 200.0, 5, pickup_popup=True),
        _sample(20.0, 205.0, 6),
    ]
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert len(groups) == 1


def test_detect_kill_groups_drops_a_rise_that_reverts_back_to_its_pre_rise_value():
    # Real footage (video 2, ~t=408.8s): the combo tens-digit "0" was
    # misread as "9" for an entire multi-second overexposed stretch --
    # long enough to survive both per-tick majority voting and the
    # transient-dip check above. The observed real sequence read
    # 184,184,184,194,184,184 with the timer never changing. The combo
    # counter only ever increases during a session (barring a rare
    # genuine reset toward zero, not a dip-and-return to the exact same
    # value) -- a rise that reverts to at or below its pre-rise value
    # shortly after is a misread, not a real kill. See DECISIONS.md,
    # "sixth root cause".
    session = [
        _sample(0.0, 300.0, 184),
        _sample(0.2, 300.0, 184),
        _sample(0.4, 300.0, 190),
        _sample(4.4, 300.0, 184),
        _sample(4.6, 300.0, 184),
    ]
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert groups == []


def test_detect_kill_groups_keeps_a_rise_that_is_never_reverted():
    session = [
        _sample(0.0, 300.0, 184),
        _sample(0.2, 295.0, 190),
        _sample(4.6, 295.0, 190),
    ]
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert len(groups) == 1
    assert groups[0].group_size == 6


def test_detect_kill_groups_keeps_a_rise_reverted_only_after_the_check_window():
    session = [
        _sample(0.0, 300.0, 184),
        _sample(0.2, 295.0, 190),
        _sample(20.0, 290.0, 184),  # a real, later, unrelated combo break
    ]
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert len(groups) == 1


def test_detect_kill_groups_drops_a_group_when_pickup_landed_in_a_different_session():
    # Real footage: severe digit misreads in a chaotic stretch (fast
    # kill chain + screen-flash) split what should be one session into
    # several spurious ones, landing a real pickup popup in a different
    # session bucket than the kill-group it affects. The pickup search
    # must not be scoped to just this session's samples.
    pickup_session = [_sample(0.0, 276.0, 39, session_id=88, pickup_popup=True)]
    affected_session = [
        _sample(0.6, 274.0, 30, session_id=89),
        _sample(1.6, 283.0, 39, session_id=89),
    ]
    all_samples = pickup_session + affected_session

    groups = event_detector.detect_kill_groups(
        affected_session, session_id=89, all_samples=all_samples
    )

    assert groups == []


def test_detect_kill_groups_drops_a_real_overexposed_frames_misread():
    # Real footage (video 2, ~t=408.8s): this exact frame is genuinely
    # overexposed -- the combo tens-digit "0"'s defining feature (a dark
    # hollow center) is blown out by lighting, not just compressed, so
    # no template or preprocessing can reliably read it correctly (see
    # DECISIONS.md, "fifth root cause"). This frame's actual misread
    # (105 -> 195) is now itself caught by
    # config.MAX_PLAUSIBLE_COMBO_VALUE (195 exceeds the real game's
    # fixed-enemy-pool maximum of 150), so `hud_reader.sample_video`
    # would drop this tick's sample entirely before it ever reaches
    # event_detector -- but keep this as a defense-in-depth test too:
    # even a misread this large that *did* land under the cap (a
    # tens-digit "0" reading closer to home, hard-coded here rather
    # than re-derived from the fixture frame) still gets caught by
    # event_detector's own group-size cap and reversion check.
    session = [
        _sample(0.0, 300.0, 105),
        _sample(0.2, 300.0, 105),
        _sample(0.4, 300.0, 145),
        _sample(4.4, 300.0, 105),
        _sample(4.6, 300.0, 105),
    ]
    groups = event_detector.detect_kill_groups(session, session_id=0)

    assert groups == []


def test_detect_kill_groups_drops_a_rise_that_is_just_recovery_from_a_dip_at_a_session_boundary():
    # Real footage (video 2, ~t=492.2s): a timer misread triggered a
    # spurious new session right where a transient combo misread also
    # landed. The existing transient-dip guard only ever looks at
    # `session_samples[i-1]` -- the previous sample *within this
    # session* -- so it can never fire for `i=0`, the first sample of a
    # newly-split session, even though the misread pattern (a dip that
    # immediately recovers to the true, unchanged value) is identical
    # to the case the guard already handles at `i>0`. See
    # DECISIONS.md, "bug C".
    prior_session = [_sample(0.0, 488.0, 187, session_id=238)]
    new_session = [
        _sample(0.4, 482.0, 181, session_id=239),  # transient misread
        _sample(0.6, 482.0, 187, session_id=239),  # recovers to the true, unchanged value
    ]
    all_samples = prior_session + new_session

    groups = event_detector.detect_kill_groups(new_session, session_id=239, all_samples=all_samples)

    assert groups == []


def test_detect_kill_groups_keeps_a_genuine_rise_at_the_start_of_a_new_session():
    prior_session = [_sample(0.0, 488.0, 175, session_id=238)]
    new_session = [
        _sample(0.4, 482.0, 181, session_id=239),
        _sample(0.6, 482.0, 187, session_id=239),  # a real +6 kill group
    ]
    all_samples = prior_session + new_session

    groups = event_detector.detect_kill_groups(new_session, session_id=239, all_samples=all_samples)

    assert len(groups) == 1
    assert groups[0].group_size == 6
