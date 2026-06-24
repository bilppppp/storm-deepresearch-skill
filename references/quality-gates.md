# Quality Gates

Run `python3 scripts/storm_research.py validate "$RUN_DIR"` or `python3 scripts/run_checks.py --package "$RUN_DIR"`. A full package is releasable only when offline validation exits zero and writes `70-validation.json`.

## Contract gate: exit 4

- Required files and strict JSON/JSONL contracts exist.
- IDs, dates, enums, and package state are valid.
- Unknown fields are rejected.

## Evidence gate: exit 5

- At least one material claim exists.
- Material factual closure is 100%.
- Source and claim references close.
- Evidence locators exist.
- Current claims pass freshness policy.
- Contested claims retain contradicting evidence.
- No unsupported material claim reaches the report.
- Every perspective question has a disposition; every answered question is used by `report_outline`.
- Full external dossiers require `storm-tasklets`, `storm-findings-pool`, and `finding-coverage` before evidence; every material Claim must link to a usable finding that shares its supporting source.
- Full dossiers use at least five researched perspectives, ten questions, six evidence-planned sections, and twelve material claims unless the run is explicitly bounded and unreleased.

`storm_research.py evidence --preflight-theory --claims claims.jsonl` can be run after retrieval to list theory claims, matched terms, supporting source types, and missing theory-grade support. It does not write an evidence receipt or weaken the evidence gate.

## Export gate: exit 6

- Markdown and HTML titles and sections match.
- References exist in every public format.
- Render fingerprints match current files.
- Full-mode PDF exists, has pages, and contains title/reference text.
- No unresolved template marker remains.
- The public report body satisfies `brief.length_contract`; references do not count toward the total.
- Section budgets reach the promised length through claims, mechanisms, evidence, counterevidence, implications, and limits rather than repetition.

## Safety gate: exit 7

- Resolved run and package-child paths remain within the approved output root and research package.
- Symlinks cannot redirect exports, audit views, or validation reports outside the package.
- Public outputs contain no local paths.
- Public outputs do not expose internal source or claim IDs.
- Credentials and raw retrieval artifacts stay outside public outputs.

The validator writes JSON and Markdown reports only when the resolved `validation/` directory remains inside the package. The process returns the highest failed gate code; a failed required check cannot exit zero.

## Stage gate: exit 8

- The receipt chain must recompute from `00-init.json` through the required prior stage.
- Editing a receipt status, validator hash, or bound artifact invalidates the chain.
- `storm_lens_mode=strict` requires Prompt 1 before plan, Prompt 2 and Prompt 3 after findings and before evidence, and Prompt 4 after draft and before review.
- Strict STORM lens artifacts must be bound into the dependent stage receipts: P1 into plan, P2/P3 into evidence, and P4 into review.
- `retry` accepts only the current failed or pending stage.
- `amend` creates a new generation and cannot downgrade a full dossier to reduced output.
- `repair-plan` may write `current/repair-plan.json`, but it does not create or replace receipts.

## Release gate: exit 9

- Public release requires a passing Yao Trust report.
- Registry metadata and trust evidence must bind the current source-contract hash.
- Human approval must bind the validation receipt and be unexpired.
- Current claims past the freshness window need host re-verification.
- The release package must match the strict allowlist and contain no process artifacts.
