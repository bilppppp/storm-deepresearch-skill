# Output Execution Runs

This report records how output-eval variants were produced and whether timing or token evidence is observed or estimated.

- Cases: `7`
- Variant runs: `14`
- Command executed: `14`
- Model executed: `0`
- Recorded fixtures: `0`
- Timing observed: `14`
- Token observed: `0`
- Token estimated: `14`
- Delta: `100.0`
- Gate pass: `True`

No model-executed runs are recorded yet.

Use `python3 scripts/yao.py output-exec --provider-runner openai` or `--runner-command` with a reviewed provider-backed runner to replace recorded fixtures with real model output evidence.

Command runner evidence is present. This proves the eval harness executed an external command, but it is not provider-backed model evidence unless the runner reports model metadata.

## Runs

| Case | Variant | Mode | Model | Duration ms | Tokens | Score | Status |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| current-technical-topic | baseline | command | local-deterministic-fixture | 16.35 | 54 | 0.0 | pass |
| current-technical-topic | with_skill | command | local-deterministic-fixture | 17.49 | 122 | 100.0 | pass |
| closed-corpus | baseline | command | local-deterministic-fixture | 22.79 | 48 | 0.0 | pass |
| closed-corpus | with_skill | command | local-deterministic-fixture | 27.08 | 98 | 100.0 | pass |
| contested-policy | baseline | command | local-deterministic-fixture | 17.66 | 50 | 0.0 | pass |
| contested-policy | with_skill | command | local-deterministic-fixture | 17.27 | 112 | 100.0 | pass |
| numerical-market-claim | baseline | command | local-deterministic-fixture | 17.76 | 45 | 0.0 | pass |
| numerical-market-claim | with_skill | command | local-deterministic-fixture | 15.98 | 112 | 100.0 | pass |
| file-backed-academic-review | baseline | command | local-deterministic-fixture | 24.01 | 44 | 0.0 | pass |
| file-backed-academic-review | with_skill | command | local-deterministic-fixture | 23.52 | 114 | 100.0 | pass |
| near-neighbor-simple-lookup | baseline | command | local-deterministic-fixture | 17.2 | 48 | 0.0 | pass |
| near-neighbor-simple-lookup | with_skill | command | local-deterministic-fixture | 16.32 | 74 | 100.0 | pass |
| high-stakes-boundary | baseline | command | local-deterministic-fixture | 15.78 | 48 | 0.0 | pass |
| high-stakes-boundary | with_skill | command | local-deterministic-fixture | 16.71 | 108 | 100.0 | pass |

## Next Fixes

- Keep recorded fixtures as reproducible baselines, but do not describe them as model-executed evidence.
- Use `scripts/provider_output_eval_runner.py` for provider-backed holdout cases when release confidence depends on real generation behavior.
- Compare timing, token cost, and assertion deltas before promoting a skill to governed reuse.
