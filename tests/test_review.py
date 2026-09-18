from biomercs_ml.review import ReviewTally, parse_review_answer


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
