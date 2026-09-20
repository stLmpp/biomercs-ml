# Kill Detector — Plan 1 of 3: Foundations

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the author everything needed to annotate their first ~3-minute block of gameplay: the ML dependency group, window tiling, the frame cache, the annotation file format and the interactive annotation tool.

**Architecture:** A new subpackage `src/biomercs_ml/detector/` holds pure, unit-tested logic (`windows`, `annotations`, `frame_cache`). Annotation files reuse the existing ground-truth JSON schema and `benchmark.GroundTruth`/`TruthKill` dataclasses. The OpenCV annotation UI is a thin script over the tested `AnnotationSession`. The OCR pipeline is not touched.

**Tech Stack:** Python 3.12, OpenCV, numpy, pytest; PyTorch-ROCm (Windows) via an `ml` dependency group. `uv` for everything.

**Spec:** `docs/superpowers/specs/2026-09-19-kill-detector-design.md` (read it first; this is plan 1 of 3 — plan 2 is training/evaluation, plan 3 is the human-feedback loop).

## Global Constraints

- Python 3.12 only for the ML wheels (`.python-version` is already `3.12`); ROCm wheels exist for Windows only — everything must still resolve/run without torch elsewhere.
- Window: 4s long, sampled at 8 fps = 32 frames; only the central 2s ("core") of a window counts kills; tiling every 2s puts each kill in exactly one window.
- Frames: 16:9 preserved, short side 224px, uint8 RGB.
- Count classes are {0, 1, 2, 3+}: counts are capped at 3.
- Annotation JSON has exactly the schema of `benchmarks/video4_t480-650.json` (`source_video`, `clip_start_s`, `alignment_shift_s`, `clip_duration_s`, `sampling_padding_s`, `kills[{clip_time_s, kind, count}]`), with `alignment_shift_s` = 0.
- The video4 window (`benchmarks/video4_t480-650.json`) is the held-out test set: nothing in this plan writes to it or reads it as training data.
- Every tunable constant lives in `src/biomercs_ml/config.py` (no magic numbers in modules).
- `AGENTS.md` conventions: `uv run` for everything, type-hint every signature, `@dataclass` for structured data, `pathlib.Path`, guard clauses over nesting, no what-comments/docstrings, TDD (failing test first), full suite (`uv run pytest -q`) before each commit, one commit per task, imperative commit messages.
- Commit messages end with these two trailer lines (blank line before them):
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01NxdGbdREH1AxkHXZDxsvJ2`
- Working directory is `D:\Projects\biomercs-ml`; use project-relative `tmp\...` paths, never `/tmp`.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml`, `uv.lock` | `ml` dependency group (ROCm torch, Windows only) |
| `src/biomercs_ml/config.py` | new detector/annotation constants (appended) |
| `src/biomercs_ml/detector/__init__.py` | empty package marker |
| `src/biomercs_ml/detector/windows.py` | pure: tile a video into windows; count kills per window |
| `src/biomercs_ml/detector/frame_cache.py` | decode a video once into a uint8 RGB `.npy` memmap; read windows from it |
| `src/biomercs_ml/detector/annotations.py` | teacher marks from a manifest; `AnnotationSession` edit state; annotation file path |
| `src/biomercs_ml/benchmark.py` | add `save_ground_truth` (inverse of `load_ground_truth`) |
| `src/biomercs_ml/dataset_manifest.py` | add `fetch_clips_in_range` |
| `scripts/build_frame_cache.py` | CLI: build caches for videos |
| `scripts/annotate.py` | CLI/OpenCV UI: annotate a span |
| `tests/test_ml_environment.py`, `tests/test_detector_windows.py`, `tests/test_detector_frame_cache.py`, `tests/test_detector_annotations.py` | new tests (plus additions to `tests/test_benchmark.py`, `tests/test_dataset_manifest.py`) |

---

### Task 1: ML dependency group

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock` (generated)
- Create: `tests/test_ml_environment.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `import torch` / `import torchvision` work in the project venv on Windows (`torch 2.9.1+rocm7.2.1`); `torch.cuda.is_available()` is true on the RX 9070 XT. Non-Windows machines resolve the group to nothing.

Verified beforehand: `uv lock` succeeds only when the group entries carry the `sys_platform == 'win32'` marker as well as the `[tool.uv.sources]` entries (without the marker on the group entries the lock fails resolving the non-Windows split).

- [ ] **Step 1: Write the environment test**

Create `tests/test_ml_environment.py`:

```python
import pytest

torch = pytest.importorskip("torch")


def test_torch_runs_a_conv_forward_pass_on_cpu():
    layer = torch.nn.Conv2d(3, 4, kernel_size=3)

    out = layer(torch.zeros(1, 3, 8, 8))

    assert out.shape == (1, 4, 6, 6)


def test_torch_computes_on_the_gpu_when_one_is_visible():
    if not torch.cuda.is_available():
        pytest.skip("no ROCm GPU visible on this machine")

    total = (torch.ones(2, device="cuda") * 2).sum().item()

    assert total == 4.0
```

- [ ] **Step 2: Run it to confirm it is skipped (torch not installed yet)**

Run: `uv run pytest tests/test_ml_environment.py -v`
Expected: 2 skipped ("could not import 'torch'").

- [ ] **Step 3: Add the group to `pyproject.toml`**

Replace the `[dependency-groups]` table and append the two `tool.uv` tables so the file's tail reads exactly:

```toml
[dependency-groups]
dev = [
    "pytest>=9.1.1",
]
ml = [
    "torch; sys_platform == 'win32'",
    "torchvision; sys_platform == 'win32'",
    "rocm-sdk-core; sys_platform == 'win32'",
    "rocm-sdk-devel; sys_platform == 'win32'",
    "rocm-sdk-libraries-custom; sys_platform == 'win32'",
    "rocm; sys_platform == 'win32'",
]

[tool.uv]
default-groups = ["dev", "ml"]

[tool.uv.sources]
torch = { url = "https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl", marker = "sys_platform == 'win32'" }
torchvision = { url = "https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/torchvision-0.24.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl", marker = "sys_platform == 'win32'" }
rocm-sdk-core = { url = "https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm_sdk_core-7.2.1-py3-none-win_amd64.whl", marker = "sys_platform == 'win32'" }
rocm-sdk-devel = { url = "https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl", marker = "sys_platform == 'win32'" }
rocm-sdk-libraries-custom = { url = "https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl", marker = "sys_platform == 'win32'" }
rocm = { url = "https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm-7.2.1.tar.gz", marker = "sys_platform == 'win32'" }
```

`default-groups = ["dev", "ml"]` makes plain `uv run pytest` keep torch installed (otherwise `uv run` could prune it).

- [ ] **Step 4: Lock and install**

Run: `uv lock` then `uv sync`
Expected: `uv lock` prints `Resolved N packages`; `uv sync` installs torch/torchvision/rocm packages (a few GB; ~100s if not cached). If the lock fails, STOP and report the exact error (the fallback in the spec is to keep the ML environment outside the lock with the `uv pip install` recipe in `DECISIONS.md`, "ML migration: environment spike").

- [ ] **Step 5: Run the environment test**

Run: `uv run pytest tests/test_ml_environment.py -v`
Expected: 2 passed (the GPU test passes on this machine; it would skip elsewhere).

- [ ] **Step 6: Full suite, then commit**

Run: `uv run pytest -q` — Expected: all pass (166 existing + 2).

```bash
git add pyproject.toml uv.lock tests/test_ml_environment.py
git commit -m "Add ML dependency group with Windows ROCm PyTorch wheels

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NxdGbdREH1AxkHXZDxsvJ2"
```

---

### Task 2: Window tiling and per-window kill counts

**Files:**
- Modify: `src/biomercs_ml/config.py` (append)
- Create: `src/biomercs_ml/detector/__init__.py` (empty)
- Create: `src/biomercs_ml/detector/windows.py`
- Test: `tests/test_detector_windows.py`

**Interfaces:**
- Consumes: `biomercs_ml.benchmark.TruthKill(timestamp_s: float, kind: Literal["bonus","bullet"], count: int)`.
- Produces:
  - `config.DETECTOR_WINDOW_S = 4.0`, `config.DETECTOR_CORE_S = 2.0`, `config.DETECTOR_MAX_COUNT = 3`
  - `windows.Window(start_s: float, core_start_s: float, core_end_s: float)` dataclass
  - `windows.tile_windows(duration_s: float, offset_s: float = 0.0) -> list[Window]`
  - `windows.window_counts(window: Window, kills: list[TruthKill]) -> tuple[int, int]` returning `(n_bonus, n_bullet)`, each capped at `config.DETECTOR_MAX_COUNT`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_detector_windows.py`:

```python
from biomercs_ml import config
from biomercs_ml.benchmark import TruthKill
from biomercs_ml.detector import windows
from biomercs_ml.detector.windows import Window


def test_tile_windows_puts_a_core_every_core_length_with_context_on_each_side():
    tiles = windows.tile_windows(10.0)

    assert [w.core_start_s for w in tiles] == [0.0, 2.0, 4.0, 6.0, 8.0]
    assert tiles[0].start_s == -1.0
    assert tiles[1].core_end_s == 4.0


def test_tile_windows_drops_a_trailing_partial_core():
    assert len(windows.tile_windows(9.0)) == 4


def test_tile_windows_offset_shifts_the_whole_grid():
    tiles = windows.tile_windows(10.0, offset_s=0.5)

    assert [w.core_start_s for w in tiles] == [0.5, 2.5, 4.5, 6.5]


def test_window_counts_counts_kills_by_kind_inside_the_core():
    window = Window(start_s=-1.0, core_start_s=0.0, core_end_s=2.0)
    kills = [TruthKill(0.5, "bonus", 2), TruthKill(1.5, "bullet", 1)]

    assert windows.window_counts(window, kills) == (2, 1)


def test_window_counts_ignores_kills_in_the_context_margin():
    window = Window(start_s=-1.0, core_start_s=0.0, core_end_s=2.0)

    assert windows.window_counts(window, [TruthKill(-0.5, "bonus", 1), TruthKill(2.5, "bullet", 1)]) == (0, 0)


def test_a_kill_exactly_on_the_core_boundary_belongs_to_the_next_window_only():
    first, second = windows.tile_windows(4.0)
    kills = [TruthKill(2.0, "bonus", 1)]

    assert windows.window_counts(first, kills) == (0, 0)
    assert windows.window_counts(second, kills) == (1, 0)


def test_window_counts_caps_each_kind_at_the_max_count_class():
    window = Window(start_s=-1.0, core_start_s=0.0, core_end_s=2.0)
    kills = [TruthKill(0.5, "bonus", config.DETECTOR_MAX_COUNT + 2)]

    assert windows.window_counts(window, kills) == (config.DETECTOR_MAX_COUNT, 0)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_detector_windows.py -v`
Expected: FAIL / ERROR — `ImportError: cannot import name 'windows'` (the package does not exist).

- [ ] **Step 3: Add the config constants**

Append to `src/biomercs_ml/config.py`:

```python

# --- Kill detector (trained video model) -- see
# docs/superpowers/specs/2026-09-19-kill-detector-design.md ---

# A training/inference window is DETECTOR_WINDOW_S long but only kills in
# its central DETECTOR_CORE_S count; the rest is visual context. Tiling a
# video every DETECTOR_CORE_S puts each kill in exactly one window.
DETECTOR_WINDOW_S = 4.0
DETECTOR_CORE_S = 2.0

# Count heads are classes {0, 1, 2, ..., DETECTOR_MAX_COUNT}, the last one
# meaning "this many or more".
DETECTOR_MAX_COUNT = 3
```

- [ ] **Step 4: Write the implementation**

Create empty `src/biomercs_ml/detector/__init__.py`, then `src/biomercs_ml/detector/windows.py`:

```python
from dataclasses import dataclass

from biomercs_ml import config
from biomercs_ml.benchmark import TruthKill


@dataclass
class Window:
    start_s: float
    core_start_s: float
    core_end_s: float


def tile_windows(duration_s: float, offset_s: float = 0.0) -> list[Window]:
    context_s = (config.DETECTOR_WINDOW_S - config.DETECTOR_CORE_S) / 2
    windows = []
    index = 0
    while offset_s + (index + 1) * config.DETECTOR_CORE_S <= duration_s:
        core_start_s = offset_s + index * config.DETECTOR_CORE_S
        windows.append(Window(core_start_s - context_s, core_start_s, core_start_s + config.DETECTOR_CORE_S))
        index += 1
    return windows


def window_counts(window: Window, kills: list[TruthKill]) -> tuple[int, int]:
    in_core = [k for k in kills if window.core_start_s <= k.timestamp_s < window.core_end_s]
    n_bonus = sum(k.count for k in in_core if k.kind == "bonus")
    n_bullet = sum(k.count for k in in_core if k.kind == "bullet")
    return min(n_bonus, config.DETECTOR_MAX_COUNT), min(n_bullet, config.DETECTOR_MAX_COUNT)
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/test_detector_windows.py -v`
Expected: 7 passed.

- [ ] **Step 6: Full suite, then commit**

Run: `uv run pytest -q` — Expected: all pass.

```bash
git add src/biomercs_ml/config.py src/biomercs_ml/detector tests/test_detector_windows.py
git commit -m "Add window tiling and per-window kill counts for the detector

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NxdGbdREH1AxkHXZDxsvJ2"
```

---

### Task 3: Save annotations in the ground-truth format

**Files:**
- Modify: `src/biomercs_ml/benchmark.py`
- Test: `tests/test_benchmark.py` (append)

**Interfaces:**
- Consumes: existing `benchmark.GroundTruth`, `TruthKill`, `load_ground_truth`.
- Produces: `benchmark.save_ground_truth(truth: GroundTruth, path: Path) -> None` — writes the JSON schema of `benchmarks/video4_t480-650.json` with `alignment_shift_s` = 0.0, creating parent directories.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_benchmark.py`:

```python
def test_save_ground_truth_round_trips_through_load_ground_truth(tmp_path):
    truth = GroundTruth(
        source_video="tmp/biomercs-footage/source.mp4",
        scored_start_s=100.0,
        scored_end_s=160.0,
        sampling_padding_s=0.0,
        kills=[TruthKill(101.5, "bonus", 2), TruthKill(140.25, "bullet", 1)],
    )
    path = tmp_path / "annotations" / "block.json"

    benchmark.save_ground_truth(truth, path)

    assert benchmark.load_ground_truth(path) == truth


def test_save_ground_truth_writes_the_video4_schema_with_zero_alignment_shift(tmp_path):
    truth = GroundTruth("v.mp4", 10.0, 20.0, 0.0, [TruthKill(12.0, "bullet", 1)])
    path = tmp_path / "block.json"

    benchmark.save_ground_truth(truth, path)

    data = json.loads(path.read_text())
    assert set(data) == {"source_video", "clip_start_s", "alignment_shift_s", "clip_duration_s", "sampling_padding_s", "kills"}
    assert data["alignment_shift_s"] == 0.0
    assert data["kills"] == [{"clip_time_s": 2.0, "kind": "bullet", "count": 1}]
```

Add `import json` to the top of `tests/test_benchmark.py` if it is not already imported.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_benchmark.py -k save_ground_truth -v`
Expected: FAIL — `AttributeError: module 'biomercs_ml.benchmark' has no attribute 'save_ground_truth'`.

- [ ] **Step 3: Implement**

Add to `src/biomercs_ml/benchmark.py` (after `load_ground_truth`):

```python
def save_ground_truth(truth: GroundTruth, path: Path) -> None:
    data = {
        "source_video": truth.source_video,
        "clip_start_s": truth.scored_start_s,
        "alignment_shift_s": 0.0,
        "clip_duration_s": truth.scored_end_s - truth.scored_start_s,
        "sampling_padding_s": truth.sampling_padding_s,
        "kills": [
            {"clip_time_s": round(k.timestamp_s - truth.scored_start_s, 3), "kind": k.kind, "count": k.count}
            for k in truth.kills
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_benchmark.py -v`
Expected: all pass (including the 2 new).

- [ ] **Step 5: Full suite, then commit**

Run: `uv run pytest -q` — Expected: all pass.

```bash
git add src/biomercs_ml/benchmark.py tests/test_benchmark.py
git commit -m "Add save_ground_truth as the inverse of load_ground_truth

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NxdGbdREH1AxkHXZDxsvJ2"
```

---

### Task 4: Teacher marks from a manifest

**Files:**
- Modify: `src/biomercs_ml/dataset_manifest.py`
- Modify: `tests/test_dataset_manifest.py` (append)
- Create: `src/biomercs_ml/detector/annotations.py`
- Test: `tests/test_detector_annotations.py`

**Interfaces:**
- Consumes: `models.ClipRecord`, `benchmark.TruthKill`, an existing manifest sqlite (`event_timestamp_s` is absolute video seconds).
- Produces:
  - `dataset_manifest.fetch_clips_in_range(db_path: Path, source_video: str, start_s: float, end_s: float) -> list[ClipRecord]` — inclusive range, ordered by `event_timestamp_s`, exact match on the stored `source_video` string.
  - `annotations.teacher_marks(db_path: Path, source_video: str, start_s: float, end_s: float) -> list[TruthKill]` — one `bonus` mark if `n_bonus > 0`, one `bullet` mark if `n_bullet > 0`, both at the clip's timestamp.

- [ ] **Step 1: Write the failing manifest test**

Append to `tests/test_dataset_manifest.py`:

```python
def test_fetch_clips_in_range_returns_only_that_video_and_span_in_time_order(tmp_path):
    db_path = tmp_path / "manifest.sqlite"
    dataset_manifest.create_db(db_path)

    def clip(video: str, t: float) -> ClipRecord:
        return ClipRecord(f"{video}_{t}.mp4", "bonus_kill", 1, 0, video, 0, t, 0.9)

    for record in [clip("a.mp4", 20.0), clip("a.mp4", 10.0), clip("a.mp4", 30.0), clip("b.mp4", 15.0)]:
        dataset_manifest.insert_clip(db_path, record)

    found = dataset_manifest.fetch_clips_in_range(db_path, "a.mp4", 10.0, 20.0)

    assert [r.event_timestamp_s for r in found] == [10.0, 20.0]
    assert all(r.source_video == "a.mp4" for r in found)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_dataset_manifest.py -k in_range -v`
Expected: FAIL — `AttributeError: ... has no attribute 'fetch_clips_in_range'`.

- [ ] **Step 3: Implement `fetch_clips_in_range`**

Add to `src/biomercs_ml/dataset_manifest.py` (next to the other `fetch_*` functions):

```python
def fetch_clips_in_range(db_path: Path, source_video: str, start_s: float, end_s: float) -> list[ClipRecord]:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            """SELECT clip_path, label_kind, n_bonus, n_bullet, source_video,
                      session_id, event_timestamp_s, confidence
               FROM clips
               WHERE source_video = ? AND event_timestamp_s BETWEEN ? AND ?
               ORDER BY event_timestamp_s""",
            (source_video, start_s, end_s),
        )
        return [ClipRecord(*row) for row in cursor.fetchall()]
    finally:
        conn.close()
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_dataset_manifest.py -v` — Expected: all pass.

- [ ] **Step 5: Write the failing `teacher_marks` tests**

Create `tests/test_detector_annotations.py`:

```python
from biomercs_ml import dataset_manifest
from biomercs_ml.benchmark import TruthKill
from biomercs_ml.detector import annotations
from biomercs_ml.models import ClipRecord


def _insert(db_path, t: float, n_bonus: int, n_bullet: int, video: str = "v.mp4") -> None:
    kind = "mixed" if n_bonus and n_bullet else ("bonus_kill" if n_bonus else "bullet_kill")
    dataset_manifest.insert_clip(db_path, ClipRecord(f"c{t}.mp4", kind, n_bonus, n_bullet, video, 0, t, 0.9))


def test_teacher_marks_turns_a_mixed_clip_into_one_bonus_and_one_bullet_mark(tmp_path):
    db_path = tmp_path / "manifest.sqlite"
    dataset_manifest.create_db(db_path)
    _insert(db_path, 10.0, n_bonus=2, n_bullet=1)

    marks = annotations.teacher_marks(db_path, "v.mp4", 0.0, 60.0)

    assert marks == [TruthKill(10.0, "bonus", 2), TruthKill(10.0, "bullet", 1)]


def test_teacher_marks_skips_kinds_with_a_zero_count_and_clips_out_of_range(tmp_path):
    db_path = tmp_path / "manifest.sqlite"
    dataset_manifest.create_db(db_path)
    _insert(db_path, 10.0, n_bonus=1, n_bullet=0)
    _insert(db_path, 90.0, n_bonus=1, n_bullet=0)

    marks = annotations.teacher_marks(db_path, "v.mp4", 0.0, 60.0)

    assert marks == [TruthKill(10.0, "bonus", 1)]
```

- [ ] **Step 6: Run to verify they fail**

Run: `uv run pytest tests/test_detector_annotations.py -v`
Expected: FAIL — `ImportError: cannot import name 'annotations'`.

- [ ] **Step 7: Implement `teacher_marks`**

Create `src/biomercs_ml/detector/annotations.py`:

```python
from pathlib import Path

from biomercs_ml import dataset_manifest
from biomercs_ml.benchmark import TruthKill


def teacher_marks(db_path: Path, source_video: str, start_s: float, end_s: float) -> list[TruthKill]:
    marks = []
    for clip in dataset_manifest.fetch_clips_in_range(db_path, source_video, start_s, end_s):
        if clip.n_bonus > 0:
            marks.append(TruthKill(clip.event_timestamp_s, "bonus", clip.n_bonus))
        if clip.n_bullet > 0:
            marks.append(TruthKill(clip.event_timestamp_s, "bullet", clip.n_bullet))
    return marks
```

- [ ] **Step 8: Run to verify they pass**

Run: `uv run pytest tests/test_detector_annotations.py -v` — Expected: 2 passed.

- [ ] **Step 9: Full suite, then commit**

Run: `uv run pytest -q` — Expected: all pass.

```bash
git add src/biomercs_ml/dataset_manifest.py src/biomercs_ml/detector/annotations.py tests/test_dataset_manifest.py tests/test_detector_annotations.py
git commit -m "Add teacher marks: read OCR-pipeline detections as annotation seeds

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NxdGbdREH1AxkHXZDxsvJ2"
```

---

### Task 5: Frame cache

**Files:**
- Modify: `src/biomercs_ml/config.py` (append)
- Create: `src/biomercs_ml/detector/frame_cache.py`
- Test: `tests/test_detector_frame_cache.py`

**Interfaces:**
- Consumes: OpenCV, numpy, `config.DETECTOR_WINDOW_S`.
- Produces:
  - `config.DETECTOR_FPS = 8`, `config.DETECTOR_SHORT_SIDE_PX = 224`, `config.DETECTOR_FRAME_CACHE_DIR = "tmp/frames"`
  - `frame_cache.FrameCache(frames: np.ndarray, fps: float)` dataclass; `frames` is `(N, H, W, 3)` uint8 RGB (memmap). Method `read_window(start_s: float, n_frames: int) -> np.ndarray` returns `(n_frames, H, W, 3)`; indices outside `[0, N-1]` are clamped to the nearest edge frame; first index is `round(start_s * fps)`.
  - `frame_cache.cache_path(video_path: Path, cache_dir: Path) -> Path` = `cache_dir / f"{video_path.parent.name}_{video_path.stem}.npy"`
  - `frame_cache.build_cache(video_path: Path, cache_dir: Path, fps: int = config.DETECTOR_FPS, short_side_px: int = config.DETECTOR_SHORT_SIDE_PX) -> Path` — frame `k` is the source frame at index `round(k / fps * source_fps)`; also writes a `.json` sidecar `{"fps": fps}` next to the `.npy`.
  - `frame_cache.load_cache(video_path: Path, cache_dir: Path) -> FrameCache`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_detector_frame_cache.py`:

```python
from pathlib import Path

import cv2
import numpy as np

from biomercs_ml.detector import frame_cache

SOURCE_FPS = 30
SIZE = (64, 48)  # width, height


def _write_video(path: Path, gray_of_frame=lambda i: 2 * i, n_frames: int = 90, bgr=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), SOURCE_FPS, SIZE)
    for i in range(n_frames):
        frame = np.full((SIZE[1], SIZE[0], 3), gray_of_frame(i), dtype=np.uint8)
        if bgr is not None:
            frame[:, :] = bgr
        writer.write(frame)
    writer.release()


def _build(tmp_path, **video_kwargs):
    video = tmp_path / "footage" / "source.avi"
    _write_video(video, **video_kwargs)
    cache_dir = tmp_path / "cache"
    frame_cache.build_cache(video, cache_dir, fps=8, short_side_px=24)
    return video, cache_dir


def test_cache_path_names_the_file_after_the_parent_folder_and_stem(tmp_path):
    path = frame_cache.cache_path(Path("tmp/biomercs-footage4/source.mp4"), tmp_path)

    assert path == tmp_path / "biomercs-footage4_source.npy"


def test_build_cache_samples_frames_at_the_target_rate_and_keeps_the_aspect_ratio(tmp_path):
    video, cache_dir = _build(tmp_path)

    cache = frame_cache.load_cache(video, cache_dir)

    assert cache.fps == 8
    assert cache.frames.shape == (24, 24, 32, 3)  # 3s * 8fps, short side 24 of a 4:3 source
    for k in (0, 1, 2, 10, 23):
        expected_gray = 2 * round(k * SOURCE_FPS / 8)
        assert abs(int(cache.frames[k, 0, 0, 0]) - expected_gray) <= 6


def test_build_cache_stores_frames_as_rgb(tmp_path):
    video, cache_dir = _build(tmp_path, bgr=(255, 0, 0))  # pure blue in OpenCV's BGR

    pixel = frame_cache.load_cache(video, cache_dir).frames[0, 0, 0]

    assert pixel[2] > 200 and pixel[0] < 50


def test_read_window_returns_the_requested_slice(tmp_path):
    video, cache_dir = _build(tmp_path)
    cache = frame_cache.load_cache(video, cache_dir)

    window = cache.read_window(2.0, 4)

    assert window.shape == (4, 24, 32, 3)
    assert np.array_equal(window, cache.frames[16:20])


def test_read_window_repeats_the_edge_frame_outside_the_video(tmp_path):
    video, cache_dir = _build(tmp_path)
    cache = frame_cache.load_cache(video, cache_dir)

    before = cache.read_window(-1.0, 4)
    after = cache.read_window(2.9, 4)

    assert all(np.array_equal(frame, cache.frames[0]) for frame in before)
    assert np.array_equal(after[-1], cache.frames[-1])
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_detector_frame_cache.py -v`
Expected: FAIL — `ImportError: cannot import name 'frame_cache'`.

- [ ] **Step 3: Add the config constants**

Append to `src/biomercs_ml/config.py`:

```python

# Frames are cached once per video at this rate/size (16:9 kept, short
# side DETECTOR_SHORT_SIDE_PX); the model trains on the cache, never the
# video. A window is DETECTOR_WINDOW_S * DETECTOR_FPS = 32 frames.
DETECTOR_FPS = 8
DETECTOR_SHORT_SIDE_PX = 224
DETECTOR_FRAME_CACHE_DIR = "tmp/frames"
```

- [ ] **Step 4: Implement**

Create `src/biomercs_ml/detector/frame_cache.py`:

```python
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from biomercs_ml import config


@dataclass
class FrameCache:
    frames: np.ndarray
    fps: float

    def read_window(self, start_s: float, n_frames: int) -> np.ndarray:
        first = round(start_s * self.fps)
        indices = np.clip(np.arange(first, first + n_frames), 0, len(self.frames) - 1)
        return self.frames[indices]


def cache_path(video_path: Path, cache_dir: Path) -> Path:
    return cache_dir / f"{video_path.parent.name}_{video_path.stem}.npy"


def build_cache(
    video_path: Path,
    cache_dir: Path,
    fps: int = config.DETECTOR_FPS,
    short_side_px: int = config.DETECTOR_SHORT_SIDE_PX,
) -> Path:
    cap = cv2.VideoCapture(str(video_path))
    source_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    scale = short_side_px / min(width, height)
    out_size = (round(width * scale), round(height * scale))
    n_out = int(total_frames / source_fps * fps)

    def source_index(k: int) -> int:
        return round(k / fps * source_fps)

    path = cache_path(video_path, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = np.lib.format.open_memmap(path, mode="w+", dtype=np.uint8, shape=(n_out, out_size[1], out_size[0], 3))

    next_k = 0
    for source_idx in range(total_frames):
        if not cap.grab():
            break
        if next_k >= n_out or source_index(next_k) > source_idx:
            continue
        ok, frame = cap.retrieve()
        if not ok:
            continue
        resized = cv2.resize(frame, out_size, interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        while next_k < n_out and source_index(next_k) <= source_idx:
            frames[next_k] = rgb
            next_k += 1

    cap.release()
    frames.flush()
    del frames  # unmap now: an open memmap blocks deleting the file on Windows
    path.with_suffix(".json").write_text(json.dumps({"fps": fps}))
    return path


def load_cache(video_path: Path, cache_dir: Path) -> FrameCache:
    path = cache_path(video_path, cache_dir)
    fps = json.loads(path.with_suffix(".json").read_text())["fps"]
    return FrameCache(frames=np.load(path, mmap_mode="r"), fps=fps)
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/test_detector_frame_cache.py -v`
Expected: 5 passed. If `test_build_cache_samples_frames...` fails on shape, print `cv2.VideoCapture(...).get(cv2.CAP_PROP_FRAME_COUNT)` for the generated `.avi` first — the assumption is 90 frames; do not loosen the assertion, fix the fixture instead.

- [ ] **Step 6: Full suite, then commit**

Run: `uv run pytest -q` — Expected: all pass.

```bash
git add src/biomercs_ml/config.py src/biomercs_ml/detector/frame_cache.py tests/test_detector_frame_cache.py
git commit -m "Add frame cache: decode a video once into a uint8 RGB memmap

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NxdGbdREH1AxkHXZDxsvJ2"
```

---

### Task 6: Annotation session (edit state)

**Files:**
- Modify: `src/biomercs_ml/config.py` (append)
- Modify: `src/biomercs_ml/detector/annotations.py`
- Test: `tests/test_detector_annotations.py` (append)

**Interfaces:**
- Consumes: `benchmark.GroundTruth`, `benchmark.TruthKill`.
- Produces:
  - `config.ANNOTATIONS_DIR = "annotations"`, `config.ANNOTATION_MERGE_TOLERANCE_S = 0.5`, `config.ANNOTATION_PICK_TOLERANCE_S = 1.0`
  - `annotations.annotation_path(video_path: Path, start_s: float, end_s: float) -> Path` = `Path(config.ANNOTATIONS_DIR) / f"{video_path.parent.name}_t{int(start_s)}-{int(end_s)}.json"`
  - `annotations.AnnotationSession(source_video: str, start_s: float, end_s: float, kills: list[TruthKill])` with:
    - `kills` attribute: `list[TruthKill]`, kept sorted by `timestamp_s`
    - `add(timestamp_s: float, kind: Literal["bonus","bullet"]) -> None`: if a mark of the same kind lies within `ANNOTATION_MERGE_TOLERANCE_S`, its `count` += 1 (simultaneous kills), else a new mark with `count` 1 at `round(timestamp_s, 3)`
    - `remove_nearest(timestamp_s: float) -> bool`: decrements the count of the nearest mark (any kind) within `ANNOTATION_PICK_TOLERANCE_S`, deleting it at 0; `False` if none is near
    - `undo() -> bool`: restores the state before the last `add`/`remove_nearest`; `False` if nothing to undo
    - `to_ground_truth() -> GroundTruth` (`sampling_padding_s` 0.0, kills sorted)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_detector_annotations.py`:

```python
from pathlib import Path

from biomercs_ml import config
from biomercs_ml.detector.annotations import AnnotationSession


def _session(*kills: TruthKill) -> AnnotationSession:
    return AnnotationSession("v.mp4", 100.0, 160.0, list(kills))


def test_annotation_path_is_named_after_the_video_folder_and_span():
    path = annotations.annotation_path(Path("tmp/biomercs-footage2/source.mp4"), 300.0, 480.0)

    assert path == Path(config.ANNOTATIONS_DIR) / "biomercs-footage2_t300-480.json"


def test_add_creates_a_single_count_mark():
    session = _session()

    session.add(110.0, "bonus")

    assert session.kills == [TruthKill(110.0, "bonus", 1)]


def test_add_of_the_same_kind_within_the_merge_tolerance_raises_the_count():
    session = _session(TruthKill(110.0, "bonus", 1))

    session.add(110.0 + config.ANNOTATION_MERGE_TOLERANCE_S, "bonus")

    assert session.kills == [TruthKill(110.0, "bonus", 2)]


def test_add_of_a_different_kind_at_the_same_time_is_a_separate_mark():
    session = _session(TruthKill(110.0, "bonus", 1))

    session.add(110.0, "bullet")

    assert sorted(session.kills, key=lambda k: k.kind) == [TruthKill(110.0, "bonus", 1), TruthKill(110.0, "bullet", 1)]


def test_add_beyond_the_merge_tolerance_is_a_new_mark_and_marks_stay_sorted():
    session = _session(TruthKill(120.0, "bonus", 1))

    session.add(110.0, "bonus")

    assert [k.timestamp_s for k in session.kills] == [110.0, 120.0]


def test_remove_nearest_decrements_then_deletes_at_zero():
    session = _session(TruthKill(110.0, "bonus", 2))

    assert session.remove_nearest(110.2) is True
    assert session.kills == [TruthKill(110.0, "bonus", 1)]
    assert session.remove_nearest(110.0) is True
    assert session.kills == []


def test_remove_nearest_returns_false_when_no_mark_is_within_the_pick_tolerance():
    session = _session(TruthKill(110.0, "bonus", 1))

    assert session.remove_nearest(110.0 + config.ANNOTATION_PICK_TOLERANCE_S + 0.1) is False
    assert session.kills == [TruthKill(110.0, "bonus", 1)]


def test_undo_restores_the_state_before_the_last_edit():
    session = _session(TruthKill(110.0, "bonus", 1))
    session.add(110.0, "bonus")
    session.remove_nearest(110.0)

    assert session.undo() is True
    assert session.kills == [TruthKill(110.0, "bonus", 2)]
    assert session.undo() is True
    assert session.kills == [TruthKill(110.0, "bonus", 1)]


def test_undo_with_no_history_returns_false():
    assert _session().undo() is False


def test_to_ground_truth_carries_the_span_and_sorted_kills():
    session = _session(TruthKill(130.0, "bullet", 1), TruthKill(105.0, "bonus", 1))

    truth = session.to_ground_truth()

    assert (truth.source_video, truth.scored_start_s, truth.scored_end_s) == ("v.mp4", 100.0, 160.0)
    assert [k.timestamp_s for k in truth.kills] == [105.0, 130.0]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_detector_annotations.py -v`
Expected: FAIL — `ImportError: cannot import name 'AnnotationSession'`.

- [ ] **Step 3: Add the config constants**

Append to `src/biomercs_ml/config.py`:

```python

# Gold annotations (the author's fully-annotated blocks) live here and are
# committed; the held-out test block stays in benchmarks/.
ANNOTATIONS_DIR = "annotations"

# Annotation tool: pressing "add" again for the same kind within this long
# of an existing mark means simultaneous kills (count + 1), not a new
# event. Removing/picking looks for the nearest mark within the pick
# tolerance.
ANNOTATION_MERGE_TOLERANCE_S = 0.5
ANNOTATION_PICK_TOLERANCE_S = 1.0
```

- [ ] **Step 4: Implement**

In `src/biomercs_ml/detector/annotations.py`, replace the imports and append the new code so the file reads:

```python
from copy import deepcopy
from pathlib import Path
from typing import Literal

from biomercs_ml import config, dataset_manifest
from biomercs_ml.benchmark import GroundTruth, TruthKill


def annotation_path(video_path: Path, start_s: float, end_s: float) -> Path:
    return Path(config.ANNOTATIONS_DIR) / f"{video_path.parent.name}_t{int(start_s)}-{int(end_s)}.json"


def teacher_marks(db_path: Path, source_video: str, start_s: float, end_s: float) -> list[TruthKill]:
    marks = []
    for clip in dataset_manifest.fetch_clips_in_range(db_path, source_video, start_s, end_s):
        if clip.n_bonus > 0:
            marks.append(TruthKill(clip.event_timestamp_s, "bonus", clip.n_bonus))
        if clip.n_bullet > 0:
            marks.append(TruthKill(clip.event_timestamp_s, "bullet", clip.n_bullet))
    return marks


class AnnotationSession:
    def __init__(self, source_video: str, start_s: float, end_s: float, kills: list[TruthKill]) -> None:
        self.source_video = source_video
        self.start_s = start_s
        self.end_s = end_s
        self.kills = sorted(kills, key=lambda k: k.timestamp_s)
        self._history: list[list[TruthKill]] = []

    def add(self, timestamp_s: float, kind: Literal["bonus", "bullet"]) -> None:
        self._history.append(deepcopy(self.kills))
        for kill in self.kills:
            if kill.kind == kind and abs(kill.timestamp_s - timestamp_s) <= config.ANNOTATION_MERGE_TOLERANCE_S:
                kill.count += 1
                return
        self.kills.append(TruthKill(round(timestamp_s, 3), kind, 1))
        self.kills.sort(key=lambda k: k.timestamp_s)

    def remove_nearest(self, timestamp_s: float) -> bool:
        near = [k for k in self.kills if abs(k.timestamp_s - timestamp_s) <= config.ANNOTATION_PICK_TOLERANCE_S]
        if not near:
            return False
        self._history.append(deepcopy(self.kills))
        nearest = min(near, key=lambda k: abs(k.timestamp_s - timestamp_s))
        nearest.count -= 1
        if nearest.count == 0:
            self.kills.remove(nearest)
        return True

    def undo(self) -> bool:
        if not self._history:
            return False
        self.kills = self._history.pop()
        return True

    def to_ground_truth(self) -> GroundTruth:
        return GroundTruth(
            source_video=self.source_video,
            scored_start_s=self.start_s,
            scored_end_s=self.end_s,
            sampling_padding_s=0.0,
            kills=sorted(self.kills, key=lambda k: k.timestamp_s),
        )
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/test_detector_annotations.py -v` — Expected: all pass (2 from Task 4 + 10 new).

- [ ] **Step 6: Full suite, then commit**

Run: `uv run pytest -q` — Expected: all pass.

```bash
git add src/biomercs_ml/config.py src/biomercs_ml/detector/annotations.py tests/test_detector_annotations.py
git commit -m "Add AnnotationSession: add/remove/undo kill marks with merge tolerance

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NxdGbdREH1AxkHXZDxsvJ2"
```

---

### Task 7: The two scripts (frame cache CLI + annotation UI)

**Files:**
- Create: `scripts/build_frame_cache.py`
- Create: `scripts/annotate.py`

**Interfaces:**
- Consumes: `frame_cache.build_cache/load_cache/cache_path`, `annotations.AnnotationSession/annotation_path/teacher_marks`, `benchmark.load_ground_truth/save_ground_truth`.
- Produces: two CLIs. No new library code. The OpenCV window cannot be unit-tested; verification is a compile check plus a manual run (Steps 4-5).

- [ ] **Step 1: Write `scripts/build_frame_cache.py`**

```python
"""Decode run videos once into the uint8 frame cache the detector trains on.

Usage: uv run python scripts/build_frame_cache.py <video> [<video> ...]
"""
import sys
from pathlib import Path

from biomercs_ml import config
from biomercs_ml.detector import frame_cache


def main() -> None:
    cache_dir = Path(config.DETECTOR_FRAME_CACHE_DIR)
    for arg in sys.argv[1:]:
        video = Path(arg)
        frame_cache.build_cache(video, cache_dir)
        frames = frame_cache.load_cache(video, cache_dir).frames
        print(f"{frame_cache.cache_path(video, cache_dir)}  shape={frames.shape}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write `scripts/annotate.py`**

```python
"""Annotate every kill in a span of a run video.

Usage: uv run python scripts/annotate.py <video> <start_s> <end_s> [teacher_manifest.sqlite]

Resumes from annotations/<...>.json if it exists; otherwise starts from the
teacher pipeline's detections in <teacher_manifest> (if given) so you only
correct them.

Keys: space play/pause | a back 1 frame | d forward 1 frame | j/l back/forward 1s
      1/2/3 speed 0.25x/0.5x/1x | b add bonus kill | g add bullet kill
      x remove one kill at the cursor | u undo | s save | q save and quit
"""
import sys
from pathlib import Path

import cv2
import numpy as np

from biomercs_ml import benchmark, config
from biomercs_ml.detector import annotations
from biomercs_ml.detector.annotations import AnnotationSession

WINDOW_NAME = "annotate"
SPEEDS = {"1": 0.25, "2": 0.5, "3": 1.0}
BONUS_COLOR = (0, 200, 0)
BULLET_COLOR = (0, 0, 255)
TIMELINE_HEIGHT = 24


def load_session(video: Path, start_s: float, end_s: float, teacher_db: Path | None) -> AnnotationSession:
    path = annotations.annotation_path(video, start_s, end_s)
    if path.exists():
        return AnnotationSession(str(video), start_s, end_s, benchmark.load_ground_truth(path).kills)
    marks = annotations.teacher_marks(teacher_db, str(video), start_s, end_s) if teacher_db else []
    return AnnotationSession(str(video), start_s, end_s, marks)


def draw_overlay(frame: np.ndarray, session: AnnotationSession, t: float, speed: float, playing: bool) -> np.ndarray:
    image = frame.copy()
    height, width = image.shape[:2]
    span = session.end_s - session.start_s

    def x_of(time_s: float) -> int:
        return int((time_s - session.start_s) / span * (width - 1))

    bar_top = height - TIMELINE_HEIGHT
    cv2.rectangle(image, (0, bar_top), (width, height), (40, 40, 40), -1)
    for kill in session.kills:
        color = BONUS_COLOR if kill.kind == "bonus" else BULLET_COLOR
        cv2.line(image, (x_of(kill.timestamp_s), bar_top), (x_of(kill.timestamp_s), height), color, 3)
    cv2.line(image, (x_of(t), bar_top), (x_of(t), height), (255, 255, 255), 1)

    near = [k for k in session.kills if abs(k.timestamp_s - t) <= config.ANNOTATION_PICK_TOLERANCE_S]
    near_text = "  ".join(f"{k.kind} x{k.count} @{k.timestamp_s:.2f}" for k in near)
    total_bonus = sum(k.count for k in session.kills if k.kind == "bonus")
    total_bullet = sum(k.count for k in session.kills if k.kind == "bullet")
    lines = [
        f"t={t:.2f}s (+{t - session.start_s:.2f})  {speed}x  {'PLAY' if playing else 'PAUSE'}",
        f"total bonus={total_bonus} bullet={total_bullet}",
        near_text,
    ]
    for row, text in enumerate(lines):
        cv2.putText(image, text, (10, 28 + 26 * row), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    return image


def save(session: AnnotationSession, video: Path) -> None:
    path = annotations.annotation_path(video, session.start_s, session.end_s)
    benchmark.save_ground_truth(session.to_ground_truth(), path)
    print(f"saved {path}  ({len(session.kills)} marks)")


def main() -> None:
    video = Path(sys.argv[1])
    start_s, end_s = float(sys.argv[2]), float(sys.argv[3])
    teacher_db = Path(sys.argv[4]) if len(sys.argv) > 4 else None
    session = load_session(video, start_s, end_s, teacher_db)

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS)
    start_idx, end_idx = round(start_s * fps), round(end_s * fps)
    frame_idx = start_idx
    speed, playing = 1.0, False

    def seek(idx: int) -> np.ndarray | None:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, image = cap.read()
        return image if ok else None

    frame = seek(frame_idx)
    if frame is None:
        sys.exit(f"cannot read {video} at {start_s}s")

    while True:
        t = frame_idx / fps
        cv2.imshow(WINDOW_NAME, draw_overlay(frame, session, t, speed, playing))
        key = cv2.waitKey(max(1, int(1000 / fps / speed)) if playing else 0) & 0xFF
        char = chr(key) if key != 255 else ""

        if playing and not char:
            ok, image = cap.read()
            if ok and frame_idx < end_idx:
                frame, frame_idx = image, frame_idx + 1
            else:
                playing = False
            continue

        if char == " ":
            playing = not playing
        elif char in SPEEDS:
            speed = SPEEDS[char]
        elif char == "d" and frame_idx < end_idx:
            ok, image = cap.read()
            if ok:
                frame, frame_idx = image, frame_idx + 1
        elif char in ("a", "j", "l"):
            step = {"a": -1, "j": -round(fps), "l": round(fps)}[char]
            target = min(max(frame_idx + step, start_idx), end_idx)
            image = seek(target)
            if image is not None:
                frame, frame_idx = image, target
        elif char == "b":
            session.add(t, "bonus")
        elif char == "g":
            session.add(t, "bullet")
        elif char == "x":
            session.remove_nearest(t)
        elif char == "u":
            session.undo()
        elif char == "s":
            save(session, video)
        elif char == "q":
            save(session, video)
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Compile-check both scripts**

Run: `uv run python -m py_compile scripts/build_frame_cache.py scripts/annotate.py`
Expected: no output (success).

- [ ] **Step 4: Manually verify the frame cache CLI**

Run: `uv run python scripts/build_frame_cache.py tmp\biomercs-footage4\source.mp4`
Expected: prints `tmp\frames\biomercs-footage4_source.npy  shape=(5368, 224, 398, 3)` (671s x 8fps ≈ 5368 frames; exact N may differ by 1-2). The file is ~1.4 GB. Note the wall-clock time it took (decoding 60fps 720p; expected a minute or two) — report it.

- [ ] **Step 5: Manually verify the annotation tool**

Run (annotates the first 30s of video 1, seeded by the teacher's manifest):
`uv run python scripts/annotate.py tmp\biomercs-footage\source.mp4 0 30 tmp\biomercs-popup-run\manifest.sqlite`

Check, and report what you saw:
1. A window opens showing the video paused at t=0 with the text overlay and a timeline bar at the bottom, teacher marks drawn as green (bonus) / red (bullet) ticks.
2. `space` plays; `space` pauses; `d`/`a` step one frame; `l`/`j` jump one second.
3. `b` at some time adds a green tick and raises "total bonus"; pressing `b` again within 0.5s raises that mark's count instead of adding a new one (overlay shows `bonus x2`); `x` lowers it; `u` undoes.
4. `q` saves and prints `saved annotations\biomercs-footage_t0-30.json (N marks)`; re-running the same command resumes from that file (marks reappear even without the manifest argument).
5. `annotations\biomercs-footage_t0-30.json` has the `benchmarks/video4_t480-650.json` schema with `alignment_shift_s: 0.0`.

Then delete the test file: `Remove-Item annotations\biomercs-footage_t0-30.json` (this was only a smoke test, not a real annotation block).

- [ ] **Step 6: Full suite, then commit**

Run: `uv run pytest -q` — Expected: all pass.

```bash
git add scripts/build_frame_cache.py scripts/annotate.py
git commit -m "Add frame-cache CLI and the OpenCV annotation tool

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NxdGbdREH1AxkHXZDxsvJ2"
```

---

### Task 8: Docs and handoff

**Files:**
- Modify: `docs/superpowers/HANDOFF.md`

**Interfaces:**
- Consumes/Produces: documentation only.

- [ ] **Step 1: Add the ML-phase section at the top of the HANDOFF status**

Insert immediately above the line `## Current status (as of 2026-09-19, an eighth session) — READ THIS FIRST` in `docs/superpowers/HANDOFF.md`:

```markdown
## ML PHASE (ninth session, current) — the OCR pipeline is archived

The HUD/OCR pipeline is frozen at git tag `ocr-pipeline-final` (recall 75.5%,
exact-count 54% on the video4 benchmark; bullet kills undetected). The project
is migrating to a trained video model with a human-feedback loop:

- Design: `docs/superpowers/specs/2026-09-19-kill-detector-design.md`
- Plan 1 (foundations: ML deps, windows, frame cache, annotation tool):
  `docs/superpowers/plans/2026-09-19-kill-detector-1-foundations.md`
- Plan 2 (training + evaluation) and plan 3 (feedback loop) are written after
  plan 1 lands.
- Environment: native Windows PyTorch-ROCm (`uv sync` installs the `ml` group);
  spike results and install recipe in DECISIONS.md, "ML migration: environment spike".

**Your next manual step (author):** annotate the first ~3-minute block:
`uv run python scripts/annotate.py tmp\biomercs-footage\source.mp4 <start> <end> tmp\biomercs-popup-run\manifest.sqlite`
(pick a busy span; `annotations\` is committed). The video4 window
`benchmarks/video4_t480-650.json` is the held-out test — never annotate or
train on it.

```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/HANDOFF.md
git commit -m "Point HANDOFF at the ML phase, spec and plan 1

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NxdGbdREH1AxkHXZDxsvJ2"
```

---

## Definition of done for Plan 1

- `uv run pytest -q` passes; torch imports and the GPU test passes on this machine.
- The author can run `scripts/annotate.py` on a span of any of the five videos, correct the teacher's marks, save, and resume.
- `scripts/build_frame_cache.py` builds a cache for a full video; `read_window` returns 32-frame windows.
- Nothing in the OCR modules changed; `benchmarks/video4_t480-650.json` is untouched.

## Next plans

- **Plan 2 — Training and evaluation:** build the training set (gold windows + weighted teacher bonuses, unknown excluded), `dataset`, `model` (r2plus1d_18 + two count heads), `train` (two-phase, fp16), `evaluate_detector.py` scoring the held-out block with `score_detections`.
- **Plan 3 — Feedback loop:** `predict` (tile a video → `DetectedClip`s + uncertainty), `active_learning` (uncertain + random windows), `review_windows.py`, retrain rounds.
