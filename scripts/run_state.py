#!/usr/bin/env python3
"""Immutable generations, stage receipts, and journal state for governed runs."""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from scripts.contract_io import validate_receipt
from scripts.harness_io import (
    atomic_promote,
    canonical_json_bytes,
    canonical_json_sha256,
    load_canonical_json,
    sha256_file,
)
from scripts.output_paths import package_child, resolve_package_dir


SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Owns all governed run state transitions and receipt verification."


class ReceiptError(ValueError):
    """Raised when a receipt or its bound artifacts cannot be recomputed."""


class StagePreconditionError(ReceiptError):
    """Raised when a stage lacks a valid predecessor receipt."""


class Stage(str, Enum):
    INIT = "init"
    PLAN = "plan"
    RETRIEVAL = "retrieval"
    EVIDENCE = "evidence"
    DRAFT = "draft"
    REVIEW = "review"
    RENDER = "render"
    VALIDATION = "validation"
    RELEASE = "release"


STAGE_ORDER = tuple(Stage)
STAGE_FILE_PREFIX = {
    Stage.INIT: "00",
    Stage.PLAN: "10",
    Stage.RETRIEVAL: "20",
    Stage.EVIDENCE: "30",
    Stage.DRAFT: "40",
    Stage.REVIEW: "50",
    Stage.RENDER: "60",
    Stage.VALIDATION: "70",
    Stage.RELEASE: "80",
}
STATE_BY_STAGE = {
    Stage.INIT: "initialized",
    Stage.PLAN: "planned",
    Stage.RETRIEVAL: "retrieved",
    Stage.EVIDENCE: "evidence_ready",
    Stage.DRAFT: "drafted",
    Stage.REVIEW: "reviewed",
    Stage.RENDER: "rendered",
    Stage.VALIDATION: "validated",
    Stage.RELEASE: "released",
}


def stage_file_name(stage: Stage) -> str:
    return f"{STAGE_FILE_PREFIX[stage]}-{stage.value}.json"


def stages_through(stage: Stage) -> tuple[Stage, ...]:
    return STAGE_ORDER[: STAGE_ORDER.index(stage) + 1]


def previous_stage(stage: Stage) -> Stage | None:
    index = STAGE_ORDER.index(stage)
    return None if index == 0 else STAGE_ORDER[index - 1]


@dataclass(frozen=True)
class RunLayout:
    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", resolve_package_dir(self.root))

    def generation_root(self, generation: int) -> Path:
        _require_generation_number(generation)
        return package_child(self.root, f"work/generations/g{generation:04d}")

    def generation_input(self, generation: int, relative: str) -> Path:
        return package_child(self.generation_root(generation), f"inputs/{relative}")

    def artifact(self, generation: int, relative: str) -> Path:
        return package_child(self.generation_root(generation), f"artifacts/{relative}")

    def evidence_cache(self, generation: int, relative: str) -> Path:
        return package_child(self.generation_root(generation), f"evidence-cache/{relative}")

    def receipt(self, generation: int, stage: Stage) -> Path:
        _require_generation_number(generation)
        return package_child(
            self.root,
            f"state/generations/g{generation:04d}/receipts/{stage_file_name(stage)}",
        )

    @property
    def journal(self) -> Path:
        return package_child(self.root, "state/run-journal.jsonl")


def _require_generation_number(generation: int) -> None:
    if not isinstance(generation, int) or generation < 1:
        raise ValueError("generation must be a positive integer")


def create_generation(layout: RunLayout, generation: int) -> Path:
    root = layout.generation_root(generation)
    if root.exists() or root.is_symlink():
        raise FileExistsError(root)
    for relative in ("inputs", "artifacts", "evidence-cache"):
        (root / relative).mkdir(parents=True, exist_ok=False)
    layout.receipt(generation, Stage.INIT).parent.mkdir(parents=True, exist_ok=False)
    append_journal_event(layout, {
        "event": "generation_created",
        "generation": generation,
        "recorded_at": _utc_now(),
    })
    return root


def latest_generation(layout: RunLayout) -> int | None:
    root = package_child(layout.root, "work/generations")
    if not root.is_dir():
        return None
    generations = [
        int(match.group(1))
        for path in root.iterdir()
        if path.is_dir() and (match := re.fullmatch(r"g(\d{4})", path.name))
    ]
    return max(generations, default=None)


def append_journal_event(layout: RunLayout, event: dict[str, object]) -> None:
    path = layout.journal
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(event)
    file_descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(file_descriptor, payload)
        os.fsync(file_descriptor)
    finally:
        os.close(file_descriptor)


def receipt_digest(payload: dict[str, object]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "receipt_sha256"}
    return canonical_json_sha256(unsigned)


def load_json(path: Path) -> dict[str, Any]:
    try:
        return load_canonical_json(path)
    except ValueError as exc:
        raise ReceiptError(str(exc)) from exc


def _artifact_path(layout: RunLayout, generation: int, logical_path: str) -> Path:
    if not isinstance(logical_path, str) or not logical_path:
        raise ReceiptError("artifact path must be a non-empty string")
    return package_child(layout.generation_root(generation), logical_path)


def verify_artifact_hashes(
    layout: RunLayout, generation: int, receipt: dict[str, object]
) -> None:
    for field in ("input_artifacts", "output_artifacts"):
        records = receipt.get(field)
        if not isinstance(records, dict):
            raise ReceiptError(f"{field} must be an object")
        for logical_path, expected_hash in records.items():
            path = _artifact_path(layout, generation, str(logical_path))
            if not path.is_file() or path.is_symlink():
                raise ReceiptError(f"artifact is missing or unsafe: {logical_path}")
            observed = sha256_file(path)
            if observed != expected_hash:
                raise ReceiptError(f"artifact hash mismatch: {logical_path}")


def verify_receipt_chain(
    layout: RunLayout, generation: int, through: Stage, package_hash: str
) -> None:
    previous_digest = ""
    for stage in stages_through(through):
        path = layout.receipt(generation, stage)
        if not path.is_file() or path.is_symlink():
            raise ReceiptError(f"missing {stage.value} receipt")
        receipt = load_json(path)
        if receipt_digest(receipt) != receipt.get("receipt_sha256"):
            raise ReceiptError(f"receipt digest mismatch: {stage.value}")
        contract_errors = validate_receipt(receipt)
        if contract_errors:
            raise ReceiptError(f"invalid {stage.value} receipt: {'; '.join(contract_errors)}")
        if receipt.get("stage") != stage.value:
            raise ReceiptError(f"receipt stage mismatch: {stage.value}")
        if receipt.get("generation") != generation:
            raise ReceiptError(f"receipt generation mismatch: {stage.value}")
        if receipt.get("previous_receipt_sha256") != previous_digest:
            raise ReceiptError(f"previous receipt digest mismatch: {stage.value}")
        if receipt.get("skill_package_sha256") != package_hash:
            raise ReceiptError(f"skill package hash mismatch: {stage.value}")
        verify_artifact_hashes(layout, generation, receipt)
        previous_digest = str(receipt["receipt_sha256"])


def verify_stage_precondition(
    layout: RunLayout, generation: int, stage: Stage, package_hash: str
) -> None:
    predecessor = previous_stage(stage)
    if predecessor is None:
        return
    if not layout.receipt(generation, predecessor).is_file():
        raise StagePreconditionError(f"missing {predecessor.value} receipt")
    try:
        verify_receipt_chain(layout, generation, predecessor, package_hash)
    except ReceiptError as exc:
        raise StagePreconditionError(str(exc)) from exc


def _logical_hashes(
    layout: RunLayout, generation: int, paths: Iterable[Path]
) -> dict[str, str]:
    generation_root = layout.generation_root(generation).resolve()
    result: dict[str, str] = {}
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_relative_to(generation_root) or resolved == generation_root:
            raise ReceiptError(f"receipt artifact escapes generation: {path}")
        if not resolved.is_file() or path.is_symlink():
            raise ReceiptError(f"receipt artifact is missing or unsafe: {path}")
        logical = resolved.relative_to(generation_root).as_posix()
        result[logical] = sha256_file(resolved)
    return dict(sorted(result.items()))


def _validate_declared_inputs(
    layout: RunLayout, generation: int, inputs: dict[str, str]
) -> None:
    for logical_path, expected_hash in inputs.items():
        path = _artifact_path(layout, generation, logical_path)
        if not path.is_file() or path.is_symlink():
            raise ReceiptError(f"input artifact is missing or unsafe: {logical_path}")
        if sha256_file(path) != expected_hash:
            raise ReceiptError(f"input artifact hash mismatch: {logical_path}")


def _write_receipt_no_clobber(path: Path, receipt: dict[str, object]) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(canonical_json_bytes(receipt))
            handle.flush()
            os.fsync(handle.fileno())
        atomic_promote(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def commit_stage_receipt(
    layout: RunLayout,
    *,
    generation: int,
    stage: Stage,
    package_hash: str,
    validator_hash: str,
    input_artifacts: dict[str, str],
    output_paths: Iterable[Path],
    checks: Iterable[dict[str, object]] = (),
    run_id: str | None = None,
) -> dict[str, object]:
    verify_stage_precondition(layout, generation, stage, package_hash)
    path = layout.receipt(generation, stage)
    if path.exists() or path.is_symlink():
        raise FileExistsError(path)
    _validate_declared_inputs(layout, generation, input_artifacts)
    predecessor = previous_stage(stage)
    previous_digest = ""
    if predecessor is not None:
        previous_receipt = load_json(layout.receipt(generation, predecessor))
        previous_digest = str(previous_receipt["receipt_sha256"])
    receipt: dict[str, object] = {
        "schema_version": "2.0",
        "run_id": run_id or layout.root.name,
        "generation": generation,
        "stage": stage.value,
        "status": "passed",
        "previous_receipt_sha256": previous_digest,
        "skill_package_sha256": package_hash,
        "validator_sha256": validator_hash,
        "input_artifacts": dict(sorted(input_artifacts.items())),
        "output_artifacts": _logical_hashes(layout, generation, output_paths),
        "checks": list(checks),
        "completed_at": _utc_now(),
    }
    receipt["receipt_sha256"] = receipt_digest(receipt)
    contract_errors = validate_receipt(receipt)
    if contract_errors:
        raise ReceiptError(f"invalid receipt: {'; '.join(contract_errors)}")
    _write_receipt_no_clobber(path, receipt)
    append_journal_event(layout, {
        "event": "stage_passed",
        "generation": generation,
        "stage": stage.value,
        "receipt_sha256": receipt["receipt_sha256"],
        "recorded_at": receipt["completed_at"],
    })
    return receipt


def receipt_chain_status(
    layout: RunLayout, generation: int, package_hash: str
) -> dict[str, object]:
    receipts: list[dict[str, object]] = []
    last_valid: Stage | None = None
    for stage in STAGE_ORDER:
        path = layout.receipt(generation, stage)
        if path.is_symlink():
            return {
                "state": "invalid",
                "generation": generation,
                "last_valid_stage": last_valid.value if last_valid else None,
                "next_stage": stage.value,
                "invalid_stage": stage.value,
                "error": f"receipt is unsafe: {stage.value}",
                "invalidated_artifacts": [],
                "receipts": receipts,
            }
        if not path.is_file():
            state = STATE_BY_STAGE[last_valid] if last_valid else "uninitialized"
            return {
                "state": state,
                "generation": generation,
                "last_valid_stage": last_valid.value if last_valid else None,
                "next_stage": stage.value,
                "invalid_stage": None,
                "error": None,
                "invalidated_artifacts": [],
                "receipts": receipts,
            }
        invalidated_artifacts: list[str] = []
        try:
            receipt = load_json(path)
            outputs = receipt.get("output_artifacts")
            if isinstance(outputs, dict):
                invalidated_artifacts = sorted(str(path) for path in outputs)
            verify_receipt_chain(layout, generation, stage, package_hash)
        except ReceiptError as exc:
            return {
                "state": "invalid",
                "generation": generation,
                "last_valid_stage": last_valid.value if last_valid else None,
                "next_stage": stage.value,
                "invalid_stage": stage.value,
                "error": str(exc),
                "invalidated_artifacts": invalidated_artifacts,
                "receipts": receipts,
            }
        receipts.append({
            "stage": stage.value,
            "receipt_sha256": str(receipt["receipt_sha256"]),
        })
        last_valid = stage
    return {
        "state": STATE_BY_STAGE[Stage.RELEASE],
        "generation": generation,
        "last_valid_stage": Stage.RELEASE.value,
        "next_stage": None,
        "invalid_stage": None,
        "error": None,
        "invalidated_artifacts": [],
        "receipts": receipts,
    }


def derived_state(layout: RunLayout, generation: int, package_hash: str) -> str:
    state = "uninitialized"
    for stage in STAGE_ORDER:
        if not layout.receipt(generation, stage).is_file():
            break
        verify_receipt_chain(layout, generation, stage, package_hash)
        state = STATE_BY_STAGE[stage]
    return state


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
