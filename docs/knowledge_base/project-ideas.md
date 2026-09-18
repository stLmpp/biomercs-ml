# Project ideas (not yet scoped)

Ideas worth remembering for `biomercs-ml`, deliberately kept out of the
current spec/plan. See [README.md](./README.md) for how to use this
file — append here rather than losing ideas that come up mid-conversation.

## Bootstrapping / self-training loop

Once a first small hand-labeled dataset and a first model exist, use the
model to pre-label a much larger unlabeled batch, review/correct only the
low-confidence predictions (active learning) instead of relabeling
everything by hand, retrain, and repeat. Each cycle should reduce the
manual labeling burden. Needs a human review checkpoint every cycle, or
the model can reinforce its own blind spots silently.

## Two-layer analysis architecture (ML for detection, LLM for narration)

The precision-critical part (recognizing what actually happened in a
clip — movement, positioning, technique execution) is fundamentally a
supervised ML / computer-vision problem, not something to hand to a
general-purpose multimodal LLM — RE5/RE6 is a closed, deterministic game
engine (fixed animations, fixed assets, fixed maps), which is exactly the
favorable case for classical/supervised CV (even simple frame/template
matching for known, fixed animations) rather than open-world video
understanding. A general LLM/VLM is the wrong tool for that detection
step, but a good fit *on top* of structured, already-detected events —
narrating differences between two runs in natural language, or answering
strategy questions from a text knowledge base (a real RAG use case, using
material like `mercenaries-mechanics.md` as the corpus).

## Automated run coaching (the original idea that started this project)

Long-term goal: feed the system a video (the author's own run), compare
it against WR runs in the same map section, and get feedback on where
time/technique was lost. Concretely scoped down from "watch a whole run
end-to-end," which isn't reliable with current tooling — instead: use
detected events (once they exist) to identify the specific short clip
where the author's run diverged from a reference WR run in the same
section, and only then apply closer (possibly LLM-assisted) comparison to
that narrow clip pair. Point detection at where to look; don't ask a
model to freeform-review an entire run.

## Per-enemy attribution inside "mixed" kill groups

The current kill-labeling pipeline (see the
[kill-labeling-pipeline design spec](../superpowers/specs/2026-09-16-kill-labeling-pipeline-design.md))
can tell that a simultaneous kill group was a mix of N bonus kills and M
bullet kills, but not *which* specific enemy was which, from HUD signals
alone. Possible future angle: sample at native frame rate (60fps) instead
of a coarser interval, and check whether the game engine actually
processes simultaneous kills as discrete internal ticks a few frames
apart (even if visually merged to a human) — if so, matching each
enemy's death-animation start frame to the nearest timer increment could
resolve individual attribution. Speculative, not validated, not planned.

## GPU acceleration for digit-template matching -- likely not worth it as-is, revisit only after batching

Investigated during a performance pass on `hud_reader.sample_video`
(2026-09-18): profiling found ~84% of a pipeline run's time is
`cv2.matchTemplate` calls in the per-tick digit-matching loop (the rest
is HUD-offset calibration, since sped up ~8.6x with a coarse-to-fine
search -- see DECISIONS.md). GPU seemed like an obvious lever, so it
was benchmarked directly rather than assumed: on the dev Mac (M2 Pro,
OpenCV built with OpenCL support, `cv2.ocl.haveOpenCL()` true),
`cv2.matchTemplate` via `cv2.UMat` (OpenCV's transparent GPU dispatch)
measured **~30x *slower*** than plain CPU for this workload (3.2ms/call
vs 0.11ms/call) -- the crops are tiny (~34x46 to ~46x52px), so GPU
kernel-launch and memory-transfer overhead per call vastly exceeds the
actual compute, since the pipeline makes ~250k+ *separate* tiny calls
rather than one large batched one.

The user also has a second PC (AMD Ryzen 9700X + Radeon 9070 XT) --
worth keeping this idea open for that machine specifically, but the
same root problem (overhead-dominated tiny-call workload) would very
likely still apply there, and could be *worse*: a discrete GPU talks to
the CPU over PCIe with real per-call transfer latency, whereas Apple
Silicon's unified memory has none. More CPU cores on that machine
*would* directly help the separate multiprocessing effort (parallelize
`sample_video`'s per-tick reads across processes -- see DECISIONS.md),
independent of the GPU question.

**GPU would only plausibly help after a much bigger rewrite**: stack
all of a digit's template samples into one tensor and do a single
batched cross-correlation per slot (e.g. via PyTorch's `conv2d` on
ROCm/MPS) instead of thousands of separate `cv2.matchTemplate` calls --
amortizing dispatch overhead across a real batch. That's effectively
replacing OpenCV's matching core with a hand-rolled correlation
implementation, a project of its own (high effort, real correctness
risk re-validating against every existing digit-matching test and
fixture), not a follow-on to the current multiprocessing work. Revisit
only if that batching rewrite is separately justified -- don't reach
for GPU on its own again without it.

## Movement/positioning analysis

The thing that actually separates a good run from a world record is
movement/positioning decision-making (see `mercenaries-mechanics.md`),
not the scoring HUD numbers. HUD OCR (timer, kill/combo counters) is
reliable but is the *least* important signal for this — it only helped
bootstrap ground truth for the bullet-kill/bonus-kill label, which
happens to be HUD-derivable. Actually modeling movement quality will need
real spatial/temporal computer vision (tracking player and enemy
positions over time), which hasn't been designed yet.
