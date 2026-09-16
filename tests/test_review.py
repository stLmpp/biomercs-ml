from biomercs_ml.review import ReviewTally


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
