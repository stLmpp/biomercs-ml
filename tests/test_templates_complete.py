from pathlib import Path

from biomercs_ml import config

ALL_DIGITS = {str(d) for d in range(10)}


def test_timer_digit_templates_complete():
    present = {p.stem for p in Path(config.TIMER_DIGITS_DIR).glob("*.png")}
    missing = ALL_DIGITS - present
    assert not missing, f"missing timer digit templates: {sorted(missing)}"


def test_combo_digit_templates_complete():
    present = {p.stem for p in Path(config.COMBO_DIGITS_DIR).glob("*.png")}
    missing = ALL_DIGITS - present
    assert not missing, f"missing combo digit templates: {sorted(missing)}"
