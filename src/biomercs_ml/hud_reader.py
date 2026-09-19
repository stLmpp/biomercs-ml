import math
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from biomercs_ml import config
from biomercs_ml.models import HudSample, RawHudSample


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


def waist_notch_score(crop: np.ndarray) -> float:
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    binary = cv2.threshold(hsv[:, :, 2], 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    h = binary.shape[0]
    top_band = range(0, h // 3)
    middle_band = range(h // 3, 2 * h // 3)
    bottom_band = range(2 * h // 3, h)

    def leftmost_ink_positions(rows: range) -> list[int]:
        positions = []
        for row in rows:
            ink = np.where(binary[row] > 0)[0]
            if len(ink) > 0:
                positions.append(int(ink[0]))
        return positions

    top_and_bottom = leftmost_ink_positions(top_band) + leftmost_ink_positions(bottom_band)
    middle = leftmost_ink_positions(middle_band)
    if not top_and_bottom or not middle:
        return 0.0
    return float(np.mean(middle) - np.mean(top_and_bottom))


def base_widen_score(crop: np.ndarray) -> float:
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    binary = cv2.threshold(hsv[:, :, 2], 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    width = binary.shape[1]

    def row_span(row: int) -> tuple[int, int] | None:
        ink = np.where(binary[row] > 0)[0]
        if len(ink) == 0:
            return None
        return int(ink[0]), int(ink[-1])

    spans = [row_span(row) for row in range(binary.shape[0])]
    # A row spanning edge-to-edge is a HUD border line bleeding into the
    # margin read_digit_slots adds (config.DIGIT_SEARCH_MARGIN_PX), not
    # part of the glyph -- exclude it, or it would stretch the ink
    # bounding box below back out to the crop's raw (padded) shape.
    glyph_rows = [i for i, s in enumerate(spans) if s is not None and (s[1] - s[0] + 1) < width - 1]
    if not glyph_rows:
        return 0.0
    glyph_rows_set = set(glyph_rows)

    ink_top, ink_bottom = glyph_rows[0], glyph_rows[-1]
    ink_h = ink_bottom - ink_top + 1
    taper_band = range(ink_top + int(0.5 * ink_h), ink_top + int(0.85 * ink_h))
    base_band = range(ink_top + int(0.85 * ink_h), ink_bottom + 1)

    def rightmost_ink_positions(rows: range) -> list[int]:
        return [spans[row][1] for row in rows if row in glyph_rows_set]

    taper = rightmost_ink_positions(taper_band)
    base = rightmost_ink_positions(base_band)
    if not taper or not base:
        return 0.0
    return float(np.mean(base) - np.min(taper))


def match_digit(
    crop: np.ndarray,
    templates: dict[str, list[np.ndarray]],
    target_size: tuple[int, int] | None = None,
    apply_waist_notch_tiebreak: bool = False,
) -> tuple[str, float]:
    target_w, target_h = target_size if target_size is not None else (crop.shape[1], crop.shape[0])
    best_digit = "?"
    best_score = -1.0
    per_digit_best_score: dict[str, float] = {}
    for digit, samples in templates.items():
        digit_best_score = -1.0
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
            if score > digit_best_score:
                digit_best_score = score
        per_digit_best_score[digit] = digit_best_score
        if digit_best_score > best_score:
            best_score = digit_best_score
            best_digit = digit

    # Combo-font "3" structurally over-matches "8"/"9" under raw-pixel
    # correlation (see DECISIONS.md, "fourth root cause" and later
    # entries) -- a geometric check breaks the tie for this specific,
    # proven ambiguity only. Confirmed NOT to hold for the timer font,
    # so this must stay opt-in, never the default -- see config.py,
    # WAIST_NOTCH_THREE_THRESHOLD.
    if apply_waist_notch_tiebreak and best_digit in ("8", "9") and "3" in per_digit_best_score:
        if waist_notch_score(crop) > config.WAIST_NOTCH_THREE_THRESHOLD:
            return "3", per_digit_best_score["3"]

    # Same family, different axis: combo-font "2" structurally
    # over-matches "8"/"9" too (see docs/superpowers/KNOWN_BUGS.md,
    # `combo-2-vs-8-misread`) -- base_widen_score's rightmost-ink jump
    # breaks this tie the way waist_notch_score breaks the "3" one
    # above. Same opt-in guard applies: proven only for the combo font.
    if apply_waist_notch_tiebreak and best_digit in ("8", "9") and "2" in per_digit_best_score:
        if base_widen_score(crop) > config.BASE_WIDEN_TWO_THRESHOLD:
            return "2", per_digit_best_score["2"]

    return best_digit, best_score


def read_digit_slots(
    frame: np.ndarray,
    slots: list[tuple[int, int, int, int]],
    templates: dict[str, np.ndarray],
    offset: tuple[int, int] = (0, 0),
    right_bound: int | None = None,
    apply_waist_notch_tiebreak: bool = False,
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
        digit, score = match_digit(
            crop, templates, target_size=(w, h), apply_waist_notch_tiebreak=apply_waist_notch_tiebreak
        )
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
        apply_waist_notch_tiebreak=True,
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

    def score_at(dx: int, dy: int) -> float | None:
        x, y = base_x + dx, base_y + dy
        if x < 0 or y < 0 or x + w > frame_w or y + h > frame_h:
            return None
        crop = frame[y : y + h, x : x + w]
        result = cv2.matchTemplate(crop, resized_template, cv2.TM_CCOEFF_NORMED)
        return float(result[0, 0])

    def best_in(dx_range: range, dy_range: range, best_offset: tuple[int, int], best_score: float):
        for dy in dy_range:
            for dx in dx_range:
                if abs(dx) > search_radius_px or abs(dy) > search_radius_px:
                    continue
                score = score_at(dx, dy)
                if score is not None and score > best_score:
                    best_score = score
                    best_offset = (dx, dy)
        return best_offset, best_score

    stride = config.OFFSET_COARSE_SEARCH_STRIDE_PX
    best_offset, best_score = best_in(
        range(-search_radius_px, search_radius_px + 1, stride),
        range(-search_radius_px, search_radius_px + 1, stride),
        (0, 0),
        -1.0,
    )
    coarse_dx, coarse_dy = best_offset
    best_offset, best_score = best_in(
        range(coarse_dx - stride, coarse_dx + stride + 1),
        range(coarse_dy - stride, coarse_dy + stride + 1),
        best_offset,
        best_score,
    )
    return best_offset, best_score


def is_new_session(prev_timer_s: float, curr_timer_s: float) -> bool:
    # The timer only ever drifts down by ~one sampling interval per step,
    # or jumps up by a bonus (at most a handful of simultaneous +5s
    # kills). Anything outside that plausible range means a new
    # stage/round started partway through the recording.
    delta = curr_timer_s - prev_timer_s
    return delta < -config.SESSION_RESET_DROP_S or delta > config.SESSION_RESET_JUMP_S


def _is_spurious_timer_spike(prev_timer_s: float, curr_timer_s: float, next_timer_s: float) -> bool:
    # A tick's timer reading that conflicts with a neighbor on either
    # side, when that same neighbor pair otherwise agrees with each
    # other, is a transient misread (e.g. background scene geometry
    # sweeping across the timer's translucent digits for a few frames),
    # not a real session boundary -- a real new-round reset persists
    # instead of reverting. Checked in both directions, not just
    # prev->curr: SESSION_RESET_JUMP_S is loosened to tolerate real rare
    # stacked bonuses (up to ~105s), so a moderate misread (e.g. +50s)
    # can itself land under that ceiling and go undetected going up,
    # while *reverting* from it on the next tick looks like an oversized
    # drop against the much tighter SESSION_RESET_DROP_S. See
    # DECISIONS.md, "timer-noise-session-fragmentation".
    return not is_new_session(prev_timer_s, next_timer_s) and (
        is_new_session(prev_timer_s, curr_timer_s) or is_new_session(curr_timer_s, next_timer_s)
    )


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


def _sample_range(
    video_path: Path,
    timer_templates: dict[str, np.ndarray],
    combo_templates: dict[str, np.ndarray],
    combo_label_template: np.ndarray,
    popup_digit_templates: dict[str, np.ndarray],
    popup_label_template: np.ndarray,
    offset: tuple[int, int],
    fps: float,
    frame_interval: int,
    duration_s: float,
    start_frame_idx: int,
    end_frame_idx: float,
) -> list[RawHudSample]:
    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame_idx)

    results = []
    frame_idx = start_frame_idx
    last_logged_percent = -config.PROGRESS_LOG_INTERVAL_PERCENT
    while frame_idx < end_frame_idx:
        ret, frame = cap.read()
        if not ret:
            break
        current_idx = frame_idx
        frame_idx += 1

        if current_idx % frame_interval != 0:
            continue

        timestamp_s = current_idx / fps
        if duration_s > 0:
            percent = int(timestamp_s / duration_s * 100)
            if percent >= last_logged_percent + config.PROGRESS_LOG_INTERVAL_PERCENT:
                print(f"sample_video: {percent}% ({timestamp_s:.1f}s/{duration_s:.1f}s), {len(results)} samples so far")
                last_logged_percent = percent
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

        # Popup presence uses the calibrated offset like the combo-label
        # validity check above; the ones digit, like the timer/combo
        # digit slots, does not (see the comment above).
        popup_visible, _ = _majority_value(
            [is_popup_visible(f, popup_label_template, offset) for f in burst_frames]
        )
        pickup_popup = False
        bonus_popup = False
        if popup_visible:
            ones_digit, _ = _majority_value(
                [read_popup_ones_digit(f, popup_digit_templates) for f in burst_frames]
            )
            pickup_popup = ones_digit == 0
            bonus_popup = not pickup_popup

        results.append(
            RawHudSample(timestamp_s, timer_value, combo_value, confidence, pickup_popup, bonus_popup)
        )
    cap.release()

    return results


def sample_video(
    video_path: Path,
    timer_templates: dict[str, np.ndarray],
    combo_templates: dict[str, np.ndarray],
    combo_label_template: np.ndarray,
    popup_digit_templates: dict[str, np.ndarray],
    popup_label_template: np.ndarray,
    interval_s: float = config.SAMPLE_INTERVAL_S,
    max_workers: int | None = None,
) -> list[HudSample]:
    workers = max(1, max_workers if max_workers is not None else (os.cpu_count() or 1))

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = max(1, round(fps * interval_s))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_s = total_frames / fps if fps and total_frames else 0.0

    # A long pre-gameplay stretch (loading/menus, or a "preparation lap"
    # collecting time bonuses before the first kill -- a common real run
    # structure) can run past calibration's whole scan budget if it
    # starts from frame 0, locking in the wrong fallback offset for the
    # entire rest of the video. Starting from the middle sidesteps this:
    # by a run's midpoint, real gameplay HUD is almost certainly on
    # screen, regardless of how long the pre-gameplay stretch was.
    cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)
    offset = _calibrate_offset(cap, combo_label_template, frame_interval)
    cap.release()

    total_ticks = (total_frames + frame_interval - 1) // frame_interval if total_frames > 0 else 0

    if workers == 1 or total_ticks <= 1:
        end_frame_idx = total_ticks * frame_interval if total_ticks > 0 else math.inf
        raw_samples = _sample_range(
            video_path, timer_templates, combo_templates, combo_label_template,
            popup_digit_templates, popup_label_template, offset, fps, frame_interval,
            duration_s, 0, end_frame_idx,
        )
    else:
        chunk_ticks = math.ceil(total_ticks / workers)
        tick_ranges = [
            (i * chunk_ticks, min(total_ticks, (i + 1) * chunk_ticks)) for i in range(workers)
        ]
        tick_ranges = [(start, end) for start, end in tick_ranges if start < end]

        raw_samples = []
        with ProcessPoolExecutor(max_workers=len(tick_ranges)) as executor:
            futures = [
                executor.submit(
                    _sample_range, video_path, timer_templates, combo_templates,
                    combo_label_template, popup_digit_templates, popup_label_template,
                    offset, fps, frame_interval, duration_s,
                    start_tick * frame_interval, end_tick * frame_interval,
                )
                for start_tick, end_tick in tick_ranges
            ]
            # Concatenated in submission order, not completion order --
            # chunks are naturally time-ordered, so this is exactly the
            # merged, ordered list session_id assignment below expects.
            for future in futures:
                raw_samples.extend(future.result())

    return _assign_session_ids(raw_samples)


def _assign_session_ids(raw_samples: list[RawHudSample]) -> list[HudSample]:
    # A lone tick whose timer reading conflicts with its neighbor on
    # both sides -- disagreeing with the predecessor, reverted by the
    # very next reading -- is a transient misread, not a real
    # discontinuity. Identify those up front (using the raw,
    # never-corrected readings on both sides, not each other's
    # corrections) so they never reach the sequential pass below and
    # spuriously split a session.
    valid_indices = [i for i, raw in enumerate(raw_samples) if raw.timer_value_s is not None]
    spurious_indices = set()
    for pos in range(1, len(valid_indices) - 1):
        prev_i, curr_i, next_i = valid_indices[pos - 1], valid_indices[pos], valid_indices[pos + 1]
        if _is_spurious_timer_spike(
            raw_samples[prev_i].timer_value_s,
            raw_samples[curr_i].timer_value_s,
            raw_samples[next_i].timer_value_s,
        ):
            spurious_indices.add(curr_i)

    samples = []
    session_id = 0
    last_timer_value: float | None = None
    for i, raw in enumerate(raw_samples):
        timer_value = None if i in spurious_indices else raw.timer_value_s
        if timer_value is not None:
            if last_timer_value is not None and is_new_session(last_timer_value, timer_value):
                session_id += 1
            last_timer_value = timer_value

        samples.append(
            HudSample(
                raw.timestamp_s, session_id, timer_value, raw.combo_value,
                raw.confidence, raw.pickup_popup, raw.bonus_popup,
            )
        )

    # A tick with an unreadable combo still carries the popup flags and a
    # timer reading that popup-driven detection needs; only ticks with
    # neither are useless.
    return [
        s for s in samples
        if s.timer_value_s is not None or s.bonus_popup or s.pickup_popup
    ]
