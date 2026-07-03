---
name: storm-deepresearch-skill
description: Use for source-grounded deep research with STORM findings, ledgers, receipts, and Markdown/HTML/PDF. Do not use for lookup.
---

# STORM DeepResearch

## Router Rules

- Vague `run ... research X`: ask `research_profile`; recommend `default_full_dossier` (strict P1-P4), not briefing.
- Full dossiers: strict P1-P4, external/human review provenance, no self-review.
- External full dossiers: run an academic baseline; corpus-seeded search cannot replace it.
- Ingest search runs, screened candidates, and captures; bind `retrieval-audit.jsonl` internally.
- Chinese full dossiers: `8000–10000` visible chars; citations/Markdown excluded.
- Absence claims need search ledgers; Claims cannot exceed capture ceilings.
- Fresh output path only; reject existing, escaping, symlink paths.
- Use `closed_corpus` for supplied material; otherwise host search. Stop on missing evidence.

## Compact Workflow

1. `init` + `plan`: profile evidence, STORM tasklets, `report_outline`.
2. `ingest` + `findings` + `evidence`: verify bibliography, close gaps, sources, and Claims.
3. `draft` + P4 + `review-prepare` + `review`: close repairs and external review.
4. `render` + `validate` + `release`: derive formats; require Trust and approval.

## Decision Points

- Input length changes retrieval, not depth; full dossiers cannot downgrade.
- `init` needs profile-selection evidence; `amend` creates a generation.

## Output Contract

Produce plans, findings, ledgers, review, Markdown/HTML/PDF, receipts, and release. Follow [workflow](references/research-protocol.md), [gates](references/quality-gates.md), and [paths](references/output-path-policy.md).

## Failure Policy

- Never invent citations, metrics, or findings.
- Never reinitialize or truncate ledgers.
- Never edit receipts or validators to pass.
- Never mark P4 repairs applied without matching before/after hashes.
- Fail non-zero; release needs Trust, registry, re-verification, human approval.

## Resources

Lens: [prompts](references/storm-lens-prompt-pack.md). Check: `python3 scripts/run_checks.py --all`; dist: `python3 scripts/run_checks.py --dist`; cases: `evals/`.
