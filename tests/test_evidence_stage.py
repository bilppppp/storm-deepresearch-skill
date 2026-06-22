from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.governed_fixtures import (
    valid_adapter_record,
    valid_claim_v2,
    valid_contradiction_ledger_v2,
    valid_report_outline_v2,
    valid_research_plan_v2,
    valid_source_plan,
    valid_uncertainty_ledger_v2,
)


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/storm_research.py"


class EvidenceStageTests(unittest.TestCase):
    def test_evidence_stage_requires_retrieval_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.planned_run(workspace)
            inputs = self.write_evidence_inputs(run, workspace, use_retrieval=False)
            result = self.invoke_evidence(run, inputs)
            self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
            self.assertIn("missing retrieval receipt", result.stderr)

    def test_full_dossier_requires_twelve_material_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.retrieved_run(workspace)
            inputs = self.write_evidence_inputs(run, workspace, claim_count=11)
            result = self.invoke_evidence(run, inputs)
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("at least twelve material claims", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/30-evidence.json").exists())

    def test_evidence_stage_commits_closed_claims_and_outline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.retrieved_run(workspace)
            inputs = self.write_evidence_inputs(run, workspace)
            result = self.invoke_evidence(run, inputs)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            research = run / "work/generations/g0001/artifacts/research"
            for name in (
                "claim-evidence-ledger.jsonl", "contradiction-ledger.json",
                "uncertainty-ledger.json", "report-outline.json",
            ):
                self.assertTrue((research / name).is_file(), name)
            self.assertTrue((run / "state/generations/g0001/receipts/30-evidence.json").is_file())

    def invoke_evidence(
        self, run: Path, inputs: tuple[Path, Path, Path, Path]
    ) -> subprocess.CompletedProcess[str]:
        claims, contradictions, uncertainties, outline = inputs
        return self.invoke(
            "evidence", str(run), "--claims", str(claims),
            "--contradictions", str(contradictions),
            "--uncertainties", str(uncertainties),
            "--report-outline", str(outline),
        )

    def write_evidence_inputs(
        self,
        run: Path,
        workspace: Path,
        *,
        claim_count: int = 12,
        use_retrieval: bool = True,
    ) -> tuple[Path, Path, Path, Path]:
        manifest_by_query: dict[str, dict[str, object]] = {}
        if use_retrieval:
            manifest_path = run / "work/generations/g0001/artifacts/research/retrieval-manifest.jsonl"
            manifests = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
            manifest_by_query = {str(item["query_id"]): item for item in manifests}
        claims = []
        for index in range(1, claim_count + 1):
            claim_type = "fact" if index <= 10 else ("inference" if index == 11 else "recommendation")
            query_index = min(index, 10)
            claim = valid_claim_v2(index, claim_type=claim_type, source_index=query_index)
            if use_retrieval:
                manifest = manifest_by_query[f"Q{query_index:03d}"]
                source_id = str(manifest["source_id"])
                claim["supporting_source_ids"] = [source_id]
                claim["evidence_locators"] = [{
                    "source_id": source_id,
                    "locator": manifest["locator"],
                    "excerpt": manifest["excerpt"],
                    "snapshot_sha256": manifest["snapshot_sha256"],
                }]
            claims.append(claim)
        claims_path = workspace / "claims.jsonl"
        claims_path.write_text("".join(json.dumps(item) + "\n" for item in claims), encoding="utf-8")
        contradictions = workspace / "contradictions.json"
        contradictions.write_text(json.dumps(valid_contradiction_ledger_v2()), encoding="utf-8")
        uncertainties = workspace / "uncertainties.json"
        uncertainties.write_text(json.dumps(valid_uncertainty_ledger_v2()), encoding="utf-8")
        outline = valid_report_outline_v2()
        if claim_count < 12:
            for section in outline["sections"]:
                section["claim_ids"] = [
                    claim_id for claim_id in section["claim_ids"]
                    if int(claim_id[1:]) <= claim_count
                ]
        outline_path = workspace / "report-outline.json"
        outline_path.write_text(json.dumps(outline), encoding="utf-8")
        return claims_path, contradictions, uncertainties, outline_path

    def retrieved_run(self, workspace: Path) -> Path:
        run = self.planned_run(workspace)
        cache = run / "work/generations/g0001/evidence-cache"
        records = []
        for index in range(1, 11):
            record = valid_adapter_record(index)
            (cache / f"source-{index}.txt").write_text(
                f"Directly inspectable evidence excerpt {index}. Additional context.", encoding="utf-8"
            )
            records.append(record)
        retrieval = workspace / "retrieval.jsonl"
        retrieval.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
        result = self.invoke("ingest", str(run), "--input-jsonl", str(retrieval))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return run

    def planned_run(self, workspace: Path) -> Path:
        result = self.invoke(
            "init", "--topic", "Governed research", "--question",
            "What evidence supports the conclusion?", "--workspace", str(workspace),
            "--output", "test-run",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        run = workspace / "output/storm-deepresearch/test-run"
        plan = workspace / "research-plan.json"
        source_plan = workspace / "source-plan.json"
        plan.write_text(json.dumps(valid_research_plan_v2()), encoding="utf-8")
        source_plan.write_text(json.dumps(valid_source_plan()), encoding="utf-8")
        result = self.invoke(
            "plan", str(run), "--plan-json", str(plan),
            "--source-plan-json", str(source_plan),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return run

    def invoke(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *arguments], cwd=ROOT,
            capture_output=True, text=True, check=False,
        )


if __name__ == "__main__":
    unittest.main()
