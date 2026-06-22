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
    validate_brief,
    validate_report_outline,
    validate_research_plan,
    validate_source_plan,
)
from scripts.export_report import markdown_sections, markdown_title
from scripts.harness_io import (
    atomic_copy_file,
    atomic_promote,
    atomic_write_json,
    atomic_write_text,
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
    "research/uncertainty-ledger.json",
    "validation/render-manifest.json",
}
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
    unexpected = sorted(files - RENDER_ARTIFACTS)
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


def _domain_checks(artifacts: Path, brief_path: Path) -> list[Check]:
    checks: list[Check] = []
    brief = load_json(brief_path)
    plan = load_json(artifacts / "research/research-plan.json")
    source_plan = load_json(artifacts / "research/source-plan.json")
    sources = load_jsonl(artifacts / "research/source-register.jsonl")
    manifests = load_jsonl(artifacts / "research/retrieval-manifest.jsonl")
    claims = load_jsonl(artifacts / "research/claim-evidence-ledger.jsonl")
    outline = load_json(artifacts / "research/report-outline.json")
    contradictions = load_json(artifacts / "research/contradiction-ledger.json")
    uncertainties = load_json(artifacts / "research/uncertainty-ledger.json")
    paragraph_map = load_jsonl(artifacts / "research/reviewed-paragraph-map.jsonl")
    peer_review = load_json(artifacts / "research/peer-review.json")
    report = (artifacts / "report.md").read_text(encoding="utf-8")

    claim_ids = {str(item.get("claim_id")) for item in claims}
    question_ids = {str(item.get("question_id")) for item in plan.get("questions", []) if isinstance(item, dict)}
    contract_errors = validate_brief(brief)
    contract_errors.extend(validate_research_plan(plan, brief, claim_ids))
    contract_errors.extend(validate_source_plan(source_plan))
    contract_errors.extend(validate_report_outline(outline, brief, question_ids, claim_ids))
    add_check(
        checks, "contracts", contract_errors, "inputs/brief.json; artifacts/research/*.json",
        "brief, plan, source plan, and outline contracts are valid", "repair contracts and restart from the responsible stage", EXIT_CONTRACT,
    )

    evidence_errors = validate_claim_closure(claims, sources, outline, manifests)
    evidence_errors.extend(_validate_contradictions(contradictions, claims))
    evidence_errors.extend(_validate_uncertainties(uncertainties))
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

    traceability_errors = validate_report_traceability(report, paragraph_map, claims, sources)
    claim_reviews = peer_review.get("claim_reviews", [])
    paragraph_reviews = peer_review.get("paragraph_reviews", [])
    if not isinstance(claim_reviews, list) or not isinstance(paragraph_reviews, list):
        traceability_errors.append("peer review must contain claim and paragraph review arrays")
    else:
        traceability_errors.extend(validate_review_set(report, claims, claim_reviews, paragraph_reviews))
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
