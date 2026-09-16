from pathlib import Path

import cv2
import numpy as np

from biomercs_ml import config
from biomercs_ml.models import HudSample


def load_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"Could not load image: {path}")
    return img


def load_digit_templates(dir_path: str) -> dict[str, np.ndarray]:
    templates = {}
    for path in Path(dir_path).glob("*.png"):
        templates[path.stem] = load_image(str(path))
    return templates


def match_digit(crop: np.ndarray, templates: dict[str, np.ndarray]) -> tuple[str, float]:
    best_digit = "?"
    best_score = -1.0
    for digit, template in templates.items():
        resized = cv2.resize(template, (crop.shape[1], crop.shape[0]))
        result = cv2.matchTemplate(crop, resized, cv2.TM_CCOEFF_NORMED)
        score = float(result[0, 0])
        if score > best_score:
            best_score = score
            best_digit = digit
    return best_digit, best_score


def read_digit_slots(
    frame: np.ndarray,
    slots: list[tuple[int, int, int, int]],
    templates: dict[str, np.ndarray],
    offset: tuple[int, int] = (0, 0),
) -> tuple[int | None, float]:
    dx, dy = offset
    digits = []
    confidences = []
    for x, y, w, h in slots:
        crop = frame[y + dy : y + dy + h, x + dx : x + dx + w]
        digit, score = match_digit(crop, templates)
        digits.append(digit)
        confidences.append(score)
    min_confidence = min(confidences)
    if min_confidence < config.DIGIT_MATCH_MIN_CONFIDENCE:
        return None, min_confidence
    return int("".join(digits)), min_confidence


def read_timer(
    frame: np.ndarray, templates: dict[str, np.ndarray], offset: tuple[int, int] = (0, 0)
) -> tuple[float | None, float]:
    minutes, minutes_conf = read_digit_slots(frame, config.TIMER_MINUTES_SLOTS, templates, offset)
    seconds, seconds_conf = read_digit_slots(frame, config.TIMER_SECONDS_SLOTS, templates, offset)
    confidence = min(minutes_conf, seconds_conf)
    if minutes is None or seconds is None:
        return None, confidence
    return float(minutes * 60 + seconds), confidence


def read_combo(
    frame: np.ndarray, templates: dict[str, np.ndarray], offset: tuple[int, int] = (0, 0)
) -> tuple[int | None, float]:
    return read_digit_slots(frame, config.COMBO_DIGIT_SLOTS, templates, offset)


def is_valid_hud_frame(
    frame: np.ndarray, combo_label_template: np.ndarray, offset: tuple[int, int] = (0, 0)
) -> tuple[bool, float]:
    dx, dy = offset
    x, y, w, h = config.COMBO_LABEL_ROI
    crop = frame[y + dy : y + dy + h, x + dx : x + dx + w]
    resized_template = cv2.resize(combo_label_template, (w, h))
    result = cv2.matchTemplate(crop, resized_template, cv2.TM_CCOEFF_NORMED)
    score = float(result[0, 0])
    return score >= config.COMBO_LABEL_MIN_CONFIDENCE, score


def find_best_offset(
    frame: np.ndarray,
    combo_label_template: np.ndarray,
    search_radius_px: int = config.OFFSET_SEARCH_RADIUS_PX,
) -> tuple[tuple[int, int], float]:
    base_x, base_y, w, h = config.COMBO_LABEL_ROI
    resized_template = cv2.resize(combo_label_template, (w, h))
    frame_h, frame_w = frame.shape[:2]

    best_offset = (0, 0)
    best_score = -1.0
    for dy in range(-search_radius_px, search_radius_px + 1):
        for dx in range(-search_radius_px, search_radius_px + 1):
            x, y = base_x + dx, base_y + dy
            if x < 0 or y < 0 or x + w > frame_w or y + h > frame_h:
                continue
            crop = frame[y : y + h, x : x + w]
            result = cv2.matchTemplate(crop, resized_template, cv2.TM_CCOEFF_NORMED)
            score = float(result[0, 0])
            if score > best_score:
                best_score = score
                best_offset = (dx, dy)
    return best_offset, best_score


def is_new_session(prev_timer_s: float, curr_timer_s: float) -> bool:
    # The timer only ever drifts down by ~one sampling interval per step,
    # or jumps up by a bonus (at most a handful of simultaneous +5s
    # kills). Anything outside that plausible range means a new
    # stage/round started partway through the recording.
    delta = curr_timer_s - prev_timer_s
    return delta < -config.SESSION_RESET_DROP_S or delta > config.SESSION_RESET_JUMP_S


def _calibrate_offset(
    cap: cv2.VideoCapture,
    combo_label_template: np.ndarray,
    frame_interval: int,
    max_candidates: int = config.CALIBRATION_MAX_FRAMES,
) -> tuple[int, int]:
    best_offset = (0, 0)
    best_score = -1.0
    frame_idx = 0
    candidates_tried = 0
    while candidates_tried < max_candidates:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            offset, score = find_best_offset(frame, combo_label_template)
            if score > best_score:
                best_score = score
                best_offset = offset
            candidates_tried += 1
        frame_idx += 1

    if best_score < config.COMBO_LABEL_MIN_CONFIDENCE:
        return (0, 0)
    return best_offset


def sample_video(
    video_path: Path,
    timer_templates: dict[str, np.ndarray],
    combo_templates: dict[str, np.ndarray],
    combo_label_template: np.ndarray,
    interval_s: float = config.SAMPLE_INTERVAL_S,
) -> list[HudSample]:
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = max(1, round(fps * interval_s))

    offset = _calibrate_offset(cap, combo_label_template, frame_interval)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    samples = []
    session_id = 0
    last_timer_value: float | None = None
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1

        if (frame_idx - 1) % frame_interval != 0:
            continue

        timestamp_s = (frame_idx - 1) / fps
        is_valid, hud_conf = is_valid_hud_frame(frame, combo_label_template, offset)
        if not is_valid:
            continue

        timer_value, timer_conf = read_timer(frame, timer_templates, offset)
        combo_value, combo_conf = read_combo(frame, combo_templates, offset)
        confidence = min(hud_conf, timer_conf, combo_conf)

        if timer_value is not None:
            if last_timer_value is not None and is_new_session(last_timer_value, timer_value):
                session_id += 1
            last_timer_value = timer_value

        samples.append(HudSample(timestamp_s, session_id, timer_value, combo_value, confidence))
    cap.release()

    return [s for s in samples if s.timer_value_s is not None and s.combo_value is not None]
