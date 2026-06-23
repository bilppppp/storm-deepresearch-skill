# Claim-Evidence Policy

`work/generations/g0001/artifacts/research/claim-evidence-ledger.jsonl` is the authority for report claims. Markdown evidence maps are generated release views.

## Claim Types

- `fact`: needs at least one registered supporting source and a locator with an evidence-bearing excerpt.
- `inference`: needs supported factual premises and an explicit reasoning note.
- `recommendation`: needs supported premises, user context, reasoning, and tradeoffs.

## Status

- `supported`: direct evidence supports the scoped wording.
- `qualified`: evidence supports a narrower or conditional wording.
- `contested`: credible supporting and contradicting evidence both exist.
- `unsupported`: evidence is absent; a material claim cannot be released.
- `out_of_scope`: intentionally excluded from the report.

## Closure Rules

1. Every material claim maps to public report text through `report-claim-map.json`.
2. Every supporting source ID exists in `source-register.jsonl`.
3. Every supported source has a locator and excerpt.
4. Current claims use sources marked current under the brief's freshness policy.
5. Contested claims include contradicting source IDs and appear in contradiction analysis.
6. Unsupported material claims are removed, narrowed, or moved to the uncertainty ledger.

Run the governed evidence stage:

```bash
python3 scripts/storm_research.py evidence "$RUN_DIR" \
  --claims claims.jsonl \
  --contradictions contradictions.json \
  --uncertainties uncertainties.json \
  --report-outline report-outline.json
```

Exit `5` means the evidence gate failed. Do not convert that failure into a warning, do not add unmapped factual paragraphs later, and do not move unsupported facts directly into prose.
