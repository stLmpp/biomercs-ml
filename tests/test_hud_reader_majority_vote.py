from biomercs_ml import hud_reader


def test_majority_value_picks_the_value_seen_most_often():
    readings = [(3, 0.9), (3, 0.9), (10, 0.85)]

    value, confidence = hud_reader._majority_value(readings)

    assert value == 3
    assert confidence == 0.9


def test_majority_value_ignores_none_readings():
    readings = [(None, 0.4), (5, 0.8), (5, 0.7)]

    value, confidence = hud_reader._majority_value(readings)

    assert value == 5
    assert confidence == 0.8


def test_majority_value_returns_none_when_all_readings_are_none():
    readings = [(None, 0.4), (None, 0.3)]

    value, confidence = hud_reader._majority_value(readings)

    assert value is None
