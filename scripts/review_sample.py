"""Pull a random sample of labeled clips for manual review.

Usage: uv run python scripts/review_sample.py <db_path> [n]
"""
import subprocess
import sys
from pathlib import Path

from biomercs_ml import dataset_manifest

COLUMNS = [
    "id", "clip_path", "label_kind", "n_bonus", "n_bullet",
    "source_video", "session_id", "event_timestamp_s", "confidence", "created_at",
]


def main() -> None:
    db_path = Path(sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    rows = dataset_manifest.fetch_random_sample(db_path, n)
    print(f"Reviewing {len(rows)} clips. Each will open in your default player;")
    print("note whether the label matches what you see, then close the player to continue.\n")

    for row in rows:
        record = dict(zip(COLUMNS, row))
        print(f"id={record['id']} label={record['label_kind']} "
              f"(bonus={record['n_bonus']}, bullet={record['n_bullet']}) "
              f"confidence={record['confidence']:.2f} clip={record['clip_path']}")
        subprocess.run(["open", record["clip_path"]])
        input("Press Enter for the next clip...")


if __name__ == "__main__":
    main()
