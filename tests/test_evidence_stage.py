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
    valid_storm_lens_artifact,
    valid_uncertainty_ledger_v2,
)
from scripts.harness_io import sha256_file
from scripts.report_traceability import citation_index, extract_paragraphs


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/storm_research.py"


class EvidenceStageTests(unittest.TestCase):
    def test_p2_new_retrieval_disposition_blocks_p3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.retrieved_run(workspace, register_lens_for_evidence=False)
            artifacts = run / "work/generations/g0001/artifacts"
            p2_inputs = {
                "artifacts/research/storm-findings-pool.jsonl": sha256_file(artifacts / "research/storm-findings-pool.jsonl"),
                "artifacts/research/finding-coverage.json": sha256_file(artifacts / "research/finding-coverage.json"),
                "artifacts/research/source-register.jsonl": sha256_file(artifacts / "research/source-register.jsonl"),
                "artifacts/research/retrieval-manifest.jsonl": sha256_file(artifacts / "research/retrieval-manifest.jsonl"),
            }
            p2 = valid_storm_lens_artifact("P2", self.prompt_pack_hash(), p2_inputs)
            p2["output"]["resolution_actions"][0]["disposition"] = "new_retrieval"
            p2_path = workspace / "p2-new-retrieval.json"
            p2_path.write_text(json.dumps(p2), encoding="utf-8")
            result = self.invoke("lens-conflicts", str(run), "--input-json", str(p2_path))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            p3_inputs = {
                "artifacts/research/storm-findings-pool.jsonl": sha256_file(artifacts / "research/storm-findings-pool.jsonl"),
                "artifacts/research/storm-lens-conflicts.json": sha256_file(artifacts / "research/storm-lens-conflicts.json"),
            }
            p3 = valid_storm_lens_artifact("P3", self.prompt_pack_hash(), p3_inputs)
            p3_path = workspace / "p3.json"
            p3_path.write_text(json.dumps(p3), encoding="utf-8")
            result = self.invoke("lens-outline", str(run), "--input-json", str(p3_path))
            self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
            self.assertIn("requires a new retrieval generation", result.stderr)
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

    def test_strict_lens_mode_requires_p2_and_p3_before_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.retrieved_run(workspace, register_lens_for_evidence=False)
            inputs = self.write_evidence_inputs(run, workspace)
            result = self.invoke_evidence(run, inputs)
            self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
            self.assertIn("storm-lens-conflicts.json", result.stderr)

            self.register_lens_conflicts(run, workspace)
            self.register_lens_outline(run, workspace)
            result = self.invoke_evidence(run, inputs)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads((run / "state/generations/g0001/receipts/30-evidence.json").read_text(encoding="utf-8"))
            self.assertIn("artifacts/research/storm-lens-conflicts.json", receipt["input_artifacts"])
            self.assertIn("artifacts/research/storm-lens-outline.json", receipt["input_artifacts"])

    def test_evidence_requires_findings_pool_for_full_dossier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.retrieved_run(workspace, register_findings=False)
            inputs = self.write_evidence_inputs(run, workspace)
            result = self.invoke_evidence(run, inputs)
            self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
            self.assertIn("storm-findings-pool.jsonl", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/30-evidence.json").exists())

    def test_theory_claim_requires_theory_grade_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.retrieved_run(workspace)
            inputs = self.write_evidence_inputs(run, workspace)
            claims, _contradictions, _uncertainties, _outline = inputs
            records = [json.loads(line) for line in claims.read_text(encoding="utf-8").splitlines()]
            records[0]["claim_text"] = "Arendt's banality of evil is the controlling theoretical frame."
            claims.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
            result = self.invoke_evidence(run, inputs)
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("theory claim C001 requires academic, book, expert, or peer-reviewed support", result.stderr)
            self.assertFalse((run / "state/generations/g0001/receipts/30-evidence.json").exists())

    def test_evidence_preflight_theory_reports_source_types_without_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.retrieved_run(workspace)
            inputs = self.write_evidence_inputs(run, workspace)
            claims, _contradictions, _uncertainties, _outline = inputs
            records = [json.loads(line) for line in claims.read_text(encoding="utf-8").splitlines()]
            records[0]["claim_text"] = "文化工业 is the controlling theoretical frame."
            claims.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
            result = self.invoke(
                "evidence", str(run), "--claims", str(claims), "--preflight-theory",
            )
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["theory_claims"][0]["claim_id"], "C001")
            self.assertEqual(payload["theory_claims"][0]["supporting_sources"][0]["source_type"], "official")
            self.assertFalse((run / "state/generations/g0001/receipts/30-evidence.json").exists())

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

    def test_draft_preflight_reports_paragraph_context_without_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.evidenced_run(workspace)
            draft, mapping = self.write_draft_inputs(run, workspace)
            rows = mapping.read_text(encoding="utf-8").splitlines()
            mapping.write_text("\n".join(rows[:-1]) + "\n", encoding="utf-8")
            result = self.invoke(
                "draft", str(run), "--draft-md", str(draft),
                "--paragraph-map-jsonl", str(mapping), "--preflight",
            )
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["mode"], "draft-preflight")
            self.assertTrue(payload["length"]["references_excluded"])
            self.assertTrue(any(item["paragraph"] for item in payload["errors"]))
            self.assertFalse((run / "state/generations/g0001/receipts/40-draft.json").exists())

    def test_build_paragraph_map_infers_sources_and_citations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.evidenced_run(workspace)
            draft, mapping = self.write_draft_inputs(run, workspace)
            sidecar = workspace / "paragraph-sidecar.jsonl"
            rows = []
            for line in mapping.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                rows.append({
                    "text_locator": record["text_locator"],
                    "claim_ids": record["claim_ids"],
                })
            sidecar.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            generated = workspace / "generated-paragraph-map.jsonl"
            result = self.invoke(
                "build-paragraph-map", str(run),
                "--draft-md", str(draft),
                "--sidecar-jsonl", str(sidecar),
                "--to", str(generated),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            generated_rows = [json.loads(line) for line in generated.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(generated_rows), len(rows))
            self.assertTrue(all(row["source_ids"] and row["citation_keys"] for row in generated_rows))
            result = self.invoke(
                "draft", str(run), "--draft-md", str(draft),
                "--paragraph-map-jsonl", str(generated),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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

    def write_findings_inputs(self, run: Path, workspace: Path) -> Path:
        manifest_path = run / "work/generations/g0001/artifacts/research/retrieval-manifest.jsonl"
        manifests = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
        findings = []
        for index, manifest in enumerate(manifests, start=1):
            question_id = str(manifest["query_id"])
            question_index = int(question_id[1:])
            claim_ids = [f"C{question_index:03d}"]
            if question_index == 10:
                claim_ids.extend(["C011", "C012"])
            source_id = str(manifest["source_id"])
            findings.append({
                "schema_version": "2.0",
                "finding_id": f"F{index:03d}",
                "tasklet_id": question_id.replace("Q", "T", 1),
                "question_id": question_id,
                "summary": f"Finding {index} closes the planned research tasklet with inspectable evidence.",
                "source_ids": [source_id],
                "evidence_locators": [{
                    "source_id": source_id,
                    "locator": manifest["locator"],
                    "excerpt": manifest["excerpt"],
                    "snapshot_sha256": manifest["snapshot_sha256"],
                }],
                "claim_ids": claim_ids,
                "status": "usable",
                "confidence": "high",
                "limitations": ["The finding is scoped to the cited source."],
                "produced_by": "subagent-fixture-1",
                "created_at": "2026-06-23T00:00:00Z",
            })
        path = workspace / "findings.jsonl"
        path.write_text("".join(json.dumps(item) + "\n" for item in findings), encoding="utf-8")
        return path

    def retrieved_run(
        self,
        workspace: Path,
        *,
        register_findings: bool = True,
        register_lens_for_evidence: bool = True,
    ) -> Path:
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
        if register_findings:
            findings = self.write_findings_inputs(run, workspace)
            result = self.invoke("findings", str(run), "--findings-jsonl", str(findings))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            if register_lens_for_evidence:
                self.register_lens_conflicts(run, workspace)
                self.register_lens_outline(run, workspace)
        return run

    def evidenced_run(self, workspace: Path, *, strict_lens: bool = False) -> Path:
        run = self.retrieved_run(workspace)
        inputs = self.write_evidence_inputs(run, workspace)
        result = self.invoke_evidence(run, inputs)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return run

    def drafted_run(self, workspace: Path, *, strict_lens: bool = False) -> Path:
        run = self.evidenced_run(workspace, strict_lens=strict_lens)
        draft, mapping = self.write_draft_inputs(run, workspace)
        result = self.invoke(
            "draft", str(run), "--draft-md", str(draft),
            "--paragraph-map-jsonl", str(mapping),
        )
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
        init_args = [
            "init", "--topic", "Governed research", "--question",
            "What evidence supports the conclusion?", "--workspace", str(workspace),
            "--output", "test-run",
            "--profile-selection-mode", "user_requested_default",
            "--profile-selection-evidence", "test explicitly requested the default full dossier profile",
        ]
        result = self.invoke(*init_args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        run = workspace / "output/storm-deepresearch/test-run"
        plan = workspace / "research-plan.json"
        source_plan = workspace / "source-plan.json"
        plan.write_text(json.dumps(valid_research_plan_v2()), encoding="utf-8")
        source_plan.write_text(json.dumps(valid_source_plan()), encoding="utf-8")
        self.register_lens_perspectives(run, workspace)
        result = self.invoke(
            "plan", str(run), "--plan-json", str(plan),
            "--source-plan-json", str(source_plan),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return run

    def prompt_pack_hash(self) -> str:
        return sha256_file(ROOT / "references/storm-lens-prompt-pack.md")

    def register_lens_perspectives(self, run: Path, workspace: Path) -> None:
        brief = run / "work/generations/g0001/inputs/brief.json"
        lens = workspace / "storm-lens-perspectives.json"
        lens.write_text(json.dumps(valid_storm_lens_artifact(
            "P1", self.prompt_pack_hash(), {"inputs/brief.json": sha256_file(brief)}
        )), encoding="utf-8")
        result = self.invoke("lens-perspectives", str(run), "--input-json", str(lens))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def register_lens_conflicts(self, run: Path, workspace: Path) -> None:
        artifacts = run / "work/generations/g0001/artifacts"
        inputs = {
            "artifacts/research/storm-findings-pool.jsonl": sha256_file(artifacts / "research/storm-findings-pool.jsonl"),
            "artifacts/research/finding-coverage.json": sha256_file(artifacts / "research/finding-coverage.json"),
            "artifacts/research/source-register.jsonl": sha256_file(artifacts / "research/source-register.jsonl"),
            "artifacts/research/retrieval-manifest.jsonl": sha256_file(artifacts / "research/retrieval-manifest.jsonl"),
        }
        lens = workspace / "storm-lens-conflicts.json"
        lens.write_text(json.dumps(valid_storm_lens_artifact(
            "P2", self.prompt_pack_hash(), inputs
        )), encoding="utf-8")
        result = self.invoke("lens-conflicts", str(run), "--input-json", str(lens))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def register_lens_outline(self, run: Path, workspace: Path) -> None:
        artifacts = run / "work/generations/g0001/artifacts"
        inputs = {
            "artifacts/research/storm-findings-pool.jsonl": sha256_file(artifacts / "research/storm-findings-pool.jsonl"),
            "artifacts/research/storm-lens-conflicts.json": sha256_file(artifacts / "research/storm-lens-conflicts.json"),
        }
        lens = workspace / "storm-lens-outline.json"
        lens.write_text(json.dumps(valid_storm_lens_artifact(
            "P3", self.prompt_pack_hash(), inputs
        )), encoding="utf-8")
        result = self.invoke("lens-outline", str(run), "--input-json", str(lens))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def invoke(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *arguments], cwd=ROOT,
            capture_output=True, text=True, check=False,
        )


if __name__ == "__main__":
    unittest.main()
