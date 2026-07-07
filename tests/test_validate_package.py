from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import tests.test_render_stage as render_stage_helpers
from scripts.harness_io import canonical_json_sha256, sha256_file
from scripts.report_traceability import citation_index
from scripts.run_state import RunLayout
from scripts.validate_package import (
    RENDER_ARTIFACTS,
    _structural_checks,
    _profile_prompt_evidence_errors,
    _validate_review_loop_artifact,
    _validate_review_loop_summary,
    _execution_assurance_errors,
    _validate_maximal_completeness,
)
from tests.governed_fixtures import (
    valid_brief_v2,
    valid_storm_lens_artifact,
    valid_source_v2,
)


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/storm_research.py"


class ValidatePackageTests(unittest.TestCase):
    def test_maximal_source_count_cannot_replace_saturation(self) -> None:
        brief = valid_brief_v2()
        brief["research_profile"] = "maximal_full_dossier"
        sources = [valid_source_v2(index) for index in range(1, 89)]
        findings = [{
            "finding_id": f"F{index:03d}",
            "status": "usable",
            "source_ids": [f"S{index:03d}"],
        } for index in range(1, 89)]
        citation_keys = list(citation_index(sources))[:30]
        report = "\n".join(
            f"Evidence [^{key}]" for key in citation_keys
        )
        errors = _validate_maximal_completeness(
            brief,
            sources,
            [{"source_id": f"S{index:03d}", "candidate_id": f"K{index:03d}"} for index in range(1, 89)],
            [],
            [{}] * 24,
            findings,
            [{"material": True}] * 30,
            {"sections": [{}] * 10},
            [{"source_ids": [f"S{index:03d}"]} for index in range(1, 31)],
            report,
            {"saturation_assessments": []},
        )
        self.assertIn(
            "maximal_full_dossier requires retrieval saturation assessments; source count cannot close Max",
            errors,
        )
        self.assertFalse(any("requires at least 88" in error for error in errors), errors)

    def test_validation_requires_retrieval_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            (artifact_root(run) / "research/retrieval-audit.jsonl").unlink()
            result = self.validate(run)
            self.assertEqual(result.returncode, 4)
            self.assertIn("retrieval-audit.jsonl", result.stderr)

    def test_validation_reports_academic_retrieval_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            result = self.validate(run)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(
                (artifact_root(run) / "validation/validation-report.json").read_text()
            )
            checks = {item["check_id"]: item for item in report["checks"]}
            self.assertEqual(checks["academic-retrieval-integrity"]["status"], "pass")

    def validate(self, run: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), "validate", str(run)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_valid_governed_run_commits_reports_and_validation_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            result = self.validate(run)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            artifacts = artifact_root(run)
            payload = json.loads(
                (artifacts / "validation/validation-report.json").read_text(encoding="utf-8")
            )
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["schema_version"], "2.0")
            self.assertEqual(
                payload["assurance_level"], "validated_artifact_contract_only"
            )
            self.assertIn("public_release", payload["not_valid_for"])
            self.assertEqual(payload["summary"]["failed"], 0)
            depth = payload["measurements"]["report_depth"]
            self.assertEqual(depth["policy"], "bounded")
            self.assertGreater(depth["raw_body"], depth["net_body"])
            self.assertGreater(depth["citation_markers"], 0)
            self.assertTrue((artifacts / "validation/validation-report.md").is_file())
            self.assertTrue((run / "state/generations/g0001/receipts/70-validation.json").is_file())

    def test_diagnostic_debt_blocks_final_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            artifacts = artifact_root(run)
            debt = {
                "schema_version": "2.0",
                "run_intent": "diagnostic_rehearsal",
                "status": "completed_with_blockers",
                "not_valid_for": ["user_delivery", "public_release"],
                "debts": [{
                    "debt_id": "BD001",
                    "stage": "retrieval",
                    "severity": "blocking",
                    "errors": ["fixture diagnostic debt"],
                    "input_artifacts": {},
                    "measurements": {},
                    "disposition": "diagnostic_rehearsal_only",
                    "release_blocking": True,
                    "validation_blocking": True,
                    "created_at": "2026-06-23T00:00:00Z",
                }],
            }
            (artifacts / "research/blocking-debt-ledger.json").write_text(
                json.dumps(debt), encoding="utf-8"
            )
            result = self.validate(run)
            self.assertEqual(result.returncode, 8)
            self.assertIn("diagnostic-rehearsal", result.stderr)
            self.assertIn("blocking-debt-ledger.json", result.stderr)

    def test_maximal_governed_run_uses_open_ended_depth_and_review_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp), profile="maximal_full_dossier")
            result = self.validate(run)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            artifacts = artifact_root(run)
            payload = json.loads(
                (artifacts / "validation/validation-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["measurements"]["report_depth"]["policy"], "open_ended")
            peer_review = json.loads((artifacts / "research/peer-review.json").read_text(encoding="utf-8"))
            self.assertEqual(peer_review["summary"]["review_loop_policy"], "concern_driven_until_clear")
            review_loop = json.loads((artifacts / "research/review-loop.json").read_text(encoding="utf-8"))
            self.assertEqual(review_loop["summary"]["final_editor_decision"], "accept")
            self.assertEqual(review_loop["summary"]["unresolved_concerns"], 0)
            self.assertGreaterEqual(review_loop["summary"]["round_count"], 1)
            self.assertEqual(review_loop["final_integrity"]["status"], "pass")
            metrics = payload["measurements"]["max_review_loop"]
            self.assertLess(metrics["source_count"], 80)
            self.assertEqual(metrics["material_claim_count"], 12)
            self.assertEqual(metrics["search_waves"], 2)
            self.assertEqual(metrics["decision_path"], ["accept"])
            self.assertEqual(metrics["concerns_unresolved"], 0)
            self.assertEqual(metrics["final_integrity_status"], "pass")
            outcomes = payload["review_outcomes"]
            self.assertEqual(outcomes["decision_path"], ["accept"])
            self.assertEqual(outcomes["concerns_opened"], 0)
            self.assertEqual(outcomes["retrieval_cycles_triggered"], 0)
            self.assertEqual(outcomes["sources_added"], 0)
            self.assertEqual(outcomes["claims_added"], 0)
            self.assertEqual(outcomes["claims_downgraded"], 0)
            self.assertEqual(outcomes["claims_removed"], 0)
            self.assertEqual(outcomes["sections_revised"], 0)
            self.assertEqual(outcomes["storm_conflicts_closed"], 0)
            self.assertEqual(outcomes["storm_blind_spots_disclosed"], 0)
            self.assertEqual(outcomes["final_integrity"], "pass")

    def test_max_review_loop_fails_when_terminal_gap_lacks_review_closure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp), profile="maximal_full_dossier")
            artifacts = artifact_root(run)
            audit_path = artifacts / "research/retrieval-audit.jsonl"
            rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
            for row in rows:
                if row.get("record_kind") == "gap_assessment":
                    row.pop("review_concern_id", None)
            audit_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

            loop_path = artifacts / "research/review-loop.json"
            loop = json.loads(loop_path.read_text(encoding="utf-8"))
            round_record = loop["rounds"][0]
            for panel_review in round_record["panel_reviews"]:
                panel_review["concerns"] = []
            round_record["required_concerns"] = []
            round_record["editor_review"]["concern_ids"] = []
            round_record["round_sha256"] = canonical_json_sha256({
                key: value for key, value in round_record.items()
                if key != "round_sha256"
            })
            loop_path.write_text(json.dumps(loop), encoding="utf-8")

            brief = json.loads((run / "brief.json").read_text(encoding="utf-8"))
            errors = _validate_review_loop_artifact(artifacts, brief)
            self.assertIn(
                "terminal gap disposition requires independent review closure",
                "; ".join(errors),
            )

    def test_captured_execution_validation_reports_achieved_assurance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(
                Path(tmp), assurance_target="captured_host_execution"
            )
            result = self.validate(run)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(
                (artifact_root(run) / "validation/validation-report.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(
                payload["assurance_level"], "validated_captured_host_execution"
            )
            self.assertEqual(payload["not_valid_for"], [])
            self.assertFalse(payload["provider_signed"])

    def test_captured_execution_requires_profile_selection_evidence_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief = valid_brief_v2()
            brief["assurance_target"] = "captured_host_execution"
            brief["profile_selection"]["evidence_ref"] = "inputs/profile-selection-evidence.txt"
            brief["profile_selection"]["evidence_sha256"] = "a" * 64
            brief_path = root / "brief.json"
            brief_path.write_text(json.dumps(brief), encoding="utf-8")

            self.assertIn(
                "profile_selection evidence artifact is missing",
                _profile_prompt_evidence_errors(brief, brief_path),
            )
            evidence = root / "profile-selection-evidence.txt"
            evidence.write_text("user selected captured delivery\n", encoding="utf-8")
            self.assertIn(
                "profile_selection evidence artifact hash mismatch",
                _profile_prompt_evidence_errors(brief, brief_path),
            )
            brief["profile_selection"]["evidence_sha256"] = sha256_file(evidence)
            self.assertEqual(_profile_prompt_evidence_errors(brief, brief_path), [])

    def test_captured_execution_detects_transcript_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(
                Path(tmp), assurance_target="captured_host_execution"
            )
            transcript = artifact_root(run) / "research/execution/draft-transcript.txt"
            transcript.write_text("changed", encoding="utf-8")
            brief = json.loads((run / "brief.json").read_text(encoding="utf-8"))
            errors = _execution_assurance_errors(
                RunLayout(run),
                1,
                brief,
            )
            self.assertIn("draft execution transcript hash mismatch", errors)

    def test_maximal_captured_execution_rejects_shared_contexts_and_all_include(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(
                Path(tmp), profile="maximal_full_dossier",
                assurance_target="captured_host_execution",
            )
            artifacts = artifact_root(run)
            retrieval_provenance = artifacts / "research/execution/retrieval-provenance.json"
            draft_provenance = artifacts / "research/execution/draft-provenance.json"
            retrieval_payload = json.loads(retrieval_provenance.read_text(encoding="utf-8"))
            draft_payload = json.loads(draft_provenance.read_text(encoding="utf-8"))
            draft_payload["context_id"] = retrieval_payload["context_id"]
            draft_payload["execution_id"] = retrieval_payload["execution_id"]
            draft_provenance.write_text(json.dumps(draft_payload), encoding="utf-8")
            audit_path = artifacts / "research/retrieval-audit.jsonl"
            audit = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
            for record in audit:
                if record.get("record_kind") == "candidate":
                    record["disposition"] = "include"
            audit_path.write_text("".join(json.dumps(row) + "\n" for row in audit), encoding="utf-8")
            brief = json.loads((run / "brief.json").read_text(encoding="utf-8"))
            errors = _execution_assurance_errors(
                RunLayout(run),
                1,
                brief,
            )
            self.assertIn(
                "maximal captured execution requires three distinct execution contexts",
                errors,
            )
            self.assertIn(
                "maximal captured execution candidate pool cannot be all include",
                errors,
            )

    def test_maximal_captured_execution_revalidates_raw_search_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(
                Path(tmp), profile="maximal_full_dossier",
                assurance_target="captured_host_execution",
            )
            artifacts = artifact_root(run)
            audit = [
                json.loads(line)
                for line in (artifacts / "research/retrieval-audit.jsonl")
                .read_text(encoding="utf-8").splitlines()
            ]
            search = next(row for row in audit if row.get("record_kind") == "search_run")
            raw = run / "work/generations/g0001/evidence-cache" / str(search["raw_artifact"])
            raw.write_text(
                "Captured search transcript. Results summarized in candidate records.\n",
                encoding="utf-8",
            )
            brief = json.loads((run / "brief.json").read_text(encoding="utf-8"))
            errors = _execution_assurance_errors(RunLayout(run), 1, brief)
            self.assertIn(
                f"search run {search['search_run_id']} response must be structured JSON with inspectable result rows",
                errors,
            )

    def test_maximal_validation_requires_review_loop_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp), profile="maximal_full_dossier")
            (artifact_root(run) / "research/review-loop.json").unlink()
            result = self.validate(run)
            self.assertEqual(result.returncode, 8)
            self.assertIn("receipt-chain", result.stdout + result.stderr)

    def test_maximal_validation_rejects_unresolved_review_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp), profile="maximal_full_dossier")
            loop_path = artifact_root(run) / "research/review-loop.json"
            payload = json.loads(loop_path.read_text(encoding="utf-8"))
            payload["summary"]["final_editor_decision"] = "major_revision"
            payload["summary"]["unresolved_concerns"] = 1
            loop_path.write_text(json.dumps(payload), encoding="utf-8")
            brief = json.loads((run / "brief.json").read_text(encoding="utf-8"))
            errors = _validate_review_loop_artifact(artifact_root(run), brief)
            self.assertIn(
                "maximal_full_dossier review loop final editor decision must be accept",
                errors,
            )

    def test_review_loop_summary_policy_matches_profile(self) -> None:
        brief = valid_brief_v2()
        p4 = valid_storm_lens_artifact("P4", "a" * 64, {}, target_sha256="b" * 64)
        summary = {
            "decision": "passed",
            "review_loop_policy": "concern_driven_until_clear",
            "p4_repair_actions": 0,
        }
        self.assertIn(
            "peer review loop policy must be single_pass_external_review",
            _validate_review_loop_summary(brief, summary, p4),
        )
        brief["research_profile"] = "maximal_full_dossier"
        brief["length_contract"] = {
            "unit": "words",
            "policy": "open_ended",
            "content_standard": "evidence_led",
        }
        self.assertEqual(_validate_review_loop_summary(brief, summary, p4), [])

    def test_validate_is_idempotent_after_validation_receipt_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            first = self.validate(run)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            second = self.validate(run)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)

    def test_strict_lens_run_validates_phase_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp), strict_lens=True)
            result = self.validate(run)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(
                (artifact_root(run) / "validation/validation-report.json").read_text(encoding="utf-8")
            )
            checks = {item["check_id"]: item for item in payload["checks"]}
            self.assertEqual(checks["storm-lens-phase-order"]["status"], "pass")

    def test_collect_copies_only_validated_deliverables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = build_valid_governed_run(workspace)
            result = self.validate(run)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            target = workspace / "collected"
            result = subprocess.run(
                [
                    sys.executable, str(CLI), "collect", str(run), "--to", str(target),
                    "--allow-artifact-contract",
                ],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((target / "report.md").is_file())
            self.assertTrue((target / "exports/report.html").is_file())
            self.assertTrue((target / "exports/report.pdf").is_file())
            self.assertTrue((target / "validation/validation-report.json").is_file())
            self.assertFalse((target / "audit").exists())
            self.assertFalse((target / "work").exists())
            self.assertFalse((target / "state").exists())
            manifest = json.loads((target / "collect-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["files"]["report.md"],
                sha256_file(target / "report.md"),
            )
            self.assertTrue(manifest["artifact_contract_override"])
            self.assertFalse(manifest["audit_bundle_included"])

    def test_captured_collect_includes_audit_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = build_valid_governed_run(
                workspace, assurance_target="captured_host_execution"
            )
            result = self.validate(run)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            target = workspace / "collected"
            result = subprocess.run(
                [
                    sys.executable, str(CLI), "collect", str(run), "--to", str(target),
                ],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((target / "report.md").is_file())
            self.assertTrue((target / "audit/research/retrieval-audit.jsonl").is_file())
            self.assertTrue((target / "audit/research/source-plan.json").is_file())
            self.assertTrue((target / "audit/research/execution/retrieval-provenance.json").is_file())
            manifest = json.loads((target / "collect-manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["audit_bundle_included"])
            self.assertEqual(
                manifest["files"]["audit/research/retrieval-audit.jsonl"],
                sha256_file(target / "audit/research/retrieval-audit.jsonl"),
            )

    def test_artifact_contract_collect_requires_explicit_fixture_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = build_valid_governed_run(workspace)
            result = self.validate(run)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(
                [
                    sys.executable, str(CLI), "collect", str(run),
                    "--to", str(workspace / "collected"),
                ],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 4)
            self.assertIn("validated_captured_host_execution", result.stderr)

    def test_validator_rejects_forged_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            receipt = run / "state/generations/g0001/receipts/30-evidence.json"
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            payload["validator_sha256"] = "0" * 64
            receipt.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            result = self.validate(run)
            self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
            self.assertIn("receipt", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/70-validation.json").exists())

    def test_validator_rejects_markdown_named_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            bad = artifact_root(run) / "research/uncertainty-ledger.json"
            bad.write_text("# not JSON\n", encoding="utf-8")
            result = self.validate(run)
            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            self.assertIn("valid JSON", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/70-validation.json").exists())

    def test_validator_rejects_undeclared_process_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            extra = artifact_root(run) / "research/claim-updates.jsonl"
            extra.write_text("{}\n", encoding="utf-8")
            result = self.validate(run)
            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            self.assertIn("undeclared artifact", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/70-validation.json").exists())

    def test_public_local_path_leak_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            report = artifact_root(run) / "report.md"
            report.write_text(
                report.read_text(encoding="utf-8") + "\n/Users/example/private.txt\n",
                encoding="utf-8",
            )
            result = self.validate(run)
            self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
            self.assertIn("local path leak", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/70-validation.json").exists())

    def test_public_audit_boilerplate_prose_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = build_valid_governed_run(Path(tmp))
            report = artifact_root(run) / "report.md"
            report.write_text(
                report.read_text(encoding="utf-8")
                + "\n\n这条可审计来源是 direct evidence 的记录。\n\n这条可审计来源是 adjacent evidence 的记录。\n",
                encoding="utf-8",
            )
            result = self.validate(run)
            self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
            self.assertIn("audit/source-register boilerplate", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/70-validation.json").exists())

    def test_reduced_inventory_may_omit_pdf_but_full_inventory_may_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp)
            for relative in RENDER_ARTIFACTS - {"exports/report.pdf"}:
                path = artifacts / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.suffix == ".json":
                    path.write_text("{}\n", encoding="utf-8")
                elif path.suffix == ".jsonl":
                    path.write_text("{}\n", encoding="utf-8")
                else:
                    path.write_text("fixture\n", encoding="utf-8")
            _, reduced_code = _structural_checks(artifacts, pdf_required=False)
            full_checks, full_code = _structural_checks(artifacts, pdf_required=True)
            self.assertEqual(reduced_code, 0)
            self.assertEqual(full_code, 6)
            self.assertIn("required PDF is missing", full_checks[-1].message)


def artifact_root(run: Path) -> Path:
    return run / "work/generations/g0001/artifacts"


def build_valid_governed_run(
    parent: Path, *, strict_lens: bool = False,
    profile: str = "default_full_dossier", assurance_target: str = "artifact_contract",
) -> Path:
    helper = render_stage_helpers.RenderStageTests(methodName="runTest")
    run = helper.reviewed_run(
        parent, strict_lens=strict_lens, profile=profile,
        assurance_target=assurance_target,
    )
    result = helper.invoke("render", str(run), "--pdf-renderer", "weasyprint")
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return run


if __name__ == "__main__":
    unittest.main()
