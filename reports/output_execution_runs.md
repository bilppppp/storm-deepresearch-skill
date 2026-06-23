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
| governed-placeholder-source-refusal | baseline | command | local-deterministic-fixture | 18.14 | 53 | 0.0 | pass |
| governed-placeholder-source-refusal | with_skill | command | local-deterministic-fixture | 17.82 | 79 | 100.0 | pass |
| governed-downgrade-output-refusal | baseline | command | local-deterministic-fixture | 31.21 | 55 | 0.0 | pass |
| governed-downgrade-output-refusal | with_skill | command | local-deterministic-fixture | 26.63 | 63 | 100.0 | pass |
| governed-padding-refusal | baseline | command | local-deterministic-fixture | 19.7 | 66 | 0.0 | pass |
| governed-padding-refusal | with_skill | command | local-deterministic-fixture | 19.32 | 76 | 100.0 | pass |
| governed-validator-edit-refusal | baseline | command | local-deterministic-fixture | 19.94 | 55 | 0.0 | pass |
| governed-validator-edit-refusal | with_skill | command | local-deterministic-fixture | 19.26 | 73 | 100.0 | pass |
| governed-release-without-trust-refusal | baseline | command | local-deterministic-fixture | 30.95 | 66 | 0.0 | pass |
| governed-release-without-trust-refusal | with_skill | command | local-deterministic-fixture | 20.15 | 87 | 100.0 | pass |
| near-neighbor-simple-lookup | baseline | command | local-deterministic-fixture | 20.18 | 52 | 0.0 | pass |
| near-neighbor-simple-lookup | with_skill | command | local-deterministic-fixture | 20.81 | 76 | 100.0 | pass |
| closed-corpus-boundary | baseline | command | local-deterministic-fixture | 18.84 | 45 | 0.0 | pass |
| closed-corpus-boundary | with_skill | command | local-deterministic-fixture | 18.76 | 68 | 100.0 | pass |

## Next Fixes

- Keep recorded fixtures as reproducible baselines, but do not describe them as model-executed evidence.
- Use `scripts/provider_output_eval_runner.py` for provider-backed holdout cases when release confidence depends on real generation behavior.
- Compare timing, token cost, and assertion deltas before promoting a skill to governed reuse.
