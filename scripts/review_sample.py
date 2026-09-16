"""Pull a random sample of labeled clips for manual review.

Usage: uv run python scripts/review_sample.py <db_path> [n]
"""
import subprocess
import sys
from pathlib import Path

from biomercs_ml import dataset_manifest
from biomercs_ml.review import ReviewTally

COLUMNS = [
    "id", "clip_path", "label_kind", "n_bonus", "n_bullet",
    "source_video", "session_id", "event_timestamp_s", "confidence", "created_at",
    "review_correct",
]


def _close_player() -> None:
    subprocess.run(
        ["osascript", "-e", 'tell application "QuickTime Player" to close every document'],
        capture_output=True,
    )


def main() -> None:
    db_path = Path(sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    dataset_manifest.create_db(db_path)  # no-op on an existing, up-to-date db
    rows = dataset_manifest.fetch_random_sample(db_path, n)
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
        answer = input("Correct? (y/n, r to redo previous, Enter to skip): ").strip().lower()
        _close_player()

        if answer == "r":
            if tally.undo_last() is None:
                print("Nothing to redo yet.\n")
                continue
            index -= 1
            continue

        outcome = "y" if answer == "y" else "n" if answer == "n" else "skip"
        tally.record(outcome)
        if outcome != "skip":
            dataset_manifest.record_review(db_path, record["id"], correct=(outcome == "y"))
        index += 1

    reviewed = tally.correct + tally.incorrect
    print(f"\nReviewed {reviewed} clips ({tally.skipped} skipped): {tally.correct} correct, {tally.incorrect} incorrect.")
    if reviewed:
        print(f"Agreement: {tally.correct / reviewed:.1%}")


if __name__ == "__main__":
    main()
