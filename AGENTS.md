# AGENTS.md

Guidance for anyone (human or agent) working in this repo. Project context
(what this is, why it exists) lives in `docs/superpowers/` and
`docs/knowledge_base/` — read those first. This file is about *how* to write
code here.

## Environment

- Python 3.12+, managed entirely with `uv`. Never use `pip` directly.
- Add a runtime dependency: `uv add <package>`. Dev-only: `uv add --dev <package>`.
- Run anything in the project's venv: `uv run <command>` (e.g. `uv run pytest`).
- Layout is `src/biomercs_ml/` (src-layout), tests mirror it under `tests/`.

## Testing

- Run the full suite: `uv run pytest -v`. Run one file: `uv run pytest tests/test_x.py -v`.
- TDD is the default workflow here: write a failing test, watch it fail for
  the right reason, then write the minimal implementation that passes it.
  Don't write implementation code with no failing test behind it.
- Every public function gets at least one test. Prefer real fixtures
  (`tests/fixtures/`) over mocks; mock only true I/O boundaries this project
  doesn't control (e.g. `yt_dlp.YoutubeDL` in `test_downloader.py` — no real
  network call in a test).
- A test's assertions should fail for a specific, named reason — avoid
  tautological asserts that pass regardless of whether the code is correct.

## Code style

- Type-hint every function signature (params and return). This codebase
  targets 3.12+, so use `X | None`, `list[X]`, `dict[K, V]` — not
  `Optional`/`List`/`Dict` from `typing`.
- Use `@dataclass` for structured data crossing a function boundary (see
  `models.py`). Don't pass around bare tuples/dicts for anything with more
  than 2 fields.
- Avoid deep nesting. Prefer early `return`/`continue`/`break` guard clauses
  over nested `if` blocks — a function body nested more than ~3 levels deep
  is a sign it should be flattened or split. Example of the pattern this
  codebase uses (from `hud_reader.sample_video`):

  ```python
  if not is_valid:
      continue
  # ... happy path, not indented under an `if`
  ```

  instead of wrapping the rest of the loop body in `if is_valid: ...`.
- Use `pathlib.Path`, not `os.path`, for filesystem paths.
- No comments explaining *what* code does — names should make that obvious.
  Only comment a non-obvious *why* (a hidden constraint, a workaround, a
  domain rule that isn't derivable from the code itself).
- No docstrings on every function as a matter of course. A module-level
  docstring is fine when it documents a non-obvious constraint (see
  `config.py`).
- Keep each pipeline module (`hud_reader`, `event_detector`, `auto_labeler`,
  `clip_extractor`, `downloader`, `dataset_manifest`) doing exactly one job
  with a narrow, explicit interface — that's the whole point of the
  architecture. Don't reach into another module's internals; go through its
  public functions.
- Centralize tunable constants in `config.py`. Never hardcode a magic number
  (pixel coordinate, threshold, interval) inline in a pipeline module.
- Don't add abstractions, config flags, or error handling for cases that
  can't happen here. This is a personal-use pipeline with known inputs, not
  a library — match the code's ambition to that.

## Git

- One commit per completed task/feature, not one giant commit at the end.
- Imperative mood, present tense commit messages ("Add X", not "Added X" or
  "Adds X").
- Run the full test suite before committing.
