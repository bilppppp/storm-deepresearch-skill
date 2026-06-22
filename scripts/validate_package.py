#!/usr/bin/env python3
"""Strictly validate a STORM DeepResearch output package."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    from .contract_io import ContractError, load_json, load_jsonl, validate_research_package
    from .output_paths import OutputPathError, package_child, resolve_package_dir
    from .validate_evidence import compute_coverage, validate_claim_closure
except ImportError:
    from contract_io import ContractError, load_json, load_jsonl, validate_research_package
    from output_paths import OutputPathError, package_child, resolve_package_dir
    from validate_evidence import compute_coverage, validate_claim_closure


EXIT_CONTRACT = 4
EXIT_EVIDENCE = 5
EXIT_EXPORT = 6
EXIT_SAFETY = 7

REQUIRED = (
    "brief.json",
    "research/research-plan.json",
    "research/source-register.jsonl",
    "research/source-register.md",
    "research/claim-evidence-ledger.jsonl",
    "research/evidence-map.md",
    "research/report-claim-map.json",
    "research/perspective-questions.md",
    "research/contradiction-ledger.json",
    "research/contradiction-map.md",
    "research/uncertainty-ledger.md",
    "research/peer-review.md",
    "report.md",
    "exports/report.html",
    "validation/render-manifest.json",
)
LOCAL_PATH_PATTERNS = (
    re.compile(r"/Users/[^\s<]+"),
    re.compile(r"/mnt/data/[^\s<]+"),
    re.compile(r"file:///[^\s<]+"),
    re.compile(r"[A-Za-z]:\\\\[^\s<]+"),
)
TEMPLATE_MARKER = re.compile(r"(?:\{\{|\{%|\{#)")
INTERNAL_ID = re.compile(r"\b[CS]\d{3}\b")
REFERENCE_HEADING = re.compile(r"^##\s+(?:References|参考资料|参考文献)\s*$", re.IGNORECASE | re.MULTILINE)


@dataclass
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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def markdown_title(text: str) -> str:
    match = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def markdown_sections(text: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE)]


def strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def html_title(text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    return strip_tags(match.group(1)) if match else ""


def html_sections(text: str) -> list[str]:
    return [strip_tags(value) for value in re.findall(r"<h2[^>]*>(.*?)</h2>", text, re.IGNORECASE | re.DOTALL)]


def report_body(text: str) -> str:
    reference = REFERENCE_HEADING.search(text)
    body = text[:reference.start()] if reference else text
    body = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
    body = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", body)
    body = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", body)
    body = re.sub(r"https?://\S+", " ", body)
    body = re.sub(r"^\s*\|?\s*:?-{3,}.*$", " ", body, flags=re.MULTILINE)
    body = re.sub(r"[#*_`>|]", " ", body)
    return body


def measure_report_units(text: str, unit: str) -> int:
    body = report_body(text)
    if unit == "words":
        return len(re.findall(r"\b[\w]+(?:[-'][\w]+)*\b", body, flags=re.UNICODE))
    return len(re.findall(r"\S", body, flags=re.UNICODE))


def research_utilization_errors(
    brief: dict[str, Any], plan: dict[str, Any], claims: list[dict[str, Any]], report_sections: list[str]
) -> list[str]:
    errors: list[str] = []
    outline = plan.get("report_outline", {}) if isinstance(plan.get("report_outline"), dict) else {}
    questions = plan.get("questions", []) if isinstance(plan.get("questions"), list) else []
    sections = outline.get("sections", []) if isinstance(outline.get("sections"), list) else []
    if plan.get("status") != "complete":
        errors.append("research plan must be complete before release")
    if outline.get("status") != "complete":
        errors.append("report_outline must be complete before release")
    if any(isinstance(question, dict) and question.get("status") == "planned" for question in questions):
        errors.append("planned perspective questions remain without a recorded disposition")

    thresholds = {
        "briefing": (1, 1, 1, 1),
        "standard_report": (3, 6, 4, 6),
        "full_dossier": (5, 10, 6, 12),
    }
    min_perspectives, min_questions, min_sections, min_claims = thresholds.get(
        str(brief.get("depth_level")), thresholds["standard_report"]
    )
    perspectives = {str(item).strip().casefold() for item in plan.get("perspectives", []) if str(item).strip()}
    material_claims = [claim for claim in claims if claim.get("material")]
    if len(perspectives) < min_perspectives:
        errors.append(f"depth requires at least {min_perspectives} researched perspectives")
    if len(questions) < min_questions:
        errors.append(f"depth requires at least {min_questions} perspective questions")
    if len(sections) < min_sections:
        errors.append(f"depth requires at least {min_sections} evidence-planned report sections")
    if len(material_claims) < min_claims:
        errors.append(f"depth requires at least {min_claims} material claims")

    outlined_claim_ids: set[str] = set()
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = str(section.get("title", "")).strip()
        if title and title not in report_sections:
            errors.append(f"outlined section is missing from report.md: {title}")
        if not section.get("question_ids"):
            errors.append(f"outline section {section.get('section_id', '')} has no STORM questions")
        if not section.get("claim_ids"):
            errors.append(f"outline section {section.get('section_id', '')} has no evidence-backed claims")
        outlined_claim_ids.update(str(item) for item in section.get("claim_ids", []))
    missing_material = sorted(
        str(claim.get("claim_id")) for claim in material_claims
        if str(claim.get("claim_id")) not in outlined_claim_ids
    )
    if missing_material:
        errors.append("material claims are absent from report_outline: " + ", ".join(missing_material))
    target_sum = sum(
        int(section.get("target_units", 0)) for section in sections
        if isinstance(section, dict) and isinstance(section.get("target_units"), int)
    )
    if sections and target_sum < int(outline.get("minimum", 0) or 0):
        errors.append("report_outline section budgets do not reach the minimum length contract")
    if sections and target_sum > int(outline.get("maximum", 0) or 0):
        errors.append("report_outline section budgets exceed the maximum length contract")
    return errors


def add_check(
    checks: list[Check], check_id: str, passed: bool, path: str, success: str, failure: str,
    repair: str, exit_code: int, severity: str = "error",
) -> None:
    checks.append(Check(
        check_id=check_id,
        severity="info" if passed else severity,
        status="pass" if passed else "fail",
        path=path,
        message=success if passed else failure,
        repair_command="" if passed else repair,
        exit_code=0 if passed else exit_code,
    ))


def write_reports(root: Path, checks: list[Check], ok: bool) -> None:
    validation = package_child(root, "validation")
    validation.mkdir(parents=True, exist_ok=True)
    summary = {
        "passed": sum(item.status == "pass" for item in checks),
        "warnings": sum(item.status == "warn" for item in checks),
        "failed": sum(item.status == "fail" for item in checks),
    }
    payload = {
        "schema_version": "1.0",
        "ok": ok,
        "package_state": "validated" if ok else "validation_failed",
        "checks": [item.public() for item in checks],
        "summary": summary,
    }
    (validation / "validation-report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = ["# Validation Report", "", f"**Status:** {'PASS' if ok else 'FAIL'}", ""]
    for item in checks:
        mark = "x" if item.status == "pass" else " "
        lines.append(f"- [{mark}] `{item.check_id}` {item.message} (`{item.path}`)")
        if item.repair_command:
            lines.append(f"  Repair: `{item.repair_command}`")
    lines.extend(["", f"Passed: {summary['passed']} | Warnings: {summary['warnings']} | Failed: {summary['failed']}"])
    (validation / "validation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate(root: Path) -> tuple[list[Check], int]:
    checks: list[Check] = []
    try:
        root = resolve_package_dir(root)
        boundary_paths = list(REQUIRED) + [
            "exports/report.pdf",
            "validation/validation-report.json",
            "validation/validation-report.md",
        ]
        for relative in boundary_paths:
            package_child(root, relative)
    except OutputPathError as exc:
        add_check(
            checks,
            "package-path-boundary",
            False,
            ".",
            "all package paths remain inside the resolved research package",
            str(exc),
            "replace escaping symlinks with real directories inside the research package",
            EXIT_SAFETY,
        )
        return checks, EXIT_SAFETY
    for relative in REQUIRED:
        path = root / relative
        exists = path.is_file()
        add_check(
            checks, f"file:{relative}", exists, relative, f"{relative} exists", f"required file is missing: {relative}",
            "python3 scripts/init_research_package.py --help", EXIT_CONTRACT if relative.startswith(("brief", "research/")) else EXIT_EXPORT,
        )

    brief: dict[str, Any] = {}
    plan: dict[str, Any] = {}
    sources: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    report_map: dict[str, Any] = {}
    try:
        brief = load_json(root / "brief.json")
        plan = load_json(root / "research" / "research-plan.json")
        sources = load_jsonl(root / "research" / "source-register.jsonl")
        claims = load_jsonl(root / "research" / "claim-evidence-ledger.jsonl")
        report_map = load_json(root / "research" / "report-claim-map.json")
        contract_errors = validate_research_package(root)
    except ContractError as exc:
        contract_errors = [str(exc)]
    relational_errors = [
        item for item in contract_errors
        if "unknown source_id" in item or "unknown claim_id" in item
    ]
    utilization_contract_errors = [item for item in contract_errors if "not used by report_outline" in item]
    contract_errors = [
        item for item in contract_errors
        if item not in relational_errors and item not in utilization_contract_errors
    ]
    add_check(
        checks, "contracts", not contract_errors, "brief.json; research/*.json*",
        "research contracts are valid", "; ".join(contract_errors),
        "python3 scripts/validate_contracts.py OUTPUT_DIR", EXIT_CONTRACT,
    )

    evidence_errors = relational_errors + utilization_contract_errors + (
        validate_claim_closure(claims, sources, report_map) if not contract_errors else []
    )
    material_claims = [claim for claim in claims if claim.get("material")]
    if not material_claims:
        evidence_errors.append("no material claims are registered")
    coverage = compute_coverage(claims)
    if coverage["material_fact_closure"] != 1.0:
        evidence_errors.append("material fact closure is below 100%")
    add_check(
        checks, "evidence-closure", not evidence_errors, "research/claim-evidence-ledger.jsonl",
        "material claims have closed evidence", "; ".join(evidence_errors),
        "python3 scripts/validate_evidence.py OUTPUT_DIR", EXIT_EVIDENCE,
    )

    report_path = root / "report.md"
    html_path = root / "exports" / "report.html"
    public_texts: list[tuple[str, str]] = []
    for relative, path in (("report.md", report_path), ("exports/report.html", html_path)):
        if path.is_file():
            public_texts.append((relative, path.read_text(encoding="utf-8", errors="replace")))
    local_leaks = [f"{relative}: {pattern.pattern}" for relative, text in public_texts for pattern in LOCAL_PATH_PATTERNS if pattern.search(text)]
    add_check(
        checks, "public-path-safety", not local_leaks, "report.md; exports/report.html",
        "public outputs contain no local path leak", "local path leak detected: " + ", ".join(local_leaks),
        "remove local filesystem paths from public outputs", EXIT_SAFETY,
    )
    exposed_ids = [relative for relative, text in public_texts if INTERNAL_ID.search(text)]
    add_check(
        checks, "public-id-safety", not exposed_ids, "report.md; exports/report.html",
        "public outputs do not expose internal claim/source IDs", "internal audit IDs leaked into: " + ", ".join(exposed_ids),
        "use research/report-claim-map.json instead of public audit IDs", EXIT_SAFETY,
    )
    template_leaks = [relative for relative, text in public_texts if TEMPLATE_MARKER.search(text)]
    add_check(
        checks, "template-resolution", not template_leaks, "report.md; exports/report.html",
        "no template markers remain", "template marker remains in: " + ", ".join(template_leaks),
        "rerun scripts/export_report.py after resolving template values", EXIT_EXPORT,
    )

    report_text = report_path.read_text(encoding="utf-8", errors="replace") if report_path.is_file() else ""
    html_text = html_path.read_text(encoding="utf-8", errors="replace") if html_path.is_file() else ""
    md_title = markdown_title(report_text)
    rendered_title = html_title(html_text)
    titles_match = bool(md_title) and md_title == rendered_title
    add_check(
        checks, "title-consistency", titles_match, "report.md; exports/report.html",
        "Markdown and HTML titles match", f"title mismatch: Markdown={md_title!r}, HTML={rendered_title!r}",
        "rerun scripts/export_report.py with the Markdown H1 as --title", EXIT_EXPORT,
    )
    md_sections = markdown_sections(report_text)
    rendered_sections = html_sections(html_text)
    utilization_errors = research_utilization_errors(brief, plan, claims, md_sections) if not contract_errors else []
    add_check(
        checks, "storm-research-utilization", not utilization_errors, "research/research-plan.json; report.md",
        "STORM questions, material claims, and section budgets are used by the report",
        "; ".join(utilization_errors),
        "complete question dispositions and map them into research-plan.report_outline", EXIT_EVIDENCE,
    )

    length_contract = brief.get("length_contract", {}) if isinstance(brief.get("length_contract"), dict) else {}
    length_unit = str(length_contract.get("unit", "characters"))
    report_units = measure_report_units(report_text, length_unit)
    minimum_units = int(length_contract.get("minimum", 0) or 0)
    maximum_units = int(length_contract.get("maximum", 0) or 0)
    length_errors: list[str] = []
    if report_units < minimum_units:
        length_errors.append(
            f"report body is shorter than the length contract: {report_units} {length_unit} < {minimum_units}"
        )
    if maximum_units and report_units > maximum_units:
        length_errors.append(
            f"report body exceeds the length contract: {report_units} {length_unit} > {maximum_units}"
        )
    add_check(
        checks, "report-depth", not length_errors, "brief.json; report.md",
        f"report body satisfies the evidence-led length contract ({report_units} {length_unit})",
        "; ".join(length_errors),
        "expand or tighten evidence-backed outline sections; do not pad with repetition", EXIT_EXPORT,
    )
    sections_match = bool(md_sections) and all(section in rendered_sections for section in md_sections)
    add_check(
        checks, "section-consistency", sections_match, "report.md; exports/report.html",
        "all Markdown sections appear in HTML", "HTML omits or changes Markdown sections",
        "rerun scripts/export_report.py from canonical report.md", EXIT_EXPORT,
    )
    references_present = "References" in md_sections and "References" in rendered_sections
    add_check(
        checks, "references-section", references_present, "report.md; exports/report.html",
        "references section appears in Markdown and HTML", "references section is missing",
        "add a References section backed by the source register and re-export", EXIT_EXPORT,
    )

    manifest: dict[str, Any] = {}
    try:
        manifest = load_json(root / "validation" / "render-manifest.json")
        manifest_error = ""
    except ContractError as exc:
        manifest_error = str(exc)
    hash_errors = []
    if manifest_error:
        hash_errors.append(manifest_error)
    else:
        if report_path.is_file() and manifest.get("report_md_sha256") != digest(report_path):
            hash_errors.append("Markdown fingerprint mismatch")
        if html_path.is_file() and manifest.get("report_html_sha256") != digest(html_path):
            hash_errors.append("HTML fingerprint mismatch")
        if manifest.get("title") != md_title:
            hash_errors.append("manifest title mismatch")
        manifest_sections = [item.get("title") for item in manifest.get("section_fingerprints", []) if isinstance(item, dict)]
        if manifest_sections != md_sections:
            hash_errors.append("section fingerprint manifest mismatch")
    add_check(
        checks, "render-manifest", not hash_errors, "validation/render-manifest.json",
        "render fingerprints match current files", "; ".join(hash_errors),
        "rerun scripts/export_report.py from canonical report.md", EXIT_EXPORT,
    )

    pdf_path = root / "exports" / "report.pdf"
    pdf_required = brief.get("output_mode", "full") == "full"
    pdf_errors: list[str] = []
    if pdf_required and not pdf_path.is_file():
        pdf_errors.append("required PDF is missing")
    if pdf_path.is_file():
        raw = pdf_path.read_bytes()
        if not raw.startswith(b"%PDF-") or len(raw) < 1000:
            pdf_errors.append("PDF signature or size is invalid")
        if manifest.get("report_pdf_sha256") != digest(pdf_path):
            pdf_errors.append("PDF fingerprint mismatch")
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(pdf_path))
            extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
            if not reader.pages:
                pdf_errors.append("PDF has no pages")
            if md_title not in extracted or "References" not in extracted:
                pdf_errors.append("PDF does not contain the report title and references text")
        except Exception as exc:
            pdf_errors.append(f"PDF text verification failed: {exc}")
    add_check(
        checks, "pdf-integrity", not pdf_errors, "exports/report.pdf",
        "PDF requirement and content checks pass" if pdf_required else "PDF is optional in reduced mode",
        "; ".join(pdf_errors),
        "rerun scripts/export_report.py with --require-pdf", EXIT_EXPORT,
    )

    failed_codes = [item.exit_code for item in checks if item.status == "fail"]
    return checks, max(failed_codes, default=0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    try:
        root = resolve_package_dir(args.output_dir)
    except OutputPathError as exc:
        print(f"Unsafe research package path: {exc}", file=sys.stderr)
        return EXIT_SAFETY
    checks, exit_code = validate(root)
    try:
        write_reports(root, checks, exit_code == 0)
    except OutputPathError as exc:
        print(f"Unsafe research package path: {exc}", file=sys.stderr)
        return EXIT_SAFETY
    for item in checks:
        stream = sys.stderr if item.status == "fail" else sys.stdout
        print(f"[{item.status.upper()}] {item.check_id}: {item.message}", file=stream)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
