from __future__ import annotations

import copy
import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.contract_io import max_review_rubric_binding
from scripts.harness_io import canonical_json_sha256, compute_skill_package_hash
from scripts.harness_io import sha256_file
from scripts.report_traceability import (
    extract_paragraphs,
    validate_review_bindings,
    validate_semantic_review,
)
from scripts.storm_research import (
    _validate_review_loop_contract,
    _validate_review_provenance,
    _validate_revision_map,
)
import tests.test_evidence_stage as evidence_stage_helpers
from tests.governed_fixtures import valid_storm_lens_artifact


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/storm_research.py"


class ReviewStageTests(unittest.TestCase):
    def test_p4_required_action_cannot_use_empty_revision_map(self) -> None:
        action = {
            "action_id": "RA001", "target_kind": "draft", "target_id": "draft",
            "before_sha256": "a" * 64, "action": "rewrite", "disposition": "required",
            "reason": "The draft overstates the result.",
        }
        errors = _validate_revision_map(
            {"schema_version": "2.0", "revisions": []}, [action],
            draft_sha256="a" * 64, candidate_sha256="b" * 64,
        )
        self.assertIn("P4 repair actions are not closed in revision map", errors)

    def test_review_concern_revision_binds_target_action_and_terminal_state(self) -> None:
        concern = {
            "concern_id": "RC001",
            "target_sha256": "a" * 64,
            "required_action": "Add the missing counterevidence and qualify the conclusion.",
            "terminal_disposition": "addressed",
        }
        revision = {
            "action_id": "RC001",
            "before_sha256": "a" * 64,
            "after_sha256": "b" * 64,
            "action": concern["required_action"],
            "status": "applied",
            "reason": "The revised paragraph now includes the counterevidence and narrows the claim.",
        }
        errors = _validate_revision_map(
            {"schema_version": "2.0", "revisions": [revision]},
            [],
            draft_sha256="c" * 64,
            candidate_sha256="d" * 64,
            review_concerns={"RC001": concern},
        )
        self.assertEqual(errors, [])

    def test_review_concern_revision_rejects_unrelated_before_hash(self) -> None:
        concern = {
            "concern_id": "RC001",
            "target_sha256": "a" * 64,
            "required_action": "Add the missing counterevidence and qualify the conclusion.",
            "terminal_disposition": "addressed",
        }
        revision = {
            "action_id": "RC001",
            "before_sha256": "e" * 64,
            "after_sha256": "b" * 64,
            "action": concern["required_action"],
            "status": "applied",
            "reason": "The revised paragraph now includes the counterevidence and narrows the claim.",
        }
        errors = _validate_revision_map(
            {"schema_version": "2.0", "revisions": [revision]},
            [],
            draft_sha256="c" * 64,
            candidate_sha256="d" * 64,
            review_concerns={"RC001": concern},
        )
        self.assertIn("revision 1 before_sha256 does not match review concern target", errors)

    def test_concern_driven_loop_accepts_changed_subject_after_re_review(self) -> None:
        roles = [
            "source_integrity_reviewer", "evidence_method_reviewer", "domain_reviewer",
            "perspective_interdisciplinary_reviewer", "devils_advocate",
            "storm_synthesis_reviewer",
        ]
        base_concern = {
            "concern_id": "RC001", "reviewer_role": "domain_reviewer",
            "severity": "major", "target_kind": "claim", "target_id": "C001",
            "target_sha256": "1" * 64, "evidence_or_locator": "paragraph:1; source:S001",
            "problem": "The conclusion exceeds the direct evidence registered for the claim.",
            "required_action": "Downgrade the conclusion and add the missing limitation.",
            "acceptance_test": "C001 is scoped to the direct evidence and states the limitation.",
            "origin_action_ids": [], "issue_type": "evidence_strength",
            "required_stage": "evidence", "uncertainty_id": None,
            "report_binding": None, "disposition": "open", "reason": None,
        }

        def panel(subject: str, concern: dict[str, object]) -> list[dict[str, object]]:
            rows = []
            for role in roles:
                rows.append({
                    "reviewer_role": role, "decision": "accept",
                    "reason": f"{role} reviewed the exact frozen subject, evidence locators, perspective coverage, and concern closure with a concrete role-specific rationale.",
                    "rubric_id": max_review_rubric_binding(
                        role, compute_skill_package_hash(ROOT)
                    )[0],
                    "rubric_sha256": max_review_rubric_binding(
                        role, compute_skill_package_hash(ROOT)
                    )[1],
                    "reviewed_subject_sha256": subject,
                    "reviewer_context_id": f"ctx-{subject[0]}-{role}",
                    "execution_id": f"exec-{subject[0]}-{role}",
                    "concerns": [concern] if role == "domain_reviewer" else [],
                    "storm_analysis": (
                        self.storm_review_analysis(subject)
                        if role == "storm_synthesis_reviewer" else None
                    ),
                })
            return rows

        closed = dict(base_concern)
        closed.update({"disposition": "addressed", "reason": "The revised claim is narrower and the limitation is explicit in the report."})
        component_keys = {
            "report", "paragraph_map", "revision_map", "claims", "sources", "findings",
            "contradictions", "uncertainties", "p2", "p3", "p4", "retrieval_audit",
            "finding_coverage",
        }
        first_artifacts = {key: "2" * 64 for key in component_keys}
        first_artifacts.update({"report": "3" * 64, "revision_map": "4" * 64})
        second_artifacts = dict(first_artifacts)
        second_artifacts.update({"report": "5" * 64, "claims": "6" * 64})
        first_subject = canonical_json_sha256(first_artifacts)
        second_subject = canonical_json_sha256(second_artifacts)
        first_panel = panel(first_subject, base_concern)
        next(item for item in first_panel if item["reviewer_role"] == "domain_reviewer")["decision"] = "major_revision"
        loop = {
            "schema_version": "2.0", "policy": "concern_driven_until_clear",
            "rounds": [
                {
                    "round_id": "RR001", "candidate_sha256": "3" * 64,
                    "review_subject_sha256": first_subject, "panel_reviews": first_panel,
                    "editor_decision": "major_revision",
                    "editor_review": {
                        "context_id": "ctx-editor-1", "execution_id": "exec-editor-1",
                        "decision": "major_revision",
                        "reason": "The editor preserved the major domain concern because the claim exceeded direct evidence and requires a causal revision before acceptance.",
                        "concern_ids": ["RC001"],
                    },
                    "required_concerns": [base_concern], "revision_map_sha256": "4" * 64,
                    "re_review_result": "requires_re_review", "unresolved_concerns": 1,
                    "generation": 1, "draft_receipt_sha256": "a" * 64,
                    "review_request_sha256": "b" * 64,
                    "review_subject_artifacts": first_artifacts, "round_sha256": "0" * 64,
                },
                {
                    "round_id": "RR002", "candidate_sha256": "5" * 64,
                    "review_subject_sha256": second_subject, "panel_reviews": panel(second_subject, closed),
                    "editor_decision": "accept",
                    "editor_review": {
                        "context_id": "ctx-editor-2", "execution_id": "exec-editor-2",
                        "decision": "accept",
                        "reason": "The editor verified the changed subject, confirmed the prior concern is addressed, and found no newly introduced material defect.",
                        "concern_ids": ["RC001"],
                    },
                    "required_concerns": [closed], "revision_map_sha256": "4" * 64,
                    "re_review_result": "pass", "unresolved_concerns": 0,
                    "generation": 2, "draft_receipt_sha256": "c" * 64,
                    "review_request_sha256": "d" * 64,
                    "review_subject_artifacts": second_artifacts, "round_sha256": "0" * 64,
                },
            ],
            "final_integrity": {
                "review_subject_sha256": second_subject, "status": "pass",
                "checked_claim_ids": ["C001"], "regression_issues": [],
            },
            "summary": {
                "round_count": 2, "final_editor_decision": "accept", "unresolved_concerns": 0,
                "final_candidate_sha256": "5" * 64, "final_review_subject_sha256": second_subject,
                "terminal_reason": "The changed subject passed independent re-review and final integrity.",
            },
        }
        for round_record in loop["rounds"]:
            round_record["round_sha256"] = canonical_json_sha256({
                key: value for key, value in round_record.items() if key != "round_sha256"
            })
        errors = _validate_review_loop_contract(
            loop, final_candidate_sha256="5" * 64,
            final_review_subject_sha256=second_subject, revision_map_sha256="4" * 64,
            material_claim_ids={"C001"}, revision_action_ids={"RC001"},
            p4_action_ids=set(), required_gap_review_ids=set(),
            high_stakes=False, author_context_id="author-context",
            skill_package_sha256=compute_skill_package_hash(ROOT),
            uncertainty_records={}, report_binding_ids=set(),
            current_generation=2,
            round_bindings={
                1: {
                    "draft_receipt_sha256": "a" * 64,
                    "review_request_sha256": "b" * 64,
                    "blocked_round_sha256": loop["rounds"][0]["round_sha256"],
                },
                2: {
                    "draft_receipt_sha256": "c" * 64,
                    "review_request_sha256": "d" * 64,
                },
            },
            final_review_subject_artifacts=second_artifacts,
        )
        self.assertEqual(errors, [])

        copied = copy.deepcopy(loop)
        first_storm = next(
            item for item in copied["rounds"][0]["panel_reviews"]
            if item["reviewer_role"] == "storm_synthesis_reviewer"
        )["storm_analysis"]
        next(
            item for item in copied["rounds"][1]["panel_reviews"]
            if item["reviewer_role"] == "storm_synthesis_reviewer"
        )["storm_analysis"] = copy.deepcopy(first_storm)
        copied["rounds"][1]["round_sha256"] = canonical_json_sha256({
            key: value for key, value in copied["rounds"][1].items()
            if key != "round_sha256"
        })
        copied_errors = _validate_review_loop_contract(
            copied, final_candidate_sha256="5" * 64,
            final_review_subject_sha256=second_subject, revision_map_sha256="4" * 64,
            material_claim_ids={"C001"}, revision_action_ids={"RC001"},
            p4_action_ids=set(), required_gap_review_ids=set(),
            high_stakes=False, author_context_id="author-context",
            skill_package_sha256=compute_skill_package_hash(ROOT),
            uncertainty_records={}, report_binding_ids=set(), current_generation=2,
            round_bindings={
                1: {
                    "draft_receipt_sha256": "a" * 64,
                    "review_request_sha256": "b" * 64,
                    "blocked_round_sha256": copied["rounds"][0]["round_sha256"],
                },
                2: {
                    "draft_receipt_sha256": "c" * 64,
                    "review_request_sha256": "d" * 64,
                },
            },
            final_review_subject_artifacts=second_artifacts,
        )
        self.assertIn(
            "storm_synthesis_reviewer copied the prior round audit instead of re-reviewing the changed subject",
            copied_errors,
        )

    def test_review_provenance_rejects_same_author_and_reviewer_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "transcript.txt"
            transcript.write_text("review", encoding="utf-8")
            request = {"author_context_id": "same", "request_sha256": "a" * 64, "created_at": "2026-06-29T00:00:00Z"}
            review = self.review_record(1, "claim", "C001", "b" * 64)
            review.update({"author_run_id": "same", "reviewer_run_id": "session", "reviewed_at": "2026-06-29T00:00:00Z"})
            provenance = {
                "schema_version": "2.0", "provenance_id": "RPROV-test", "review_session_id": "session",
                "execution_kind": "external_model", "author_context_id": "same", "reviewer_context_id": "same",
                "reviewer_identity": "reviewer", "provider": "provider", "model": "model", "runner": "runner",
                "execution_id": "exec", "request_sha256": "a" * 64, "review_output_sha256": "c" * 64,
                "transcript_ref": "artifacts/research/reviewer-transcript.txt",
                "transcript_sha256": sha256_file(transcript), "started_at": "2026-06-29T00:00:00Z",
                "completed_at": "2026-06-29T00:00:00Z", "isolation_attestation": True,
                "review_sessions": [{
                    "round_id": None, "generation": None, "round_sha256": None,
                    "reviewer_role": "aggregate_reviewer",
                    "context_id": "same", "execution_id": "exec", "start_byte": 0,
                    "end_byte": 6, "sha256": hashlib.sha256(b"review").hexdigest(),
                }],
            }
            errors = _validate_review_provenance(provenance, request, "c" * 64, transcript, [review])
            self.assertIn("reviewer context must differ from author context", errors)

    def test_review_provenance_rejects_segment_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "transcript.txt"
            transcript.write_text("independent review segment", encoding="utf-8")
            request = {"author_context_id": "author", "request_sha256": "a" * 64, "created_at": "2026-06-29T00:00:00Z"}
            review = self.review_record(1, "claim", "C001", "b" * 64)
            review.update({"author_run_id": "author", "reviewer_run_id": "session", "reviewed_at": "2026-06-29T00:00:00Z"})
            provenance = {
                "schema_version": "2.0", "provenance_id": "RPROV-test", "review_session_id": "session",
                "execution_kind": "external_model", "author_context_id": "author", "reviewer_context_id": "reviewer",
                "reviewer_identity": "reviewer", "provider": "provider", "model": "model", "runner": "runner",
                "execution_id": "exec", "request_sha256": "a" * 64, "review_output_sha256": "c" * 64,
                "transcript_ref": "artifacts/research/reviewer-transcript.txt",
                "transcript_sha256": sha256_file(transcript), "started_at": "2026-06-29T00:00:00Z",
                "completed_at": "2026-06-29T00:00:00Z", "isolation_attestation": True,
                "review_sessions": [{
                    "round_id": None, "generation": None, "round_sha256": None,
                    "reviewer_role": "aggregate_reviewer",
                    "context_id": "reviewer", "execution_id": "exec", "start_byte": 0,
                    "end_byte": len(transcript.read_bytes()), "sha256": "0" * 64,
                }],
            }
            errors = _validate_review_provenance(provenance, request, "c" * 64, transcript, [review])
            self.assertIn("review provenance session 1 transcript segment hash mismatch", errors)
    def test_review_rejects_author_as_reviewer(self) -> None:
        review = self.review_record(1, "claim", "C001", "a" * 64)
        review["reviewer_run_id"] = review["author_run_id"]
        self.assertIn("reviewer must be independent", validate_semantic_review(review))

    def test_review_rejects_self_attested_independence_without_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace)
            self.register_lens_review(run, workspace)
            inputs = self.write_review_inputs(run, workspace)
            result = self.invoke_review(run, inputs, with_provenance=False)
            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            self.assertIn("--review-provenance", result.stderr)

    def test_overstated_material_claim_blocks_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace)
            self.register_lens_review(run, workspace)
            inputs = self.write_review_inputs(run, workspace)
            reviews = [json.loads(line) for line in inputs[0].read_text(encoding="utf-8").splitlines()]
            reviews[0]["verdict"] = "overstated"
            reviews[0]["required_action"] = "qualify"
            inputs[0].write_text("".join(json.dumps(item) + "\n" for item in reviews), encoding="utf-8")
            result = self.invoke_review(run, inputs)
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("material review did not pass", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/50-review.json").exists())

    def test_changed_revised_paragraph_invalidates_review(self) -> None:
        report = "# T\n\nOriginal paragraph."
        paragraph = extract_paragraphs(report)[0]
        review = self.review_record(1, "paragraph", paragraph.locator, paragraph.sha256)
        errors = validate_review_bindings(report + " changed", [review])
        self.assertIn(f"reviewed paragraph hash mismatch: {paragraph.locator}", errors)

    def test_passing_independent_review_promotes_canonical_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace)
            self.register_lens_review(run, workspace)
            inputs = self.write_review_inputs(run, workspace)
            result = self.invoke_review(run, inputs)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            artifacts = run / "work/generations/g0001/artifacts"
            self.assertTrue((artifacts / "report.md").is_file())
            self.assertTrue((artifacts / "research/peer-review.json").is_file())
            self.assertTrue((artifacts / "research/peer-review.md").is_file())
            self.assertTrue((run / "state/generations/g0001/receipts/50-review.json").is_file())

    def test_review_prepare_is_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace)
            self.register_lens_review(run, workspace)
            inputs = self.write_review_inputs(run, workspace)
            command = [
                sys.executable, str(CLI), "review-prepare", str(run),
                "--candidate-md", str(inputs[5]), "--candidate-map", str(inputs[6]),
                "--revision-map", str(inputs[7]), "--author-context-id", "author-run-1",
            ]
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            request_path = run / "work/generations/g0001/artifacts/research/review-request.json"
            before = request_path.read_bytes()

            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)

            self.assertEqual(second.returncode, 8, second.stdout + second.stderr)
            self.assertIn("review request is immutable", second.stderr)
            self.assertEqual(request_path.read_bytes(), before)

    def test_strict_lens_mode_requires_p4_after_draft_before_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace, strict_lens=True)
            inputs = self.write_review_inputs(run, workspace)
            result = subprocess.run(
                [
                    sys.executable, str(CLI), "review-prepare", str(run),
                    "--candidate-md", str(inputs[5]), "--candidate-map", str(inputs[6]),
                    "--revision-map", str(inputs[7]), "--author-context-id", "author-run-1",
                ],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
            self.assertIn("storm-lens-red-team.json", result.stderr)

            self.register_lens_review(run, workspace)
            result = self.invoke_review(run, inputs)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads((run / "state/generations/g0001/receipts/50-review.json").read_text(encoding="utf-8"))
            self.assertIn("artifacts/research/storm-lens-red-team.json", receipt["input_artifacts"])

    def test_maximal_review_rejects_generic_panel_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace, profile="maximal_full_dossier")
            self.register_lens_review(run, workspace)
            inputs = self.write_review_inputs(run, workspace)
            loop_path = inputs[8]
            assert loop_path is not None
            loop = json.loads(loop_path.read_text(encoding="utf-8"))
            loop["rounds"][0]["panel_reviews"][0]["reason"] = "Check source closure."
            loop_path.write_text(json.dumps(loop), encoding="utf-8")
            result = self.invoke_review(run, inputs)
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("reason is generic or too short", result.stderr)

    def test_maximal_review_rejects_arbitrary_rubric_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace, profile="maximal_full_dossier")
            self.register_lens_review(run, workspace)
            inputs = self.write_review_inputs(run, workspace)
            loop_path = inputs[8]
            assert loop_path is not None
            loop = json.loads(loop_path.read_text(encoding="utf-8"))
            loop["rounds"][0]["panel_reviews"][0]["rubric_sha256"] = "b" * 64
            loop_path.write_text(json.dumps(loop), encoding="utf-8")

            result = self.invoke_review(run, inputs)

            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("rubric hash does not match the committed role rubric", result.stderr)

    def test_maximal_review_rejects_editor_accept_with_open_major_concern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace, profile="maximal_full_dossier")
            self.register_lens_review(run, workspace)
            inputs = self.write_review_inputs(run, workspace)
            loop_path = inputs[8]
            assert loop_path is not None
            loop = json.loads(loop_path.read_text(encoding="utf-8"))
            subject = loop["rounds"][0]["review_subject_sha256"]
            concern = {
                "concern_id": "RC001",
                "reviewer_role": "domain_reviewer",
                "severity": "major",
                "target_kind": "claim",
                "target_id": "C001",
                "target_sha256": "b" * 64,
                "evidence_or_locator": "paragraph:1; source:S001",
                "problem": "The stated conclusion exceeds the human evidence represented in the registered source.",
                "required_action": "downgrade_claim_or_add_human_evidence",
                "acceptance_test": "C001 is qualified or gains direct human evidence.",
                "origin_action_ids": [], "issue_type": "evidence_strength",
                "required_stage": "evidence", "uncertainty_id": None,
                "report_binding": None,
                "disposition": "open",
                "reason": None,
            }
            domain = next(
                item for item in loop["rounds"][0]["panel_reviews"]
                if item["reviewer_role"] == "domain_reviewer"
            )
            domain["concerns"] = [concern]
            domain["decision"] = "major_revision"
            loop["rounds"][0].update({
                "review_subject_sha256": subject,
                "required_concerns": [concern],
                "editor_decision": "accept",
                "unresolved_concerns": 1,
            })
            loop_path.write_text(json.dumps(loop), encoding="utf-8")
            result = self.invoke_review(run, inputs)
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("editor decision conflicts with open concerns", result.stderr)
            blocked = run / "state/generations/g0001/review-blocked.json"
            self.assertTrue(blocked.is_file())
            blocked_payload = json.loads(blocked.read_text(encoding="utf-8"))
            self.assertEqual(blocked_payload["blocking_issue_ids"], ["RC001"])
            status = subprocess.run(
                [sys.executable, str(CLI), "status", str(run)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertEqual(json.loads(status.stdout)["state"], "blocked_with_unresolved_issues")
            explain = subprocess.run(
                [sys.executable, str(CLI), "explain", str(run)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(explain.returncode, 0, explain.stdout + explain.stderr)
            explain_payload = json.loads(explain.stdout)
            self.assertEqual(explain_payload["blocking_issue_ids"], ["RC001"])
            self.assertIn("--resume-blocked-review", explain_payload["repair_command"])
            amended = subprocess.run(
                [
                    sys.executable, str(CLI), "amend", str(run),
                    "--resume-blocked-review", "--initiator", "human-reviewer",
                    "--approval-evidence", "approval:test-review-cycle",
                    "--reason", "Resume the required evidence revision cycle.",
                ],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(amended.returncode, 0, amended.stdout + amended.stderr)
            amendment = json.loads(
                (run / "work/generations/g0002/inputs/amendment.json").read_text(encoding="utf-8")
            )
            self.assertEqual(amendment["invalidation_start_stage"], "evidence")
            self.assertEqual(amendment["changes"][0]["before"], blocked_payload["block_sha256"])

    def test_maximal_review_requires_complete_storm_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace, profile="maximal_full_dossier")
            self.register_lens_review(run, workspace)
            inputs = self.write_review_inputs(run, workspace)
            loop_path = inputs[8]
            assert loop_path is not None
            loop = json.loads(loop_path.read_text(encoding="utf-8"))
            storm = next(
                item for item in loop["rounds"][0]["panel_reviews"]
                if item["reviewer_role"] == "storm_synthesis_reviewer"
            )
            del storm["storm_analysis"]["blind_spots"]
            loop_path.write_text(json.dumps(loop), encoding="utf-8")
            result = self.invoke_review(run, inputs)
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("complete STORM audit", result.stderr)

    def test_maximal_review_rejects_empty_storm_category_without_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace, profile="maximal_full_dossier")
            self.register_lens_review(run, workspace)
            inputs = self.write_review_inputs(run, workspace)
            loop_path = inputs[8]
            assert loop_path is not None
            loop = json.loads(loop_path.read_text(encoding="utf-8"))
            storm = next(
                item for item in loop["rounds"][0]["panel_reviews"]
                if item["reviewer_role"] == "storm_synthesis_reviewer"
            )
            storm["storm_analysis"]["direct_conflicts"] = []
            loop_path.write_text(json.dumps(loop), encoding="utf-8")

            result = self.invoke_review(run, inputs)

            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("direct_conflicts requires explicit disposition", result.stderr)

    def test_maximal_review_concern_requires_deterministic_stage_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace, profile="maximal_full_dossier")
            self.register_lens_review(run, workspace)
            inputs = self.write_review_inputs(run, workspace)
            loop_path = inputs[8]
            assert loop_path is not None
            loop = json.loads(loop_path.read_text(encoding="utf-8"))
            concern = {
                "concern_id": "RC001", "reviewer_role": "domain_reviewer",
                "severity": "major", "target_kind": "claim", "target_id": "C001",
                "target_sha256": "b" * 64,
                "evidence_or_locator": "paragraph:1; source:S001",
                "problem": "The conclusion lacks the direct human evidence required by its scope.",
                "required_action": "add_human_evidence_or_downgrade",
                "acceptance_test": "C001 gains direct human evidence or is downgraded.",
                "origin_action_ids": [], "issue_type": None, "required_stage": None,
                "uncertainty_id": None, "report_binding": None,
                "disposition": "open", "reason": None,
            }
            domain = next(
                item for item in loop["rounds"][0]["panel_reviews"]
                if item["reviewer_role"] == "domain_reviewer"
            )
            domain["concerns"] = [concern]
            domain["decision"] = "major_revision"
            round_record = loop["rounds"][0]
            round_record["required_concerns"] = [concern]
            round_record["editor_decision"] = "major_revision"
            round_record["editor_review"]["decision"] = "major_revision"
            round_record["editor_review"]["concern_ids"] = ["RC001"]
            round_record["unresolved_concerns"] = 1
            loop_path.write_text(json.dumps(loop), encoding="utf-8")

            result = self.invoke_review(run, inputs)

            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("requires issue_type and required_stage", result.stderr)

    def test_preserved_uncertainty_requires_ledger_and_report_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace, profile="maximal_full_dossier")
            self.register_lens_review(run, workspace)
            inputs = self.write_review_inputs(run, workspace)
            loop_path = inputs[8]
            assert loop_path is not None
            loop = json.loads(loop_path.read_text(encoding="utf-8"))
            concern = {
                "concern_id": "RC001", "reviewer_role": "domain_reviewer",
                "severity": "minor", "target_kind": "claim", "target_id": "C001",
                "target_sha256": "b" * 64,
                "evidence_or_locator": "paragraph:1; source:S001",
                "problem": "The available literature leaves a genuine scientific uncertainty.",
                "required_action": "preserve_and_disclose_uncertainty",
                "acceptance_test": "The uncertainty is registered and stated at the report target.",
                "origin_action_ids": [], "issue_type": "unsupported_claim",
                "required_stage": "evidence", "uncertainty_id": None,
                "report_binding": None, "disposition": "preserved_as_uncertainty",
                "reason": "The report should preserve this bounded scientific uncertainty.",
            }
            domain = next(
                item for item in loop["rounds"][0]["panel_reviews"]
                if item["reviewer_role"] == "domain_reviewer"
            )
            domain["concerns"] = [concern]
            round_record = loop["rounds"][0]
            round_record["required_concerns"] = [concern]
            round_record["editor_review"]["concern_ids"] = ["RC001"]
            loop_path.write_text(json.dumps(loop), encoding="utf-8")

            result = self.invoke_review(run, inputs)

            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("preserved uncertainty requires uncertainty_id and report binding", result.stderr)

    def test_maximal_review_rejects_reused_panel_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace, profile="maximal_full_dossier")
            self.register_lens_review(run, workspace)
            inputs = self.write_review_inputs(run, workspace)
            loop_path = inputs[8]
            assert loop_path is not None
            loop = json.loads(loop_path.read_text(encoding="utf-8"))
            panel = loop["rounds"][0]["panel_reviews"]
            panel[1]["reviewer_context_id"] = panel[0]["reviewer_context_id"]
            loop_path.write_text(json.dumps(loop), encoding="utf-8")
            result = self.invoke_review(run, inputs)
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("panel reviewer contexts must be distinct", result.stderr)

    def test_maximal_review_rounds_require_distinct_generations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace, profile="maximal_full_dossier")
            self.register_lens_review(run, workspace)
            inputs = self.write_review_inputs(run, workspace)
            loop_path = inputs[8]
            assert loop_path is not None
            loop = json.loads(loop_path.read_text(encoding="utf-8"))
            first = loop["rounds"][0]
            first.update({
                "generation": 1,
                "draft_receipt_sha256": json.loads(
                    (run / "state/generations/g0001/receipts/40-draft.json").read_text(encoding="utf-8")
                )["receipt_sha256"],
                "review_request_sha256": "a" * 64,
                "review_subject_artifacts": {"report": first["candidate_sha256"]},
                "round_sha256": "0" * 64,
            })
            first["round_sha256"] = canonical_json_sha256({
                key: value for key, value in first.items() if key != "round_sha256"
            })
            second = copy.deepcopy(first)
            second["round_id"] = "RR002"
            second["re_review_result"] = "pass"
            second["round_sha256"] = canonical_json_sha256({
                key: value for key, value in second.items() if key != "round_sha256"
            })
            loop["rounds"] = [first, second]
            loop["summary"]["round_count"] = 2
            loop_path.write_text(json.dumps(loop), encoding="utf-8")

            result = self.invoke_review(run, inputs)

            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("review rounds must use distinct increasing generations", result.stderr)

    def drafted_run(
        self, workspace: Path, *, strict_lens: bool = False,
        profile: str = "default_full_dossier", assurance_target: str = "artifact_contract",
    ) -> Path:
        helper = evidence_stage_helpers.EvidenceStageTests(methodName="runTest")
        return helper.drafted_run(
            workspace, strict_lens=strict_lens, profile=profile,
            assurance_target=assurance_target,
        )

    def reviewed_run(
        self, workspace: Path, *, strict_lens: bool = False,
        profile: str = "default_full_dossier", assurance_target: str = "artifact_contract",
    ) -> Path:
        run = self.drafted_run(
            workspace, strict_lens=strict_lens, profile=profile,
            assurance_target=assurance_target,
        )
        self.register_lens_review(run, workspace)
        inputs = self.write_review_inputs(run, workspace)
        result = self.invoke_review(run, inputs)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return run

    def write_review_inputs(
        self, run: Path, workspace: Path
    ) -> tuple[Path, Path, Path, Path, Path, Path, Path, Path, Path | None]:
        artifacts = run / "work/generations/g0001/artifacts"
        draft = artifacts / "drafts/report-v1.md"
        paragraph_map = artifacts / "research/paragraph-map.jsonl"
        claims = [json.loads(line) for line in (artifacts / "research/claim-evidence-ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        contradictions = json.loads((artifacts / "research/contradiction-ledger.json").read_text(encoding="utf-8"))
        report = draft.read_text(encoding="utf-8")
        claim_reviews = []
        review_index = 1
        for claim in claims:
            claim_reviews.append(self.review_record(
                review_index, "claim", str(claim["claim_id"]),
                canonical_json_sha256(claim), material=bool(claim["material"]),
            ))
            review_index += 1
        paragraph_reviews = []
        draft_audits = []
        for paragraph in extract_paragraphs(report):
            paragraph_reviews.append(self.review_record(
                review_index, "paragraph", paragraph.locator, paragraph.sha256
            ))
            review_index += 1
            draft_audits.append(self.review_record(
                review_index + 500, "paragraph", paragraph.locator, paragraph.sha256
            ))
        fact_checks = []
        for offset, claim in enumerate(claims, start=1):
            fact_checks.append(self.review_record(
                offset + 700, "claim", str(claim["claim_id"]),
                canonical_json_sha256(claim), material=bool(claim["material"]),
            ))
        conflict_reviews = [self.conflict_review_record(contradictions)]
        claim_path = workspace / "claim-reviews.jsonl"
        paragraph_path = workspace / "report-audit.jsonl"
        fact_path = workspace / "fact-checks.jsonl"
        conflict_path = workspace / "conflict-reviews.jsonl"
        draft_audit_path = workspace / "draft-audit.jsonl"
        revised = workspace / "revised.md"
        revised_map = workspace / "revised-paragraph-map.jsonl"
        revision_map = workspace / "revision-map.json"
        review_loop = workspace / "review-loop.json"
        claim_path.write_text("".join(json.dumps(item) + "\n" for item in claim_reviews), encoding="utf-8")
        paragraph_path.write_text("".join(json.dumps(item) + "\n" for item in paragraph_reviews), encoding="utf-8")
        fact_path.write_text("".join(json.dumps(item) + "\n" for item in fact_checks), encoding="utf-8")
        conflict_path.write_text("".join(json.dumps(item) + "\n" for item in conflict_reviews), encoding="utf-8")
        draft_audit_path.write_text("".join(json.dumps(item) + "\n" for item in draft_audits), encoding="utf-8")
        revised.write_text(report, encoding="utf-8")
        revised_map.write_bytes(paragraph_map.read_bytes())
        revision_map.write_text(json.dumps({"schema_version": "2.0", "revisions": []}), encoding="utf-8")
        brief = json.loads((run / "work/generations/g0001/inputs/brief.json").read_text(encoding="utf-8"))
        if brief.get("research_profile") == "maximal_full_dossier":
            review_loop.write_text(json.dumps(self.review_loop_record(
                run, revised, revised_map, revision_map
            )), encoding="utf-8")
            return claim_path, paragraph_path, fact_path, conflict_path, draft_audit_path, revised, revised_map, revision_map, review_loop
        return claim_path, paragraph_path, fact_path, conflict_path, draft_audit_path, revised, revised_map, revision_map, None

    def review_loop_record(
        self, run: Path, revised: Path, revised_map: Path, revision_map: Path
    ) -> dict[str, object]:
        candidate_hash = sha256_file(revised)
        revision_hash = sha256_file(revision_map)
        artifacts = run / "work/generations/g0001/artifacts"
        subject_paths = {
            "report": revised,
            "paragraph_map": revised_map,
            "revision_map": revision_map,
            "claims": artifacts / "research/claim-evidence-ledger.jsonl",
            "sources": artifacts / "research/source-register.jsonl",
            "findings": artifacts / "research/storm-findings-pool.jsonl",
            "contradictions": artifacts / "research/contradiction-ledger.json",
            "uncertainties": artifacts / "research/uncertainty-ledger.json",
            "p2": artifacts / "research/storm-lens-conflicts.json",
            "p3": artifacts / "research/storm-lens-outline.json",
            "p4": artifacts / "research/storm-lens-red-team.json",
            "retrieval_audit": artifacts / "research/retrieval-audit.jsonl",
            "finding_coverage": artifacts / "research/finding-coverage.json",
        }
        subject_artifacts = {
            key: sha256_file(path) for key, path in sorted(subject_paths.items())
        }
        subject_hash = canonical_json_sha256(subject_artifacts)
        roles = [
            "source_integrity_reviewer", "evidence_method_reviewer",
            "domain_reviewer", "perspective_interdisciplinary_reviewer",
            "devils_advocate", "storm_synthesis_reviewer",
        ]
        panel = []
        package_hash = compute_skill_package_hash(ROOT)
        terminal_gap_concern: dict[str, object] | None = None
        retrieval_audit = [
            json.loads(line)
            for line in (artifacts / "research/retrieval-audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        terminal_gap = next(
            (
                item for item in retrieval_audit
                if item.get("record_kind") == "gap_assessment"
                and item.get("review_concern_id") == "RC001"
            ),
            None,
        )
        if terminal_gap is not None:
            terminal_gap_concern = {
                "concern_id": "RC001",
                "reviewer_role": "domain_reviewer",
                "severity": "minor",
                "target_kind": "gap_assessment",
                "target_id": str(terminal_gap.get("assessment_id")),
                "target_sha256": canonical_json_sha256(terminal_gap),
                "evidence_or_locator": f"retrieval-audit:{terminal_gap.get('assessment_id')}",
                "problem": "The terminal gap disposition must be independently verified before Max may treat retrieval as closed.",
                "required_action": "verify_gap_terminal_disposition",
                "acceptance_test": "The domain reviewer confirms the terminal gap disposition is supported by the bound search waves and screened candidates.",
                "origin_action_ids": [],
                "issue_type": "gap_terminal_disposition",
                "required_stage": "retrieval",
                "uncertainty_id": None,
                "report_binding": None,
                "disposition": "addressed",
                "reason": "The domain reviewer checked the bound retrieval audit and accepted this terminal gap disposition for the deterministic fixture.",
            }
        for role in roles:
            rubric_id, rubric_sha256 = max_review_rubric_binding(role, package_hash)
            concerns = (
                [terminal_gap_concern]
                if role == "domain_reviewer" and terminal_gap_concern is not None
                else []
            )
            panel.append({
                "reviewer_role": role,
                "decision": "accept",
                "reason": (
                    f"{role} inspected the frozen report and evidence bundle, found no blocking "
                    "support, scope, contradiction, perspective, or citation defect in this deterministic fixture."
                ),
                "rubric_id": rubric_id,
                "rubric_sha256": rubric_sha256,
                "reviewed_subject_sha256": subject_hash,
                "reviewer_context_id": f"ctx-{role}",
                "execution_id": f"exec-{role}",
                "concerns": concerns,
                "storm_analysis": (
                    self.storm_review_analysis(subject_hash)
                    if role == "storm_synthesis_reviewer" else None
                ),
            })
        loop = {
            "schema_version": "2.0",
            "policy": "concern_driven_until_clear",
            "rounds": [
                {
                    "round_id": "RR001",
                    "candidate_sha256": candidate_hash,
                    "review_subject_sha256": subject_hash,
                    "panel_reviews": panel,
                    "editor_decision": "accept",
                    "editor_review": {
                        "context_id": "ctx-editor-synthesizer",
                        "execution_id": "exec-editor-synthesizer",
                        "decision": "accept",
                        "reason": "The editor reconciled all six independent panel reports, confirmed the terminal gap disposition review was closed, and advanced the frozen subject to final integrity.",
                        "concern_ids": ["RC001"] if terminal_gap_concern is not None else [],
                    },
                    "required_concerns": [terminal_gap_concern] if terminal_gap_concern is not None else [],
                    "revision_map_sha256": revision_hash,
                    "re_review_result": "not_required",
                    "unresolved_concerns": 0,
                    "generation": 1,
                    "draft_receipt_sha256": json.loads(
                        (run / "state/generations/g0001/receipts/40-draft.json").read_text(encoding="utf-8")
                    )["receipt_sha256"],
                    "review_request_sha256": "0" * 64,
                    "review_subject_artifacts": subject_artifacts,
                    "round_sha256": "0" * 64,
                },
            ],
            "final_integrity": {
                "review_subject_sha256": subject_hash,
                "status": "pass",
                "checked_claim_ids": [f"C{index:03d}" for index in range(1, 13)],
                "regression_issues": [],
            },
            "summary": {
                "round_count": 1,
                "final_editor_decision": "accept",
                "unresolved_concerns": 0,
                "final_candidate_sha256": candidate_hash,
                "final_review_subject_sha256": subject_hash,
                "terminal_reason": "The independent panel found no blockers and final integrity passed.",
            },
        }
        loop["rounds"][0]["round_sha256"] = canonical_json_sha256({
            key: value for key, value in loop["rounds"][0].items()
            if key != "round_sha256"
        })
        return loop

    def storm_review_analysis(self, subject_hash: str) -> dict[str, object]:
        statements = {
            "direct_conflicts": "No direct perspective conflict remains in this bounded fixture.",
            "cross_perspective_consensus": "All perspectives retain the same narrow evidence boundary.",
            "blind_spots": "No additional material blind spot is applicable to this fixture.",
            "resolver_questions": "No unresolved question would change this fixture conclusion.",
            "missing_perspectives": "No relevant perspective is missing from the deterministic fixture.",
            "historical_patterns": "Historical analogy is not applicable to this contract fixture.",
            "dispositions": "The STORM audit is closed for this exact frozen subject.",
        }
        result: dict[str, object] = {
            "strongest_evidence": "Registered full-text evidence directly supports the scoped fixture claims.",
            "weakest_evidence": "The final recommendation remains bounded by the stated limitations.",
        }
        for index, field in enumerate(statements, start=1):
            result[field] = [{
                "item_id": f"ST{index:03d}",
                "statement": f"{statements[field]} Subject {subject_hash[:8]}.",
                "disposition": "closed" if field == "dispositions" else "not_applicable",
                "reason": "The reviewer checked the current subject and recorded an explicit bounded disposition.",
                "concern_id": None,
            }]
        return result

    def review_record(
        self,
        index: int,
        target_kind: str,
        target_id: str,
        target_sha256: str,
        *,
        material: bool = True,
    ) -> dict[str, object]:
        return {
            "schema_version": "2.0",
            "review_id": f"REV{index:03d}",
            "review_type": "claim_entailment" if target_kind == "claim" else "report_assertion",
            "author_run_id": "author-run-1",
            "reviewer_run_id": "reviewer-run-1",
            "independent": True,
            "target_kind": target_kind,
            "target_id": target_id,
            "target_sha256": target_sha256,
            "material": material,
            "verdict": "supported",
            "reason": "The target is supported and does not introduce external material assertions.",
            "evidence_or_locator": f"{target_kind}:{target_id}",
            "allowable_scope": None,
            "required_action": "none",
            "acceptance_test": "The reviewed target hash and evidentiary scope remain unchanged.",
            "findings": [],
            "reviewed_at": "2026-06-23T00:00:00Z",
        }

    def conflict_review_record(self, contradictions: dict[str, object]) -> dict[str, object]:
        return {
            "schema_version": "2.0",
            "review_id": "CRV001",
            "author_run_id": "author-run-1",
            "reviewer_run_id": "conflict-reviewer-run-1",
            "independent": True,
            "target_kind": "contradiction_ledger",
            "target_id": "contradiction-ledger",
            "target_sha256": canonical_json_sha256(contradictions),
            "verdict": "supported",
            "reason": "The contradiction ledger is empty and no contested claims are present.",
            "required_action": "none",
            "reviewed_at": "2026-06-23T00:00:00Z",
        }

    def register_lens_review(self, run: Path, workspace: Path) -> None:
        artifacts = run / "work/generations/g0001/artifacts"
        draft = artifacts / "drafts/report-v1.md"
        paragraph_map = artifacts / "research/paragraph-map.jsonl"
        inputs = {
            "artifacts/drafts/report-v1.md": sha256_file(draft),
            "artifacts/research/paragraph-map.jsonl": sha256_file(paragraph_map),
        }
        lens = workspace / "storm-lens-red-team.json"
        lens.write_text(json.dumps(valid_storm_lens_artifact(
            "P4",
            sha256_file(ROOT / "references/storm-lens-prompt-pack.md"),
            inputs,
            target_sha256=sha256_file(draft),
        )), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(CLI), "lens-review", str(run), "--input-json", str(lens)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def invoke_review(
        self, run: Path, inputs: tuple[Path, Path, Path, Path, Path, Path, Path, Path, Path | None],
        *,
        with_provenance: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        claims, audit, fact_checks, conflict_reviews, draft_audit, revised, revised_map, revision_map, review_loop = inputs
        command = [
            sys.executable, str(CLI), "review", str(run),
            "--claim-reviews", str(claims), "--report-audit", str(audit),
            "--fact-checks", str(fact_checks),
            "--conflict-reviews", str(conflict_reviews),
            "--draft-audit", str(draft_audit),
            "--revised-md", str(revised),
            "--revised-paragraph-map-jsonl", str(revised_map),
            "--revision-map", str(revision_map),
        ]
        if review_loop is not None:
            command.extend(["--review-loop", str(review_loop)])
        if with_provenance:
            brief = json.loads((run / "brief.json").read_text(encoding="utf-8"))
            captured = brief.get("assurance_target") == "captured_host_execution"
            author_context = "author-run-1"
            if captured:
                draft_provenance = json.loads(
                    (run / "work/generations/g0001/artifacts/research/execution/draft-provenance.json")
                    .read_text(encoding="utf-8")
                )
                author_context = str(draft_provenance["context_id"])
            prepare = subprocess.run(
                [
                    sys.executable, str(CLI), "review-prepare", str(run),
                    "--candidate-md", str(revised), "--candidate-map", str(revised_map),
                    "--revision-map", str(revision_map), "--author-context-id", author_context,
                ],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(prepare.returncode, 0, prepare.stdout + prepare.stderr)
            request = json.loads((run / "work/generations/g0001/artifacts/research/review-request.json").read_text(encoding="utf-8"))
            if review_loop is not None:
                loop_payload = json.loads(review_loop.read_text(encoding="utf-8"))
                current_round = loop_payload["rounds"][-1]
                current_round["review_request_sha256"] = request["request_sha256"]
                current_round["round_sha256"] = canonical_json_sha256({
                    key: value for key, value in current_round.items()
                    if key != "round_sha256"
                })
                review_loop.write_text(json.dumps(loop_payload), encoding="utf-8")
            reviewed_at = request["created_at"]
            completed_at = reviewed_at
            if captured:
                from datetime import datetime, timedelta
                started_value = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
                reviewed_at = (started_value + timedelta(microseconds=1)).isoformat().replace("+00:00", "Z")
                completed_at = (started_value + timedelta(milliseconds=1)).isoformat().replace("+00:00", "Z")
            for path in (claims, audit, fact_checks, conflict_reviews, draft_audit):
                rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                for row in rows:
                    row["author_run_id"] = author_context
                    row["reviewer_run_id"] = "reviewer-run-1"
                    row["reviewed_at"] = reviewed_at
                path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            output_payload = {
                "claim_reviews": [json.loads(line) for line in claims.read_text(encoding="utf-8").splitlines()],
                "paragraph_reviews": [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()],
                "fact_checks": [json.loads(line) for line in fact_checks.read_text(encoding="utf-8").splitlines()],
                "conflict_reviews": [json.loads(line) for line in conflict_reviews.read_text(encoding="utf-8").splitlines()],
                "draft_audits": [json.loads(line) for line in draft_audit.read_text(encoding="utf-8").splitlines()],
                "review_loop": (
                    json.loads(review_loop.read_text(encoding="utf-8"))
                    if review_loop is not None else {}
                ),
            }
            transcript = revised.parent / "reviewer-transcript.txt"
            loop_payload = output_payload["review_loop"]
            session_specs: list[tuple[str | None, int | None, str | None, str, str, str]] = []
            if loop_payload:
                for round_record in loop_payload["rounds"]:
                    for panel_review in round_record["panel_reviews"]:
                        session_specs.append((
                            round_record["round_id"], round_record["generation"],
                            round_record["round_sha256"], panel_review["reviewer_role"],
                            panel_review["reviewer_context_id"], panel_review["execution_id"],
                        ))
                    editor = round_record["editor_review"]
                    session_specs.append((
                        round_record["round_id"], round_record["generation"],
                        round_record["round_sha256"], "editor_synthesizer",
                        editor["context_id"], editor["execution_id"],
                    ))
            else:
                session_specs.append((
                    None, None, None, "aggregate_reviewer", "reviewer-context-1", "exec-1"
                ))
            transcript_bytes = b""
            review_sessions = []
            for round_id, generation, round_sha256, role, context_id, execution_id in session_specs:
                segment = (
                    f"{role} independently inspected the frozen review subject, cited exact targets, "
                    "tested evidence and perspective closure, and recorded a reasoned decision.\n"
                    "The reviewer checked source locators, claim strength, counterevidence, and unresolved gaps against the immutable request.\n"
                    "The resulting decision names what passed, what remains uncertain, and which stage must change if repair is required.\n"
                ).encode("utf-8")
                start = len(transcript_bytes)
                transcript_bytes += segment
                review_sessions.append({
                    "round_id": round_id, "generation": generation,
                    "round_sha256": round_sha256, "reviewer_role": role,
                    "context_id": context_id, "execution_id": execution_id,
                    "start_byte": start, "end_byte": len(transcript_bytes),
                    "sha256": hashlib.sha256(segment).hexdigest(),
                })
            transcript.write_bytes(transcript_bytes)
            provenance = revised.parent / "reviewer-provenance.json"
            provenance.write_text(json.dumps({
                "schema_version": "2.0", "provenance_id": "RPROV-test",
                "review_session_id": "reviewer-run-1", "execution_kind": "external_model",
                "author_context_id": author_context, "reviewer_context_id": "reviewer-context-1",
                "reviewer_identity": "test reviewer", "provider": "test-provider",
                "model": "test-model", "runner": "test-runner", "execution_id": "exec-1",
                "request_sha256": request["request_sha256"],
                "review_output_sha256": canonical_json_sha256(output_payload),
                "transcript_ref": "artifacts/research/reviewer-transcript.txt",
                "transcript_sha256": sha256_file(transcript), "started_at": reviewed_at,
                "completed_at": completed_at, "isolation_attestation": True,
                "review_sessions": review_sessions,
            }), encoding="utf-8")
            command.extend(["--review-provenance", str(provenance), "--review-transcript", str(transcript)])
        return subprocess.run(
            command,
            cwd=ROOT, capture_output=True, text=True, check=False,
        )


if __name__ == "__main__":
    unittest.main()
