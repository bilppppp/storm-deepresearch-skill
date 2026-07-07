---
name: storm-deepresearch-skill
description: Use for source-grounded deep research. Do not use for lookup.
---

# STORM DeepResearch

Ask research_profile/assurance_target. Every run starts with `scripts/storm_research.py init`; `run_checks.py` is not research validation. Default `default_full_dossier`; Max `maximal_full_dossier`. Zh `8000–10000`; use P1-P4, `report_outline`, academic baseline.

## Compact Workflow

`init`->`plan(report_outline)`->`ingest/findings/evidence`->`draft/P4/review`->`render/validate/release`.

## Decision Points

`maximal_full_dossier`: no source-count stopping target; close gaps by novelty/corpus/uncertainty. Max captured retrieval: typed records -> `retrieval-preflight` -> `retrieval-prepare` -> `ingest`.

`diagnostic_rehearsal`: test intent only. Use `init --run-intent diagnostic_rehearsal`; if retrieval gates fail, `ingest --allow-diagnostic-debt` may record `research/blocking-debt-ledger.json` and continue for observation. Never present diagnostic output as validated delivery; final validation/release must stay blocked.

## Output Contract

See references/output-path-policy.md.

## Failure Policy

Never reinitialize/truncate ledgers, invent evidence, edit receipts/hashes, or merge reviews. If blocked, use `status`/`explain`; never handwrite manual report/evidence dossier. Blocked final: status/stage/next; no topic findings.

For diagnostic runs, preserve `unreachable` and `access_limited_uncertainty` literally; do not rewrite them as `zero_results` or `saturated`.

## Resources

`scripts/run_checks.py`; `evals/`.
