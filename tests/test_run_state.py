from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.harness_io import atomic_write_json
from scripts.run_state import (
    ReceiptError,
    RunLayout,
    Stage,
    StagePreconditionError,
    append_journal_event,
    commit_stage_receipt,
    create_generation,
    receipt_digest,
    verify_receipt_chain,
    verify_stage_precondition,
)
from tests.governed_fixtures import make_run_with_plan_receipt


PACKAGE_HASH = "a" * 64
VALIDATOR_HASH = "b" * 64


class RunStateTests(unittest.TestCase):
    def test_stage_cannot_advance_without_previous_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            layout = RunLayout(Path(tmp))
            create_generation(layout, 1)
            with self.assertRaisesRegex(StagePreconditionError, "missing plan receipt"):
                verify_stage_precondition(layout, 1, Stage.RETRIEVAL, PACKAGE_HASH)

    def test_modified_upstream_artifact_invalidates_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            layout = make_run_with_plan_receipt(Path(tmp))
            plan = layout.artifact(1, "research/research-plan.json")
            plan.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ReceiptError, "artifact hash mismatch"):
                verify_receipt_chain(layout, 1, Stage.PLAN, PACKAGE_HASH)

    def test_forged_status_does_not_bypass_receipt_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            layout = make_run_with_plan_receipt(Path(tmp))
            path = layout.receipt(1, Stage.PLAN)
            receipt = json.loads(path.read_text(encoding="utf-8"))
            receipt["status"] = "failed"
            receipt["receipt_sha256"] = receipt_digest(receipt)
            receipt["status"] = "passed"
            atomic_write_json(path, receipt)
            with self.assertRaisesRegex(ReceiptError, "receipt digest mismatch"):
                verify_receipt_chain(layout, 1, Stage.PLAN, PACKAGE_HASH)

    def test_generation_and_receipt_are_no_clobber(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            layout = RunLayout(Path(tmp))
            create_generation(layout, 1)
            with self.assertRaises(FileExistsError):
                create_generation(layout, 1)
            brief = layout.generation_input(1, "brief.json")
            atomic_write_json(brief, {"schema_version": "2.0"})
            commit_stage_receipt(
                layout,
                generation=1,
                stage=Stage.INIT,
                package_hash=PACKAGE_HASH,
                validator_hash=VALIDATOR_HASH,
                input_artifacts={},
                output_paths=[brief],
            )
            with self.assertRaises(FileExistsError):
                commit_stage_receipt(
                    layout,
                    generation=1,
                    stage=Stage.INIT,
                    package_hash=PACKAGE_HASH,
                    validator_hash=VALIDATOR_HASH,
                    input_artifacts={},
                    output_paths=[brief],
                )

    def test_journal_appends_canonical_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            layout = RunLayout(Path(tmp))
            append_journal_event(layout, {"event": "first", "generation": 1})
            append_journal_event(layout, {"event": "second", "generation": 1})
            lines = layout.journal.read_text(encoding="utf-8").splitlines()
            self.assertEqual([json.loads(line)["event"] for line in lines], ["first", "second"])

if __name__ == "__main__":
    unittest.main()
