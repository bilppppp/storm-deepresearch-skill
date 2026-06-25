---
name: storm-deepresearch-skill
description: Use for source-grounded deep research with STORM tasklets, findings, claim ledgers, receipts, and Markdown/HTML/PDF release. Trigger for dossiers, reviews, and corpora. Do not use for lookup, role-play, summary, or short answers.
---

# STORM DeepResearch

## Router Rules

- Vague `run ... research X`: ask one `research_profile` choice; default `default_full_dossier`, not `briefing`.
- Chinese full dossiers: `8000–10000` body chars; `briefing` must be explicit.
- Initialize a fresh safe output path; reject existing, escaping, or symlinked targets.
- Use `closed_corpus` for supplied material; otherwise use approved host search.
- Run `scripts/storm_research.py`; stop on missing findings/evidence, broken receipts, or approval.

## Compact Workflow

1. `init`: normalize brief and create generation `g0001`.
2. `plan`: generate STORM questions, source plan, tasklets, and `report_outline`.
3. `ingest` + `findings`: accept retrieval records; register usable discoveries before Claims close.
4. `evidence`: close source and Claim ledgers under [source](references/source-and-evidence-policy.md) and [claim](references/claim-evidence-policy.md) policy.
5. `draft` + `review`: bind paragraphs, citations, Claims, fact checks, conflict review, draft audit, and semantic review.
6. `render` + `validate` + `release`: derive formats, use `repair-plan` on failure, then require Trust and approval.

## Decision Points

- Input length changes retrieval, not report depth; use `bounded_partial`, not padding.
- Full dossiers cannot be downgraded to reduced output after render failure.
- `amend` creates a new generation; `retry`, `status`, and `explain` inspect receipts.

## Output Contract

Produce brief, plans, tasklets, findings, ledgers, review, Markdown, HTML, full-mode PDF, validation receipt, optional repair plan, and allowlisted release. Follow [workflow](references/research-protocol.md), [writing](references/report-writing.md), [export](references/export-workflow.md), [gates](references/quality-gates.md), and [output paths](references/output-path-policy.md).

## Failure Policy

- Never invent citations, quotes, metrics, or full-dossier findings.
- Never reinitialize or truncate ledgers; only derived artifacts are replaceable.
- Never edit receipts or validators to pass.
- Fail non-zero with repair details; release requires Yao Trust, registry match, re-verification, and approval.

## Resources

Lens: [prompts](references/storm-lens-prompt-pack.md). Check: `python3 scripts/run_checks.py --all`; cases: `evals/`.
