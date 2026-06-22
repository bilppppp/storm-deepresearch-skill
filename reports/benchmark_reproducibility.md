# Benchmark Reproducibility

Generated at: `2026-06-21`
Commit: `unknown`
Working tree dirty at generation: `none`
Source tree dirty at generation: `none`
Generated evidence dirty at generation: `none`
Evidence bundle SHA256: `5d35a8aca1be59308d61622e9297394d1439516582ff01474d2ce01ea33b4715`

## Summary

- reproducibility ready: `false`
- release lock ready: `false`
- methodology complete: `true`
- required artifacts: `25`
- missing artifacts: `9`
- source contract sha256: `26ef58b7f9b3`
- archive sha256: `65c6f7a42c72`
- output cases: `7`
- disclosed failure cases: `0`
- reproduction commands: `23`
- provider evidence complete: `false`
- human review complete: `true`
- world-class ready: `false`
- world-class source checks: `0` pass / `0` total; `0` blocked
- beta test ready: `false`
- beta test blockers: `3`
- beta deferred evidence: `0`
- public claim ready: `false`
- public claim blockers: `5`
- changed files at generation: `None`
- source changed files at generation: `None`
- generated changed files at generation: `None`

This report proves local benchmark reproducibility only. It keeps external provider and human-review gaps visible instead of counting them as complete. The git commit and dirty samples are generation-time context; the evidence bundle SHA is the durable anchor for the artifacts listed below.

## Beta Test Boundary

- ready: `false`
- scope: beta/public test release without superiority, fully-reviewed, or world-class claims
- policy: Human blind-review, native permission enforcement, real client telemetry, and ledger acceptance may be deferred for beta/public testing, but public claims must remain blocked until those evidence entries are accepted.
- required wording: Use beta, public test, or technical preview wording; do not claim world-class readiness, fully reviewed quality, or proven superiority over baseline.

| Blocker |
| --- |
| local benchmark reproducibility is incomplete |
| release lock is not clean or commit is unavailable |
| provider-backed model holdout source evidence is incomplete |

| Deferred evidence | Reason |
| --- | --- |
| none | none |

## Public Claim Boundary

- ready: `false`
- scope: public benchmark or world-class readiness claim
- policy: Local reproducibility can pass before public claims; public claims require provider evidence, human adjudication, clean release lock, accepted world-class evidence, and complete source checks.

| Blocker |
| --- |
| local benchmark reproducibility is incomplete |
| release lock is not clean or commit is unavailable |
| provider-backed model holdout evidence is incomplete |
| world-class evidence is not accepted yet (7 open gaps, 0 ledger pending) |
| world-class source checks are not all accepted (0/0 pass, 0 blocked) |

## Release Lock

- ready: `false`
- reason: git status unavailable; git commit unavailable; working tree cleanliness unknown
- status scope: generation-time status

## Evidence Bundle

- algorithm: `sha256(path,label,exists,artifact_sha256)`
- artifacts: `16` / `25`
- sha256: `5d35a8aca1be59308d61622e9297394d1439516582ff01474d2ce01ea33b4715`

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
| failure_disclosure | `evals/failure-cases.md` | present | `3a067c775dda` |
| output_cases | `evals/output/cases.jsonl` | present | `ffa0e861368c` |
| output_schema | `evals/output/schema.json` | present | `f9b01671f840` |
| output_scorecard | `reports/output_quality_scorecard.json` | present | `74cf529fe424` |
| output_execution | `reports/output_execution_runs.json` | present | `6cc959be7c1e` |
| blind_review | `reports/output_blind_review_pack.json` | present | `353f12e37d73` |
| review_adjudication | `reports/output_review_adjudication.json` | present | `e7320ff9e79f` |
| trigger_scorecard | `reports/route_scorecard.json` | present | `4d44bf17d0f8` |
| runtime_conformance | `reports/conformance_matrix.json` | present | `adc46b2f933d` |
| trust_report | `reports/security_trust_report.json` | present | `7e67b88e7975` |
| python_compatibility | `reports/python_compatibility.json` | present | `fe018f18f186` |
| registry_audit | `reports/registry_audit.json` | present | `414c589eebc1` |
| package_verification | `reports/package_verification.json` | present | `83f71e4f53d5` |
| install_simulation | `reports/install_simulation.json` | present | `e68925810293` |
| skill_os2_audit | `reports/skill_os2_audit.json` | present | `1bd18651aa91` |
| world_class_evidence_plan | `reports/world_class_evidence_plan.json` | missing | `` |
| world_class_evidence_ledger | `reports/world_class_evidence_ledger.json` | missing | `` |
| world_class_evidence_intake | `reports/world_class_evidence_intake.json` | missing | `` |
| world_class_evidence_preflight | `reports/world_class_evidence_preflight.json` | missing | `` |
| world_class_submission_review | `reports/world_class_submission_review.json` | missing | `` |
| world_class_operator_runbook | `reports/world_class_operator_runbook.json` | missing | `` |
| world_class_operator_runbook_markdown | `reports/world_class_operator_runbook.md` | missing | `` |
| world_class_operator_runbook_html | `reports/world_class_operator_runbook.html` | missing | `` |
| world_class_claim_guard | `reports/world_class_claim_guard.json` | missing | `` |

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
- disclosed cases: `0`
- policy: Keep representative failures visible and tied to regression checks.

## Limits

- The git commit and dirty flags are generation-time context; release lock is blocked by source changes, while generated evidence artifacts are tracked separately.
- Local command-runner evidence is reproducible but does not replace provider-backed model holdout evidence.
- Pending blind-review decisions are visible but do not count as human adjudication.
- World-class readiness remains false until external and human evidence gaps close.
- Beta/public testing may proceed without human blind-review only when wording avoids superiority, fully-reviewed, or world-class claims.
