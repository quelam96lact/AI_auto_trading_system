# Fix Pre-existing ruff Findings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get `uv run ruff check trading tests` to exit 0 (so the CI
workflow added in `docs/superpowers/plans/2026-08-08-ci-cd-and-ruff-fix.md`
goes green) by fixing the 29 findings that are genuine style issues and
suppressing the 19 findings that are confirmed-intentional resilience/
timezone patterns — without rewriting any runtime behavior.

**Architecture:** One `pyproject.toml` config change (`[tool.ruff.lint]
ignore = [...]`) handles the 19 intentional-pattern findings in one step.
The 29 style findings are fixed in two passes: `ruff check --fix` for
everything auto-fixable, then a handful of manual one-line edits for what's
left (`SIM102`/`SIM103`/`SIM117` restructuring, one `ClassVar` annotation,
one unused variable, one closure default-arg fix).

**Tech Stack:** `ruff` (already added as a dev dependency in the CI/ruff
fix plan), `uv run pytest`.

## Global Constraints

- Do not change any runtime behavior — 133 existing unit tests must
  continue to pass unchanged after every step.
- Do not touch `except Exception` handling or datetime-parsing logic in
  `trading/collector/*` — those are the confirmed-intentional patterns this
  plan suppresses via config, not rewrites.
- `[tool.ruff.lint] ignore = ["BLE001", "S110", "DTZ007", "DTZ001"]`, each
  with an inline comment explaining why (copy the rationale from the spec —
  no silent ignores).
- Final state: `uv run ruff check trading tests` exits 0.

---

### Task 1: Add `[tool.ruff.lint]` ignore config

**Files:**
- Modify: `pyproject.toml`

**Interfaces:** none (config only).

- [ ] **Step 1: Add the section**

At the end of `pyproject.toml`, add:

```toml
[tool.ruff.lint]
# BLE001/S110: except Exception tran la pattern CO Y cho resilience cua he
# thong trading live (collector/feed khong duoc crash vi 1 loi la) - xem
# docs/superpowers/specs/2026-08-08-fix-preexisting-ruff-findings-design.md.
# DTZ007/DTZ001: parse chuoi gio VN khong co tz (SSI tra ve vay) bang
# strptime() (naive) roi .replace(tzinfo=TZ) ngay sau - cach lam dung cho
# du lieu khong co tz trong chuoi goc, khong phai bug.
ignore = ["BLE001", "S110", "DTZ007", "DTZ001"]
```

- [ ] **Step 2: Confirm the 19 intentional findings disappear and 29 remain**

Run: `uv run ruff check trading tests`
Expected: fewer errors than before (down from 48). Run:
`uv run ruff check trading tests 2>&1 | tail -3` to see the new total —
expected to say `Found 29 errors` (the style findings from Task 2/3).

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest -m "not integration" -v`
Expected: all pass, unchanged (config-only change, no code touched).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "ruff: ignore BLE001/S110/DTZ007/DTZ001 (confirmed intentional patterns)"
```

---

### Task 2: Auto-fix everything ruff can fix safely

**Files:**
- Modify: whatever `ruff check --fix` touches (expected: import ordering
  and modernization across several files under `trading/` and `tests/`).

**Interfaces:** none (mechanical fixes only).

- [ ] **Step 1: Run the auto-fixer**

Run: `uv run ruff check --fix trading tests`
This resolves the `[*]`-marked findings (`I001` import sort, `UP035`,
`UP041`, and the auto-fixable `F401` unused imports).

- [ ] **Step 2: Review the diff**

Run: `git diff --stat`
Expected: only import-statement lines change (reordering, `from typing
import Callable` → `from collections.abc import Callable`, unused-import
removals) — no logic lines. If anything outside an import statement
changed, stop and inspect that file manually before continuing.

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest -m "not integration" -v`
Expected: all pass, unchanged.

- [ ] **Step 4: Check remaining ruff count**

Run: `uv run ruff check trading tests 2>&1 | tail -3`
Expected: fewer than 29 remain (auto-fix handles `I001` ×7, `UP035` ×3,
`UP041` ×1, and some/all of `F401` ×3 — the exact remaining count depends
on how many `F401`s were auto-fixable; note it for Task 3).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "style: auto-fix ruff import-sort and modernize findings"
```

---

### Task 3: Manual fixes for the rest

**Files:**
- Modify: `trading/collector/feed.py` (B023)
- Modify: `trading/derivative_backtest.py` (SIM102)
- Modify: `trading/derivative_risk.py` (SIM103)
- Modify: `tests/test_feed.py` (RUF012)
- Modify: whichever file(s) `uv run ruff check trading tests` still lists
  for `SIM117` (×9) and `F841` (×1) and `C408` (×1) and any leftover
  `F401` — run the command first to get exact locations before editing
  (see Step 1).

**Interfaces:** none (style-only edits, no signature changes).

- [ ] **Step 1: List everything still remaining**

Run: `uv run ruff check trading tests`
Read the full output — this is the authoritative list of exact
file:line:column locations for this task. Work through them one rule at a
time (below), re-running this command after each rule to confirm progress.

- [ ] **Step 2: Fix B023 in `trading/collector/feed.py`**

Find (around line 78):
```python
                stream.start(
                    self.on_raw, lambda e: dead.set(), build_channel(self.symbols)
                )
```
Replace with (bind `dead` as a default argument, same pattern the
neighboring `_closed` closure in this file already uses):
```python
                stream.start(
                    self.on_raw,
                    lambda e, dead=dead: dead.set(),
                    build_channel(self.symbols),
                )
```

- [ ] **Step 3: Fix SIM102 in `trading/derivative_backtest.py`**

Ruff will print the exact suggested combined condition for the nested
`elif`/`if` in `run_derivative_backtest()` (the `bear`/`net == 0` branch).
Combine the two conditions with `and` into a single `if`, keeping the same
body — e.g. if the two conditions are `crossover == "bear" and net == 0`
(outer) and `risk.approve_open("short", net, daily_pnl, today)` (inner),
the result is:
```python
        elif (
            crossover == "bear"
            and net == 0
            and risk.approve_open("short", net, daily_pnl, today)
        ):
            all_fills.append(
                broker.open_short(bar.symbol, strategy.qty, bar.close, bar.ts)
            )
```
Apply the equivalent combination ruff suggests — do not change which
branch this is (still the "open short from flat" branch), only the `if`
structure.

- [ ] **Step 4: Fix SIM103 in `trading/derivative_risk.py`**

In `DerivativeRiskManager.approve_open()`, replace:
```python
        if self._halt_check(daily_pnl, today):
            return False
        if abs(current_qty) >= self.max_contracts:
            return False
        return True
```
with:
```python
        if self._halt_check(daily_pnl, today):
            return False
        return not abs(current_qty) >= self.max_contracts
```

- [ ] **Step 5: Fix RUF012 in `tests/test_feed.py`**

Find (around line 56-58):
```python
class FakeStreaming:
    instances = []
    fail_first_wait = True
```
Add the `ClassVar` import and annotation:
```python
from typing import ClassVar


class FakeStreaming:
    instances: ClassVar[list] = []
    fail_first_wait = True
```
(If `typing` is already imported in this file, add `ClassVar` to the
existing import line instead of a new one — check the top of the file
first.)

- [ ] **Step 6: Fix the remaining `SIM117`, `F841`, `C408`, and any leftover
  `F401` findings from Step 1's list**

For each remaining location ruff lists:
- `SIM117` ("Use a single `with` statement with multiple contexts"): ruff's
  `help:` text shows the exact combined `with` statement — apply it as
  shown, changing only the `with`/nesting structure, not the code inside.
- `F841` ("local variable assigned but never used", in
  `tests/test_confirm_real_order.py`, variable `mock_alert`): read the
  test, confirm the variable really is unused (not a typo'd reference
  elsewhere in the same test), then either remove the assignment (if the
  mock object itself is never asserted on) or prefix it with `_` (e.g.
  `_mock_alert = ...`) if pytest fixture mechanics require the assignment
  to exist. Prefer removing it entirely if nothing in the test references
  it — do not guess; open the test function and check every line.
- `C408` ("unnecessary `dict()` call"): replace `dict(...)` with the
  equivalent `{...}` literal ruff's `help:` text shows.

Re-run `uv run ruff check trading tests` after each rule group to confirm
it's gone before moving to the next.

- [ ] **Step 7: Run the full test suite**

Run: `uv run pytest -m "not integration" -v`
Expected: all 133 pass, same count as before this whole plan started (no
test added, none removed, no behavior changed).

- [ ] **Step 8: Confirm ruff is fully clean**

Run: `uv run ruff check trading tests`
Expected: `All checks passed!`, exit code 0.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "style: fix remaining ruff findings (SIM102/103/117, RUF012, F841, C408, B023)"
```

---

### Task 4: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Full clean run**

Run: `uv run ruff check trading tests && uv run pytest -m "not integration" -v`
Expected: ruff `All checks passed!`, pytest all pass.

- [ ] **Step 2: Confirm no unrelated files changed**

Run: `git diff main...HEAD --stat -- pyproject.toml trading/ tests/`
Read the list — every changed file should be one already named in Task
1-3 above, or an import-sort-only change from Task 2's auto-fix. If a file
neither named in this plan nor part of Task 2's auto-fix shows a change,
stop and investigate before proceeding.

- [ ] **Step 3: Push and confirm CI goes green**

```bash
git push origin feature/data-layer
```
Then check the workflow run (e.g. `gh run list --branch feature/data-layer
--limit 3` and `gh run watch <run-id>` or check in the GitHub UI) — expect
the `ruff check` step to now pass where it previously failed.

- [ ] **Step 4: Report back**

Summarize: final ruff/pytest output, the list of commits made, and the CI
run result (URL or run ID + conclusion).
