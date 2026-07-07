# Max Retrieval Execution Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not dispatch subagents unless the user explicitly asks for delegation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the `maximal_full_dossier` retrieval execution path so a real host can turn searches into compliant `retrieval-audit.jsonl`, source register, captured provenance, and findings without falling back to manual reports or stopping at `retrieval`.

**Architecture:** Keep the existing governed stage chain and canonical artifacts. Add profile-aware retrieval preflight and provenance preparation inside `scripts/storm_research.py`, align schema/docs with the real `gap_assessment` contract, and defer review-only bindings to review/final validation instead of requiring future review IDs during retrieval. Do not add a standalone script or a new public deliverable file.

**Tech Stack:** Python 3.11 standard library, JSON Schema Draft 2020-12, existing `unittest` suite, existing receipt/generation harness, existing Yao package validation.

---

## Verified Defects Being Repaired

1. `capture-source` and `ingest-dir` are documented and suggested as retrieval helpers, but they generate `manual-capture`, `surface_class=web`, skipped resolvers, and all-included candidates. That is insufficient for Max academic/captured runs, which require planned discovery surfaces, candidate screening, cross-index resolver evidence, publisher/full-text coverage, and captured execution provenance.
2. `captured_host_execution` retrieval requires `--execution-provenance` and `--execution-transcript`, with exact `input_artifacts` and `record_ids`, but there is no command that computes those values for the host before `ingest`.
3. The plan document still uses the former saturation-assessment name, while schema and code accept only `gap_assessment`.
4. `gap_assessment.review_concern_id` is currently required in retrieval input even though the domain-review concern does not exist until review. This forces the host to invent future concern IDs.
5. `search_wave.material_delta` is required during retrieval, but final material delta is recomputed after findings. This asks the host to know a value that may only be knowable after the findings pool exists.
6. `status`/`explain` still suggests generic `capture-source` / `ingest-dir` repair steps for Max captured retrieval, which points the host toward a path that cannot pass the Max gates.

## Non-Goals

- Do not weaken final Max validation.
- Do not reintroduce fixed source-count thresholds.
- Do not add a standalone retrieval script.
- Do not make `capture-source` pretend to satisfy academic baseline, resolver, or saturation gates.
- Do not require runtime duration or token usage as proof.

---

### Task 1: Lock Down The Current Retrieval Failure As Tests

**Files:**
- Modify: `tests/test_storm_research_cli.py`
- Modify: `tests/test_library_contract.py`
- Modify: `tests/test_normalize_retrieval.py`

- [ ] **Step 1: Add a test proving Max doctor suggestions do not point to low-fidelity helpers**

Add this test to `tests/test_storm_research_cli.py`:

```python
def test_explain_for_max_captured_retrieval_points_to_preflight_and_prepare(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        run = self.planned_run(
            workspace,
            profile="maximal_full_dossier",
            assurance_target="captured_host_execution",
        )
        result = self.invoke("explain", str(run))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["failed_stage"], "retrieval")
        self.assertIn("retrieval has not been run", payload["failed_checks"])
        suggestions = " ".join(payload.get("suggestions", []))
        self.assertIn("retrieval-preflight", suggestions)
        self.assertIn("retrieval-prepare", suggestions)
        self.assertNotIn("capture-source or ingest-dir", suggestions)
```

- [ ] **Step 2: Add a docs-contract test rejecting stale saturation-assessment naming**

Add this assertion to `tests/test_library_contract.py`:

```python
def test_docs_use_gap_assessment_not_saturation_assessment(self) -> None:
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "README.md",
            ROOT / "references/research-protocol.md",
            ROOT / "references/quality-gates.md",
            ROOT / "docs/superpowers/plans/2026-07-06-max-mode-repair.md",
            ROOT / "docs/superpowers/plans/2026-07-07-max-retrieval-execution-repair.md",
        ]
        if path.exists()
    )
    self.assertIn("gap_assessment", docs)
    self.assertNotIn('"record_kind": ' + '"saturation_assessment"', docs)
```

- [ ] **Step 3: Add a test proving low-fidelity helper output is marked unsuitable for Max captured runs**

Add this test to `tests/test_storm_research_cli.py`:

```python
def test_capture_source_warns_when_used_for_max_captured_retrieval(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        run = self.planned_run(
            workspace,
            profile="maximal_full_dossier",
            assurance_target="captured_host_execution",
        )
        snapshot = workspace / "source.txt"
        snapshot.write_text(
            "Directly inspectable evidence excerpt with enough context for capture validation.",
            encoding="utf-8",
        )
        output = workspace / "retrieval-inputs.jsonl"
        result = self.invoke(
            "capture-source", str(run),
            "--query-id", "Q001",
            "--url", "https://example.org/max-capture",
            "--snapshot", str(snapshot),
            "--title", "Max manual capture",
            "--publisher", "Example Publisher",
            "--content-excerpt", "Directly inspectable evidence excerpt",
            "--source-type", "secondary_synthesis",
            "--primary-class", "secondary",
            "--reliability-tier", "B",
            "--reliability-notes", "Manual capture for one source only.",
            "--to", str(output),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["max_compatibility"], "insufficient_for_max_captured")
        warning_text = json.dumps(payload["warnings"], ensure_ascii=False)
        self.assertIn("retrieval-preflight", warning_text)
        self.assertIn("resolver", warning_text)
```

- [ ] **Step 4: Run the focused tests and confirm they fail**

```bash
.venv/bin/python -m unittest \
  tests.test_storm_research_cli.StormResearchCLITests.test_explain_for_max_captured_retrieval_points_to_preflight_and_prepare \
  tests.test_storm_research_cli.StormResearchCLITests.test_capture_source_warns_when_used_for_max_captured_retrieval \
  tests.test_library_contract.LibraryContractTests.test_docs_use_gap_assessment_not_saturation_assessment -v
```

Expected: failures mention missing `suggestions`, missing `max_compatibility`, and the stale saturation-assessment record name.

---

### Task 2: Add Retrieval Preflight Without Writing Receipts

**Files:**
- Modify: `scripts/storm_research.py`
- Modify: `tests/test_storm_research_cli.py`
- Modify: `README.md`
- Modify: `references/research-protocol.md`

- [ ] **Step 1: Add failing CLI tests for `retrieval-preflight`**

Add these tests to `tests/test_storm_research_cli.py`:

```python
def test_retrieval_preflight_reports_expected_record_ids_and_max_errors(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        run = self.planned_run(
            workspace,
            profile="maximal_full_dossier",
            assurance_target="captured_host_execution",
        )
        retrieval = self.write_retrieval_inputs(run, workspace, source_count=2)
        result = self.invoke("retrieval-preflight", str(run), "--input-jsonl", str(retrieval))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["stage"], "retrieval")
        self.assertIn("expected_record_ids", payload)
        self.assertTrue(any(item.startswith("SR") for item in payload["expected_record_ids"]))
        error_text = " ".join(payload["errors"])
        self.assertIn("requires two independent academic discovery surfaces", error_text)
        self.assertIn("candidate screening cannot be all include", error_text)
        self.assertFalse((run / "state/generations/g0001/receipts/20-retrieval.json").exists())

def test_retrieval_preflight_passes_for_valid_max_inputs_without_receipt(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        run = self.planned_run(
            workspace,
            profile="maximal_full_dossier",
            assurance_target="captured_host_execution",
        )
        retrieval = self.write_retrieval_inputs(run, workspace, maximal=True)
        result = self.invoke("retrieval-preflight", str(run), "--input-jsonl", str(retrieval))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["record_counts"]["search_run"], 12)
        self.assertIn("SR001", payload["expected_record_ids"])
        self.assertIn("GA001", payload["expected_record_ids"])
        self.assertFalse((run / "state/generations/g0001/receipts/20-retrieval.json").exists())
```

- [ ] **Step 2: Implement `command_retrieval_preflight`**

In `scripts/storm_research.py`, add a helper that shares the same validation path as `command_ingest` but does not promote artifacts or write receipts:

```python
def _retrieval_preflight_payload(layout: RunLayout, generation: int, input_jsonl: Path) -> dict[str, object]:
    brief = verify_current_brief_view(layout, generation)
    records = load_jsonl(input_jsonl)
    errors: list[str] = []
    sources: list[dict[str, object]] = []
    manifests: list[dict[str, object]] = []
    audit: list[dict[str, object]] = []
    try:
        sources, manifests, audit = normalize_retrieval_records(
            records,
            mode=str(brief["retrieval_mode"]),
            cache_root=layout.evidence_cache(generation, "."),
        )
    except (ContractError, SourceEvidenceError, ValueError) as exc:
        errors.append(str(exc))
    if not errors:
        source_plan_path = layout.artifact(generation, "research/source-plan.json")
        source_plan = load_json(source_plan_path)
        planned_ids = {
            str(item.get("query_id"))
            for item in source_plan.get("questions", [])
            if isinstance(item, dict)
        }
        covered_ids = {str(item.get("query_id")) for item in manifests}
        missing = sorted(planned_ids - covered_ids)
        if missing:
            errors.append("retrieval evidence does not cover planned questions: " + ", ".join(missing))
        errors.extend(validate_retrieval_audit_contract(audit, manifests, sources, source_plan, brief))
        if (
            brief.get("research_profile") == "maximal_full_dossier"
            and brief.get("assurance_target") == "captured_host_execution"
        ):
            errors.extend(validate_captured_retrieval_artifacts(audit, layout.evidence_cache(generation, ".")))
        errors.extend(validate_retrieval_depth(sources, brief, audit))
    expected_record_ids = sorted(
        str(record.get("search_run_id") or record.get("candidate_id") or record.get("wave_id"))
        if record.get("record_kind") != "gap_assessment"
        else str(record.get("assessment_id"))
        for record in audit
        if record.get("record_kind") in {"search_run", "candidate", "search_wave", "gap_assessment"}
    )
    counts: dict[str, int] = {}
    for record in audit:
        kind = str(record.get("record_kind"))
        counts[kind] = counts.get(kind, 0) + 1
    return {
        "schema_version": "2.0",
        "stage": "retrieval",
        "ok": not errors,
        "errors": list(dict.fromkeys(errors)),
        "expected_record_ids": expected_record_ids,
        "record_counts": counts,
        "assurance_target": brief.get("assurance_target"),
        "research_profile": brief.get("research_profile"),
        "receipt_written": False,
    }

def command_retrieval_preflight(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.RETRIEVAL, package_hash)
    payload = _retrieval_preflight_payload(layout, generation, args.input_jsonl)
    _print_json(payload)
    return EXIT_OK
```

- [ ] **Step 3: Wire the parser**

In `build_parser()` in `scripts/storm_research.py`, add:

```python
preflight = sub.add_parser("retrieval-preflight")
preflight.add_argument("run_dir", type=Path)
preflight.add_argument("--input-jsonl", type=Path, required=True)
preflight.set_defaults(func=command_retrieval_preflight)
```

- [ ] **Step 4: Run focused tests**

```bash
.venv/bin/python -m unittest \
  tests.test_storm_research_cli.StormResearchCLITests.test_retrieval_preflight_reports_expected_record_ids_and_max_errors \
  tests.test_storm_research_cli.StormResearchCLITests.test_retrieval_preflight_passes_for_valid_max_inputs_without_receipt -v
```

Expected: both tests pass; no `20-retrieval.json` receipt is created.

---

### Task 3: Add Retrieval Provenance Preparation

**Files:**
- Modify: `scripts/storm_research.py`
- Modify: `tests/test_storm_research_cli.py`
- Modify: `README.md`
- Modify: `references/research-protocol.md`

- [ ] **Step 1: Add a failing test for `retrieval-prepare`**

Add this test to `tests/test_storm_research_cli.py`:

```python
def test_retrieval_prepare_writes_matching_execution_provenance(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        run = self.planned_run(
            workspace,
            profile="maximal_full_dossier",
            assurance_target="captured_host_execution",
        )
        retrieval = self.write_retrieval_inputs(run, workspace, maximal=True)
        transcript = workspace / "retrieval-transcript.txt"
        transcript.write_text(
            "host searched PubMed and OpenAlex\n"
            "host screened include and exclude candidates\n"
            "host captured full text and resolver snapshots\n",
            encoding="utf-8",
        )
        plan_receipt = json.loads(
            (run / "state/generations/g0001/receipts/10-plan.json").read_text(encoding="utf-8")
        )
        started_at = plan_receipt["completed_at"]
        completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        output = workspace / "retrieval-execution.json"
        result = self.invoke(
            "retrieval-prepare", str(run),
            "--input-jsonl", str(retrieval),
            "--transcript", str(transcript),
            "--context-id", "retrieval-context-1",
            "--provider", "openai",
            "--model", "gpt-5.5",
            "--runner", "codex-exec",
            "--execution-id", "retrieval-exec-1",
            "--started-at", started_at,
            "--completed-at", completed_at,
            "--to", str(output),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["stage"], "retrieval")
        self.assertEqual(payload["execution_kind"], "host_execution")
        self.assertEqual(payload["input_artifacts"], {
            "artifacts/research/execution/retrieval-input.jsonl": sha256_file(retrieval)
        })
        self.assertIn("GA001", payload["record_ids"])
        self.assertEqual(payload["transcript_sha256"], sha256_file(transcript))
        result = self.invoke(
            "ingest", str(run),
            "--input-jsonl", str(retrieval),
            "--execution-provenance", str(output),
            "--execution-transcript", str(transcript),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
```

- [ ] **Step 2: Implement `command_retrieval_prepare`**

In `scripts/storm_research.py`, add:

```python
def command_retrieval_prepare(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.RETRIEVAL, package_hash)
    brief = verify_current_brief_view(layout, generation)
    if brief.get("assurance_target") != "captured_host_execution":
        raise CLIContractError("retrieval-prepare is only valid for captured_host_execution")
    preflight = _retrieval_preflight_payload(layout, generation, args.input_jsonl)
    if not preflight["ok"]:
        raise RetrievalGateError("retrieval-preflight failed: " + "; ".join(preflight["errors"]))
    transcript_text = args.transcript.read_text(encoding="utf-8")
    transcript_errors = _execution_transcript_errors(transcript_text, label="retrieval")
    if transcript_errors:
        raise CLIContractError("; ".join(transcript_errors))
    payload = {
        "schema_version": "2.0",
        "provenance_id": "EPROV-" + uuid.uuid4().hex[:12],
        "stage": "retrieval",
        "execution_kind": "host_execution",
        "context_id": args.context_id,
        "provider": args.provider,
        "model": args.model,
        "runner": args.runner,
        "execution_id": args.execution_id,
        "started_at": args.started_at,
        "completed_at": args.completed_at,
        "transcript_sha256": sha256_file(args.transcript),
        "input_artifacts": {
            "artifacts/research/execution/retrieval-input.jsonl": sha256_file(args.input_jsonl)
        },
        "record_ids": preflight["expected_record_ids"],
        "provider_signed": False,
    }
    target = args.to
    atomic_write_json(target, payload)
    _print_json({
        "schema_version": "2.0",
        "ok": True,
        "provenance": str(target),
        "record_count": len(payload["record_ids"]),
        "record_ids": payload["record_ids"],
    })
    return EXIT_OK
```

- [ ] **Step 3: Wire the parser**

Add:

```python
prepare = sub.add_parser("retrieval-prepare")
prepare.add_argument("run_dir", type=Path)
prepare.add_argument("--input-jsonl", type=Path, required=True)
prepare.add_argument("--transcript", type=Path, required=True)
prepare.add_argument("--context-id", required=True)
prepare.add_argument("--provider", required=True)
prepare.add_argument("--model", required=True)
prepare.add_argument("--runner", required=True)
prepare.add_argument("--execution-id", required=True)
prepare.add_argument("--started-at", required=True)
prepare.add_argument("--completed-at", required=True)
prepare.add_argument("--to", type=Path, required=True)
prepare.set_defaults(func=command_retrieval_prepare)
```

- [ ] **Step 4: Run the focused test**

```bash
.venv/bin/python -m unittest \
  tests.test_storm_research_cli.StormResearchCLITests.test_retrieval_prepare_writes_matching_execution_provenance -v
```

Expected: test passes and `ingest` accepts the prepared provenance.

---

### Task 4: Make Max Helper Output Honest

**Files:**
- Modify: `scripts/storm_research.py`
- Modify: `tests/test_storm_research_cli.py`
- Modify: `README.md`

- [ ] **Step 1: Implement Max compatibility warnings for helper commands**

Add this helper to `scripts/storm_research.py`:

```python
def _retrieval_helper_warning(layout: RunLayout, generation: int) -> tuple[str, list[str]]:
    brief = verify_current_brief_view(layout, generation)
    if (
        brief.get("research_profile") == "maximal_full_dossier"
        and brief.get("assurance_target") == "captured_host_execution"
    ):
        return (
            "insufficient_for_max_captured",
            [
                "capture-source/ingest-dir only create low-fidelity manual capture records.",
                "Max captured retrieval still needs typed search_run, candidate screening, resolver outcomes, publisher/full-text capture, search_wave/gap_assessment, retrieval-preflight, and retrieval-prepare.",
            ],
        )
    return "not_checked", []
```

In `command_capture_source()` and `command_ingest_dir()`, add `max_compatibility` and append these warnings to the JSON output.

- [ ] **Step 2: Update `test_capture_source_warns_when_used_for_max_captured_retrieval`**

Ensure the test from Task 1 now passes.

- [ ] **Step 3: Update README helper wording**

In `README.md` under `### 3. Ingest`, replace the helper description with this language:

```markdown
`capture-source` and `ingest-dir` are convenience builders for simple captures and fixture-like batches. They are not sufficient by themselves for `maximal_full_dossier` with `captured_host_execution`, because Max also requires executed search runs, candidate screening, resolver snapshots, full-text/publisher coverage, search waves, gap assessments, and execution provenance. For Max, use them only as partial capture builders, then enrich the JSONL and run `retrieval-preflight` before `ingest`.
```

- [ ] **Step 4: Run docs and helper tests**

```bash
.venv/bin/python -m unittest \
  tests.test_storm_research_cli.StormResearchCLITests.test_capture_source_warns_when_used_for_max_captured_retrieval \
  tests.test_library_contract -v
```

Expected: tests pass.

---

### Task 5: Fix Gap Assessment Causality Without Weakening Final Validation

**Files:**
- Modify: `schemas/retrieval-record.schema.json`
- Modify: `scripts/contract_io.py`
- Modify: `scripts/normalize_retrieval.py`
- Modify: `scripts/storm_research.py`
- Modify: `scripts/validate_package.py`
- Test: `tests/test_normalize_retrieval.py`
- Test: `tests/test_storm_research_cli.py`
- Test: `tests/test_validate_package.py`

- [ ] **Step 1: Add failing tests for deferred review binding**

Add to `tests/test_normalize_retrieval.py`:

```python
def test_gap_assessment_accepts_missing_review_concern_at_ingest(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        records = [
            valid_search_run_record(1, pass_kind="gap_fill"),
            valid_search_wave_record(1, search_run_ids=["SR001"], new_candidate_ids=[]),
            valid_search_wave_record(2, search_run_ids=["SR001"], new_candidate_ids=[]),
            valid_gap_assessment_record(supporting_search_run_ids=["SR001"]),
        ]
        records[-1].pop("review_concern_id", None)
        for record in records:
            if record.get("record_kind") == "search_run":
                artifact = workspace / str(record["raw_artifact"])
                artifact.write_text('{"results":[]}\n', encoding="utf-8")
                record["snapshot_sha256"] = sha256_file(artifact)
                request = workspace / str(record["request_artifact"])
                request.write_text('{"query":"gap"}\n', encoding="utf-8")
                record["request_sha256"] = sha256_file(request)
        errors = []
        for record in records:
            errors.extend(validate_retrieval_input_record(record))
        self.assertEqual(errors, [])
```

Add to `tests/test_validate_package.py`:

```python
def test_max_validation_fails_when_terminal_gap_lacks_review_closure(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        run = self.valid_max_package(workspace)
        audit_path = run / "work/generations/g0001/artifacts/research/retrieval-audit.jsonl"
        rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
        for row in rows:
            if row.get("record_kind") == "gap_assessment":
                row.pop("review_concern_id", None)
        audit_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        result = self.invoke_validate(run)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("terminal gap disposition requires independent review closure", result.stderr)
```

- [ ] **Step 2: Make `review_concern_id` optional in retrieval input**

In `schemas/retrieval-record.schema.json`, remove `review_concern_id` from the required list for `gap_assessment`, but keep the property pattern.

In `scripts/contract_io.py`, change:

```python
if not re.fullmatch(r"RC\d{3}", str(review_concern_id)):
    errors.append("review_concern_id must match RC followed by three digits")
```

to:

```python
if review_concern_id is not None and not re.fullmatch(r"RC\d{3}", str(review_concern_id)):
    errors.append("review_concern_id must match RC followed by three digits")
```

Remove the ingest-time branch that requires it for every terminal state.

- [ ] **Step 3: Move review binding to final validation**

In `scripts/validate_package.py`, when validating Max saturation, require each terminal `gap_assessment` to be closed by either:

```python
assessment.get("review_concern_id") in closed_review_concern_ids
```

or a review-loop concern with:

```python
target_kind in {"gap", "gap_assessment"}
target_id in {gap_id, assessment_id}
disposition in {"addressed", "accepted_uncertainty", "waived"}
```

and reject `waived` without a reason.

- [ ] **Step 4: Run focused tests**

```bash
.venv/bin/python -m unittest \
  tests.test_normalize_retrieval \
  tests.test_validate_package -v
```

Expected: tests pass; ingest no longer requires a future review concern ID, but final validation still fails without review closure.

---

### Task 6: Make Search-Wave Material Delta Recomputed-Only

**Files:**
- Modify: `schemas/retrieval-record.schema.json`
- Modify: `scripts/contract_io.py`
- Modify: `scripts/storm_research.py`
- Modify: `tests/test_normalize_retrieval.py`
- Modify: `tests/test_storm_research_cli.py`

- [ ] **Step 1: Add failing tests for unknown material delta during retrieval**

Add to `tests/test_normalize_retrieval.py`:

```python
def test_search_wave_allows_null_material_delta_for_pre_findings_retrieval(self) -> None:
    record = valid_search_wave_record(1, search_run_ids=["SR001"], new_candidate_ids=["K001"])
    record["material_delta"] = None
    self.assertEqual(validate_retrieval_input_record(record), [])
```

Add to `tests/test_storm_research_cli.py`:

```python
def test_findings_recomputes_null_search_wave_material_delta(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        run = self.retrieved_run(
            workspace,
            profile="maximal_full_dossier",
            register_findings=False,
            gap_fill_query_ids={"Q001"},
        )
        audit_path = run / "work/generations/g0001/artifacts/research/retrieval-audit.jsonl"
        rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
        for row in rows:
            if row.get("record_kind") == "search_wave":
                row["material_delta"] = None
        audit_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        findings = self.write_findings_inputs(run, workspace)
        result = self.invoke("findings", str(run), "--findings-jsonl", str(findings))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        coverage = json.loads(
            (run / "work/generations/g0001/artifacts/research/finding-coverage.json").read_text(encoding="utf-8")
        )
        wave = coverage["search_waves"][0]
        self.assertIsNone(wave["submitted_material_delta"])
        self.assertIsInstance(wave["material_delta"], int)
```

- [ ] **Step 2: Allow `material_delta: null` in schema and contract**

In `schemas/retrieval-record.schema.json`, change:

```json
"material_delta": {"type": "integer", "minimum": 0}
```

to:

```json
"material_delta": {"type": ["integer", "null"], "minimum": 0}
```

In `scripts/contract_io.py`, change the `search_wave material_delta` check to:

```python
delta = data.get("material_delta")
if delta is not None and (not isinstance(delta, int) or isinstance(delta, bool) or delta < 0):
    errors.append("search_wave material_delta must be null or a non-negative integer")
```

- [ ] **Step 3: Keep final recomputation strict**

In `findings_coverage()` in `scripts/storm_research.py`, keep existing recomputation. Only emit a declaration error when submitted delta is not `None` and differs:

```python
if submitted_delta is not None and submitted_delta != material_delta:
    declaration_errors.append(
        f"{wave.get('wave_id')} submitted material_delta does not recompute"
    )
```

This is already close to the current code; verify it still handles `None`.

- [ ] **Step 4: Run focused tests**

```bash
.venv/bin/python -m unittest \
  tests.test_normalize_retrieval \
  tests.test_storm_research_cli -v
```

Expected: tests pass; retrieval no longer asks the host to know post-findings material novelty in advance.

---

### Task 7: Make Explain/Doctor Profile-Aware

**Files:**
- Modify: `scripts/storm_research.py`
- Modify: `tests/test_storm_research_cli.py`
- Modify: `README.md`
- Modify: `references/quality-gates.md`

- [ ] **Step 1: Add suggestions to `explain` payload**

In `command_explain()`, include:

```python
"suggestions": _doctor_suggestions_for_run(layout, generation, status.get("next_stage")),
```

Implement:

```python
def _doctor_suggestions_for_run(layout: RunLayout, generation: int, next_stage: object) -> list[str]:
    brief = verify_current_brief_view(layout, generation)
    stage = str(next_stage or "")
    if stage == "retrieval" and (
        brief.get("research_profile") == "maximal_full_dossier"
        and brief.get("assurance_target") == "captured_host_execution"
    ):
        return [
            "build typed retrieval JSONL with search_run, candidate, capture, search_wave, and gap_assessment records",
            "do not rely on capture-source/ingest-dir alone for Max captured retrieval",
            "run storm_research.py retrieval-preflight RUN_DIR --input-jsonl retrieval-records.jsonl",
            "run storm_research.py retrieval-prepare RUN_DIR --input-jsonl retrieval-records.jsonl --transcript retrieval-transcript.txt --context-id ... --provider ... --model ... --runner ... --execution-id ... --started-at ... --completed-at ... --to retrieval-execution.json",
            "run storm_research.py ingest RUN_DIR --input-jsonl retrieval-records.jsonl --execution-provenance retrieval-execution.json --execution-transcript retrieval-transcript.txt",
        ]
    return _doctor_suggestions(next_stage)
```

- [ ] **Step 2: Keep generic suggestions for non-Max runs**

Add this test:

```python
def test_explain_keeps_generic_retrieval_suggestions_for_default_profile(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        run = self.planned_run(workspace, profile="default_full_dossier")
        result = self.invoke("explain", str(run))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        suggestions = " ".join(payload.get("suggestions", []))
        self.assertIn("capture-source", suggestions)
        self.assertIn("ingest", suggestions)
```

- [ ] **Step 3: Run focused tests**

```bash
.venv/bin/python -m unittest \
  tests.test_storm_research_cli.StormResearchCLITests.test_explain_for_max_captured_retrieval_points_to_preflight_and_prepare \
  tests.test_storm_research_cli.StormResearchCLITests.test_explain_keeps_generic_retrieval_suggestions_for_default_profile -v
```

Expected: both tests pass.

---

### Task 8: Update Documentation And Migration Notes

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `agents/interface.yaml`
- Modify: `references/research-protocol.md`
- Modify: `references/retrieval-adapters.md`
- Modify: `references/quality-gates.md`
- Modify: `docs/migration-v3-to-v4.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/superpowers/plans/2026-07-06-max-mode-repair.md`

- [ ] **Step 1: Replace the stale saturation-assessment example**

In `docs/superpowers/plans/2026-07-06-max-mode-repair.md`, replace:

```json
"record_kind": "gap_assessment"
```

with:

```json
"record_kind": "gap_assessment"
```

and update the surrounding prose to say terminal gap assessment.

- [ ] **Step 2: Document the Max retrieval path**

Add this compact command sequence to README and `references/research-protocol.md`:

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" retrieval-preflight "$RUN_DIR" \
  --input-jsonl retrieval-records.jsonl

"$PY" "$SKILL_ROOT/scripts/storm_research.py" retrieval-prepare "$RUN_DIR" \
  --input-jsonl retrieval-records.jsonl \
  --transcript retrieval-transcript.txt \
  --context-id "$HOST_CONTEXT_ID" \
  --provider "$PROVIDER" \
  --model "$MODEL" \
  --runner "$RUNNER" \
  --execution-id "$EXECUTION_ID" \
  --started-at "$STARTED_AT" \
  --completed-at "$COMPLETED_AT" \
  --to retrieval-execution.json

"$PY" "$SKILL_ROOT/scripts/storm_research.py" ingest "$RUN_DIR" \
  --input-jsonl retrieval-records.jsonl \
  --execution-provenance retrieval-execution.json \
  --execution-transcript retrieval-transcript.txt
```

- [ ] **Step 3: Make SKILL and interface prompt reflect the new path**

In `SKILL.md`, keep the body short but include:

```markdown
For Max captured retrieval, do `retrieval-preflight` then `retrieval-prepare` before `ingest`; `capture-source`/`ingest-dir` are partial capture helpers, not Max-complete retrieval.
```

In `agents/interface.yaml`, keep the default prompt under host length limits and include:

```yaml
default_prompt: "Run init first. For Max captured retrieval: typed records -> retrieval-preflight -> retrieval-prepare -> ingest. capture-source/ingest-dir alone are not Max-complete. If blocked, status/explain only; no topic findings."
```

- [ ] **Step 4: Run docs contract tests**

```bash
.venv/bin/python -m unittest tests.test_library_contract -v
```

Expected: tests pass and resource boundary remains within budget.

---

### Task 9: End-To-End Verification

**Files:**
- No source edits expected unless tests fail.

- [ ] **Step 1: Run focused retrieval suite**

```bash
.venv/bin/python -m unittest \
  tests.test_normalize_retrieval \
  tests.test_storm_research_cli \
  tests.test_evidence_stage \
  tests.test_validate_package -v
```

Expected: all tests pass.

- [ ] **Step 2: Run full checks**

```bash
.venv/bin/python scripts/run_checks.py --all
```

Expected: unit tests, compile, schema checks, and Yao validation pass.

- [ ] **Step 3: Run distribution checks**

```bash
.venv/bin/python scripts/run_checks.py --dist
```

Expected: OpenAI, Claude, generic, and VS Code adapters validate; `dist/storm-deepresearch-skill.zip` is regenerated.

- [ ] **Step 4: Record the archive hash**

```bash
shasum -a 256 dist/storm-deepresearch-skill.zip
```

Expected: output contains the new package SHA-256.

---

### Task 10: Re-run The Isolated PBCT Max Retrieval Acceptance

**Files:**
- Modify only this plan file to record the result.

**2026-07-07 execution note:** The distribution archive was unpacked to
`/private/tmp/storm-pbct-max-retrieval-repair.q0Yv56`, a fresh Python 3.11
virtual environment was created, and `requirements-dev.lock` installed
successfully. The natural-language `codex exec` acceptance did not start the
host workflow because Codex returned a usage-limit error before tool work:
`You've hit your usage limit ... try again at 4:00 PM`. Therefore Task 10 is
not accepted from that attempt; no PBCT topic findings were produced by that
attempt.

**2026-07-07 resumed execution note:** After usage recovered, the same isolated
package was used for the natural-language host acceptance. The host selected
`maximal_full_dossier` and `captured_host_execution`, initialized the governed
run, registered P1, committed `plan`, and then stopped at `retrieval` without
claiming a final report. Local verification showed `last_valid_stage=plan`,
`next_stage=retrieval`, and `explain` returned Max-specific suggestions for
typed retrieval records, `retrieval-preflight`, `retrieval-prepare`, and
`ingest`. This satisfies acceptance path 2 for this repair.

- [x] **Step 1: Unpack the new dist to a fresh temp directory**

```bash
TMPDIR="$(mktemp -d /private/tmp/storm-pbct-max-retrieval-repair.XXXXXX)"
ditto -x -k dist/storm-deepresearch-skill.zip "$TMPDIR"
uv venv --python 3.11 "$TMPDIR/storm-deepresearch-skill/.venv"
uv pip install --python "$TMPDIR/storm-deepresearch-skill/.venv/bin/python" -r "$TMPDIR/storm-deepresearch-skill/requirements-dev.lock"
```

- [x] **Step 2: Run the natural-language host acceptance**

```bash
codex exec --skip-git-repo-check --sandbox workspace-write \
  "使用 $TMPDIR/storm-deepresearch-skill 这个技能，以 Max 模式研究 proton boron capture therapy，默认输出中文。"
```

- [x] **Step 3: Inspect the observed state**

If the host completes retrieval, verify:

```bash
"$TMPDIR/storm-deepresearch-skill/.venv/bin/python" \
  "$TMPDIR/storm-deepresearch-skill/scripts/storm_research.py" status "$RUN_DIR"
```

Expected if retrieval succeeds:

```json
{
  "last_valid_stage": "retrieval",
  "next_stage": "evidence"
}
```

Expected if retrieval is still blocked:

```json
{
  "state": "planned",
  "next_stage": "retrieval"
}
```

In either case, the host final answer must not include topic findings unless `validate` passed.

- [x] **Step 4: Acceptance criteria for this repair**

This repair is accepted when a real host does at least one of the following:

1. Successfully uses `retrieval-preflight` and `retrieval-prepare`, then commits `20-retrieval.json` with `retrieval-audit.jsonl`, `source-register.jsonl`, retrieval provenance, and transcript.
2. Stops at retrieval but returns profile-aware `status`/`explain` with the new Max retrieval repair path and no PBCT topic findings.

Full PBCT Max delivery is a later acceptance target; this repair only proves the retrieval execution path is no longer self-contradictory.

---

## Completion Definition

This repair is complete only when:

1. Docs no longer mention the former saturation-assessment name as a record kind.
2. `capture-source` and `ingest-dir` honestly warn that they are insufficient for Max captured retrieval.
3. `retrieval-preflight` reports Max retrieval failures before receipt-writing.
4. `retrieval-prepare` generates provenance that `ingest` accepts.
5. Gap terminal review closure is required by final validation, not invented during retrieval.
6. `search_wave.material_delta` can be unknown at retrieval and is recomputed after findings.
7. `explain` gives Max-specific repair commands.
8. `run_checks.py --all` and `run_checks.py --dist` pass.
9. A fresh isolated host run confirms the blocked-output behavior remains intact and the retrieval repair path is visible.
