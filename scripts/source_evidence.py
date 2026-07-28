#!/usr/bin/env python3
"""Capture and validate inspectable retrieval evidence without network access."""
from __future__ import annotations

import ipaddress
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree

from pypdf import PdfReader

from scripts.contract_io import validate_retrieval_evidence as validate_retrieval_contract
from scripts.harness_io import sha256_bytes


SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Computes authoritative source hashes and provenance for the retrieval stage."

RESERVED_HOSTS = {"example.com", "example.org", "example.net", "localhost"}
RESERVED_SUFFIXES = (".example", ".internal", ".invalid", ".localhost", ".test")
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
SECONDARY_SOURCE_TYPES = {
    "blog", "community", "encyclopedia", "news", "search_result", "secondary_synthesis",
    "trade_press", "vendor_analysis",
}
TIER_A_SOURCE_TYPES = {
    "audited_filing", "dataset", "law", "official", "peer_reviewed_paper", "regulation",
    "standard", "user_provided_file",
}
ACADEMIC_SOURCE_TYPES = {
    "academic", "book", "peer_reviewed_paper", "secondary_synthesis",
}


class SourceEvidenceError(ValueError):
    """Raised when captured evidence cannot satisfy deterministic provenance checks."""


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def canonicalize_public_url(value: str) -> str:
    errors = validate_public_url(value)
    if errors:
        raise SourceEvidenceError("; ".join(errors))
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.port:
        host = f"{host}:{parsed.port}"
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_KEYS
    ]
    return urlunsplit((parsed.scheme.lower(), host, parsed.path or "/", urlencode(sorted(query)), ""))


def validate_public_url(value: str) -> list[str]:
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    errors: list[str] = []
    if parsed.scheme.lower() not in {"http", "https"} or not host:
        errors.append("URL must be absolute HTTP or HTTPS")
        return errors
    if parsed.username or parsed.password:
        errors.append("URL must not contain credentials")
    if host in RESERVED_HOSTS or host.endswith(RESERVED_SUFFIXES):
        errors.append("reserved or placeholder domain")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and not address.is_global:
        errors.append("private or reserved network address")
    return errors


def resolve_snapshot(cache_root: Path, relative: str) -> Path:
    root = cache_root.expanduser().resolve()
    if not root.is_dir():
        raise SourceEvidenceError(f"evidence cache does not exist: {root}")
    requested = Path(relative)
    if requested.is_absolute() or ".." in requested.parts or not relative:
        raise SourceEvidenceError("snapshot path must be relative to evidence cache")
    unresolved = root / requested
    resolved = unresolved.resolve(strict=False)
    if resolved == root or not resolved.is_relative_to(root):
        raise SourceEvidenceError("snapshot path escapes evidence cache")
    if unresolved.is_symlink():
        raise SourceEvidenceError("snapshot path cannot be a symlink")
    if not resolved.is_file():
        raise SourceEvidenceError(f"snapshot file is missing: {relative}")
    return resolved


def validate_audit_snapshot(record: dict[str, Any], cache_root: Path) -> list[str]:
    try:
        snapshot = resolve_snapshot(cache_root, str(record.get("raw_artifact", "")))
    except SourceEvidenceError as exc:
        return [str(exc)]
    actual = sha256_bytes(snapshot.read_bytes())
    if actual != record.get("snapshot_sha256"):
        return ["snapshot_sha256 does not match audit artifact"]
    return []


def validate_candidate_snapshots(record: dict[str, Any], cache_root: Path) -> list[str]:
    errors: list[str] = []
    outcomes = record.get("resolver_outcomes", [])
    if not isinstance(outcomes, list):
        return ["resolver_outcomes must be an array"]
    for outcome in outcomes:
        if not isinstance(outcome, dict) or outcome.get("status") == "skipped":
            continue
        snapshot_errors = validate_audit_snapshot(outcome, cache_root)
        errors.extend(snapshot_errors)
        if outcome.get("status") == "matched" and not snapshot_errors:
            errors.extend(_validate_matched_resolver_payload(outcome, cache_root))
    return _unique(errors)


def _normalized_identifier(value: object) -> str:
    text = str(value or "").strip().casefold()
    for prefix in (
        "https://doi.org/", "http://doi.org/", "doi:", "https://openalex.org/",
        "https://arxiv.org/abs/", "http://arxiv.org/abs/", "arxiv:",
    ):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text


def _resolver_payload_record(
    outcome: dict[str, Any], payload: dict[str, Any]
) -> dict[str, object] | None:
    resolver = str(outcome.get("resolver", "")).casefold().replace("-", "_")
    basis = str(outcome.get("query_basis", ""))
    if resolver == "crossref":
        if payload.get("status") != "ok" or not isinstance(payload.get("message"), dict):
            return None
        record = payload["message"]
        date = record.get("published") or record.get("published-print") or {}
        parts = date.get("date-parts", []) if isinstance(date, dict) else []
        authors = record.get("author", [])
        titles = record.get("title", [])
        return {
            "identifier": record.get("DOI"),
            "title": titles[0] if isinstance(titles, list) and titles else "",
            "authors": [
                " ".join(filter(None, (item.get("given"), item.get("family"))))
                for item in (authors if isinstance(authors, list) else []) if isinstance(item, dict)
            ],
            "year": parts[0][0] if parts and parts[0] else None,
        }
    if resolver == "openalex":
        if not str(payload.get("id", "")).startswith("https://openalex.org/"):
            return None
        return {
            "identifier": payload.get("doi") if basis == "doi" else payload.get("id"),
            "title": payload.get("title"),
            "authors": [
                item.get("author", {}).get("display_name", "")
                for item in (payload.get("authorships") or []) if isinstance(item, dict)
            ],
            "year": payload.get("publication_year"),
        }
    if resolver in {"semantic_scholar", "semanticscholar"}:
        if not payload.get("paperId") or not isinstance(payload.get("externalIds"), dict):
            return None
        keys = {"doi": "DOI", "pmid": "PubMed", "arxiv_id": "ArXiv"}
        return {
            "identifier": payload["externalIds"].get(keys.get(basis), payload.get("paperId")),
            "title": payload.get("title"),
            "authors": [item.get("name", "") for item in (payload.get("authors") or []) if isinstance(item, dict)],
            "year": payload.get("year"),
        }
    if resolver in {"pubmed", "ncbi_pubmed"}:
        result = payload.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("uids"), list):
            return None
        uid = str(result["uids"][0]) if result["uids"] else ""
        record = result.get(uid)
        if not isinstance(record, dict):
            return None
        year_match = re.search(r"\b(?:19|20)\d{2}\b", str(record.get("pubdate", "")))
        article_ids = record.get("articleids") or []
        identifier = uid
        if basis != "pmid":
            id_type = {"doi": "doi", "arxiv_id": "arxiv"}.get(basis)
            identifier = next((
                item.get("value") for item in article_ids
                if isinstance(item, dict) and item.get("idtype") == id_type
            ), None)
        return {
            "identifier": identifier,
            "title": record.get("title"),
            "authors": [item.get("name", "") for item in (record.get("authors") or []) if isinstance(item, dict)],
            "year": int(year_match.group()) if year_match else None,
        }
    return None


def _validate_matched_resolver_payload(
    outcome: dict[str, Any], cache_root: Path
) -> list[str]:
    snapshot = resolve_snapshot(cache_root, str(outcome.get("raw_artifact", "")))
    resolver = str(outcome.get("resolver", "")).casefold().replace("-", "_")
    observed: dict[str, object] | None
    if resolver in {"arxiv", "arxiv_api"}:
        try:
            root = ElementTree.fromstring(snapshot.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, ElementTree.ParseError):
            return ["matched arXiv resolver snapshot must be a parseable Atom response"]
        namespace = {"a": "http://www.w3.org/2005/Atom"}
        entry = root.find("a:entry", namespace)
        if entry is None:
            observed = None
        else:
            published = entry.findtext("a:published", default="", namespaces=namespace)
            observed = {
                "identifier": entry.findtext("a:id", default="", namespaces=namespace),
                "title": entry.findtext("a:title", default="", namespaces=namespace),
                "authors": [node.findtext("a:name", default="", namespaces=namespace) for node in entry.findall("a:author", namespace)],
                "year": int(published[:4]) if re.fullmatch(r"\d{4}", published[:4]) else None,
            }
    else:
        try:
            payload = json.loads(snapshot.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ["matched resolver snapshot must be a parseable provider JSON response"]
        observed = _resolver_payload_record(outcome, payload) if isinstance(payload, dict) else None
    if observed is None:
        return [
            f"matched {outcome.get('resolver')} resolver snapshot is not a recognized provider response"
        ]
    expected = _normalized_identifier(outcome.get("matched_identifier"))
    errors: list[str] = []
    if expected and _normalized_identifier(observed.get("identifier")) != expected:
        errors.append("matched resolver identifier is not present in the provider response")
    if _normalize_whitespace(str(observed.get("title") or "")).casefold() != _normalize_whitespace(
        str(outcome.get("returned_title") or "")
    ).casefold():
        errors.append("resolver returned_title does not match the provider response")
    if observed.get("year") != outcome.get("returned_year"):
        errors.append("resolver returned_year does not match the provider response")
    raw_authors = {_normalize_whitespace(str(item)).casefold() for item in observed.get("authors", [])}
    claimed_authors = {
        _normalize_whitespace(str(item)).casefold() for item in outcome.get("returned_authors", [])
    }
    if raw_authors != claimed_authors:
        errors.append("resolver returned_authors do not match the provider response")
    return errors


def normalized_snapshot_text(path: Path, content_type: str) -> str:
    media_type = content_type.partition(";")[0].strip().lower()
    if media_type == "application/pdf" or path.suffix.casefold() == ".pdf":
        try:
            text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        except Exception as exc:
            raise SourceEvidenceError(f"PDF snapshot cannot be read: {exc}") from exc
    else:
        try:
            decoded = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise SourceEvidenceError("snapshot must be UTF-8 text or a readable PDF") from exc
        if media_type in {"text/html", "application/xhtml+xml"}:
            parser = _VisibleTextParser()
            parser.feed(decoded)
            text = " ".join(parser.parts)
        else:
            text = decoded
    normalized = _normalize_whitespace(text)
    if not normalized:
        raise SourceEvidenceError("captured content is empty after normalization")
    return normalized


def _classification_errors(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    capture_level = record.get("capture_level")
    ceiling = record.get("evidence_strength_ceiling")
    source_type = str(record.get("source_type", ""))
    primary_class = record.get("primary_class")
    tier = record.get("reliability_tier")
    notes = str(record.get("reliability_notes", "")).strip()
    if capture_level == "search_snippet" and ceiling == "strong":
        errors.append("search snippet cannot be strong evidence")
    if capture_level == "search_snippet" and tier == "A":
        errors.append("search snippet cannot be Tier A")
    if source_type in SECONDARY_SOURCE_TYPES and primary_class == "primary":
        errors.append("secondary synthesis cannot be classified as primary")
    if tier == "A":
        if primary_class != "primary" or source_type not in TIER_A_SOURCE_TYPES:
            errors.append("Tier A requires a compatible primary source role")
        if not notes:
            errors.append("Tier A requires a concrete reliability basis")
    canonical_url = str(record.get("canonical_url") or "")
    host = urlsplit(canonical_url).hostname or ""
    if host.casefold().endswith("wikipedia.org"):
        if source_type != "encyclopedia":
            errors.append("Wikipedia sources must use source_type encyclopedia")
        if primary_class != "secondary":
            errors.append("Wikipedia sources must be classified as secondary")
        if tier == "A":
            errors.append("Wikipedia sources cannot be Tier A")
    return errors


def validate_retrieval_evidence(
    record: dict[str, Any], cache_root: Path
) -> list[str]:
    errors = validate_retrieval_contract(record)
    canonical_url = record.get("canonical_url")
    final_url = record.get("final_url")
    if isinstance(canonical_url, str):
        errors.extend(validate_public_url(canonical_url))
    if isinstance(final_url, str):
        errors.extend(validate_public_url(final_url))
    errors.extend(_classification_errors(record))
    try:
        snapshot = resolve_snapshot(cache_root, str(record.get("snapshot_ref", "")))
        normalized = normalized_snapshot_text(snapshot, str(record.get("content_type", "")))
    except SourceEvidenceError as exc:
        errors.append(str(exc))
        return _unique(errors)
    snapshot_hash = sha256_bytes(snapshot.read_bytes())
    normalized_hash = sha256_bytes(normalized.encode("utf-8"))
    excerpt = _normalize_whitespace(str(record.get("excerpt", "")))
    excerpt_hash = sha256_bytes(excerpt.encode("utf-8"))
    if snapshot_hash != record.get("snapshot_sha256"):
        errors.append("snapshot_sha256 does not match captured content")
    if normalized_hash != record.get("normalized_text_sha256"):
        errors.append("normalized_text_sha256 does not match captured content")
    if excerpt_hash != record.get("excerpt_sha256"):
        errors.append("excerpt_sha256 does not match excerpt")
    if excerpt and excerpt not in normalized:
        errors.append("excerpt is absent from captured content")
    return _unique(errors)


def capture_retrieval_evidence(
    record: dict[str, Any], cache_root: Path
) -> dict[str, object]:
    url = str(record.get("url", "")).strip()
    file_ref_value = record.get("file_ref")
    file_ref = str(file_ref_value).strip() if file_ref_value is not None else ""
    if bool(url) == bool(file_ref):
        raise SourceEvidenceError("exactly one of url or file_ref is required")
    canonical_url = canonicalize_public_url(url) if url else None
    final_url_value = str(record.get("final_url", url)).strip() if url else ""
    final_url = canonicalize_public_url(final_url_value) if url else None
    snapshot_ref = str(record.get("raw_artifact", "")).strip()
    snapshot = resolve_snapshot(cache_root, snapshot_ref)
    content_type = str(record.get("content_type", "")).strip()
    normalized = normalized_snapshot_text(snapshot, content_type)
    excerpt = _normalize_whitespace(str(record.get("content_excerpt", "")))
    captured: dict[str, object] = {
        "schema_version": "2.0",
        "source_id": str(record.get("source_id", "S001")),
        "candidate_id": str(record.get("candidate_id", "")),
        "search_run_ids": list(record.get("search_run_ids", [])),
        "query_id": str(record.get("query_id", "")),
        "canonical_url": canonical_url,
        "final_url": final_url,
        "file_ref": file_ref or None,
        "observed_status": record.get("observed_status") if url else None,
        "content_type": content_type,
        "retrieved_at": str(record.get("retrieved_at", "")),
        "adapter": str(record.get("adapter", "")),
        "adapter_run_id": str(record.get("adapter_run_id", "")),
        "capture_level": str(record.get("capture_level", "")),
        "evidence_strength_ceiling": str(record.get("evidence_strength_ceiling", "")),
        "snapshot_ref": snapshot_ref,
        "snapshot_sha256": sha256_bytes(snapshot.read_bytes()),
        "normalized_text_sha256": sha256_bytes(normalized.encode("utf-8")),
        "locator_type": str(record.get("locator_type", "text")),
        "locator": str(record.get("content_locator", "")),
        "excerpt": excerpt,
        "excerpt_sha256": sha256_bytes(excerpt.encode("utf-8")),
        "published_at": record.get("published_at"),
        "publication_date_status": str(record.get("publication_date_status", "")),
        "source_type": str(record.get("source_type", "")),
        "primary_class": str(record.get("primary_class", "")),
        "reliability_tier": str(record.get("reliability_tier", "")),
        "reliability_notes": str(record.get("reliability_notes", "")),
    }
    errors = validate_retrieval_evidence(captured, cache_root)
    if errors:
        raise SourceEvidenceError("; ".join(errors))
    return captured


def _unique(errors: list[str]) -> list[str]:
    return list(dict.fromkeys(errors))
