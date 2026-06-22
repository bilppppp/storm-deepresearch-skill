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

Normalize records with:

```bash
python3 scripts/normalize_retrieval.py adapter-output.jsonl \
  --mode host \
  --package "$RUN_DIR"
```

The normalizer writes only `$RUN_DIR/research/source-register.jsonl`. It preserves existing IDs, merges newer records by canonical identity, allocates new IDs monotonically, and commits atomically. Malformed provenance, destructive ledger replacement, absolute public file paths, mode mismatches, and invalid timestamps are hard failures.

## Network Boundary

Bundled scripts do not initiate research network requests. Host tools or an explicitly approved provider own network execution. This keeps runtime permissions visible and prevents undocumented API behavior.
