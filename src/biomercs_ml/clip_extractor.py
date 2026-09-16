import subprocess
from pathlib import Path

from biomercs_ml import config


def extract_clip(
    video_path: Path,
    timestamp_s: float,
    output_path: Path,
    before_s: float = config.CLIP_BEFORE_S,
    after_s: float = config.CLIP_AFTER_S,
) -> Path:
    start = max(0.0, timestamp_s - before_s)
    duration = before_s + after_s
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(start),
            "-i",
            str(video_path),
            "-t",
            str(duration),
            "-c",
            "copy",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path
