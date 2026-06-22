# Changelog

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
