from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.harness_io import (
    atomic_promote,
    atomic_write_json,
    canonical_json_sha256,
    compute_skill_package_hash,
)


class HarnessIOTests(unittest.TestCase):
    def test_canonical_json_hash_ignores_key_order(self) -> None:
        self.assertEqual(
            canonical_json_sha256({"b": 2, "a": 1}),
            canonical_json_sha256({"a": 1, "b": 2}),
        )

    def test_atomic_promote_rejects_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, destination = root / "source", root / "destination"
            source.write_text("new", encoding="utf-8")
            destination.write_text("old", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                atomic_promote(source, destination)
            self.assertEqual(destination.read_text(encoding="utf-8"), "old")
            self.assertEqual(source.read_text(encoding="utf-8"), "new")

    def test_atomic_write_json_writes_canonical_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "record.json"
            atomic_write_json(path, {"b": 2, "a": 1})
            self.assertEqual(path.read_text(encoding="utf-8"), '{"a":1,"b":2}\n')
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"a": 1, "b": 2})

    def test_package_hash_uses_declared_files_and_ignores_generated_trees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "reports").mkdir()
            (root / ".venv").mkdir()
            (root / "manifest.json").write_text(
                json.dumps({"factory_components": ["scripts", "reports"]}),
                encoding="utf-8",
            )
            (root / "SKILL.md").write_text("skill", encoding="utf-8")
            governed = root / "scripts" / "worker.py"
            governed.write_text("VALUE = 1\n", encoding="utf-8")
            (root / "reports" / "mutable.json").write_text("one", encoding="utf-8")
            (root / ".venv" / "cache").write_text("one", encoding="utf-8")

            first = compute_skill_package_hash(root)
            (root / "reports" / "mutable.json").write_text("two", encoding="utf-8")
            (root / ".venv" / "cache").write_text("two", encoding="utf-8")
            self.assertEqual(compute_skill_package_hash(root), first)

            governed.write_text("VALUE = 2\n", encoding="utf-8")
            self.assertNotEqual(compute_skill_package_hash(root), first)


if __name__ == "__main__":
    unittest.main()
