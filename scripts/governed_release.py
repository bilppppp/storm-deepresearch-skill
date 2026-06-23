#!/usr/bin/env python3
"""Trust-aware release construction for governed STORM runs."""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from scripts.contract_io import (
    ContractError,
    load_json,
    load_jsonl,
    validate_governed_trust_evidence,
    validate_human_approval,
    validate_release_manifest,
    validate_reverification_record,
)
from scripts.harness_io import (
    atomic_copy_file,
    atomic_promote,
    atomic_write_json,
    atomic_write_text,
    compute_skill_package_hash,
    sha256_file,
)
from scripts.output_paths import package_child
from scripts.run_state import (
    RunLayout,
    Stage,
    commit_stage_receipt,
    latest_generation,
    load_json as load_receipt,
    verify_stage_precondition,
)


SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Imported by the single storm-research release command."
ROOT = Path(__file__).resolve().parents[1]
YAO_SCAN_DIRS = (
    "agents", "assets", "docs", "evals", "references", "runtime", "scripts",
    "security", "skill-ir", "templates",
)
YAO_ROOT_FILES = ("SKILL.md", "README.md", "manifest.json", "requirements-ci.txt", "Makefile")
YAO_TEXT_SUFFIXES = {".css", ".js", ".md", ".json", ".jsonl", ".yaml", ".yml", ".py", ".sh", ".txt", ".toml"}

RELEASE_FILES = {
    "brief.json",
    "exports/report.html",
    "exports/report.pdf",
    "report.md",
    "research/claim-evidence-ledger.jsonl",
    "research/contradiction-ledger.json",
    "research/contradiction-map.md",
    "research/evidence-map.md",
    "research/peer-review.md",
    "research/report-claim-map.json",
    "research/report-outline.json",
    "research/research-plan.json",
    "research/source-plan.json",
    "research/source-register.jsonl",
    "research/source-register.md",
    "research/uncertainty-ledger.md",
    "validation/release-manifest.json",
    "validation/render-manifest.json",
    "validation/validation-report.json",
    "validation/validation-report.md",
}
RELEASE_MANIFEST = "validation/release-manifest.json"


class ReleaseGateError(ValueError):
    """Raised when governed Trust or release boundaries are not proven."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_datetime(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReleaseGateError(f"invalid ISO datetime: {value}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def yao_source_contract_hash(root: Path) -> str:
    """Recompute Yao's documented source-contract hash without importing Yao internals."""
    files: set[Path] = set()
    for relative in YAO_ROOT_FILES:
        path = root / relative
        if path.is_file() and not path.is_symlink():
            files.add(path)
    for relative in YAO_SCAN_DIRS:
        directory = root / relative
        if not directory.is_dir() or directory.is_symlink():
            continue
        for path in directory.rglob("*"):
            if (
                path.is_file() and not path.is_symlink()
                and path.suffix in YAO_TEXT_SUFFIXES and path.stat().st_size <= 1_000_000
            ):
                files.add(path)
    digest = hashlib.sha256()
    for path in sorted(files):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _require_external_file(path: Path | None, layout: RunLayout, label: str) -> Path:
    if path is None:
        raise ReleaseGateError(f"{label} is required")
    if path.is_symlink():
        raise ReleaseGateError(f"{label} cannot be a symlink")
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ReleaseGateError(f"{label} is missing: {resolved}")
    if resolved.is_relative_to(layout.root) or resolved.is_relative_to(ROOT):
        raise ReleaseGateError(f"{label} must be host-controlled outside the run and Skill package")
    return resolved


def _registry_package_hash(payload: dict[str, Any]) -> str:
    checksums = payload.get("checksums")
    if isinstance(checksums, dict):
        return str(checksums.get("package_sha256", ""))
    return str(payload.get("package_sha256", ""))


def validate_trust_boundary(
    layout: RunLayout,
    trust_path: Path | None,
    registry_path: Path | None,
    internal_package_hash: str,
) -> tuple[Path, Path, dict[str, Any]]:
    trust_file = _require_external_file(trust_path, layout, "trust evidence")
    registry_file = _require_external_file(registry_path, layout, "Registry metadata")
    trust = load_json(trust_file)
    errors = validate_governed_trust_evidence(trust)
    if errors:
        raise ReleaseGateError("; ".join(errors))
    report_ref = Path(str(trust["yao_trust_report"]))
    if not report_ref.is_absolute():
        report_ref = trust_file.parent / report_ref
    yao_report_file = _require_external_file(report_ref, layout, "Yao Trust report")
    if sha256_file(yao_report_file) != trust.get("yao_trust_report_sha256"):
        raise ReleaseGateError("Yao Trust report hash mismatch")
    report = load_json(yao_report_file)
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if report.get("ok") is not True or report.get("failures"):
        raise ReleaseGateError("Yao Trust report is not passing")
    for field in ("permission_missing_count", "permission_invalid_count", "permission_expired_count"):
        if summary.get(field) != 0:
            raise ReleaseGateError(f"Yao Trust report has nonzero {field}")
    yao_hash = yao_source_contract_hash(ROOT)
    registry = load_json(registry_file)
    registry_hash = _registry_package_hash(registry)
    if registry_hash != yao_hash:
        raise ReleaseGateError("Registry package hash mismatch")
    if summary.get("package_hash_scope") != "source-contract-without-generated-reports":
        raise ReleaseGateError("Yao Trust report uses an unsupported package hash scope")
    if summary.get("package_sha256") != yao_hash:
        raise ReleaseGateError("Yao Trust package hash mismatch")
    if trust.get("skill_package_sha256") != internal_package_hash:
        raise ReleaseGateError("governed Skill package hash mismatch")
    if trust.get("registry_package_sha256") != registry_hash:
        raise ReleaseGateError("trust evidence Registry package hash mismatch")
    return trust_file, registry_file, trust


def validate_approval(
    layout: RunLayout,
    approval_path: Path | None,
    validation_receipt_sha256: str,
    *,
    now: datetime,
) -> Path:
    approval_file = _require_external_file(approval_path, layout, "human approval")
    approval = load_json(approval_file)
    errors = validate_human_approval(approval)
    if errors:
        raise ReleaseGateError("; ".join(errors))
    if approval.get("scope") != "public_release" or approval.get("decision") != "approved":
        raise ReleaseGateError("human approval does not authorize public release")
    if approval.get("approved_artifact_sha256") != validation_receipt_sha256:
        raise ReleaseGateError("human approval does not bind the validation receipt")
    if _parse_datetime(approval.get("reviewed_at")) > now:
        raise ReleaseGateError("human approval reviewed_at is in the future")
    expires_at = approval.get("expires_at")
    if expires_at is not None and _parse_datetime(expires_at) < now:
        raise ReleaseGateError("human approval is expired")
    return approval_file


def required_reverification_sources(
    brief: dict[str, Any],
    claims: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    *,
    today: date,
) -> set[str]:
    source_by_id = {str(source.get("source_id")): source for source in sources}
    max_age_days = int(brief.get("freshness_policy", {}).get("max_age_days", 0))
    required: set[str] = set()
    for claim in claims:
        if not claim.get("freshness_required"):
            continue
        for source_id in claim.get("supporting_source_ids", []):
            source = source_by_id.get(str(source_id))
            if source is None:
                required.add(str(source_id))
                continue
            retrieved = _parse_datetime(source.get("retrieved_at")).date()
            if retrieved + timedelta(days=max_age_days) < today:
                required.add(str(source_id))
    return required


def validate_reverification(
    layout: RunLayout,
    records_path: Path | None,
    required_ids: set[str],
    sources: list[dict[str, Any]],
    *,
    now: datetime,
    max_age_days: int,
) -> tuple[set[str], str | None]:
    if records_path is None:
        if required_ids:
            raise ReleaseGateError("current evidence requires host re-verification")
        return set(), None
    records_file = _require_external_file(records_path, layout, "re-verification records")
    records = load_jsonl(records_file)
    source_by_id = {str(source.get("source_id")): source for source in sources}
    verified: set[str] = set()
    errors: list[str] = []
    for record in records:
        record_errors = list(validate_reverification_record(record))
        source_id = str(record.get("source_id", ""))
        source = source_by_id.get(source_id)
        if source is None:
            record_errors.append(f"re-verification references unknown source {source_id}")
            errors.extend(record_errors)
            continue
        if record.get("canonical_url") != source.get("canonical_url"):
            record_errors.append(f"re-verification URL mismatch for {source_id}")
        if record.get("status") != "current":
            record_errors.append(f"re-verification did not confirm current status for {source_id}")
        if record.get("content_sha256") != source.get("content_hash"):
            record_errors.append(f"re-verification content hash mismatch for {source_id}")
        checked_at = _parse_datetime(record.get("checked_at"))
        if checked_at > now or checked_at.date() + timedelta(days=max_age_days) < now.date():
            record_errors.append(f"re-verification is outside the freshness window for {source_id}")
        if not record_errors:
            verified.add(source_id)
        errors.extend(record_errors)
    missing = sorted(required_ids - verified)
    if missing:
        errors.append("missing current re-verification for: " + ", ".join(missing))
    if errors:
        raise ReleaseGateError("; ".join(dict.fromkeys(errors)))
    return verified, sha256_file(records_file)


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _source_register_markdown(sources: list[dict[str, Any]]) -> str:
    lines = [
        "# Source Register", "",
        "| ID | Title | Organization | Published | Retrieved | Type | Class | Tier | Location | Freshness |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for source in sources:
        values = (
            source.get("source_id"), source.get("title"), source.get("author_or_org"),
            source.get("published_at") or "unknown", source.get("retrieved_at"),
            source.get("source_type"), source.get("primary_class"), source.get("reliability_tier"),
            source.get("canonical_url") or source.get("file_ref"), source.get("freshness_status"),
        )
        lines.append("| " + " | ".join(_cell(value) for value in values) + " |")
    return "\n".join(lines) + "\n"


def _evidence_map_markdown(claims: list[dict[str, Any]]) -> str:
    lines = [
        "# Evidence Map", "",
        "| Claim | Type | Status | Supports | Contradicts | Strength | Confidence | Limitation |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for claim in claims:
        values = (
            claim.get("claim_text"), claim.get("claim_type"), claim.get("status"),
            ", ".join(claim.get("supporting_source_ids", [])),
            ", ".join(claim.get("contradicting_source_ids", [])),
            claim.get("evidence_strength"), claim.get("confidence"), claim.get("limitation"),
        )
        lines.append("| " + " | ".join(_cell(value) for value in values) + " |")
    return "\n".join(lines) + "\n"


def _contradiction_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Contradiction Map", ""]
    conflicts = payload.get("conflicts", [])
    if not conflicts:
        return "\n".join([*lines, "No conflicts assessed.", ""])
    for conflict in conflicts:
        lines.extend([
            f"## {_cell(conflict.get('conflict_id', 'Conflict'))}", "",
            f"- Claim: {_cell(conflict.get('claim_id', ''))}",
            f"- Sources: {_cell(', '.join(conflict.get('source_ids', [])))}",
            f"- Analysis: {_cell(conflict.get('analysis', ''))}",
            f"- Resolution: {_cell(conflict.get('resolution_status', ''))}",
            f"- Change condition: {_cell(conflict.get('change_condition', ''))}", "",
        ])
    return "\n".join(lines)


def _uncertainty_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Uncertainty Ledger", ""]
    records = payload.get("uncertainties", [])
    if not records:
        return "\n".join([*lines, "No unresolved uncertainties recorded.", ""])
    for record in records:
        lines.extend([
            f"## {_cell(record.get('uncertainty_id', 'Uncertainty'))}", "",
            f"- Claim: {_cell(record.get('claim_id', ''))}",
            f"- Description: {_cell(record.get('description', ''))}",
            f"- Impact: {_cell(record.get('impact', ''))}",
            f"- Next evidence: {_cell(record.get('next_evidence', ''))}", "",
        ])
    return "\n".join(lines)


def _copy_release_source(source: Path, destination: Path, generation_root: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise ReleaseGateError(f"release source is missing or unsafe: {source}")
    resolved = source.resolve()
    if not resolved.is_relative_to(generation_root.resolve()):
        raise ReleaseGateError(f"release source escapes current generation: {source}")
    atomic_copy_file(source, destination)


def _ensure_release_targets_available(layout: RunLayout, generation: int) -> None:
    targets = (
        ("release receipt", layout.receipt(generation, Stage.RELEASE)),
        ("authoritative release package", layout.artifact(generation, "release-package")),
        ("public release projection", package_child(layout.root, "release")),
    )
    for label, path in targets:
        if path.exists() or path.is_symlink():
            raise ReleaseGateError(f"{label} already exists")


def _build_release_staging(
    layout: RunLayout,
    generation: int,
    manifest_base: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    generation_root = layout.generation_root(generation)
    artifacts = layout.artifact(generation, ".")
    staging = package_child(layout.root, f"work/.staging/g{generation:04d}/release-{uuid.uuid4().hex}")
    staging.mkdir(parents=True, exist_ok=False)
    copy_map = {
        "brief.json": layout.generation_input(generation, "brief.json"),
        "research/research-plan.json": artifacts / "research/research-plan.json",
        "research/source-plan.json": artifacts / "research/source-plan.json",
        "research/source-register.jsonl": artifacts / "research/source-register.jsonl",
        "research/claim-evidence-ledger.jsonl": artifacts / "research/claim-evidence-ledger.jsonl",
        "research/report-outline.json": artifacts / "research/report-outline.json",
        "research/contradiction-ledger.json": artifacts / "research/contradiction-ledger.json",
        "research/peer-review.md": artifacts / "research/peer-review.md",
        "report.md": artifacts / "report.md",
        "exports/report.html": artifacts / "exports/report.html",
        "validation/render-manifest.json": artifacts / "validation/render-manifest.json",
        "validation/validation-report.json": artifacts / "validation/validation-report.json",
        "validation/validation-report.md": artifacts / "validation/validation-report.md",
    }
    pdf = artifacts / "exports/report.pdf"
    if pdf.is_file():
        copy_map["exports/report.pdf"] = pdf
    for relative, source in copy_map.items():
        _copy_release_source(source, staging / relative, generation_root)
    sources = load_jsonl(artifacts / "research/source-register.jsonl")
    claims = load_jsonl(artifacts / "research/claim-evidence-ledger.jsonl")
    contradictions = load_json(artifacts / "research/contradiction-ledger.json")
    uncertainties = load_json(artifacts / "research/uncertainty-ledger.json")
    paragraph_map = load_jsonl(artifacts / "research/reviewed-paragraph-map.jsonl")
    atomic_write_text(staging / "research/source-register.md", _source_register_markdown(sources))
    atomic_write_text(staging / "research/evidence-map.md", _evidence_map_markdown(claims))
    atomic_write_text(staging / "research/contradiction-map.md", _contradiction_markdown(contradictions))
    atomic_write_text(staging / "research/uncertainty-ledger.md", _uncertainty_markdown(uncertainties))
    atomic_write_json(staging / "research/report-claim-map.json", {
        "schema_version": "2.0",
        "mappings": paragraph_map,
    })
    observed = {
        path.relative_to(staging).as_posix()
        for path in staging.rglob("*") if path.is_file() and not path.is_symlink()
    }
    allowed_payload = RELEASE_FILES - {RELEASE_MANIFEST}
    if not observed <= allowed_payload:
        raise ReleaseGateError("release staging contains undeclared files")
    required = allowed_payload - {"exports/report.pdf"}
    missing = sorted(required - observed)
    if missing:
        raise ReleaseGateError("release staging is missing: " + ", ".join(missing))
    files = {
        relative: sha256_file(staging / relative)
        for relative in sorted(observed)
    }
    manifest = {**manifest_base, "files": files}
    errors = validate_release_manifest(manifest)
    if errors:
        raise ReleaseGateError("; ".join(errors))
    atomic_write_json(staging / RELEASE_MANIFEST, manifest)
    for relative, expected in files.items():
        if sha256_file(staging / relative) != expected:
            raise ReleaseGateError(f"release staging hash mismatch: {relative}")
    return staging, manifest


def release_run(
    run_dir: Path,
    *,
    trust_path: Path | None,
    registry_path: Path | None,
    approval_path: Path | None,
    reverification_path: Path | None,
) -> Path:
    layout = RunLayout(run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise ReleaseGateError("run has no generation")
    internal_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.RELEASE, internal_hash)
    if trust_path is None:
        raise ReleaseGateError("trust evidence is required")
    trust_file, registry_file, _ = validate_trust_boundary(
        layout, trust_path, registry_path, internal_hash
    )
    validation_receipt = load_receipt(layout.receipt(generation, Stage.VALIDATION))
    validation_digest = str(validation_receipt["receipt_sha256"])
    if approval_path is None:
        raise ReleaseGateError("human approval is required for public release")
    now = _utc_now()
    approval_file = validate_approval(
        layout, approval_path, validation_digest, now=now
    )
    brief = load_json(layout.generation_input(generation, "brief.json"))
    artifacts = layout.artifact(generation, ".")
    claims = load_jsonl(artifacts / "research/claim-evidence-ledger.jsonl")
    sources = load_jsonl(artifacts / "research/source-register.jsonl")
    required_ids = required_reverification_sources(brief, claims, sources, today=now.date())
    verified_ids, records_hash = validate_reverification(
        layout,
        reverification_path,
        required_ids,
        sources,
        now=now,
        max_age_days=int(brief["freshness_policy"]["max_age_days"]),
    )
    _ensure_release_targets_available(layout, generation)
    manifest_base = {
        "schema_version": "2.0",
        "run_id": layout.root.name,
        "generation": generation,
        "release_created_at": _iso(now),
        "validation_receipt_sha256": validation_digest,
        "skill_package_sha256": internal_hash,
        "registry_metadata_sha256": sha256_file(registry_file),
        "trust_report_sha256": sha256_file(trust_file),
        "human_approval_sha256": sha256_file(approval_file),
        "reverification_summary": {
            "required_source_ids": sorted(required_ids),
            "verified_source_ids": sorted(verified_ids),
            "record_sha256": records_hash,
        },
    }
    staging, _ = _build_release_staging(layout, generation, manifest_base)
    authoritative = layout.artifact(generation, "release-package")
    atomic_promote(staging, authoritative)
    outputs = sorted(path for path in authoritative.rglob("*") if path.is_file())
    validation_report = layout.artifact(generation, "validation/validation-report.json")
    commit_stage_receipt(
        layout,
        generation=generation,
        stage=Stage.RELEASE,
        package_hash=internal_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts={
            "artifacts/validation/validation-report.json": sha256_file(validation_report),
        },
        output_paths=outputs,
    )
    projection_staging = package_child(
        layout.root, f"work/.staging/g{generation:04d}/release-projection-{uuid.uuid4().hex}"
    )
    shutil.copytree(authoritative, projection_staging, symlinks=False)
    projected_files = {
        path.relative_to(projection_staging).as_posix()
        for path in projection_staging.rglob("*") if path.is_file() and not path.is_symlink()
    }
    public_manifest = load_json(projection_staging / RELEASE_MANIFEST)
    expected_projection = set(public_manifest["files"]) | {RELEASE_MANIFEST}
    if projected_files != expected_projection:
        raise ReleaseGateError("release projection does not match the strict allowlist")
    for path in projection_staging.rglob("*"):
        if path.is_symlink():
            raise ReleaseGateError("release projection contains a symlink")
    for relative, expected in public_manifest["files"].items():
        if sha256_file(projection_staging / relative) != expected:
            raise ReleaseGateError(f"release projection hash mismatch: {relative}")
    release = package_child(layout.root, "release")
    atomic_promote(projection_staging, release)
    return release
