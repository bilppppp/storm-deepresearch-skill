---
name: storm-deepresearch-skill
description: Use for source-grounded deep research, literature review, or complex reports that need STORM perspectives, academic retrieval, Claim-to-source traceability, evidence-method fit, independent review, and Markdown/HTML/PDF. Do not use for quick lookup, simple summarization, evidence-free role-play, or personalized professional advice.
---

# STORM DeepResearch

## Router Rules

- Vague `run ... research X`: ask `research_profile`; recommend `default_full_dossier` (strict P1-P4), not briefing.
- Full dossiers: strict P1-P4, external/human review provenance, no self-review.
- Full dossiers are deliverable only when `status.local_delivery_ready=true`; otherwise continue or report a concrete blocker.
- Preserve at least five genuinely different STORM perspectives; do not rename near-duplicates to satisfy the count.
- External full dossiers: run an academic baseline; corpus-seeded search cannot replace it.
- Ingest search runs, screened candidates, and captures; bind `retrieval-audit.jsonl` internally.
- Chinese full dossiers: `8000–10000` visible chars; citations/Markdown excluded.
- Absence claims need search ledgers; Claims cannot exceed capture ceilings.
- Fresh output path only; reject existing, escaping, symlink paths.
- Use `closed_corpus` for supplied material; otherwise host search. Stop on missing evidence.

## Evidence and Review Decisions

- Judge the concrete conclusion first: recorded fact, association, causal effect, generalization, inference, or recommendation.
- Compare that conclusion with source type, research method, sample, time, geography, capture level, and counterevidence. Tier, prestige, or source count cannot upgrade what a method can prove.
- Official material supports documented features, rules, and positions—not independent effectiveness. User accounts support individual experience—not prevalence. News supports that an event or claim was reported—not that the underlying claim is true.
- Observational evidence supports measured proportions or associations within scope—not causality. Experiments and reviews remain bounded by identification assumptions, measurements, follow-up, included studies, heterogeneity, and applicability.
- Unknown publication date or freshness is a non-blocking risk for semantic review. Do not require template disclaimers or `qualified` status. A known stale or unsuitable historical source cannot support an explicit current fact.
- Hard-fail fake or uncheckable evidence, unsupported material Claims, material citation mismatch, dangerous method overreach, known-stale evidence for current facts, and credential/path/network leakage.
- When evidence supports a narrower statement, warn and qualify, rewrite, remove, or add evidence. Every blocking finding must identify a concrete Claim, sentence, source, or dangerous output; never reject a source category wholesale.
- Give reviewers readable `review-context.md`, not hashes; it projects existing governed artifacts without creating a second authority system.

## Compact Workflow

1. `init` + `plan`: profile evidence, STORM tasklets, `report_outline`.
2. `ingest` + `findings` + `evidence`: close bibliography, gaps, sources, and Claims without exceeding capture or method limits.
3. `draft` + P4 + `review-prepare`: freeze and hand off to a separate model context or human; the author must not manufacture review provenance.
4. `review` + `render` + `validate` + `collect`: finish local delivery. Use `release` only for a public research package.

## Decision Points

- Input length changes retrieval, not depth; full dossiers cannot downgrade.
- `init` needs profile-selection evidence; `amend` creates a generation.
- Required evidence roles combine across the question and report; every Claim need not independently cover every role.
- Formal correctness is a safety floor. Report quality depends on answering the real question, non-obvious synthesis, mechanisms, conflicts, tradeoffs, action value, and honest uncertainty.

## Output Contract

Produce governed research, independent review, Markdown/HTML/PDF, and receipts; release only when requested. Follow [workflow](references/research-protocol.md), [gates](references/quality-gates.md), and [paths](references/output-path-policy.md).

## Failure Policy

- Never invent citations, metrics, or findings.
- Never reinitialize or truncate ledgers.
- Never edit receipts or validators to pass.
- Never mark P4 repairs applied without matching before/after hashes.
- Never write or copy files into harness-owned `current/`, or present `_build` files as final. Use `collect` only after validation.
- Evidence review blocks only key, material failures; warnings remain visible and non-blocking. Operational contract violations may still fail non-zero.
- Local render/validation and ordinary Git commits need no human release signature. Public research-package release needs Trust, registry, re-verification, and human approval.

## Resources

Evidence: [policy](references/source-and-evidence-policy.md). Lens: [prompts](references/storm-lens-prompt-pack.md). Check: `python3 scripts/run_checks.py --all`; dist: `python3 scripts/run_checks.py --dist`; cases: `evals/`.
