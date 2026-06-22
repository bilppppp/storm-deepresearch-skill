---
name: storm-deepresearch-skill
description: Use for source-grounded deep research that needs multi-perspective question generation, claim-evidence traceability, contradiction and uncertainty handling, and validated Markdown, HTML, and PDF deliverables. Trigger for research reports, literature or industry reviews, decision briefs, and supplied document or URL corpora where factual reliability matters. Do not use for quick lookup, unsupported expert role-play, simple summarization, or short-answer tasks.
---

# STORM DeepResearch

Build auditable research. Perspectives ask; ledgers authorize facts.

## Router Rules

- Default Chinese dossiers to `8000–10000` body characters. Shorten only for a briefing or evidence boundary.
- Initialize a fresh workspace-scoped run; reject existing or escaping paths.
- Use `closed_corpus` for supplied-only material; otherwise approved host search. For high-stakes topics, avoid personalized advice.

## Compact Workflow

1. Normalize the brief and lock `length_contract`.
2. Generate questions with the [protocol](references/research-protocol.md) and [STORM mapping](references/storm-workflow-mapping.md).
3. Retrieve through an approved [adapter](references/retrieval-adapters.md); memory is not evidence.
4. Merge ledgers monotonically; close claims under the [source](references/source-and-evidence-policy.md) and [claim](references/claim-evidence-policy.md) policies.
5. Preserve contradictions and unknowns.
6. Map every answered question and material claim into `report_outline`.
7. Draft `report.md`, review, export, and validate.

## Decision Points

- Provider retrieval is opt-in; credentials stay in environment variables.
- Seek independent support for contested claims. Input length changes retrieval, not report depth; use `bounded_partial` instead of padding.
- PDF omission requires reduced mode.

## Output Contract

Produce the brief, outline, ledgers, review, Markdown, HTML, full-mode PDF, and validation. Follow [writing](references/report-writing.md), [export](references/export-workflow.md), and [gates](references/quality-gates.md).

## Failure Policy

- Never invent citations, quotations, or metrics.
- Never reinitialize or truncate ledgers; only derived artifacts are replaceable.
- Fail gates non-zero with repair details.

## Resources

- Contracts live in `schemas/`, `references/`, and [output paths](references/output-path-policy.md); `scripts/` executes and `evals/` tests them.
- Release only after `python3 scripts/run_checks.py --all` passes.
