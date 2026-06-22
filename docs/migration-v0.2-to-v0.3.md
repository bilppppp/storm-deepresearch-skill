# Migration: 0.2.0 to 0.3.0

## Required brief fields

Add `report_language` and a strict `length_contract`:

```json
{
  "report_language": "zh-CN",
  "length_contract": {
    "unit": "characters",
    "minimum": 8000,
    "target": 9000,
    "maximum": 10000,
    "content_standard": "evidence_led"
  }
}
```

## Required research-plan fields

Every question now records `status`, `claim_ids`, and `disposition_note`. Add `report_outline` with the same unit and bounds as the brief. Before release, every answered question and material claim must be assigned to a section with `purpose`, `target_units`, and at least three evidence-led `required_elements`.

## Validation behavior

- `report-depth` exits `6` when body length falls outside the brief contract.
- `storm-research-utilization` exits `5` when planned research is not used or a depth floor is unmet.
- References are excluded from length counts.

Use `scripts/init_research_package.py --help` to create a fresh 0.3.0 contract and migrate existing ledgers into it.
