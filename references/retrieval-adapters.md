# Retrieval Adapters

Perspectives generate questions. Only retrieved or user-supplied material can become evidence.

## Modes

### `host`

Default when the host agent has approved browser or search tools. The agent retrieves sources, then writes adapter JSONL matching `schemas/retrieval-record.schema.json`.

### `provider`

Use only when the user explicitly configures a provider adapter. Credentials come from environment variables and must never enter the skill, brief, logs, source register, or report.

### `closed_corpus`

Use only supplied files and URLs. Do not expand the corpus through external search. Record file identity and content hash where available.

## Adapter Record

Each record needs a stable query ID, URL or relative file reference, exact title, publisher, publication and retrieval times, evidence-bearing excerpt, content locator, and adapter identity. Optional reliability labels are reviewer judgments, not proof.

Commit records with:

```bash
python3 scripts/storm_research.py ingest "$RUN_DIR" \
  --input-jsonl adapter-output.jsonl
```

The ingest stage writes generation-scoped `source-register.jsonl` and `retrieval-manifest.jsonl`, then commits `20-retrieval.json`. Malformed provenance, placeholder domains, missing snapshots, destructive ledger replacement, absolute public file paths, mode mismatches, invalid timestamps, secondary-as-primary classification, and blanket Tier A reliability are hard failures.

`scripts/normalize_retrieval.py` remains an internal worker. New automation should call `storm_research.py ingest`.

## Network Boundary

Bundled scripts do not initiate research network requests. Host tools or an explicitly approved provider own network execution. This keeps runtime permissions visible and prevents undocumented API behavior.
