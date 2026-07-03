# STORM Academic Retrieval Index Design

**Date:** 2026-07-03
**Status:** approved
**Target:** governed full-dossier retrieval with lighter briefing support
**External benchmark:** `Imbad0202/academic-research-skills-codex@715224a`

## 1. Problem

STORM already converts multi-perspective questions into tasklets, preserves captured
source snapshots, binds findings and Claims to locators, and blocks unsupported
reports. Its current retrieval boundary does not, however, prove that a host search
was broad or reproducible. A retrieval record proves that one accepted source was
captured; it does not record the actual database query, original hit count, rejected
candidates, bibliographic identity checks, or relationships among preprint,
conference, and journal versions.

The upgrade must improve recall and bibliographic integrity without replacing the
existing STORM P1-P4 workflow, adding another user-facing research mode, or making
agents choose among more scripts and commands.

## 2. Decisions

1. Keep the two primary user paths: `default_full_dossier` and `briefing`.
2. Make an academic baseline mandatory inside new external full-dossier runs.
3. Let briefing use a lighter search process, but verify every academic source that
   it actually cites.
4. Preserve `closed_corpus` as a contextual restriction that forbids external
   retrieval.
5. Keep the existing receipt stages and public CLI commands.
6. Keep `retrieval-manifest.jsonl` capture-only.
7. Add exactly one governed runtime artifact,
   `research/retrieval-audit.jsonl`, for search runs and candidate decisions.
8. Do not add Python modules or standalone scripts. Extend existing implementation,
   schemas, tests, and documentation.
9. Treat Academic Research Skills as a design benchmark only. Its CC BY-NC content
   must not be copied into this MIT-0 package.

## 3. Goals

- Record reproducible search execution, not only accepted sources.
- Add DOI, PMID, arXiv, Semantic Scholar, and OpenAlex identities where available.
- Distinguish index match, index miss, provider outage, and non-applicability.
- Preserve excluded candidates and exclusion reasons.
- Prevent multiple versions of one scholarly work from inflating source depth.
- Use user corpora as seeds while retaining baseline external search and gap-fill.
- Keep source capture, Claim closure, STORM lenses, review, and rendering behavior
  compatible with their current responsibilities.

## 4. Non-Goals

- Do not build a general crawler or replace host browser/search tools.
- Do not require one commercial academic database or provider API.
- Do not treat citation count, DOI presence, or journal reputation as proof that a
  source supports a Claim.
- Do not force every research question to be answered by academic literature.
- Do not introduce a third `academic` user mode.
- Do not implement Zotero, Obsidian, or live reference-manager synchronization in
  this upgrade.
- Do not silently migrate or reinterpret receipts created by an older skill package.

## 5. Architecture

The main workflow remains:

```text
init -> P1 -> plan -> retrieval -> findings -> P2 -> P3 -> evidence
     -> draft -> P4 -> external review -> render -> validate
```

The retrieval stage expands internally:

```text
source plan
  -> corpus screening
  -> academic baseline search
  -> topic-specific and counterevidence search
  -> candidate screening
  -> bibliographic verification
  -> version-family resolution
  -> gap-fill
  -> content capture
  -> ingest receipt
```

The host still owns network execution. It submits one enriched JSONL input to the
existing `ingest` command. `ingest` validates and separates that input into:

- `retrieval-audit.jsonl`: search runs and screened candidates;
- `retrieval-manifest.jsonl`: accepted, inspectable evidence captures;
- `source-register.jsonl`: accepted canonical source versions.

The existing `schemas/retrieval-record.schema.json` becomes the input union for
`search_run`, `candidate`, and `capture` records. The existing
`schemas/retrieval-evidence.schema.json` remains capture-only and continues to
govern `retrieval-manifest.jsonl`.

## 6. Existing Artifact Changes

### 6.1 `source-plan.json`

Each question retains its current fields and adds `search_requirements`:

```json
{
  "query_id": "Q001",
  "question": "...",
  "evidence_need": "...",
  "required_source_classes": ["academic"],
  "search_requirements": {
    "aliases": ["..."],
    "required_surfaces": ["scholarly_index", "publisher_or_registry"],
    "academic_required": true,
    "corpus_seeded": true,
    "inclusion_criteria": ["..."],
    "exclusion_criteria": ["..."]
  }
}
```

New full dossiers must include an academic source class. Questions from the
Academic/Scientist lens and questions about named theories, scholars, study
findings, or methodology must set `academic_required: true`.

### 6.2 `retrieval-audit.jsonl`

This is the only new governed artifact. It has two record kinds.

`search_run` records contain:

- stable `search_run_id` and planned `query_id`;
- `pass_kind`: `corpus`, `baseline`, `counterevidence`, or `gap_fill`;
- surface name and class;
- exact query string and aliases;
- search time and result count;
- result-page or API-response snapshot reference and SHA-256;
- execution status: `completed`, `zero_results`, or `unreachable`;
- limitations.

`candidate` records contain:

- stable `candidate_id` and originating search-run IDs;
- title, authors, year, venue, URL, and available identifiers;
- resolver outcomes and their response snapshot hashes;
- screening disposition: `include`, `exclude`, or `needs_review`;
- categorical and human-readable screening reason;
- optional `version_family_id`, version role, and relationship basis.

Only candidates promoted to `include` may produce capture records. Excluded and
needs-review candidates remain in the audit but never enter the source register.

### 6.3 `retrieval-manifest.jsonl`

This file remains a collection of evidence captures. Existing snapshot, locator,
excerpt, provenance, and evidence-ceiling semantics remain unchanged. Each capture
adds:

- `candidate_id`;
- `search_run_ids`;
- the exact scholarly version identity used by the capture.

### 6.4 `source-register.jsonl`

Accepted sources add one nested bibliographic object:

```json
{
  "identifiers": {
    "doi": null,
    "pmid": null,
    "arxiv_id": null,
    "semantic_scholar_id": null,
    "openalex_id": null
  },
  "bibliographic_status": "verified",
  "version_family_id": "W001",
  "version_role": "journal"
}
```

The object is required for accepted academic sources in new full dossiers and for
academic sources cited by briefing runs. Non-academic sources may omit identifiers
but retain the existing source provenance contract.

### 6.5 `finding-coverage.json`

The generated coverage view adds:

- academic-baseline completion;
- corpus-seeded question coverage;
- query IDs requiring gap-fill;
- completed gap-fill query IDs;
- zero-result and unreachable search runs;
- unresolved tasklets after retrieval.

It remains a generated view, not a new source of truth.

## 7. Bibliographic Verification

Resolver outcomes use four states:

```text
matched | unmatched | unreachable | skipped
```

`unreachable` means the resolver did not return a trustworthy answer and must never
be reduced to `unmatched`. A single index miss cannot establish non-existence.

An academic candidate is `verified` when one of these paths succeeds:

1. A persistent identifier resolves in its authoritative registry and returned
   title metadata agrees with the candidate.
2. Two independent authoritative metadata sources agree on title, author, and year
   when no persistent identifier exists.
3. An original publisher or library record agrees with an acquired original work.

An identifier that resolves to conflicting title metadata produces `conflicted`,
not `verified`. A material academic source with `conflicted`, `unverified`, or
`needs_review` status cannot enter a released report.

Resolver response snapshots must be stored under the generation evidence cache and
bound by hash. Providers are adapters; no single provider is mandatory. Appropriate
surfaces include Crossref, PubMed, arXiv, Semantic Scholar, OpenAlex, publisher
records, library catalogs, and domain registries.

## 8. Version Families

Automatic family membership requires an exact identifier relationship or explicit
version metadata. Examples include an arXiv record that identifies its journal DOI
or metadata that explicitly links conference and journal versions.

Title similarity alone may create only a `needs_review` candidate relationship. It
must never auto-merge works.

Rules:

- one version family counts as one independent deep source for retrieval-depth
  thresholds;
- individual versions retain separate source IDs and capture hashes;
- a Claim locator must bind the exact version that was read;
- the system may prefer a reviewed or more complete version for citation, but it
  must not silently move an excerpt or locator between versions.

## 9. Corpus-Seeded Search And Gap-Fill

The operational rule is `corpus-seeded + baseline-search + gap-fill`, not a corpus
shortcut.

1. Corpus entries are screened against the same inclusion and exclusion criteria as
   external candidates.
2. Corpus presence never implies verification or inclusion.
3. Full dossiers perform baseline external academic search even when the corpus
   appears complete.
4. Search then targets uncovered, weakly supported, stale, or contradicted tasklets.
5. A failed or zero-result search does not mark a question answered.
6. Only explicit `closed_corpus` runs omit external baseline search, and their
   absence conclusions remain scoped to the supplied corpus.

P2 `new_retrieval` actions continue to create a new generation through the existing
`amend` path. No second mutation path is introduced.

## 10. Mode Rules

### Full dossier

- academic baseline is mandatory;
- at least two independent academic discovery surfaces must be executed;
- planned academic-required questions must be represented by completed search runs;
- candidate screening and version resolution are mandatory;
- unresolved or weak tasklets require gap-fill or explicit uncertainty;
- accepted academic sources require verified bibliographic identity.

### Briefing

- exhaustive candidate screening and two-surface gap-fill are not mandatory;
- search runs remain recorded when external retrieval occurs;
- every academic source actually cited must still be bibliographically verified;
- retrieval difficulty cannot silently downgrade evidence or fabricate references.

### Closed corpus

- external search runs and resolver network calls are forbidden;
- corpus candidates may retain user-supplied identifiers without external
  verification;
- released claims may state only what was found or not found in the supplied corpus.

`critique_deepresearch` remains a full-dossier contextual profile and adds academic
coverage for theory, historical comparison, reception, and counterevidence.

## 11. Ingest Gates

The existing `ingest` command must fail non-zero when any applicable condition is
true:

- a full dossier lacks a completed academic baseline;
- a planned academic-required query lacks an appropriate search run;
- a completed search run lacks a valid result snapshot and hash;
- a candidate disposition is missing or exclusion lacks a reason;
- an included candidate lacks a capture;
- a capture refers to an excluded, needs-review, or unknown candidate;
- an accepted academic source is not bibliographically verified;
- an identifier resolves to conflicting metadata;
- multiple versions inflate the independent-source threshold;
- corpus coverage is used to suppress mandatory external baseline search;
- required gap-fill is missing;
- a closed-corpus run contains an external search or resolver call.

The current placeholder-domain, snapshot, classification, timestamp, source-depth,
Claim locator, evidence ceiling, and absence-search gates remain in force.

## 12. Failure And Recovery

- Provider failure is recorded as `unreachable`; an alternative resolver may satisfy
  the verification requirement.
- If every suitable resolver is unavailable, the run stops at retrieval rather than
  downgrading to briefing.
- A zero-result search run is valid execution evidence but not evidence of absence.
- Material absence conclusions still require the existing `absence_search` contract.
- A conflicted identifier requires correction, exclusion, or explicit human review
  before the candidate can be included.
- P2-discovered gaps use `amend` to create a new generation; completed ledgers are
  never overwritten.
- Existing `status`, `explain`, `repair-plan`, and `retry` behavior remains the
  recovery interface.

## 13. Implementation Boundary

No new Python file or CLI command is planned. The implementation is limited to the
existing files that own these responsibilities:

- `scripts/storm_research.py`
- `scripts/normalize_retrieval.py`
- `scripts/source_evidence.py`
- `scripts/validate_evidence.py`
- `scripts/contract_io.py`
- existing source-plan, retrieval, source-record, and validation schemas and the
  finding contract in `scripts/contract_io.py`
- existing retrieval, evidence, CLI, incident, and package tests
- `README.md`, `SKILL.md`, interface, research protocol, retrieval adapter policy,
  source/evidence policy, quality gates, migration notes, and changelog

The implementation may add test methods and fixture records to existing test and
fixture files. A new standalone test module requires a demonstrated ownership gap
and is not part of the default plan.

## 14. Test Design

Positive and adversarial tests must cover:

- one work found under multiple URLs and one DOI;
- arXiv, conference, and journal versions counted as one family;
- a Claim locator bound to the correct version;
- a DOI hit with matching metadata;
- an index miss followed by an independent successful match;
- provider outage preserved as `unreachable`;
- corpus entries screened under the same criteria as external candidates;
- full-dossier baseline plus successful gap-fill;
- briefing with verified academic citations;
- excluded candidate with a complete reason;
- DOI resolution with title mismatch rejected;
- fuzzy-title auto-merge rejected;
- missing academic baseline rejected;
- corpus suppression of external baseline rejected;
- unverified academic capture rejected;
- excluded candidate capture rejected;
- zero results rejected as direct absence evidence;
- closed-corpus external resolver rejected;
- result snapshot hash mismatch rejected;
- existing Claim, review, render, validation, package, and install tests remain green.

End-to-end acceptance uses:

1. A film-criticism dossier combining scholarly theory, historical context,
   interviews, reception, and non-academic evidence.
2. A PBCT dossier exercising PubMed-class discovery, trial-registry evidence,
   bibliographic verification, version resolution, and high-stakes absence rules.

## 15. Migration And Rollback

This is a new-run contract change. Older runs remain bound to their original skill
package hash and are not silently upgraded. The release must include migration notes
describing the new retrieval input and audit artifact.

Rollback consists of restoring the previous package and starting a new generation or
run under that package. The upgrade must not rewrite old receipts, source registers,
retrieval manifests, or evidence snapshots.

## 16. Acceptance Criteria

The upgrade is complete only when:

- full dossiers cannot pass ingest without an academic baseline;
- briefings cannot cite an unverified academic source;
- search execution and excluded candidates are recoverable from the receipt-bound
  retrieval audit;
- identifier conflicts and provider outages retain distinct states;
- version families cannot inflate source-depth coverage;
- corpus input seeds rather than suppresses external full-dossier search;
- gap-fill is causally tied to uncovered or weak tasklets;
- no new user-facing mode, formal stage, CLI command, or Python module is added;
- the full test, schema, Yao validation, distribution, and install-simulation suites
  pass;
- regenerated documentation and distribution packages match actual behavior.
