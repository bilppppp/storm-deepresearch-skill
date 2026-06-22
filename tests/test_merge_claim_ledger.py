from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.merge_claim_ledger import merge_claim_records
from tests.test_contracts import valid_claim


ROOT = Path(__file__).resolve().parents[1]


class ClaimLedgerMergeTests(unittest.TestCase):
    def test_merge_preserves_existing_claims_and_order(self) -> None:
        first = valid_claim()
        second = valid_claim()
        second["claim_id"] = "C002"
        second["claim_text"] = "A second material claim."
        merged = merge_claim_records([first], [second])
        self.assertEqual([claim["claim_id"] for claim in merged], ["C001", "C002"])
        self.assertEqual(merged[0], first)

    def test_explicit_same_id_revision_cannot_delete_other_claims(self) -> None:
        first = valid_claim()
        second = valid_claim()
        second["claim_id"] = "C002"
        revision = dict(first)
        revision["limitation"] = "Revised limitation."
        merged = merge_claim_records([first, second], [revision])
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["limitation"], "Revised limitation.")
        self.assertEqual(merged[1], second)

    def test_invalid_update_leaves_existing_claim_ledger_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "package"
            ledger = package / "research" / "claim-evidence-ledger.jsonl"
            ledger.parent.mkdir(parents=True)
            original = json.dumps(valid_claim()) + "\n"
            ledger.write_text(original, encoding="utf-8")
            update = Path(tmp) / "claims.jsonl"
            update.write_text('{"claim_id":"C002"}\n', encoding="utf-8")
            result = subprocess.run(
                [
                    str(ROOT / ".venv" / "bin" / "python"),
                    str(ROOT / "scripts" / "merge_claim_ledger.py"),
                    str(update),
                    "--package",
                    str(package),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 4)
            self.assertEqual(ledger.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
