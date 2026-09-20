# Kill Detector (trained video model) — Design

**Date:** 2026-09-19
**Status:** Approved for planning

## Context

The HUD template-matching pipeline (frozen at git tag `ocr-pipeline-final`,
commit `9e4257c`) reads the run timer, combo counter and "+05 sec." popup to
find and label kills. After nine sessions it plateaued:

- Benchmark (video4 t=480-650s, 49 hand-counted kills): recall 75.5%,
  clip precision 100%, exact-count accuracy 54%.
- Author review of 20 clips: 14 correct. Errors are bonus undercounts on
  simultaneous multi-kills.
- **Bullet kills are essentially undetected** (~1 clip per video although ~27%
  of real kills are bullets): they have no popup, and the combo HUD is hidden
  ~56% of the time.
- The author's bar is >= 140 of ~150 kills per run (~93% recall).

The author decided the OCR route is exhausted and asked to migrate to a real
trained model with human feedback ("reinforcement" here means a
learn-from-corrections loop, not classical RL — there is no agent acting in
the game). The distinction the model must learn — `bonus_kill` (melee/dash
finisher, +5s) vs `bullet_kill` (gunfire) — is an **action-recognition**
problem visible in the scene; the HUD is only an indirect proxy for it.

## Goals

1. Detect every kill in a run video and label it `bonus`/`bullet` with a
   count, at >= 93% kill recall and materially better exact-count accuracy
   than the OCR baseline.
2. A human-in-the-loop cycle where the model proposes, the author corrects
   the windows it is least sure about, and the model retrains — each cycle
   cutting manual labeling effort.
3. Reuse, not rewrite: the OCR pipeline becomes the "teacher" for weak
   labels; the benchmark and review tooling carry over.

## Non-goals

- Dense per-kill timing (a temporal-localization model). Windows only.
- Per-enemy attribution inside a mixed kill group.
- Run-vs-WR comparison, LLM narration, coaching (see
  `docs/knowledge_base/project-ideas.md`).
- Classical RL algorithms (policy gradient, reward shaping).
- Generalizing beyond the five existing videos for now.
- Touching or refactoring the existing OCR modules.

## Decisions taken in brainstorming

| Fork | Choice | Why |
|---|---|---|
| Model output | Kill detector over the video (not a clip re-classifier, not a HUD-only CNN) | Only this attacks recall and bullets, the actual blockers |
| Model family | Full video model, end-to-end fine-tuning (`r2plus1d_18`, Kinetics-400 pretrained) | Learns motion + appearance; chosen by the author over frozen-feature + temporal head. Risk accepted: cost per experiment and overfitting on little data — mitigated below |
| Formulation | Window classification (A), not dense localization | Fits noisy teacher timings and the existing 4s-clip review UX |
| Labels | Dense-annotated ~3-minute blocks in several videos, teacher weak labels for bonuses, human window corrections | Teacher has ~0 bullet recall, so "no detection" cannot mean "no kill" |
| Environment | Native Windows, PyTorch-ROCm 7.2.1, Python 3.12, RX 9070 XT | Verified by spike (see below) |
| Repo | Same repo, subpackage; OCR archived by tag | Teacher, benchmark and manifests are the shared data contract |

## Environment (verified by spike, 2026-09-19)

RX 9070 XT (gfx1201, 15.9 GiB), Ryzen 7 9700X, 31 GB RAM. `torch
2.9.1+rocm7.2.1` from AMD's repo wheels (cp312, win_amd64, not on PyPI):
`cuda.is_available()` true; 15.6 TFLOPS fp32 / 127.8 TFLOPS fp16 matmul; a
small 224px CNN trains at ~840 img/s fp32, ~1820 img/s fp16 autocast, ~112
img/s on CPU. Only the discrete GPU is visible to torch. Windows ROCm supports
PyTorch only (no TensorFlow/JAX/ONNX-ROCm/vLLM). Full recipe and the fp16
warmup pitfall: `DECISIONS.md`, "ML migration: environment spike".

## Data

### Gold annotations (`annotations/`)

The author fully annotates ~3-minute blocks — every kill, with kind and
count, including bullets and "nothing happened here" — in videos 1, 2, 3 and
5, one block at a time (start with a single block so the pipeline runs end to
end). Same JSON schema as `benchmarks/video4_t480-650.json` (`clip_time_s`,
`kind`, `count`), so `benchmark.load_ground_truth` and `score_detections` work
unchanged. Because timestamps come from the annotation tool's own frame
position, `alignment_shift_s` is 0 (the -3s player-lag offset of the video4
file does not apply).

**Annotation tool** (`scripts/annotate.py`): an OpenCV window plays the
chosen span with the teacher's detections pre-marked. Keys add a kill at the
current time (kind + count), delete or edit a teacher mark, and step
frame-by-frame or slow. Correcting a pre-filled timeline is faster than
listing kills from scratch.

### Held-out test

The video4 window (`benchmarks/`, 49 kills) is **never** used to train or to
select hyperparameters. As more blocks are annotated, the test block rotates
across blocks so one 49-kill window does not decide everything (a single
window is noisy, roughly +-10 recall points).

### Teacher weak labels

`tmp\biomercs-popup-run*/manifest.sqlite` (`event_timestamp_s`, `n_bonus`,
`n_bullet`). Outside annotated blocks, teacher **bonus** detections are
positives with a reduced weight (default 0.3, in `config.py`). Everything else
outside annotated blocks is **unknown**, not negative, and is excluded from
training — otherwise the model learns that bullet kills are "nothing".

## Windows

- Length 4s (matches `CLIP_BEFORE_S`/`CLIP_AFTER_S`), sampled at 8 fps = 32
  frames. Aspect 16:9 preserved, short side ~224px; whether a smaller
  resolution loses accuracy is tested early. All constants live in
  `config.py`.
- A window's label counts only kills in its **central 2s**; the outer 1s each
  side is context. Tiling a video every 2s puts each kill in exactly one
  window, so inference needs no overlap merging. Each window maps to a
  `DetectedClip` centered on the window, so `score_detections` is reused as is.
- Training jitters the tile grid offset randomly so the model does not rely on
  kills landing mid-window.
- **Frame cache** (`frame_cache`): each video is decoded once (OpenCV), sampled
  at exact timestamps, resized, stored as a uint8 memmap under `tmp\frames\`
  (gitignored). ~7 GB for the five videos. Training reads the cache, never the
  video.

## Model

`torchvision.models.video.r2plus1d_18` (Kinetics-400 weights), classifier
replaced by two heads: `n_bonus` in {0, 1, 2, 3+} and `n_bullet` in
{0, 1, 2, 3+}. "No kill" is (0, 0); "mixed" is derived (both > 0), not a
class.

### Alternative backbone: X-CLIP (fallback, not the first attempt)

`r2plus1d_18` is pretrained on Kinetics-400 (real-world video), so the domain
gap to game footage is a real risk. The nearest evidence found in the
literature is a fine-tuned **X-CLIP** (video model built on CLIP, whose
web-scale image-text pretraining includes game screenshots) detecting events
in unseen first-person-shooter gameplay with >90% accuracy
([Gameplay Highlights Generation](https://arxiv.org/html/2505.07721v1)). No
pretrained model specific to RE5 or third-person shooters was found. If
`r2plus1d_18` underperforms on the held-out block, X-CLIP (via Hugging Face
`transformers`) is the next backbone to try, behind the same `model` module
interface, same windows, same cache. **Unverified:** `transformers` under
PyTorch-ROCm on Windows has not been tested; run a spike (load the model,
one fp16 forward/backward on the GPU) before committing to it.

## Training

- Cross-entropy on both heads. Empty windows dominate, so positives are
  oversampled. Sample weights: author-labeled 1.0, teacher-only bonus 0.3;
  unknown windows excluded.
- Phase 1: a few epochs with the stem and early layers frozen (limits
  overfitting on ~150 gold kills). Phase 2: unfreeze all at a low learning
  rate. AdamW, fp16 autocast (warm up under the same autocast context before
  timing), early stopping on validation, checkpoints.
- Validation: leave-one-video-out over the annotated blocks of videos 1, 2, 3,
  5; the final model trains on all of them.

## Evaluation

The same three numbers as the OCR baseline, via `score_detections` on the
held-out block — recall (weighted by kill count), clip precision, exact-count
accuracy — plus a bonus-vs-bullet confusion matrix. **To beat: recall 75.5%,
exact count 54%.** Ultimate bar: >= 93% recall.

## Human feedback loop ("reinforcement")

Each round:

1. The model tiles the not-yet-labeled parts of the videos and predicts.
2. It selects windows to review: the most uncertain (entropy of the two
   heads) plus ~30% random windows. The random slice catches confident-wrong
   cases, so the loop does not silently reinforce the model's own blind spots.
3. The author corrects counts in a review tool (`review_windows.py`). In the
   window formulation, reviewing a window fully labels it — no full-timeline
   annotation needed.
4. Corrections become gold windows; the model retrains from the previous
   weights for a few epochs, then is measured on the held-out block.
5. Stop when the held-out score stops improving.

The cost of one round (train time) is unmeasured; it is measured on the first
run once the frame cache exists.

## Code layout

New subpackage `src/biomercs_ml/detector/`, one job per module: `frame_cache`,
`windows` (tiling and window labels — pure), `annotations` (load gold,
merge with teacher, weights), `dataset` (torch Dataset over the cache),
`model`, `train`, `predict` (tile a video → `DetectedClip`s and per-window
uncertainty), `active_learning` (pick windows to review). Scripts:
`annotate.py`, `build_frame_cache.py`, `train_detector.py`,
`review_windows.py`, `evaluate_detector.py`. Existing OCR modules are
untouched; they supply teacher labels only through the existing manifests.

## Dependencies

An optional `ml` dependency group with the ROCm `torch`/`torchvision` wheels.
They are direct URLs, Windows + Python 3.12 only, so a universal `uv` lock may
resist. Decision for the first implementation step, by a quick test:
either wire them via `[tool.uv.sources]` with markers, or keep the ML
environment outside the lock with the documented `uv pip install` recipe. Either
way the OCR pipeline and its tests must keep running without torch.

## Testing

TDD as elsewhere (AGENTS.md). Pure logic — tiling, window labels, weight
merging, uncertainty selection, cache indexing — gets real tests using the
existing synthetic video. Model and training get CPU smoke tests on tiny
random tensors, guarded by `pytest.importorskip("torch")` so the OCR suite
runs anywhere. Real model quality is judged only by the benchmark, not unit
tests.

## Risks

- **Overfitting** on ~150 gold kills with a video model. Mitigation: partial
  freezing, augmentation, leave-one-video-out, and the option to fall back to a
  frozen-feature + temporal-head model (same cache, same windows).
- **Domain gap:** Kinetics pretraining is real-world video, not game footage.
  Mitigation: the X-CLIP alternative backbone above, and the frozen-feature +
  temporal-head fallback.
- **Noisy evaluation:** one 49-kill test window. Mitigation: rotate the test
  block as annotation grows.
- **Window boundaries:** a kill near the edge of the 2s core is ambiguous;
  jitter and the benchmark's +-2s clip window bound the impact.
- **Long-run cost:** unknown until the first measured round.

## Open items decided during implementation (defaults given)

- Input resolution — default short side 224; test a smaller one early.
- `uv` lock vs external ML environment — decided by the first-step test.
- Teacher weak-label weight — default 0.3; only revisited if it hurts the
  validation score.
