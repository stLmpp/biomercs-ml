# Kill-Labeling Data Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn raw Resident Evil 5/6 "The Mercenaries" gameplay video into a
SQLite-backed dataset of short, labeled clips (`bullet_kill` / `bonus_kill`
/ `mixed`), using the game's own HUD (run timer + combo counter) as
ground truth — no manual clip-by-clip labeling required for this target.

**Architecture:** Six independent, single-responsibility Python modules
form a pipeline: `downloader` (YouTube → local file) → `hud_reader`
(video → per-frame timer/combo readings) → `event_detector` (readings →
grouped kill events) → `auto_labeler` (events → labels) →
`clip_extractor` (labels → clip files) → `dataset_manifest` (clips →
SQLite rows). `pipeline.py` wires them together for one video end to end.

**Tech Stack:** Python 3.12+, managed with `uv`; OpenCV (`opencv-python`)
for template matching and frame decoding; `ffmpeg` (system binary, called
via `subprocess`) for clip cutting; `yt-dlp` for YouTube downloads;
`sqlite3` (stdlib) for the manifest; `pytest` for tests.

**Spec:** [docs/superpowers/specs/2026-09-16-kill-labeling-pipeline-design.md](../specs/2026-09-16-kill-labeling-pipeline-design.md)

## Global Constraints

- Language is Python for the entire pipeline (spec: "Language and environment").
- No per-enemy attribution inside `mixed` groups — group-level label only (spec: "Label taxonomy").
- Model training is out of scope for this plan (spec: "Goal of this sub-project").
- Sampling interval starts at 0.2s; clip window is 2s before to 2s after the event timestamp (spec: stages 1 and 4).
- All ROI pixel coordinates in this plan are calibrated against `tests/fixtures/frames/sample_frame_01.png` (1280x720) and **must be recalibrated** (same process as Task 2) if source footage has a different resolution or HUD layout.

---

## Prerequisites (one-time machine setup, not a task)

Run these on the MacBook before Task 1:

```bash
brew install uv ffmpeg
```

Verify: `uv --version` and `ffmpeg -version` both print a version.

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `biomercs_ml/__init__.py`
- Create: `biomercs_ml/config.py`
- Create: `biomercs_ml/models.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `biomercs_ml.config` module with all tunable constants used by every later task. `biomercs_ml.models` module with `HudSample`, `KillGroup`, `LabelKind`, `KillLabel`, `ClipRecord` dataclasses used by every later task.

- [ ] **Step 1: Create the project and add dependencies**

```bash
cd /Users/stlmpp/projects/biomercs-app/biomercs-ml
uv init --name biomercs-ml --python 3.12 --no-readme
uv add opencv-python numpy yt-dlp
uv add --dev pytest
```

- [ ] **Step 2: Write `biomercs_ml/config.py`**

```python
"""Tunable constants for the HUD-reading pipeline.

All pixel coordinates below were calibrated against
tests/fixtures/frames/sample_frame_01.png at 1280x720 resolution, using
the crop recipe documented in Task 2 of
docs/superpowers/plans/2026-09-16-kill-labeling-pipeline.md. Recalibrate
every ROI/slot value here if source footage has a different resolution
or HUD layout.
"""

REFERENCE_RESOLUTION = (1280, 720)  # (width, height)

# Each slot/ROI below is (x, y, width, height) in pixels.
TIMER_MINUTES_SLOTS = [(525, 93, 40, 76), (555, 93, 40, 76)]
TIMER_SECONDS_SLOTS = [(605, 93, 40, 76), (635, 93, 40, 76)]
COMBO_DIGIT_SLOTS = [(916, 113, 34, 46), (948, 113, 34, 46), (980, 113, 34, 46)]
COMBO_LABEL_ROI = (1015, 113, 110, 46)

TIMER_DIGITS_DIR = "templates/digits_timer"
COMBO_DIGITS_DIR = "templates/digits_combo"
COMBO_LABEL_TEMPLATE_PATH = "templates/combo_label.png"

DIGIT_MATCH_MIN_CONFIDENCE = 0.6
COMBO_LABEL_MIN_CONFIDENCE = 0.6

SAMPLE_INTERVAL_S = 0.2
SESSION_RESET_DROP_S = 1.0
SESSION_RESET_JUMP_S = 25.0
LABEL_TOLERANCE_S = 1.0

CLIP_BEFORE_S = 2.0
CLIP_AFTER_S = 2.0
```

- [ ] **Step 3: Write `biomercs_ml/models.py`**

```python
from dataclasses import dataclass
from typing import Literal

LabelKind = Literal["bullet_kill", "bonus_kill", "mixed"]


@dataclass
class HudSample:
    timestamp_s: float
    session_id: int
    timer_value_s: float | None
    combo_value: int | None
    confidence: float


@dataclass
class KillGroup:
    session_id: int
    timestamp_s: float
    group_size: int
    timer_before_s: float
    timer_after_s: float
    elapsed_s: float
    confidence: float


@dataclass
class KillLabel:
    kind: LabelKind
    n_bonus: int
    n_bullet: int


@dataclass
class ClipRecord:
    clip_path: str
    label_kind: LabelKind
    n_bonus: int
    n_bullet: int
    source_video: str
    session_id: int
    event_timestamp_s: float
    confidence: float
```

- [ ] **Step 4: Write a sanity test and run it**

```python
# tests/test_config.py
from biomercs_ml import config


def test_slot_counts_match_expected_digit_counts():
    assert len(config.TIMER_MINUTES_SLOTS) == 2
    assert len(config.TIMER_SECONDS_SLOTS) == 2
    assert len(config.COMBO_DIGIT_SLOTS) == 3


def test_all_slots_are_same_size_within_their_field():
    timer_slots = config.TIMER_MINUTES_SLOTS + config.TIMER_SECONDS_SLOTS
    timer_sizes = {(w, h) for _, _, w, h in timer_slots}
    assert timer_sizes == {(40, 76)}

    combo_sizes = {(w, h) for _, _, w, h in config.COMBO_DIGIT_SLOTS}
    assert combo_sizes == {(34, 46)}
```

Run: `uv run pytest tests/test_config.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock biomercs_ml tests
git commit -m "Scaffold biomercs-ml project with config and models"
```

---

### Task 2: Finish the digit template set

**Context:** Task 1's calibration already produced real, working
templates for most digits, sourced from three real frames
(`tests/fixtures/frames/sample_frame_01.png`, `sample_frame_02.png`,
`sample_frame_03.png`): timer digits `0, 1, 2, 3, 5, 8` in
`templates/digits_timer/`, and combo digits `0, 3, 5, 7` in
`templates/digits_combo/`. The remaining digits need to come from other
real frames in your own footage — this task can't be completed without
you supplying at least one frame per missing digit.

**Files:**
- Modify: `templates/digits_timer/` (add `4.png, 6.png, 7.png, 9.png`)
- Modify: `templates/digits_combo/` (add `1.png, 2.png, 4.png, 6.png, 8.png, 9.png`)
- Create: `tests/test_templates_complete.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_templates_complete.py
from pathlib import Path

from biomercs_ml import config

ALL_DIGITS = {str(d) for d in range(10)}


def test_timer_digit_templates_complete():
    present = {p.stem for p in Path(config.TIMER_DIGITS_DIR).glob("*.png")}
    missing = ALL_DIGITS - present
    assert not missing, f"missing timer digit templates: {sorted(missing)}"


def test_combo_digit_templates_complete():
    present = {p.stem for p in Path(config.COMBO_DIGITS_DIR).glob("*.png")}
    missing = ALL_DIGITS - present
    assert not missing, f"missing combo digit templates: {sorted(missing)}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_templates_complete.py -v`
Expected: FAIL — both tests report missing digits (timer missing `4,6,7,9`; combo missing `1,2,4,6,8,9`).

- [ ] **Step 3: Capture the missing digits from your own footage**

For each missing digit, find a frame in your own recordings where it
appears in the relevant field (timer minutes/seconds, or combo count),
extract that frame, and crop it using the same slots as Task 1's
calibration. Reusable recipe (replace `INPUT.mp4` and `TIMESTAMP`):

```bash
# 1. Extract a still frame at a timestamp where the digit you need is visible
ffmpeg -y -ss TIMESTAMP -i INPUT.mp4 -frames:v 1 /tmp/frame.png

# 2. If the frame's resolution isn't 1280x720, scale it to match first —
#    otherwise the slot coordinates below won't line up:
ffmpeg -y -i /tmp/frame.png -vf "scale=1280:720" /tmp/frame_scaled.png

# 3. Crop the specific digit slot you need. Example: timer minutes,
#    first digit (x=525, y=93, w=40, h=76):
ffmpeg -y -i /tmp/frame_scaled.png -vf "crop=40:76:525:93" /tmp/digit.png

# 4. Look at /tmp/digit.png, confirm which digit it shows, then save it
#    under the correct name, e.g.:
cp /tmp/digit.png templates/digits_timer/4.png
```

Slot coordinates to use for step 3, per field (from `biomercs_ml/config.py`):
- Timer minutes: `(525,93,40,76)` or `(555,93,40,76)`
- Timer seconds: `(605,93,40,76)` or `(635,93,40,76)`
- Combo digits: `(916,113,34,46)`, `(948,113,34,46)`, or `(980,113,34,46)`

Repeat until every digit 0-9 has a template in both
`templates/digits_timer/` and `templates/digits_combo/`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_templates_complete.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add templates tests/test_templates_complete.py
git commit -m "Complete digit template sets for timer and combo fields"
```

---

### Task 3: `hud_reader` — digit matching

**Files:**
- Create: `biomercs_ml/hud_reader.py`
- Test: `tests/test_hud_reader_digits.py`

**Interfaces:**
- Consumes: `biomercs_ml.config` (slot/path constants), `biomercs_ml.models` (none directly yet).
- Produces: `load_image(path: str) -> np.ndarray`, `load_digit_templates(dir_path: str) -> dict[str, np.ndarray]`, `match_digit(crop: np.ndarray, templates: dict[str, np.ndarray]) -> tuple[str, float]`, `read_digit_slots(frame: np.ndarray, slots: list[tuple[int,int,int,int]], templates: dict[str, np.ndarray]) -> tuple[int | None, float]` — all used by Task 4.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hud_reader_digits.py
import cv2

from biomercs_ml import config, hud_reader

FRAME_PATH = "tests/fixtures/frames/sample_frame_01.png"


def _load_frame():
    return hud_reader.load_image(FRAME_PATH)


def test_load_digit_templates_loads_available_timer_digits():
    templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    for digit in "0123456789":
        assert digit in templates


def test_match_digit_identifies_correct_digit():
    templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    frame = _load_frame()
    x, y, w, h = config.TIMER_MINUTES_SLOTS[0]  # known to show "0"
    crop = frame[y : y + h, x : x + w]
    digit, score = hud_reader.match_digit(crop, templates)
    assert digit == "0"
    assert score > config.DIGIT_MATCH_MIN_CONFIDENCE


def test_read_digit_slots_reads_timer_minutes_as_02():
    templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    frame = _load_frame()
    value, confidence = hud_reader.read_digit_slots(
        frame, config.TIMER_MINUTES_SLOTS, templates
    )
    assert value == 2
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE


def test_read_digit_slots_reads_timer_seconds_as_28():
    templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    frame = _load_frame()
    value, confidence = hud_reader.read_digit_slots(
        frame, config.TIMER_SECONDS_SLOTS, templates
    )
    assert value == 28
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE


def test_read_digit_slots_reads_combo_as_003():
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    frame = _load_frame()
    value, confidence = hud_reader.read_digit_slots(
        frame, config.COMBO_DIGIT_SLOTS, templates
    )
    assert value == 3
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hud_reader_digits.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError` — `biomercs_ml/hud_reader.py` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```python
# biomercs_ml/hud_reader.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hud_reader_digits.py -v`
Expected: 5 passed (requires Task 2 complete — all 10 digits present in both template dirs).

- [ ] **Step 5: Commit**

```bash
git add biomercs_ml/hud_reader.py tests/test_hud_reader_digits.py
git commit -m "Add digit template matching to hud_reader"
```

---

### Task 4: `hud_reader` — field readers, validity check, video sampling

**Files:**
- Modify: `biomercs_ml/hud_reader.py`
- Test: `tests/test_hud_reader_fields.py`
- Test: `tests/test_hud_reader_video.py`

**Interfaces:**
- Consumes: `load_image`, `load_digit_templates`, `read_digit_slots` (Task 3); `biomercs_ml.models.HudSample`.
- Produces: `read_timer(frame, templates) -> tuple[float | None, float]`, `read_combo(frame, templates) -> tuple[int | None, float]`, `is_valid_hud_frame(frame, combo_label_template) -> tuple[bool, float]`, `is_new_session(prev_timer_s: float, curr_timer_s: float) -> bool`, `sample_video(video_path, timer_templates, combo_templates, combo_label_template, interval_s=config.SAMPLE_INTERVAL_S) -> list[HudSample]` (each returned `HudSample` already carries its `session_id`) — used by Task 5 and `pipeline.py` (Task 10).

- [ ] **Step 1: Write the failing tests for field readers and validity check**

```python
# tests/test_hud_reader_fields.py
from biomercs_ml import config, hud_reader

FRAME_PATH = "tests/fixtures/frames/sample_frame_01.png"


def test_read_timer_returns_148_seconds():
    frame = hud_reader.load_image(FRAME_PATH)
    templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    value, confidence = hud_reader.read_timer(frame, templates)
    assert value == 2 * 60 + 28
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE


def test_read_combo_returns_3():
    frame = hud_reader.load_image(FRAME_PATH)
    templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    value, confidence = hud_reader.read_combo(frame, templates)
    assert value == 3
    assert confidence > config.DIGIT_MATCH_MIN_CONFIDENCE


def test_is_valid_hud_frame_true_on_gameplay_frame():
    frame = hud_reader.load_image(FRAME_PATH)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
    is_valid, score = hud_reader.is_valid_hud_frame(frame, combo_label_template)
    assert is_valid is True
    assert score > config.COMBO_LABEL_MIN_CONFIDENCE


def test_is_valid_hud_frame_false_on_blank_frame():
    import numpy as np

    blank = np.zeros((720, 1280, 3), dtype=np.uint8)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
    is_valid, _ = hud_reader.is_valid_hud_frame(blank, combo_label_template)
    assert is_valid is False


def test_is_new_session_false_for_normal_countdown():
    assert hud_reader.is_new_session(prev_timer_s=100.0, curr_timer_s=99.8) is False


def test_is_new_session_false_for_plausible_bonus_jump():
    # 3 simultaneous bonus kills (+15s) minus 0.2s decay
    assert hud_reader.is_new_session(prev_timer_s=100.0, curr_timer_s=114.8) is False


def test_is_new_session_true_for_backward_jump():
    assert hud_reader.is_new_session(prev_timer_s=100.0, curr_timer_s=30.0) is True


def test_is_new_session_true_for_implausibly_large_jump():
    assert hud_reader.is_new_session(prev_timer_s=10.0, curr_timer_s=300.0) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hud_reader_fields.py -v`
Expected: FAIL with `AttributeError: module 'biomercs_ml.hud_reader' has no attribute 'read_timer'`.

- [ ] **Step 3: Add field readers and validity check to `biomercs_ml/hud_reader.py`**

```python
def read_timer(
    frame: np.ndarray, templates: dict[str, np.ndarray]
) -> tuple[float | None, float]:
    minutes, minutes_conf = read_digit_slots(frame, config.TIMER_MINUTES_SLOTS, templates)
    seconds, seconds_conf = read_digit_slots(frame, config.TIMER_SECONDS_SLOTS, templates)
    confidence = min(minutes_conf, seconds_conf)
    if minutes is None or seconds is None:
        return None, confidence
    return float(minutes * 60 + seconds), confidence


def read_combo(
    frame: np.ndarray, templates: dict[str, np.ndarray]
) -> tuple[int | None, float]:
    return read_digit_slots(frame, config.COMBO_DIGIT_SLOTS, templates)


def is_valid_hud_frame(
    frame: np.ndarray, combo_label_template: np.ndarray
) -> tuple[bool, float]:
    x, y, w, h = config.COMBO_LABEL_ROI
    crop = frame[y : y + h, x : x + w]
    resized_template = cv2.resize(combo_label_template, (w, h))
    result = cv2.matchTemplate(crop, resized_template, cv2.TM_CCOEFF_NORMED)
    score = float(result[0, 0])
    return score >= config.COMBO_LABEL_MIN_CONFIDENCE, score


def is_new_session(prev_timer_s: float, curr_timer_s: float) -> bool:
    # The timer only ever drifts down by ~one sampling interval per step,
    # or jumps up by a bonus (at most a handful of simultaneous +5s
    # kills). Anything outside that plausible range means a new
    # stage/round started partway through the recording.
    delta = curr_timer_s - prev_timer_s
    return delta < -config.SESSION_RESET_DROP_S or delta > config.SESSION_RESET_JUMP_S
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hud_reader_fields.py -v`
Expected: 8 passed.

- [ ] **Step 5: Write the failing test for `sample_video`**

```python
# tests/test_hud_reader_video.py
from pathlib import Path

from biomercs_ml import config, hud_reader

VIDEO_PATH = "tests/fixtures/synthetic_static.mp4"


def test_sample_video_reads_consistent_samples_from_static_video():
    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)

    samples = hud_reader.sample_video(
        Path(VIDEO_PATH), timer_templates, combo_templates, combo_label_template
    )

    # 1s video sampled every 0.2s -> ~5 samples; the frame never changes,
    # so every sample should read the same known values and stay in one
    # session (no timer discontinuity to split on).
    assert 4 <= len(samples) <= 6
    for sample in samples:
        assert sample.timer_value_s == 148.0
        assert sample.combo_value == 3
        assert sample.session_id == 0
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_hud_reader_video.py -v`
Expected: FAIL with `AttributeError: module 'biomercs_ml.hud_reader' has no attribute 'sample_video'`.

- [ ] **Step 7: Add `sample_video` to `biomercs_ml/hud_reader.py`**

```python
from pathlib import Path

from biomercs_ml.models import HudSample


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

    samples = []
    session_id = 0
    last_timer_value: float | None = None
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            timestamp_s = frame_idx / fps
            is_valid, hud_conf = is_valid_hud_frame(frame, combo_label_template)
            if is_valid:
                timer_value, timer_conf = read_timer(frame, timer_templates)
                combo_value, combo_conf = read_combo(frame, combo_templates)
                confidence = min(hud_conf, timer_conf, combo_conf)
                if timer_value is not None and last_timer_value is not None:
                    if is_new_session(last_timer_value, timer_value):
                        session_id += 1
                if timer_value is not None:
                    last_timer_value = timer_value
                samples.append(
                    HudSample(timestamp_s, session_id, timer_value, combo_value, confidence)
                )
        frame_idx += 1
    cap.release()

    return [s for s in samples if s.timer_value_s is not None and s.combo_value is not None]
```

Add the import (`from biomercs_ml.models import HudSample`) near the top of the file with the other imports, rather than inline — the inline placement above is only to show where it's first needed.

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_hud_reader_video.py tests/test_hud_reader_fields.py tests/test_hud_reader_digits.py -v`
Expected: all passed.

- [ ] **Step 9: Commit**

```bash
git add biomercs_ml/hud_reader.py tests/test_hud_reader_fields.py tests/test_hud_reader_video.py
git commit -m "Add HUD field readers, validity check, and video sampling"
```

---

### Task 5: `event_detector`

**Files:**
- Create: `biomercs_ml/event_detector.py`
- Test: `tests/test_event_detector.py`

**Interfaces:**
- Consumes: `biomercs_ml.models.HudSample` (already tagged with `session_id` by `hud_reader.sample_video`, Task 4).
- Produces: `detect_kill_groups(session_samples: list[HudSample], session_id: int) -> list[KillGroup]` — used by `pipeline.py` (Task 10). Session boundaries are `hud_reader`'s responsibility (Task 4's `is_new_session`/`sample_video`), not this module's — this function assumes it's only ever given samples that already belong to one session.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_event_detector.py
from biomercs_ml import event_detector
from biomercs_ml.models import HudSample


def _sample(t, timer, combo, session_id=0, conf=0.9):
    return HudSample(
        timestamp_s=t, session_id=session_id, timer_value_s=timer, combo_value=combo, confidence=conf
    )


def test_detect_kill_groups_finds_single_kill():
    session = [_sample(0.0, 100.0, 5), _sample(0.2, 99.8, 5), _sample(0.4, 104.6, 6)]
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert len(groups) == 1
    group = groups[0]
    assert group.session_id == 0
    assert group.group_size == 1
    assert group.timer_before_s == 99.8
    assert group.timer_after_s == 104.6
    assert group.elapsed_s == 0.2


def test_detect_kill_groups_ignores_combo_reset():
    session = [_sample(0.0, 100.0, 12), _sample(0.2, 99.8, 0)]  # combo dropped, not a kill
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert groups == []


def test_detect_kill_groups_finds_simultaneous_triple_kill():
    session = [_sample(0.0, 100.0, 5), _sample(0.2, 114.8, 8)]  # +3 combo, +15s bonus
    groups = event_detector.detect_kill_groups(session, session_id=0)
    assert len(groups) == 1
    assert groups[0].group_size == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_event_detector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'biomercs_ml.event_detector'`.

- [ ] **Step 3: Write the implementation**

```python
# biomercs_ml/event_detector.py
from biomercs_ml.models import HudSample, KillGroup


def detect_kill_groups(session_samples: list[HudSample], session_id: int) -> list[KillGroup]:
    groups = []
    for prev, curr in zip(session_samples, session_samples[1:]):
        group_size = curr.combo_value - prev.combo_value
        if group_size > 0:
            groups.append(
                KillGroup(
                    session_id=session_id,
                    timestamp_s=curr.timestamp_s,
                    group_size=group_size,
                    timer_before_s=prev.timer_value_s,
                    timer_after_s=curr.timer_value_s,
                    elapsed_s=curr.timestamp_s - prev.timestamp_s,
                    confidence=min(prev.confidence, curr.confidence),
                )
            )
    return groups
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_event_detector.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add biomercs_ml/event_detector.py tests/test_event_detector.py
git commit -m "Add event_detector: kill-group detection from combo increases"
```

---

### Task 6: `auto_labeler`

**Files:**
- Create: `biomercs_ml/auto_labeler.py`
- Test: `tests/test_auto_labeler.py`

**Interfaces:**
- Consumes: `biomercs_ml.models.KillGroup`, `biomercs_ml.config.LABEL_TOLERANCE_S`.
- Produces: `label_kill_group(group: KillGroup, tolerance_s: float = config.LABEL_TOLERANCE_S) -> KillLabel | None` — used by `pipeline.py` (Task 10). Returns `None` when the group's timer delta doesn't cleanly fit any bonus/bullet composition within tolerance (spec: "auto_labeler", ambiguous case handling).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_auto_labeler.py
from biomercs_ml import auto_labeler
from biomercs_ml.models import KillGroup


def _group(group_size, timer_before, timer_after, elapsed_s=0.2):
    return KillGroup(
        session_id=0,
        timestamp_s=elapsed_s,
        group_size=group_size,
        timer_before_s=timer_before,
        timer_after_s=timer_after,
        elapsed_s=elapsed_s,
        confidence=0.9,
    )


def test_labels_single_bullet_kill():
    # delta = -0.2 (just normal decay, no bonus) -> bonus_seconds = 0
    group = _group(group_size=1, timer_before=100.0, timer_after=99.8)
    label = auto_labeler.label_kill_group(group)
    assert label.kind == "bullet_kill"
    assert label.n_bonus == 0
    assert label.n_bullet == 1


def test_labels_single_bonus_kill():
    # delta = +4.8 (=5 - 0.2 decay) -> bonus_seconds = 5.0
    group = _group(group_size=1, timer_before=100.0, timer_after=104.8)
    label = auto_labeler.label_kill_group(group)
    assert label.kind == "bonus_kill"
    assert label.n_bonus == 1
    assert label.n_bullet == 0


def test_labels_simultaneous_triple_bonus_kill():
    # delta = +14.8 (=15 - 0.2 decay) -> bonus_seconds = 15.0 -> 3 bonus
    group = _group(group_size=3, timer_before=100.0, timer_after=114.8)
    label = auto_labeler.label_kill_group(group)
    assert label.kind == "bonus_kill"
    assert label.n_bonus == 3
    assert label.n_bullet == 0


def test_labels_mixed_group():
    # delta = +9.8 (=10 - 0.2 decay) -> bonus_seconds = 10.0 -> 2 bonus, 1 bullet, of 3
    group = _group(group_size=3, timer_before=100.0, timer_after=109.8)
    label = auto_labeler.label_kill_group(group)
    assert label.kind == "mixed"
    assert label.n_bonus == 2
    assert label.n_bullet == 1


def test_returns_none_when_delta_does_not_fit_any_composition():
    # delta doesn't land near any multiple of 5 within tolerance
    group = _group(group_size=1, timer_before=100.0, timer_after=102.5)
    label = auto_labeler.label_kill_group(group)
    assert label is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_auto_labeler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'biomercs_ml.auto_labeler'`.

- [ ] **Step 3: Write the implementation**

```python
# biomercs_ml/auto_labeler.py
from biomercs_ml import config
from biomercs_ml.models import KillGroup, KillLabel


def label_kill_group(
    group: KillGroup, tolerance_s: float = config.LABEL_TOLERANCE_S
) -> KillLabel | None:
    raw_delta = group.timer_after_s - group.timer_before_s
    # The timer counts down ~1s per elapsed second even with no kill, so
    # cancel that decay out before checking for clean multiples of 5.
    bonus_seconds = raw_delta + group.elapsed_s

    n_bonus = round(bonus_seconds / 5.0)
    n_bonus = max(0, min(n_bonus, group.group_size))
    residual = abs(bonus_seconds - 5.0 * n_bonus)
    if residual > tolerance_s:
        return None

    n_bullet = group.group_size - n_bonus
    if n_bonus == group.group_size:
        kind = "bonus_kill"
    elif n_bonus == 0:
        kind = "bullet_kill"
    else:
        kind = "mixed"
    return KillLabel(kind=kind, n_bonus=n_bonus, n_bullet=n_bullet)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_auto_labeler.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add biomercs_ml/auto_labeler.py tests/test_auto_labeler.py
git commit -m "Add auto_labeler: bullet/bonus/mixed classification from timer delta"
```

---

### Task 7: `dataset_manifest`

**Files:**
- Create: `biomercs_ml/dataset_manifest.py`
- Test: `tests/test_dataset_manifest.py`

**Interfaces:**
- Consumes: `biomercs_ml.models.ClipRecord`.
- Produces: `create_db(db_path: Path) -> None`, `insert_clip(db_path: Path, record: ClipRecord) -> int`, `fetch_random_sample(db_path: Path, n: int) -> list[tuple]` — `insert_clip`/`create_db` used by `pipeline.py` (Task 10); `fetch_random_sample` used by the review helper (Task 11).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dataset_manifest.py
from pathlib import Path

from biomercs_ml import dataset_manifest
from biomercs_ml.models import ClipRecord


def _record(clip_path="clip1.mp4"):
    return ClipRecord(
        clip_path=clip_path,
        label_kind="bonus_kill",
        n_bonus=1,
        n_bullet=0,
        source_video="video1.mp4",
        session_id=0,
        event_timestamp_s=12.4,
        confidence=0.95,
    )


def test_create_db_then_insert_and_read_back(tmp_path):
    db_path = tmp_path / "manifest.sqlite"
    dataset_manifest.create_db(db_path)

    row_id = dataset_manifest.insert_clip(db_path, _record())
    assert row_id == 1

    rows = dataset_manifest.fetch_random_sample(db_path, n=10)
    assert len(rows) == 1
    assert rows[0][1] == "clip1.mp4"  # clip_path column


def test_fetch_random_sample_respects_limit(tmp_path):
    db_path = tmp_path / "manifest.sqlite"
    dataset_manifest.create_db(db_path)
    for i in range(5):
        dataset_manifest.insert_clip(db_path, _record(clip_path=f"clip{i}.mp4"))

    rows = dataset_manifest.fetch_random_sample(db_path, n=3)
    assert len(rows) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_dataset_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'biomercs_ml.dataset_manifest'`.

- [ ] **Step 3: Write the implementation**

```python
# biomercs_ml/dataset_manifest.py
import sqlite3
from pathlib import Path

from biomercs_ml.models import ClipRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_path TEXT NOT NULL,
    label_kind TEXT NOT NULL,
    n_bonus INTEGER NOT NULL,
    n_bullet INTEGER NOT NULL,
    source_video TEXT NOT NULL,
    session_id INTEGER NOT NULL,
    event_timestamp_s REAL NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def create_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def insert_clip(db_path: Path, record: ClipRecord) -> int:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO clips
               (clip_path, label_kind, n_bonus, n_bullet, source_video,
                session_id, event_timestamp_s, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.clip_path,
                record.label_kind,
                record.n_bonus,
                record.n_bullet,
                record.source_video,
                record.session_id,
                record.event_timestamp_s,
                record.confidence,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def fetch_random_sample(db_path: Path, n: int) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("SELECT * FROM clips ORDER BY RANDOM() LIMIT ?", (n,))
        return cursor.fetchall()
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_dataset_manifest.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add biomercs_ml/dataset_manifest.py tests/test_dataset_manifest.py
git commit -m "Add dataset_manifest: SQLite storage for labeled clips"
```

---

### Task 8: `clip_extractor`

**Files:**
- Create: `biomercs_ml/clip_extractor.py`
- Test: `tests/test_clip_extractor.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (only `biomercs_ml.config` for default window sizes).
- Produces: `extract_clip(video_path: Path, timestamp_s: float, output_path: Path, before_s: float = config.CLIP_BEFORE_S, after_s: float = config.CLIP_AFTER_S) -> Path` — used by `pipeline.py` (Task 10).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_clip_extractor.py
from pathlib import Path

from biomercs_ml import clip_extractor

VIDEO_PATH = Path("tests/fixtures/synthetic_static.mp4")


def test_extract_clip_creates_a_playable_file(tmp_path):
    output_path = tmp_path / "clip.mp4"
    result = clip_extractor.extract_clip(
        VIDEO_PATH, timestamp_s=0.5, output_path=output_path, before_s=0.2, after_s=0.2
    )
    assert result == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_extract_clip_clamps_start_to_zero_near_beginning(tmp_path):
    output_path = tmp_path / "clip_start.mp4"
    # timestamp - before_s would be negative; must not error, must clamp to 0
    result = clip_extractor.extract_clip(
        VIDEO_PATH, timestamp_s=0.1, output_path=output_path, before_s=2.0, after_s=0.2
    )
    assert result.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_clip_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'biomercs_ml.clip_extractor'`.

- [ ] **Step 3: Write the implementation**

```python
# biomercs_ml/clip_extractor.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_clip_extractor.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add biomercs_ml/clip_extractor.py tests/test_clip_extractor.py
git commit -m "Add clip_extractor: ffmpeg-based clip cutting"
```

---

### Task 9: `downloader`

**Files:**
- Create: `biomercs_ml/downloader.py`
- Test: `tests/test_downloader.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `download(url: str, output_dir: Path) -> Path` — used by `pipeline.py` (Task 10).

**Note:** This task's test does not hit the network (no real YouTube
call) — it verifies `download` builds correct `yt-dlp` options and
derives the right output path, by faking `yt_dlp.YoutubeDL`. An actual
download only happens when `pipeline.py` is run against a real URL
later (Task 11), which is a manual/human step, not something to
automate in a test.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_downloader.py
from pathlib import Path
from unittest.mock import MagicMock, patch

from biomercs_ml import downloader


@patch("biomercs_ml.downloader.yt_dlp.YoutubeDL")
def test_download_requests_best_quality_and_mp4_output(mock_ydl_class, tmp_path):
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = {"id": "abc123"}
    mock_ydl.prepare_filename.return_value = str(tmp_path / "abc123.mp4")
    mock_ydl_class.return_value = mock_ydl

    result = downloader.download("https://youtube.com/watch?v=abc123", tmp_path)

    called_opts = mock_ydl_class.call_args[0][0]
    assert called_opts["format"] == "bestvideo+bestaudio/best"
    assert called_opts["merge_output_format"] == "mp4"
    assert result == (tmp_path / "abc123.mp4")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_downloader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'biomercs_ml.downloader'`.

- [ ] **Step 3: Write the implementation**

```python
# biomercs_ml/downloader.py
from pathlib import Path

import yt_dlp


def download(url: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return Path(filename).with_suffix(".mp4")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_downloader.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add biomercs_ml/downloader.py tests/test_downloader.py
git commit -m "Add downloader: yt-dlp wrapper for YouTube sources"
```

---

### Task 10: `pipeline` — end-to-end orchestration

**Files:**
- Create: `biomercs_ml/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 3-9 (`hud_reader`, `event_detector`, `auto_labeler`, `clip_extractor`, `dataset_manifest`, `downloader`) plus `biomercs_ml.models.ClipRecord`.
- Produces: `resolve_video(source: str, download_dir: Path) -> Path`, `run(video_source: str, output_dir: Path, db_path: Path) -> None` — this is the entry point Task 11's manual run uses.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
from pathlib import Path

from biomercs_ml import dataset_manifest, pipeline

VIDEO_PATH = "tests/fixtures/synthetic_static.mp4"


def test_resolve_video_passes_through_local_paths(tmp_path):
    result = pipeline.resolve_video(VIDEO_PATH, tmp_path)
    assert result == Path(VIDEO_PATH)


def test_run_on_static_video_produces_no_clips(tmp_path):
    # The synthetic static video never changes combo, so no kill groups
    # exist and the manifest should end up empty — this still proves the
    # whole pipeline runs end to end without erroring.
    db_path = tmp_path / "manifest.sqlite"
    pipeline.run(VIDEO_PATH, output_dir=tmp_path, db_path=db_path)

    rows = dataset_manifest.fetch_random_sample(db_path, n=10)
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'biomercs_ml.pipeline'`.

- [ ] **Step 3: Write the implementation**

```python
# biomercs_ml/pipeline.py
from pathlib import Path

from biomercs_ml import auto_labeler, clip_extractor, config, dataset_manifest, downloader, event_detector, hud_reader
from biomercs_ml.models import ClipRecord


def resolve_video(source: str, download_dir: Path) -> Path:
    if source.startswith("http://") or source.startswith("https://"):
        return downloader.download(source, download_dir)
    return Path(source)


def run(video_source: str, output_dir: Path, db_path: Path) -> None:
    video_path = resolve_video(video_source, output_dir / "downloads")

    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)

    samples = hud_reader.sample_video(video_path, timer_templates, combo_templates, combo_label_template)

    sessions: dict[int, list] = {}
    for sample in samples:
        sessions.setdefault(sample.session_id, []).append(sample)

    dataset_manifest.create_db(db_path)
    clips_dir = output_dir / "clips"

    for session_id, session_samples in sessions.items():
        groups = event_detector.detect_kill_groups(session_samples, session_id)
        for group in groups:
            label = auto_labeler.label_kill_group(group)
            if label is None:
                continue

            clip_path = clips_dir / f"{video_path.stem}_{session_id}_{group.timestamp_s:.1f}.mp4"
            clip_extractor.extract_clip(video_path, group.timestamp_s, clip_path)

            record = ClipRecord(
                clip_path=str(clip_path),
                label_kind=label.kind,
                n_bonus=label.n_bonus,
                n_bullet=label.n_bullet,
                source_video=str(video_path),
                session_id=session_id,
                event_timestamp_s=group.timestamp_s,
                confidence=group.confidence,
            )
            dataset_manifest.insert_clip(db_path, record)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests across every task pass.

- [ ] **Step 6: Commit**

```bash
git add biomercs_ml/pipeline.py tests/test_pipeline.py
git commit -m "Add pipeline: end-to-end orchestration of all stages"
```

---

### Task 11: Manual validation run and review helper

**Context:** This is the spec's validation step ("pull a random sample
of ~100-200 labeled groups and manually verify each against the source
video"). It requires your own real footage and your own eyes — it can't
be automated, but the helper script below makes the review fast.

**Files:**
- Create: `scripts/review_sample.py`
- Test: none (this task's deliverable is a manual review outcome, not code correctness)

- [ ] **Step 1: Write the review helper script**

```python
# scripts/review_sample.py
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
```

- [ ] **Step 2: Run the pipeline against one of your own real videos**

```bash
uv run python -c "
from pathlib import Path
from biomercs_ml import pipeline
pipeline.run('/path/to/your/real/video.mp4', Path('run_output'), Path('run_output/manifest.sqlite'))
"
```

- [ ] **Step 3: Review a sample and record the observed accuracy**

```bash
uv run python scripts/review_sample.py run_output/manifest.sqlite 100
```

For each clip, confirm by eye whether `label_kind` matches what actually
happened. Count agreements vs. disagreements. Per the spec, the target
bar is >98% agreement before trusting this pipeline to generate training
data at scale. If the observed rate falls short, the sample itself is
the debugging set — trace disagreements back to the likely cause (a
confidence threshold too loose in `config.py`, a missed session
boundary, an incomplete digit template) and adjust before re-running.

- [ ] **Step 4: Commit**

```bash
git add scripts/review_sample.py
git commit -m "Add manual review helper script for validating auto-labeled clips"
```
