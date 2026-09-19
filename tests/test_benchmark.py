from pathlib import Path

from biomercs_ml import benchmark, config
from biomercs_ml.benchmark import DetectedClip, GroundTruth, TruthKill

VIDEO4_TRUTH_PATH = Path("benchmarks/video4_t480-650.json")


def _truth(*kills: TruthKill, scored_start_s: float = 0.0, scored_end_s: float = 1000.0) -> GroundTruth:
    return GroundTruth(
        source_video="unused.mp4",
        scored_start_s=scored_start_s,
        scored_end_s=scored_end_s,
        sampling_padding_s=0.0,
        kills=list(kills),
    )


def test_load_ground_truth_has_the_49_hand_counted_kills_split_36_bonus_13_bullet():
    truth = benchmark.load_ground_truth(VIDEO4_TRUTH_PATH)

    bonus = sum(k.count for k in truth.kills if k.kind == "bonus")
    bullet = sum(k.count for k in truth.kills if k.kind == "bullet")
    assert (bonus, bullet) == (36, 13)


def test_load_ground_truth_shifts_clip_relative_times_to_absolute_video_time():
    truth = benchmark.load_ground_truth(VIDEO4_TRUTH_PATH)

    # clip 00:03 -> 480 (clip start) + 3 - 3 (alignment shift)
    assert truth.kills[0].timestamp_s == 480.0
    assert truth.scored_start_s == 477.0
    assert truth.scored_end_s == 647.0


def test_score_counts_a_kill_inside_a_clip_window_as_covered():
    truth = _truth(TruthKill(100.0, "bonus", 1))

    score = benchmark.score_detections(truth, [DetectedClip(101.0, n_bonus=1, n_bullet=0)])

    assert score.kills_covered == 1
    assert score.recall == 1.0


def test_score_ignores_a_kill_outside_every_clip_window():
    truth = _truth(TruthKill(100.0, "bonus", 1))
    too_late = 100.0 + config.CLIP_BEFORE_S + 0.1

    score = benchmark.score_detections(truth, [DetectedClip(too_late, n_bonus=1, n_bullet=0)])

    assert score.kills_covered == 0
    assert score.recall == 0.0


def test_score_weights_recall_by_kill_count_not_by_event_count():
    truth = _truth(TruthKill(100.0, "bonus", 3), TruthKill(200.0, "bullet", 1))

    score = benchmark.score_detections(truth, [DetectedClip(100.0, n_bonus=3, n_bullet=0)])

    assert (score.kills_covered, score.total_kills) == (3, 4)
    assert score.recall == 0.75


def test_score_precision_is_the_fraction_of_clips_that_contain_a_real_kill():
    truth = _truth(TruthKill(100.0, "bonus", 1))
    clips = [DetectedClip(100.0, 1, 0), DetectedClip(500.0, 1, 0)]

    score = benchmark.score_detections(truth, clips)

    assert score.precision == 0.5


def test_score_count_accuracy_requires_exact_bonus_and_bullet_counts():
    truth = _truth(TruthKill(100.0, "bonus", 2), TruthKill(300.0, "bullet", 1))
    clips = [DetectedClip(100.0, n_bonus=2, n_bullet=0), DetectedClip(300.0, n_bonus=0, n_bullet=2)]

    score = benchmark.score_detections(truth, clips)

    assert score.clips_count_correct == 1
    assert score.count_accuracy == 0.5


def test_score_sums_every_truth_kill_inside_one_clip_window_when_checking_counts():
    truth = _truth(TruthKill(100.0, "bonus", 1), TruthKill(101.5, "bullet", 1))

    score = benchmark.score_detections(truth, [DetectedClip(100.5, n_bonus=1, n_bullet=1)])

    assert score.clips_count_correct == 1


def test_score_only_considers_clips_inside_the_scored_range():
    truth = _truth(TruthKill(100.0, "bonus", 1), scored_start_s=90.0, scored_end_s=110.0)
    clips = [DetectedClip(100.0, 1, 0), DetectedClip(500.0, 1, 0)]

    score = benchmark.score_detections(truth, clips)

    assert score.clips_scored == 1
    assert score.precision == 1.0


def test_score_with_no_clips_is_all_zero_without_dividing_by_zero():
    truth = _truth(TruthKill(100.0, "bonus", 1))

    score = benchmark.score_detections(truth, [])

    assert (score.recall, score.precision, score.count_accuracy) == (0.0, 0.0, 0.0)
