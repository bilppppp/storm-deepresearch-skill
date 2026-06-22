# Output Path and Ledger Policy

## Default boundary

Create each run under:

```text
<workspace>/output/storm-deepresearch/<topic-slug>-<timestamp>/
```

`--workspace` identifies the user workspace. `--output-root` may select another user-approved root. A relative `--output` is a new run-directory name below that root; an absolute value must still resolve below it.

Resolve existing symlinks before comparing paths. Reject a target when the resolved run directory is the root itself or is outside the resolved root. Package tools apply the same rule to `research/`, `exports/`, and `validation/` children.

## No-clobber initialization

Initialization is create-only. If the target path already exists, stop with exit `4`; do not inspect, truncate, recreate, or partially update it. Choose a new run directory instead. There is no implicit resume or force mode.

## Ledger preservation

These are authoritative records:

- `research/source-register.jsonl`
- `research/claim-evidence-ledger.jsonl`

Never recreate or truncate them after initialization. The retrieval normalizer reads the existing source register, preserves all existing IDs, updates a matching identity only with a newer retrieval record, assigns new IDs monotonically, and replaces the file atomically only after the complete merge succeeds. A failed parse or merge leaves the existing ledger unchanged.

Use `scripts/merge_claim_ledger.py` for Claim updates. It preserves every existing Claim and its order, appends new IDs, replaces only an explicitly supplied matching ID, validates all records before commit, and writes atomically. A failed update leaves the previous Claim ledger unchanged.

## Regenerable files

The following are derived and may be replaced inside the same package:

- Markdown audit views such as `source-register.md` and `evidence-map.md`
- `exports/report.html` and `exports/report.pdf`
- `validation/render-manifest.json`
- `validation/validation-report.json` and `.md`

Regeneration does not authorize writes outside the package or replacement of canonical ledgers.
