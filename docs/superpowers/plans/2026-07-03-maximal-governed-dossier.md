# Maximal Governed Dossier Implementation Plan

> Superseded by `2026-07-06-max-mode-repair.md`. Numeric Max quotas and the old review policy in this historical plan must not be used by current runs.

> **For agentic workers:** Execute inline unless the user explicitly requests delegation. This is a large contract update; keep changes in the `storm-maximal-dossier` worktree and use existing scripts, schemas, and tests instead of adding standalone runner files.

**Goal:** Add a no-word-cap full research profile for cases where the user wants the host to write as much as the evidence warrants, while preserving governed evidence, strict STORM P1-P4, academic retrieval, external review provenance, and a loop that only promotes one final `report.md` after review passes.

**Architecture:** Reuse the existing generation chain. Add a new profile that maps to `full_dossier`, `full` output, `host` retrieval, strict STORM lens, and academic baseline. Change length validation from bounded range to explicit open-ended policy for that profile. Represent the loop through existing stages: `amend` creates a new generation for additional retrieval or major rewrites; `draft -> P4 -> review-prepare -> external review -> render -> validate` promotes only the review-approved candidate. Add summary metadata so the harness can prove the final report passed all review lanes without exposing process junk in release artifacts.

**Baseline:** Before implementation, `scripts/run_checks.py --all` passed on branch `storm-maximal-dossier`: 209 unittest cases, compileall, and Yao validate all OK.

---

## File Map

**Existing implementation files**

- `scripts/storm_research.py`: profile defaults, init contract, draft length enforcement, review summary, status/explain guidance.
- `scripts/contract_io.py`: strict `brief.length_contract` and profile validation.
- `scripts/report_traceability.py`: body length metrics and quote limits.
- `scripts/validate_package.py`: final `report-depth`, review closure, inventory, validation report metrics.
- `scripts/init_research_package.py`: compatibility initializer expectations if it asserts default bounded full dossier behavior.
- `scripts/run_checks.py`: no expected logic change unless dist checks need a version assertion update.

**Existing schemas**

- `schemas/brief.schema.json`
- `schemas/validation-report.schema.json`
- Any review schema only if review-loop summary needs a strict contract inside `peer-review.json`.

**Existing tests**

- `tests/test_contracts.py`
- `tests/test_storm_research_cli.py`
- `tests/test_evidence_stage.py`
- `tests/test_review_stage.py`
- `tests/test_validate_package.py`
- `tests/test_library_contract.py`
- `tests/test_init_research_package.py`
- `tests/governed_fixtures.py`

**Docs and metadata**

- `README.md`
- `SKILL.md`
- `agents/interface.yaml`
- `references/research-protocol.md`
- `references/quality-gates.md`
- `references/report-writing.md`
- `docs/migration-v3-to-v4.md`
- `CHANGELOG.md`
- `manifest.json`

## Contract Decisions

Use one new profile name everywhere:

```text
maximal_full_dossier
```

This profile means:

- Full dossier, full output, host retrieval, strict STORM lens.
- Same source, Claim, academic baseline, absence-search, P2/P3/P4, external review, render, validate, and release gates as `default_full_dossier`.
- No minimum, target, or maximum body length gate.
- Quote-padding limits still apply; open-ended does not allow long blockquotes to fake substance.
- Validation report still records `raw_body`, `citation_markers`, and `net_body`, but reports the length policy as `open_ended`.
- Final public `report.md` is promoted only after review passes. Drafts and review candidates remain internal.

`default_full_dossier` remains the recommended default for ordinary research. `maximal_full_dossier` is an explicit user-selected advanced option, not the default replacement.

## Task 1: Add Open-Ended Length Contract

**Files:**
- Modify: `schemas/brief.schema.json`
- Modify: `scripts/contract_io.py`
- Modify: `scripts/storm_research.py`
- Modify: `scripts/validate_package.py`
- Modify: `tests/governed_fixtures.py`
- Modify: `tests/test_contracts.py`
- Modify: `tests/test_storm_research_cli.py`
- Modify: `tests/test_validate_package.py`

- [ ] Add a strict `length_contract.policy` enum with values `bounded` and `open_ended`.
- [ ] For `bounded`, keep required positive integer `minimum`, `target`, `maximum`, and `minimum <= target <= maximum`.
- [ ] For `open_ended`, require `minimum`, `target`, and `maximum` to be absent; keep `unit` and `content_standard`.
- [ ] Add `maximal_full_dossier` to init and brief profile enums.
- [ ] Make `maximal_full_dossier` default to `length_contract.policy = open_ended`.
- [ ] Reject `--min-units` or `--max-units` when the selected profile is `maximal_full_dossier`; this avoids silently converting it back to a bounded profile.
- [ ] Update draft preflight and draft commit so open-ended runs skip range checks but still run traceability and quote-padding checks.
- [ ] Update package validation so `report-depth` passes open-ended length with metrics recorded and clear wording.
- [ ] Add tests proving a short open-ended report is not failed by length alone but still fails if traceability, quotes, or review closure fail.
- [ ] Add tests proving bounded full dossier behavior is unchanged.

## Task 2: Make Review Loop Closure Observable

**Files:**
- Modify: `scripts/storm_research.py`
- Modify: `scripts/validate_package.py`
- Modify: `tests/test_review_stage.py`
- Modify: `tests/test_validate_package.py`
- Modify: `tests/governed_fixtures.py`

- [ ] Extend `peer-review.json.summary` with `review_loop_policy`.
- [ ] For normal full dossiers, record `single_pass_external_review`.
- [ ] For `maximal_full_dossier`, record `iterate_until_pass`.
- [ ] Record counts for all existing review lanes: claim reviews, paragraph reviews, fact checks, conflict reviews, draft audits, and P4 repair actions.
- [ ] Require all review lanes already required for full dossiers to be present and passing; do not weaken current review gates.
- [ ] For `maximal_full_dossier`, require `P4` to exist even if there are no repair actions, so the red-team step is visible.
- [ ] If P4 has required repairs, require applied revisions before `review-prepare`, as current code already does.
- [ ] Keep the actual loop outside one command: failed review exits non-zero; the operator uses `amend` or retries the failed stage. Do not add an infinite loop command.
- [ ] Add validation checks that `maximal_full_dossier` cannot validate without `review_loop_policy = iterate_until_pass`.

## Task 3: Keep Profile Selection And UX Clean

**Files:**
- Modify: `agents/interface.yaml`
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `tests/test_library_contract.py`

- [ ] Add `maximal_full_dossier` to advanced profile options.
- [ ] Keep primary menu as `default_full_dossier` and `briefing`; do not force every vague request into maximal mode.
- [ ] Document the user prompt shape:

```text
运行 /path/to/storm-deepresearch-skill，使用 maximal_full_dossier。
不设字数上限；不要用 briefing；按 STORM -> 索引 -> 写作 -> 外部审查循环推进，
只有所有审查通过后输出唯一最终 report。
我的研究内容是：xxx
```

- [ ] Update `SKILL.md` router rules so hosts ask whether the user wants default complete research, short briefing, or advanced maximal mode only when the user asks for no-budget / no-cap / exhaustive research.
- [ ] Ensure docs say this is slower and more expensive in host time/tool calls, but not more permissive on evidence.

## Task 4: Version, Migration, And Release Notes

**Files:**
- Modify: `manifest.json`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Create: `docs/migration-v3-to-v4.md`
- Modify: `references/research-protocol.md`
- Modify: `references/quality-gates.md`
- Modify: `references/report-writing.md`

- [ ] Bump to `4.0.0` because `brief.length_contract` changes shape for all new runs.
- [ ] Explain that old v3 bounded brief files are interpreted by old packages; new v4 runs require explicit `policy`.
- [ ] Document that open-ended length is not a bypass for evidence, citation, PDF, review, or release gates.
- [ ] Document that the loop is receipt/generation driven, not an unbounded hidden while-loop inside one command.

## Task 5: Verification

**Narrow checks after each task:**

```bash
.venv/bin/python -m unittest tests.test_contracts tests.test_storm_research_cli tests.test_review_stage tests.test_validate_package tests.test_library_contract -v
```

**Full checks before declaring complete:**

```bash
.venv/bin/python scripts/run_checks.py --all
.venv/bin/python scripts/run_checks.py --dist
```

**Expected observable results:**

- `storm_research.py init --research-profile maximal_full_dossier ...` creates a valid brief with `length_contract.policy = open_ended`.
- `default_full_dossier` still creates a bounded `8000-10000` Chinese net body character contract.
- Draft and validation report record length metrics for both profiles.
- Open-ended profile does not fail solely because body length is below or above the bounded range.
- Open-ended profile still fails on missing traceability, excessive quote padding, missing P4, missing external review provenance, open P4 repairs, missing PDF, or format drift.
- Dist package validates with OpenAI, Claude, agent-skills, VS Code, and generic adapters.
