"""Pull clips for manual review.

Usage: uv run python scripts/review_sample.py <db_path> [n|wrong]

A number pulls a random sample of that size. "wrong" instead re-reviews
every clip already marked incorrect in a prior pass -- useful for going
back with a correction (see parse_review_answer) once a first pass has
already flagged which ones are wrong.
"""
import subprocess
import sys
from pathlib import Path

from biomercs_ml import dataset_manifest
from biomercs_ml.review import ReviewTally, normalize_review_answer, parse_review_answer

COLUMNS = [
    "id", "clip_path", "label_kind", "n_bonus", "n_bullet",
    "source_video", "session_id", "event_timestamp_s", "confidence", "created_at",
    "review_correct", "review_true_n_bonus", "review_true_n_bullet",
]


def _close_player() -> None:
    subprocess.run(
        ["osascript", "-e", 'tell application "QuickTime Player" to close every document'],
        capture_output=True,
    )


def main() -> None:
    db_path = Path(sys.argv[1])
    mode = sys.argv[2] if len(sys.argv) > 2 else "100"

    dataset_manifest.create_db(db_path)  # no-op on an existing, up-to-date db
    if mode == "wrong":
        rows = dataset_manifest.fetch_reviewed_incorrect(db_path)
    else:
        rows = dataset_manifest.fetch_random_sample(db_path, int(mode))
    print(f"Reviewing {len(rows)} clips. Each will open in your default player;")
    print("watch it, then answer whether the label matches what you saw.\n")

    tally = ReviewTally()
    index = 0
    while index < len(rows):
        record = dict(zip(COLUMNS, rows[index]))
        print(f"id={record['id']} label={record['label_kind']} "
              f"(bonus={record['n_bonus']}, bullet={record['n_bullet']}) "
              f"confidence={record['confidence']:.2f} clip={record['clip_path']}")
        subprocess.run(["open", record["clip_path"]])
        answer = input(
            "Correct? (y/n, or <bonus>/<bullet> e.g. 1/2 for the true counts, "
            "r to redo previous, Enter to skip): "
        )
        _close_player()

        if answer.strip().lower() == "r":
            if tally.undo_last() is None:
                print("Nothing to redo yet.\n")
                continue
            index -= 1
            continue

        parsed = normalize_review_answer(
            parse_review_answer(answer), record["n_bonus"], record["n_bullet"]
        )
        tally.record(parsed.outcome)
        if parsed.outcome != "skip":
            dataset_manifest.record_review(
                db_path,
                record["id"],
                correct=(parsed.outcome == "y"),
                true_n_bonus=parsed.true_n_bonus,
                true_n_bullet=parsed.true_n_bullet,
            )
        index += 1

    reviewed = tally.correct + tally.incorrect
    print(f"\nReviewed {reviewed} clips ({tally.skipped} skipped): {tally.correct} correct, {tally.incorrect} incorrect.")
    if reviewed:
        print(f"Agreement: {tally.correct / reviewed:.1%}")


if __name__ == "__main__":
    main()
