# STORM DeepResearch Library Upgrade Design

**Date:** 2026-06-21  
**Status:** proposed  
**Target maturity:** library  
**Source package:** `<skill-root>`

## 1. Problem Statement

The current package is a useful research-protocol draft, but it cannot yet defend production-grade claims. It describes multi-perspective research, source registration, evidence mapping, peer review, and Markdown/HTML/PDF delivery, but the executable layer does not enforce those promises.

Observed evidence:

- Yao Meta Skill validation fails because `SKILL.md` has no frontmatter, `agents/interface.yaml` is missing, and governance metadata is incomplete.
- Governance score is `42/100` (`draft`).
- Initial-load size is about `2049` tokens, above the `1000` production budget and the intended lean entrypoint.
- There are no real trigger or output eval cases, baseline outputs, adversarial hallucination fixtures, or regression evidence.
- `scripts/export_report.py` does not use `templates/report.html.j2`; without optional Python packages, Markdown tables render as paragraphs and PDF generation silently degrades.
- `scripts/validate_package.py` accepts a package containing placeholders, empty evidence tables, and no PDF with exit code `0`.

The upgrade must convert research intentions into machine-checkable contracts without pretending that automated checks can prove truth by themselves.

## 2. Goals

1. Make the package installable and routeable as a Library-grade agent skill.
2. Treat STORM perspectives as question-generation lenses, never as evidence sources.
3. Give every material factual claim a traceable relationship to registered evidence.
4. Separate facts, inferences, recommendations, contradictions, and unknowns.
5. Support host-agent retrieval by default and optional command/API adapters through one portable contract.
6. Use `report.md` as the canonical public report and deterministically derive HTML and PDF.
7. Fail visibly and with non-zero exit status when required evidence, requested exports, or validation gates are missing.
8. Prove improvement with trigger tests, deterministic fixtures, adversarial cases, and comparison against the current package snapshot.

## 3. Non-Goals

- Do not bundle a paid search service or require a specific model provider in v1.
- Do not claim to eliminate all hallucinations or to produce PhD-equivalent research in minutes.
- Do not treat agreement among simulated perspectives as evidence of truth.
- Do not add DOCX, slide, visual-illustration, or publishing-platform workflows in v1.
- Do not build a general crawler, browser automation platform, or citation-ranking service.
- Do not make legal, medical, or investment decisions automatically.

## 4. Capability Boundary

The skill owns reusable, source-grounded, multi-perspective research packages for users who need a substantial report rather than a quick answer. Inputs may be a topic, question, URL list, local file set, or rough brief. The default outputs remain:

```text
output/
├── brief.json
├── research/
│   ├── research-plan.json
│   ├── source-register.jsonl
│   ├── source-register.md
│   ├── claim-evidence-ledger.jsonl
│   ├── evidence-map.md
│   ├── report-claim-map.json
│   ├── perspective-questions.md
│   ├── contradiction-ledger.json
│   ├── contradiction-map.md
│   ├── uncertainty-ledger.md
│   └── peer-review.md
├── report.md
├── exports/
│   ├── report.html
│   └── report.pdf
└── validation/
    ├── validation-report.json
    └── validation-report.md
```

Quick lookup, casual brainstorming, source-free opinion writing, pure file conversion, and high-stakes final decisions remain outside the default route.

## 5. Architecture

### 5.1 Agent Orchestration Layer

The agent handles semantic judgment:

1. Normalize the user request into `brief.json`.
2. Select and adapt perspectives for the domain.
3. Convert each perspective into concrete research questions and evidence needs.
4. Use available host tools, user materials, or an approved retrieval adapter.
5. Explain conflicts, applicability limits, and implications.
6. Draft and revise the final report.

The agent must not cite model memory, simulated expert statements, or perspective consensus as evidence.

### 5.2 Deterministic Contract Layer

Scripts handle repeatable behavior:

- initialize the output package from schemas and templates;
- validate brief, source, claim, contradiction, and export records;
- generate readable Markdown views from machine-readable ledgers;
- check claim-source closure, duplicate IDs, unsupported exact statistics, placeholders, path leaks, and source freshness;
- export and verify HTML/PDF from the canonical Markdown;
- emit JSON and Markdown validation reports with stable exit semantics.

### 5.3 Optional Governed Overlay

When the brief is legal, medical, financial, safety-critical, or explicitly high-stakes:

- require `human_review_required: true`;
- block recommendations from being marked final without reviewer identity, review date, and decision;
- preserve unresolved conflicts and low-confidence findings in the public report;
- never convert the research output into individualized professional advice.

## 6. Data Contracts

### 6.1 Brief

`brief.json` remains the run entrypoint. Required fields:

- `topic`, `research_question`, `user_goal`, `audience`;
- `depth_level`, `geography`, `timeframe`;
- `source_constraints`, `output_formats`;
- `recency_requirement`, `uncertainty_tolerance`;
- `high_stakes`, `human_review_required`;
- `assumptions`, `user_materials`, `retrieval_date`.

### 6.2 Research Plan

`research-plan.json` records:

- chosen perspectives and why each is relevant;
- questions, evidence needed, likely blind spots, and stop conditions;
- requested source classes and date ranges;
- questions intentionally excluded from the run.

The five STORM-inspired perspectives are defaults, not a required fixed set.

### 6.3 Source Register

`source-register.jsonl` is canonical. Each record contains:

- stable `source_id`;
- exact title, author/organization, URL or local reference;
- publication/update date and retrieval date;
- source type, authority tier, language, geography;
- adapter/provider provenance;
- relevant questions, caveats, and optional content hash;
- availability status and retrieval error when applicable.

`source-register.md` is generated for human review.

### 6.4 Claim-Evidence Ledger

`claim-evidence-ledger.jsonl` is canonical. Each record contains:

- stable `claim_id` and exact claim text;
- `claim_type`: `fact`, `inference`, or `recommendation`;
- importance and report section;
- supporting and contradicting source IDs;
- evidence strength and confidence;
- freshness/applicability notes;
- `status`: `supported`, `contested`, `insufficient`, or `withdrawn`;
- what evidence would change the conclusion.

Material facts cannot be `supported` with zero source IDs. Recommendations must link to supported or explicitly contested claims. `evidence-map.md` is generated from this ledger.

`report-claim-map.json` maps material claim IDs to the exact report heading and a stable text excerpt. This lets validation prove that public findings come from the claim ledger without placing internal `C1/S1` markers in reader-facing prose.

### 6.5 Retrieval Adapter

The portable adapter request is JSON:

```json
{
  "question_id": "Q1",
  "query": "...",
  "source_types": ["official", "paper"],
  "date_from": "2025-01-01",
  "domains": [],
  "max_results": 10
}
```

The response returns normalized source records, observed errors, and adapter metadata. The default mode is `host-tool`, where the agent writes normalized records after using available browser/search tools. Optional command adapters read one request from stdin and return JSON to stdout. Missing credentials must fail that adapter explicitly; they must never trigger fabricated or model-memory fallback evidence.

## 7. Report And Export Contract

`report.md` is the only canonical public narrative. It must include:

- research question and scope;
- method and source base;
- findings ranked by confidence;
- contradictions and uncertainties;
- implications/recommendations with conditions;
- what would change major conclusions;
- limitations and human-readable references.

Internal source and claim IDs may appear in audit artifacts. Public prose should use readable citations and links rather than leaking raw internal IDs unless the user requests an audit edition. `report-claim-map.json` provides the private bridge between public prose and the audit ledgers.

Export pipeline:

1. Pandoc parses the final Markdown, including tables, links, code, and headings.
2. Jinja renders the maintained HTML shell with title, date, metadata, navigation, and CSS.
3. WeasyPrint is the preferred PDF backend; a reviewed Chromium headless backend is the fallback.
4. Requested PDF failure is a validation failure unless the brief explicitly allows degraded delivery.
5. The validator checks title, required sections, link presence, placeholder absence, local path absence, PDF existence/readability, and Markdown/HTML/PDF content parity signals.

## 8. Error Handling And Exit Codes

- `0`: requested package and all required gates passed.
- `1`: package exists but one or more quality/release gates failed.
- `2`: invalid CLI usage, malformed schema, unreadable input, or missing required dependency.

Required behavior:

- Retrieval failure is recorded per question and source; the run may continue only if the brief's evidence requirements can still be met.
- Empty or unavailable evidence cannot be converted into a confident claim.
- Conflicting sources create a contradiction record instead of forced consensus.
- Current claims with stale or unknown dates fail freshness gates according to the brief.
- Exporters write to temporary files and replace final files only after success.
- Validation reports list every failure and warning; no broad exception handler may silently convert failure into success.
- Partial delivery must state exactly which formats or research questions remain incomplete.

## 9. Evaluation Design

### 9.1 Trigger Evals

Create should-trigger and should-not-trigger cases covering:

- substantial source-grounded research;
- user-material-first research;
- current technical or regulatory research;
- quick factual lookup;
- casual brainstorming;
- pure Markdown/PDF conversion;
- generic article writing without a research requirement.

### 9.2 Deterministic Fixtures

Fixtures must include:

- one fully valid package;
- missing/invalid brief fields;
- empty evidence ledger;
- orphan claim citation;
- unregistered source ID;
- duplicate source or claim ID;
- exact number with no supporting source;
- stale source for a current claim;
- unresolved placeholder;
- local path leak;
- missing requested PDF;
- mismatched report/HTML title;
- successful table, link, and TOC export.

### 9.3 Adversarial Output Evals

Use realistic prompts that pressure the system to:

- invent a paper or URL;
- treat five simulated perspectives as independent confirmation;
- produce a precise statistic from weak evidence;
- hide a source conflict to make the report cleaner;
- connect unrelated facts into a persuasive narrative;
- provide high-stakes advice without reviewer approval.

### 9.4 Baseline Comparison

Before editing, snapshot the current package into a sibling evaluation workspace. Compare old and new skill outputs on at least three representative cases:

1. fast-changing technical topic;
2. contested evidence topic;
3. user-file-first research with limited external retrieval.

New output must beat the snapshot on evidence closure, unsupported-claim rejection, export success, and package validation. Human review remains required for usefulness, writing quality, and whether the synthesis overstates its evidence.

## 10. Package And Governance Changes

Planned package changes:

- add valid `SKILL.md` frontmatter and reduce initial load below the Library budget;
- add `agents/interface.yaml`;
- add project `AGENTS.md` with scripts, paths, validation commands, and caveats;
- expand `manifest.json` with owner, updated date, status, maturity, lifecycle, review cadence, compatibility, and factory components;
- add JSON schemas for brief, plan, sources, claims, contradictions, and validation report;
- refactor `export_report.py` and `validate_package.py`;
- add ledger rendering/validation helpers only where they remove repeated logic;
- add unit tests, fixtures, trigger evals, and output eval cases;
- update README and research/export references;
- remove generated `__pycache__` from the package and ignore it going forward.

The current output paths remain compatible wherever possible.

## 11. Acceptance Criteria

The upgrade is complete only when all of the following are evidenced:

1. Yao Meta Skill structure, lint, resource-boundary, and governance checks pass.
2. Governance score is at least `85`, consistent with declared Library maturity.
3. `SKILL.md` stays within the Library initial-load budget.
4. All deterministic tests pass, including every negative fixture failing for the intended reason.
5. A representative report exports valid Markdown, HTML, and PDF on the supported local toolchain.
6. HTML tables, links, TOC, and print layout are visually inspected.
7. PDF is readable and free of local paths, debug headers, and obvious rendering defects.
8. Claim/source closure, placeholder, freshness, and requested-format gates return non-zero on failure.
9. Three end-to-end output eval cases show a positive delta over the current snapshot.
10. Remaining limitations and any missing provider-backed or human-review evidence are stated without overclaiming.

## 12. Risks And Decisions

- A validator can prove structural evidence closure, not that a source is truthful or that a citation semantically entails a claim. Semantic citation review remains an Agent and human-review responsibility.
- Jinja and a PDF backend introduce dependencies; they must be pinned and checked explicitly.
- Host-tool retrieval improves portability but makes end-to-end runs less deterministic. Deterministic fixture tests and adapter contracts contain this risk without pretending to eliminate it.
- The target directory is not currently a Git repository. A snapshot is mandatory before implementation. Initializing Git is recommended but requires separate user approval.
