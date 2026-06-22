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
from scripts.report_traceability import citation_index, extract_paragraphs


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

    def test_draft_requires_evidence_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.retrieved_run(workspace)
            draft = workspace / "draft.md"
            mapping = workspace / "paragraph-map.jsonl"
            draft.write_text("# Incomplete\n", encoding="utf-8")
            mapping.write_text("", encoding="utf-8")
            result = self.invoke(
                "draft", str(run), "--draft-md", str(draft),
                "--paragraph-map-jsonl", str(mapping),
            )
            self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
            self.assertIn("missing evidence receipt", result.stderr)

    def test_draft_rejects_handwritten_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.evidenced_run(workspace)
            draft, mapping = self.write_draft_inputs(run, workspace)
            draft.write_text(
                draft.read_text(encoding="utf-8") + "\n## References\n\n[^invented]: invented\n",
                encoding="utf-8",
            )
            result = self.invoke(
                "draft", str(run), "--draft-md", str(draft),
                "--paragraph-map-jsonl", str(mapping),
            )
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("hand-written References", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/40-draft.json").exists())

    def test_draft_generates_references_and_commits_traceability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.evidenced_run(workspace)
            draft, mapping = self.write_draft_inputs(run, workspace)
            result = self.invoke(
                "draft", str(run), "--draft-md", str(draft),
                "--paragraph-map-jsonl", str(mapping),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            artifact_root = run / "work/generations/g0001/artifacts"
            report = artifact_root / "drafts/report-v1.md"
            self.assertIn("## References", report.read_text(encoding="utf-8"))
            self.assertTrue((artifact_root / "research/paragraph-map.jsonl").is_file())
            self.assertTrue((artifact_root / "research/citation-index.json").is_file())
            self.assertTrue((run / "state/generations/g0001/receipts/40-draft.json").is_file())

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

    def evidenced_run(self, workspace: Path) -> Path:
        run = self.retrieved_run(workspace)
        inputs = self.write_evidence_inputs(run, workspace)
        result = self.invoke_evidence(run, inputs)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return run

    def write_draft_inputs(self, run: Path, workspace: Path) -> tuple[Path, Path]:
        research = run / "work/generations/g0001/artifacts/research"
        sources = [json.loads(line) for line in (research / "source-register.jsonl").read_text(encoding="utf-8").splitlines()]
        claims = [json.loads(line) for line in (research / "claim-evidence-ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        key_by_source = {
            str(source["source_id"]): key for key, source in citation_index(sources).items()
        }
        blocks = ["# Governed Research Dossier"]
        for index, claim in enumerate(claims, start=1):
            source_id = str(claim["supporting_source_ids"][0])
            key = key_by_source[source_id]
            details = " ".join(f"bounded-detail-{index}-{word}" for word in range(1, 300))
            blocks.extend([
                f"## Evidence Section {index}",
                f"{claim['claim_text']} {details} [^{key}]",
            ])
        draft_text = "\n\n".join(blocks) + "\n"
        paragraphs = extract_paragraphs(draft_text)
        records = []
        for paragraph, claim in zip(paragraphs, claims, strict=True):
            source_id = str(claim["supporting_source_ids"][0])
            records.append({
                "schema_version": "2.0",
                "paragraph_sha256": paragraph.sha256,
                "paragraph_type": "factual" if claim["claim_type"] == "fact" else claim["claim_type"],
                "claim_ids": [claim["claim_id"]],
                "source_ids": [source_id],
                "citation_keys": [key_by_source[source_id]],
                "text_locator": paragraph.locator,
            })
        draft = workspace / "draft.md"
        mapping = workspace / "paragraph-map.jsonl"
        draft.write_text(draft_text, encoding="utf-8")
        mapping.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
        return draft, mapping

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
