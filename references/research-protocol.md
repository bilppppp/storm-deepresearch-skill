# Research Protocol

## Phase 0 — Normalize the brief
Create `brief.json`. Classify the user packet as thin, moderate, or rich. User material defines intent and angle; external research verifies, completes, updates, and challenges it. Lock language, depth, and `length_contract`. A short prompt does not authorize a short dossier; `briefing` depth requires an explicit user-request reason.

In 1.0, this is the `storm_research.py init` stage. The authoritative brief is `work/generations/g0001/inputs/brief.json`; root `brief.json` is a view. A changed view cannot advance the receipt chain.

## Phase 1 — Build a source plan
List expected source classes before searching. For each source class, define what it can and cannot prove.

Example:
- Official documentation can prove product behavior but not user satisfaction.
- Academic papers can prove study findings but may not generalize to current practice.
- News can prove reported events but may not prove causality.
- Community posts can reveal pain points but are anecdotal.

For full dossiers with external research allowed, source classes cannot be only user transcript, closed corpus, local files, or supplied materials. At least half of planned questions must require external source classes, and the retrieval budget must allow at least six external sources.

## Phase 2 — Generate perspectives
Use default perspectives as the seed, then adapt to the topic.

Default perspectives:
1. Practitioner
2. Academic/Scientist
3. Skeptic/Critic
4. Economist/Incentive Analyst
5. Historian/Comparativist

Optional perspectives:
- Regulator
- Engineer/Architect
- User/Customer
- Security reviewer
- Ethicist
- Operator
- Teacher
- Investor
- Local stakeholder
- Open-source maintainer

This operationalizes the article's first prompt. Perspectives are question generators, not sources. Do not ask an imagined persona to provide "its strongest evidence" from memory; retrieve evidence for the persona's questions.

## Phase 3 — Research through questions
For each perspective, generate at least two concrete research questions for a full dossier. Search for answers. Every question records `planned`, `answered`, `unresolved`, or `out_of_scope`; answered questions link claim IDs, while unresolved questions enter the uncertainty ledger.

For film reviews or essay prompts, do not search only the film's background page. Turn the user's concepts, comparisons, and named theorists into separate research questions, then retrieve sources that can actually prove or challenge those claims.

## Phase 4 — Create evidence map
Each key claim must be recorded with source IDs, confidence, strength, contradictions, and notes.

Evidence strength guidance:
- Strong: primary source, official data, high-quality peer-reviewed evidence, directly relevant.
- Medium: reputable secondary source, expert synthesis, credible but indirect.
- Weak: anecdote, single community report, dated source, unclear method.
- Unknown: plausible but not verified.

## Phase 5 — Map contradictions
Contradictions are not defects. They are research findings. Preserve them with context. This operationalizes the article's second prompt, but reject the shortcut "all perspectives agree, therefore true": consensus still needs evidence.

## Phase 6 — Build the synthesis outline
Complete `research-plan.report_outline` before prose. Allocate the full length budget across distinct sections. Each section must resolve named perspective questions, use material claim IDs, and specify evidence-led expansion elements. This is the article's third prompt turned into an auditable synthesis plan rather than a short briefing.

## Phase 7 — Peer review
Red-team the draft. Score finding confidence, identify the weakest link, check source and perspective dominance, add a missing perspective where useful, and record required revisions. This operationalizes the article's fourth prompt. Self-scores guide review; they are not evidence.

## Phase 8 — Export and validate
Generate final Markdown, HTML, and PDF-ready outputs. Run validation.

In governed runs, every phase after init maps to a stage receipt: `plan`, `ingest`, `evidence`, `draft`, `review`, `render`, `validate`, and optionally `release`. If any phase has missing evidence, do not continue to the next stage. Use `status`, `explain`, and `retry` to inspect the receipt chain; use `amend` only to create a new generation.
