from biomercs_ml.review import ReviewTally, normalize_review_answer, parse_review_answer


def test_review_tally_counts_correct_incorrect_and_skipped():
    tally = ReviewTally()
    tally.record("y")
    tally.record("y")
    tally.record("n")
    tally.record("skip")

    assert tally.correct == 2
    assert tally.incorrect == 1
    assert tally.skipped == 1


def test_review_tally_undo_last_removes_and_returns_the_most_recent_outcome():
    tally = ReviewTally()
    tally.record("y")
    tally.record("n")

    undone = tally.undo_last()

    assert undone == "n"
    assert tally.correct == 1
    assert tally.incorrect == 0


def test_review_tally_undo_last_returns_none_when_nothing_recorded_yet():
    tally = ReviewTally()

    assert tally.undo_last() is None


def test_parse_review_answer_y_means_correct():
    answer = parse_review_answer("y")
    assert answer.outcome == "y"
    assert answer.true_n_bonus is None
    assert answer.true_n_bullet is None


def test_parse_review_answer_n_means_incorrect_with_no_correction():
    answer = parse_review_answer("n")
    assert answer.outcome == "n"
    assert answer.true_n_bonus is None
    assert answer.true_n_bullet is None


def test_parse_review_answer_bonus_slash_bullet_means_incorrect_with_a_correction():
    # "1/2" -- the reviewer watched the clip and it was actually 1 bonus
    # kill and 2 bullet kills, not whatever auto_labeler produced.
    answer = parse_review_answer("1/2")
    assert answer.outcome == "n"
    assert answer.true_n_bonus == 1
    assert answer.true_n_bullet == 2


def test_parse_review_answer_zero_slash_zero_is_a_valid_correction():
    answer = parse_review_answer("0/0")
    assert answer.outcome == "n"
    assert answer.true_n_bonus == 0
    assert answer.true_n_bullet == 0


def test_parse_review_answer_falls_back_to_skip_for_unrecognized_input():
    answer = parse_review_answer("")
    assert answer.outcome == "skip"
    assert answer.true_n_bonus is None
    assert answer.true_n_bullet is None

    garbage = parse_review_answer("maybe")
    assert garbage.outcome == "skip"


def test_normalize_review_answer_collapses_a_correction_matching_the_detected_counts_to_y():
    # A reviewer typing "1/0" when the clip already detected (1, 0) meant
    # the same thing as "y" -- label_kind is fully deterministic from
    # (n_bonus, n_bullet) (see auto_labeler.label_kill_group), so a
    # correction that numerically matches the detection is unambiguously
    # a "correct" verdict, not a real correction.
    answer = parse_review_answer("1/0")
    normalized = normalize_review_answer(answer, detected_n_bonus=1, detected_n_bullet=0)
    assert normalized.outcome == "y"
    assert normalized.true_n_bonus is None
    assert normalized.true_n_bullet is None


def test_normalize_review_answer_keeps_a_correction_that_differs_from_the_detected_counts():
    answer = parse_review_answer("1/2")
    normalized = normalize_review_answer(answer, detected_n_bonus=0, detected_n_bullet=2)
    assert normalized.outcome == "n"
    assert normalized.true_n_bonus == 1
    assert normalized.true_n_bullet == 2


def test_normalize_review_answer_leaves_plain_y_and_n_untouched():
    y = normalize_review_answer(parse_review_answer("y"), detected_n_bonus=1, detected_n_bullet=0)
    assert y.outcome == "y"

    n = normalize_review_answer(parse_review_answer("n"), detected_n_bonus=1, detected_n_bullet=0)
    assert n.outcome == "n"
    assert n.true_n_bonus is None
    assert n.true_n_bullet is None
