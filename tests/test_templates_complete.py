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


def test_popup_digit_templates_cover_exactly_the_ones_digit_values_that_can_appear():
    # Deliberately not all 10 digits: the popup's ones digit can only
    # ever be "5" (the kill-bonus popup, always fixed at "+05") or "0"
    # (a map pickup, always +30/+60/+90) -- see config.POPUP_ONES_DIGIT_SLOT.
    present = {p.stem for p in Path(config.POPUP_DIGITS_DIR).glob("*.png")}
    assert present == {"0", "5"}
