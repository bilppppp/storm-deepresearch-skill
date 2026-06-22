from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class LibraryContractTests(unittest.TestCase):
    def test_skill_frontmatter_and_execution_surfaces_are_present(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        _, raw_frontmatter, body = text.split("---", 2)
        frontmatter = yaml.safe_load(raw_frontmatter)
        self.assertEqual(frontmatter["name"], "storm-deepresearch-skill")
        self.assertIn("source-grounded deep research", frontmatter["description"])
        self.assertIn("Do not use", frontmatter["description"])
        for heading in (
            "## Compact Workflow",
            "## Decision Points",
            "## Output Contract",
            "## Failure Policy",
            "## Resources",
        ):
            self.assertIn(heading, body)
        self.assertIn("scripts/run_checks.py", body)
        self.assertIn("evals/", body)
        self.assertIn("8000–10000", body)
        self.assertIn("report_outline", body)
        self.assertIn("output-path-policy.md", body)
        self.assertIn("Never reinitialize", body)

    def test_skill_initial_load_stays_within_library_budget(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        estimated_tokens = len(re.findall(r"\S+", text)) * 4 // 3
        self.assertLessEqual(estimated_tokens, 1300)

    def test_yao_resource_boundary_accepts_library_budget(self) -> None:
        script = Path.home() / ".agents" / "skills" / "yao-meta-skill" / "scripts" / "resource_boundary_check.py"
        result = subprocess.run(
            [sys.executable, str(script), str(ROOT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_manifest_declares_library_governance(self) -> None:
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        expected = {
            "name": "storm-deepresearch-skill",
            "version": "0.4.0",
            "owner": "陈旭",
            "updated_at": "2026-06-22",
            "review_cadence": "quarterly",
            "status": "active",
            "maturity_tier": "library",
            "lifecycle_stage": "library",
            "context_budget_tier": "library",
        }
        for key, value in expected.items():
            self.assertEqual(manifest.get(key), value, key)
        components = set(manifest["factory_components"])
        self.assertTrue({"references", "scripts", "evals", "templates", "tests", "reports"} <= components)
        self.assertEqual(manifest["license"], "MIT-0")
        self.assertTrue((ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT-0\n"))
        self.assertEqual(
            set(manifest["target_platforms"]),
            {"openai", "claude", "agent-skills", "vscode", "generic"},
        )

    def test_interface_is_portable_and_has_safe_defaults(self) -> None:
        interface = yaml.safe_load((ROOT / "agents" / "interface.yaml").read_text(encoding="utf-8"))
        self.assertEqual(interface["interface"]["display_name"], "STORM DeepResearch")
        self.assertIn("evidence", interface["interface"]["short_description"].lower())
        compatibility = interface["compatibility"]
        self.assertEqual(compatibility["canonical_format"], "agent-skills")
        self.assertEqual(compatibility["execution"]["context"], "inline")
        self.assertEqual(compatibility["execution"]["shell"], "bash")
        self.assertEqual(compatibility["trust"]["remote_inline_execution"], "forbid")
        expected_targets = {"openai", "claude", "agent-skills", "vscode", "generic"}
        self.assertEqual(set(compatibility["adapter_targets"]), expected_targets)
        self.assertEqual(set(compatibility["degradation"]), expected_targets)
        defaults = interface["contract"]["defaults"]
        self.assertEqual(defaults["output_collision_policy"], "fail")
        self.assertEqual(defaults["ledger_update_policy"], "monotonic-merge")

    def test_packaging_expectations_cover_distributed_adapters(self) -> None:
        expectations = json.loads(
            (ROOT / "evals" / "packaging_expectations.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(expectations["required_targets"]),
            {"openai", "claude", "generic", "vscode"},
        )
        self.assertIn("compiler", expectations["required_fields"])
        for target in expectations["required_targets"]:
            self.assertIn(f"{target}_required_files", expectations)

    def test_trigger_cases_cover_positive_negative_and_near_neighbor(self) -> None:
        cases = json.loads((ROOT / "evals" / "trigger_cases.json").read_text(encoding="utf-8"))
        for key in ("should_trigger", "should_not_trigger", "near_neighbor"):
            self.assertGreaterEqual(len(cases[key]), 5, key)
            self.assertEqual(len(cases[key]), len(set(cases[key])), key)


if __name__ == "__main__":
    unittest.main()
