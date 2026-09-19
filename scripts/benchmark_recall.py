"""Score the detection pipeline against a hand-counted ground-truth window.

Usage: uv run python scripts/benchmark_recall.py [truth.json] [--refresh]

Runs the real sampler over the ground-truth window, then the same
session-assignment / kill-grouping / labeling code pipeline.run uses, and
prints recall, clip precision and count accuracy. The slow step (raw HUD
sampling, ~2 min) is cached under tmp\\benchmark\\; pass --refresh after
changing hud_reader so the cache doesn't go stale.
"""
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

import cv2

from biomercs_ml import benchmark, config, hud_reader, pipeline
from biomercs_ml.models import RawHudSample

DEFAULT_TRUTH_PATH = Path("benchmarks/video4_t480-650.json")
CACHE_DIR = Path("tmp/benchmark")


def sample_window(truth: benchmark.GroundTruth) -> list[RawHudSample]:
    video_path = Path(truth.source_video)
    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
    popup_digit_templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
    popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_interval = max(1, round(fps * config.SAMPLE_INTERVAL_S))
    # Same calibration sample_video does, so the offset matches production.
    cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)
    offset = hud_reader._calibrate_offset(cap, combo_label_template, frame_interval)
    cap.release()

    # Sample ticks sit on multiples of frame_interval, like sample_video's.
    start_frame = math.ceil((truth.scored_start_s - truth.sampling_padding_s) * fps / frame_interval) * frame_interval
    end_frame = (truth.scored_end_s + truth.sampling_padding_s) * fps
    return hud_reader._sample_range(
        video_path, timer_templates, combo_templates, combo_label_template,
        popup_digit_templates, popup_label_template, offset, fps, frame_interval,
        total_frames / fps, start_frame, end_frame,
    )


def load_or_sample(truth: benchmark.GroundTruth, cache_path: Path, refresh: bool) -> list[RawHudSample]:
    if cache_path.exists() and not refresh:
        return [RawHudSample(**row) for row in json.loads(cache_path.read_text())]
    raw_samples = sample_window(truth)
    if not raw_samples:
        sys.exit(f"0 samples from {truth.source_video} -- wrong path?")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps([asdict(s) for s in raw_samples]))
    return raw_samples


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    refresh = "--refresh" in sys.argv
    truth_path = Path(args[0]) if args else DEFAULT_TRUTH_PATH
    truth = benchmark.load_ground_truth(truth_path)

    raw_samples = load_or_sample(truth, CACHE_DIR / f"{truth_path.stem}_raw_samples.json", refresh)
    samples = hud_reader._assign_session_ids(raw_samples)
    detections = [
        benchmark.DetectedClip(group.timestamp_s, label.n_bonus, label.n_bullet)
        for group, label in pipeline.label_kill_groups(samples)
    ]
    score = benchmark.score_detections(truth, detections)

    print(f"samples: {len(samples)}  sessions: {len({s.session_id for s in samples})}")
    print(f"clips in scored window: {score.clips_scored}")
    print(f"recall:         {score.kills_covered}/{score.total_kills} kills = {score.recall:.1%}")
    print(f"precision:      {score.clips_hitting}/{score.clips_scored} clips hit a real kill = {score.precision:.1%}")
    print(f"count accuracy: {score.clips_count_correct}/{score.clips_hitting} hitting clips exact = {score.count_accuracy:.1%}")


if __name__ == "__main__":
    main()
