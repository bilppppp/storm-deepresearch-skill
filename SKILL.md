---
name: storm-deepresearch-skill
description: Use for source-grounded deep research with STORM questions, claim-evidence traceability, contradictions, uncertainty, governed receipts, and Markdown/HTML/PDF release. Trigger for reports, reviews, decision briefs, and supplied corpora. Do not use for quick lookup, unsupported role-play, simple summary, or short answers.
---

# STORM DeepResearch

Governed research harness: perspectives ask; ledgers authorize facts; receipts authorize progress.

## Router Rules

- Default Chinese dossiers to `8000–10000` body characters. Shorten only for a briefing or evidence boundary.
- Initialize a fresh workspace-scoped run; reject existing or escaping paths.
- Use `closed_corpus` for supplied-only material; otherwise approved host search. Avoid personalized high-stakes advice.
- Advance only through `scripts/storm_research.py`; root files are views, not proof.
- Stop on `missing evidence`, broken receipt chain, or absent approval.

## Compact Workflow

1. `init`: normalize brief and length; create generation `g0001`.
2. `plan`: generate STORM questions, source plan, and `report_outline`.
3. `ingest`: accept only approved retrieval records; memory is not evidence.
4. `evidence`: close source and Claim ledgers under [source](references/source-and-evidence-policy.md) and [claim](references/claim-evidence-policy.md) policy.
5. `draft` and `review`: bind paragraphs, citations, Claims, and semantic review.
6. `render`, `validate`, `release`: derive formats, verify gates, require Trust and approval.

## Decision Points

- Input length changes retrieval, not report depth; use `bounded_partial` instead of padding.
- Full dossiers cannot be amended to reduced output after render failure.
- `amend` creates a new generation. `retry`, `status`, and `explain` inspect receipts; they do not bypass them.

## Output Contract

Produce brief, source plan, ledgers, semantic review, Markdown, HTML, full-mode PDF, validation receipt, and allowlisted release. Follow [writing](references/report-writing.md), [export](references/export-workflow.md), [gates](references/quality-gates.md), and [output paths](references/output-path-policy.md).

## Failure Policy

- Never invent citations, quotations, or metrics.
- Never reinitialize or truncate ledgers; only derived artifacts are replaceable.
- Never edit receipts or validators to pass.
- Fail non-zero with repair details; release requires Yao Trust, registry match, re-verification, and approval.

## Resources

- Contracts live in `schemas/`, `references/`, and [output paths](references/output-path-policy.md); `scripts/` executes and `evals/` tests.
- Release only after `python3 scripts/run_checks.py --all` passes.
