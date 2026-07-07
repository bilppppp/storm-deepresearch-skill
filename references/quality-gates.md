# Quality Gates

Run `python3 scripts/storm_research.py validate "$RUN_DIR"` or `python3 scripts/run_checks.py --package "$RUN_DIR"`. A full package is releasable only when offline validation exits zero and writes `70-validation.json`.

Every user-facing run must begin with `storm_research.py init`. A manual report or evidence dossier is not a valid skill run, and `run_checks.py is not research validation`: it checks the skill implementation, not a research package. Missing network snapshots, captured provenance, review evidence, or receipt chain must stop as blocked/non-zero instead of producing public Markdown/HTML/PDF. A blocked final answer is a status handoff only: include the current `status`, failed stage, `explain` reason, and next repair command; do not include topic findings, citations, conclusions, or a provisional report.

## Contract gate: exit 4

- Required files and strict JSON/JSONL contracts exist.
- IDs, dates, enums, and package state are valid.
- Unknown fields are rejected.
- `defaulted_after_prompt` must bind the actual user-facing profile prompt file; a text claim that a menu was shown is insufficient.
- `captured_host_execution` must bind `--profile-selection-evidence-file` into `brief.profile_selection.evidence_ref/evidence_sha256`; a free-text profile evidence string alone is artifact-only quality, not delivery proof.

## Evidence gate: exit 5

- At least one material claim exists.
- Material factual closure is 100%.
- Source and claim references close.
- A Claim cannot declare stronger evidence than its bound retrieval capture; inference and recommendation strength cannot exceed their weakest premise.
- Evidence locators exist.
- Source helpers reject bad captures by default, including common anti-bot, access-denied, loading-only, and too-short snapshots.
- Current claims pass freshness policy.
- Contested claims retain contradicting evidence.
- No unsupported material claim reaches the report.
- Every perspective question has a disposition; every answered question is used by `report_outline`.
- Full external dossiers require `storm-tasklets`, `storm-findings-pool`, and `finding-coverage` before evidence; every material Claim must link to a usable finding that shares its supporting source.
- External full dossiers pass an academic baseline across at least two scholarly surfaces; briefings verify every academic source they cite.
- `retrieval-audit.jsonl` closes search runs, planned source-plan surfaces for each query, non-all-include candidate screening, resolver snapshots for every declared included academic identifier, canonical version families, and exact captures. A response snapshot reused across different executed queries fails. Max academic candidates require two matched independent resolvers including OpenAlex or Semantic Scholar and the applicable identifier-native resolver. Duplicate bibliographic identities split across families fail.
- Capture semantics are enforced: `abstract` cannot exceed medium evidence, `metadata` must remain background, and abstract/title locators cannot be labelled `full_text`.
- Every Max material Claim must bind at least one matching abstract, full-text, official-data, or user-file capture; title metadata and search snippets cannot close a material Claim.
- Corpus-seeded questions still run the baseline; `needs_more_evidence` findings require gap-fill or an explicit uncertainty disposition.
- Zero-result, unmatched, and unreachable records remain distinct and cannot directly close questions or prove absence. A captured host must not convert an unreachable endpoint into a zero-result search to satisfy a gate; access limits close only through `access_limited_uncertainty` with a bound uncertainty.
- `critique_deepresearch` source plans must cover user claim extraction, supporting evidence, counterevidence or contradiction, theory/framework, reception or criticism, and historical comparison or blind spot before `plan` can commit.
- Full dossiers use at least five researched perspectives, ten questions, six evidence-planned sections, and twelve material claims unless the run is explicitly bounded and unreleased.
- `maximal_full_dossier` replaces numeric floors with relational closure. Every P1 tasklet, material assertion, planned section, P2 blind spot, and resolver question must end in evidence, uncertainty, or approved scope disposition. `search_wave` declares candidate/source/finding/contradiction/uncertainty/Claim deltas; findings and final validation recompute them before `gap_assessment` may prove saturation. Retrieval input may leave `material_delta` and `review_concern_id` unknown; final validation requires every terminal gap assessment to be accepted by the domain reviewer through either a declared review concern ID or a `gap_assessment` / `gap` target in `review-loop.json`. Counts remain visible metrics and never cause acceptance.
- High-stakes medical `maximal_full_dossier` runs require a literature database, a trial registry, and at least three search aliases.
- Material absence claims require a bound search audit; high-stakes medical absence claims cover aliases, a trial registry, and a bibliographic database.

`storm_research.py evidence --preflight-theory --claims claims.jsonl` can be run after retrieval to list theory claims, matched terms, supporting source types, and missing theory-grade support. It does not write an evidence receipt or weaken the evidence gate.

## Export gate: exit 6

- Markdown and HTML titles and sections match.
- References exist in every public format.
- Render fingerprints match current files.
- Full-mode PDF exists, has pages, and contains title/reference text.
- No unresolved template marker remains.
- For `length_contract.policy=bounded`, the public report net body satisfies `brief.length_contract`; bibliography, footnote keys, link destinations, image markers, and Markdown syntax do not count. For `open_ended`, validation records raw, citation-marker, and net counts but does not enforce min/target/max.
- Markdown blockquotes and fenced code are excluded from `report-depth`; oversized quoted blocks fail when they exceed both the absolute quote limit and 25% of countable body length.
- Section budgets reach the promised length or open-ended depth through claims, mechanisms, evidence, counterevidence, implications, and limits rather than repetition.

## Safety gate: exit 7

- Resolved run and package-child paths remain within the approved output root and research package.
- Symlinks cannot redirect exports, audit views, or validation reports outside the package.
- Public outputs contain no local paths.
- Public outputs do not expose internal source or claim IDs.
- Credentials and raw retrieval artifacts stay outside public outputs.

The validator writes JSON and Markdown reports only when the resolved `validation/` directory remains inside the package. The process returns the highest failed gate code; a failed required check cannot exit zero.

## Stage gate: exit 8

- The receipt chain must recompute from `00-init.json` through the required prior stage.
- Editing a receipt status, validator hash, or bound artifact invalidates the chain.
- `storm_lens_mode=strict` requires Prompt 1 before plan, Prompt 2 and Prompt 3 after findings and before evidence, and Prompt 4 after draft and before review.
- Strict STORM lens artifacts must be bound into the dependent stage receipts: P1 into plan, P2/P3 into evidence, and P4 into review.
- P2 must dispose every blind spot/resolver; `new_retrieval` prevents P3/evidence.
- P4 repair actions must close through before/after hashes in the revision map.
- Full dossiers require a frozen review request and captured external-model or human provenance; self-review and same-context review fail.
- `maximal_full_dossier` requires `research/review-loop.json` with `policy=concern_driven_until_clear`, package-bound role rubrics, six isolated panel roles including STORM synthesis, a separate editor, exact concern targets and routed stages, P4 action links, revision-map hashes, required re-review, final `accept`, zero unresolved concerns, and final integrity. Every STORM category has an explicit disposition. Rounds bind distinct increasing generations, draft receipts, review requests, subject manifests, immutable blocker receipts when revised, and per-round transcript sessions. A round count or summary string cannot pass Max.
- Receipt, retrieval, finding, lens, and review timestamps must remain inside their causal stage windows.
- `captured_host_execution` requires receipt-bound retrieval and draft provenance/transcripts plus isolated review provenance. Input/output hashes, record IDs, execution IDs, contexts, transcripts, and causal windows are recomputed.
- External full dossiers reject all-include candidate pools. Max captured runs also reject reuse of one execution/context across retrieval, draft, and review. No minimum runtime or token-spend heuristic is used.
- `retry` accepts only the current failed or pending stage.
- `amend --changes-json` creates an approved brief generation; `amend --resume-blocked-review` binds the immutable blocker and routes the next generation to the earliest required upstream stage. Neither can downgrade a full dossier to reduced output.
- `repair-plan` may write `current/repair-plan.json`, but it does not create or replace receipts.

## Release gate: exit 9

- Public release requires a passing Yao Trust report.
- Public release requires `assurance_level=validated_captured_host_execution`; artifact-contract validation is insufficient.
- Registry metadata and trust evidence must bind the current source-contract hash.
- Human approval must bind the validation receipt and be unexpired.
- Current claims past the freshness window need host re-verification.
- The release package must match the strict allowlist and contain no process artifacts.
