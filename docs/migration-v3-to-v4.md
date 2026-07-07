# Migration from 3.x to 4.0.0

Version 4.0 adds an explicit length policy to every new brief and introduces the advanced `maximal_full_dossier` profile. Max is no longer only an open-ended length setting; it is a source, findings, evidence, and review-loop contract.

## Contract changes

Every new v4 brief also requires an explicit, independent assurance target:

```json
{"assurance_target": "artifact_contract"}
```

Use `artifact_contract` only for fixtures or harness acceptance. User delivery uses `captured_host_execution`, which requires receipt-bound retrieval, draft, and isolated review execution evidence. Artifact-only validation can return `ok: true` for its selected target, but reports `validated_artifact_contract_only` and cannot be normally collected or publicly released.

`brief.length_contract` now requires:

```json
{
  "unit": "words",
  "policy": "bounded",
  "minimum": 3500,
  "target": 5000,
  "maximum": 7000,
  "content_standard": "evidence_led"
}
```

For `maximal_full_dossier`, the contract is open-ended and must not include `minimum`, `target`, or `maximum`:

```json
{
  "unit": "words",
  "policy": "open_ended",
  "content_standard": "evidence_led"
}
```

`report_outline` mirrors the same `policy`. Bounded outlines keep `minimum`, `target`, and `maximum`; open-ended outlines omit them while still requiring section-level `target_units` as planning guidance.

## Profile behavior

`default_full_dossier` remains the recommended default. It is still strict STORM, host retrieval, full output, academic baseline, external review, and bounded body depth.

`maximal_full_dossier` is only for explicit no-cap, no-budget, exhaustive, or "write as much as warranted" requests. It resolves `--language auto` to `zh-CN` and uses open-ended retrieval and body length. It has no source-count or candidate-count acceptance threshold. Completion requires relational tasklet/Claim/section closure, domain-adaptive surfaces, mandatory counterevidence, recomputable gap terminal assessments, and a concern-driven STORM plus academic panel/editor/re-review/final-integrity loop.

The v4 retrieval union is also stricter. Every `search_run` binds both a request JSON artifact/hash and the raw response artifact/hash; the request JSON repeats `query_id`, `surface`, `query`, and `aliases`, and ingest recomputes all values. A `search_wave` now declares new candidate/source/finding/contradiction/uncertainty IDs, changed Claim IDs, and optional `material_delta`; final validation checks those IDs against the ledgers and recomputes the delta. A terminal `gap_assessment` can omit `review_concern_id` during retrieval, but the final review loop must close it by concern ID or by a `gap_assessment` / `gap` target. A single response artifact cannot be relabelled as several executed queries. Candidates add `canonical_version`; duplicate identifiers or exact title/author/year identities must share a version family, and a multi-record family selects exactly one included canonical version. Capture levels now distinguish `abstract` and `metadata` from `full_text`; abstract evidence is capped at medium, metadata at background. Max academic candidates need at least two independent matched resolvers including OpenAlex or Semantic Scholar, plus the applicable identifier-native resolver. Captured Max retrieval should run `retrieval-preflight`, `retrieval-prepare`, then `ingest`.

Max reports must synthesize domain findings. Source-register prose such as "这条可审计来源是..." or "this source record..." is invalid in public report prose and invalid as a Max material Claim. Use the ledgers and generated references for audit details; use the report for findings, mechanisms, contradictions, limitations, and implications.

The compatibility review summary for maximal runs still includes:

```json
{
  "review_loop_policy": "concern_driven_until_clear",
  "p4_repair_actions": 0
}
```

This summary is not enough to validate Max. The promoted artifacts must also include `research/review-loop.json`:

```json
{
  "schema_version": "2.0",
  "policy": "concern_driven_until_clear",
  "rounds": [],
  "summary": {
    "final_editor_decision": "accept",
    "unresolved_concerns": 0
  }
}
```

This does not create a hidden infinite loop. Each round binds its generation, draft receipt, immutable review request, complete subject manifest, package-derived rubric, transcript sessions, and round digest. Failed review writes `state/generations/gNNNN/review-blocked.json` and exits non-zero; use `amend --resume-blocked-review` to create the next generation. Old clients that submit several synthetic rounds in one generation fail. Validation also exposes a recomputed root-level `review_outcomes` object; it is audit metadata, not article prose.

## Existing runs

Do not edit old v3 briefs to add `policy` or `assurance_target`. Existing v3 runs remain bound to the package hash and validators that created them. Start a new v4 run to use open-ended length, Max completeness, or captured execution assurance.

To interpret or repair a v3 run, use the archived 3.0.0 package. Rolling back the executable does not downgrade a v4 run.
