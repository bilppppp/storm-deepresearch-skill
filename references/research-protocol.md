# Research Protocol

## Phase 0 — Normalize the brief
Create `brief.json`. Classify the user packet as thin, moderate, or rich. User material defines intent and angle; external research verifies, completes, updates, and challenges it. Lock language, depth, and `length_contract`. A short prompt does not authorize a short dossier; `briefing` depth requires an explicit user-request reason.

In 1.1, this is the `storm_research.py init` stage. The authoritative brief is `work/generations/g0001/inputs/brief.json`; root `brief.json` is a view. A changed view cannot advance the receipt chain.

`storm_lens_mode` defaults to `strict` for `default_full_dossier` and `critique_deepresearch`: Prompt 1, Prompt 2, Prompt 3, and Prompt 4 must produce phase-bound `storm-lens-*.json` artifacts before the dependent stage can advance. Use `advisory` only for explicit compatibility work or short briefing runs.

`research_profile` is the user-facing run preset. For vague "run this skill to research X" requests, offer complete deep research (recommended) or briefing before init. If the user does not choose or asks for the default, use `default_full_dossier`, which already enforces strict P1-P4; never infer `briefing` without explicit user request. `strict_storm_lens` is a legacy CLI alias that new runs normalize to `default_full_dossier`, not a separate menu option. Use `critique_deepresearch` or `closed_corpus` as context-specific advanced profiles. `repair_existing_run` is not an init profile: inspect the existing run with `status` and `explain`, then repair or retry the failed stage.

## Phase 1 — Build a source plan
List expected source classes before searching. For each source class, define what it can and cannot prove.

Example:
- Official documentation can prove product behavior but not user satisfaction.
- Academic papers can prove study findings but may not generalize to current practice.
- News can prove reported events but may not prove causality.
- Community posts can reveal pain points but are anecdotal.

For full dossiers with external research allowed, source classes cannot be only user transcript, closed corpus, local files, or supplied materials. At least half of planned questions must require external source classes, and the retrieval budget must allow at least six external sources.

Each planned question defines aliases, required discovery surfaces, academic need, corpus-seeded status, and inclusion/exclusion criteria. Every external full dossier includes an academic baseline across at least two scholarly surfaces. A supplied corpus seeds terminology and candidate claims but never cancels the baseline.

For `critique_deepresearch`, the source plan must cover six search dimensions before tasklets can be generated: user claim extraction, supporting evidence, counterevidence or contradiction, theory/framework, reception or criticism, and historical comparison or blind spot. A plan that only searches background pages is invalid.

## Phase 2 — Generate perspectives
Use the STORM lens prompts in [storm-lens-prompt-pack.md](storm-lens-prompt-pack.md) as the seed, then adapt to the topic.

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

In strict mode, register `research/storm-lens-perspectives.json` with `lens-perspectives` before `plan`. The plan receipt must bind that artifact.

## Phase 3 — Research through tasklets
For each perspective, generate at least two concrete research questions for a full dossier. Search for answers. Every question records `planned`, `answered`, `unresolved`, or `out_of_scope`; answered questions link claim IDs, while unresolved questions enter the uncertainty ledger.

Use the host, provider, and closed-corpus boundaries in [Retrieval Adapters](retrieval-adapters.md). Search snippets identify candidates but cannot close material Claims; bundled scripts do not initiate research network requests.

For film reviews or essay prompts, do not search only the film's background page. Turn the user's concepts, comparisons, and named theorists into separate research questions, then retrieve sources that can actually prove or challenge those claims.

In 1.1, `plan` automatically creates `research/storm-tasklets.jsonl`. After `ingest`, run `storm_research.py findings` to register `research/storm-findings-pool.jsonl` and `research/finding-coverage.json`. A full external dossier cannot advance to evidence unless every tasklet has at least one usable finding. A `needs_more_evidence` finding requires a later gap-fill search; if it remains unresolved, bind its tasklet to exactly one uncertainty record.

## Phase 4 — Create findings and evidence map
Findings are the bridge between retrieval and Claims. A finding must name the tasklet, source IDs, evidence locators, limitations, and candidate Claim IDs. Do not turn search snippets, model memory, or unsupported interpretation into findings.

Before findings, ingest a typed search audit: search runs, screened candidates, and exact captures. Academic candidates must have resolver-backed bibliographic identity. Version-family siblings are one independent work, and Claims must cite the captured version that actually contains the located evidence. The internal `retrieval-audit.jsonl` is receipt-bound and excluded from public release.

Each key claim must be recorded with source IDs, confidence, strength, contradictions, and notes.

Evidence strength guidance:
- Strong: primary source, official data, high-quality peer-reviewed evidence, directly relevant.
- Medium: reputable secondary source, expert synthesis, credible but indirect.
- Weak: anecdote, single community report, dated source, unclear method.
- Unknown: plausible but not verified.

## Phase 5 — Map contradictions
Run the evidence-grounded contradiction prompt from [storm-lens-prompt-pack.md](storm-lens-prompt-pack.md) after first findings. Contradictions are not defects. They are research findings. Preserve them with context. This operationalizes the article's second prompt, but reject the shortcut "all perspectives agree, therefore true": consensus still needs evidence.

In strict mode, register `research/storm-lens-conflicts.json` with `lens-conflicts` after findings and before evidence. The evidence receipt must bind that artifact.

Every blind spot and resolver question must have a `resolution_action`. `new_retrieval` stops Prompt 3 and requires a new generation; `uncertainty` must bind the uncertainty ledger; `out_of_scope` requires a reason. A resolver question cannot be acknowledged and then ignored.

## Phase 6 — Build the synthesis outline
Run the synthesis outline prompt only after findings, contradiction mapping, and any resolver search. Complete `research-plan.report_outline` before prose. Allocate the full length budget across distinct sections. Each section must resolve named perspective questions, use material claim IDs, and specify evidence-led expansion elements. This is the article's third prompt turned into an auditable synthesis plan rather than a short briefing.

Draft sections with the evidence-led expansion, length, confidence, and recommendation rules in [Report Writing Rules](report-writing.md). Those rules protect depth without using repetition, oversized quotation, or source lists as padding.

In strict mode, register `research/storm-lens-outline.json` with `lens-outline` after `lens-conflicts` and before evidence. The evidence receipt must bind that artifact.

## Phase 7 — Peer review
Run the red-team prompt after `draft`. Score finding confidence, identify the weakest link, check source and perspective dominance, add a missing perspective where useful, and record required revisions. This operationalizes the article's fourth prompt. Self-scores guide review; they are not evidence.

Full dossiers require three explicit review tracks in addition to the base semantic review: fact checks for material Claims, conflict review for the contradiction ledger, and draft audit for paragraph assertions. These records must come from a captured external-model execution or human reviewer, not from self-attested string IDs.

In strict mode, register `research/storm-lens-red-team.json` with `lens-review` after draft. Close every repair action in `revision-map.json`, freeze the candidate with `review-prepare`, then hand the immutable request to the external reviewer. The review receipt binds P4, the candidate, request, provenance, transcript, and final review artifacts.

Material absence claims require an `absence-search-ledger.jsonl`. Full dossiers use at least two discovery surfaces; high-stakes medical absence claims also require a trial registry, bibliographic database, and at least three aliases. Closed-corpus runs may only claim absence inside the supplied corpus.

## Phase 8 — Export and validate
Generate final Markdown, HTML, and PDF-ready outputs. Run validation.

Follow [Export Workflow](export-workflow.md) for renderer dependencies, reduced-output boundaries, render-manifest checks, and local `collect` handoff.

In governed runs, every major phase after init maps to a stage receipt: `plan`, `ingest`, `evidence`, `draft`, `review`, `render`, `validate`, and optionally `release`. `findings`, `lens-perspectives`, `lens-conflicts`, `lens-outline`, `lens-review`, `review-prepare`, and `repair-plan` are governed helper commands. Harness-owned timestamps and strictly increasing receipts prove phase causality. If any phase has missing evidence, do not continue to the next stage. Use `status`, `explain`, `repair-plan`, and `retry` to inspect or repair the chain; use `amend` only to create a new generation.
