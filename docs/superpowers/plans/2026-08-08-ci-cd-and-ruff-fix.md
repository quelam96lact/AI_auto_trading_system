# CI/CD + ruff Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal GitHub Actions workflow that runs the unit test
suite and `ruff check` on every push and every PR into `main`, and fix the
missing `ruff` dev dependency so `uv run ruff check trading tests` (already
documented in `CLAUDE.md`) actually works.

**Architecture:** One new workflow file (`.github/workflows/ci.yml`) with a
single job: checkout → install `uv` → `uv sync --extra dev` → run pytest
(excluding integration tests, which need Postgres/NATS not available on the
runner) → run `ruff check`. `ruff` is added to `pyproject.toml`'s `dev`
extra so both CI and local `uv sync --extra dev` install it.

**Tech Stack:** GitHub Actions, `uv` (via `astral-sh/setup-uv`), Python
3.11, `ruff` (default rule set, no `[tool.ruff]` customization).

## Global Constraints

- Trigger: every `push` (any branch) + every `pull_request` targeting
  `main`.
- Single job, `ubuntu-latest`, Python 3.11 (matches `requires-python =
  ">=3.11"`).
- Do NOT run integration tests in CI (`-m "not integration"` only) — no
  Postgres/NATS service on the runner.
- Do NOT add `[tool.ruff]` config or `ruff format --check` — default rules,
  `ruff check` only, matching what `CLAUDE.md` already documents.
- Do NOT fix any lint errors `ruff check` finds in pre-existing code — report
  them verbatim instead.
- Do NOT modify `DEPLOYMENT.md`, `docker-compose.yml`, or any file under
  `trading/`.

---

### Task 1: Add `ruff` dev dependency + verify it installs and runs locally

**Files:**
- Modify: `pyproject.toml:14`

**Interfaces:** none (dependency declaration only).

- [ ] **Step 1: Read the current dev dependency line**

Run: `grep -n "^dev = " pyproject.toml`
Expected output: `14:dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]`

- [ ] **Step 2: Add `ruff` to the `dev` extra**

In `pyproject.toml`, change line 14 from:
```toml
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]
```
to:
```toml
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "ruff>=0.6"]
```

- [ ] **Step 3: Sync and verify `ruff` installs**

Run: `uv sync --extra dev`
Expected: completes with no errors, installs `ruff` into `.venv`.

- [ ] **Step 4: Run `ruff check` and record the exact result**

Run: `uv run ruff check trading tests`

Two possible outcomes — handle both:
- **Exit code 0, no output:** clean, nothing further to do in this task.
- **Non-zero exit, lint errors printed:** these are pre-existing issues in
  code this task does not own. **Do not fix them.** Copy the full output
  verbatim into your final report (see "Báo cáo lại" in the execution
  prompt) under a clearly labeled section, e.g. "Pre-existing ruff findings
  (not fixed, out of scope)". Continue to Task 2 regardless — a non-zero
  `ruff check` exit here does not block this task; it only becomes a CI gate
  after Task 2 (see Task 2 Step 3's note).

- [ ] **Step 5: Run the full unit test suite to confirm nothing else broke**

Run: `uv run pytest -m "not integration" -v`
Expected: all PASS (adding a dev-only tool dependency does not change any
runtime behavior — if anything fails, it is unrelated to this change and
must be reported, not silently worked around).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml
git commit -m "fix: add missing ruff dev dependency"
```

---

### Task 2: Add the GitHub Actions CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:** none (CI configuration only).

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: uv sync --extra dev
      - run: uv run pytest -m "not integration" -v
      - run: uv run ruff check trading tests
```

- [ ] **Step 2: Validate the YAML is well-formed**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('valid YAML')"`
Expected: prints `valid YAML`, no exception. (`PyYAML` is already a project
dependency — see `pyproject.toml:10` — so this doesn't require installing
anything new.)

- [ ] **Step 3: Note the pre-existing ruff findings from Task 1, if any**

If Task 1 Step 4 found pre-existing lint errors, this new CI job's
`ruff check` step **will fail on the very first run** once pushed (this
plan does not fix those errors — that's explicitly out of scope). This is
expected and not a defect in this task's work — call it out clearly in your
final report so Claude (the planner) knows to expect a red CI check on the
first push and can decide separately whether to fix the pre-existing lint
issues.

- [ ] **Step 4: Confirm no other files changed**

Run: `git status --short`
Expected: exactly `pyproject.toml` (modified, from Task 1) and
`.github/workflows/ci.yml` (new, untracked) — nothing else.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow for tests + lint"
```

---

### Task 3: Final verification and report

**Files:** none (verification only)

- [ ] **Step 1: Run the full unit test suite one more time**

Run: `uv run pytest -m "not integration" -v`
Expected: all PASS.

- [ ] **Step 2: Confirm only the 2 expected files changed across both commits**

Run: `git diff main...HEAD --stat -- pyproject.toml .github/`
Expected: shows exactly `pyproject.toml` (+1/-1 line) and
`.github/workflows/ci.yml` (new file) — nothing else. (Note: unlike a
`git diff HEAD --stat` check against forbidden files in other plans, this
plan's Task 1/2 are the only changes expected on top of whatever the branch
already had before this plan started — if `main...HEAD` shows unrelated
pre-existing diffs from earlier work on this branch, that's expected branch
history, not something this task introduced; cross-check with `git log
--oneline -5` to see this plan's 2 commits sit on top of the branch's prior
tip.)

- [ ] **Step 3: Report back**

Summarize: whether `ruff check` was clean or found pre-existing issues
(paste the full output either way), full `pytest` output, confirmation from
Step 2, and the 2 commit hashes created.

Do not push. Do not open a PR.
