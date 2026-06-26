#!/usr/bin/env python3
"""Generate public references and validate report-to-ledger traceability."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from scripts.contract_io import validate_paragraph_map_record, validate_semantic_review_record
from scripts.harness_io import canonical_json_sha256, sha256_bytes


SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Binds report paragraphs and public citations to governed Claims and sources."
CITATION_RE = re.compile(r"\[\^([a-z0-9][a-z0-9-]{1,80})\]")
REFERENCE_DEF_RE = re.compile(r"^\[\^([a-z0-9][a-z0-9-]{1,80})\]:\s*(.+)$")
HEADING_RE = re.compile(r"(?m)^#{2,6}\s+(.+?)\s*#*\s*$")
MAPPING_COMMENT_RE = re.compile(r"<!--\s*storm-map:(.*?)-->", re.IGNORECASE | re.DOTALL)
FENCE_RE = re.compile(r"(?ms)^```.*?^```\s*")
REFERENCE_SECTION_TITLES = {
    "references",
    "reference",
    "bibliography",
    "works cited",
    "sources",
    "source list",
    "source register",
    "reference list",
    "参考文献",
    "参考资料",
    "参考来源",
    "资料来源",
    "来源",
    "来源列表",
    "引用来源",
    "文献",
}
MAX_QUOTED_SHARE = 0.25
MAX_QUOTED_UNITS = {"characters": 1200, "words": 500}
REFERENCE_SECTION_COMPACT_TITLES = {
    re.sub(r"[\s:：/|_-]+", "", title.casefold())
    for title in REFERENCE_SECTION_TITLES
}


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


def _host_slug(value: str) -> str:
    host = urlsplit(value).hostname or ""
    labels = [part for part in host.casefold().split(".") if part and part != "www"]
    return _slug("-".join(labels[:2]), words=2)


def _short_source_hash(source: dict[str, Any]) -> str:
    seed = "|".join(
        str(source.get(field, ""))
        for field in ("author_or_org", "title", "canonical_url", "file_ref", "content_hash")
    )
    return sha256_bytes(seed.encode("utf-8"))[:6]


def citation_index(sources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    for source in sorted(sources, key=lambda item: str(item.get("source_id", ""))):
        published = source.get("published_at")
        retrieved = str(source.get("retrieved_at", ""))
        year = str(published)[:4] if published else retrieved[:4] or "undated"
        author_slug = _slug(str(source.get("author_or_org", "source")), words=2)
        if author_slug == "source":
            author_slug = _host_slug(str(source.get("canonical_url", "")))
        title_slug = _slug(str(source.get("title", "source")), words=3)
        if title_slug == "source":
            title_slug = _short_source_hash(source)
        base = "-".join((
            author_slug,
            year,
            title_slug,
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


def _heading_title(raw_title: str) -> str:
    title = re.sub(r"\s*\{#[^}]+\}\s*$", "", raw_title).strip()
    title = re.sub(r"^[\d.、)）]+\s*", "", title).strip()
    return title.strip(" :：")


def _is_reference_section_title(raw_title: str) -> bool:
    title = _heading_title(raw_title)
    normalized = re.sub(r"\s+", " ", title.casefold()).strip(" :：")
    compact = re.sub(r"[\s:：/|_-]+", "", normalized)
    return normalized in REFERENCE_SECTION_TITLES or compact in REFERENCE_SECTION_COMPACT_TITLES


def _reference_section_match(markdown: str) -> re.Match[str] | None:
    for match in HEADING_RE.finditer(markdown):
        if _is_reference_section_title(match.group(1)):
            return match
    return None


def _split_references(markdown: str) -> tuple[str, str]:
    match = _reference_section_match(markdown)
    if not match:
        return markdown.rstrip(), ""
    return markdown[: match.start()].rstrip(), markdown[match.end() :].strip()


def strip_mapping_comments(markdown: str) -> str:
    return MAPPING_COMMENT_RE.sub("", markdown)


def mapping_directives(markdown: str) -> list[dict[str, object]]:
    directives: list[dict[str, object]] = []
    for match in MAPPING_COMMENT_RE.finditer(markdown):
        fields: dict[str, object] = {}
        for part in re.split(r";|\n", match.group(1)):
            if not part.strip() or "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip().casefold().replace("-", "_")
            values = [item.strip() for item in re.split(r",|\s+", value.strip()) if item.strip()]
            if key in {"claim", "claims", "claim_ids"}:
                fields["claim_ids"] = values
            elif key in {"source", "sources", "source_ids"}:
                fields["source_ids"] = values
            elif key in {"citation", "citations", "citation_keys"}:
                fields["citation_keys"] = values
            elif key in {"type", "paragraph_type"}:
                fields["paragraph_type"] = values[0] if values else ""
        directives.append(fields)
    return directives


def citation_keys_in_body(markdown: str) -> list[str]:
    body, _ = _split_references(strip_mapping_comments(markdown))
    return list(dict.fromkeys(CITATION_RE.findall(body)))


def generate_references(draft: str, sources: list[dict[str, Any]]) -> str:
    body, _ = _split_references(strip_mapping_comments(draft))
    index = citation_index(sources)
    definitions = [reference_definition(key, index[key]) for key in citation_keys_in_body(body) if key in index]
    reference_body = "\n".join(definitions)
    return f"{body}\n\n## References\n\n{reference_body}\n"


def has_handwritten_references(markdown: str) -> bool:
    _, reference_body = _split_references(strip_mapping_comments(markdown))
    return bool(reference_body)


def extract_paragraphs(markdown: str) -> list[Paragraph]:
    body, _ = _split_references(strip_mapping_comments(markdown))
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
    return _unit_length(countable_body_text(report), unit)


def _strip_fences(markdown: str) -> str:
    return FENCE_RE.sub("", markdown)


def _blockquote_lines(markdown: str) -> list[str]:
    body, _ = _split_references(strip_mapping_comments(markdown))
    return [
        line.lstrip()[1:].strip()
        for line in _strip_fences(body).splitlines()
        if line.lstrip().startswith(">")
    ]


def countable_body_text(markdown: str) -> str:
    body, _ = _split_references(strip_mapping_comments(markdown))
    body = _strip_fences(body)
    lines = [line for line in body.splitlines() if not line.lstrip().startswith(">")]
    return "\n".join(lines)


def _unit_length(text: str, unit: str) -> int:
    if unit == "characters":
        return len(re.sub(r"\s+", "", text))
    return len(re.findall(r"\b[\w'-]+\b", text, flags=re.UNICODE))


def quoted_length(report: str, unit: str) -> int:
    return _unit_length("\n".join(_blockquote_lines(report)), unit)


def quote_limit_errors(report: str, unit: str) -> list[str]:
    quoted = quoted_length(report, unit)
    countable = body_length(report, unit)
    absolute = MAX_QUOTED_UNITS.get(unit, MAX_QUOTED_UNITS["words"])
    if quoted > absolute and quoted > max(1, int(countable * MAX_QUOTED_SHARE)):
        return [
            f"quoted block length {quoted} {unit} exceeds {MAX_QUOTED_SHARE:.0%} of countable body and absolute limit {absolute}"
        ]
    return []


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


def validate_review_set(
    report: str,
    claims: list[dict[str, Any]],
    claim_reviews: list[dict[str, Any]],
    paragraph_reviews: list[dict[str, Any]],
) -> list[str]:
    """Recompute independent semantic-review coverage and target bindings."""
    errors: list[str] = []
    all_reviews = [*claim_reviews, *paragraph_reviews]
    review_ids: set[str] = set()
    for review in all_reviews:
        review_id = str(review.get("review_id", ""))
        if review_id in review_ids:
            errors.append(f"duplicate semantic review ID {review_id}")
        review_ids.add(review_id)
        errors.extend(validate_semantic_review(review))
    reviews_by_claim = {
        str(review.get("target_id")): review
        for review in claim_reviews if review.get("target_kind") == "claim"
    }
    for claim in claims:
        if not claim.get("material"):
            continue
        claim_id = str(claim.get("claim_id"))
        review = reviews_by_claim.get(claim_id)
        if review is None:
            errors.append(f"material claim {claim_id} lacks entailment review")
            continue
        if review.get("target_sha256") != canonical_json_sha256(claim):
            errors.append(f"claim review hash mismatch: {claim_id}")
        if review.get("verdict") != "supported":
            errors.append(f"material review did not pass: {claim_id}")
    errors.extend(validate_review_bindings(report, paragraph_reviews))
    reviews_by_paragraph = {
        str(review.get("target_id")): review
        for review in paragraph_reviews if review.get("target_kind") == "paragraph"
    }
    for paragraph in extract_paragraphs(report):
        review = reviews_by_paragraph.get(paragraph.locator)
        if review is None:
            errors.append(f"report paragraph lacks assertion audit: {paragraph.locator}")
        elif review.get("verdict") != "supported":
            errors.append(f"material review did not pass: {paragraph.locator}")
    return list(dict.fromkeys(errors))
