#!/usr/bin/env python3
"""Validate a governed STORM run and commit validation authority on success."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contract_io import (
    ContractError,
    MAX_REVIEW_ROLES,
    REVIEW_ISSUE_STAGE,
    load_json,
    load_jsonl,
    max_review_rubric_binding,
    validate_conflict_review_record,
    validate_finding_record,
    validate_brief,
    validate_report_outline,
    validate_research_plan,
    validate_retrieval_input_record,
    validate_tasklet_record,
    validate_storm_review_analysis,
    validate_source_plan,
)
from scripts.normalize_retrieval import (
    validate_captured_retrieval_artifacts,
    validate_retrieval_audit,
)
from scripts.normalize_retrieval import independent_source_identity
from scripts.export_report import markdown_sections, markdown_title
from scripts.harness_io import (
    atomic_copy_file,
    atomic_promote,
    atomic_write_json,
    atomic_write_text,
    canonical_json_sha256,
    compute_skill_package_hash,
    sha256_file,
)
from scripts.output_paths import OutputPathError, package_child
from scripts.report_traceability import (
    body_length,
    body_length_metrics,
    cited_sources_in_body,
    quote_limit_errors,
    validate_report_traceability,
    validate_review_set,
)
from scripts.run_state import (
    ReceiptError,
    RunLayout,
    Stage,
    commit_stage_receipt,
    latest_generation,
    verify_receipt_chain,
)
from scripts.validate_evidence import (
    compute_coverage,
    validate_absence_searches,
    validate_claim_closure,
    validate_material_capture_depth,
)


SCRIPT_INTERFACE = "public-worker-cli"
SCRIPT_INTERFACE_REASON = "Offline governed validation and validation receipt commitment."
ROOT = Path(__file__).resolve().parents[1]
EXIT_CONTRACT = 4
EXIT_EVIDENCE = 5
EXIT_EXPORT = 6
EXIT_SAFETY = 7
EXIT_STAGE = 8
SHALLOW_SOURCE_TYPES = {"community", "encyclopedia", "search_result"}
USER_SOURCE_TYPES = {"user_provided_file"}

RENDER_ARTIFACTS = {
    "drafts/report-v1.md",
    "review-candidate/report.md",
    "review-candidate/paragraph-map.jsonl",
    "review-candidate/revision-map.json",
    "exports/report.html",
    "exports/report.pdf",
    "report.md",
    "research/citation-index.json",
    "research/claim-evidence-ledger.jsonl",
    "research/contradiction-ledger.json",
    "research/paragraph-map.jsonl",
    "research/peer-review.json",
    "research/peer-review.md",
    "research/review-request.json",
    "research/reviewer-provenance.json",
    "research/reviewer-transcript.txt",
    "research/report-outline.json",
    "research/research-plan.json",
    "research/retrieval-manifest.jsonl",
    "research/retrieval-audit.jsonl",
    "research/reviewed-paragraph-map.jsonl",
    "research/revision-map.json",
    "research/source-plan.json",
    "research/source-register.jsonl",
    "research/storm-tasklets.jsonl",
    "research/uncertainty-ledger.json",
    "validation/render-manifest.json",
}
OPTIONAL_ARTIFACTS = {
    "research/absence-search-ledger.jsonl",
    "research/finding-coverage.json",
    "research/review-loop.json",
    "research/storm-findings-pool.jsonl",
    "research/storm-lens-perspectives.json",
    "research/storm-lens-conflicts.json",
    "research/storm-lens-outline.json",
    "research/storm-lens-red-team.json",
    "research/execution/retrieval-input.jsonl",
    "research/execution/retrieval-provenance.json",
    "research/execution/retrieval-transcript.txt",
    "research/execution/draft-input.md",
    "research/execution/draft-paragraph-map-input.jsonl",
    "research/execution/draft-provenance.json",
    "research/execution/draft-transcript.txt",
}
VALIDATION_ARTIFACTS = {
    "validation/validation-report.json",
    "validation/validation-report.md",
}
STORM_LENS_ARTIFACTS = {
    "P1": ("research/storm-lens-perspectives.json", "before_retrieval"),
    "P2": ("research/storm-lens-conflicts.json", "after_findings"),
    "P3": ("research/storm-lens-outline.json", "after_conflicts"),
    "P4": ("research/storm-lens-red-team.json", "after_draft"),
}
STORM_LENS_PROMPT_PACK = ROOT / "references/storm-lens-prompt-pack.md"
LOCAL_PATH_PATTERNS = (
    re.compile(r"/Users/[^\s<]+"),
    re.compile(r"/mnt/data/[^\s<]+"),
    re.compile(r"file:///[^\s<]+"),
    re.compile(r"[A-Za-z]:\\\\[^\s<]+"),
)
TEMPLATE_MARKER = re.compile(r"(?:\{\{|\{%|\{#)")
INTERNAL_ID = re.compile(r"\b[CS]\d{3}\b")
AUDIT_BOILERPLATE_PATTERNS = (
    re.compile(r"这条可审计来源"),
    re.compile(r"该段把这条公开引用定位为证据图谱"),
    re.compile(r"this auditable source", re.IGNORECASE),
    re.compile(r"this source record", re.IGNORECASE),
)


@dataclass(frozen=True)
class Check:
    check_id: str
    severity: str
    status: str
    path: str
    message: str
    repair_command: str
    exit_code: int = 0

    def public(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("exit_code")
        return payload


def add_check(
    checks: list[Check],
    check_id: str,
    errors: Iterable[str],
    path: str,
    success: str,
    repair: str,
    exit_code: int,
) -> None:
    failures = list(dict.fromkeys(str(error) for error in errors if str(error)))
    checks.append(Check(
        check_id=check_id,
        severity="error" if failures else "info",
        status="fail" if failures else "pass",
        path=path,
        message="; ".join(failures) if failures else success,
        repair_command=repair if failures else "",
        exit_code=exit_code if failures else 0,
    ))


def _files_under(root: Path) -> tuple[set[str], list[str]]:
    files: set[str] = set()
    unsafe: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            unsafe.append(f"symlink is forbidden in governed artifacts: {relative}")
        elif path.is_file():
            files.add(relative)
    return files, unsafe


def _parse_artifacts(root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        try:
            if path.suffix == ".json":
                json.loads(path.read_text(encoding="utf-8"))
            elif path.suffix == ".jsonl":
                for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                    if line.strip():
                        value = json.loads(line)
                        if not isinstance(value, dict):
                            errors.append(f"{relative}:{line_number} must contain a JSON object")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"{relative} is not valid JSON: {exc}")
    return errors


def _structural_checks(
    artifacts: Path, *, pdf_required: bool, validation_committed: bool = False
) -> tuple[list[Check], int]:
    checks: list[Check] = []
    files, unsafe = _files_under(artifacts)
    add_check(
        checks, "artifact-boundary", unsafe, "artifacts/",
        "artifact tree contains no symlinks", "replace symlinks with governed files", EXIT_SAFETY,
    )
    if unsafe:
        return checks, EXIT_SAFETY
    missing = sorted(RENDER_ARTIFACTS - files)
    optional_artifacts = set(OPTIONAL_ARTIFACTS)
    if validation_committed:
        optional_artifacts.update(VALIDATION_ARTIFACTS)
    unexpected = sorted(files - RENDER_ARTIFACTS - optional_artifacts)
    missing_non_pdf = [item for item in missing if item != "exports/report.pdf"]
    add_check(
        checks, "artifact-inventory", [
            *(f"required artifact is missing: {item}" for item in missing_non_pdf),
            *(f"undeclared artifact: {item}" for item in unexpected),
        ], "artifacts/", "artifact inventory matches the rendered-stage allowlist",
        "remove process files and recreate missing artifacts through the orchestrator", EXIT_CONTRACT,
    )
    if missing_non_pdf or unexpected:
        return checks, EXIT_CONTRACT
    add_check(
        checks, "artifact-json", _parse_artifacts(artifacts), "artifacts/**/*.json*",
        "all JSON and JSONL artifacts parse", "regenerate malformed contract artifacts", EXIT_CONTRACT,
    )
    if checks[-1].status == "fail":
        return checks, EXIT_CONTRACT
    if pdf_required and "exports/report.pdf" in missing:
        add_check(
            checks, "pdf-presence", ["required PDF is missing"], "artifacts/exports/report.pdf",
            "required PDF exists", "rerun render with a working PDF backend", EXIT_EXPORT,
        )
        return checks, EXIT_EXPORT
    return checks, 0


def _public_safety_checks(artifacts: Path) -> tuple[list[Check], int]:
    checks: list[Check] = []
    public_paths = (artifacts / "report.md", artifacts / "exports/report.html")
    texts = [(path.relative_to(artifacts).as_posix(), path.read_text(encoding="utf-8")) for path in public_paths]
    local_errors = [
        f"local path leak in {relative}: {pattern.pattern}"
        for relative, text in texts for pattern in LOCAL_PATH_PATTERNS if pattern.search(text)
    ]
    add_check(
        checks, "public-path-safety", local_errors, "report.md; exports/report.html",
        "public outputs contain no local path leak", "remove local filesystem paths", EXIT_SAFETY,
    )
    id_errors = [f"internal audit ID leaked into {relative}" for relative, text in texts if INTERNAL_ID.search(text)]
    add_check(
        checks, "public-id-safety", id_errors, "report.md; exports/report.html",
        "public outputs contain no internal source or Claim IDs", "replace audit IDs with generated citations", EXIT_SAFETY,
    )
    template_errors = [f"template marker remains in {relative}" for relative, text in texts if TEMPLATE_MARKER.search(text)]
    add_check(
        checks, "template-resolution", template_errors, "report.md; exports/report.html",
        "public outputs contain no unresolved template markers", "resolve template values and rerender", EXIT_EXPORT,
    )
    boilerplate_errors: list[str] = []
    for relative, text in texts:
        matches = sum(len(pattern.findall(text)) for pattern in AUDIT_BOILERPLATE_PATTERNS)
        if matches >= 2:
            boilerplate_errors.append(
                f"public report uses audit/source-register boilerplate as prose in {relative}"
            )
    add_check(
        checks, "public-prose-quality", boilerplate_errors, "report.md; exports/report.html",
        "public outputs do not turn source-register audit language into report prose",
        "rewrite the report around synthesized findings and keep audit wording in ledgers", EXIT_EXPORT,
    )
    failed = [check.exit_code for check in checks if check.status == "fail"]
    return checks, max(failed, default=0)


def _html_title(text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    return html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip() if match else ""


def _html_sections(text: str) -> list[str]:
    return [
        html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
        for value in re.findall(r"<h2[^>]*>(.*?)</h2>", text, re.IGNORECASE | re.DOTALL)
    ]


def _validate_contradictions(payload: dict[str, Any], claims: list[dict[str, Any]]) -> list[str]:
    if set(payload) != {"schema_version", "conflicts"} or payload.get("schema_version") != "2.0":
        return ["contradiction ledger has invalid top-level contract"]
    conflicts = payload.get("conflicts")
    if not isinstance(conflicts, list):
        return ["contradiction ledger conflicts must be an array"]
    errors: list[str] = []
    registered: set[str] = set()
    fields = {"conflict_id", "claim_id", "source_ids", "analysis", "resolution_status", "change_condition"}
    for index, conflict in enumerate(conflicts, start=1):
        if not isinstance(conflict, dict) or set(conflict) != fields:
            errors.append(f"contradiction {index} has invalid fields")
            continue
        registered.add(str(conflict.get("claim_id", "")))
        if not str(conflict.get("analysis", "")).strip():
            errors.append(f"contradiction {index} requires analysis")
        if not isinstance(conflict.get("source_ids"), list) or len(conflict["source_ids"]) < 2:
            errors.append(f"contradiction {index} requires opposing source IDs")
    for claim in claims:
        if claim.get("status") == "contested" and claim.get("claim_id") not in registered:
            errors.append(f"contested claim {claim.get('claim_id')} is missing from contradiction ledger")
    return errors


def _validate_uncertainties(payload: dict[str, Any]) -> list[str]:
    if set(payload) != {"schema_version", "uncertainties"} or payload.get("schema_version") != "2.0":
        return ["uncertainty ledger has invalid top-level contract"]
    records = payload.get("uncertainties")
    if not isinstance(records, list):
        return ["uncertainty ledger uncertainties must be an array"]
    fields = {
        "uncertainty_id", "claim_id", "question_ids", "tasklet_ids",
        "description", "impact", "next_evidence",
    }
    errors: list[str] = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict) or set(record) != fields:
            errors.append(f"uncertainty {index} has invalid fields")
        elif not all(str(record.get(field, "")).strip() for field in ("uncertainty_id", "description", "impact", "next_evidence")):
            errors.append(f"uncertainty {index} has empty required fields")
        else:
            for field, pattern in (("question_ids", r"Q\d{3}"), ("tasklet_ids", r"T\d{3}")):
                values = record.get(field)
                if not isinstance(values, list) or not all(re.fullmatch(pattern, str(item)) for item in values):
                    errors.append(f"uncertainty {index} has invalid {field}")
    return errors


def _is_full_external_dossier(brief: dict[str, Any]) -> bool:
    return (
        brief.get("depth_level") == "full_dossier"
        and brief.get("source_policy") != "closed_corpus"
        and brief.get("retrieval_mode") != "closed_corpus"
    )


def _is_maximal_full_dossier(brief: dict[str, Any]) -> bool:
    return brief.get("research_profile") == "maximal_full_dossier"


def _surface_bucket(value: object) -> str | None:
    text = str(value or "").casefold()
    if not text:
        return None
    if "counter" in text or "contradict" in text or "反证" in text:
        return "counterevidence"
    if "review" in text or "synthesis" in text or "secondary" in text or "综述" in text:
        return "secondary_synthesis"
    if "publisher" in text or "full_text" in text or "full text" in text or "doi" in text:
        return "publisher_or_full_text"
    if "registry" in text or "trial" in text or "official" in text or "clinicaltrials" in text or "ictrp" in text:
        return "official_or_registry"
    if "scholar" in text or "academic" in text or "openalex" in text or "pubmed" in text or "literature" in text:
        return "scholarly_index"
    return None


def _audit_surface_buckets(audit: list[dict[str, Any]]) -> set[str]:
    buckets: set[str] = set()
    for record in audit:
        if record.get("record_kind") != "search_run":
            continue
        for field in ("surface_class", "surface", "pass_kind"):
            bucket = _surface_bucket(record.get(field))
            if bucket:
                buckets.add(bucket)
    return buckets


def _is_user_material_source(source: dict[str, Any]) -> bool:
    source_type = str(source.get("source_type", "")).casefold()
    if source_type in USER_SOURCE_TYPES:
        return True
    text = " ".join(
        str(source.get(key, ""))
        for key in ("title", "author_or_org", "canonical_url", "file_ref", "reliability_notes")
    ).casefold()
    return any(marker in text for marker in ("user", "supplied", "transcript", "local-corpus", "用户", "语料"))


def _is_deep_external_source(source: dict[str, Any]) -> bool:
    if _is_user_material_source(source):
        return False
    if not str(source.get("canonical_url") or "").startswith(("http://", "https://")):
        return False
    if str(source.get("source_type", "")).casefold() in SHALLOW_SOURCE_TYPES:
        return False
    return True


def _validate_maximal_completeness(
    brief: dict[str, Any],
    sources: list[dict[str, Any]],
    manifests: list[dict[str, Any]],
    audit: list[dict[str, Any]],
    tasklets: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    outline: dict[str, Any],
    paragraph_map: list[dict[str, Any]],
    report: str,
    finding_coverage: dict[str, Any] | None = None,
    contradictions: dict[str, Any] | None = None,
    uncertainties: dict[str, Any] | None = None,
) -> list[str]:
    if not _is_maximal_full_dossier(brief):
        return []
    errors: list[str] = []
    usable_findings = [finding for finding in findings if finding.get("status") == "usable"]
    material_claims = [claim for claim in claims if claim.get("material")]
    boilerplate_claims = [
        str(claim.get("claim_id"))
        for claim in material_claims
        if any(pattern.search(str(claim.get("claim_text", ""))) for pattern in AUDIT_BOILERPLATE_PATTERNS)
    ]
    if boilerplate_claims:
        errors.append(
            "maximal_full_dossier material claims cannot be source-register boilerplate: "
            + ", ".join(boilerplate_claims[:10])
        )
    coverage = finding_coverage if isinstance(finding_coverage, dict) else {}
    waves = [record for record in audit if record.get("record_kind") == "search_wave"]
    declarations = {
        str(record.get("gap_id")): record
        for record in audit if record.get("record_kind") == "gap_assessment"
    }
    if not waves or not declarations:
        errors.append(
            "maximal_full_dossier requires retrieval saturation assessments; source count cannot close Max"
        )
    else:
        candidate_ids_by_source: dict[str, set[str]] = {}
        for manifest in manifests:
            candidate_ids_by_source.setdefault(str(manifest.get("source_id")), set()).add(
                str(manifest.get("candidate_id"))
            )
        actual_finding_ids = {str(item.get("finding_id")) for item in usable_findings}
        actual_conflict_ids = {
            str(item.get("conflict_id"))
            for item in (contradictions or {}).get("conflicts", []) if isinstance(item, dict)
        }
        actual_uncertainty_ids = {
            str(item.get("uncertainty_id"))
            for item in (uncertainties or {}).get("uncertainties", []) if isinstance(item, dict)
        }
        actual_claim_ids = {str(item.get("claim_id")) for item in claims}
        source_ids_by_candidate: dict[str, set[str]] = {}
        for manifest in manifests:
            source_ids_by_candidate.setdefault(str(manifest.get("candidate_id")), set()).add(
                str(manifest.get("source_id"))
            )
        coverage_waves = {
            str(item.get("wave_id")): item
            for item in coverage.get("search_waves", []) if isinstance(item, dict)
        }
        computed: dict[str, list[tuple[str, int]]] = {}
        for wave in waves:
            new_candidates = {str(item) for item in wave.get("new_candidate_ids", [])}
            submitted_findings = {str(item) for item in wave.get("new_finding_ids", [])}
            submitted_conflicts = {str(item) for item in wave.get("new_contradiction_ids", [])}
            submitted_uncertainties = {str(item) for item in wave.get("new_uncertainty_ids", [])}
            submitted_claims = {str(item) for item in wave.get("changed_claim_ids", [])}
            unknown = sorted(
                (submitted_findings - actual_finding_ids)
                | (submitted_conflicts - actual_conflict_ids)
                | (submitted_uncertainties - actual_uncertainty_ids)
                | (submitted_claims - actual_claim_ids)
            )
            if unknown:
                errors.append(
                    f"{wave.get('wave_id')} material delta references unknown final ledger IDs: "
                    + ", ".join(unknown)
                )
            new_findings = ({
                str(finding.get("finding_id"))
                for finding in usable_findings
                if any(
                    candidate_ids_by_source.get(str(source_id), set()) & new_candidates
                    for source_id in finding.get("source_ids", [])
                )
            } | submitted_findings) & actual_finding_ids
            finding_claim_ids = {
                str(claim_id)
                for finding in usable_findings
                if str(finding.get("finding_id")) in new_findings
                for claim_id in finding.get("claim_ids", [])
            }
            delta = (
                len(new_findings)
                + len(submitted_conflicts & actual_conflict_ids)
                + len(submitted_uncertainties & actual_uncertainty_ids)
                + len((submitted_claims & actual_claim_ids) - finding_claim_ids)
            )
            derived_sources = {
                source_id for candidate_id in new_candidates
                for source_id in source_ids_by_candidate.get(candidate_id, set())
            }
            if set(str(item) for item in wave.get("new_source_ids", [])) != derived_sources:
                errors.append(f"{wave.get('wave_id')} new_source_ids do not recompute")
            if wave.get("material_delta") is not None and wave.get("material_delta") != delta:
                errors.append(f"{wave.get('wave_id')} submitted material_delta does not recompute")
            coverage_wave = coverage_waves.get(str(wave.get("wave_id")), {})
            if coverage_wave.get("material_delta") != delta:
                errors.append(f"{wave.get('wave_id')} finding coverage material_delta does not recompute")
            computed.setdefault(str(wave.get("gap_id")), []).append(
                (str(wave.get("wave_id")), delta)
            )
        submitted = {
            str(item.get("gap_id")): item
            for item in coverage.get("saturation_assessments", [])
            if isinstance(item, dict)
        }
        for gap_id, rows in sorted(computed.items()):
            ordered = sorted(rows)
            declaration = declarations.get(gap_id)
            assessment = submitted.get(gap_id)
            if declaration is None:
                errors.append(f"{gap_id} lacks a declared terminal gap assessment")
                continue
            terminal_state = str(declaration.get("terminal_state", ""))
            supporting_ids = [str(item) for item in declaration.get("supporting_wave_ids", [])]
            supporting_rows = [item for item in ordered if item[0] in supporting_ids]
            if terminal_state == "saturated" and (
                len(supporting_rows) < 2
                or not all(delta == 0 for _wave, delta in supporting_rows[-2:])
            ):
                errors.append(f"{gap_id} has not reached material novelty saturation")
            if not assessment or assessment.get("terminal_state") != terminal_state:
                errors.append(f"{gap_id} saturation assessment is missing or inconsistent")
            elif assessment.get("supporting_wave_ids") != supporting_ids:
                errors.append(f"{gap_id} saturation wave binding does not recompute")
            if terminal_state == "bounded_corpus_exhausted":
                total_windows = declaration.get("total_result_windows")
                retrieved_windows = declaration.get("result_windows_retrieved")
                coverage_total_windows = (
                    assessment.get("total_result_windows")
                    if isinstance(assessment, dict) else None
                )
                coverage_retrieved_windows = (
                    assessment.get("result_windows_retrieved")
                    if isinstance(assessment, dict) else None
                )
                if (
                    declaration.get("enumeration_complete") is not True
                    or not isinstance(total_windows, int)
                    or isinstance(total_windows, bool)
                    or total_windows < 1
                    or not isinstance(retrieved_windows, int)
                    or isinstance(retrieved_windows, bool)
                    or retrieved_windows != total_windows
                    or coverage_total_windows != total_windows
                    or coverage_retrieved_windows != retrieved_windows
                    or not isinstance(declaration.get("access_limitations"), list)
                ):
                    errors.append(
                        f"{gap_id} bounded corpus exhaustion requires complete result-window enumeration"
                    )
        extra_declarations = sorted(set(declarations) - set(computed))
        if extra_declarations:
            errors.append(
                "terminal gap assessments lack search waves: " + ", ".join(extra_declarations)
            )
    if brief.get("high_stakes"):
        surfaces = [
            str(record.get("surface", "")).casefold()
            for record in audit
            if record.get("record_kind") == "search_run"
        ]
        surface_classes = [
            str(record.get("surface_class", "")).casefold()
            for record in audit
            if record.get("record_kind") == "search_run"
        ]
        buckets = _audit_surface_buckets(audit)
        has_literature = any("pubmed" in item for item in surfaces) or "literature_database" in surface_classes
        has_registry = "official_or_registry" in buckets
        aliases = [
            alias
            for record in audit
            if record.get("record_kind") == "search_run"
            for alias in record.get("aliases", [])
        ]
        if not has_literature or not has_registry or len(set(str(alias).casefold() for alias in aliases)) < 3:
            errors.append("maximal_full_dossier high-stakes retrieval requires PubMed/literature, trial registry, and at least three aliases")
    return list(dict.fromkeys(errors))


def _validate_review_loop_artifact(
    artifacts: Path,
    brief: dict[str, Any],
) -> list[str]:
    if not _is_maximal_full_dossier(brief):
        return []
    path = artifacts / "research/review-loop.json"
    if not path.is_file() or path.is_symlink():
        return ["maximal_full_dossier requires research/review-loop.json"]
    loop = load_json(path)
    fields = {"schema_version", "policy", "rounds", "final_integrity", "summary"}
    if set(loop) != fields:
        return ["review-loop.json has invalid fields"]
    errors: list[str] = []
    if loop.get("schema_version") != "2.0":
        errors.append("review-loop.json schema_version must be 2.0")
    if loop.get("policy") != "concern_driven_until_clear":
        errors.append("review-loop.json policy must be concern_driven_until_clear")
    rounds = loop.get("rounds")
    final_integrity = loop.get("final_integrity")
    summary = loop.get("summary")
    if not isinstance(rounds, list) or not rounds:
        errors.append("maximal_full_dossier requires at least one substantive panel review")
        rounds = []
    if not isinstance(final_integrity, dict):
        errors.append("review-loop.json final_integrity must be an object")
        final_integrity = {}
    if not isinstance(summary, dict):
        errors.append("review-loop.json summary must be an object")
        summary = {}
    if summary.get("round_count") != len(rounds):
        errors.append("review-loop.json summary round_count must match rounds")
    if summary.get("final_editor_decision") != "accept":
        errors.append("maximal_full_dossier review loop final editor decision must be accept")
    if summary.get("unresolved_concerns") != 0:
        errors.append("maximal_full_dossier review loop must have zero unresolved concerns")
    report_hash = sha256_file(artifacts / "report.md")
    revision_hash = sha256_file(artifacts / "review-candidate/revision-map.json")
    subject_paths = {
        "report": artifacts / "report.md",
        "paragraph_map": artifacts / "research/reviewed-paragraph-map.jsonl",
        "revision_map": artifacts / "review-candidate/revision-map.json",
        "claims": artifacts / "research/claim-evidence-ledger.jsonl",
        "sources": artifacts / "research/source-register.jsonl",
        "findings": artifacts / "research/storm-findings-pool.jsonl",
        "contradictions": artifacts / "research/contradiction-ledger.json",
        "uncertainties": artifacts / "research/uncertainty-ledger.json",
        "p2": artifacts / "research/storm-lens-conflicts.json",
        "p3": artifacts / "research/storm-lens-outline.json",
        "p4": artifacts / "research/storm-lens-red-team.json",
        "retrieval_audit": artifacts / "research/retrieval-audit.jsonl",
        "finding_coverage": artifacts / "research/finding-coverage.json",
    }
    missing_subject = [key for key, value in subject_paths.items() if not value.is_file() or value.is_symlink()]
    if missing_subject:
        errors.append("review subject is missing governed artifacts: " + ", ".join(sorted(missing_subject)))
        subject_hash = ""
        subject_artifacts: dict[str, str] = {}
    else:
        subject_artifacts = {
            key: sha256_file(value) for key, value in sorted(subject_paths.items())
        }
        subject_hash = canonical_json_sha256(subject_artifacts)
    if summary.get("final_candidate_sha256") != report_hash:
        errors.append("review-loop.json final candidate hash mismatch")
    if summary.get("final_review_subject_sha256") != subject_hash:
        errors.append("review-loop.json final review subject hash mismatch")
    required_roles = MAX_REVIEW_ROLES
    opened: set[str] = set()
    terminal: set[str] = set()
    terminal_gap_targets: dict[str, str] = {}
    concern_contracts: dict[str, dict[str, Any]] = {}
    linked_p4_actions: set[str] = set()
    revision_map = load_json(artifacts / "review-candidate/revision-map.json")
    review_provenance = load_json(artifacts / "research/reviewer-provenance.json")
    author_context_id = str(review_provenance.get("author_context_id", ""))
    package_hash = compute_skill_package_hash(ROOT)
    uncertainty_records = {
        str(item.get("uncertainty_id")): item
        for item in load_json(artifacts / "research/uncertainty-ledger.json").get("uncertainties", [])
        if isinstance(item, dict)
    }
    reviewed_map = load_jsonl(artifacts / "research/reviewed-paragraph-map.jsonl")
    report_binding_ids = {
        *(str(item.get("paragraph_locator")) for item in reviewed_map if isinstance(item, dict)),
        *(
            f"claim:{claim.get('claim_id')}"
            for claim in load_jsonl(artifacts / "research/claim-evidence-ledger.jsonl")
            if isinstance(claim, dict)
        ),
    }
    revision_actions = {
        str(item.get("action_id"))
        for item in revision_map.get("revisions", []) if isinstance(item, dict)
    }
    previous_storm_analysis_sha256: str | None = None
    previous_generation: int | None = None
    previous_subject_artifacts: dict[str, str] | None = None
    previous_open_concerns: list[dict[str, Any]] = []
    generation_match = re.fullmatch(r"g(\d{4})", artifacts.parent.name)
    current_generation = int(generation_match.group(1)) if generation_match else 0
    run_root = artifacts.parents[3]
    round_bindings: dict[int, dict[str, str]] = {}
    for generation in range(1, current_generation + 1):
        state_root = run_root / f"state/generations/g{generation:04d}"
        generation_artifacts = run_root / f"work/generations/g{generation:04d}/artifacts"
        draft_receipt_path = state_root / "receipts/40-draft.json"
        request_path = generation_artifacts / "research/review-request.json"
        if not draft_receipt_path.is_file() or not request_path.is_file():
            continue
        binding = {
            "draft_receipt_sha256": str(load_json(draft_receipt_path).get("receipt_sha256", "")),
            "review_request_sha256": str(load_json(request_path).get("request_sha256", "")),
        }
        block_path = state_root / "review-blocked.json"
        if block_path.is_file() and not block_path.is_symlink():
            block = load_json(block_path)
            binding["blocked_round_sha256"] = str(block.get("blocked_round_sha256", ""))
            if block.get("review_request_sha256") != binding["review_request_sha256"]:
                errors.append(f"review loop generation {generation} blocker request hash mismatch")
            for field in (
                "review_provenance_sha256", "review_output_sha256", "review_transcript_sha256",
            ):
                if not re.fullmatch(r"[0-9a-f]{64}", str(block.get(field, ""))):
                    errors.append(f"review loop generation {generation} blocker lacks {field}")
        round_bindings[generation] = binding
    for index, round_record in enumerate(rounds, start=1):
        if not isinstance(round_record, dict):
            errors.append(f"review loop round {index} must be an object")
            continue
        expected_round_fields = {
            "round_id", "candidate_sha256", "review_subject_sha256", "panel_reviews",
            "editor_decision", "editor_review", "required_concerns", "revision_map_sha256",
            "re_review_result", "unresolved_concerns", "generation",
            "draft_receipt_sha256", "review_request_sha256",
            "review_subject_artifacts", "round_sha256",
        }
        if set(round_record) != expected_round_fields:
            errors.append(f"review loop round {index} has invalid fields")
            continue
        round_generation = round_record.get("generation")
        if not isinstance(round_generation, int) or round_generation < 1:
            errors.append(f"review loop round {index} generation is invalid")
        elif previous_generation is not None and round_generation <= previous_generation:
            errors.append("review rounds must use distinct increasing generations")
        previous_generation = round_generation if isinstance(round_generation, int) else previous_generation
        if canonical_json_sha256({
            key: value for key, value in round_record.items() if key != "round_sha256"
        }) != round_record.get("round_sha256"):
            errors.append(f"review loop round {index} round_sha256 mismatch")
        round_subject_artifacts = round_record.get("review_subject_artifacts")
        expected_subject_keys = set(subject_paths)
        if (
            not isinstance(round_subject_artifacts, dict)
            or set(round_subject_artifacts) != expected_subject_keys
            or not all(re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in round_subject_artifacts.values())
        ):
            errors.append(f"review loop round {index} review_subject_artifacts are invalid")
            round_subject_artifacts = {}
        elif canonical_json_sha256(round_subject_artifacts) != round_record.get("review_subject_sha256"):
            errors.append(f"review loop round {index} subject manifest hash mismatch")
        binding = round_bindings.get(round_generation, {}) if isinstance(round_generation, int) else {}
        if (
            round_record.get("draft_receipt_sha256") != binding.get("draft_receipt_sha256")
            or round_record.get("review_request_sha256") != binding.get("review_request_sha256")
        ):
            errors.append(f"review loop round {index} is not bound to its generation receipts")
        if index < len(rounds) and round_record.get("round_sha256") != binding.get("blocked_round_sha256"):
            errors.append(f"review loop round {index} lacks an immutable blocked review receipt")
        if previous_subject_artifacts is not None and previous_open_concerns:
            changed = {
                key for key in expected_subject_keys
                if previous_subject_artifacts.get(key) != round_subject_artifacts.get(key)
            }
            for concern in previous_open_concerns:
                required_components = {
                    "retrieval": {"retrieval_audit", "sources", "findings", "finding_coverage"},
                    "evidence": {"claims", "contradictions", "uncertainties", "finding_coverage"},
                    "draft": {"report", "paragraph_map", "revision_map", "p3", "p4"},
                }.get(str(concern.get("required_stage", "")), set())
                if required_components and not changed.intersection(required_components):
                    errors.append(
                        f"review concern {concern.get('concern_id')} did not change its required upstream artifacts"
                    )
        previous_subject_artifacts = dict(round_subject_artifacts)
        round_subject = str(round_record.get("review_subject_sha256", ""))
        panel = round_record.get("panel_reviews")
        if not isinstance(panel, list):
            errors.append(f"review loop round {index} panel_reviews must be an array")
            panel = []
        roles = {str(item.get("reviewer_role")) for item in panel if isinstance(item, dict)}
        missing_roles = sorted(required_roles - roles)
        if missing_roles:
            errors.append(f"review loop round {index} missing reviewer roles: " + ", ".join(missing_roles))
        panel_contexts: list[str] = []
        panel_executions: list[str] = []
        for item in panel:
            if not isinstance(item, dict):
                errors.append(f"review loop round {index} panel review must be an object")
                continue
            expected_panel_fields = {
                "reviewer_role", "decision", "reason", "rubric_id", "rubric_sha256",
                "reviewed_subject_sha256", "reviewer_context_id", "execution_id",
                "concerns", "storm_analysis",
            }
            role = str(item.get("reviewer_role"))
            if set(item) != expected_panel_fields:
                errors.append(f"review loop round {index} panel review has invalid fields")
                continue
            reason = str(item.get("reason", "")).strip()
            if len(reason) < 80:
                errors.append(f"review loop {role} reason is generic or too short")
            expected_rubric_id, expected_rubric_sha256 = max_review_rubric_binding(
                role, package_hash
            )
            if not str(item.get("rubric_id", "")).strip() or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("rubric_sha256", ""))):
                errors.append(f"review loop {role} rubric binding is invalid")
            elif (
                item.get("rubric_id") != expected_rubric_id
                or item.get("rubric_sha256") != expected_rubric_sha256
            ):
                errors.append(
                    f"review loop {role} rubric hash does not match the committed role rubric"
                )
            if item.get("reviewed_subject_sha256") != round_subject:
                errors.append(f"review loop {role} reviewed the wrong subject")
            context_id = str(item.get("reviewer_context_id", ""))
            execution_id = str(item.get("execution_id", ""))
            if not context_id or context_id == author_context_id:
                errors.append(f"review loop {role} context is missing or not isolated from author")
            if not execution_id:
                errors.append(f"review loop {role} execution_id is required")
            panel_contexts.append(context_id)
            panel_executions.append(execution_id)
            if role == "storm_synthesis_reviewer":
                storm_analysis = item.get("storm_analysis")
                errors.extend(validate_storm_review_analysis(storm_analysis))
                if isinstance(storm_analysis, dict):
                    storm_digest = canonical_json_sha256(storm_analysis)
                    if previous_storm_analysis_sha256 == storm_digest:
                        errors.append(
                            "storm_synthesis_reviewer copied the prior round audit instead of re-reviewing the changed subject"
                        )
                    previous_storm_analysis_sha256 = storm_digest
        if len(panel_contexts) != len(set(panel_contexts)):
            errors.append("panel reviewer contexts must be distinct")
        if len(panel_executions) != len(set(panel_executions)):
            errors.append("panel reviewer executions must be distinct")
        editor_review = round_record.get("editor_review")
        editor_fields = {"context_id", "execution_id", "decision", "reason", "concern_ids"}
        if not isinstance(editor_review, dict) or set(editor_review) != editor_fields:
            errors.append(f"review loop round {index} editor_review has invalid fields")
            editor_review = {}
        else:
            if round_generation != current_generation:
                errors.append("review loop final round must bind the current generation")
            if round_subject_artifacts != subject_artifacts:
                errors.append("review loop final round subject artifacts mismatch")
            editor_context = str(editor_review.get("context_id", ""))
            if not editor_context or editor_context == author_context_id or editor_context in set(panel_contexts):
                errors.append(f"review loop round {index} editor context is not isolated")
            if not str(editor_review.get("execution_id", "")).strip():
                errors.append(f"review loop round {index} editor execution_id is required")
            if len(str(editor_review.get("reason", "")).strip()) < 80:
                errors.append(f"review loop round {index} editor reason is generic or too short")
        concerns = round_record.get("required_concerns")
        if not isinstance(concerns, list):
            errors.append(f"review loop round {index} required_concerns must be an array")
            concerns = []
        concern_ids: set[str] = set()
        open_severities: set[str] = set()
        for concern in concerns:
            if not isinstance(concern, dict):
                errors.append(f"review loop round {index} concern must be an object")
                continue
            expected_concern_fields = {
                "concern_id", "reviewer_role", "severity", "target_kind", "target_id",
                "target_sha256", "evidence_or_locator", "problem", "required_action",
                "acceptance_test", "origin_action_ids", "issue_type", "required_stage",
                "uncertainty_id", "report_binding", "disposition", "reason",
            }
            if set(concern) != expected_concern_fields:
                errors.append(f"review loop round {index} concern has invalid fields")
                continue
            concern_id = str(concern.get("concern_id", ""))
            concern_ids.add(concern_id)
            origin_action_ids = concern.get("origin_action_ids")
            if not isinstance(origin_action_ids, list) or not all(
                re.fullmatch(r"RA\d{3}", str(item)) for item in origin_action_ids
            ) or len(origin_action_ids) != len(set(str(item) for item in origin_action_ids)):
                errors.append(f"review loop concern {concern_id} has invalid origin_action_ids")
            else:
                linked_p4_actions.update(str(item) for item in origin_action_ids)
            current = concern_contracts.setdefault(concern_id, dict(concern))
            for field in ("reviewer_role", "severity", "target_kind", "target_id", "target_sha256", "required_action", "acceptance_test"):
                if current.get(field) != concern.get(field):
                    errors.append(f"review loop concern {concern_id} changed its contract across rounds")
            expected_stage = REVIEW_ISSUE_STAGE.get(str(concern.get("issue_type", "")))
            if expected_stage is None or concern.get("required_stage") != expected_stage:
                errors.append(
                    f"review loop concern {concern_id} requires issue_type and required_stage with deterministic routing"
                )
            disposition = concern.get("disposition")
            if disposition == "open":
                opened.add(concern_id)
                open_severities.add(str(concern.get("severity")))
            elif disposition in {"addressed", "waived", "preserved_as_uncertainty"}:
                terminal.add(concern_id)
                current["terminal_disposition"] = disposition
                if (
                    concern.get("reviewer_role") == "domain_reviewer"
                    and concern.get("target_kind") in {"gap", "gap_assessment"}
                    and str(concern.get("target_id", "")).strip()
                ):
                    terminal_gap_targets[
                        f"{concern.get('target_kind')}:{concern.get('target_id')}"
                    ] = concern_id
                if not str(concern.get("reason", "")).strip():
                    errors.append(f"review loop concern {concern_id} terminal disposition lacks reason")
                if disposition == "waived" and brief.get("high_stakes") and concern.get("severity") in {"blocker", "major"}:
                    errors.append(f"high-stakes concern {concern_id} cannot be waived")
                if disposition == "preserved_as_uncertainty":
                    uncertainty_id = str(concern.get("uncertainty_id") or "")
                    report_binding = str(concern.get("report_binding") or "")
                    uncertainty = uncertainty_records.get(uncertainty_id)
                    if (
                        not re.fullmatch(r"U\d{3}", uncertainty_id)
                        or uncertainty is None
                        or not report_binding
                        or report_binding not in report_binding_ids
                        or (
                            concern.get("target_kind") == "claim"
                            and uncertainty.get("claim_id") != concern.get("target_id")
                        )
                    ):
                        errors.append(
                            f"review loop concern {concern_id} preserved uncertainty requires uncertainty_id and report binding"
                        )
                elif concern.get("uncertainty_id") is not None or concern.get("report_binding") is not None:
                    errors.append(
                        f"review loop concern {concern_id} uncertainty fields are only valid for preserved_as_uncertainty"
                    )
            else:
                errors.append(f"review loop concern {concern_id} disposition is invalid")
        panel_concern_ids = {
            str(concern.get("concern_id"))
            for item in panel if isinstance(item, dict)
            for concern in item.get("concerns", []) if isinstance(concern, dict)
        }
        if panel_concern_ids != concern_ids:
            errors.append(f"review loop round {index} editor concern matrix does not match panel concerns")
        expected_decision = (
            "reject" if "blocker" in open_severities else
            "major_revision" if "major" in open_severities else
            "minor_revision" if "minor" in open_severities else "accept"
        )
        if round_record.get("editor_decision") != expected_decision:
            errors.append(f"review loop round {index} editor decision conflicts with open concerns")
        if editor_review:
            if editor_review.get("decision") != round_record.get("editor_decision"):
                errors.append(f"review loop round {index} editor review decision mismatch")
            if set(str(item) for item in editor_review.get("concern_ids", [])) != concern_ids:
                errors.append(f"review loop round {index} editor review omitted panel concerns")
        if index < len(rounds):
            if round_record.get("revision_map_sha256") != revision_hash:
                errors.append(f"review loop round {index} revision_map_sha256 mismatch")
            if not concerns:
                errors.append(f"review loop round {index} must record revision concerns")
            if round_record.get("re_review_result") not in {"pending", "requires_re_review"}:
                errors.append(f"review loop round {index} must require re-review")
        else:
            if round_record.get("candidate_sha256") != report_hash:
                errors.append("review loop final round candidate hash mismatch")
            if round_subject != subject_hash:
                errors.append("review loop final round subject hash mismatch")
            if round_record.get("editor_decision") != "accept":
                errors.append("review loop final round editor_decision must be accept")
            expected_re_review = "pass" if len(rounds) > 1 else "not_required"
            if round_record.get("re_review_result") != expected_re_review:
                errors.append(f"review loop final round re_review_result must be {expected_re_review}")
            if round_record.get("unresolved_concerns") != 0:
                errors.append("review loop final round must have zero unresolved concerns")
        previous_open_concerns = [
            item for item in concerns
            if isinstance(item, dict) and item.get("disposition") == "open"
        ]
    missing_revisions = sorted(opened - revision_actions)
    if missing_revisions:
        errors.append("review concerns are missing from revision map: " + ", ".join(missing_revisions))
    unclosed = sorted(opened - terminal)
    if unclosed:
        errors.append("review concerns remain unresolved after re-review: " + ", ".join(unclosed))
    p4 = load_json(artifacts / "research/storm-lens-red-team.json")
    p4_action_ids = {
        str(item.get("action_id"))
        for item in p4.get("output", {}).get("repair_actions", []) if isinstance(item, dict)
    }
    missing_p4_links = sorted(p4_action_ids - linked_p4_actions)
    if missing_p4_links:
        errors.append("P4 repair actions are absent from the review concern matrix: " + ", ".join(missing_p4_links))
    required_gap_review_ids: set[str] = set()
    required_gap_review_targets: list[set[str]] = []
    for item in load_jsonl(artifacts / "research/retrieval-audit.jsonl"):
        if item.get("record_kind") != "gap_assessment" or item.get("terminal_state") not in {
            "saturated", "bounded_corpus_exhausted",
            "access_limited_uncertainty", "out_of_scope",
        }:
            continue
        review_concern_id = item.get("review_concern_id")
        if review_concern_id:
            required_gap_review_ids.add(str(review_concern_id))
        else:
            required_gap_review_targets.append({
                f"gap_assessment:{item.get('assessment_id')}",
                f"gap:{item.get('gap_id')}",
            })
    missing_gap_reviews = sorted(required_gap_review_ids - terminal)
    if missing_gap_reviews:
        errors.append("gap terminal assessments lack closed independent review: " + ", ".join(missing_gap_reviews))
    for target_options in required_gap_review_targets:
        if not set(target_options) & set(terminal_gap_targets):
            errors.append(
                "terminal gap disposition requires independent review closure: "
                + " or ".join(sorted(target_options))
            )
    wrong_gap_reviewers = sorted(
        concern_id for concern_id in required_gap_review_ids & terminal
        if concern_contracts.get(concern_id, {}).get("reviewer_role") != "domain_reviewer"
    )
    if wrong_gap_reviewers:
        errors.append(
            "gap terminal assessments require domain reviewer acceptance: "
            + ", ".join(wrong_gap_reviewers)
        )
    revision_records = {
        str(item.get("action_id")): item
        for item in revision_map.get("revisions", []) if isinstance(item, dict)
    }
    expected_status = {
        "addressed": "applied",
        "waived": "waived",
        "preserved_as_uncertainty": "preserved_as_uncertainty",
    }
    for concern_id in sorted(opened):
        concern = concern_contracts.get(concern_id, {})
        revision = revision_records.get(concern_id)
        if not isinstance(revision, dict):
            continue
        if revision.get("before_sha256") != concern.get("target_sha256"):
            errors.append(f"review concern {concern_id} revision target hash mismatch")
        if revision.get("action") != concern.get("required_action"):
            errors.append(f"review concern {concern_id} revision action mismatch")
        terminal_status = expected_status.get(str(concern.get("terminal_disposition", "")))
        if terminal_status and revision.get("status") != terminal_status:
            errors.append(f"review concern {concern_id} revision status mismatch")
        if revision.get("status") == "applied" and revision.get("before_sha256") == revision.get("after_sha256"):
            errors.append(f"review concern {concern_id} applied revision did not change its target")
    expected_integrity_fields = {
        "review_subject_sha256", "status", "checked_claim_ids", "regression_issues",
    }
    if set(final_integrity) != expected_integrity_fields:
        errors.append("review-loop.json final_integrity has invalid fields")
    else:
        material_claim_ids = {
            str(claim.get("claim_id"))
            for claim in load_jsonl(artifacts / "research/claim-evidence-ledger.jsonl")
            if claim.get("material")
        }
        if final_integrity.get("review_subject_sha256") != subject_hash:
            errors.append("final integrity reviewed the wrong subject")
        if final_integrity.get("status") != "pass" or final_integrity.get("regression_issues") != []:
            errors.append("final integrity must pass with zero regression issues")
        if set(str(item) for item in final_integrity.get("checked_claim_ids", [])) != material_claim_ids:
            errors.append("final integrity must check every material Claim")
    return list(dict.fromkeys(errors))


def _validate_tasklets(
    tasklets: list[dict[str, Any]], plan: dict[str, Any], source_plan: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    question_ids = {
        str(item.get("question_id"))
        for item in plan.get("questions", [])
        if isinstance(item, dict)
    }
    source_question_ids = {
        str(item.get("query_id"))
        for item in source_plan.get("questions", [])
        if isinstance(item, dict)
    }
    seen_tasklets: set[str] = set()
    seen_questions: set[str] = set()
    for index, tasklet in enumerate(tasklets, start=1):
        errors.extend(f"tasklet {index}: {item}" for item in validate_tasklet_record(tasklet))
        tasklet_id = str(tasklet.get("tasklet_id", ""))
        if tasklet_id in seen_tasklets:
            errors.append(f"duplicate tasklet_id {tasklet_id}")
        seen_tasklets.add(tasklet_id)
        question_id = str(tasklet.get("question_id", ""))
        seen_questions.add(question_id)
        if question_id not in question_ids:
            errors.append(f"tasklet {tasklet_id} references unknown research question {question_id}")
        if question_id not in source_question_ids:
            errors.append(f"tasklet {tasklet_id} lacks source-plan coverage")
    missing = sorted(question_ids - seen_questions)
    if missing:
        errors.append("storm tasklets must cover every research question: " + ", ".join(missing))
    return errors


def _profile_prompt_evidence_errors(brief: dict[str, Any], brief_path: Path) -> list[str]:
    selection = brief.get("profile_selection")
    if not isinstance(selection, dict):
        return []
    errors: list[str] = []
    if brief.get("assurance_target") == "captured_host_execution":
        evidence_ref = selection.get("evidence_ref")
        if evidence_ref != "inputs/profile-selection-evidence.txt":
            errors.append("profile_selection.evidence_ref must be inputs/profile-selection-evidence.txt")
        evidence_path = brief_path.parent / "profile-selection-evidence.txt"
        if not evidence_path.is_file() or evidence_path.is_symlink():
            errors.append("profile_selection evidence artifact is missing")
        elif sha256_file(evidence_path) != selection.get("evidence_sha256"):
            errors.append("profile_selection evidence artifact hash mismatch")
    if selection.get("mode") == "defaulted_after_prompt":
        prompt_ref = selection.get("prompt_ref")
        if prompt_ref != "inputs/profile-selection-prompt.txt":
            errors.append("profile_selection.prompt_ref must be inputs/profile-selection-prompt.txt")
        prompt_path = brief_path.parent / "profile-selection-prompt.txt"
        if not prompt_path.is_file() or prompt_path.is_symlink():
            errors.append("defaulted_after_prompt prompt artifact is missing")
        elif sha256_file(prompt_path) != selection.get("prompt_sha256"):
            errors.append("defaulted_after_prompt prompt artifact hash mismatch")
    return errors


def _validate_findings(
    findings: list[dict[str, Any]],
    tasklets: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    manifests: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    *,
    require_tasklet_coverage: bool,
) -> list[str]:
    errors: list[str] = []
    tasklet_by_id = {str(item.get("tasklet_id")): item for item in tasklets}
    question_by_tasklet = {
        str(item.get("tasklet_id")): str(item.get("question_id"))
        for item in tasklets
    }
    source_ids = {str(item.get("source_id")) for item in sources}
    manifests_by_source: dict[str, list[dict[str, Any]]] = {}
    for manifest in manifests:
        manifests_by_source.setdefault(str(manifest.get("source_id")), []).append(manifest)
    usable_tasklets: set[str] = set()
    usable_by_claim: dict[str, list[dict[str, Any]]] = {}
    seen_findings: set[str] = set()
    for index, finding in enumerate(findings, start=1):
        errors.extend(f"finding {index}: {item}" for item in validate_finding_record(finding))
        finding_id = str(finding.get("finding_id", ""))
        if finding_id in seen_findings:
            errors.append(f"duplicate finding_id {finding_id}")
        seen_findings.add(finding_id)
        tasklet_id = str(finding.get("tasklet_id", ""))
        if tasklet_id not in tasklet_by_id:
            errors.append(f"finding {finding_id} references unknown tasklet {tasklet_id}")
        elif str(finding.get("question_id")) != question_by_tasklet[tasklet_id]:
            errors.append(f"finding {finding_id} question_id does not match its tasklet")
        for source_id in finding.get("source_ids", []):
            if str(source_id) not in source_ids:
                errors.append(f"finding {finding_id} references unknown source {source_id}")
        for locator in finding.get("evidence_locators", []):
            if not isinstance(locator, dict):
                continue
            source_id = str(locator.get("source_id", ""))
            if source_id not in source_ids:
                continue
            if not any(
                str(manifest.get("snapshot_sha256")) == str(locator.get("snapshot_sha256"))
                for manifest in manifests_by_source.get(source_id, [])
            ):
                errors.append(f"finding {finding_id} locator snapshot does not bind source {source_id}")
        if finding.get("status") == "usable":
            usable_tasklets.add(tasklet_id)
            for claim_id in finding.get("claim_ids", []):
                usable_by_claim.setdefault(str(claim_id), []).append(finding)
    if require_tasklet_coverage:
        missing = sorted(set(tasklet_by_id) - usable_tasklets)
        if missing:
            errors.append("findings pool must cover every STORM tasklet: " + ", ".join(missing))
    for claim in claims:
        if not claim.get("material"):
            continue
        claim_id = str(claim.get("claim_id", ""))
        linked = usable_by_claim.get(claim_id, [])
        if not linked:
            errors.append(f"material claim {claim_id} is not linked to a usable STORM finding")
            continue
        claim_sources = {str(source_id) for source_id in claim.get("supporting_source_ids", [])}
        if not any(claim_sources & {str(source_id) for source_id in finding.get("source_ids", [])} for finding in linked):
            errors.append(f"material claim {claim_id} finding link does not share supporting sources")
    return errors


def _validate_conflict_reviews(
    contradictions: dict[str, Any], reviews: list[dict[str, Any]]
) -> list[str]:
    if not reviews:
        return ["contradiction ledger lacks independent conflict review"]
    errors: list[str] = []
    ledger_reviewed = False
    seen_reviews: set[str] = set()
    for index, review in enumerate(reviews, start=1):
        errors.extend(f"conflict review {index}: {item}" for item in validate_conflict_review_record(review))
        review_id = str(review.get("review_id", ""))
        if review_id in seen_reviews:
            errors.append(f"duplicate conflict review ID {review_id}")
        seen_reviews.add(review_id)
        if review.get("target_kind") == "contradiction_ledger":
            ledger_reviewed = True
            if review.get("target_id") != "contradiction-ledger":
                errors.append("contradiction ledger review target_id must be contradiction-ledger")
            if review.get("target_sha256") != canonical_json_sha256(contradictions):
                errors.append("contradiction ledger review hash mismatch")
        if review.get("verdict") != "supported":
            errors.append(f"conflict review did not pass: {review_id}")
    if not ledger_reviewed:
        errors.append("contradiction ledger requires a ledger-level review")
    return errors


def _validate_lens_artifact(
    payload: dict[str, Any], *, prompt_id: str
) -> list[str]:
    fields = {
        "schema_version", "prompt_id", "prompt_pack_sha256", "phase",
        "input_artifacts", "output", "created_at",
    }
    errors: list[str] = []
    if set(payload) != fields:
        return [f"storm lens {prompt_id} has invalid top-level fields"]
    if payload.get("schema_version") != "2.0":
        errors.append(f"storm lens {prompt_id} schema_version must be 2.0")
    if payload.get("prompt_id") != prompt_id:
        errors.append(f"storm lens {prompt_id} prompt_id mismatch")
    if payload.get("phase") != STORM_LENS_ARTIFACTS[prompt_id][1]:
        errors.append(f"storm lens {prompt_id} phase mismatch")
    if payload.get("prompt_pack_sha256") != sha256_file(STORM_LENS_PROMPT_PACK):
        errors.append(f"storm lens {prompt_id} prompt pack hash mismatch")
    if not isinstance(payload.get("input_artifacts"), dict):
        errors.append(f"storm lens {prompt_id} input_artifacts must be an object")
    if not isinstance(payload.get("output"), dict):
        errors.append(f"storm lens {prompt_id} output must be an object")
    return errors


def _receipt_input_keys(artifacts: Path, receipt_name: str) -> set[str]:
    run_root = artifacts.parents[3]
    generation_name = artifacts.parent.name
    receipt = load_json(run_root / f"state/generations/{generation_name}/receipts/{receipt_name}")
    inputs = receipt.get("input_artifacts")
    return set(inputs) if isinstance(inputs, dict) else set()


def _validate_storm_lens_traceability(
    artifacts: Path,
    brief: dict[str, Any],
    plan: dict[str, Any],
    outline: dict[str, Any],
    claims: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    contradictions: dict[str, Any],
    uncertainties: dict[str, Any],
) -> list[str]:
    if brief.get("storm_lens_mode", "advisory") != "strict":
        return []
    errors: list[str] = []
    lens_payloads: dict[str, dict[str, Any]] = {}
    for prompt_id, (relative, _phase) in STORM_LENS_ARTIFACTS.items():
        path = artifacts / relative
        if not path.is_file() or path.is_symlink():
            errors.append(f"strict STORM lens mode requires {relative}")
            continue
        payload = load_json(path)
        errors.extend(_validate_lens_artifact(payload, prompt_id=prompt_id))
        lens_payloads[prompt_id] = payload
    if errors:
        return errors

    receipt_expectations = {
        "10-plan.json": "artifacts/research/storm-lens-perspectives.json",
        "30-evidence.json": "artifacts/research/storm-lens-conflicts.json",
        "30-evidence.json#outline": "artifacts/research/storm-lens-outline.json",
        "50-review.json": "artifacts/research/storm-lens-red-team.json",
    }
    plan_inputs = _receipt_input_keys(artifacts, "10-plan.json")
    evidence_inputs = _receipt_input_keys(artifacts, "30-evidence.json")
    review_inputs = _receipt_input_keys(artifacts, "50-review.json")
    if receipt_expectations["10-plan.json"] not in plan_inputs:
        errors.append("plan receipt does not bind storm-lens-perspectives.json")
    if receipt_expectations["30-evidence.json"] not in evidence_inputs:
        errors.append("evidence receipt does not bind storm-lens-conflicts.json")
    if receipt_expectations["30-evidence.json#outline"] not in evidence_inputs:
        errors.append("evidence receipt does not bind storm-lens-outline.json")
    if receipt_expectations["50-review.json"] not in review_inputs:
        errors.append("review receipt does not bind storm-lens-red-team.json")

    p1_output = lens_payloads["P1"]["output"]
    p1_questions = set(str(item) for item in p1_output.get("question_ids", []))
    plan_questions = {
        str(item.get("question_id"))
        for item in plan.get("questions", [])
        if isinstance(item, dict)
    }
    if not plan_questions <= p1_questions:
        errors.append("storm lens P1 does not cover all planned questions")

    p2_output = lens_payloads["P2"]["output"]
    finding_ids = {
        str(finding.get("finding_id"))
        for finding in findings
        if isinstance(finding, dict)
    }
    unknown_findings = sorted(set(str(item) for item in p2_output.get("finding_ids", [])) - finding_ids)
    if unknown_findings:
        errors.append("storm lens P2 references unknown findings: " + ", ".join(unknown_findings))
    p2_conflict_claims = set(str(item) for item in p2_output.get("conflict_claim_ids", []))
    for conflict in contradictions.get("conflicts", []):
        if isinstance(conflict, dict) and str(conflict.get("claim_id", "")) not in p2_conflict_claims:
            errors.append(f"contradiction {conflict.get('claim_id')} is absent from storm lens P2")
    expected_resolution_texts = {
        *(str(item) for item in p2_output.get("blind_spots", [])),
        *(str(item) for item in p2_output.get("resolver_questions", [])),
    }
    resolution_actions = p2_output.get("resolution_actions", [])
    if not isinstance(resolution_actions, list):
        errors.append("storm lens P2 resolution_actions must be an array")
        resolution_actions = []
    observed_resolution_texts = {
        str(item.get("text")) for item in resolution_actions if isinstance(item, dict)
    }
    if observed_resolution_texts != expected_resolution_texts:
        errors.append("storm lens P2 does not dispose every blind spot and resolver question")
    uncertainty_ids = {
        str(item.get("uncertainty_id"))
        for item in uncertainties.get("uncertainties", []) if isinstance(item, dict)
    }
    for action in resolution_actions:
        if not isinstance(action, dict):
            continue
        if action.get("disposition") == "new_retrieval":
            errors.append(f"storm lens P2 action {action.get('action_id')} still requires new retrieval")
        if action.get("disposition") == "uncertainty" and str(action.get("uncertainty_id")) not in uncertainty_ids:
            errors.append(f"storm lens P2 action {action.get('action_id')} references unknown uncertainty")

    p3_output = lens_payloads["P3"]["output"]
    p3_sections = set(str(item) for item in p3_output.get("section_ids", []))
    outline_sections = {
        str(section.get("section_id"))
        for section in outline.get("sections", [])
        if isinstance(section, dict)
    }
    if not outline_sections <= p3_sections:
        errors.append("storm lens P3 does not cover all outline sections")
    p3_claims = set(str(item) for item in p3_output.get("claim_ids", []))
    material_claims = {
        str(claim.get("claim_id"))
        for claim in claims
        if isinstance(claim, dict) and claim.get("material")
    }
    if not material_claims <= p3_claims:
        errors.append("storm lens P3 does not cover all material Claims")

    p4_output = lens_payloads["P4"]["output"]
    draft_path = artifacts / "drafts/report-v1.md"
    if p4_output.get("target_kind") != "draft":
        errors.append("storm lens P4 target_kind must be draft")
    if p4_output.get("target_sha256") != sha256_file(draft_path):
        errors.append("storm lens P4 target hash does not match draft report-v1.md")
    return errors


def _parsed_datetime(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _receipt_payload(artifacts: Path, name: str) -> dict[str, Any]:
    run_root = artifacts.parents[3]
    generation_name = artifacts.parent.name
    return load_json(run_root / f"state/generations/{generation_name}/receipts/{name}")


def _validate_phase_timestamps(
    artifacts: Path,
    brief: dict[str, Any],
    manifests: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    receipts = {
        key: _receipt_payload(artifacts, name)
        for key, name in (
            ("init", "00-init.json"), ("plan", "10-plan.json"),
            ("retrieval", "20-retrieval.json"), ("evidence", "30-evidence.json"),
            ("draft", "40-draft.json"), ("review", "50-review.json"),
        )
    }
    times = {key: _parsed_datetime(value.get("completed_at")) for key, value in receipts.items()}
    if any(value is None for value in times.values()):
        return ["stage receipt completed_at is invalid"]
    ordered = [times[key] for key in ("init", "plan", "retrieval", "evidence", "draft", "review")]
    if any(left >= right for left, right in zip(ordered, ordered[1:])):
        errors.append("stage receipt completed_at values are not strictly increasing")
    skew = timedelta(minutes=5)
    for manifest in manifests:
        observed = _parsed_datetime(manifest.get("retrieved_at"))
        if not observed or observed < times["plan"] - skew or observed > times["retrieval"] + skew:
            errors.append(f"retrieval {manifest.get('source_id')}/{manifest.get('query_id')} timestamp is outside plan-retrieval window")
    for finding in findings:
        observed = _parsed_datetime(finding.get("created_at"))
        if not observed or observed < times["retrieval"] or observed > times["evidence"]:
            errors.append(f"finding {finding.get('finding_id')} timestamp is outside retrieval-evidence window")
    if brief.get("storm_lens_mode") == "strict":
        lens_windows = {
            "P1": (times["init"], times["plan"]),
            "P2": (times["retrieval"], times["evidence"]),
            "P3": (times["retrieval"], times["evidence"]),
            "P4": (times["draft"], times["review"]),
        }
        lens_times: dict[str, datetime] = {}
        for prompt_id, (relative, _phase) in STORM_LENS_ARTIFACTS.items():
            payload = load_json(artifacts / relative)
            observed = _parsed_datetime(payload.get("created_at"))
            start, end = lens_windows[prompt_id]
            if not observed or observed < start or observed > end:
                errors.append(f"storm lens {prompt_id} timestamp is outside its phase window")
            elif observed:
                lens_times[prompt_id] = observed
        if lens_times.get("P2") and lens_times.get("P3") and lens_times["P2"] > lens_times["P3"]:
            errors.append("storm lens P3 predates P2")
    return list(dict.fromkeys(errors))


def _validate_lens_review_closure(artifacts: Path) -> list[str]:
    p4 = load_json(artifacts / "research/storm-lens-red-team.json")
    revision_map = load_json(artifacts / "research/revision-map.json")
    repairs = p4.get("output", {}).get("repair_actions", [])
    revisions = revision_map.get("revisions", [])
    if not isinstance(repairs, list) or not isinstance(revisions, list):
        return ["P4 repair actions or revision map is invalid"]
    repair_by_id = {
        str(item.get("action_id")): item for item in repairs if isinstance(item, dict)
    }
    revision_by_id = {
        str(item.get("action_id")): item for item in revisions if isinstance(item, dict)
    }
    errors: list[str] = []
    unknown = sorted(
        action_id for action_id in set(revision_by_id) - set(repair_by_id)
        if not re.fullmatch(r"RC\d{3}", action_id)
    )
    if unknown:
        errors.append("revision map contains unknown P4 actions: " + ", ".join(unknown))
    draft_hash = sha256_file(artifacts / "drafts/report-v1.md")
    report_hash = sha256_file(artifacts / "report.md")
    for action_id, action in repair_by_id.items():
        revision = revision_by_id.get(action_id)
        if revision is None:
            errors.append(f"P4 action {action_id} is absent from revision map")
            continue
        required_status = "applied" if action.get("disposition") == "required" else "waived"
        if revision.get("status") != required_status:
            errors.append(f"P4 action {action_id} must be {required_status}")
        if revision.get("before_sha256") != action.get("before_sha256"):
            errors.append(f"P4 action {action_id} before hash mismatch")
        if revision.get("action") != action.get("action"):
            errors.append(f"P4 action {action_id} action mismatch")
        if action.get("target_kind") == "draft":
            if revision.get("before_sha256") != draft_hash:
                errors.append(f"P4 action {action_id} draft before hash mismatch")
            if required_status == "applied" and revision.get("after_sha256") != report_hash:
                errors.append(f"P4 action {action_id} draft after hash mismatch")
        if required_status == "waived" and not str(revision.get("reason", "")).strip():
            errors.append(f"P4 action {action_id} waiver lacks reason")
    return list(dict.fromkeys(errors))


def _validate_review_provenance_artifacts(
    artifacts: Path, peer_review: dict[str, Any]
) -> list[str]:
    request = load_json(artifacts / "research/review-request.json")
    provenance = load_json(artifacts / "research/reviewer-provenance.json")
    errors: list[str] = []
    generation_match = re.fullmatch(r"g(\d{4})", artifacts.parent.name)
    current_generation = int(generation_match.group(1)) if generation_match else 0
    request_unsigned = {key: value for key, value in request.items() if key != "request_sha256"}
    if request.get("request_sha256") != canonical_json_sha256(request_unsigned):
        errors.append("review request hash mismatch")
    for logical, expected in request.get("candidate_artifacts", {}).items():
        relative = str(logical).removeprefix("artifacts/")
        path = artifacts / relative
        if not path.is_file() or sha256_file(path) != expected:
            errors.append(f"review candidate hash mismatch: {logical}")
    review_output = {
        key: peer_review.get(key, [])
        for key in ("claim_reviews", "paragraph_reviews", "fact_checks", "conflict_reviews", "draft_audits")
    }
    review_loop = (
        load_json(artifacts / "research/review-loop.json")
        if (artifacts / "research/review-loop.json").is_file() else {}
    )
    review_output["review_loop"] = review_loop
    if provenance.get("execution_kind") not in {"external_model", "human"}:
        errors.append("review provenance is not external_model or human")
    if provenance.get("author_context_id") == provenance.get("reviewer_context_id"):
        errors.append("reviewer context equals author context")
    if provenance.get("request_sha256") != request.get("request_sha256"):
        errors.append("review provenance request hash mismatch")
    if provenance.get("review_output_sha256") != canonical_json_sha256(review_output):
        errors.append("review provenance output hash mismatch")
    transcript = artifacts / "research/reviewer-transcript.txt"
    if provenance.get("transcript_sha256") != sha256_file(transcript):
        errors.append("reviewer transcript hash mismatch")
    if provenance.get("isolation_attestation") is not True:
        errors.append("review isolation attestation is missing")
    transcript_bytes = transcript.read_bytes()
    sessions = provenance.get("review_sessions")
    observed_sessions: set[tuple[str, str, str, str, str, str]] = set()
    ranges: list[tuple[int, int]] = []
    session_fields = {
        "round_id", "generation", "round_sha256", "reviewer_role", "context_id", "execution_id",
        "start_byte", "end_byte", "sha256",
    }
    if not isinstance(sessions, list) or not sessions:
        errors.append("review provenance requires review_sessions")
        sessions = []
    for index, session in enumerate(sessions, start=1):
        if not isinstance(session, dict) or set(session) != session_fields:
            errors.append(f"review provenance session {index} has invalid fields")
            continue
        start, end = session.get("start_byte"), session.get("end_byte")
        if not isinstance(start, int) or not isinstance(end, int) or not (0 <= start < end <= len(transcript_bytes)):
            errors.append(f"review provenance session {index} byte range is invalid")
            continue
        if any(start < prior_end and prior_start < end for prior_start, prior_end in ranges):
            errors.append(f"review provenance session {index} overlaps another transcript segment")
        ranges.append((start, end))
        if hashlib.sha256(transcript_bytes[start:end]).hexdigest() != session.get("sha256"):
            errors.append(f"review provenance session {index} transcript segment hash mismatch")
        observed_sessions.add((
            str(session.get("round_id")), str(session.get("generation")),
            str(session.get("round_sha256")), str(session.get("reviewer_role")),
            str(session.get("context_id")), str(session.get("execution_id")),
        ))
    if review_loop:
        expected_sessions: set[tuple[str, str, str, str, str, str]] = set()
        for round_record in review_loop.get("rounds", []):
            if not isinstance(round_record, dict):
                continue
            if round_record.get("generation") != current_generation:
                continue
            round_id = str(round_record.get("round_id"))
            for panel_review in round_record.get("panel_reviews", []):
                if isinstance(panel_review, dict):
                    expected_sessions.add((
                        round_id, str(round_record.get("generation")),
                        str(round_record.get("round_sha256")), str(panel_review.get("reviewer_role")),
                        str(panel_review.get("reviewer_context_id")),
                        str(panel_review.get("execution_id")),
                    ))
            editor = round_record.get("editor_review")
            if isinstance(editor, dict):
                expected_sessions.add((
                    round_id, str(round_record.get("generation")),
                    str(round_record.get("round_sha256")), "editor_synthesizer", str(editor.get("context_id")),
                    str(editor.get("execution_id")),
                ))
        if observed_sessions != expected_sessions:
            errors.append("review provenance sessions do not match panel and editor executions")
    session_id = provenance.get("review_session_id")
    author_id = provenance.get("author_context_id")
    started = _parsed_datetime(provenance.get("started_at"))
    completed = _parsed_datetime(provenance.get("completed_at"))
    created = _parsed_datetime(request.get("created_at"))
    if not started or not completed or not created or not (created <= started <= completed):
        errors.append("review provenance timestamps are not causal")
    for key, collection in review_output.items():
        if key == "review_loop":
            continue
        if not isinstance(collection, list):
            errors.append("peer review collection is invalid")
            continue
        for review in collection:
            if not isinstance(review, dict):
                continue
            if review.get("reviewer_run_id") != session_id or review.get("author_run_id") != author_id:
                errors.append(f"review {review.get('review_id')} is not provenance-bound")
            reviewed = _parsed_datetime(review.get("reviewed_at"))
            if started and completed and (not reviewed or not (started <= reviewed <= completed)):
                errors.append(f"review {review.get('review_id')} timestamp is outside reviewer execution")
    summary = peer_review.get("summary", {})
    if not isinstance(summary, dict) or summary.get("assurance") != "captured external review":
        errors.append("peer review does not disclose captured external review assurance")
    if peer_review.get("reviewer_provenance") != provenance:
        errors.append("peer review embedded provenance mismatch")
    return list(dict.fromkeys(errors))


def _validate_review_loop_summary(
    brief: dict[str, Any],
    summary: dict[str, Any],
    p4: dict[str, Any] | None,
) -> list[str]:
    if not _is_full_external_dossier(brief):
        return []
    expected_loop_policy = (
        "concern_driven_until_clear"
        if brief.get("research_profile") == "maximal_full_dossier"
        else "single_pass_external_review"
    )
    errors: list[str] = []
    if summary.get("review_loop_policy") != expected_loop_policy:
        errors.append(f"peer review loop policy must be {expected_loop_policy}")
    if brief.get("storm_lens_mode") == "strict":
        repairs = (p4 or {}).get("output", {}).get("repair_actions", [])
        expected_repairs = len(repairs) if isinstance(repairs, list) else 0
        if summary.get("p4_repair_actions") != expected_repairs:
            errors.append("peer review P4 repair count does not match storm lens P4")
    return errors


def _domain_checks(artifacts: Path, brief_path: Path) -> list[Check]:
    checks: list[Check] = []
    brief = load_json(brief_path)
    plan = load_json(artifacts / "research/research-plan.json")
    source_plan = load_json(artifacts / "research/source-plan.json")
    sources = load_jsonl(artifacts / "research/source-register.jsonl")
    manifests = load_jsonl(artifacts / "research/retrieval-manifest.jsonl")
    audit = load_jsonl(artifacts / "research/retrieval-audit.jsonl")
    tasklets = load_jsonl(artifacts / "research/storm-tasklets.jsonl")
    findings_path = artifacts / "research/storm-findings-pool.jsonl"
    coverage_path = artifacts / "research/finding-coverage.json"
    findings = load_jsonl(findings_path) if findings_path.exists() else []
    claims = load_jsonl(artifacts / "research/claim-evidence-ledger.jsonl")
    outline = load_json(artifacts / "research/report-outline.json")
    contradictions = load_json(artifacts / "research/contradiction-ledger.json")
    uncertainties = load_json(artifacts / "research/uncertainty-ledger.json")
    absence_path = artifacts / "research/absence-search-ledger.jsonl"
    absence_searches = load_jsonl(absence_path) if absence_path.exists() else []
    finding_coverage = load_json(coverage_path) if coverage_path.exists() else {}
    paragraph_map = load_jsonl(artifacts / "research/reviewed-paragraph-map.jsonl")
    peer_review = load_json(artifacts / "research/peer-review.json")
    report = (artifacts / "report.md").read_text(encoding="utf-8")

    claim_ids = {str(item.get("claim_id")) for item in claims}
    question_ids = {str(item.get("question_id")) for item in plan.get("questions", []) if isinstance(item, dict)}
    contract_errors = validate_brief(brief)
    contract_errors.extend(_profile_prompt_evidence_errors(brief, brief_path))
    contract_errors.extend(validate_research_plan(plan, brief, claim_ids))
    contract_errors.extend(validate_source_plan(source_plan))
    contract_errors.extend(validate_report_outline(outline, brief, question_ids, claim_ids))
    contract_errors.extend(_validate_tasklets(tasklets, plan, source_plan))
    add_check(
        checks, "contracts", contract_errors, "inputs/brief.json; artifacts/research/*.json",
        "brief, plan, source plan, and outline contracts are valid", "repair contracts and restart from the responsible stage", EXIT_CONTRACT,
    )

    audit_errors: list[str] = []
    for index, record in enumerate(audit, start=1):
        audit_errors.extend(
            f"retrieval audit row {index}: {item}"
            for item in validate_retrieval_input_record(record)
        )
    audit_errors.extend(validate_retrieval_audit(audit, manifests, sources, source_plan, brief))
    add_check(
        checks,
        "academic-retrieval-integrity",
        audit_errors,
        "artifacts/research/retrieval-audit.jsonl; artifacts/research/retrieval-manifest.jsonl",
        "academic baseline, candidate screening, version families, and captures are closed",
        "repair retrieval audit inputs and create a new governed generation",
        EXIT_EVIDENCE,
    )

    evidence_errors = validate_claim_closure(claims, sources, outline, manifests)
    evidence_errors.extend(validate_absence_searches(claims, absence_searches, sources, manifests, brief))
    if _is_maximal_full_dossier(brief):
        evidence_errors.extend(validate_material_capture_depth(claims, manifests))
    evidence_errors.extend(_validate_contradictions(contradictions, claims))
    evidence_errors.extend(_validate_uncertainties(uncertainties))
    full_external_dossier = _is_full_external_dossier(brief)
    if full_external_dossier:
        if not findings_path.exists():
            evidence_errors.append("full external dossier requires storm-findings-pool.jsonl")
        if not coverage_path.exists():
            evidence_errors.append("full external dossier requires finding-coverage.json")
    if findings:
        evidence_errors.extend(_validate_findings(
            findings, tasklets, sources, manifests, claims,
            require_tasklet_coverage=full_external_dossier,
        ))
    elif full_external_dossier:
        evidence_errors.append("full external dossier requires non-empty STORM findings")
    if finding_coverage and (
        finding_coverage.get("schema_version") != "2.0"
        or not isinstance(finding_coverage.get("missing_tasklet_ids"), list)
    ):
        evidence_errors.append("finding coverage has invalid contract")
    elif full_external_dossier and finding_coverage.get("missing_tasklet_ids"):
        evidence_errors.append("finding coverage still has missing tasklets")
    uncertainty_ids = {
        str(item.get("uncertainty_id"))
        for item in uncertainties.get("uncertainties", []) if isinstance(item, dict)
    }
    for assessment in finding_coverage.get("saturation_assessments", []):
        if not isinstance(assessment, dict):
            continue
        if assessment.get("terminal_state") == "access_limited_uncertainty" and str(assessment.get("uncertainty_id")) not in uncertainty_ids:
            evidence_errors.append(
                f"{assessment.get('gap_id')} access limitation is not registered in uncertainty ledger"
            )
    coverage = compute_coverage(claims)
    if coverage["material_fact_closure"] != 1.0:
        evidence_errors.append("material fact closure is below 100%")
    if not any(claim.get("material") for claim in claims):
        evidence_errors.append("no material Claims are registered")
    add_check(
        checks, "evidence-closure", evidence_errors, "artifacts/research/claim-evidence-ledger.jsonl",
        "material Claims, sources, snapshots, contradictions, and outline are closed",
        "repair the Claim-Evidence ledger and rerun evidence", EXIT_EVIDENCE,
    )

    add_check(
        checks,
        "maximal-completeness",
        _validate_maximal_completeness(
            brief, sources, manifests, audit, tasklets, findings, claims, outline, paragraph_map,
            report, finding_coverage, contradictions, uncertainties,
        ),
        "artifacts/research/source-register.jsonl; artifacts/research/storm-findings-pool.jsonl; artifacts/research/claim-evidence-ledger.jsonl",
        "maximal_full_dossier tasklet closure and retrieval saturation recompute or are not applicable",
        "continue gap-fill retrieval and findings until material novelty saturates",
        EXIT_EVIDENCE,
    )

    add_check(
        checks,
        "storm-lens-traceability",
        _validate_storm_lens_traceability(
            artifacts, brief, plan, outline, claims, findings, contradictions, uncertainties
        ),
        "artifacts/research/storm-lens-*.json; receipts/",
        "STORM lens artifacts are phase-bound or advisory mode is explicit",
        "register lens artifacts at the required phase and rerun the dependent stage",
        EXIT_STAGE,
    )
    add_check(
        checks,
        "storm-lens-phase-order",
        _validate_phase_timestamps(artifacts, brief, manifests, findings),
        "artifacts/research/storm-lens-*.json; receipts/",
        "receipts, retrieval, findings, and STORM lens timestamps are causal",
        "create a new generation with harness-owned timestamps",
        EXIT_STAGE,
    )
    closure_errors = (
        _validate_lens_review_closure(artifacts)
        if brief.get("storm_lens_mode") == "strict" else []
    )
    add_check(
        checks,
        "storm-lens-review-closure",
        closure_errors,
        "artifacts/research/storm-lens-red-team.json; artifacts/research/revision-map.json",
        "every P4 repair action is closed by an applied revision or reasoned waiver",
        "repair the candidate and rebuild the revision map before external review",
        EXIT_EVIDENCE,
    )

    traceability_errors = validate_report_traceability(report, paragraph_map, claims, sources)
    claim_reviews = peer_review.get("claim_reviews", [])
    paragraph_reviews = peer_review.get("paragraph_reviews", [])
    fact_checks = peer_review.get("fact_checks", [])
    conflict_reviews = peer_review.get("conflict_reviews", [])
    draft_audits = peer_review.get("draft_audits", [])
    if not isinstance(claim_reviews, list) or not isinstance(paragraph_reviews, list):
        traceability_errors.append("peer review must contain claim and paragraph review arrays")
    else:
        traceability_errors.extend(validate_review_set(report, claims, claim_reviews, paragraph_reviews))
    if _is_full_external_dossier(brief):
        if not all(isinstance(value, list) and value for value in (fact_checks, conflict_reviews, draft_audits)):
            traceability_errors.append("full dossier requires fact_checks, conflict_reviews, and draft_audits")
        else:
            traceability_errors.extend(validate_review_set(report, claims, fact_checks, draft_audits))
            traceability_errors.extend(_validate_conflict_reviews(contradictions, conflict_reviews))
    summary = peer_review.get("summary")
    if not isinstance(summary, dict) or summary.get("decision") != "passed":
        traceability_errors.append("peer review summary is not passing")
    else:
        p4 = (
            load_json(artifacts / "research/storm-lens-red-team.json")
            if brief.get("storm_lens_mode") == "strict" else None
        )
        traceability_errors.extend(_validate_review_loop_summary(brief, summary, p4))
    traceability_errors.extend(_validate_review_provenance_artifacts(artifacts, peer_review))
    traceability_errors.extend(_validate_review_loop_artifact(artifacts, brief))
    add_check(
        checks, "report-traceability", traceability_errors,
        "artifacts/report.md; artifacts/research/reviewed-paragraph-map.jsonl; artifacts/research/peer-review.json",
        "every paragraph, citation, Claim, and independent review is closed",
        "repair mappings or reviews and rerun review", EXIT_EVIDENCE,
    )

    length_contract = brief["length_contract"]
    metrics = body_length_metrics(report, str(length_contract["unit"]))
    measured = int(metrics["net_body"])
    length_errors = []
    length_policy = str(length_contract.get("policy", "bounded"))
    if length_policy == "bounded" and (
        measured < int(length_contract["minimum"]) or measured > int(length_contract["maximum"])
    ):
        length_errors.append(
            f"report body length {measured} {length_contract['unit']} is outside "
            f"{length_contract['minimum']}-{length_contract['maximum']}"
        )
    elif length_policy != "open_ended" and length_policy != "bounded":
        length_errors.append("length_contract.policy must be bounded or open_ended")
    length_errors.extend(quote_limit_errors(report, str(length_contract["unit"])))
    length_message = (
        "report body records open-ended evidence-led depth "
        if length_policy == "open_ended"
        else "report body satisfies the evidence-led length contract "
    )
    add_check(
        checks, "report-depth", length_errors, "artifacts/report.md",
        (
            length_message
            +
            f"(raw={metrics['raw_body']}, citations={metrics['citation_markers']}, "
            f"net={measured} {length_contract['unit']})"
        ),
        "revise evidence-backed sections without padding", EXIT_EXPORT,
    )
    return checks


def _render_checks(artifacts: Path, *, pdf_required: bool) -> list[Check]:
    checks: list[Check] = []
    report_path = artifacts / "report.md"
    html_path = artifacts / "exports/report.html"
    pdf_path = artifacts / "exports/report.pdf"
    manifest_path = artifacts / "validation/render-manifest.json"
    report = report_path.read_text(encoding="utf-8")
    html_text = html_path.read_text(encoding="utf-8")
    manifest = load_json(manifest_path)
    title = markdown_title(report)
    section_records = markdown_sections(report)
    section_titles = [item["title"] for item in section_records]
    render_errors: list[str] = []
    if _html_title(html_text) != title:
        render_errors.append("Markdown and HTML title mismatch")
    html_section_titles = _html_sections(html_text)
    if any(item not in html_section_titles for item in section_titles):
        render_errors.append("HTML omits or changes Markdown sections")
    if "References" not in section_titles or "References" not in html_section_titles:
        render_errors.append("References is missing from Markdown or HTML")
    expected_manifest: dict[str, object] = {
        "report_md_sha256": sha256_file(report_path),
        "report_html_sha256": sha256_file(html_path),
        "report_pdf_sha256": sha256_file(pdf_path) if pdf_path.is_file() else None,
    }
    for field, expected in expected_manifest.items():
        if manifest.get(field) != expected:
            render_errors.append(f"render manifest {field} mismatch")
    if manifest.get("schema_version") != "2.0" or manifest.get("title") != title:
        render_errors.append("render manifest contract or title mismatch")
    if manifest.get("section_fingerprints") != section_records:
        render_errors.append("render section fingerprints mismatch")
    if pdf_required and not pdf_path.is_file():
        render_errors.append("required PDF is missing")
    elif pdf_path.is_file():
        try:
            reader = PdfReader(pdf_path)
            extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
            if not reader.pages:
                render_errors.append("PDF has no pages")
            if title not in extracted or "References" not in extracted:
                render_errors.append("PDF does not contain the title and References")
            if manifest.get("pdf_page_count") != len(reader.pages):
                render_errors.append("PDF page count does not match render manifest")
        except Exception as exc:
            render_errors.append(f"PDF is unreadable: {exc}")
    elif manifest.get("pdf_renderer") != "none" or manifest.get("pdf_page_count") != 0:
        render_errors.append("reduced render manifest incorrectly declares a PDF")
    add_check(
        checks, "format-parity", render_errors,
        "artifacts/report.md; artifacts/exports/*; artifacts/validation/render-manifest.json",
        "Markdown, HTML, PDF, and render manifest agree",
        "rerun render from the reviewed canonical Markdown", EXIT_EXPORT,
    )
    return checks


EXECUTION_PROVENANCE_FIELDS = {
    "schema_version", "provenance_id", "stage", "execution_kind",
    "context_id", "provider", "model", "runner", "execution_id",
    "started_at", "completed_at", "transcript_ref", "transcript_sha256",
    "input_artifacts", "output_artifacts", "record_ids", "provider_signed",
}


def _execution_transcript_errors(text: str, label: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    errors: list[str] = []
    if len(text.strip()) < 200:
        errors.append(f"{label} transcript has fewer than 200 characters")
    if len(lines) < 3:
        errors.append(f"{label} transcript has fewer than three non-empty lines")
    return errors


def _validate_execution_provenance_file(
    layout: RunLayout,
    generation: int,
    *,
    stage: str,
    expected_record_ids: list[str],
) -> tuple[dict[str, object] | None, list[str]]:
    errors: list[str] = []
    provenance_path = layout.artifact(
        generation, f"research/execution/{stage}-provenance.json"
    )
    transcript_path = layout.artifact(
        generation, f"research/execution/{stage}-transcript.txt"
    )
    if not provenance_path.is_file() or provenance_path.is_symlink():
        return None, [f"captured execution is missing {stage} provenance"]
    if not transcript_path.is_file() or transcript_path.is_symlink():
        return None, [f"captured execution is missing {stage} transcript"]
    provenance = load_json(provenance_path)
    if set(provenance) != EXECUTION_PROVENANCE_FIELDS:
        errors.append(f"{stage} execution provenance has invalid fields")
    if provenance.get("schema_version") != "2.0" or provenance.get("stage") != stage:
        errors.append(f"{stage} execution provenance contract mismatch")
    if provenance.get("execution_kind") != "host_execution":
        errors.append(f"{stage} execution kind is not host_execution")
    if provenance.get("provider_signed") is not False:
        errors.append(f"{stage} provider_signed must be false")
    if provenance.get("record_ids") != expected_record_ids:
        errors.append(f"{stage} execution record_ids do not match governed records")
    transcript = transcript_path.read_text(encoding="utf-8")
    if provenance.get("transcript_sha256") != sha256_file(transcript_path):
        errors.append(f"{stage} execution transcript hash mismatch")
    expected_ref = f"artifacts/research/execution/{stage}-transcript.txt"
    if provenance.get("transcript_ref") != expected_ref:
        errors.append(f"{stage} execution transcript_ref mismatch")
    errors.extend(_execution_transcript_errors(transcript, stage))
    generation_root = layout.generation_root(generation)
    for field in ("input_artifacts", "output_artifacts"):
        hashes = provenance.get(field)
        if not isinstance(hashes, dict) or not hashes:
            errors.append(f"{stage} execution {field} is empty")
            continue
        for logical, expected_hash in hashes.items():
            try:
                path = package_child(generation_root, str(logical))
            except OutputPathError as exc:
                errors.append(f"{stage} execution {field} path is unsafe: {exc}")
                continue
            if not path.is_file() or path.is_symlink() or sha256_file(path) != expected_hash:
                errors.append(f"{stage} execution {field} hash mismatch: {logical}")
    return provenance, errors


def _execution_assurance_errors(
    layout: RunLayout,
    generation: int,
    brief: dict[str, object],
) -> list[str]:
    if brief.get("assurance_target") != "captured_host_execution":
        return []
    artifacts = layout.artifact(generation, ".")
    audit = load_jsonl(artifacts / "research/retrieval-audit.jsonl")
    claims = load_jsonl(artifacts / "research/claim-evidence-ledger.jsonl")
    retrieval_ids = sorted(
        str(
            record.get("search_run_id") or record.get("candidate_id")
            or record.get("wave_id") or record.get("assessment_id")
        )
        for record in audit
        if record.get("record_kind") in {
            "search_run", "candidate", "search_wave", "gap_assessment"
        }
    )
    claim_ids = sorted(str(claim.get("claim_id")) for claim in claims)
    retrieval, errors = _validate_execution_provenance_file(
        layout, generation, stage="retrieval", expected_record_ids=retrieval_ids
    )
    draft, draft_errors = _validate_execution_provenance_file(
        layout, generation, stage="draft", expected_record_ids=claim_ids
    )
    errors.extend(draft_errors)
    review_path = artifacts / "research/reviewer-provenance.json"
    transcript_path = artifacts / "research/reviewer-transcript.txt"
    request_path = artifacts / "research/review-request.json"
    if not all(path.is_file() and not path.is_symlink() for path in (review_path, transcript_path, request_path)):
        errors.append("captured execution is missing review provenance, request, or transcript")
        return list(dict.fromkeys(errors))
    review = load_json(review_path)
    request = load_json(request_path)
    errors.extend(_execution_transcript_errors(transcript_path.read_text(encoding="utf-8"), "review"))
    plan_receipt = load_json(layout.receipt(generation, Stage.PLAN))
    retrieval_receipt = load_json(layout.receipt(generation, Stage.RETRIEVAL))
    evidence_receipt = load_json(layout.receipt(generation, Stage.EVIDENCE))
    draft_receipt = load_json(layout.receipt(generation, Stage.DRAFT))
    review_receipt = load_json(layout.receipt(generation, Stage.REVIEW))
    windows = [
        ("retrieval", retrieval, plan_receipt.get("completed_at"), retrieval_receipt.get("completed_at")),
        ("draft", draft, evidence_receipt.get("completed_at"), draft_receipt.get("completed_at")),
        ("review", review, request.get("created_at"), review_receipt.get("completed_at")),
    ]
    parsed: dict[str, tuple[datetime, datetime]] = {}
    for label, provenance, lower_raw, upper_raw in windows:
        if not isinstance(provenance, dict):
            continue
        lower = _parsed_datetime(lower_raw)
        started = _parsed_datetime(provenance.get("started_at"))
        completed = _parsed_datetime(provenance.get("completed_at"))
        upper = _parsed_datetime(upper_raw)
        if not all((lower, started, completed, upper)) or not (lower <= started < completed <= upper):
            errors.append(f"{label} execution is outside its causal receipt window")
        else:
            parsed[label] = (started, completed)
    if all(label in parsed for label in ("retrieval", "draft", "review")):
        if not (parsed["retrieval"][1] <= parsed["draft"][0] and parsed["draft"][1] <= parsed["review"][0]):
            errors.append("retrieval, draft, and review execution windows overlap or are out of order")
    if isinstance(draft, dict):
        if request.get("author_context_id") != draft.get("context_id"):
            errors.append("review request author context does not match draft execution context")
        if review.get("author_context_id") != draft.get("context_id"):
            errors.append("review provenance author context does not match draft execution context")
    if review.get("reviewer_context_id") == review.get("author_context_id"):
        errors.append("reviewer context is not isolated from author context")
    if brief.get("research_profile") == "maximal_full_dossier":
        errors.extend(validate_captured_retrieval_artifacts(
            audit, layout.evidence_cache(generation, ".")
        ))
        contexts = [
            item.get("context_id") if isinstance(item, dict) else None
            for item in (retrieval, draft)
        ] + [review.get("reviewer_context_id")]
        executions = [
            item.get("execution_id") if isinstance(item, dict) else None
            for item in (retrieval, draft)
        ] + [review.get("execution_id")]
        if len(set(contexts)) != 3 or None in contexts:
            errors.append("maximal captured execution requires three distinct execution contexts")
        if len(set(executions)) != 3 or None in executions:
            errors.append("maximal captured execution requires three distinct execution IDs")
        dispositions = {
            str(record.get("disposition"))
            for record in audit if record.get("record_kind") == "candidate"
        }
        if dispositions == {"include"}:
            errors.append("maximal captured execution candidate pool cannot be all include")
    return list(dict.fromkeys(errors))


def validate_governed_run(
    layout: RunLayout, generation: int, package_hash: str
) -> tuple[list[Check], int]:
    artifacts = layout.artifact(generation, ".")
    brief_path = layout.generation_input(generation, "brief.json")
    validation_committed = layout.receipt(generation, Stage.VALIDATION).is_file()
    try:
        brief = load_json(brief_path)
    except ContractError as exc:
        checks = []
        add_check(
            checks, "brief-json", [f"authoritative brief is not valid JSON: {exc}"],
            "inputs/brief.json", "authoritative brief parses", "create a new governed generation", EXIT_CONTRACT,
        )
        return checks, EXIT_CONTRACT
    diagnostic_errors: list[str] = []
    if brief.get("run_intent") == "diagnostic_rehearsal":
        diagnostic_errors.append(
            "diagnostic_rehearsal runs are observation artifacts and cannot be validated for user delivery"
        )
    debt_path = artifacts / "research/blocking-debt-ledger.json"
    if debt_path.is_file() and not debt_path.is_symlink():
        diagnostic_errors.append(
            "blocking-debt-ledger.json is present; unresolved diagnostic debt blocks validation"
        )
    if diagnostic_errors:
        checks: list[Check] = []
        add_check(
            checks,
            "diagnostic-rehearsal",
            diagnostic_errors,
            "inputs/brief.json; artifacts/research/blocking-debt-ledger.json",
            "only user_delivery runs without blocking debt can validate",
            "create a new user_delivery run and close the blocked gates without --allow-diagnostic-debt",
            EXIT_STAGE,
        )
        return checks, EXIT_STAGE
    pdf_required = brief.get("output_mode") == "full"
    checks, code = _structural_checks(
        artifacts, pdf_required=pdf_required, validation_committed=validation_committed
    )
    if code:
        return checks, code
    safety_checks, code = _public_safety_checks(artifacts)
    checks.extend(safety_checks)
    if code:
        return checks, code
    try:
        verify_receipt_chain(layout, generation, Stage.RENDER, package_hash)
        receipt_errors: list[str] = []
    except ReceiptError as exc:
        receipt_errors = [f"receipt chain verification failed: {exc}"]
    add_check(
        checks, "receipt-chain", receipt_errors, "state/generations/*/receipts/",
        "receipt chain and all bound hashes recompute", "restore authoritative artifacts or create a new generation", EXIT_STAGE,
    )
    if receipt_errors:
        return checks, EXIT_STAGE
    assurance_errors = _execution_assurance_errors(layout, generation, brief)
    add_check(
        checks,
        "execution-assurance",
        assurance_errors,
        "inputs/brief.json; artifacts/research/execution/; artifacts/research/reviewer-provenance.json",
        (
            "captured host execution evidence is hash-bound and causal"
            if brief.get("assurance_target") == "captured_host_execution"
            else "artifact contract validation is explicitly scoped without host execution claims"
        ),
        "supply stage-bound retrieval, draft, and review execution evidence or select artifact_contract at init",
        EXIT_STAGE,
    )
    if assurance_errors:
        return checks, EXIT_STAGE
    try:
        checks.extend(_domain_checks(artifacts, brief_path))
        checks.extend(_render_checks(artifacts, pdf_required=pdf_required))
    except (ContractError, KeyError, TypeError, ValueError, OSError) as exc:
        add_check(
            checks, "validation-runtime", [str(exc)], "artifacts/",
            "all validation inputs are readable", "repair the malformed governed artifact", EXIT_CONTRACT,
        )
    failed = [check.exit_code for check in checks if check.status == "fail"]
    return checks, max(failed, default=0)


def _report_payload(
    checks: list[Check], generation: int, measurements: dict[str, object], assurance_target: str,
    review_outcomes: dict[str, object] | None = None,
) -> dict[str, object]:
    captured = assurance_target == "captured_host_execution"
    payload: dict[str, object] = {
        "schema_version": "2.0",
        "ok": True,
        "generation": generation,
        "validated_through": Stage.RENDER.value,
        "assurance_target": assurance_target,
        "assurance_level": (
            "validated_captured_host_execution"
            if captured else "validated_artifact_contract_only"
        ),
        "provider_signed": False,
        "not_valid_for": [] if captured else [
            "user_delivery", "real_host_execution_claim", "public_release"
        ],
        "limitations": [
            (
                "Captured execution evidence is hash-bound but not provider-signed."
                if captured
                else "Artifact contracts were validated without captured host execution evidence."
            )
        ],
        "checks": [check.public() for check in checks],
        "measurements": measurements,
        "summary": {
            "passed": sum(check.status == "pass" for check in checks),
            "warnings": sum(check.status == "warn" for check in checks),
            "failed": sum(check.status == "fail" for check in checks),
        },
    }
    if review_outcomes is not None:
        payload["review_outcomes"] = review_outcomes
    return payload


def _report_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# Validation Report", "", "**Status:** PASS",
        f"**Assurance:** `{payload.get('assurance_level', '')}`",
        "**Provider signed:** no", "",
    ]
    for raw in payload["checks"]:
        check = raw if isinstance(raw, dict) else {}
        lines.append(f"- [x] `{check.get('check_id', '')}` {check.get('message', '')} (`{check.get('path', '')}`)")
    summary = payload["summary"]
    depth = payload.get("measurements", {}).get("report_depth", {})
    review_loop = payload.get("measurements", {}).get("max_review_loop", {})
    lines.extend([
        "",
        (
            "Report depth: "
            f"raw={depth.get('raw_body', 0)}, citations={depth.get('citation_markers', 0)}, "
            f"net={depth.get('net_body', 0)} {depth.get('unit', '')}"
        ),
        f"Passed: {summary['passed']} | Warnings: {summary['warnings']} | Failed: {summary['failed']}",
    ])
    if review_loop:
        lines.append(
            "Max loop: "
            f"search waves={review_loop.get('search_waves', 0)}, "
            f"review rounds={review_loop.get('round_count', 0)}, "
            f"decisions={','.join(review_loop.get('decision_path', []))}, "
            f"concerns opened={review_loop.get('concerns_opened', 0)}, "
            f"unresolved={review_loop.get('concerns_unresolved', 0)}, "
            f"integrity={review_loop.get('final_integrity_status', '')}"
        )
    return "\n".join(lines) + "\n"


def _max_review_loop_metrics(artifacts: Path) -> dict[str, object] | None:
    loop_path = artifacts / "research/review-loop.json"
    if not loop_path.is_file() or loop_path.is_symlink():
        return None
    loop = load_json(loop_path)
    rounds = [item for item in loop.get("rounds", []) if isinstance(item, dict)]
    terminal: dict[str, str] = {}
    opened: set[str] = set()
    for round_record in rounds:
        for concern in round_record.get("required_concerns", []):
            if not isinstance(concern, dict):
                continue
            concern_id = str(concern.get("concern_id", ""))
            disposition = str(concern.get("disposition", ""))
            if disposition == "open":
                opened.add(concern_id)
            elif disposition in {"addressed", "waived", "preserved_as_uncertainty"}:
                terminal[concern_id] = disposition
    audit = load_jsonl(artifacts / "research/retrieval-audit.jsonl")
    coverage = load_json(artifacts / "research/finding-coverage.json")
    assessments = [
        item for item in coverage.get("saturation_assessments", [])
        if isinstance(item, dict)
    ]
    integrity = loop.get("final_integrity")
    sources = load_jsonl(artifacts / "research/source-register.jsonl")
    candidates = [item for item in audit if item.get("record_kind") == "candidate"]
    tasklets = load_jsonl(artifacts / "research/storm-tasklets.jsonl")
    findings = load_jsonl(artifacts / "research/storm-findings-pool.jsonl")
    claims = load_jsonl(artifacts / "research/claim-evidence-ledger.jsonl")
    outline = load_json(artifacts / "research/report-outline.json")
    return {
        "source_count": len(sources),
        "candidate_count": len(candidates),
        "tasklet_count": len(tasklets),
        "usable_finding_count": sum(item.get("status") == "usable" for item in findings),
        "material_claim_count": sum(bool(item.get("material")) for item in claims),
        "section_count": len(outline.get("sections", [])),
        "search_waves": sum(item.get("record_kind") == "search_wave" for item in audit),
        "saturated_gaps": sum(item.get("terminal_state") == "saturated" for item in assessments),
        "round_count": len(rounds),
        "decision_path": [str(item.get("editor_decision", "")) for item in rounds],
        "concerns_opened": len(opened),
        "concerns_addressed": sum(value == "addressed" for value in terminal.values()),
        "concerns_waived": sum(value == "waived" for value in terminal.values()),
        "concerns_preserved_as_uncertainty": sum(
            value == "preserved_as_uncertainty" for value in terminal.values()
        ),
        "concerns_unresolved": len(opened - set(terminal)),
        "final_integrity_status": (
            str(integrity.get("status", "")) if isinstance(integrity, dict) else ""
        ),
    }


def _review_outcomes(artifacts: Path) -> dict[str, object] | None:
    loop_path = artifacts / "research/review-loop.json"
    if not loop_path.is_file() or loop_path.is_symlink():
        return None
    loop = load_json(loop_path)
    rounds = [item for item in loop.get("rounds", []) if isinstance(item, dict)]
    terminal: dict[str, str] = {}
    opened: dict[str, dict[str, object]] = {}
    for round_record in rounds:
        for concern in round_record.get("required_concerns", []):
            if not isinstance(concern, dict):
                continue
            concern_id = str(concern.get("concern_id", ""))
            if concern.get("disposition") == "open":
                opened[concern_id] = concern
            elif concern.get("disposition") in {
                "addressed", "waived", "preserved_as_uncertainty",
            }:
                terminal[concern_id] = str(concern.get("disposition"))
    run_root = artifacts.parents[3]
    sources_added = 0
    claims_added = 0
    claims_downgraded = 0
    claims_removed = 0
    sections_revised = 0
    storm_conflicts_closed = 0
    retrieval_cycles_triggered = 0
    strength_rank = {"background": 0, "weak": 1, "medium": 2, "strong": 3}
    for previous_round, current_round in zip(rounds, rounds[1:]):
        previous_generation = int(previous_round.get("generation", 0))
        current_generation = int(current_round.get("generation", 0))
        if previous_generation < 1 or current_generation <= previous_generation:
            continue
        previous_artifacts = run_root / f"work/generations/g{previous_generation:04d}/artifacts"
        current_artifacts = run_root / f"work/generations/g{current_generation:04d}/artifacts"
        prior_open = [
            item for item in previous_round.get("required_concerns", [])
            if isinstance(item, dict) and item.get("disposition") == "open"
        ]
        if any(item.get("required_stage") == "retrieval" for item in prior_open):
            retrieval_cycles_triggered += 1
        previous_sources = {
            str(item.get("source_id"))
            for item in load_jsonl(previous_artifacts / "research/source-register.jsonl")
        }
        current_sources = {
            str(item.get("source_id"))
            for item in load_jsonl(current_artifacts / "research/source-register.jsonl")
        }
        sources_added += len(current_sources - previous_sources)
        previous_claims = {
            str(item.get("claim_id")): item
            for item in load_jsonl(previous_artifacts / "research/claim-evidence-ledger.jsonl")
        }
        current_claims = {
            str(item.get("claim_id")): item
            for item in load_jsonl(current_artifacts / "research/claim-evidence-ledger.jsonl")
        }
        claims_added += len(set(current_claims) - set(previous_claims))
        claims_removed += len(set(previous_claims) - set(current_claims))
        for claim_id in set(previous_claims) & set(current_claims):
            before = previous_claims[claim_id]
            after = current_claims[claim_id]
            if strength_rank.get(str(after.get("evidence_strength")), -1) < strength_rank.get(
                str(before.get("evidence_strength")), -1
            ) or (
                before.get("status") == "supported"
                and after.get("status") in {"contested", "uncertain", "rejected"}
            ):
                claims_downgraded += 1
        previous_sections = {
            str(item.get("section_id")): canonical_json_sha256(item)
            for item in load_json(previous_artifacts / "research/report-outline.json").get("sections", [])
            if isinstance(item, dict)
        }
        current_sections = {
            str(item.get("section_id")): canonical_json_sha256(item)
            for item in load_json(current_artifacts / "research/report-outline.json").get("sections", [])
            if isinstance(item, dict)
        }
        sections_revised += sum(
            previous_sections.get(section_id) != digest
            for section_id, digest in current_sections.items()
            if section_id in previous_sections
        )
        previous_conflicts = {
            str(item.get("conflict_id")): item
            for item in load_json(previous_artifacts / "research/contradiction-ledger.json").get("conflicts", [])
            if isinstance(item, dict)
        }
        current_conflicts = {
            str(item.get("conflict_id")): item
            for item in load_json(current_artifacts / "research/contradiction-ledger.json").get("conflicts", [])
            if isinstance(item, dict)
        }
        storm_conflicts_closed += sum(
            conflict_id not in current_conflicts
            or current_conflicts[conflict_id].get("resolution_status") in {"resolved", "bounded", "preserved"}
            for conflict_id, conflict in previous_conflicts.items()
            if conflict.get("resolution_status") not in {"resolved", "bounded", "preserved"}
        )
    blind_spots_disclosed = sum(
        concern.get("issue_type") == "blind_spot"
        and terminal.get(concern_id) in {"addressed", "preserved_as_uncertainty"}
        for concern_id, concern in opened.items()
    )
    final_integrity = loop.get("final_integrity")
    return {
        "decision_path": [str(item.get("editor_decision", "")) for item in rounds],
        "concerns_opened": len(opened),
        "concerns_addressed": sum(value == "addressed" for value in terminal.values()),
        "concerns_preserved_as_uncertainty": sum(
            value == "preserved_as_uncertainty" for value in terminal.values()
        ),
        "concerns_waived": sum(value == "waived" for value in terminal.values()),
        "retrieval_cycles_triggered": retrieval_cycles_triggered,
        "sources_added": sources_added,
        "claims_added": claims_added,
        "claims_downgraded": claims_downgraded,
        "claims_removed": claims_removed,
        "sections_revised": sections_revised,
        "storm_conflicts_closed": storm_conflicts_closed,
        "storm_blind_spots_disclosed": blind_spots_disclosed,
        "final_integrity": (
            str(final_integrity.get("status", "")) if isinstance(final_integrity, dict) else ""
        ),
    }


def commit_validation(
    layout: RunLayout,
    generation: int,
    package_hash: str,
    checks: list[Check],
) -> None:
    brief = load_json(layout.generation_input(generation, "brief.json"))
    unit = str(brief["length_contract"]["unit"])
    policy = str(brief["length_contract"].get("policy", "bounded"))
    depth_metrics = body_length_metrics(
        layout.artifact(generation, "report.md").read_text(encoding="utf-8"), unit
    )
    measurements: dict[str, object] = {
        "report_depth": {
            "unit": unit,
            "policy": policy,
            "raw_body": depth_metrics["raw_body"],
            "citation_markers": depth_metrics["citation_markers"],
            "net_body": depth_metrics["net_body"],
        }
    }
    max_metrics = _max_review_loop_metrics(layout.artifact(generation, "."))
    if max_metrics is not None:
        measurements["max_review_loop"] = max_metrics
    payload = _report_payload(
        checks, generation, measurements, str(brief["assurance_target"]),
        _review_outcomes(layout.artifact(generation, ".")),
    )
    staging = package_child(
        layout.root, f"work/.staging/g{generation:04d}/validation-{uuid.uuid4().hex}"
    )
    staging.mkdir(parents=True, exist_ok=False)
    staged_json = staging / "validation-report.json"
    staged_markdown = staging / "validation-report.md"
    atomic_write_json(staged_json, payload)
    atomic_write_text(staged_markdown, _report_markdown(payload))
    report_json = layout.artifact(generation, "validation/validation-report.json")
    report_markdown = layout.artifact(generation, "validation/validation-report.md")
    atomic_promote(staged_json, report_json)
    atomic_promote(staged_markdown, report_markdown)
    staging.rmdir()
    render_manifest = layout.artifact(generation, "validation/render-manifest.json")
    commit_stage_receipt(
        layout,
        generation=generation,
        stage=Stage.VALIDATION,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts={
            "artifacts/validation/render-manifest.json": sha256_file(render_manifest),
            "artifacts/report.md": sha256_file(layout.artifact(generation, "report.md")),
        },
        output_paths=[report_json, report_markdown],
        checks=[check.public() for check in checks],
    )
    current = package_child(layout.root, "current/validation")
    current.mkdir(parents=True, exist_ok=True)
    for source, destination in (
        (report_json, current / report_json.name),
        (report_markdown, current / report_markdown.name),
    ):
        if destination.exists():
            destination.unlink()
        atomic_copy_file(source, destination)


def validate_and_commit(run_dir: Path) -> tuple[list[Check], int]:
    layout = RunLayout(run_dir)
    generation = latest_generation(layout)
    if generation is None:
        return [Check(
            "generation", "error", "fail", "work/generations/", "run has no generation",
            "initialize a governed run", EXIT_STAGE,
        )], EXIT_STAGE
    package_hash = compute_skill_package_hash(ROOT)
    checks, exit_code = validate_governed_run(layout, generation, package_hash)
    if exit_code == 0:
        validation_receipt = layout.receipt(generation, Stage.VALIDATION)
        if validation_receipt.is_file():
            try:
                verify_receipt_chain(layout, generation, Stage.VALIDATION, package_hash)
            except ReceiptError as exc:
                add_check(
                    checks, "validation-receipt", [f"validation receipt verification failed: {exc}"],
                    "state/generations/*/receipts/70-validation.json",
                    "validation receipt recomputes",
                    "restore authoritative artifacts or create a new generation", EXIT_STAGE,
                )
                return checks, EXIT_STAGE
        else:
            commit_validation(layout, generation, package_hash, checks)
    return checks, exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    try:
        checks, exit_code = validate_and_commit(args.run_dir)
    except (ReceiptError, OutputPathError, FileExistsError) as exc:
        print(f"Validation stage failed: {exc}", file=sys.stderr)
        return EXIT_STAGE
    for check in checks:
        stream = sys.stderr if check.status == "fail" else sys.stdout
        print(f"[{check.status.upper()}] {check.check_id}: {check.message}", file=stream)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
