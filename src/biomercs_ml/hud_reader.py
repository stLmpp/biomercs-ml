from pathlib import Path

import cv2
import numpy as np

from biomercs_ml import config


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
) -> tuple[int | None, float]:
    digits = []
    confidences = []
    for x, y, w, h in slots:
        crop = frame[y : y + h, x : x + w]
        digit, score = match_digit(crop, templates)
        digits.append(digit)
        confidences.append(score)
    min_confidence = min(confidences)
    if min_confidence < config.DIGIT_MATCH_MIN_CONFIDENCE:
        return None, min_confidence
    return int("".join(digits)), min_confidence
