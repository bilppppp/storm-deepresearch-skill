# Benchmark Methodology

## Benchmark Types

The release uses three distinct evidence classes: deterministic unit/adversarial tests, Yao trigger and output fixtures, and one representative end-to-end research package. Recorded fixtures are not provider-backed model runs and are not human review.

## Sample Sources

The seven Output Lab cases cover current technical research, a closed corpus, contested policy, exact numerical claims, a file-backed academic excerpt, a near-neighbor lookup, and a high-stakes boundary. Two cases use checked-in files. Six validator fixtures exercise explicit failure paths.

The representative package uses the official STORM paper, the Stanford OVAL repository, and the user-supplied article as separately classified sources. The article motivates the workflow but does not authorize STORM performance claims.

## Evaluation Dimensions

Output assertions cover provenance, material-claim closure, freshness, contradiction handling, uncertainty, scope boundaries, format completeness, and strict validation. Trigger evaluation measures precision, recall, ambiguity, and no-route accuracy. Package evaluation measures contracts, trust, target compatibility, archive safety, installation, and permissions.

## Weighting Rule

Each Output Lab assertion has an explicit positive weight. A case passes only when all required phrases are present and forbidden phrases are absent under the Yao fixture grader. Aggregate fixture pass rate is the unweighted share of passing cases; it is reported separately from human preference and provider evidence.

## Failure Disclosure

The 0.1.0 baseline is a recorded snapshot, not a reconstructed model run. Its permissive behavior scored zero against the new assertions. The 0.2.0 command runner replays deterministic fixture outputs, so the +100-point delta proves contract discrimination, not general model superiority. There are no provider-backed executions, observed token counts, human blind-review decisions, production telemetry, or Git release lock in this directory.

Representative validator failures and expected exit codes are listed in `evals/failure-cases.md`.

## Reproduction

From the project root:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/run_checks.py --all
.venv/bin/python scripts/run_checks.py --package examples/validated-output
```

Yao artifacts are generated with the installed Meta Skill CLI under `$HOME/.agents/skills/yao-meta-skill/scripts/yao.py`. Re-run `output-eval`, `output-exec`, `conformance`, `trust`, `package`, `package-verify`, and `install-simulate` with the checked-in eval cases and packaging expectations. Do not treat pending blind-review templates as completed adjudication.
