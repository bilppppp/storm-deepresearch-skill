# Example Output Tree

```text
output/
├── brief.json
├── research/
│   ├── research-plan.json
│   ├── source-register.jsonl
│   ├── source-register.md
│   ├── claim-evidence-ledger.jsonl
│   ├── evidence-map.md
│   ├── report-claim-map.json
│   ├── perspective-questions.md
│   ├── contradiction-ledger.json
│   ├── contradiction-map.md
│   ├── uncertainty-ledger.md
│   └── peer-review.md
├── report.md
├── exports/
│   ├── report.html
│   └── report.pdf
└── validation/
    ├── render-manifest.json
    ├── validation-report.json
    └── validation-report.md
```

JSON/JSONL files are machine-authoritative. Markdown files under `research/` are human-readable audit views. `report.md` is the only public content source; HTML and PDF are derived outputs.
