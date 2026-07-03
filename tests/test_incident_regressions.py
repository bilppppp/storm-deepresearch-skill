from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

import tests.test_evidence_stage as evidence_stage_helpers
import tests.test_governed_release as release_helpers
import tests.test_render_stage as render_stage_helpers
import tests.test_storm_research_cli as cli_helpers
import tests.test_validate_package as validate_helpers
from scripts.harness_io import sha256_file


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/storm_research.py"
FIXTURE = ROOT / "tests/fixtures/governed/gemini-bypass-redacted/cases.json"

RECEIPTS = {
    "init": "00-init.json",
    "plan": "10-plan.json",
    "retrieval": "20-retrieval.json",
    "evidence": "30-evidence.json",
    "draft": "40-draft.json",
    "review": "50-review.json",
    "render": "60-render.json",
    "validation": "70-validation.json",
    "release": "80-release.json",
}

CASES = {
    "placeholder-source": ("ingest", 5, "reserved or placeholder domain", "retrieval"),
    "full-to-reduced": ("amend", 8, "full dossier cannot be amended", "init"),
    "unmapped-factual-paragraph": ("draft", 5, "report paragraph is unmapped", "draft"),
    "fake-json": ("validate", 4, "artifact-json", "validation"),
    "forged-receipt": ("validate", 8, "receipt-chain", "validation"),
    "modified-package": ("release", 9, "governed Skill package hash mismatch", "release"),
}


@dataclass(frozen=True)
class IncidentRun:
    result: subprocess.CompletedProcess[str]
    run: Path
    failed_receipt_stage: str
    preserved_path: Path
    preserved_sha256: str
    generation: int = 1


class IncidentRegressionTests(unittest.TestCase):
    def test_redacted_fixture_defines_all_confirmed_shortcuts(self) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertTrue(payload["redacted"])
        case_ids = {case["id"] for case in payload["cases"]}
        self.assertGreaterEqual(case_ids, {
            "placeholder-source",
            "blanket-tier-a",
            "secondary-as-primary",
            "full-to-reduced",
            "unmapped-factual-paragraph",
            "handwritten-references",
            "fake-json",
            "intermediate-files",
            "forged-receipt",
            "modified-package",
        })

    def test_incidents_fail_at_expected_stage(self) -> None:
        for name, (_command, code, marker, failed_stage) in CASES.items():
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as tmp:
                    incident = self.run_incident_fixture(name, Path(tmp))
                    result = incident.result
                    self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                    self.assertIn(marker, result.stdout + result.stderr)
                    self.assertFalse(
                        self.receipt_path(
                            incident.run, incident.failed_receipt_stage,
                            generation=incident.generation,
                        ).exists()
                    )
                    self.assertEqual(sha256_file(incident.preserved_path), incident.preserved_sha256)
                    self.assertEqual(failed_stage, incident.failed_receipt_stage)

    def test_source_classification_shortcuts_fail_during_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            helper = cli_helpers.StormResearchCLITests(methodName="runTest")
            run = helper.planned_run(workspace)
            retrieval = helper.write_retrieval_inputs(run, workspace)
            records = [json.loads(line) for line in retrieval.read_text(encoding="utf-8").splitlines()]
            capture = next(record for record in records if record.get("record_kind") == "capture")
            capture["source_type"] = "encyclopedia"
            capture["primary_class"] = "primary"
            capture["reliability_tier"] = "A"
            retrieval.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            result = self.invoke("ingest", str(run), "--input-jsonl", str(retrieval))
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("secondary synthesis cannot be classified as primary", result.stderr)
            self.assertFalse(self.receipt_path(run, "retrieval").exists())

    def run_incident_fixture(self, name: str, workspace: Path) -> IncidentRun:
        if name == "placeholder-source":
            helper = cli_helpers.StormResearchCLITests(methodName="runTest")
            run = helper.planned_run(workspace)
            preserved = run / "work/generations/g0001/artifacts/research/research-plan.json"
            before = sha256_file(preserved)
            retrieval = helper.write_retrieval_inputs(run, workspace, placeholder=True)
            result = self.invoke("ingest", str(run), "--input-jsonl", str(retrieval))
            return IncidentRun(result, run, "retrieval", preserved, before)

        if name == "full-to-reduced":
            helper = render_stage_helpers.RenderStageTests(methodName="runTest")
            run = helper.reviewed_run(workspace)
            failed_render = self.invoke("render", str(run), "--pdf-renderer", "none")
            self.assertEqual(failed_render.returncode, 6, failed_render.stdout + failed_render.stderr)
            preserved = run / "work/generations/g0001/inputs/brief.json"
            before = sha256_file(preserved)
            changes = workspace / "changes.json"
            changes.write_text(json.dumps({"output_mode": "reduced"}) + "\n", encoding="utf-8")
            result = self.invoke(
                "amend", str(run), "--changes-json", str(changes),
                "--initiator", "human-reviewer",
                "--approval-evidence", "approval:red-team",
            )
            return IncidentRun(result, run, "init", preserved, before, generation=2)

        if name == "unmapped-factual-paragraph":
            helper = evidence_stage_helpers.EvidenceStageTests(methodName="runTest")
            run = helper.evidenced_run(workspace)
            preserved = run / "state/generations/g0001/receipts/30-evidence.json"
            before = sha256_file(preserved)
            draft, mapping = helper.write_draft_inputs(run, workspace)
            records = mapping.read_text(encoding="utf-8").splitlines()
            mapping.write_text("\n".join(records[1:]) + "\n", encoding="utf-8")
            result = self.invoke(
                "draft", str(run), "--draft-md", str(draft),
                "--paragraph-map-jsonl", str(mapping),
            )
            return IncidentRun(result, run, "draft", preserved, before)

        if name == "fake-json":
            run = validate_helpers.build_valid_governed_run(workspace)
            preserved = run / "state/generations/g0001/receipts/60-render.json"
            before = sha256_file(preserved)
            bad = run / "work/generations/g0001/artifacts/research/uncertainty-ledger.json"
            bad.write_text("# not JSON\n", encoding="utf-8")
            result = self.invoke("validate", str(run))
            return IncidentRun(result, run, "validation", preserved, before)

        if name == "forged-receipt":
            run = validate_helpers.build_valid_governed_run(workspace)
            preserved = run / "work/generations/g0001/artifacts/report.md"
            before = sha256_file(preserved)
            receipt = run / "state/generations/g0001/receipts/30-evidence.json"
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            payload["validator_sha256"] = "0" * 64
            receipt.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            result = self.invoke("validate", str(run))
            return IncidentRun(result, run, "validation", preserved, before)

        if name == "modified-package":
            helper = release_helpers.GovernedReleaseTests(methodName="runTest")
            run = helper.validated_run(workspace)
            preserved = run / "state/generations/g0001/receipts/70-validation.json"
            before = sha256_file(preserved)
            trust, registry = helper.write_trust_bundle(workspace)
            approval = helper.write_approval(workspace, run)
            trust_payload = json.loads(trust.read_text(encoding="utf-8"))
            trust_payload["skill_package_sha256"] = "0" * 64
            trust.write_text(json.dumps(trust_payload) + "\n", encoding="utf-8")
            result = helper.invoke_release(run, trust, registry, approval)
            return IncidentRun(result, run, "release", preserved, before)

        raise AssertionError(f"unknown incident fixture: {name}")

    def invoke(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def receipt_path(run: Path, stage: str, *, generation: int = 1) -> Path:
        return run / f"state/generations/g{generation:04d}/receipts/{RECEIPTS[stage]}"


if __name__ == "__main__":
    unittest.main()
