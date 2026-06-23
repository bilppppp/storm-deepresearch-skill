# Benchmark Reproducibility

Generated at: `2026-06-23`
Commit: `23b8fbe01047b73b7f1062a474c249037960cb46`
Working tree dirty at generation: `true`
Source tree dirty at generation: `false`
Generated evidence dirty at generation: `true`
Evidence bundle SHA256: `47709864fbf425f9da02a972873b08297922692c7bc260a316672bcdae27a098`

## Summary

- reproducibility ready: `true`
- release lock ready: `true`
- methodology complete: `true`
- required artifacts: `25`
- missing artifacts: `0`
- source contract sha256: `09990b2e5a52`
- archive sha256: `decb0044d88b`
- output cases: `7`
- disclosed failure cases: `17`
- reproduction commands: `23`
- provider evidence complete: `false`
- human review complete: `false`
- world-class ready: `false`
- world-class source checks: `9` pass / `19` total; `10` blocked
- beta test ready: `false`
- beta test blockers: `1`
- beta deferred evidence: `4`
- public claim ready: `false`
- public claim blockers: `4`
- changed files at generation: `20`
- source changed files at generation: `0`
- generated changed files at generation: `20`

This report proves local benchmark reproducibility only. It keeps external provider and human-review gaps visible instead of counting them as complete. The git commit and dirty samples are generation-time context; the evidence bundle SHA is the durable anchor for the artifacts listed below.

## Beta Test Boundary

- ready: `false`
- scope: beta/public test release without superiority, fully-reviewed, or world-class claims
- policy: Human blind-review, native permission enforcement, real client telemetry, and ledger acceptance may be deferred for beta/public testing, but public claims must remain blocked until those evidence entries are accepted.
- required wording: Use beta, public test, or technical preview wording; do not claim world-class readiness, fully reviewed quality, or proven superiority over baseline.

| Blocker |
| --- |
| provider-backed model holdout source evidence is incomplete |

| Deferred evidence | Reason |
| --- | --- |
| `provider-holdout` | Provider-backed source evidence exists, but formal ledger submission and reviewer acceptance are still pending before public claims. |
| `human-adjudication` | Human adjudication evidence is still pending; deferred for beta/public testing and still required before superiority, fully-reviewed, or world-class claims. |
| `native-permission-enforcement` | Native enforcement proof is still pending; deferred for beta/public testing and still required before world-class claims. |
| `native-client-telemetry` | Real client telemetry is still pending; deferred for beta/public testing and still required before world-class claims. |

## Public Claim Boundary

- ready: `false`
- scope: public benchmark or world-class readiness claim
- policy: Local reproducibility can pass before public claims; public claims require provider evidence, human adjudication, clean release lock, accepted world-class evidence, and complete source checks.

| Blocker |
| --- |
| provider-backed model holdout evidence is incomplete |
| human blind-review adjudication is incomplete |
| world-class evidence is not accepted yet (7 open gaps, 4 ledger pending) |
| world-class source checks are not all accepted (9/19 pass, 10 blocked) |

## Release Lock

- ready: `true`
- reason: only generated evidence artifacts were dirty at generation time
- status scope: generation-time status before this report is written

## Evidence Bundle

- algorithm: `sha256(path,label,exists,artifact_sha256)`
- artifacts: `25` / `25`
- sha256: `47709864fbf425f9da02a972873b08297922692c7bc260a316672bcdae27a098`

## Methodology Sections

| Section | Status |
| --- | --- |
| `## Benchmark Types` | present |
| `## Sample Sources` | present |
| `## Evaluation Dimensions` | present |
| `## Weighting Rule` | present |
| `## Failure Disclosure` | present |
| `## Reproduction` | present |

## Required Artifacts

| Label | Path | Status | SHA256 |
| --- | --- | --- | --- |
| methodology | `reports/benchmark_methodology.md` | present | `ed6e391e0521` |
| failure_disclosure | `evals/failure-cases.md` | present | `03d867149373` |
| output_cases | `evals/output/cases.jsonl` | present | `c3c0afeac15e` |
| output_schema | `evals/output/schema.json` | present | `0bdac2ad1273` |
| output_scorecard | `reports/output_quality_scorecard.json` | present | `3117605c68ab` |
| output_execution | `reports/output_execution_runs.json` | present | `5b2d32e4bc0f` |
| blind_review | `reports/output_blind_review_pack.json` | present | `37bc9aa23d0d` |
| review_adjudication | `reports/output_review_adjudication.json` | present | `ec3edbd6c861` |
| trigger_scorecard | `reports/route_scorecard.json` | present | `4d44bf17d0f8` |
| runtime_conformance | `reports/conformance_matrix.json` | present | `bd5bca67fc13` |
| trust_report | `reports/security_trust_report.json` | present | `e715685e8d33` |
| python_compatibility | `reports/python_compatibility.json` | present | `9c80e8cc12e2` |
| registry_audit | `reports/registry_audit.json` | present | `e17cfe02f19c` |
| package_verification | `reports/package_verification.json` | present | `2990f1f28432` |
| install_simulation | `reports/install_simulation.json` | present | `29d0fa3929e7` |
| skill_os2_audit | `reports/skill_os2_audit.json` | present | `6388be5847c7` |
| world_class_evidence_plan | `reports/world_class_evidence_plan.json` | present | `ef350c27a41f` |
| world_class_evidence_ledger | `reports/world_class_evidence_ledger.json` | present | `9347fa24601d` |
| world_class_evidence_intake | `reports/world_class_evidence_intake.json` | present | `177f00416fb6` |
| world_class_evidence_preflight | `reports/world_class_evidence_preflight.json` | present | `071b42620463` |
| world_class_submission_review | `reports/world_class_submission_review.json` | present | `beecbd0b8a7d` |
| world_class_operator_runbook | `reports/world_class_operator_runbook.json` | present | `ef60f539b5a8` |
| world_class_operator_runbook_markdown | `reports/world_class_operator_runbook.md` | present | `79c1ee1bbe97` |
| world_class_operator_runbook_html | `reports/world_class_operator_runbook.html` | present | `4d457b4151fe` |
| world_class_claim_guard | `reports/world_class_claim_guard.json` | present | `eb987da92122` |

## Reproduction Commands

- `git rev-parse HEAD`
  - evidence: `git commit hash`
- `make eval-suite`
  - evidence: `reports/eval_suite.json`
- `python3 scripts/yao.py output-eval`
  - evidence: `reports/output_quality_scorecard.json`
- `python3 scripts/yao.py output-exec --runner-command '["python3","scripts/local_output_eval_runner.py"]'`
  - evidence: `reports/output_execution_runs.json`
- `python3 scripts/yao.py output-review`
  - evidence: `reports/output_review_adjudication.json`
- `python3 scripts/yao.py skill-ir . --output-json skill-ir/examples/yao-meta-skill.json`
  - evidence: `skill-ir/examples/yao-meta-skill.json`
- `python3 scripts/yao.py conformance .`
  - evidence: `reports/conformance_matrix.json`
- `python3 scripts/yao.py trust .`
  - evidence: `reports/security_trust_report.json`
- `python3 scripts/yao.py python-compat .`
  - evidence: `reports/python_compatibility.json`
- `python3 scripts/yao.py package . --platform openai --platform claude --platform generic --platform vscode --expectations evals/packaging_expectations.json --output-dir dist --zip`
  - evidence: `dist/yao-meta-skill.zip`
- `python3 scripts/yao.py package-verify . --package-dir dist --require-zip`
  - evidence: `reports/package_verification.json`
- `python3 scripts/yao.py install-simulate . --package-dir dist`
  - evidence: `reports/install_simulation.json`
- `python3 scripts/yao.py registry-audit .`
  - evidence: `reports/registry_audit.json`
- `python3 scripts/yao.py skill-os2-audit .`
  - evidence: `reports/skill_os2_audit.json`
- `python3 scripts/yao.py world-class-evidence .`
  - evidence: `reports/world_class_evidence_plan.json`
- `python3 scripts/yao.py world-class-ledger . --submissions-dir evidence/world_class/submissions`
  - evidence: `reports/world_class_evidence_ledger.json`
- `python3 scripts/yao.py world-class-intake . --submissions-dir evidence/world_class/submissions`
  - evidence: `reports/world_class_evidence_intake.json`
- `python3 scripts/yao.py world-class-preflight . --submissions-dir evidence/world_class/submissions`
  - evidence: `reports/world_class_evidence_preflight.json`
- `python3 scripts/yao.py world-class-submission-review . --submissions-dir evidence/world_class/submissions`
  - evidence: `reports/world_class_submission_review.json`
- `python3 scripts/yao.py world-class-runbook . --submissions-dir evidence/world_class/submissions`
  - evidence: `reports/world_class_operator_runbook.json`
- `python3 scripts/yao.py world-class-claim-guard .`
  - evidence: `reports/world_class_claim_guard.json`
- `python3 scripts/yao.py evidence-consistency .`
  - evidence: `reports/evidence_consistency.json`
- `make ci-test`
  - evidence: `CI target output`

## Failure Disclosure

- path: `evals/failure-cases.md`
- disclosed cases: `17`
- policy: Keep representative failures visible and tied to regression checks.

## Limits

- The git commit and dirty flags are generation-time context; release lock is blocked by source changes, while generated evidence artifacts are tracked separately.
- Local command-runner evidence is reproducible but does not replace provider-backed model holdout evidence.
- Pending blind-review decisions are visible but do not count as human adjudication.
- World-class readiness remains false until external and human evidence gaps close.
- Beta/public testing may proceed without human blind-review only when wording avoids superiority, fully-reviewed, or world-class claims.
