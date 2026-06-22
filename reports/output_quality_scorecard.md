# Output Quality Scorecard

This v0 scorecard compares static without-skill and with-skill outputs using assertion grading.

- Cases: `7`
- Baseline pass rate: `0.0`
- With-skill pass rate: `100.0`
- Delta: `100.0`
- Regressions: `0`
- Blind A/B pairs: `7`
- Gate pass: `True`

Blind review artifacts are generated separately so reviewers can inspect A/B outputs without seeing the answer key.
Run output review adjudication after reviewer decisions are recorded; pending cases should stay pending rather than being counted as human agreement.

## Case Results

| Case | Baseline | With Skill | Delta | Winner | Failed With-Skill Assertions |
| --- | ---: | ---: | ---: | --- | --- |
| current-technical-topic | 0.0 | 100.0 | 100.0 | with_skill | None |
| closed-corpus | 0.0 | 100.0 | 100.0 | with_skill | None |
| contested-policy | 0.0 | 100.0 | 100.0 | with_skill | None |
| numerical-market-claim | 0.0 | 100.0 | 100.0 | with_skill | None |
| file-backed-academic-review | 0.0 | 100.0 | 100.0 | with_skill | None |
| near-neighbor-simple-lookup | 0.0 | 100.0 | 100.0 | with_skill | None |
| high-stakes-boundary | 0.0 | 100.0 | 100.0 | with_skill | None |

## Failure Taxonomy

- No with-skill assertion failures.

## Next Fixes

- Add holdout cases before using this as a release gate.
- Promote repeated failed assertions into the output-risk profile.
- Keep assertions tied to material deliverables, not phrasing trivia.
