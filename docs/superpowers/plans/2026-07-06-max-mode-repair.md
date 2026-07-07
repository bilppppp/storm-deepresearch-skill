# Max Mode Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task in the existing `storm-maximal-dossier` worktree. Do not dispatch subagents unless the user explicitly asks for delegation. Preserve unrelated worktree changes.

**Goal:** Repair `maximal_full_dossier` so it stops on demonstrated research saturation and substantive STORM-plus-academic review closure, rather than fixed source counts or review-shaped JSON.

**Architecture:** Keep the existing governed stage chain and artifact names. Replace fixed Max quantity gates with a coverage-and-saturation contract recorded in the existing research plan and `retrieval-audit.jsonl`. Replace the current role/count review check with a concern-centric state machine in the existing `review-loop.json`, binding each review, revision, re-review, and STORM disposition to exact report/evidence hashes and captured host execution.

**Tech Stack:** Python standard library, JSON Schema Draft 2020-12, `unittest`, existing receipt/generation harness, existing Markdown/HTML/PDF render pipeline.

---

## Defects Being Repaired

1. Max currently exposes `80 + 8`, `120`, `24`, `40`, `30`, and `10` as terminal thresholds. This makes an agent optimize for the numbers and permits an exactly-88-source result to look complete even when material gaps remain.
2. A genuinely small or bounded corpus cannot pass without manufacturing sources, even if every discoverable record has been screened.
3. `review-loop.json` currently proves roles, round count, hashes, and final `accept`, but not that reviews are specific, independent, or causally responsible for changes.
4. Current fixtures use generic reasons such as `Check source closure.` and reuse the same candidate hash in both rounds. The contract therefore accepts a simulated loop.
5. P4 STORM red-team output and the academic panel are adjacent artifacts. They do not yet share one concern, action, and re-review state machine.

## Contract Decisions

### Max completion

- Source, candidate, tasklet, finding, Claim, section, and review-round counts remain observable metrics, not success targets.
- Remove `80 + 8` and `120` from pass/fail logic and from host-facing prompts. Do not replace them with another fixed source number.
- Remove fixed `24/40/30/10` Max pass thresholds. Completeness is relational:
  - every P1 research question becomes a tasklet;
  - every tasklet ends as `answered`, `uncertainty`, or reasoned `out_of_scope`;
  - every material report assertion maps to a registered Claim and exact evidence locator;
  - every planned section maps to evidence or an explicit uncertainty;
  - every P2 blind spot and resolver question has a closed disposition.
- Max retrieval ends only when every open gap has one of these evidence-backed terminal states, and each terminal state binds a `review_concern_id` that the domain reviewer must close in `review-loop.json`:
  - `saturated`: two consecutive gap-fill waves add no new material finding, contradiction, or usable evidence for that gap;
  - `bounded_corpus_exhausted`: the finite result set was enumerated, deduplicated, screened, and captured as far as access permits;
  - `access_limited_uncertainty`: access prevented exhaustion, the limitation is disclosed, and reviewers confirm the missing material does not support a stronger conclusion;
  - `out_of_scope`: the scope decision is explicit and accepted by the editor.
- Source count never proves saturation. A run with 200 sources and an open material gap fails. A genuinely bounded corpus with fewer than 80 sources may pass only with exhaustive search evidence and independent review acceptance. A small-source run with only self-declared saturation and no closed terminal-gap review concern fails.
- Runtime and token use remain observations, never validation criteria.

### Review completion

- Do not require a manufactured non-accept round. A clean candidate may receive `accept` at initial panel review, but it still needs a separate final-integrity pass.
- Any actual blocking or required concern starts a revision cycle. That cycle cannot close until the revised report/evidence bundle is independently re-reviewed.
- Max has no hidden infinite loop and no fixed maximum review count. Each cycle is an explicit generation/receipt. A stopped run with open concerns is `blocked_with_unresolved_issues`, not deliverable.
- Scientific uncertainty may remain when accurately scoped and disclosed. Workflow defects, unsupported material Claims, unprocessed STORM gaps, and unresolved blocking concerns may not remain.

## Existing Files To Modify

- `scripts/storm_research.py`: Max contract, plan/retrieval saturation gates, review state machine, status/explain output.
- `scripts/contract_io.py`: strict validation of the repaired Max brief.
- `scripts/normalize_retrieval.py`: normalize additional retrieval-audit record kinds without creating a new ledger.
- `scripts/validate_package.py`: independently recompute saturation and review closure.
- `scripts/validate_evidence.py`: final material-Claim and uncertainty closure checks.
- `schemas/brief.schema.json`: replace fixed Max minima with completion-policy fields.
- `schemas/research-plan.schema.json`: allow Max open-ended retrieval budget and explicit stop conditions.
- `schemas/retrieval-record.schema.json`: add search-wave, gap-assessment, and saturation-assessment records.
- `schemas/review-provenance.schema.json`: support per-role, per-round captured sessions in one provenance envelope.
- `schemas/semantic-review-record.schema.json`: require specific targets, evidence, requested action, and acceptance test.
- `schemas/validation-report.schema.json`: expose saturation and substantive review outcomes.
- Existing Max, retrieval, review, package-validation, and fixture tests.
- `README.md`, `SKILL.md`, `agents/interface.yaml`, prompt/protocol/gate/writing references, migration guide, and changelog.

No new runtime script or public deliverable file is introduced. `retrieval-audit.jsonl`, `review-loop.json`, and `validation-report.json` remain the canonical artifacts.

---

### Task 1: Replace Fixed Max Quotas With A Saturation Contract

**Files:**
- Modify: `schemas/brief.schema.json`
- Modify: `schemas/research-plan.schema.json`
- Modify: `scripts/contract_io.py`
- Modify: `scripts/storm_research.py`
- Test: `tests/test_contracts.py`
- Test: `tests/test_storm_research_cli.py`

- [x] **Step 1: Add failing brief-contract tests**

Assert that a new Max brief contains this contract and does not contain the old numeric quota fields:

```json
{
  "completion_policy": "coverage_and_saturation",
  "discovery_surface_policy": "domain_adaptive_with_mandatory_counterevidence",
  "surface_applicability_required": true,
  "tasklet_closure_required": true,
  "storm_gap_closure_required": true,
  "material_novelty_window": 2,
  "final_integrity_required": true,
  "review_policy": "concern_driven_until_clear"
}
```

Specifically reject `min_independent_sources`, `min_used_source_buffer`, `min_candidate_records`, `min_tasklets`, `min_usable_findings`, `min_material_claims`, `min_evidence_sections`, and `min_review_rounds` in a new Max brief.

- [x] **Step 2: Run the narrow tests and confirm failure**

```bash
.venv/bin/python -m unittest tests.test_contracts tests.test_storm_research_cli -v
```

Expected: failures refer to the current numeric Max contract and `retrieval_budget.max_sources >= 88`.

- [x] **Step 3: Implement the repaired brief and plan contract**

Change Max `retrieval_budget` to:

```json
{
  "policy": "open_ended_until_saturation",
  "max_queries": null,
  "max_sources": null,
  "stop_conditions": [
    "tasklet_closure",
    "storm_gap_closure",
    "material_novelty_saturation",
    "reviewer_no_material_omission"
  ]
}
```

Keep bounded numeric budgets for briefing and default full dossier. Reject numeric Max ceilings because they silently turn Max into a quota-limited run.

The source plan must contain a surface-applicability matrix. Scholarly indexes, publisher/full text, secondary synthesis, and counterevidence are normal external-research expectations; official sources, registries, patents, archives, datasets, or other domain surfaces become mandatory when the topic makes them applicable. High-stakes medical work still requires a literature database and a trial registry. A non-applicable surface needs a reason and may be challenged by the domain reviewer.

- [x] **Step 4: Remove quantity-based Max plan and ingest failures**

Delete the `80 + 8`, `120`, `24`, `40`, `30`, and `10` terminal checks. Preserve discovery-surface coverage, high-stakes aliases, candidate include/exclude decisions, exact captures, identity resolution, version merging, and Claim-Evidence closure.

- [x] **Step 5: Re-run the narrow tests**

Expected: the repaired contract tests pass; default full dossier and briefing tests remain unchanged.

---

### Task 2: Make Retrieval Saturation Recomputable

**Files:**
- Modify: `schemas/retrieval-record.schema.json`
- Modify: `scripts/normalize_retrieval.py`
- Modify: `scripts/storm_research.py`
- Modify: `scripts/validate_package.py`
- Test: `tests/test_normalize_retrieval.py`
- Test: `tests/test_storm_research_cli.py`
- Test: `tests/test_validate_package.py`

- [x] **Step 1: Add failing saturation tests**

Add these cases:

1. Exactly 88 used sources with an open P2 retrieval gap fails.
2. More than 88 sources without consecutive zero-material-delta waves fails.
3. A bounded corpus below 80 passes when every returned candidate is screened and the independent domain reviewer accepts the exhaustion claim.
4. A claimed saturation record whose counts do not match search runs/candidates/findings fails.
5. Reusing the same query response as two search waves fails.

- [x] **Step 2: Extend the existing retrieval ledger**

Add `record_kind` values without creating another file:

```json
{
  "record_kind": "search_wave",
  "wave_id": "W003",
  "gap_ids": ["G004"],
  "search_run_ids": ["SR021", "SR022"],
  "new_candidate_ids": ["K081"],
  "new_source_ids": [],
  "new_finding_ids": [],
  "new_contradiction_ids": [],
  "material_delta": 0
}
```

```json
{
  "record_kind": "gap_assessment",
  "gap_id": "G004",
  "terminal_state": "saturated",
  "supporting_wave_ids": ["W003", "W004"],
  "reason": "Two independent gap-fill waves produced no material novelty.",
  "review_concern_id": "RC014"
}
```

For every terminal state, require a `review_concern_id` that is later closed by the domain reviewer. For `bounded_corpus_exhausted`, require result counts, pages/windows retrieved, every candidate disposition, deduplication totals, and access-limit disclosure. For `access_limited_uncertainty`, require an uncertainty-ledger ID.

- [x] **Step 3: Recompute material delta**

Do not trust the submitted integer. Recompute each wave from newly registered candidate/source/finding/contradiction IDs and their receipt timestamps. Reject unknown IDs, IDs first seen before the wave, duplicated response hashes, and validation-time backfills.

- [x] **Step 4: Gate P3, evidence, and validation on saturation**

Any P2 `new_retrieval` disposition blocks P3/evidence until a later generation supplies search waves and a terminal assessment. Final validation requires every material gap to be closed by one allowed terminal state.

- [x] **Step 5: Run retrieval and package tests**

```bash
.venv/bin/python -m unittest tests.test_normalize_retrieval tests.test_storm_research_cli tests.test_validate_package -v
```

---

### Task 3: Put The Max Intent Into Prompts Before Work Starts

**Files:**
- Modify: `SKILL.md`
- Modify: `agents/interface.yaml`
- Modify: `references/storm-lens-prompt-pack.md`
- Modify: `references/research-protocol.md`
- Modify: `references/report-writing.md`
- Test: `tests/test_library_contract.py`

- [x] **Step 1: Add failing documentation/interface assertions**

Require the Max instructions to state all of the following:

- source count is an observation, never a stopping target;
- do not stop at 80, 88, 120, or any other round number;
- begin with broad STORM questions, then search, run P2 gap analysis, and continue gap-fill waves until saturation;
- never manufacture one-source/one-paragraph prose to satisfy a counter;
- plan section depth and evidence needs before drafting;
- review can send the run back to retrieval, evidence, outline, or writing.

- [x] **Step 2: Update P1-P4 operating instructions**

P1 defines perspectives and falsifiable questions. P2 converts contradictions, blind spots, consensus, strongest/weakest evidence, resolver questions, and historical analogues into gap IDs. P3 is blocked until gap dispositions are valid. P4 generates concern records against the frozen draft rather than a prose-only red-team summary.

- [x] **Step 3: Update writing instructions**

Require synthesis by mechanism, controversy, chronology, and implications. Explicitly prohibit source-register narration and citation accumulation that does not alter an argument. Keep references outside body-length metrics.

- [x] **Step 4: Run library contract tests**

```bash
.venv/bin/python -m unittest tests.test_library_contract -v
```

---

### Task 4: Replace Review-Shaped JSON With Specific Concerns

**Files:**
- Modify: `schemas/semantic-review-record.schema.json`
- Modify: `scripts/storm_research.py`
- Modify: `scripts/validate_package.py`
- Test: `tests/test_review_stage.py`
- Test: `tests/test_validate_package.py`

- [x] **Step 1: Add failing specificity tests**

Reject:

- `Check source closure.` and equivalent generic reasons;
- concerns without exact target IDs;
- concerns without evidence/locator, required action, or acceptance test;
- editor `accept` while a blocking concern remains;
- a concern marked addressed without a revision-map entry;
- a second-round review that repeats first-round text or evaluates the old subject hash.

- [x] **Step 2: Require this concern contract**

Change the aggregate `review-loop.json` policy to `concern_driven_until_clear`. Require at least one substantive panel review and one separate final-integrity result, but do not require a non-accept decision or a fixed number of revision rounds.

```json
{
  "concern_id": "RC014",
  "reviewer_role": "domain_reviewer",
  "severity": "major",
  "target_kind": "claim",
  "target_id": "C021",
  "target_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "evidence_or_locator": "paragraph:17; sources:S015,S017",
  "problem": "The clinical-readiness conclusion exceeds the registered human evidence.",
  "required_action": "downgrade_claim_or_add_human_evidence",
  "acceptance_test": "C021 is qualified as preclinical or gains direct human evidence.",
  "disposition": "open",
  "reason": null
}
```

Allowed terminal dispositions are `addressed`, `waived`, and `preserved_as_uncertainty`. Evidence-integrity and high-stakes medical concerns cannot be waived. Other waivers require an editor reason and cannot support a stronger Claim.

- [x] **Step 3: Separate panel from editor**

Require these independent panel roles:

- `source_integrity_reviewer`
- `evidence_method_reviewer`
- `domain_reviewer`
- `perspective_interdisciplinary_reviewer`
- `devils_advocate`
- `storm_synthesis_reviewer`

`editor_synthesizer` is not a panel reviewer. It consumes the concern matrix and computes the decision:

```text
blocker present -> reject
major present   -> major_revision
minor only      -> minor_revision
none            -> accept
```

The editor may merge duplicates but may not silently remove or weaken concerns.

- [x] **Step 4: Use stable rubric hashes**

Each panel record binds a role-specific rubric ID and the current skill-package hash. This imports the academic-review principle of committing review criteria before adjudication without adding another prompt file or runtime stage.

- [x] **Step 5: Run review tests**

```bash
.venv/bin/python -m unittest tests.test_review_stage tests.test_validate_package -v
```

---

### Task 5: Integrate STORM Into Every Review Cycle

**Files:**
- Modify: `schemas/storm-lens-artifact.schema.json`
- Modify: `scripts/storm_research.py`
- Modify: `scripts/validate_package.py`
- Modify: `references/storm-lens-prompt-pack.md`
- Test: `tests/test_review_stage.py`
- Test: `tests/test_validate_package.py`

- [x] **Step 1: Add failing STORM-review tests**

Reject a Max review round that lacks any of:

- direct perspective conflicts;
- strongest and weakest evidence assessments;
- cross-perspective consensus;
- field-wide blind spots;
- resolver questions;
- missing perspective analysis;
- historical-pattern analysis when applicable;
- a disposition for each item.

- [x] **Step 2: Bind P4 outputs into the common concern matrix**

Every material P4 issue must create or reference a `concern_id`. A resolver question requiring more evidence creates `new_retrieval`; a genuine unresolved scientific issue creates `preserved_as_uncertainty`; a scope exclusion requires an editor-approved reason.

- [x] **Step 3: Re-run STORM after revisions**

Re-review must answer both:

1. Did the revision close each prior concern?
2. Did the revision create a new contradiction, erase a perspective, weaken evidence, or overstate consensus?

The post-revision STORM audit binds the new report/evidence bundle hash. Copying the previous audit fails.

- [x] **Step 4: Route review findings back to the correct stage**

Map required actions deterministically:

```text
missing_source | blind_spot | resolver_question -> amend from retrieval
unsupported_claim | evidence_strength           -> amend from evidence
missing_perspective | synthesis_failure          -> amend from outline/draft
citation_or_wording                              -> revise draft
```

No review-only status change can close an issue that requires an upstream artifact change.

---

### Task 6: Prove Review Independence And Causal Revision

**Files:**
- Modify: `schemas/review-provenance.schema.json`
- Modify: `scripts/storm_research.py`
- Modify: `scripts/validate_package.py`
- Test: `tests/test_review_stage.py`
- Test: `tests/test_validate_package.py`

- [x] **Step 1: Add failing provenance tests**

Reject Max captured execution when:

- a reviewer shares the author context;
- panel reviewer contexts are reused;
- the editor shares a panel reviewer context;
- a review transcript segment does not hash to its provenance record;
- review begins before the immutable review request;
- a required revision leaves the complete review-subject hash unchanged;
- re-review occurs before the amendment/draft receipt.

- [x] **Step 2: Extend the existing provenance envelope**

Keep one `reviewer-transcript.txt`. Add per-session byte ranges and hashes so each reviewer and editor has a separately verifiable transcript segment:

```json
{
  "round_id": "RR002",
  "reviewer_role": "devils_advocate",
  "context_id": "ctx-da-002",
  "execution_id": "exec-da-002",
  "transcript_segment": {
    "start_byte": 4200,
    "end_byte": 7311,
    "sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
  }
}
```

- [x] **Step 3: Bind a complete review subject**

Compute `review_subject_sha256` over the canonical hashes of report, paragraph map, Claim ledger, source register, findings, contradiction/uncertainty ledgers, P2/P3/P4 artifacts, and retrieval saturation records. A prose revision must change the report hash. A retrieval/evidence revision must change the subject hash even if the report text legitimately remains unchanged.

- [x] **Step 4: Preserve artifact-only testing**

`artifact_contract` fixtures may use deterministic synthetic provenance but remain marked `validated_artifact_contract_only` and non-releasable. Formal Max delivery continues to require `captured_host_execution`.

---

### Task 7: Make Re-Review And Final Integrity Fail Closed

**Files:**
- Modify: `scripts/storm_research.py`
- Modify: `scripts/validate_evidence.py`
- Modify: `scripts/validate_package.py`
- Modify: `schemas/validation-report.schema.json`
- Test: `tests/test_evidence_validation.py`
- Test: `tests/test_review_stage.py`
- Test: `tests/test_validate_package.py`

- [x] **Step 1: Add failing closure tests**

Cover:

- an initial clean panel plus independent final-integrity pass succeeds without a fake revision;
- any concern starts a revision cycle;
- required action without changed upstream artifact fails;
- partial or unresolved major concern blocks delivery;
- preserved uncertainty passes only when the report states the same limitation and does not overclaim;
- final integrity checks 100% of material Claims and all body citations;
- a new re-review concern reopens the loop.

- [x] **Step 2: Replace round-count validation**

Validate states, not counts:

```text
panel_complete
  -> accept -> final_integrity
  -> minor/major/reject -> amend -> revise -> re_review
re_review
  -> accept -> final_integrity
  -> concern_opened -> amend -> revise -> re_review
final_integrity
  -> pass -> promotable
  -> fail -> concern_opened
```

- [x] **Step 3: Add deterministic final-integrity checks**

Recompute Claim-source closure, evidence ceilings, paragraph mappings, citation keys, format parity, P4/STORM dispositions, saturation records, review concern closure, and candidate hashes. The final editor cannot override these machine failures.

- [x] **Step 4: Record a blocked terminal state**

When the host stops before closure, status/explain reports `blocked_with_unresolved_issues` and lists the blocking concern/gap IDs. It must not render, collect, or release a final package.

---

### Task 8: Report Review Outcomes Without Polluting The Article

**Files:**
- Modify: `schemas/validation-report.schema.json`
- Modify: `scripts/validate_package.py`
- Modify: `scripts/storm_research.py`
- Modify: `references/export-workflow.md`
- Test: `tests/test_validate_package.py`
- Test: `tests/test_governed_release.py`

- [x] **Step 1: Add outcome-summary tests**

Require validation to report:

```json
{
  "review_outcomes": {
    "decision_path": ["major_revision", "minor_revision", "accept"],
    "concerns_opened": 12,
    "concerns_addressed": 9,
    "concerns_preserved_as_uncertainty": 3,
    "concerns_waived": 0,
    "retrieval_cycles_triggered": 2,
    "sources_added": 17,
    "claims_added": 3,
    "claims_downgraded": 4,
    "claims_removed": 2,
    "sections_revised": 3,
    "storm_conflicts_closed": 2,
    "storm_blind_spots_disclosed": 1,
    "final_integrity": "pass"
  }
}
```

Recompute all counts from ledgers and revision maps. Do not trust summary values submitted by the host.

- [x] **Step 2: Keep the public package clean**

The only report is the final `report.md` plus derived HTML/PDF. Internal review transcripts and matrices remain in the governed run/audit handoff and do not appear as article prose or inflate body length.

- [x] **Step 3: Preserve audit access**

Captured-host `collect` includes the validation outcome summary and references to internal audit artifacts. Public `release` includes only the approved report formats and validation report.

---

### Task 9: Update Documentation And Migration Semantics

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `agents/interface.yaml`
- Modify: `references/quality-gates.md`
- Modify: `references/research-protocol.md`
- Modify: `references/report-writing.md`
- Modify: `docs/migration-v3-to-v4.md`
- Modify: `CHANGELOG.md`
- Modify: `manifest.json` only if 4.0.0 has already been published
- Test: `tests/test_library_contract.py`

- [x] **Step 1: Remove all statements that Max requires 88 body-cited sources**

Replace them with coverage/saturation semantics. Explain explicitly that counts are metrics and cannot cause acceptance.

- [x] **Step 2: Document genuine review behavior**

Explain that STORM identifies conflicts, consensus, weak perspectives, resolver questions, and blind spots; the academic panel evaluates source integrity, methods, domain coverage, interdisciplinary perspective, and strongest counterargument; the editor routes concrete concerns; re-review verifies exact changes.

- [x] **Step 3: Keep the version boundary honest**

The current 4.0.0 changes are uncommitted in this worktree, so repair them before release without inventing a 5.0 label. If 4.0.0 has been externally published before implementation begins, bump the repaired contract and add an explicit migration note instead of silently changing a released schema.

- [x] **Step 4: Run documentation and interface tests**

```bash
.venv/bin/python -m unittest tests.test_library_contract tests.test_contracts -v
```

---

### Task 10: Full Verification And Isolated PBCT Acceptance

**Files:**
- Modify only failing implementation/tests/docs from Tasks 1-9.
- Do not reuse or overwrite previous PBCT run directories.

- [x] **Step 1: Run focused regression suites**

```bash
.venv/bin/python -m unittest \
  tests.test_contracts \
  tests.test_normalize_retrieval \
  tests.test_storm_research_cli \
  tests.test_evidence_stage \
  tests.test_evidence_validation \
  tests.test_review_stage \
  tests.test_validate_package \
  tests.test_governed_release \
  tests.test_library_contract -v
```

- [x] **Step 2: Run complete source and distribution checks**

```bash
.venv/bin/python scripts/run_checks.py --all
.venv/bin/python scripts/run_checks.py --dist
```

Expected: unit tests, compile, schemas, Yao validation, package validation, and platform adapters pass.

- [ ] **Step 3: Run a new captured-host PBCT Max study**

2026-07-06 acceptance attempt: a fresh copy of the verified distribution was unpacked to an
isolated temporary workspace and invoked with the exact natural-language request below. The
isolated Codex host returned a usage-limit error immediately after
`turn.started`, before creating research artifacts. Steps 3-5 therefore remain incomplete;
no earlier PBCT run was copied, modified, or relabeled as acceptance evidence.

2026-07-07 acceptance attempt: a fresh copy of the verified distribution was unpacked to
`/private/tmp/storm-pbct-max-acceptance.eDj0fA/storm-deepresearch-skill`, dependencies were
installed in that isolated copy, and the host was invoked with:

```text
使用 /private/tmp/storm-pbct-max-acceptance.eDj0fA/storm-deepresearch-skill 这个技能，以 Max 模式研究 proton boron capture therapy，默认输出中文。
```

The run selected `maximal_full_dossier`, `captured_host_execution`, `zh-CN`, and high-stakes
medical mode, then failed closed at `evidence` with
`state=blocked_with_unresolved_issues`. It exposed two repair gaps now addressed above:
small-source saturation still needed a closed terminal-gap domain review concern, and `explain`
should route blocked review recovery to `amend --resume-blocked-review` instead of same-generation
`retry evidence`.

2026-07-07 post-repair acceptance attempt: the newly verified distribution was unpacked to
`/private/tmp/storm-pbct-max-acceptance.xeP1GT/storm-deepresearch-skill`, dependencies were installed
in that isolated copy, and the same natural-language request was submitted. `codex exec` returned
the host usage-limit error before creating a run directory, brief, receipts, or research artifacts.
This does not validate or invalidate the repaired Max contract; it leaves Steps 3-5 incomplete.

2026-07-07 resumed acceptance attempt: after the usage limit recovered, a fresh distribution copy
was unpacked to `/private/tmp/storm-pbct-max-acceptance.NNh5MA/storm-deepresearch-skill` and invoked
with the same natural-language request. The host correctly selected `maximal_full_dossier`,
`captured_host_execution`, `zh-CN`, strict STORM lens, and high-stakes medical mode, but it never
completed retrieval. It repeatedly tried to manufacture a tiny bounded-corpus retrieval input and
failed closed before a retrieval receipt. The last observed blocker was that source-plan wording
`clinical trial registry` did not match actual `ClinicalTrials.gov registry`/`trial_registry`
evidence. This attempt exposed two additional harness defects that are now covered by tests and
implementation: registry-surface semantic normalization, and a hard requirement that
`bounded_corpus_exhausted` provide complete result-window enumeration plus access-limit disclosure.

2026-07-07 second resumed acceptance attempt: the distribution with archive SHA-256
`39d8a09ac982f95a390e92a00d5b5d7b3eebe63636e0bd42e594b366f73ed923` was unpacked to
`/private/tmp/storm-pbct-max-acceptance.dxp4bA/storm-deepresearch-skill`, dependencies were installed
in that isolated copy, and the same request was submitted. `codex exec` returned a usage-limit error
before any run directory or research artifact was created. This attempt is not acceptance evidence
for or against the repaired contract; it only confirms the latest package was ready to run and the
external host quota blocked execution.

2026-07-07 third resumed acceptance attempt: after the usage limit recovered, the current distribution
with archive SHA-256 `33b7b05a04e4c8f45a1c176235c31e01b4a28ca2ba733bd6e2ad5fe0c076035c`
was unpacked to `/private/tmp/storm-pbct-max-acceptance.rjaxMx/storm-deepresearch-skill`,
dependencies were installed, and the same request was submitted. The host correctly initialized
`maximal_full_dossier`, `captured_host_execution`, `zh-CN`, strict STORM lens, and high-stakes mode.
It fixed an initial invalid P1 artifact and then passed `plan`, leaving the governed run at
`state=planned`, `last_valid_stage=plan`, `next_stage=retrieval`. It performed web searches but did
not write `retrieval-audit.jsonl`, source register, findings, evidence, draft, review, render, or
validation receipts. Instead, it explicitly stated that it could not write network snapshots in the
current shell environment and returned a provisional topic report. This is an acceptance failure:
the harness did not falsely validate anything, but the host violated the blocked-run output contract
by summarizing topic findings before retrieval/validation. The package docs and library contract
were tightened after this attempt: blocked final answers may contain only `status`, failed stage,
`explain` reason, and next repair command, with no topic findings, citations, conclusions, or
provisional report.

2026-07-07 fourth resumed acceptance attempt: after the blocked-output repair and full checks, the
current distribution with archive SHA-256
`ef9e3b0f8bd492ce54d870ff706567ce193baa752e6dbf7a7c2909c3c5aafbc9` was unpacked to
`/private/tmp/storm-pbct-max-acceptance.0bHKtK/storm-deepresearch-skill`, dependencies were installed,
and the same request was submitted. The host correctly selected `maximal_full_dossier`,
`captured_host_execution`, `zh-CN`, strict STORM lens, and high-stakes medical planning. It passed
`lens-perspectives` and `plan`, then stopped at `retrieval` with `state=planned` and
`explain` reporting `retrieval has not been run`. Unlike the third attempt, the final user-facing
answer did not include PBCT topic findings, citations, conclusions, or a provisional report; it
only reported the run directory, completed stages, failed stage, and next repair step. This is a
positive acceptance result for the blocked-output contract, but it is still not a complete PBCT Max
study because no retrieval, findings, evidence, draft, review, render, or validation receipts were
created.

Use a fresh run and fresh host contexts. Do not copy prior PBCT sources, ledgers, drafts, review records, or transcripts. The natural-language request remains:

```text
使用这个技能，以 Max 模式研究 proton boron capture therapy，默认输出中文。
```

- [ ] **Step 4: Inspect observable acceptance evidence**

The run passes only when:

- profile routing selects `maximal_full_dossier` and `captured_host_execution`;
- Chinese is the resolved language;
- no source-count target appears in the brief, plan, or host instructions;
- all required discovery surfaces and medical aliases were actually searched;
- every open STORM gap has a recomputable terminal disposition;
- stopping is justified by material-novelty saturation or bounded-corpus evidence, not a round source count;
- panel reviewer and editor contexts are isolated;
- concerns cite exact targets and cause observable retrieval/evidence/report changes;
- re-review evaluates the new review-subject hash;
- final integrity verifies all material Claims and citations;
- the only promoted report is the final reviewed `report.md`, with matching HTML and PDF;
- validation summarizes what the review changed without inserting audit boilerplate into the article.

- [ ] **Step 5: Compare against the two failed behavioral signatures**

Fail acceptance if either occurs:

1. Retrieval stops immediately when a round number such as 80 or 88 is reached.
2. Review progresses from generic one-line comments to `accept` without specific concerns, changed artifacts, independent re-review, and a final-integrity pass.

## Rollback Boundary

- Old governed runs remain immutable and are interpreted by their original package hash.
- Do not rewrite previous PBCT receipts or relabel old runs as saturated/reviewed.
- If the repaired contract cannot validate, the new run remains non-deliverable; do not silently fall back to the old numeric Max gates.

## Completion Definition

This repair is complete only when all focused and full checks pass and the isolated PBCT acceptance demonstrates both properties:

1. Max stops because the research question space has been covered and material novelty has saturated, not because a counter reached a target.
2. Review findings are specific, independently produced, causally connected to revisions or new retrieval, re-reviewed against the changed subject, and closed by final integrity rather than a self-declared `accept`.
