# Changelog

## Unreleased

- Added `retrieval-preflight` and `retrieval-prepare` so Max captured runs can validate typed retrieval JSONL and generate matching execution provenance before `ingest`.
- Made helper output honest: `capture-source` and `ingest-dir` now warn that they are partial capture builders and insufficient for Max captured retrieval by themselves.
- Deferred terminal gap review binding from retrieval input to review/final validation; `search_wave.material_delta` may be null before findings and is recomputed later.
- Repaired `maximal_full_dossier` so source, candidate, tasklet, finding, Claim, section, and review-round counts are metrics rather than stopping targets. Max now closes on tasklet/STORM-gap coverage plus recomputable material-novelty saturation, bounded-corpus exhaustion, access-limited uncertainty, or approved scope disposition.
- Replaced review-shaped Max JSON with a concern-driven STORM plus academic panel: isolated role contexts, separate editor synthesis, P4 action links, causal revision-map closure, required re-review after real concerns, and final integrity. Public report prose still rejects source-register narration such as `这条可审计来源是...`.
- Bound every Max review round to a distinct generation, draft receipt, review request, complete subject manifest, package-derived role rubric, round digest, and transcript session. Blocking review now writes an immutable blocker and resumes only through `amend --resume-blocked-review`.
- Expanded Max material-novelty recomputation across sources, findings, contradictions, uncertainties, and Claim changes; bounded-corpus closure now requires domain-reviewer acceptance.
- Added root-level validation `review_outcomes` recomputed from generation ledgers and revision maps without adding audit narration to the report.
- Split research depth from validation assurance with required `artifact_contract` and `captured_host_execution` targets.
- Added receipt-bound retrieval/draft execution provenance, causal transcript and context checks, explicit validation assurance levels, artifact-only collect override, and captured-only public release.
- Tightened profile intake and academic retrieval audit: `defaulted_after_prompt` now requires a hash-bound prompt artifact; external full dossiers must cover source-plan required surfaces, include non-all-include screening decisions, and resolver-check every declared included academic identifier. Captured local collect now includes an `audit/` bundle for handoff review.
- Closed Max threshold-gaming paths: different query executions cannot reuse one response snapshot; Max academic candidates require cross-index resolution; duplicate bibliographic identities must share a canonical version family; and abstract/metadata captures can no longer be labelled as full text.

## 4.0.0 - 2026-07-03

### Added

- `maximal_full_dossier` advanced profile for explicit no-cap or exhaustive research requests.
- `length_contract.policy` with `bounded` and `open_ended` modes.
- `report_depth.policy` in validation reports.
- Review-loop summary fields for maximal runs: `review_loop_policy=concern_driven_until_clear` and `p4_repair_actions`.

### Changed

- New bounded briefs and report outlines explicitly declare `policy=bounded`.
- `maximal_full_dossier` removes the min/target/max body-length range gate while preserving traceability, quote limits, academic retrieval, strict STORM lens, external review provenance, PDF/HTML parity, and release gates.
- Validation checks the review loop policy for full dossiers and ensures P4 repair counts match the registered red-team artifact.

### Migration

- Follow `docs/migration-v3-to-v4.md`; old v3 runs remain bound to their 3.0 package and are not silently upgraded.

## 3.0.0 - 2026-07-03

### Added

- Typed `search_run`, `candidate`, and `capture` records in the existing ingest JSONL contract.
- Receipt-bound internal retrieval audit with search/resolver snapshots, screening decisions, bibliographic identities, and version families.
- Academic baseline, corpus-seeded, counterevidence, and gap-fill retrieval passes.

### Changed

- External full dossiers require two scholarly discovery surfaces; briefings verify every academic source they cite.
- Academic Claims must bind a verified candidate and the exact captured version; sibling versions count as one independent work.
- Zero results, unmatched candidates, and unreachable resolvers remain distinct and cannot directly prove absence.
- Custom 2.x retrieval adapters must emit the 3.0 typed union; old runs are not silently migrated.
- Merged the duplicate `strict_storm_lens` user option into the recommended `default_full_dossier`; the old CLI name remains a compatibility alias and normalizes to the canonical profile.

### Migration

- Follow `docs/migration-v2-to-v3.md`; roll back to the archived 2.0.0 package when interpreting a 2.x run.

## 2.0.0 - 2026-06-29

### Added

- External review handoff and provenance binding through `review-prepare`.
- Absence-search ledgers for material “not found” claims.
- Explicit P2 resolution actions and P4 repair-to-revision closure.
- Machine-readable raw, citation-marker, and net report-depth measurements.

### Changed

- Full dossiers reject self-attested review, non-causal timestamps, evidence strength above capture ceiling, and unresolved resolver searches.
- Source identity is deduplicated independently from query coverage, allowing one source to support multiple planned questions.
- Net body counting excludes citation keys, link destinations, image markers, and Markdown control syntax.

- `init` now requires profile-selection evidence via `--profile-selection-mode` and `--profile-selection-evidence`; missing profile intake fails before any run directory is committed.
- `init` now preserves caller-provided `user_goal`, `audience`, `geography`, `timeframe`, freshness, uncertainty, high-stakes, user material, and assumptions in `brief.json`.
- Report-depth validation now measures net body length only; generated or hand-written bibliography/source sections such as `References`, `参考文献`, `参考资料`, `资料来源`, and `Sources` cannot satisfy the minimum length gate.
- Added `capture-source` and `ingest-dir` helpers that copy snapshots into evidence cache, build retrieval input JSONL, and reject common bad captures before `ingest`.
- Added `build-paragraph-map` to generate paragraph mappings from sidecar JSONL or stripped `storm-map` comments while preserving final draft validation.
- Markdown blockquotes and fenced code are now excluded from report-depth counts; oversized quote blocks fail the draft and validation gates.
- Added `doctor` to summarize run health, artifact presence, failed checks, and next actions without writing receipts.
- `default_full_dossier` and `critique_deepresearch` now default to strict STORM lens artifacts across plan, evidence, and review.
- `critique_deepresearch` source plans now fail unless they cover user claim extraction, support, counterevidence, theory/framework, reception/criticism, and historical comparison/blind spots.
- Added `scripts/run_checks.py --dist` as the canonical four-adapter package, archive sanitization, and package-verification command.

### Migration

- Follow `docs/migration-v1.1-to-v2.0.md`; old runs remain bound to their 1.1 package hash and are not silently upgraded.

## 1.1.0 - 2026-06-24

### Added

- STORM tasklets generated from every planned research question.
- `findings` command for registering a source-bound findings pool before evidence closure.
- Evidence gate requiring full dossiers to link material Claims to usable findings.
- Full-dossier review inputs for fact checks, conflict review, and draft audit.
- `repair-plan` command that writes structured repair actions without creating receipts.
- Batch mode for the local output eval runner with subprocess isolation per case.

### Changed

- Validation now includes tasklet coverage, finding coverage, and the expanded independent review bundle.
- README and references document the findings pool as the bridge between retrieval and Claim ledgers.

## 1.0.0 - 2026-06-23

### Added

- Governed `storm_research.py` orchestrator with generation-scoped inputs, artifacts, receipts, and release boundary.
- Immutable receipt chain for init, plan, retrieval, evidence, draft, review, render, validation, and release.
- Recovery commands: `status`, `explain`, `retry`, `amend`, and read-only `import-legacy`.
- Trust-aware release gate requiring Yao Trust evidence, Registry hash match, human approval, and current-source re-verification when needed.
- Redacted Gemini bypass incident regressions and adversarial output-eval prompts.

### Changed

- New automation should call `scripts/storm_research.py`; direct worker scripts are compatibility or internal surfaces.
- Public release is built from a strict allowlist and excludes process artifacts, raw inputs, state, and caches.
- Full dossiers cannot be amended to reduced output after PDF failure.

### Migration

- Update commands according to `docs/migration-v0.4-to-v1.0.md`.

## 0.4.0 - 2026-06-22

### Added

- Workspace-scoped default runs under `output/storm-deepresearch/<slug>-<timestamp>`.
- Resolved-path containment checks for run creation, retrieval normalization, audit rendering, export, and validation.
- Monotonic source-register merging that preserves existing IDs and writes atomically.
- Package-scoped Claim-ledger merging that cannot delete omitted existing Claims and commits atomically.

### Changed

- Initialization is create-only and fails when the target already exists; it never truncates research ledgers.
- Retrieval normalization now accepts `--package` and writes only the canonical source register.
- Report export now accepts the package directory and writes only fixed `exports/` and `validation/` children.

### Migration

- Update commands according to `docs/migration-v0.3-to-v0.4.md`.

## 0.3.0 - 2026-06-22

### Added

- Language-aware evidence-led length contracts: Chinese full dossiers default to 8000-10000 body characters and English dossiers to 3500-7000 words.
- Strict `research-plan.report_outline` section budgets linking STORM questions and material claims to final prose.
- Non-zero `report-depth` and `storm-research-utilization` validation gates.
- Explicit mapping from the motivating article's four prompts to auditable Library artifacts.

### Changed

- New research packages default to `full_dossier`; input length changes research effort, not output depth.
- Report writing now expands evidence through mechanisms, counterevidence, examples, implications, limitations, and change conditions instead of repetition.

### Migration

- Existing briefs and research plans must add the fields documented in `docs/migration-v0.2-to-v0.3.md`.

## 0.2.0 - 2026-06-21

### Added

- Yao-compatible runtime interface, manifest governance, trigger cases, five-target semantic contracts, and four distributable platform adapters.
- Strict JSON Schema contracts for briefs, plans, retrieval, sources, claims, report maps, and validation reports.
- Retrieval normalization boundary for host, provider, and closed-corpus modes.
- Claim-Evidence closure, freshness, contradiction, and report mapping validation.
- Canonical Markdown export through Pandoc, Jinja2, and WeasyPrint/Chromium with render fingerprints.
- Non-zero package validation, adversarial fixtures, Output Lab cases, trust checks, and a validated example package.

### Changed

- Perspectives now generate questions only; they are never evidence authorities.
- `report.md` is the sole content source for HTML and PDF.
- Source and claim JSONL ledgers are authoritative; Markdown audit tables are generated views.
- Full output mode requires a verified PDF.

### Removed

- The obsolete permissive `templates/brief.schema.json`; use `schemas/brief.schema.json`.

## 0.1.0 - 2026-06-21

- Initial STORM-inspired prompt workflow, Markdown templates, exporter, and permissive package validator.
