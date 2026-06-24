#!/usr/bin/env python3
"""Validate a governed STORM run and commit validation authority on success."""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contract_io import (
    ContractError,
    load_json,
    load_jsonl,
    validate_conflict_review_record,
    validate_finding_record,
    validate_brief,
    validate_report_outline,
    validate_research_plan,
    validate_tasklet_record,
    validate_source_plan,
)
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
from scripts.validate_evidence import compute_coverage, validate_claim_closure


SCRIPT_INTERFACE = "public-worker-cli"
SCRIPT_INTERFACE_REASON = "Offline governed validation and validation receipt commitment."
ROOT = Path(__file__).resolve().parents[1]
EXIT_CONTRACT = 4
EXIT_EVIDENCE = 5
EXIT_EXPORT = 6
EXIT_SAFETY = 7
EXIT_STAGE = 8

RENDER_ARTIFACTS = {
    "drafts/report-v1.md",
    "exports/report.html",
    "exports/report.pdf",
    "report.md",
    "research/citation-index.json",
    "research/claim-evidence-ledger.jsonl",
    "research/contradiction-ledger.json",
    "research/paragraph-map.jsonl",
    "research/peer-review.json",
    "research/peer-review.md",
    "research/report-outline.json",
    "research/research-plan.json",
    "research/retrieval-manifest.jsonl",
    "research/reviewed-paragraph-map.jsonl",
    "research/revision-map.json",
    "research/source-plan.json",
    "research/source-register.jsonl",
    "research/storm-tasklets.jsonl",
    "research/uncertainty-ledger.json",
    "validation/render-manifest.json",
}
OPTIONAL_ARTIFACTS = {
    "research/finding-coverage.json",
    "research/storm-findings-pool.jsonl",
    "research/storm-lens-perspectives.json",
    "research/storm-lens-conflicts.json",
    "research/storm-lens-outline.json",
    "research/storm-lens-red-team.json",
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


def _structural_checks(artifacts: Path, *, pdf_required: bool) -> tuple[list[Check], int]:
    checks: list[Check] = []
    files, unsafe = _files_under(artifacts)
    add_check(
        checks, "artifact-boundary", unsafe, "artifacts/",
        "artifact tree contains no symlinks", "replace symlinks with governed files", EXIT_SAFETY,
    )
    if unsafe:
        return checks, EXIT_SAFETY
    missing = sorted(RENDER_ARTIFACTS - files)
    unexpected = sorted(files - RENDER_ARTIFACTS - OPTIONAL_ARTIFACTS)
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
    fields = {"uncertainty_id", "claim_id", "description", "impact", "next_evidence"}
    errors: list[str] = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict) or set(record) != fields:
            errors.append(f"uncertainty {index} has invalid fields")
        elif not all(str(record.get(field, "")).strip() for field in ("uncertainty_id", "description", "impact", "next_evidence")):
            errors.append(f"uncertainty {index} has empty required fields")
    return errors


def _is_full_external_dossier(brief: dict[str, Any]) -> bool:
    return (
        brief.get("depth_level") == "full_dossier"
        and brief.get("source_policy") != "closed_corpus"
        and brief.get("retrieval_mode") != "closed_corpus"
    )


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


def _domain_checks(artifacts: Path, brief_path: Path) -> list[Check]:
    checks: list[Check] = []
    brief = load_json(brief_path)
    plan = load_json(artifacts / "research/research-plan.json")
    source_plan = load_json(artifacts / "research/source-plan.json")
    sources = load_jsonl(artifacts / "research/source-register.jsonl")
    manifests = load_jsonl(artifacts / "research/retrieval-manifest.jsonl")
    tasklets = load_jsonl(artifacts / "research/storm-tasklets.jsonl")
    findings_path = artifacts / "research/storm-findings-pool.jsonl"
    coverage_path = artifacts / "research/finding-coverage.json"
    findings = load_jsonl(findings_path) if findings_path.exists() else []
    claims = load_jsonl(artifacts / "research/claim-evidence-ledger.jsonl")
    outline = load_json(artifacts / "research/report-outline.json")
    contradictions = load_json(artifacts / "research/contradiction-ledger.json")
    uncertainties = load_json(artifacts / "research/uncertainty-ledger.json")
    finding_coverage = load_json(coverage_path) if coverage_path.exists() else {}
    paragraph_map = load_jsonl(artifacts / "research/reviewed-paragraph-map.jsonl")
    peer_review = load_json(artifacts / "research/peer-review.json")
    report = (artifacts / "report.md").read_text(encoding="utf-8")

    claim_ids = {str(item.get("claim_id")) for item in claims}
    question_ids = {str(item.get("question_id")) for item in plan.get("questions", []) if isinstance(item, dict)}
    contract_errors = validate_brief(brief)
    contract_errors.extend(validate_research_plan(plan, brief, claim_ids))
    contract_errors.extend(validate_source_plan(source_plan))
    contract_errors.extend(validate_report_outline(outline, brief, question_ids, claim_ids))
    contract_errors.extend(_validate_tasklets(tasklets, plan, source_plan))
    add_check(
        checks, "contracts", contract_errors, "inputs/brief.json; artifacts/research/*.json",
        "brief, plan, source plan, and outline contracts are valid", "repair contracts and restart from the responsible stage", EXIT_CONTRACT,
    )

    evidence_errors = validate_claim_closure(claims, sources, outline, manifests)
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
        "storm-lens-phase-order",
        _validate_storm_lens_traceability(
            artifacts, brief, plan, outline, claims, findings, contradictions
        ),
        "artifacts/research/storm-lens-*.json; receipts/",
        "STORM lens artifacts are phase-bound or advisory mode is explicit",
        "register lens artifacts at the required phase and rerun the dependent stage",
        EXIT_STAGE,
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
    add_check(
        checks, "report-traceability", traceability_errors,
        "artifacts/report.md; artifacts/research/reviewed-paragraph-map.jsonl; artifacts/research/peer-review.json",
        "every paragraph, citation, Claim, and independent review is closed",
        "repair mappings or reviews and rerun review", EXIT_EVIDENCE,
    )

    length_contract = brief["length_contract"]
    measured = body_length(report, str(length_contract["unit"]))
    length_errors = []
    if measured < int(length_contract["minimum"]) or measured > int(length_contract["maximum"]):
        length_errors.append(
            f"report body length {measured} {length_contract['unit']} is outside "
            f"{length_contract['minimum']}-{length_contract['maximum']}"
        )
    add_check(
        checks, "report-depth", length_errors, "artifacts/report.md",
        f"report body satisfies the evidence-led length contract ({measured} {length_contract['unit']})",
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


def validate_governed_run(
    layout: RunLayout, generation: int, package_hash: str
) -> tuple[list[Check], int]:
    artifacts = layout.artifact(generation, ".")
    brief_path = layout.generation_input(generation, "brief.json")
    try:
        brief = load_json(brief_path)
    except ContractError as exc:
        checks = []
        add_check(
            checks, "brief-json", [f"authoritative brief is not valid JSON: {exc}"],
            "inputs/brief.json", "authoritative brief parses", "create a new governed generation", EXIT_CONTRACT,
        )
        return checks, EXIT_CONTRACT
    pdf_required = brief.get("output_mode") == "full"
    checks, code = _structural_checks(artifacts, pdf_required=pdf_required)
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


def _report_payload(checks: list[Check], generation: int) -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "ok": True,
        "generation": generation,
        "validated_through": Stage.RENDER.value,
        "checks": [check.public() for check in checks],
        "summary": {
            "passed": sum(check.status == "pass" for check in checks),
            "warnings": sum(check.status == "warn" for check in checks),
            "failed": sum(check.status == "fail" for check in checks),
        },
    }


def _report_markdown(payload: dict[str, object]) -> str:
    lines = ["# Validation Report", "", "**Status:** PASS", ""]
    for raw in payload["checks"]:
        check = raw if isinstance(raw, dict) else {}
        lines.append(f"- [x] `{check.get('check_id', '')}` {check.get('message', '')} (`{check.get('path', '')}`)")
    summary = payload["summary"]
    lines.extend([
        "",
        f"Passed: {summary['passed']} | Warnings: {summary['warnings']} | Failed: {summary['failed']}",
    ])
    return "\n".join(lines) + "\n"


def commit_validation(
    layout: RunLayout,
    generation: int,
    package_hash: str,
    checks: list[Check],
) -> None:
    payload = _report_payload(checks, generation)
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
