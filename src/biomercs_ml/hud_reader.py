from collections import Counter
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


def load_digit_templates(dir_path: str) -> dict[str, list[np.ndarray]]:
    templates = {}
    for digit_dir in Path(dir_path).iterdir():
        if not digit_dir.is_dir():
            continue
        templates[digit_dir.name] = [load_image(str(path)) for path in sorted(digit_dir.glob("*.png"))]
    return templates


def match_digit(
    crop: np.ndarray,
    templates: dict[str, list[np.ndarray]],
    target_size: tuple[int, int] | None = None,
) -> tuple[str, float]:
    target_w, target_h = target_size if target_size is not None else (crop.shape[1], crop.shape[0])
    best_digit = "?"
    best_score = -1.0
    for digit, samples in templates.items():
        for template in samples:
            resized = cv2.resize(template, (target_w, target_h))
            # .max() rather than [0, 0]: when crop is padded larger than the
            # resized template (read_digit_slots' search margin), this finds
            # the best-aligned position within it; when crop is exactly
            # target-sized, the result is 1x1 and this is equivalent to [0, 0].
            result = cv2.matchTemplate(crop, resized, cv2.TM_CCOEFF_NORMED)
            score = float(result.max())
            # A digit only needs to win with any one of its own samples
            # -- see "fifth root cause" in DECISIONS.md.
            if score > best_score:
                best_score = score
                best_digit = digit
    return best_digit, best_score


def read_digit_slots(
    frame: np.ndarray,
    slots: list[tuple[int, int, int, int]],
    templates: dict[str, np.ndarray],
    offset: tuple[int, int] = (0, 0),
    right_bound: int | None = None,
) -> tuple[int | None, float]:
    dx, dy = offset
    frame_h, frame_w = frame.shape[:2]
    margin = config.DIGIT_SEARCH_MARGIN_PX
    hard_right_bound = right_bound if right_bound is not None else frame_w
    digits = []
    confidences = []
    for i, (x, y, w, h) in enumerate(slots):
        # Adjacent digit slots (or another HUD element just past the
        # last one, e.g. the "COMBO" label sitting 1px after combo's
        # last digit) can sit close enough that the margin below would
        # otherwise search into that neighbor's ink and match against
        # it instead. Clamp the margin's *extension* to the midpoint
        # with each neighboring slot, and to `right_bound` past the
        # last one, but never shrink past the slot's own nominal box --
        # that box is exactly the template's target size, so going
        # smaller than it would break the match outright.
        nominal_x0, nominal_x1 = x + dx, x + dx + w
        left_limit = 0
        if i > 0:
            prev_x, _, prev_w, _ = slots[i - 1]
            left_limit = (prev_x + prev_w + x) // 2 + dx
        right_limit = hard_right_bound
        if i < len(slots) - 1:
            next_x, _, _, _ = slots[i + 1]
            right_limit = min(right_limit, (x + w + next_x) // 2 + dx)

        px0 = min(nominal_x0, max(0, left_limit, nominal_x0 - margin))
        px1 = max(nominal_x1, min(frame_w, right_limit, nominal_x1 + margin))
        py0 = max(0, y + dy - margin)
        py1 = min(frame_h, y + dy + h + margin)
        crop = frame[py0:py1, px0:px1]
        digit, score = match_digit(crop, templates, target_size=(w, h))
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
    # The "COMBO" label sits immediately after the last digit slot (see
    # config.COMBO_LABEL_ROI) -- bound the margin there too, not just
    # between the digit slots themselves.
    value, confidence = read_digit_slots(
        frame,
        config.COMBO_DIGIT_SLOTS,
        templates,
        offset,
        right_bound=config.COMBO_LABEL_ROI[0] + offset[0],
    )
    # The game's fixed enemy pool means the combo counter can never
    # exceed config.MAX_PLAUSIBLE_COMBO_VALUE -- a reading above it is
    # always a misread, no matter how confident the match.
    if value is not None and value > config.MAX_PLAUSIBLE_COMBO_VALUE:
        return None, confidence
    return value, confidence


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


def is_popup_visible(
    frame: np.ndarray, popup_label_template: np.ndarray, offset: tuple[int, int] = (0, 0)
) -> tuple[bool, float]:
    dx, dy = offset
    x, y, w, h = config.POPUP_LABEL_ROI
    crop = frame[y + dy : y + dy + h, x + dx : x + dx + w]
    resized_template = cv2.resize(popup_label_template, (w, h))
    result = cv2.matchTemplate(crop, resized_template, cv2.TM_CCOEFF_NORMED)
    score = float(result[0, 0])
    return score >= config.POPUP_LABEL_MIN_CONFIDENCE, score


def read_popup_ones_digit(
    frame: np.ndarray, templates: dict[str, np.ndarray], offset: tuple[int, int] = (0, 0)
) -> tuple[int | None, float]:
    # The "sec." label sits only a few pixels after this digit (see
    # config.POPUP_LABEL_ROI) -- bound the margin there too.
    return read_digit_slots(
        frame,
        [config.POPUP_ONES_DIGIT_SLOT],
        templates,
        offset,
        right_bound=config.POPUP_LABEL_ROI[0] + offset[0],
    )


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
    votes: Counter[tuple[int, int]] = Counter()
    frame_idx = 0
    candidates_tried = 0
    while candidates_tried < max_candidates:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            offset, score = find_best_offset(frame, combo_label_template)
            candidates_tried += 1
            if score >= config.CALIBRATION_MIN_CONFIDENCE:
                votes[offset] += 1
                if votes[offset] >= config.CALIBRATION_MIN_VOTES:
                    return offset
        frame_idx += 1

    return (0, 0)


def _majority_value(
    readings: list[tuple[int | float | None, float]],
) -> tuple[int | float | None, float]:
    valid = [(value, confidence) for value, confidence in readings if value is not None]
    if not valid:
        return None, max((confidence for _, confidence in readings), default=0.0)
    votes = Counter(value for value, _ in valid)
    winning_value, _ = votes.most_common(1)[0]
    winning_confidences = [confidence for value, confidence in valid if value == winning_value]
    return winning_value, max(winning_confidences)


def sample_video(
    video_path: Path,
    timer_templates: dict[str, np.ndarray],
    combo_templates: dict[str, np.ndarray],
    combo_label_template: np.ndarray,
    popup_digit_templates: dict[str, np.ndarray],
    popup_label_template: np.ndarray,
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

        # The calibrated offset is derived from (and only applied to) the
        # combo-label validity check above -- digit slots are calibrated
        # independently and reading them at that same offset can break
        # otherwise-correct matches (see test_hud_reader_video.py).
        burst_frames = [frame]
        for _ in range(config.SAMPLE_VOTE_FRAMES - 1):
            burst_ret, burst_frame = cap.read()
            if not burst_ret:
                break
            burst_frames.append(burst_frame)
            frame_idx += 1

        timer_value, timer_conf = _majority_value(
            [read_timer(f, timer_templates) for f in burst_frames]
        )
        combo_value, combo_conf = _majority_value(
            [read_combo(f, combo_templates) for f in burst_frames]
        )
        confidence = min(hud_conf, timer_conf, combo_conf)

        if timer_value is not None:
            if last_timer_value is not None and is_new_session(last_timer_value, timer_value):
                session_id += 1
            last_timer_value = timer_value

        # Popup presence uses the calibrated offset like the combo-label
        # validity check above; the ones digit, like the timer/combo
        # digit slots, does not (see the comment above).
        popup_visible, _ = _majority_value(
            [is_popup_visible(f, popup_label_template, offset) for f in burst_frames]
        )
        pickup_popup = False
        if popup_visible:
            ones_digit, _ = _majority_value(
                [read_popup_ones_digit(f, popup_digit_templates) for f in burst_frames]
            )
            pickup_popup = ones_digit == 0

        samples.append(
            HudSample(timestamp_s, session_id, timer_value, combo_value, confidence, pickup_popup)
        )
    cap.release()

    return [s for s in samples if s.timer_value_s is not None and s.combo_value is not None]
