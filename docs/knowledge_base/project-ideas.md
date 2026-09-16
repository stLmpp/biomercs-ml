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

## Movement/positioning analysis

The thing that actually separates a good run from a world record is
movement/positioning decision-making (see `mercenaries-mechanics.md`),
not the scoring HUD numbers. HUD OCR (timer, kill/combo counters) is
reliable but is the *least* important signal for this — it only helped
bootstrap ground truth for the bullet-kill/bonus-kill label, which
happens to be HUD-derivable. Actually modeling movement quality will need
real spatial/temporal computer vision (tracking player and enemy
positions over time), which hasn't been designed yet.
