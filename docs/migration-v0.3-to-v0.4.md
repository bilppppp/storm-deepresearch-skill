# Migration: 0.3.0 to 0.4.0

## Output directory

New runs default to `<workspace>/output/storm-deepresearch/<topic-slug>-<timestamp>`. Pass `--workspace` when the current process directory is not the user's workspace. Use `--output-root` only for an explicitly approved alternative root.

`--output` now names a new child below the approved root. Existing targets fail with exit `4`; there is no implicit overwrite or resume.

```bash
python3 scripts/init_research_package.py \
  --topic "Research topic" \
  --question "Research question" \
  --workspace /path/to/workspace \
  --output research-run
```

## Retrieval normalization

Replace arbitrary `--output` with the research package boundary:

```bash
python3 scripts/normalize_retrieval.py adapter-output.jsonl \
  --mode host \
  --package /path/to/workspace/output/storm-deepresearch/research-run
```

The normalizer preserves existing source IDs, adds new IDs monotonically, and leaves the prior ledger unchanged if parsing or merging fails.

Update Claims through the package-scoped merge command rather than replacing the JSONL file:

```bash
python3 scripts/merge_claim_ledger.py claim-updates.jsonl \
  --package /path/to/workspace/output/storm-deepresearch/research-run
```

The input contains complete new or revised Claim records. Existing Claims omitted from the update remain untouched.

## Export

Pass the research package directory rather than separate Markdown and output paths:

```bash
python3 scripts/export_report.py /path/to/research-run \
  --template templates/report.html.j2 \
  --title "Research Report" \
  --require-pdf
```

The exporter reads `report.md` and writes only `exports/` and `validation/` inside that package. Replace escaping symlinks with real package directories before migrating.
