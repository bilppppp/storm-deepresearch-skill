# STORM DeepResearch Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox completion and verification gates. In the current session, execute inline unless the user explicitly requests delegation.

**Goal:** Upgrade `storm-deepresearch-skill` from a prompt-heavy scaffold into a Yao Library package with schema-backed evidence, hybrid retrieval contracts, deterministic export, strict validation, and reproducible evals.

**Architecture:** `report.md` is canonical. Perspectives generate research questions, adapters return normalized retrieval records, source and claim ledgers carry evidence authority, and deterministic scripts render and validate every output. Yao Meta Skill supplies package, governance, Output Lab, Review Studio, trust, and install gates.

**Tech Stack:** Python 3.11 standard library, Pandoc 3.8.3, Jinja2 3.1.6, WeasyPrint 69.0 with Chromium fallback, JSON Schema Draft 2020-12 contracts, `unittest`, Yao Meta Skill CLI.

**Design Inputs:** `docs/superpowers/specs/2026-06-21-storm-deepresearch-library-design.md`, `docs/superpowers/specs/2026-06-21-storm-deepresearch-library-meta-design.md`, and `docs/superpowers/specs/2026-06-21-storm-deepresearch-target-skill-ir.json`.

---

## Execution Preconditions

- Target directory: `<skill-root>`
- The target is not currently a Git repository.
- Before implementation, create a verified sibling snapshot.
- Ask for explicit approval before `git init`; do not fabricate commit history.
- Do not install packages or call external retrieval providers without approval.

## Task 0: Preserve the Current Baseline

**Files:**
- Create: `../storm-deepresearch-skill-v0.1.0-snapshot/`
- Create: `reports/baseline/current-package-audit.md`

- [ ] Verify that the target is not a Git repository.

```bash
cd "<skill-root>"
test ! -d .git
```

Expected: exit `0` and no output.

- [ ] Copy a lossless snapshot after confirming the sibling path does not exist.

```bash
test ! -e ../storm-deepresearch-skill-v0.1.0-snapshot
ditto . ../storm-deepresearch-skill-v0.1.0-snapshot
diff -qr . ../storm-deepresearch-skill-v0.1.0-snapshot
```

Expected: `diff` exits `0` with no output.

- [ ] Record the known baseline failures: invalid Skill IR, governance `42/100`, stability `59/100`, initial load `2049`, false-pass validator, incomplete export.

- [ ] Ask for approval to run `git init`. If approved, initialize and commit the untouched baseline.

```bash
git init
git add -A
git commit -m "chore: snapshot storm deepresearch v0.1.0"
```

## Task 1: Add the Library Interface and Governance Contract

**Files:**
- Modify: `SKILL.md`
- Modify: `manifest.json`
- Create: `agents/interface.yaml`
- Modify: `README.md`
- Test: `evals/trigger_cases.json`

- [ ] Write failing trigger and structure checks first.

`evals/trigger_cases.json` must contain at least five positive, five negative, and five edge cases copied from `target-skill-ir.json` and assigned stable IDs.

- [ ] Add YAML frontmatter to `SKILL.md` with `name`, `description`, and Library-compatible metadata.

```yaml
---
name: storm-deepresearch-skill
description: Use for source-grounded deep research that needs multi-perspective question generation, claim-evidence traceability, contradiction and uncertainty handling, and validated Markdown, HTML, and PDF deliverables. Do not use for quick lookup, unsupported role-play, or short-answer tasks.
---
```

- [ ] Reduce `SKILL.md` to the trigger surface, execution skeleton, branch decisions, required artifacts, failure policy, and exact script commands. Move detailed research policy to existing references.

- [ ] Add manifest governance fields and declare every component directory.

Required values:

```json
{
  "version": "0.2.0",
  "owner": "陈旭",
  "updated_at": "2026-06-21",
  "review_cadence": "quarterly",
  "status": "active",
  "maturity_tier": "library",
  "lifecycle_stage": "library",
  "context_budget_tier": "library"
}
```

- [ ] Define `agents/interface.yaml` inputs, output mode, retrieval mode, permissions, stop conditions, artifacts, and explicit non-goals.

- [ ] Run the narrow checks.

```bash
META="$HOME/.agents/skills/yao-meta-skill"
PY=.venv/bin/python
$PY $META/scripts/yao.py skill-ir . --output-json reports/skill-ir.json
$PY $META/scripts/yao.py validate .
```

Expected: Skill IR exits `0`; remaining failures are limited to not-yet-implemented eval/runtime gates.

- [ ] If Git was approved, commit.

```bash
git add SKILL.md manifest.json agents/interface.yaml README.md evals/trigger_cases.json
git commit -m "feat: define library interface and trigger contract"
```

## Task 2: Add Schema-Backed Research Contracts

**Files:**
- Create: `schemas/brief.schema.json`
- Create: `schemas/research-plan.schema.json`
- Create: `schemas/retrieval-record.schema.json`
- Create: `schemas/source-record.schema.json`
- Create: `schemas/claim-evidence-record.schema.json`
- Create: `schemas/report-claim-map.schema.json`
- Create: `schemas/validation-report.schema.json`
- Create: `scripts/contract_io.py`
- Create: `scripts/init_research_package.py`
- Create: `tests/test_contracts.py`
- Create: `tests/test_init_research_package.py`

- [ ] Write failing tests for required fields, enums, unknown fields, stable IDs, duplicate IDs, malformed dates, and invalid state transitions.

Representative test:

```python
def test_fact_without_support_is_rejected(self):
    record = {
        "claim_id": "C001",
        "claim_text": "The market grew by 40%.",
        "claim_type": "fact",
        "supporting_source_ids": [],
        "contradicting_source_ids": [],
        "status": "supported",
    }
    with self.assertRaisesRegex(ContractError, "fact requires supporting evidence"):
        validate_claim_record(record)
```

- [ ] Implement a small standard-library contract loader. It must reject unknown top-level fields and aggregate all validation messages before exiting.

Required public API:

- `ContractError(ValueError)`: aggregates contract violations into one exception.
- `load_json(path: Path) -> dict[str, object]`: reads UTF-8 JSON and rejects non-object roots.
- `load_jsonl(path: Path) -> list[dict[str, object]]`: reports file and line for malformed records.
- `validate_brief(data: dict[str, object]) -> list[str]`: returns every brief violation in stable order.
- `validate_source_record(data: dict[str, object]) -> list[str]`: validates IDs, provenance, dates, and freshness state.
- `validate_claim_record(data: dict[str, object]) -> list[str]`: validates claim type, evidence relations, and status consistency.
- `validate_research_package(root: Path) -> list[str]`: resolves cross-file IDs and state invariants.

- [ ] Implement the initializer so it creates a valid empty package with explicit states, not fake evidence or placeholder claims.

```bash
python3 scripts/init_research_package.py \
  --topic "Test topic" \
  --question "What evidence answers the test question?" \
  --output /private/tmp/storm-contract-smoke
python3 scripts/validate_contracts.py /private/tmp/storm-contract-smoke
```

Expected: initialization exits `0`; validation reports the package as initialized but not release-ready.

- [ ] Run tests.

```bash
python3 -m unittest tests.test_contracts tests.test_init_research_package -v
```

Expected: all tests pass.

- [ ] Commit if Git is active.

```bash
git add schemas scripts/contract_io.py scripts/init_research_package.py tests
git commit -m "feat: add research package contracts"
```

## Task 3: Define Hybrid Retrieval and Source Normalization

**Files:**
- Create: `references/retrieval-adapters.md`
- Create: `scripts/normalize_retrieval.py`
- Create: `tests/test_normalize_retrieval.py`
- Create: `tests/fixtures/retrieval/host-valid.jsonl`
- Create: `tests/fixtures/retrieval/provider-invalid.jsonl`
- Modify: `SKILL.md`
- Modify: `agents/interface.yaml`

- [ ] Write failing tests for host, provider, and closed-corpus modes.

The normalizer must reject missing URL/file identity, missing retrieval time, absolute raw artifact paths in public fields, duplicate canonical sources, and adapter names not allowed by the brief.

- [ ] Implement the pure normalization boundary.

Required public API:

- `canonicalize_url(value: str) -> str`: lowercase scheme and host, remove fragments and tracking parameters, preserve evidence-bearing query parameters.
- `normalize_retrieval_record(record, mode) -> dict[str, object]`: validate the adapter payload and return the source-schema field set only.
- `merge_source_records(records) -> list[dict[str, object]]`: deduplicate by canonical URL or file hash, merge retrieval metadata, and assign stable source IDs after sorting.

- [ ] Document three modes:

1. `host`: agent retrieves with approved native tools and writes adapter JSONL;
2. `provider`: explicit command/API adapter with environment-only credentials;
3. `closed_corpus`: only supplied files and URLs, no external expansion.

- [ ] State that the package never runs an undocumented network client and never stores credentials.

- [ ] Run tests.

```bash
python3 -m unittest tests.test_normalize_retrieval -v
```

Expected: valid host fixture passes; invalid provider fixture fails with all provenance errors.

- [ ] Commit if Git is active.

```bash
git add references/retrieval-adapters.md scripts/normalize_retrieval.py tests agents/interface.yaml SKILL.md
git commit -m "feat: add retrieval adapter contract"
```

## Task 4: Build Claim-Evidence Closure and Audit Views

**Files:**
- Create: `references/claim-evidence-policy.md`
- Create: `scripts/render_audit_views.py`
- Create: `scripts/validate_evidence.py`
- Create: `tests/test_evidence_validation.py`
- Create: `tests/fixtures/empty-evidence/`
- Create: `tests/fixtures/fabricated-citation/`
- Create: `tests/fixtures/stale-source/`
- Modify: `references/source-and-evidence-policy.md`
- Modify: `templates/evidence-map.md`
- Modify: `templates/contradiction-map.md`

- [ ] Write failing tests for every adversarial fixture.

Hard gates:

```text
fact + no support                         -> fail
supported + unknown source ID             -> fail
current claim + stale source              -> fail
report material claim + no claim mapping  -> fail
unsupported claim in public report        -> fail
contested claim + omitted contradiction   -> fail
inference labeled as fact                 -> fail
```

- [ ] Implement claim closure.

Required public API:

- `validate_claim_closure(claims, sources, report_claim_map) -> list[str]`: resolve all IDs, apply type-specific evidence rules, and return stable diagnostics.
- `compute_coverage(claims) -> dict[str, float]`: calculate material fact closure, contested-claim disclosure, freshness compliance, and unsupported-claim counts.

Coverage metrics must include material claims, supported material facts, qualified or contested claims, unsupported claims, and freshness violations. Unsupported material facts must be zero for release.

- [ ] Render human-readable Markdown views from JSON/JSONL ledgers. Never parse the Markdown views back as authority.

- [ ] Run tests.

```bash
python3 -m unittest tests.test_evidence_validation -v
```

Expected: positive fixtures pass and every adversarial fixture exits non-zero.

- [ ] Commit if Git is active.

```bash
git add references scripts templates tests
git commit -m "feat: enforce claim evidence closure"
```

## Task 5: Replace Export with a Canonical Pandoc/Jinja Pipeline

**Files:**
- Modify: `scripts/export_report.py`
- Modify: `templates/report.html.j2`
- Modify: `references/export-workflow.md`
- Create: `requirements.lock`
- Create: `tests/test_export_report.py`
- Create: `tests/fixtures/export/report.md`
- Create: `tests/fixtures/export/expected-sections.json`

- [ ] Pin the verified Python dependencies.

```text
Jinja2==3.1.6
weasyprint==69.0
```

Pandoc remains a documented system dependency; record and validate `pandoc --version` at runtime.

- [ ] Write failing export tests for Markdown tables, fenced code, Unicode, title consistency, unresolved Jinja markers, missing Pandoc, missing required PDF, and reduced mode.

- [ ] Replace `simple_markdown_to_html`. The exporter must invoke Pandoc for a fragment, pass it through Jinja2, then attempt WeasyPrint and Chromium in that order.

Required command:

```bash
python3 scripts/export_report.py output/report.md \
  --out output/exports \
  --template templates/report.html.j2 \
  --title "Research Report" \
  --require-pdf
```

- [ ] Add SHA-256 fingerprints for the canonical Markdown and normalized section text to `validation/render-manifest.json`.

- [ ] Run tests and a representative export.

```bash
python3 -m unittest tests.test_export_report -v
python3 scripts/export_report.py tests/fixtures/export/report.md \
  --out /private/tmp/storm-export-smoke \
  --template templates/report.html.j2 \
  --title "Export Fixture" \
  --require-pdf
```

Expected: Markdown, HTML, and PDF exist; no template markers remain; title and required sections match.

- [ ] Render PDF pages to images and inspect clipping, overflow, page breaks, tables, and references.

- [ ] Commit if Git is active.

```bash
git add scripts/export_report.py templates/report.html.j2 references/export-workflow.md requirements.lock tests
git commit -m "feat: make report export deterministic"
```

## Task 6: Replace the Permissive Validator

**Files:**
- Modify: `scripts/validate_package.py`
- Create: `scripts/run_checks.py`
- Create: `tests/test_validate_package.py`
- Create: `tests/fixtures/missing-pdf/`
- Create: `tests/fixtures/template-leak/`
- Create: `tests/fixtures/local-path-leak/`
- Create: `tests/fixtures/valid-full-package/`
- Modify: `references/quality-gates.md`

- [ ] Write a subprocess test matrix that asserts exact non-zero outcomes.

```python
def test_missing_required_pdf_exits_six(self):
    result = run_validator("tests/fixtures/missing-pdf")
    self.assertEqual(result.returncode, 6)
    self.assertIn("required PDF is missing", result.stderr)
```

- [ ] Validate in this order: arguments, schemas, required files, evidence closure, safety, render manifest, HTML, PDF, cross-format consistency.

- [ ] Always write both `validation-report.json` and `.md`, including check ID, severity, status, path, message, and repair command.

- [ ] Return the highest-priority non-zero exit code; never return zero with failed required checks.

- [ ] Add a single local gate command.

```bash
python3 scripts/run_checks.py --package tests/fixtures/valid-full-package
```

Expected: all unit tests and the representative package pass.

- [ ] Run the negative matrix.

```bash
python3 -m unittest tests.test_validate_package -v
for fixture in empty-evidence fabricated-citation stale-source missing-pdf template-leak local-path-leak; do
  python3 scripts/validate_package.py "tests/fixtures/$fixture" && exit 1 || true
done
```

Expected: every invalid fixture returns non-zero.

- [ ] Commit if Git is active.

```bash
git add scripts tests references/quality-gates.md
git commit -m "fix: make validation failures enforceable"
```

## Task 7: Build the Output Eval and Baseline Suite

**Files:**
- Create: `evals/evals.json`
- Create: `evals/adversarial_cases.json`
- Create: `evals/fixtures/current-technical-topic/`
- Create: `evals/fixtures/closed-corpus/`
- Create: `evals/fixtures/contested-policy/`
- Create: `evals/fixtures/numerical-market-claim/`
- Create: `evals/fixtures/file-backed-review/`
- Create: `evals/fixtures/near-neighbor-lookup/`
- Create: `evals/fixtures/high-stakes-boundary/`
- Create: `reports/baseline/`

- [ ] Capture `v0.1.0` results from the verified snapshot before running candidate results.

- [ ] Define assertions for evidence closure, entailment, contradiction coverage, freshness, uncertainty, format completeness, consistency, and usefulness.

- [ ] Use recorded fixtures for deterministic regression and label them accurately. Do not call them model-executed evidence.

- [ ] Run Yao Output Lab and baseline comparison using the actual CLI help for this installed version.

```bash
META="$HOME/.agents/skills/yao-meta-skill"
PY=.venv/bin/python
$PY $META/scripts/yao.py output-eval --help
$PY $META/scripts/yao.py baseline-compare --help
```

Then execute the exact flags reported by those commands and save all artifacts under `reports/`.

- [ ] Generate a blind A/B review kit and record reviewer decisions before promotion.

- [ ] Require zero evidence/safety regressions and a positive aggregate score delta.

- [ ] Commit if Git is active.

```bash
git add evals reports/baseline
git commit -m "test: add research output lab and baseline suite"
```

## Task 8: Run Yao Library Gates and Package Simulation

**Files:**
- Generate: `reports/skill-ir.json`
- Generate: `reports/output-risk-profile.*`
- Generate: `reports/artifact-design-profile.*`
- Generate: `reports/prompt-quality-profile.*`
- Generate: `reports/system-model.*`
- Generate: `reports/iteration-directions.*`
- Generate: `reports/review-studio.*`
- Generate: `reports/trust_report.*`
- Generate: package artifacts under Yao's configured output directory

- [ ] Run core validation.

```bash
META="$HOME/.agents/skills/yao-meta-skill"
PY=.venv/bin/python
$PY $META/scripts/yao.py validate .
$PY $META/scripts/yao.py skill-ir . --output-json reports/skill-ir.json
$PY $META/scripts/yao.py output-risk-profile . --output-md reports/output-risk-profile.md --output-json reports/output-risk-profile.json
$PY $META/scripts/yao.py artifact-design-profile . --output-md reports/artifact-design-profile.md --output-json reports/artifact-design-profile.json
$PY $META/scripts/yao.py prompt-quality-profile . --output-md reports/prompt-quality-profile.md --output-json reports/prompt-quality-profile.json
$PY $META/scripts/yao.py system-model . --output-md reports/system-model.md --output-json reports/system-model.json
$PY $META/scripts/yao.py iteration-directions . --output-md reports/iteration-directions.md --output-json reports/iteration-directions.json
```

Expected: structure, lint, governance, and resource checks pass; governance score is at least `85`; initial load is at most `1300` tokens.

- [ ] Run Review Studio, trust, conformance, packaging, package verification, and install simulation after checking the installed CLI help for exact flags.

```bash
$PY $META/scripts/yao.py review-studio --help
$PY $META/scripts/yao.py trust --help
$PY $META/scripts/yao.py conformance --help
$PY $META/scripts/yao.py package --help
$PY $META/scripts/yao.py package-verify --help
$PY $META/scripts/yao.py install-simulate --help
```

- [ ] Block release on any Review Studio blocker. Warning waivers require reviewer, reason, scope, and expiry; blockers cannot be waived.

- [ ] Commit generated evidence only if it is stable, relative-path-safe, and intended for source control.

## Task 9: Documentation, Migration, and Final Release Review

**Files:**
- Modify: `README.md`
- Create: `CHANGELOG.md`
- Create: `docs/migration-v0.1-to-v0.2.md`
- Create: `docs/release-checklist.md`
- Modify: `manifest.json`

- [ ] Document installation, dependencies, adapter modes, exact run commands, output structure, validation exit codes, and known limitations.

- [ ] Document migration from Markdown-first audit files to JSON/JSONL authority plus generated Markdown views.

- [ ] Document rollback to the verified `v0.1.0` snapshot.

- [ ] Search for stale names, old output trees, permissive PDF wording, absolute local paths, unresolved placeholders, and credential-shaped strings.

```bash
rg -n "PDF-ready|PDF not generated|source-register\.md|evidence-map\.md|\{\{|\{%|local path|file:///|api[_-]?key|token" \
  SKILL.md README.md manifest.json agents schemas scripts references templates tests evals docs
```

- [ ] Run the complete gate from a clean temporary output directory.

```bash
python3 scripts/run_checks.py --all
```

- [ ] Inspect `git diff --check`, staged diff, and secret scan before commit.

```bash
git diff --check
git status --short
git diff --stat
git diff --cached
```

- [ ] Commit if Git is active.

```bash
git add -A
git commit -m "docs: finalize storm deepresearch library release"
```

## Final Acceptance

- [ ] `target-skill-ir.json` is reproduced by Yao from the package without manual repair.
- [ ] Yao validate, governance, resource, trust, conformance, package, verification, and install simulation pass.
- [ ] Governance score is at least `85/100`.
- [ ] `SKILL.md` initial load is at most `1300` tokens.
- [ ] All deterministic and adversarial tests pass.
- [ ] Seven Output Lab cases exist, including file-backed, near-neighbor, and boundary cases.
- [ ] Blind A/B review is adjudicated and candidate beats the `v0.1.0` snapshot without evidence or safety regression.
- [ ] Representative Markdown, HTML, and PDF are complete and content-consistent.
- [ ] HTML and rendered PDF pages pass visual inspection.
- [ ] Every required failure exits non-zero.
- [ ] Documentation contains exact installation and rollback commands and no local paths or secrets.
