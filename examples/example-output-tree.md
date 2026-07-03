# Example Output Tree

```text
output/
├── brief.json
├── current/
│   ├── report.md
│   ├── research/
│   └── validation/
├── work/
│   └── generations/
│       └── g0001/
│           ├── inputs/
│           │   └── brief.json
│           ├── evidence-cache/
│           └── artifacts/
│               ├── research/
│               │   ├── research-plan.json
│               │   ├── source-plan.json
│               │   ├── storm-tasklets.jsonl
│               │   ├── storm-findings-pool.jsonl
│               │   ├── finding-coverage.json
│               │   ├── storm-lens-perspectives.json      # strict mode
│               │   ├── storm-lens-conflicts.json         # strict mode
│               │   ├── storm-lens-outline.json           # strict mode
│               │   ├── storm-lens-red-team.json          # strict mode
│               │   ├── source-register.jsonl
│               │   │   # academic rows contain bibliographic identifiers/status/version family
│               │   ├── retrieval-manifest.jsonl
│               │   ├── retrieval-audit.jsonl             # internal; receipt-bound, not released
│               │   ├── claim-evidence-ledger.jsonl
│               │   ├── contradiction-ledger.json
│               │   ├── uncertainty-ledger.json
│               │   ├── report-outline.json
│               │   ├── paragraph-map.jsonl
│               │   ├── citation-index.json
│               │   ├── revision-map.json
│               │   ├── peer-review.json
│               │   └── peer-review.md
│               ├── drafts/
│               │   └── report-v1.md
│               ├── report.md
│               ├── exports/
│               │   ├── report.html
│               │   └── report.pdf
│               └── validation/
│                   ├── render-manifest.json
│                   ├── validation-report.json
│                   └── validation-report.md
└── state/
    ├── run-journal.jsonl
    └── generations/
        └── g0001/
            └── receipts/
                ├── 00-init.json
                ├── 10-plan.json
                ├── 20-retrieval.json
                ├── 30-evidence.json
                ├── 40-draft.json
                ├── 50-review.json
                ├── 60-render.json
                └── 70-validation.json
```

Files under `work/generations/g0001/` are authoritative. `current/` is a convenience view. `report.md` is the only public content source; HTML and PDF are derived outputs. `storm-lens-*.json` files are required only when `storm_lens_mode` is `strict`. `retrieval-audit.jsonl` preserves search, screening, resolver, and version-family evidence internally and is excluded from the public release projection.
