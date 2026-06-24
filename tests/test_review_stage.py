from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.harness_io import canonical_json_sha256
from scripts.harness_io import sha256_file
from scripts.report_traceability import (
    extract_paragraphs,
    validate_review_bindings,
    validate_semantic_review,
)
import tests.test_evidence_stage as evidence_stage_helpers
from tests.governed_fixtures import valid_storm_lens_artifact


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/storm_research.py"


class ReviewStageTests(unittest.TestCase):
    def test_review_rejects_author_as_reviewer(self) -> None:
        review = self.review_record(1, "claim", "C001", "a" * 64)
        review["reviewer_run_id"] = review["author_run_id"]
        self.assertIn("reviewer must be independent", validate_semantic_review(review))

    def test_overstated_material_claim_blocks_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace)
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
            inputs = self.write_review_inputs(run, workspace)
            result = self.invoke_review(run, inputs)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            artifacts = run / "work/generations/g0001/artifacts"
            self.assertTrue((artifacts / "report.md").is_file())
            self.assertTrue((artifacts / "research/peer-review.json").is_file())
            self.assertTrue((artifacts / "research/peer-review.md").is_file())
            self.assertTrue((run / "state/generations/g0001/receipts/50-review.json").is_file())

    def test_strict_lens_mode_requires_p4_after_draft_before_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.drafted_run(workspace, strict_lens=True)
            inputs = self.write_review_inputs(run, workspace)
            result = self.invoke_review(run, inputs)
            self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
            self.assertIn("storm-lens-red-team.json", result.stderr)

            self.register_lens_review(run, workspace)
            result = self.invoke_review(run, inputs)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads((run / "state/generations/g0001/receipts/50-review.json").read_text(encoding="utf-8"))
            self.assertIn("artifacts/research/storm-lens-red-team.json", receipt["input_artifacts"])

    def drafted_run(self, workspace: Path, *, strict_lens: bool = False) -> Path:
        helper = evidence_stage_helpers.EvidenceStageTests(methodName="runTest")
        return helper.drafted_run(workspace, strict_lens=strict_lens)

    def reviewed_run(self, workspace: Path, *, strict_lens: bool = False) -> Path:
        run = self.drafted_run(workspace, strict_lens=strict_lens)
        if strict_lens:
            self.register_lens_review(run, workspace)
        inputs = self.write_review_inputs(run, workspace)
        result = self.invoke_review(run, inputs)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return run

    def write_review_inputs(
        self, run: Path, workspace: Path
    ) -> tuple[Path, Path, Path, Path, Path, Path, Path, Path]:
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
        claim_path.write_text("".join(json.dumps(item) + "\n" for item in claim_reviews), encoding="utf-8")
        paragraph_path.write_text("".join(json.dumps(item) + "\n" for item in paragraph_reviews), encoding="utf-8")
        fact_path.write_text("".join(json.dumps(item) + "\n" for item in fact_checks), encoding="utf-8")
        conflict_path.write_text("".join(json.dumps(item) + "\n" for item in conflict_reviews), encoding="utf-8")
        draft_audit_path.write_text("".join(json.dumps(item) + "\n" for item in draft_audits), encoding="utf-8")
        revised.write_text(report, encoding="utf-8")
        revised_map.write_bytes(paragraph_map.read_bytes())
        revision_map.write_text(json.dumps({"schema_version": "2.0", "revisions": []}), encoding="utf-8")
        return claim_path, paragraph_path, fact_path, conflict_path, draft_audit_path, revised, revised_map, revision_map

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
            "allowable_scope": None,
            "required_action": "none",
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
        self, run: Path, inputs: tuple[Path, Path, Path, Path, Path, Path, Path, Path]
    ) -> subprocess.CompletedProcess[str]:
        claims, audit, fact_checks, conflict_reviews, draft_audit, revised, revised_map, revision_map = inputs
        return subprocess.run(
            [
                sys.executable, str(CLI), "review", str(run),
                "--claim-reviews", str(claims), "--report-audit", str(audit),
                "--fact-checks", str(fact_checks),
                "--conflict-reviews", str(conflict_reviews),
                "--draft-audit", str(draft_audit),
                "--revised-md", str(revised),
                "--revised-paragraph-map-jsonl", str(revised_map),
                "--revision-map", str(revision_map),
            ],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )


if __name__ == "__main__":
    unittest.main()
