import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from biomercs_ml import config


@dataclass
class TruthKill:
    timestamp_s: float
    kind: Literal["bonus", "bullet"]
    count: int


@dataclass
class GroundTruth:
    source_video: str
    scored_start_s: float
    scored_end_s: float
    sampling_padding_s: float
    kills: list[TruthKill]


@dataclass
class DetectedClip:
    timestamp_s: float
    n_bonus: int
    n_bullet: int


@dataclass
class BenchmarkScore:
    total_kills: int
    kills_covered: int
    clips_scored: int
    clips_hitting: int
    clips_count_correct: int

    @property
    def recall(self) -> float:
        return self.kills_covered / self.total_kills if self.total_kills else 0.0

    @property
    def precision(self) -> float:
        return self.clips_hitting / self.clips_scored if self.clips_scored else 0.0

    @property
    def count_accuracy(self) -> float:
        return self.clips_count_correct / self.clips_hitting if self.clips_hitting else 0.0


def load_ground_truth(path: Path) -> GroundTruth:
    data = json.loads(path.read_text())
    origin_s = data["clip_start_s"] + data["alignment_shift_s"]
    return GroundTruth(
        source_video=data["source_video"],
        scored_start_s=origin_s,
        scored_end_s=origin_s + data["clip_duration_s"],
        sampling_padding_s=data["sampling_padding_s"],
        kills=[TruthKill(origin_s + k["clip_time_s"], k["kind"], k["count"]) for k in data["kills"]],
    )


def _kills_in_clip_window(truth: GroundTruth, clip: DetectedClip) -> list[TruthKill]:
    window_start_s = clip.timestamp_s - config.CLIP_BEFORE_S
    window_end_s = clip.timestamp_s + config.CLIP_AFTER_S
    return [k for k in truth.kills if window_start_s <= k.timestamp_s <= window_end_s]


def score_detections(truth: GroundTruth, detections: list[DetectedClip]) -> BenchmarkScore:
    clips = [c for c in detections if truth.scored_start_s <= c.timestamp_s <= truth.scored_end_s]

    covered_ids: set[int] = set()
    clips_hitting = 0
    clips_count_correct = 0
    for clip in clips:
        kills = _kills_in_clip_window(truth, clip)
        if not kills:
            continue
        clips_hitting += 1
        covered_ids.update(id(k) for k in kills)
        truth_bonus = sum(k.count for k in kills if k.kind == "bonus")
        truth_bullet = sum(k.count for k in kills if k.kind == "bullet")
        if (clip.n_bonus, clip.n_bullet) == (truth_bonus, truth_bullet):
            clips_count_correct += 1

    return BenchmarkScore(
        total_kills=sum(k.count for k in truth.kills),
        kills_covered=sum(k.count for k in truth.kills if id(k) in covered_ids),
        clips_scored=len(clips),
        clips_hitting=clips_hitting,
        clips_count_correct=clips_count_correct,
    )
