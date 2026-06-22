# Validation Report

**Status:** PASS

- [x] `file:brief.json` brief.json exists (`brief.json`)
- [x] `file:research/research-plan.json` research/research-plan.json exists (`research/research-plan.json`)
- [x] `file:research/source-register.jsonl` research/source-register.jsonl exists (`research/source-register.jsonl`)
- [x] `file:research/source-register.md` research/source-register.md exists (`research/source-register.md`)
- [x] `file:research/claim-evidence-ledger.jsonl` research/claim-evidence-ledger.jsonl exists (`research/claim-evidence-ledger.jsonl`)
- [x] `file:research/evidence-map.md` research/evidence-map.md exists (`research/evidence-map.md`)
- [x] `file:research/report-claim-map.json` research/report-claim-map.json exists (`research/report-claim-map.json`)
- [x] `file:research/perspective-questions.md` research/perspective-questions.md exists (`research/perspective-questions.md`)
- [x] `file:research/contradiction-ledger.json` research/contradiction-ledger.json exists (`research/contradiction-ledger.json`)
- [x] `file:research/contradiction-map.md` research/contradiction-map.md exists (`research/contradiction-map.md`)
- [x] `file:research/uncertainty-ledger.md` research/uncertainty-ledger.md exists (`research/uncertainty-ledger.md`)
- [x] `file:research/peer-review.md` research/peer-review.md exists (`research/peer-review.md`)
- [x] `file:report.md` report.md exists (`report.md`)
- [x] `file:exports/report.html` exports/report.html exists (`exports/report.html`)
- [x] `file:validation/render-manifest.json` validation/render-manifest.json exists (`validation/render-manifest.json`)
- [x] `contracts` research contracts are valid (`brief.json; research/*.json*`)
- [x] `evidence-closure` material claims have closed evidence (`research/claim-evidence-ledger.jsonl`)
- [x] `public-path-safety` public outputs contain no local path leak (`report.md; exports/report.html`)
- [x] `public-id-safety` public outputs do not expose internal claim/source IDs (`report.md; exports/report.html`)
- [x] `template-resolution` no template markers remain (`report.md; exports/report.html`)
- [x] `title-consistency` Markdown and HTML titles match (`report.md; exports/report.html`)
- [x] `storm-research-utilization` STORM questions, material claims, and section budgets are used by the report (`research/research-plan.json; report.md`)
- [x] `report-depth` report body satisfies the evidence-led length contract (826 words) (`brief.json; report.md`)
- [x] `section-consistency` all Markdown sections appear in HTML (`report.md; exports/report.html`)
- [x] `references-section` references section appears in Markdown and HTML (`report.md; exports/report.html`)
- [x] `render-manifest` render fingerprints match current files (`validation/render-manifest.json`)
- [x] `pdf-integrity` PDF requirement and content checks pass (`exports/report.pdf`)

Passed: 27 | Warnings: 0 | Failed: 0
