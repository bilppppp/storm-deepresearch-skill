from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.init_research_package import initialize
from scripts.render_audit_views import render
from scripts.validate_package import measure_report_units
from tests.test_contracts import valid_claim, valid_source


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
VALIDATOR = ROOT / "scripts" / "validate_package.py"
EXPORTER = ROOT / "scripts" / "export_report.py"
REPORT_FIXTURE = ROOT / "tests" / "fixtures" / "export" / "report.md"
TEMPLATE = ROOT / "templates" / "report.html.j2"


class ValidatePackageTests(unittest.TestCase):
    def validate(self, package: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(PYTHON), str(VALIDATOR), str(package)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_valid_full_package_passes_and_writes_structured_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_valid_package(Path(tmp))
            result = self.validate(package)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads((package / "validation" / "validation-report.json").read_text(encoding="utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["package_state"], "validated")
            self.assertEqual(payload["summary"]["failed"], 0)
            self.assertTrue(all(set(item) == {"check_id", "severity", "status", "path", "message", "repair_command"} for item in payload["checks"]))

    def test_missing_required_pdf_exits_six(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_valid_package(Path(tmp))
            (package / "exports" / "report.pdf").unlink()
            result = self.validate(package)
            self.assertEqual(result.returncode, 6)
            self.assertIn("required PDF is missing", result.stderr)

    def test_reduced_package_can_omit_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_valid_package(Path(tmp))
            brief_path = package / "brief.json"
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            brief["output_mode"] = "reduced"
            brief_path.write_text(json.dumps(brief), encoding="utf-8")
            (package / "exports" / "report.pdf").unlink()
            manifest_path = package / "validation" / "render-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["report_pdf_sha256"] = ""
            manifest["pdf_renderer"] = "none"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self.validate(package)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_empty_evidence_exits_five(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_valid_package(Path(tmp))
            (package / "research" / "claim-evidence-ledger.jsonl").write_text("", encoding="utf-8")
            (package / "research" / "report-claim-map.json").write_text('{"schema_version":"1.0","mappings":[]}', encoding="utf-8")
            result = self.validate(package)
            self.assertEqual(result.returncode, 5)
            self.assertIn("no material claims", result.stderr)

    def test_fabricated_source_id_exits_five(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_valid_package(Path(tmp))
            claim = valid_claim()
            claim["supporting_source_ids"] = ["S999"]
            claim["evidence_locators"] = [{"source_id": "S999", "locator": "section 1", "excerpt": "invented"}]
            (package / "research" / "claim-evidence-ledger.jsonl").write_text(json.dumps(claim) + "\n", encoding="utf-8")
            result = self.validate(package)
            self.assertEqual(result.returncode, 5)
            self.assertIn("unknown source_id S999", result.stderr)

    def test_stale_source_for_current_claim_exits_five(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_valid_package(Path(tmp))
            source = valid_source()
            source["freshness_status"] = "stale"
            (package / "research" / "source-register.jsonl").write_text(json.dumps(source) + "\n", encoding="utf-8")
            result = self.validate(package)
            self.assertEqual(result.returncode, 5)
            self.assertIn("requires current evidence", result.stderr)

    def test_template_marker_exits_six(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_valid_package(Path(tmp))
            report_path = package / "report.md"
            report_path.write_text(report_path.read_text(encoding="utf-8") + "\n{{ unresolved }}\n", encoding="utf-8")
            result = self.validate(package)
            self.assertEqual(result.returncode, 6)
            self.assertIn("template marker", result.stderr)

    def test_local_path_leak_exits_seven(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_valid_package(Path(tmp))
            report_path = package / "report.md"
            report_path.write_text(report_path.read_text(encoding="utf-8") + "\n/Users/example/private.txt\n", encoding="utf-8")
            result = self.validate(package)
            self.assertEqual(result.returncode, 7)
            self.assertIn("local path leak", result.stderr)

    def test_validation_report_rejects_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            package = build_valid_package(Path(tmp))
            shutil.rmtree(package / "validation")
            (package / "validation").symlink_to(Path(outside), target_is_directory=True)
            result = self.validate(package)
            self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
            self.assertIn("escapes the research package", result.stderr)
            self.assertFalse((Path(outside) / "validation-report.json").exists())

    def test_html_title_drift_exits_six(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_valid_package(Path(tmp))
            html_path = package / "exports" / "report.html"
            html_path.write_text(html_path.read_text(encoding="utf-8").replace(
                "<title>Evidence-Grounded Research Fixture</title>", "<title>Wrong title</title>"
            ), encoding="utf-8")
            result = self.validate(package)
            self.assertEqual(result.returncode, 6)
            self.assertIn("title mismatch", result.stderr)

    def test_short_report_exits_six(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_valid_package(Path(tmp))
            brief_path = package / "brief.json"
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            brief["length_contract"].update({"minimum": 5000, "target": 5500, "maximum": 6000})
            brief_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            plan_path = package / "research" / "research-plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["report_outline"].update({"minimum": 5000, "target": 5500, "maximum": 6000})
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result = self.validate(package)
            self.assertEqual(result.returncode, 6)
            self.assertIn("report body is shorter than the length contract", result.stderr)

    def test_unmapped_answered_question_exits_five(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_valid_package(Path(tmp))
            plan_path = package / "research" / "research-plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["questions"].append({
                "question_id": "Q002",
                "perspective": "skeptic",
                "text": "What evidence would overturn the conclusion?",
                "status": "answered",
                "claim_ids": ["C001"],
                "disposition_note": "The answer should appear in the report.",
            })
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result = self.validate(package)
            self.assertEqual(result.returncode, 5)
            self.assertIn("answered question Q002 is not used by report_outline", result.stderr)

    def test_length_measure_excludes_references(self) -> None:
        text = "# 标题\n\n## 分析\n\n这是有效正文。\n\n## References\n\n" + ("引用资料" * 100)
        count = measure_report_units(text, "characters")
        self.assertGreater(count, 4)
        self.assertLess(count, 30)


def build_valid_package(parent: Path) -> Path:
    package = parent / "output"
    initialize("Evidence-Grounded Research Fixture", "How can formats remain consistent?", package)
    brief_path = package / "brief.json"
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    brief["package_state"] = "rendered"
    brief["depth_level"] = "briefing"
    brief["length_contract"] = {
        "unit": "words",
        "minimum": 100,
        "target": 500,
        "maximum": 2000,
        "content_standard": "evidence_led",
    }
    brief_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    research = package / "research"
    research_plan = json.loads((research / "research-plan.json").read_text(encoding="utf-8"))
    research_plan.update({
        "status": "complete",
        "perspectives": ["practitioner", "academic", "skeptic", "economist", "historian"],
        "questions": [{
            "question_id": "Q001",
            "perspective": "academic",
            "text": "What evidence supports the pipeline?",
            "status": "answered",
            "claim_ids": ["C001"],
            "disposition_note": "Used in Key Findings.",
        }],
        "source_priorities": ["official"],
        "stopping_conditions": ["material claim closure reaches 100%"],
        "report_outline": {
            "status": "complete",
            "unit": "words",
            "minimum": 100,
            "target": 500,
            "maximum": 2000,
            "sections": [{
                "section_id": "SEC01",
                "title": "Key Findings",
                "purpose": "Explain the evidence-backed finding.",
                "target_units": 300,
                "question_ids": ["Q001"],
                "claim_ids": ["C001"],
                "required_elements": ["claim", "mechanism", "evidence", "limitation"],
            }],
        },
    })
    (research / "research-plan.json").write_text(json.dumps(research_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (research / "source-register.jsonl").write_text(json.dumps(valid_source(), ensure_ascii=False) + "\n", encoding="utf-8")
    (research / "claim-evidence-ledger.jsonl").write_text(json.dumps(valid_claim(), ensure_ascii=False) + "\n", encoding="utf-8")
    (research / "report-claim-map.json").write_text(json.dumps({
        "schema_version": "1.0",
        "mappings": [{"anchor": "key-findings", "fingerprint": "fixture-finding", "claim_ids": ["C001"]}],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    render(package)
    shutil.copy2(REPORT_FIXTURE, package / "report.md")
    export = subprocess.run(
        [
            str(PYTHON), str(EXPORTER), str(package),
            "--template", str(TEMPLATE), "--title", "Evidence-Grounded Research Fixture", "--require-pdf",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if export.returncode != 0:
        raise AssertionError(export.stdout + export.stderr)
    return package


if __name__ == "__main__":
    unittest.main()
