---
name: storm-deepresearch-skill
description: Use for source-grounded deep research with STORM findings, ledgers, receipts, and Markdown/HTML/PDF. Do not use for lookup.
---

# STORM DeepResearch

## Router Rules

- Vague `run ... research X`: ask `research_profile`; default `default_full_dossier`, not `briefing`.
- Full dossiers require strict P1/P2/P3/P4 lens artifacts.
- Chinese full dossiers: `8000–10000` net body chars; bibliography/source sections excluded; `briefing` must be explicit.
- Fresh output path only; reject existing, escaping, symlink paths.
- Use `closed_corpus` for supplied material; otherwise host search.
- Run `scripts/storm_research.py`; stop on missing evidence.

## Compact Workflow

1. `init`: enforce profile evidence; create `g0001`.
2. `plan`: STORM questions, source plan, tasklets, `report_outline`.
3. `ingest` + `findings`: register retrieval before Claims.
4. `evidence`: close source and Claim ledgers.
5. `draft` + `review`: bind paragraphs, citations, Claims, checks, conflicts.
6. `render` + `validate` + `release`: derive formats; release needs Trust and approval.

## Decision Points

- Input length changes retrieval, not report depth.
- Full dossiers cannot downgrade after render failure.
- `init` fails without `--profile-selection-mode` and `--profile-selection-evidence`.
- `amend` creates a generation; `retry`/`status`/`explain` inspect.

## Output Contract

Produce brief, plans, tasklets, findings, ledgers, review, Markdown, HTML, PDF, validation receipt, repair plan, and allowlisted release. Follow [workflow](references/research-protocol.md), [writing](references/report-writing.md), [export](references/export-workflow.md), [gates](references/quality-gates.md), [paths](references/output-path-policy.md).

## Failure Policy

- Never invent citations, quotes, metrics, or full-dossier findings.
- Never reinitialize or truncate ledgers.
- Never edit receipts or validators to pass.
- Fail non-zero with repair details; release needs Trust, registry match, re-verification, approval.

## Resources

Lens: [prompts](references/storm-lens-prompt-pack.md). Check: `python3 scripts/run_checks.py --all`; dist: `python3 scripts/run_checks.py --dist`; cases: `evals/`.
