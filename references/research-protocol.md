# Research Protocol

## Phase 0 — Normalize the brief
Create `brief.json`. Classify the user packet as thin, moderate, or rich. User material defines intent and angle; external research verifies, completes, updates, and challenges it. Lock language, depth, and `length_contract.policy`. A short prompt does not authorize a short dossier; `briefing` depth requires an explicit user-request reason.

In 1.1, this is the `storm_research.py init` stage. The authoritative brief is `work/generations/g0001/inputs/brief.json`; root `brief.json` is a view. A changed view cannot advance the receipt chain.

`storm_lens_mode` defaults to `strict` for `default_full_dossier` and `critique_deepresearch`: Prompt 1, Prompt 2, Prompt 3, and Prompt 4 must produce phase-bound `storm-lens-*.json` artifacts before the dependent stage can advance. Use `advisory` only for explicit compatibility work or short briefing runs.

`research_profile` is the user-facing run preset. For vague "run this skill to research X" requests, offer complete deep research (recommended) or briefing before init. If the user does not choose or asks for the default, use `default_full_dossier`, which already enforces strict P1-P4; never infer `briefing` without explicit user request. `defaulted_after_prompt` requires the actual menu prompt as `--profile-prompt-file`; the prompt is copied into generation inputs and hash-bound in the brief. A skill directory name containing `maximal` is not a profile choice, but it is an ambiguity signal; ask before init rather than silently defaulting. `maximal_full_dossier` is an advanced profile only for explicit no-cap, no-budget, exhaustive, or "write as much as warranted" requests. It defaults `--language auto` to `zh-CN` and writes `maximal_completeness_contract` into the brief; the contract replaces body-length min/max with auditable depth gates. `strict_storm_lens` is a legacy CLI alias that new runs normalize to `default_full_dossier`, not a separate menu option. Use `critique_deepresearch` or `closed_corpus` as context-specific advanced profiles. `repair_existing_run` is not an init profile: inspect the existing run with `status` and `explain`, then repair or retry the failed stage.

`assurance_target` is independent from research depth and is also required at init. Use `artifact_contract` for deterministic fixtures and harness acceptance; it can prove schemas, ledgers, receipts, traceability, and rendering, but not real host execution. Use `captured_host_execution` for user delivery: `init` requires `--profile-selection-evidence-file` with the user selection transcript or equivalent host dialogue excerpt; `ingest` and `draft` require stage provenance plus substantive transcripts; review must use an isolated context. Validation calls this captured, not provider-signed. No profile automatically upgrades artifact evidence into captured execution.

## Phase 1 — Build a source plan
List expected source classes before searching. For each source class, define what it can and cannot prove.

Example:
- Official documentation can prove product behavior but not user satisfaction.
- Academic papers can prove study findings but may not generalize to current practice.
- News can prove reported events but may not prove causality.
- Community posts can reveal pain points but are anecdotal.

For full dossiers with external research allowed, source classes cannot be only user transcript, closed corpus, local files, or supplied materials. At least half of planned questions must require external source classes, and bounded profiles must allow at least six external sources. `maximal_full_dossier` uses an open-ended retrieval budget with no numeric ceiling or stopping quota. It plans domain-applicable discovery surfaces and mandatory counterevidence; source, candidate, tasklet, finding, Claim, section, and round counts are metrics only.

Each planned question defines aliases, required discovery surfaces, academic need, corpus-seeded status, and inclusion/exclusion criteria. Every external full dossier includes an academic baseline across at least two scholarly surfaces. A supplied corpus seeds terminology and candidate claims but never cancels the baseline. High-stakes medical Max runs must also plan PubMed or an equivalent literature database, ClinicalTrials or an equivalent registry, and at least three search aliases.

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

For film reviews or essay prompts, do not search only the film's background page. Turn the user's concepts, comparisons, and named theorists into separate research questions, then retrieve sources that can actually prove or challenge those claims.

In 1.1, `plan` automatically creates `research/storm-tasklets.jsonl`. After `ingest`, run `storm_research.py findings` to register `research/storm-findings-pool.jsonl` and `research/finding-coverage.json`. A full external dossier cannot advance to evidence unless every tasklet has a usable finding or an explicit uncertainty disposition. In Max, a `needs_more_evidence` finding requires later `search_wave` records and one `gap_assessment`; valid terminal states are material-novelty saturation, bounded-corpus exhaustion, access-limited uncertainty, or reasoned out-of-scope.

## Phase 4 — Create findings and evidence map
Findings are the bridge between retrieval and Claims. A finding must name the tasklet, source IDs, evidence locators, limitations, and candidate Claim IDs. Do not turn search snippets, model memory, or unsupported interpretation into findings.

Before findings, ingest a typed search audit: search runs, screened candidates, exact captures, and when Max is closing a gap, `search_wave` / `gap_assessment` records. The audit must cover every planned `required_surfaces` entry for the same query; missing planned databases, registries, publisher/full-text passes, or counterevidence surfaces fail. One response snapshot cannot be reused across different query IDs, surfaces, query strings, or aliases. Candidate screening cannot be all `include`; at least one excluded or needs-review candidate with a reason is required for external full dossiers. Included academic candidates must have resolver-backed bibliographic identity for every non-null DOI/PMID/arXiv/OpenAlex/Semantic Scholar identifier they declare. Max academic candidates require two independent matched resolvers, including OpenAlex or Semantic Scholar, plus the applicable identifier-native resolver. Every candidate marks whether it is the canonical version; duplicate identifiers or exact title/author/year identities cannot span families, and each multi-record family has one included canonical version. `abstract`, `metadata`, and `full_text` captures are distinct: abstract evidence is capped at medium and metadata at background. Version-family siblings become one source identity, and Claims must cite the capture that contains the located evidence. For Max captured retrieval, run `retrieval-preflight` on the JSONL, then `retrieval-prepare` to create hash-bound provenance and transcript binding, then `ingest`. `capture-source` and `ingest-dir` are partial capture helpers, not complete Max retrieval. The internal `retrieval-audit.jsonl` is receipt-bound and excluded from public release, but captured local `collect` projects it under `audit/` for handoff review.

Each key claim must be recorded with source IDs, confidence, strength, contradictions, and notes. Max never treats a source, candidate, finding, Claim, section, or review-round count as proof of completion. Every search wave binds executed queries plus `new_candidate_ids`, `new_source_ids`, `new_finding_ids`, `new_contradiction_ids`, `new_uncertainty_ids`, changed Claim IDs, and optional `material_delta`. Findings and final validation recompute those declarations; an existing source can still produce material novelty through a new finding, locator, contradiction, uncertainty, or Claim-strength/status change. Two independently executed zero-material-delta waves may close a gap as saturated, but every terminal gap disposition (`saturated`, `bounded_corpus_exhausted`, `access_limited_uncertainty`, or `out_of_scope`) must be closed by the domain reviewer in `review-loop.json`: either through a declared `review_concern_id` or a concern targeting `gap_assessment:GAxxx` / `gap:Gxxx`. A finite corpus may close below any source count only when all returned candidates are dispositioned, result/dedup counts recompute, and the domain reviewer accepts the terminal gap concern. Access limits require a bound uncertainty. Unused material remains in screening ledgers. Material Claims should state domain facts, inferences, limitations, or recommendations; "this source is an auditable record" is invalid report prose and an invalid Max material Claim.

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

In strict mode, register `research/storm-lens-outline.json` with `lens-outline` after `lens-conflicts` and before evidence. The evidence receipt must bind that artifact.

## Phase 7 — Peer review
Run the red-team prompt after `draft`. Score finding confidence, identify the weakest link, check source and perspective dominance, add a missing perspective where useful, and record required revisions. This operationalizes the article's fourth prompt. Self-scores guide review; they are not evidence.

Full dossiers require three explicit review tracks in addition to the base semantic review: fact checks for material Claims, conflict review for the contradiction ledger, and draft audit for paragraph assertions. These records must come from a captured external-model execution or human reviewer, not from self-attested string IDs. An isolated `codex exec`, Claude/OpenCode process, or human review context satisfies this role when provenance closes; the contract does not require the host framework's `spawn_agent` API.

In strict mode, register `research/storm-lens-red-team.json` with `lens-review` after draft. Close every repair action in `revision-map.json`, freeze the candidate with `review-prepare`, then hand the immutable request to external reviewers. Max uses `policy=concern_driven_until_clear`: source integrity, evidence/method, domain, interdisciplinary, devil's-advocate, and STORM synthesis reviewers bind package-derived role rubrics and isolated contexts; a separate editor computes the decision from exact concerns. Every P4 repair action enters the common concern matrix. Each concern declares an `issue_type` and deterministic `required_stage`; a review-only status cannot close an issue that requires retrieval, evidence, or draft changes. `preserved_as_uncertainty` requires an uncertainty-ledger ID and an existing paragraph/Claim report binding. Bounded-corpus and out-of-scope assessments require domain-reviewer acceptance.

Every round binds `generation`, draft receipt, review request, complete review-subject manifest, round digest, and current-generation transcript sessions. Re-review must produce a new subject and a new STORM audit; copying the previous audit fails. A clean first panel may accept, but still needs separate final integrity. A blocking round writes an immutable review blocker and exits non-zero; create the next generation with `amend --resume-blocked-review`. `status`/`explain` report blocker IDs and routed stages. There is no hidden loop and no same-generation multi-round shortcut.

Material absence claims require an `absence-search-ledger.jsonl`. Full dossiers use at least two discovery surfaces; high-stakes medical absence claims also require a trial registry, bibliographic database, and at least three aliases. Closed-corpus runs may only claim absence inside the supplied corpus.

## Phase 8 — Export and validate
Generate final Markdown, HTML, and PDF-ready outputs. Run validation.

In governed runs, every major phase after init maps to a stage receipt: `plan`, `ingest`, `evidence`, `draft`, `review`, `render`, `validate`, and optionally `release`. `findings`, `lens-perspectives`, `lens-conflicts`, `lens-outline`, `lens-review`, `review-prepare`, and `repair-plan` are governed helper commands. Harness-owned timestamps and strictly increasing receipts prove phase causality. If any phase has missing evidence, do not continue to the next stage. Use `status`, `explain`, `repair-plan`, and `retry` to inspect or repair the chain; use `amend --changes-json` for an approved brief change and `amend --resume-blocked-review` for a blocker-bound review cycle. If the run remains blocked, the final user-facing answer must be a status handoff only and must not summarize topic findings, citations, conclusions, or a provisional report.

For `captured_host_execution`, retrieval and draft provenance bind provider/model/runner, context and execution IDs, a non-zero causal time window, transcript hash, submitted inputs, produced outputs, and governed record IDs. Final validation recomputes those hashes and requires retrieval -> draft -> isolated review ordering. Max additionally rejects reuse of the same execution/context across all three phases; all external full dossiers reject all-include candidate pools. Runtime duration and token usage are observations, not proof and not pass criteria.
