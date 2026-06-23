from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from scripts.governed_release import (
    RELEASE_FILES,
    ReleaseGateError,
    required_reverification_sources,
    validate_reverification,
    yao_source_contract_hash,
)
from scripts.harness_io import compute_skill_package_hash, sha256_file
from scripts.run_state import RunLayout, Stage, verify_receipt_chain
from tests.test_validate_package import build_valid_governed_run


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/storm_research.py"


class GovernedReleaseTests(unittest.TestCase):
    def test_missing_trust_evidence_blocks_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.validated_run(workspace)
            result = self.invoke("release", str(run))
            self.assertEqual(result.returncode, 9, result.stdout + result.stderr)
            self.assertIn("trust evidence is required", result.stderr)
            self.assertFalse(self.release_receipt(run).exists())

    def test_public_release_requires_human_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.validated_run(workspace)
            trust, registry = self.write_trust_bundle(workspace)
            result = self.invoke(
                "release", str(run), "--trust", str(trust), "--registry", str(registry)
            )
            self.assertEqual(result.returncode, 9, result.stdout + result.stderr)
            self.assertIn("human approval is required", result.stderr)
            self.assertFalse(self.release_receipt(run).exists())

    def test_registry_hash_mismatch_blocks_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.validated_run(workspace)
            trust, registry = self.write_trust_bundle(workspace)
            payload = json.loads(registry.read_text(encoding="utf-8"))
            payload["checksums"]["package_sha256"] = "0" * 64
            registry.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            approval = self.write_approval(workspace, run)
            result = self.invoke_release(run, trust, registry, approval)
            self.assertEqual(result.returncode, 9, result.stdout + result.stderr)
            self.assertIn("Registry package hash mismatch", result.stderr)

    def test_false_read_only_attestation_blocks_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.validated_run(workspace)
            trust, registry = self.write_trust_bundle(workspace)
            payload = json.loads(trust.read_text(encoding="utf-8"))
            payload["skill_directory_read_only"] = False
            trust.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            approval = self.write_approval(workspace, run)
            result = self.invoke_release(run, trust, registry, approval)
            self.assertEqual(result.returncode, 9, result.stdout + result.stderr)
            self.assertIn("read-only trust boundary", result.stderr)

    def test_release_allowlist_excludes_intermediate_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.validated_run(workspace)
            intermediate = run / "work/retrieval-inputs/raw.jsonl"
            intermediate.parent.mkdir(parents=True)
            intermediate.write_text("{}\n", encoding="utf-8")
            trust, registry = self.write_trust_bundle(workspace)
            approval = self.write_approval(workspace, run)
            result = self.invoke_release(run, trust, registry, approval)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            release = run / "release"
            self.assertTrue((release / "validation/release-manifest.json").is_file())
            self.assertFalse((release / "raw.jsonl").exists())
            self.assertFalse((release / "work").exists())
            self.assertFalse((release / "state").exists())
            self.assertTrue(self.release_receipt(run).is_file())
            verify_receipt_chain(
                RunLayout(run), 1, Stage.RELEASE, compute_skill_package_hash(ROOT)
            )
            observed = {
                path.relative_to(release).as_posix()
                for path in release.rglob("*") if path.is_file()
            }
            self.assertEqual(observed, RELEASE_FILES)
            manifest = json.loads(
                (release / "validation/release-manifest.json").read_text(encoding="utf-8")
            )
            for relative, expected in manifest["files"].items():
                self.assertEqual(sha256_file(release / relative), expected)

    def test_release_receipt_collision_leaves_no_authoritative_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.validated_run(workspace)
            self.release_receipt(run).write_text("{}\n", encoding="utf-8")
            trust, registry = self.write_trust_bundle(workspace)
            approval = self.write_approval(workspace, run)
            result = self.invoke_release(run, trust, registry, approval)
            self.assertEqual(result.returncode, 9, result.stdout + result.stderr)
            self.assertIn("release receipt already exists", result.stderr)
            self.assertFalse(
                (run / "work/generations/g0001/artifacts/release-package").exists()
            )

    def test_approval_must_bind_validation_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = self.validated_run(workspace)
            trust, registry = self.write_trust_bundle(workspace)
            approval = self.write_approval(workspace, run)
            payload = json.loads(approval.read_text(encoding="utf-8"))
            payload["approved_artifact_sha256"] = "0" * 64
            approval.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            result = self.invoke_release(run, trust, registry, approval)
            self.assertEqual(result.returncode, 9, result.stdout + result.stderr)
            self.assertIn("does not bind the validation receipt", result.stderr)

    def test_stale_current_claim_requires_host_reverification(self) -> None:
        brief = {"freshness_policy": {"max_age_days": 30}}
        claims = [{"freshness_required": True, "supporting_source_ids": ["S001"]}]
        sources = [{
            "source_id": "S001",
            "retrieved_at": "2026-01-01T00:00:00Z",
            "canonical_url": "https://www.nist.gov/current",
            "content_hash": "a" * 64,
        }]
        required = required_reverification_sources(
            brief, claims, sources, today=date(2026, 6, 23)
        )
        self.assertEqual(required, {"S001"})
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            run.mkdir()
            with self.assertRaisesRegex(ReleaseGateError, "requires host re-verification"):
                validate_reverification(
                    RunLayout(run), None, required, sources,
                    now=datetime(2026, 6, 23, tzinfo=timezone.utc), max_age_days=30,
                )

    def test_historical_claim_does_not_require_online_reverification(self) -> None:
        required = required_reverification_sources(
            {"freshness_policy": {"max_age_days": 1}},
            [{"freshness_required": False, "supporting_source_ids": ["S001"]}],
            [{"source_id": "S001", "retrieved_at": "2020-01-01T00:00:00Z"}],
            today=date(2026, 6, 23),
        )
        self.assertEqual(required, set())

    def validated_run(self, workspace: Path) -> Path:
        run = build_valid_governed_run(workspace)
        result = self.invoke("validate", str(run))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return run

    def write_trust_bundle(self, workspace: Path) -> tuple[Path, Path]:
        package_hash = compute_skill_package_hash(ROOT)
        registry_hash = yao_source_contract_hash(ROOT)
        registry = workspace / "host-registry-package.json"
        registry.write_text(json.dumps({
            "schema_version": "2.0",
            "name": "storm-deepresearch-skill",
            "version": "1.0.0",
            "checksums": {"package_sha256": registry_hash},
        }) + "\n", encoding="utf-8")
        yao_report = workspace / "yao-security-trust-report.json"
        yao_report.write_text(json.dumps({
            "ok": True,
            "summary": {
                "package_hash_scope": "source-contract-without-generated-reports",
                "package_sha256": registry_hash,
                "permission_missing_count": 0,
                "permission_invalid_count": 0,
                "permission_expired_count": 0,
            },
            "failures": [],
        }) + "\n", encoding="utf-8")
        trust = workspace / "host-trust-evidence.json"
        trust.write_text(json.dumps({
            "schema_version": "1.0",
            "status": "verified",
            "skill_package_sha256": package_hash,
            "registry_package_sha256": registry_hash,
            "yao_trust_report": str(yao_report),
            "yao_trust_report_sha256": sha256_file(yao_report),
            "skill_directory_read_only": True,
            "registry_read_only": True,
            "trust_report_read_only": True,
            "verified_by": "host-test-harness",
            "verified_at": "2026-06-23T00:00:00Z",
        }) + "\n", encoding="utf-8")
        return trust, registry

    def write_approval(self, workspace: Path, run: Path) -> Path:
        receipt = json.loads(
            (run / "state/generations/g0001/receipts/70-validation.json").read_text(encoding="utf-8")
        )
        approval = workspace / "human-approval.json"
        approval.write_text(json.dumps({
            "schema_version": "2.0",
            "approval_id": "APP001",
            "reviewer": "human-reviewer",
            "scope": "public_release",
            "decision": "approved",
            "reason": "The governed validation packet is approved for public release.",
            "approved_artifact_sha256": receipt["receipt_sha256"],
            "reviewed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "expires_at": None,
        }) + "\n", encoding="utf-8")
        return approval

    def invoke_release(
        self, run: Path, trust: Path, registry: Path, approval: Path
    ) -> subprocess.CompletedProcess[str]:
        return self.invoke(
            "release", str(run), "--trust", str(trust), "--registry", str(registry),
            "--approval", str(approval),
        )

    def invoke(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *arguments], cwd=ROOT,
            capture_output=True, text=True, check=False,
        )

    @staticmethod
    def release_receipt(run: Path) -> Path:
        return run / "state/generations/g0001/receipts/80-release.json"


if __name__ == "__main__":
    unittest.main()
