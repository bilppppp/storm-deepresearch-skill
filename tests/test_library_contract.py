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
        self.assertIn("research_profile", body)
        self.assertIn("default_full_dossier", body)
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

    def test_manifest_declares_governed_3_0(self) -> None:
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        expected = {
            "name": "storm-deepresearch-skill",
            "version": "3.0.0",
            "owner": "陈旭",
            "updated_at": "2026-07-03",
            "review_cadence": "per-release",
            "status": "active",
            "maturity_tier": "governed",
            "lifecycle_stage": "governed",
            "context_budget_tier": "governed",
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
        interface_text = (ROOT / "agents" / "interface.yaml").read_text(encoding="utf-8")
        for phrase in ("receipt chain", "human approval", "missing evidence"):
            self.assertIn(phrase, interface_text)
        interface = yaml.safe_load(interface_text)
        self.assertEqual(interface["interface"]["display_name"], "STORM DeepResearch")
        self.assertIn("evidence", interface["interface"]["short_description"].lower())
        self.assertIn("research_profile", interface["interface"]["default_prompt"])
        self.assertIn("default_full_dossier", interface["interface"]["default_prompt"])
        compatibility = interface["compatibility"]
        self.assertEqual(compatibility["canonical_format"], "agent-skills")
        self.assertEqual(compatibility["execution"]["context"], "inline")
        self.assertEqual(compatibility["execution"]["shell"], "bash")
        self.assertEqual(compatibility["trust"]["remote_inline_execution"], "forbid")
        expected_targets = {"openai", "claude", "agent-skills", "vscode", "generic"}
        self.assertEqual(set(compatibility["adapter_targets"]), expected_targets)
        self.assertEqual(set(compatibility["degradation"]), expected_targets)
        defaults = interface["contract"]["defaults"]
        self.assertEqual(defaults["research_profile"], "default_full_dossier")
        visible_profiles = set(defaults["research_profile_options"])
        self.assertTrue({
            "default_full_dossier",
            "critique_deepresearch",
            "closed_corpus",
            "briefing",
            "repair_existing_run",
        } <= visible_profiles)
        self.assertNotIn("strict_storm_lens", visible_profiles)
        self.assertEqual(
            defaults["legacy_research_profile_aliases"],
            {"strict_storm_lens": "default_full_dossier"},
        )
        self.assertEqual(
            defaults["primary_research_profile_options"],
            ["default_full_dossier", "briefing"],
        )
        self.assertEqual(defaults["output_collision_policy"], "fail")
        self.assertEqual(defaults["ledger_update_policy"], "monotonic-merge")
        self.assertEqual(defaults["release_policy"], "validation-plus-trust-plus-human-approval")

    def test_docs_name_academic_retrieval_contract(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        interface = (ROOT / "agents" / "interface.yaml").read_text(encoding="utf-8")
        for token in (
            "retrieval-audit.jsonl",
            "academic baseline",
            "bibliographic",
            "corpus-seeded",
            "gap-fill",
        ):
            self.assertIn(token, readme)
        self.assertIn("academic baseline", skill)
        self.assertIn("retrieval-audit.jsonl", interface)

    def test_readme_declares_current_version(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("当前版本：`3.0.0`", readme)

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
