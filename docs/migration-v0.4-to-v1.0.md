# Migration: 0.4.0 to 1.0.0 Governed Harness

Version 1.0.0 moves the skill from a Library-style package into a governed stage harness. The main change is that mutable root files are no longer trusted as proof of progress. Every accepted stage writes generation-scoped artifacts and a recomputable receipt.

## New CLI

Use `scripts/storm_research.py` as the supported public command surface:

```bash
python3 scripts/storm_research.py init --topic "Topic" --question "Question" --workspace /path/to/workspace
python3 scripts/storm_research.py plan /path/to/run --plan-json research-plan.json --source-plan-json source-plan.json
python3 scripts/storm_research.py ingest /path/to/run --input-jsonl retrieval-records.jsonl
python3 scripts/storm_research.py evidence /path/to/run --claims claims.jsonl --contradictions contradictions.json --uncertainties uncertainties.json --report-outline report-outline.json
python3 scripts/storm_research.py draft /path/to/run --draft-md draft.md --paragraph-map-jsonl paragraph-map.jsonl
python3 scripts/storm_research.py review /path/to/run --claim-reviews claim-reviews.jsonl --report-audit report-audit.jsonl --revised-md report.md --revised-paragraph-map-jsonl reviewed-map.jsonl --revision-map revision-map.json
python3 scripts/storm_research.py render /path/to/run
python3 scripts/storm_research.py validate /path/to/run
python3 scripts/storm_research.py release /path/to/run --trust trust.json --registry package.json --approval approval.json
```

Compatibility wrappers may remain for older scripts, but new automation should call `storm_research.py`.

## Layout

Authoritative inputs and artifacts live under:

```text
work/generations/g0001/inputs/
work/generations/g0001/artifacts/
state/generations/g0001/receipts/
```

`brief.json` and `current/` are derived views for operator convenience. Editing them does not advance the run and can make the next stage fail.

## Recovery Commands

Use these commands instead of editing receipts or output metadata:

```bash
python3 scripts/storm_research.py status /path/to/run
python3 scripts/storm_research.py explain /path/to/run
python3 scripts/storm_research.py retry /path/to/run --stage render
python3 scripts/storm_research.py amend /path/to/run --changes-json changes.json --initiator "reviewer" --approval-evidence "approval:ticket-123"
```

`amend` creates a new generation and preserves previous generations. It does not copy downstream receipts. A full dossier cannot be amended to reduced output to bypass a failed PDF render.

## Legacy Import

Use read-only import for 0.4.x packages:

```bash
python3 scripts/storm_research.py import-legacy \
  --legacy-package /path/to/old-package \
  --workspace /path/to/workspace \
  --output imported-run
```

Legacy import validates and imports `brief.json`, `research/research-plan.json`, and `research/source-plan.json`. It does not create a passed retrieval receipt. If old packages lack captured source snapshots and provenance, the next required stage is `retrieval`.

## Removed Bypasses

These 0.4-era shortcuts are no longer valid:

- changing `brief.json` from `full` to `reduced` after render failure
- editing a receipt status to `passed`
- adding References without paragraph-to-claim citation mapping
- adding intermediate JSONL files to the public package
- using placeholder domains or fake source URLs
- treating a Yao trust report, registry hash, or human approval as implicit

## Release Levels

`validate` proves the offline governed package. `release` additionally requires host-controlled trust evidence, Registry metadata, human approval, and fresh re-verification for stale current claims. Public release output is built from a strict allowlist under `release/`; `work/`, `state/`, retrieval inputs, and amendment inputs are not copied.

## Rollback

The local baseline tag is `v0.4.0-baseline`. Keep the 0.4.0 archive available for rollback and comparison, but do not mix 0.4 root-state mutation with 1.0 receipt-governed runs.
