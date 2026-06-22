#!/usr/bin/env python3
"""Generate public references and validate report-to-ledger traceability."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from scripts.contract_io import validate_paragraph_map_record, validate_semantic_review_record
from scripts.harness_io import sha256_bytes


SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Binds report paragraphs and public citations to governed Claims and sources."
CITATION_RE = re.compile(r"\[\^([a-z0-9][a-z0-9-]{1,80})\]")
REFERENCE_DEF_RE = re.compile(r"^\[\^([a-z0-9][a-z0-9-]{1,80})\]:\s*(.+)$")


@dataclass(frozen=True)
class Paragraph:
    index: int
    heading: str
    text: str
    sha256: str

    @property
    def locator(self) -> str:
        return f"paragraph:{self.index}"


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _slug(value: str, *, words: int = 4) -> str:
    parts = re.findall(r"[a-z0-9]+", value.casefold())[:words]
    return "-".join(parts) or "source"


def citation_index(sources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    for source in sorted(sources, key=lambda item: str(item.get("source_id", ""))):
        published = source.get("published_at")
        retrieved = str(source.get("retrieved_at", ""))
        year = str(published)[:4] if published else retrieved[:4] or "undated"
        base = "-".join((
            _slug(str(source.get("author_or_org", "source")), words=2),
            year,
            _slug(str(source.get("title", "source")), words=3),
        ))
        counts[base] = counts.get(base, 0) + 1
        key = base if counts[base] == 1 else f"{base}-{counts[base]}"
        result[key] = source
    return result


def reference_definition(key: str, source: dict[str, Any]) -> str:
    author = _normalized(str(source.get("author_or_org", "Unknown author")))
    title = _normalized(str(source.get("title", "Untitled source")))
    published = source.get("published_at") or "publication date unknown"
    location = source.get("canonical_url") or source.get("file_ref")
    retrieved = str(source.get("retrieved_at", ""))
    return f"[^{key}]: {author}. {title}. {published}. {location}. Retrieved {retrieved}."


def _split_references(markdown: str) -> tuple[str, str]:
    match = re.search(r"(?m)^## References\s*$", markdown)
    if not match:
        return markdown.rstrip(), ""
    return markdown[: match.start()].rstrip(), markdown[match.end() :].strip()


def citation_keys_in_body(markdown: str) -> list[str]:
    body, _ = _split_references(markdown)
    return list(dict.fromkeys(CITATION_RE.findall(body)))


def generate_references(draft: str, sources: list[dict[str, Any]]) -> str:
    body, _ = _split_references(draft)
    index = citation_index(sources)
    definitions = [reference_definition(key, index[key]) for key in citation_keys_in_body(body) if key in index]
    reference_body = "\n".join(definitions)
    return f"{body}\n\n## References\n\n{reference_body}\n"


def has_handwritten_references(markdown: str) -> bool:
    _, reference_body = _split_references(markdown)
    return bool(reference_body)


def extract_paragraphs(markdown: str) -> list[Paragraph]:
    body, _ = _split_references(markdown)
    paragraphs: list[Paragraph] = []
    heading = ""
    block: list[str] = []
    in_fence = False

    def flush() -> None:
        if not block:
            return
        text = _normalized("\n".join(block))
        block.clear()
        if not text or REFERENCE_DEF_RE.match(text):
            return
        index = len(paragraphs) + 1
        paragraphs.append(Paragraph(
            index=index,
            heading=heading,
            text=text,
            sha256=sha256_bytes(text.encode("utf-8")),
        ))

    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading_match = re.match(r"^#{1,6}\s+(.+)$", line)
        if heading_match:
            flush()
            heading = _normalized(heading_match.group(1))
            continue
        if not line.strip():
            flush()
            continue
        block.append(line)
    flush()
    return paragraphs


def validate_paragraph_record(record: dict[str, Any]) -> list[str]:
    errors = validate_paragraph_map_record(record)
    if record.get("paragraph_type") == "factual" and (
        not record.get("claim_ids") or not record.get("citation_keys")
    ):
        errors.append("factual paragraph requires claims and citations")
    return list(dict.fromkeys(errors))


def validate_paragraph_hashes(
    markdown: str, paragraph_map: list[dict[str, Any]]
) -> list[str]:
    paragraphs = {paragraph.locator: paragraph for paragraph in extract_paragraphs(markdown)}
    errors: list[str] = []
    seen: set[str] = set()
    for record in paragraph_map:
        locator = str(record.get("text_locator", ""))
        if locator in seen:
            errors.append(f"duplicate paragraph mapping: {locator}")
        seen.add(locator)
        paragraph = paragraphs.get(locator)
        if paragraph is None:
            errors.append(f"paragraph mapping has no report paragraph: {locator}")
        elif paragraph.sha256 != record.get("paragraph_sha256"):
            errors.append(f"paragraph hash mismatch: {locator}")
    for locator in paragraphs.keys() - seen:
        errors.append(f"report paragraph is unmapped: {locator}")
    return errors


def validate_report_traceability(
    report: str,
    paragraph_map: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    source_by_id = {str(source.get("source_id")): source for source in sources}
    claim_by_id = {str(claim.get("claim_id")): claim for claim in claims}
    index = citation_index(sources)
    source_id_by_key = {key: str(source.get("source_id")) for key, source in index.items()}
    body, references = _split_references(report)
    used_keys = citation_keys_in_body(body)
    definitions: dict[str, str] = {}
    for line in references.splitlines():
        if not line.strip():
            continue
        match = REFERENCE_DEF_RE.match(line.strip())
        if not match:
            errors.append("References contains non-generated content")
            continue
        definitions[match.group(1)] = line.strip()
    for key in used_keys:
        source = index.get(key)
        if source is None:
            errors.append(f"citation key {key} is absent from source register")
            continue
        expected = reference_definition(key, source)
        if definitions.get(key) != expected:
            errors.append(f"citation key {key} lacks its generated reference")
    for key in definitions:
        if key not in index:
            errors.append(f"citation key {key} is absent from source register")
        if key not in used_keys:
            errors.append(f"reference {key} is not used in report body")
    errors.extend(validate_paragraph_hashes(report, paragraph_map))
    mapping_by_locator = {str(record.get("text_locator")): record for record in paragraph_map}
    for paragraph in extract_paragraphs(report):
        record = mapping_by_locator.get(paragraph.locator)
        if record is None:
            continue
        errors.extend(f"{paragraph.locator}: {item}" for item in validate_paragraph_record(record))
        claim_ids = [str(item) for item in record.get("claim_ids", [])]
        source_ids = [str(item) for item in record.get("source_ids", [])]
        citation_keys = [str(item) for item in record.get("citation_keys", [])]
        for claim_id in claim_ids:
            claim = claim_by_id.get(claim_id)
            if claim is None:
                errors.append(f"{paragraph.locator} references unknown claim_id {claim_id}")
                continue
            allowed_sources = set(claim.get("supporting_source_ids", [])) | set(claim.get("contradicting_source_ids", []))
            for source_id in source_ids:
                if source_id not in allowed_sources:
                    errors.append(f"{paragraph.locator} source {source_id} does not support claim {claim_id}")
        for source_id in source_ids:
            if source_id not in source_by_id:
                errors.append(f"{paragraph.locator} references unknown source_id {source_id}")
        for key in citation_keys:
            source_id = source_id_by_key.get(key)
            if source_id is None:
                errors.append(f"citation key {key} is absent from source register")
            elif source_id not in source_ids:
                errors.append(f"{paragraph.locator} citation {key} is not mapped to its source")
            if key not in CITATION_RE.findall(paragraph.text):
                errors.append(f"{paragraph.locator} citation {key} is not attached to paragraph text")
    duplicate_hashes: set[str] = set()
    seen_hashes: set[str] = set()
    for paragraph in extract_paragraphs(report):
        if paragraph.sha256 in seen_hashes:
            duplicate_hashes.add(paragraph.sha256)
        seen_hashes.add(paragraph.sha256)
    if duplicate_hashes:
        errors.append("report contains repeated paragraphs")
    return list(dict.fromkeys(errors))


def body_length(report: str, unit: str) -> int:
    body, _ = _split_references(report)
    if unit == "characters":
        return len(re.sub(r"\s+", "", body))
    return len(re.findall(r"\b[\w'-]+\b", body, flags=re.UNICODE))


def validate_semantic_review(record: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys(validate_semantic_review_record(record)))


def validate_review_bindings(
    report: str, reviews: list[dict[str, Any]]
) -> list[str]:
    paragraphs = {paragraph.locator: paragraph for paragraph in extract_paragraphs(report)}
    errors: list[str] = []
    for review in reviews:
        errors.extend(validate_semantic_review(review))
        if review.get("target_kind") != "paragraph":
            continue
        target_id = str(review.get("target_id", ""))
        paragraph = paragraphs.get(target_id)
        if paragraph is None or paragraph.sha256 != review.get("target_sha256"):
            errors.append(f"reviewed paragraph hash mismatch: {target_id}")
    return list(dict.fromkeys(errors))
