from biomercs_ml import config


def test_slot_counts_match_expected_digit_counts():
    assert len(config.TIMER_MINUTES_SLOTS) == 2
    assert len(config.TIMER_SECONDS_SLOTS) == 2
    assert len(config.COMBO_DIGIT_SLOTS) == 3


def test_all_slots_are_same_size_within_their_field():
    timer_slots = config.TIMER_MINUTES_SLOTS + config.TIMER_SECONDS_SLOTS
    timer_sizes = {(w, h) for _, _, w, h in timer_slots}
    assert timer_sizes == {(40, 76)}

    combo_sizes = {(w, h) for _, _, w, h in config.COMBO_DIGIT_SLOTS}
    assert combo_sizes == {(34, 46)}
