# Retrieval Adapters

Perspectives generate questions. Only retrieved or user-supplied material can become evidence.

## Modes

### `host`

Default when the host agent has approved browser or search tools. The agent retrieves sources, then writes adapter JSONL matching `schemas/retrieval-record.schema.json`.

### `provider`

Use only when the user explicitly configures a provider adapter. Credentials come from environment variables and must never enter the skill, brief, logs, source register, or report.

### `closed_corpus`

Use only supplied files and URLs. Do not expand the corpus through external search. Record file identity and content hash where available.

## Enriched ingest contract

Submit one JSONL containing a typed union defined by `schemas/retrieval-record.schema.json`:

1. `search_run` records the query, aliases, surface, pass kind (`corpus`, `baseline`, `counterevidence`, or `gap_fill`), result count, execution status, and immutable result snapshot.
2. `candidate` records screening disposition, bibliographic identifiers, resolver outcomes, and version-family membership. `unreachable` means the resolver could not be reached; it is not equivalent to `unmatched`.
3. `capture` binds an included candidate and query to the exact content snapshot, locator, excerpt, and evidence-strength ceiling used by a Claim.
4. `search_wave` and `gap_assessment` record Max gap-fill waves and terminal gap disposition. `material_delta` may be `null` before findings; final ledgers recompute it. `review_concern_id` may be omitted at ingest and must be closed later by review-loop concern ID or by a `gap_assessment` / `gap` target.

Search and resolver snapshots are required audit evidence. Search snippets can identify candidates but cannot close material Claims. A zero-result search cannot prove absence by itself. `execution_status` records the actual host attempt: if a database, registry, resolver, or publisher endpoint cannot be reached in the captured context, keep it as `unreachable` and close the affected gap with `access_limited_uncertainty`; do not recast it as `zero_results` or `saturated`.

Commit records with:

```bash
python3 scripts/storm_research.py retrieval-preflight "$RUN_DIR" \
  --input-jsonl adapter-output.jsonl

python3 scripts/storm_research.py retrieval-prepare "$RUN_DIR" \
  --input-jsonl adapter-output.jsonl \
  --transcript retrieval-transcript.txt \
  --context-id "$HOST_CONTEXT_ID" \
  --provider "$PROVIDER" \
  --model "$MODEL" \
  --runner "$RUNNER" \
  --execution-id "$EXECUTION_ID" \
  --started-at "$STARTED_AT" \
  --completed-at "$COMPLETED_AT" \
  --to retrieval-execution.json

python3 scripts/storm_research.py ingest "$RUN_DIR" \
  --input-jsonl adapter-output.jsonl \
  --execution-provenance retrieval-execution.json \
  --execution-transcript retrieval-transcript.txt
```

For `artifact_contract` or non-captured fixture runs, omit the execution provenance arguments. `capture-source` and `ingest-dir` can build partial capture rows, but they do not prove Max captured retrieval by themselves.

The ingest stage writes generation-scoped `source-register.jsonl`, `retrieval-manifest.jsonl`, and internal `retrieval-audit.jsonl`, then commits `20-retrieval.json`. The receipt binds every search, resolver, and capture snapshot. Malformed provenance, placeholder domains, missing snapshots, destructive ledger replacement, absolute public file paths, mode mismatches, invalid timestamps, secondary-as-primary classification, blanket Tier A reliability, and unverified academic candidates are hard failures.

## Academic baseline and gap filling

Every external full dossier performs an academic baseline across at least two scholarly discovery surfaces. A briefing may use one surface, but every academic source it cites still requires bibliographic verification. `closed_corpus` records only local corpus runs and skipped resolvers.

Corpus material supplies corpus-seeded aliases and claims; it does not suppress baseline or counterevidence search. Findings marked `needs_more_evidence` require a later `gap_fill` run before evidence closure. Search pass timestamps must preserve the order `corpus -> baseline/counterevidence -> gap_fill`.

DOI, PMID, arXiv, Semantic Scholar, and OpenAlex identities are normalized when available. Preprint, conference, and journal siblings enter one version family and count as one independent source for depth. Claim locators must bind the exact captured version, not a sibling version with similar metadata.

`scripts/normalize_retrieval.py` remains an internal worker. New automation should call `storm_research.py ingest`.

## Network Boundary

Bundled scripts do not initiate research network requests. Host tools or an explicitly approved provider own network execution. This keeps runtime permissions visible and prevents undocumented API behavior.
