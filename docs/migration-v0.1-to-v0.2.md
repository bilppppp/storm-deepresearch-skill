# Migration: 0.1.0 to 0.2.0

## Breaking Changes

1. `schemas/brief.schema.json` is the only brief schema. The old `templates/brief.schema.json` was permissive and has been removed.
2. Briefs now require `schema_version`, `package_state`, `source_policy`, `freshness_policy`, `retrieval_mode`, and `output_mode`; unknown fields fail validation.
3. JSONL source and claim ledgers replace Markdown tables as authoritative data.
4. A full package requires `research-plan.json`, `report-claim-map.json`, `contradiction-ledger.json`, render manifest, validation JSON, and PDF.
5. Validation failures return non-zero exit codes. Existing automation must not assume that an emitted HTML file means the package passed.

## Migration Procedure

1. Keep the original output immutable.
2. Initialize a new 0.2.0 package with `scripts/init_research_package.py`.
3. Copy scope fields into the new `brief.json`; do not copy obsolete fields such as `output_formats` or `retrieval_date`.
4. Convert each source to `schemas/source-record.schema.json` and each material statement to `schemas/claim-evidence-record.schema.json`.
5. Add evidence locators and map report prose through `research/report-claim-map.json`.
6. Regenerate Markdown audit views, HTML, PDF, and the render manifest.
7. Run `scripts/run_checks.py --package OUTPUT_DIR` and resolve every non-zero gate.

## Rollback

The verified sibling snapshot `storm-deepresearch-skill-v0.1.0-snapshot` is the source rollback boundary. Generated 0.2.0 output packages are not backward compatible and should not be copied over 0.1.0 outputs. Restore the snapshot into a new directory; do not overwrite the current source or research artifacts.
