# Quality Gates

Run `python3 scripts/run_checks.py --package OUTPUT_DIR`. A full package is releasable only when it exits zero.

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
- Full dossiers use at least five researched perspectives, ten questions, six evidence-planned sections, and twelve material claims unless the run is explicitly bounded and unreleased.

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
