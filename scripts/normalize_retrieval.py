#!/usr/bin/env python3
"""Normalize captured adapter records without committing authoritative run state."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contract_io import validate_retrieval_input_record, validate_source_record
from scripts.harness_io import atomic_write_text, canonical_json_bytes
from scripts.source_evidence import (
    ACADEMIC_SOURCE_TYPES,
    SourceEvidenceError,
    canonicalize_public_url,
    capture_retrieval_evidence,
    resolve_snapshot,
    validate_audit_snapshot,
    validate_candidate_snapshots,
    validate_search_request_snapshot,
)


SCRIPT_INTERFACE = "internal-worker-cli"
SCRIPT_INTERFACE_REASON = "Produces validated staging records; only storm_research may commit receipts."
ALLOWED_MODES = {"host", "provider", "closed_corpus"}
RESULT_COLLECTION_KEYS = ("results", "items", "records", "works", "studies", "data")


def canonicalize_url(value: str) -> str:
    return canonicalize_public_url(value)


def source_identity(record: dict[str, Any]) -> str:
    identity = record.get("canonical_url") or record.get("file_ref")
    if not isinstance(identity, str) or not identity:
        raise ValueError("source record has no canonical URL or file reference")
    return identity


def derive_bibliographic_status(candidate: dict[str, object]) -> str:
    outcomes = [
        item for item in candidate.get("resolver_outcomes", [])
        if isinstance(item, dict)
    ]
    if any(
        item.get("status") == "matched" and item.get("metadata_match") is False
        for item in outcomes
    ):
        return "conflicted"
    identifier_match = any(
        item.get("status") == "matched"
        and item.get("metadata_match") is True
        and item.get("query_basis") in {"doi", "pmid", "arxiv_id"}
        for item in outcomes
    )
    metadata_matches = {
        str(item.get("resolver"))
        for item in outcomes
        if item.get("status") == "matched" and item.get("metadata_match") is True
    }
    if identifier_match or len(metadata_matches) >= 2:
        return "verified"
    return "unverified"


def validate_version_families(candidates: list[dict[str, object]]) -> list[str]:
    families: dict[str, list[dict[str, object]]] = {}
    for candidate in candidates:
        family_id = candidate.get("version_family_id")
        if family_id:
            families.setdefault(str(family_id), []).append(candidate)
    errors: list[str] = []
    identities: dict[str, set[str]] = {}
    metadata_identities: dict[str, set[str]] = {}
    for candidate in candidates:
        family_id = str(candidate.get("version_family_id") or "")
        identifiers = candidate.get("identifiers")
        if isinstance(identifiers, dict):
            for kind, value in identifiers.items():
                if value:
                    identities.setdefault(
                        f"{kind}:{str(value).strip().casefold()}", set()
                    ).add(family_id)
        title = re.sub(r"[^a-z0-9]+", "", str(candidate.get("title", "")).casefold())
        authors = candidate.get("authors")
        first_author = str(authors[0]).casefold() if isinstance(authors, list) and authors else ""
        first_author = re.sub(r"[^a-z0-9]+", "", first_author)
        year = candidate.get("year")
        if title and first_author and year:
            metadata_identities.setdefault(
                f"{title}|{first_author}|{year}", set()
            ).add(family_id)
    for identity, family_ids in sorted(identities.items()):
        if len(family_ids) > 1:
            errors.append(
                f"bibliographic identity {identity} spans multiple version families"
            )
    for identity, family_ids in sorted(metadata_identities.items()):
        if len(family_ids) > 1:
            errors.append(
                "exact title/author/year identity spans multiple version families: "
                + identity
            )
    for family_id, members in families.items():
        if len(members) < 2:
            continue
        if any(item.get("relationship_basis") == "unresolved" for item in members):
            errors.append(f"{family_id} contains an unresolved version relationship")
        included = [item for item in members if item.get("disposition") == "include"]
        canonical = [item for item in included if item.get("canonical_version") is True]
        if included and len(canonical) != 1:
            errors.append(f"{family_id} must select exactly one included canonical version")
    return errors


def independent_source_identity(source: dict[str, object]) -> str:
    bibliographic = source.get("bibliographic")
    if isinstance(bibliographic, dict) and bibliographic.get("version_family_id"):
        return f"family:{bibliographic['version_family_id']}"
    return f"source:{source_identity(source)}"


def _surface_label(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")


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


def _search_surface_keys(search_run: dict[str, object]) -> set[str]:
    keys: set[str] = set()
    for field in ("surface", "surface_class", "pass_kind"):
        value = search_run.get(field)
        label = _surface_label(value)
        if label:
            keys.add(label)
        bucket = _surface_bucket(value)
        if bucket:
            keys.add(bucket)
    return keys


def _required_surface_is_satisfied(required: object, actual_keys: set[str]) -> bool:
    label = _surface_label(required)
    if label and label in actual_keys:
        return True
    bucket = _surface_bucket(required)
    if bucket and bucket in actual_keys:
        return True
    if bucket and (
        label in {
            "scholarly_index",
            "academic",
            "literature_database",
            "publisher_or_registry",
            "publisher_or_full_text",
            "official_registry",
            "official_or_registry",
            "secondary_synthesis",
            "counterevidence",
        }
        or "_or_" in label
    ):
        return bucket in actual_keys
    return False


def _resolver_label(value: object) -> str:
    return _surface_label(value)


def _native_resolver_matches(identifier_kind: str, resolver: object) -> bool:
    label = _resolver_label(resolver)
    markers = {
        "doi": ("crossref", "datacite", "doi"),
        "pmid": ("pubmed", "ncbi", "europe_pmc", "europepmc"),
        "arxiv_id": ("arxiv",),
        "openalex_id": ("openalex",),
        "semantic_scholar_id": ("semantic_scholar", "semanticscholar", "s2"),
    }
    return any(marker in label for marker in markers.get(identifier_kind, ()))


def _result_rows(payload: object) -> list[object] | None:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return None
    for key in RESULT_COLLECTION_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    hits = payload.get("hits")
    if isinstance(hits, list):
        return hits
    if isinstance(hits, dict) and isinstance(hits.get("hits"), list):
        return hits["hits"]
    return None


def _candidate_public_identity_markers(candidate: dict[str, object]) -> list[str]:
    markers: list[str] = []
    for field in ("title", "url"):
        value = candidate.get(field)
        if isinstance(value, str) and value.strip():
            markers.append(value.strip())
    identifiers = candidate.get("identifiers")
    if isinstance(identifiers, dict):
        for value in identifiers.values():
            if isinstance(value, str) and value.strip():
                markers.append(value.strip())
    return list(dict.fromkeys(markers))


def validate_captured_retrieval_artifacts(
    audit: list[dict[str, object]], cache_root: Path
) -> list[str]:
    """Reject self-attested search and resolver files in captured-host runs."""
    errors: list[str] = []
    candidates_by_run: dict[str, list[dict[str, object]]] = {}
    for candidate in audit:
        if candidate.get("record_kind") != "candidate":
            continue
        for search_run_id in candidate.get("search_run_ids", []):
            candidates_by_run.setdefault(str(search_run_id), []).append(candidate)
    for record in audit:
        kind = record.get("record_kind")
        if kind == "search_run" and record.get("execution_status") in {
            "completed", "zero_results",
        }:
            search_run_id = str(record.get("search_run_id", ""))
            try:
                path = resolve_snapshot(cache_root, str(record.get("raw_artifact", "")))
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (SourceEvidenceError, UnicodeDecodeError, json.JSONDecodeError):
                errors.append(
                    f"search run {search_run_id} response must be structured JSON with inspectable result rows"
                )
                continue
            rows = _result_rows(payload)
            if rows is None:
                errors.append(
                    f"search run {search_run_id} response must be structured JSON with inspectable result rows"
                )
                continue
            if len(rows) != record.get("result_count"):
                errors.append(
                    f"search run {search_run_id} result_count does not match captured result rows"
                )
            screened = candidates_by_run.get(search_run_id, [])
            if len(screened) != len(rows):
                errors.append(
                    f"search run {search_run_id} returned {len(rows)} rows but only "
                    f"{len(screened)} candidate records are screened"
                )
            raw_text = json.dumps(payload, ensure_ascii=False).casefold()
            for candidate in screened:
                candidate_id = str(candidate.get("candidate_id", ""))
                markers = _candidate_public_identity_markers(candidate)
                if not markers or not any(
                    marker.casefold() in raw_text for marker in markers
                ):
                    errors.append(
                        f"search run {search_run_id} raw results do not expose a public identity "
                        f"for candidate {candidate_id}"
                    )
        elif kind == "candidate":
            candidate_id = str(record.get("candidate_id", ""))
            for outcome in record.get("resolver_outcomes", []):
                if not isinstance(outcome, dict) or outcome.get("status") != "matched":
                    continue
                resolver = str(outcome.get("resolver", ""))
                matched_identifier = outcome.get("matched_identifier")
                if not isinstance(matched_identifier, str) or not matched_identifier.strip():
                    errors.append(
                        f"candidate {candidate_id} resolver {resolver} matched without a returned identifier"
                    )
                    continue
                try:
                    path = resolve_snapshot(cache_root, str(outcome.get("raw_artifact", "")))
                    raw_text = path.read_text(encoding="utf-8")
                    json.loads(raw_text)
                except (SourceEvidenceError, UnicodeDecodeError, json.JSONDecodeError):
                    errors.append(
                        f"candidate {candidate_id} resolver {resolver} raw response must be structured JSON"
                    )
                    continue
                if matched_identifier.casefold() not in raw_text.casefold():
                    errors.append(
                        f"candidate {candidate_id} resolver {resolver} raw response does not contain "
                        f"matched_identifier {matched_identifier}"
                    )
                query_basis = outcome.get("query_basis")
                if query_basis == "openalex_id" and not re.fullmatch(
                    r"W[1-9][0-9]*", matched_identifier
                ):
                    errors.append(
                        f"candidate {candidate_id} resolver {resolver} uses an invalid OpenAlex work identifier"
                    )
                if query_basis == "semantic_scholar_id" and not (
                    re.fullmatch(r"[0-9a-fA-F]{40}", matched_identifier)
                    or re.fullmatch(r"CorpusId:[1-9][0-9]*", matched_identifier)
                ):
                    errors.append(
                        f"candidate {candidate_id} resolver {resolver} uses an invalid Semantic Scholar paper identifier"
                    )
    return list(dict.fromkeys(errors))


def validate_retrieval_audit(
    audit: list[dict[str, object]],
    manifests: list[dict[str, object]],
    sources: list[dict[str, object]],
    source_plan: dict[str, object],
    brief: dict[str, object],
) -> list[str]:
    search_runs = {
        str(row.get("search_run_id")): row
        for row in audit
        if row.get("record_kind") == "search_run"
    }
    candidates = {
        str(row.get("candidate_id")): row
        for row in audit
        if row.get("record_kind") == "candidate"
    }
    search_waves = {
        str(row.get("wave_id")): row
        for row in audit
        if row.get("record_kind") == "search_wave"
    }
    gap_assessments = [
        row for row in audit if row.get("record_kind") == "gap_assessment"
    ]
    errors: list[str] = []
    source_ids_by_candidate: dict[str, set[str]] = {}
    for manifest in manifests:
        source_ids_by_candidate.setdefault(str(manifest.get("candidate_id")), set()).add(
            str(manifest.get("source_id"))
        )
    for wave_id, wave in search_waves.items():
        expected_sources = {
            source_id
            for candidate_id in wave.get("new_candidate_ids", [])
            for source_id in source_ids_by_candidate.get(str(candidate_id), set())
        }
        submitted_sources = {str(item) for item in wave.get("new_source_ids", [])}
        if submitted_sources != expected_sources:
            errors.append(f"search wave {wave_id} new_source_ids do not match captured candidates")
    response_uses: dict[tuple[str, str], str] = {}
    for search_run_id, search_run in search_runs.items():
        response_identity = (
            str(search_run.get("raw_artifact", "")),
            str(search_run.get("snapshot_sha256", "")),
        )
        request_identity = str(search_run.get("request_sha256", ""))
        previous = response_uses.get(response_identity)
        if previous is not None and previous != request_identity:
            errors.append(
                "search response snapshot is reused across different executed queries: "
                f"{search_run_id}"
            )
        response_uses[response_identity] = request_identity
    seen_assessed_gaps: set[str] = set()
    for assessment in gap_assessments:
        assessment_id = str(assessment.get("assessment_id", ""))
        gap_id = str(assessment.get("gap_id", ""))
        if gap_id in seen_assessed_gaps:
            errors.append(f"gap {gap_id} has multiple terminal assessments")
        seen_assessed_gaps.add(gap_id)
        runs = [
            search_runs.get(str(run_id))
            for run_id in assessment.get("supporting_search_run_ids", [])
        ]
        waves = [
            search_waves.get(str(wave_id))
            for wave_id in assessment.get("supporting_wave_ids", [])
        ]
        if any(item is None for item in runs) or any(item is None for item in waves):
            errors.append(f"gap assessment {assessment_id} has unresolved references")
            continue
        if any(str(item.get("gap_id")) != gap_id for item in waves if isinstance(item, dict)):
            errors.append(f"gap assessment {assessment_id} mixes search waves from another gap")
        terminal = assessment.get("terminal_state")
        screened_ids = {str(item) for item in assessment.get("screened_candidate_ids", [])}
        linked_candidates = {
            candidate_id
            for candidate_id, candidate in candidates.items()
            if set(str(item) for item in candidate.get("search_run_ids", []))
            & {str(item) for item in assessment.get("supporting_search_run_ids", [])}
        }
        raw_count = sum(_gap_raw_result_count(item) for item in runs if isinstance(item, dict))
        if assessment.get("raw_result_count") != raw_count:
            errors.append(f"gap assessment {assessment_id} raw result count does not recompute")
        if assessment.get("deduplicated_candidate_count") != len(screened_ids):
            errors.append(f"gap assessment {assessment_id} deduplicated count does not recompute")
        if screened_ids != linked_candidates:
            errors.append(f"gap assessment {assessment_id} does not screen every returned candidate")
        if terminal == "saturated" and len(waves) < 2:
            errors.append(f"gap assessment {assessment_id} saturation requires two search waves")
        if terminal == "saturated" and len(waves) >= 2:
            supporting_run_sets = [
                {str(item) for item in wave.get("search_run_ids", [])}
                for wave in waves
                if isinstance(wave, dict)
            ]
            reused_runs = set().union(*supporting_run_sets[:-1]) & supporting_run_sets[-1]
            if reused_runs:
                errors.append(
                    f"gap assessment {assessment_id} saturation waves must use disjoint search runs"
                )
            sequential = True
            previous_wave_time: datetime | None = None
            for wave in waves:
                if not isinstance(wave, dict):
                    sequential = False
                    break
                try:
                    wave_time = datetime.fromisoformat(
                        str(wave.get("created_at", "")).replace("Z", "+00:00")
                    )
                except ValueError:
                    sequential = False
                    break
                wave_runs = [
                    search_runs.get(str(run_id))
                    for run_id in wave.get("search_run_ids", [])
                ]
                if not wave_runs or any(
                    not isinstance(run, dict) or run.get("pass_kind") != "gap_fill"
                    for run in wave_runs
                ):
                    sequential = False
                    break
                try:
                    run_times = [
                        datetime.fromisoformat(
                            str(run.get("searched_at", "")).replace("Z", "+00:00")
                        )
                        for run in wave_runs if isinstance(run, dict)
                    ]
                except ValueError:
                    sequential = False
                    break
                if (
                    not run_times
                    or max(run_times) > wave_time
                    or (previous_wave_time is not None and min(run_times) <= previous_wave_time)
                ):
                    sequential = False
                    break
                previous_wave_time = wave_time
            if not sequential:
                errors.append(
                    f"gap assessment {assessment_id} saturation requires sequential gap_fill waves"
                )
        if terminal == "bounded_corpus_exhausted":
            if any(item.get("execution_status") not in {"completed", "zero_results"} for item in runs if isinstance(item, dict)):
                errors.append(f"gap assessment {assessment_id} bounded corpus has incomplete search runs")
            if any(candidates[item].get("disposition") == "needs_review" for item in screened_ids):
                errors.append(f"gap assessment {assessment_id} leaves candidates in needs_review")
            total_windows = assessment.get("total_result_windows")
            retrieved_windows = assessment.get("result_windows_retrieved")
            if (
                assessment.get("enumeration_complete") is not True
                or not isinstance(total_windows, int)
                or isinstance(total_windows, bool)
                or total_windows < 1
                or not isinstance(retrieved_windows, int)
                or isinstance(retrieved_windows, bool)
                or retrieved_windows != total_windows
            ):
                errors.append(
                    f"gap assessment {assessment_id} bounded corpus requires complete result-window enumeration"
                )
            access_limitations = assessment.get("access_limitations")
            if not isinstance(access_limitations, list) or not all(
                isinstance(item, str) for item in access_limitations
            ):
                errors.append(
                    f"gap assessment {assessment_id} bounded corpus requires access_limitations disclosure"
                )
        if terminal == "access_limited_uncertainty":
            if not assessment.get("uncertainty_id"):
                errors.append(f"gap assessment {assessment_id} access limit requires uncertainty_id")
            if not any(item.get("execution_status") == "unreachable" for item in runs if isinstance(item, dict)):
                errors.append(f"gap assessment {assessment_id} lacks an unreachable search run")
    external_full = (
        brief.get("depth_level") == "full_dossier"
        and brief.get("source_policy") != "closed_corpus"
        and brief.get("retrieval_mode") != "closed_corpus"
    )
    completed_statuses = {"completed", "zero_results"}
    if external_full:
        baseline = [
            row for row in search_runs.values()
            if row.get("pass_kind") == "baseline"
            and row.get("execution_status") in completed_statuses
            and row.get("surface_class") == "scholarly_index"
        ]
        if not baseline:
            errors.append("full_dossier requires a completed academic baseline")
        if len({str(row.get("surface")) for row in baseline}) < 2:
            errors.append("full_dossier requires two independent academic discovery surfaces")

        runs_by_query: dict[str, list[dict[str, object]]] = {}
        for row in search_runs.values():
            runs_by_query.setdefault(str(row.get("query_id")), []).append(row)
        for question in source_plan.get("questions", []):
            if not isinstance(question, dict):
                continue
            requirements = question.get("search_requirements")
            if not isinstance(requirements, dict):
                continue
            query_id = str(question.get("query_id"))
            query_runs = [
                row for row in runs_by_query.get(query_id, [])
                if row.get("execution_status") in completed_statuses
            ]
            actual_surface_keys: set[str] = set()
            for row in query_runs:
                actual_surface_keys.update(_search_surface_keys(row))
            missing_surfaces = [
                str(surface)
                for surface in requirements.get("required_surfaces", [])
                if not _required_surface_is_satisfied(surface, actual_surface_keys)
            ]
            if missing_surfaces:
                errors.append(
                    f"retrieval evidence for {query_id} lacks required source-plan surfaces: "
                    + ", ".join(missing_surfaces)
                )
            if not requirements.get("academic_required"):
                continue
            if not any(
                row.get("surface_class") in {"scholarly_index", "literature_database"}
                and row.get("execution_status") in completed_statuses
                for row in query_runs
            ):
                errors.append(f"academic-required query {query_id} lacks an academic search run")

        excluded_types = {"community", "encyclopedia", "search_result", "user_provided_file"}
        independent = {
            independent_source_identity(source)
            for source in sources
            if source.get("source_type") not in excluded_types
            and str(source.get("canonical_url") or "").startswith(("http://", "https://"))
        }
        if len(independent) < 6:
            errors.append(
                "full_dossier independent source depth requires at least 6 "
                "non-user, non-encyclopedia external sources"
            )
        dispositions = {
            str(candidate.get("disposition"))
            for candidate in candidates.values()
        }
        if candidates and dispositions == {"include"}:
            errors.append(
                "full_dossier candidate screening cannot be all include; record exclude or needs_review candidates with reasons"
            )

        if brief.get("research_profile") == "maximal_full_dossier":
            source_by_id = {
                str(source.get("source_id")): source for source in sources
            }
            academic_candidate_ids = {
                str(manifest.get("candidate_id"))
                for manifest in manifests
                if source_by_id.get(str(manifest.get("source_id")), {}).get("source_type")
                in ACADEMIC_SOURCE_TYPES
            }
            for candidate_id in sorted(academic_candidate_ids):
                candidate = candidates.get(candidate_id)
                if candidate is None or candidate.get("disposition") != "include":
                    continue
                matched = [
                    outcome for outcome in candidate.get("resolver_outcomes", [])
                    if isinstance(outcome, dict)
                    and outcome.get("status") == "matched"
                    and outcome.get("metadata_match") is True
                ]
                resolvers = {_resolver_label(outcome.get("resolver")) for outcome in matched}
                if len(resolvers) < 2:
                    errors.append(
                        f"maximal academic candidate {candidate_id} requires at least two matched independent resolvers"
                    )
                if not any(
                    any(marker in resolver for marker in (
                        "openalex", "semantic_scholar", "semanticscholar"
                    ))
                    for resolver in resolvers
                ):
                    errors.append(
                        f"maximal academic candidate {candidate_id} requires OpenAlex or Semantic Scholar cross-index resolution"
                    )
                identifiers = candidate.get("identifiers")
                if isinstance(identifiers, dict):
                    for kind, value in identifiers.items():
                        if value is None:
                            continue
                        if not any(
                            outcome.get("query_basis") == kind
                            and _native_resolver_matches(kind, outcome.get("resolver"))
                            for outcome in matched
                        ):
                            errors.append(
                                f"maximal academic candidate {candidate_id} lacks native {kind} resolver verification"
                            )

            publisher_run_ids = {
                search_run_id
                for search_run_id, search_run in search_runs.items()
                if _surface_bucket(search_run.get("surface")) == "publisher_or_full_text"
                or _surface_bucket(search_run.get("surface_class")) == "publisher_or_full_text"
            }
            has_publisher_capture = any(
                manifest.get("capture_level") in {"full_text", "official_data", "user_file"}
                and bool(publisher_run_ids & {
                    str(run_id) for run_id in manifest.get("search_run_ids", [])
                })
                for manifest in manifests
            )
            if not has_publisher_capture:
                errors.append(
                    "maximal_full_dossier publisher/full-text coverage requires an inspectable full-text capture bound to that search surface"
                )

    pass_rank = {"corpus": 0, "baseline": 1, "counterevidence": 1, "gap_fill": 2}
    by_query: dict[str, list[dict[str, object]]] = {}
    for row in search_runs.values():
        by_query.setdefault(str(row.get("query_id")), []).append(row)
    for query_id, rows in by_query.items():
        ordered = sorted(rows, key=lambda row: str(row.get("searched_at", "")))
        ranks = [pass_rank.get(str(row.get("pass_kind")), -1) for row in ordered]
        if ranks != sorted(ranks):
            errors.append(f"{query_id} search passes are out of order")

    if brief.get("retrieval_mode") == "closed_corpus" or brief.get("source_policy") == "closed_corpus":
        if any(
            row.get("adapter") != "closed_corpus" or row.get("surface_class") != "local_corpus"
            for row in search_runs.values()
        ):
            errors.append("closed_corpus forbids external search runs")
        for candidate in candidates.values():
            if any(
                isinstance(outcome, dict) and outcome.get("status") != "skipped"
                for outcome in candidate.get("resolver_outcomes", [])
            ):
                errors.append("closed_corpus forbids external resolver outcomes")

    manifest_candidates = {str(item.get("candidate_id")) for item in manifests}
    for candidate_id, candidate in candidates.items():
        disposition = candidate.get("disposition")
        if disposition == "include" and candidate_id not in manifest_candidates:
            errors.append(f"included candidate {candidate_id} lacks a capture")
        if disposition in {"exclude", "needs_review"} and candidate_id in manifest_candidates:
            errors.append(f"capture refers to {disposition} candidate {candidate_id}")
    for source in sources:
        if source.get("source_type") not in ACADEMIC_SOURCE_TYPES:
            continue
        bibliographic = source.get("bibliographic")
        if not isinstance(bibliographic, dict) or bibliographic.get("status") != "verified":
            errors.append(
                f"academic candidate is not bibliographically verified: {source.get('source_id')}"
            )
    return list(dict.fromkeys(errors))


def _gap_raw_result_count(search_run: dict[str, object]) -> int:
    if search_run.get("execution_status") == "unreachable":
        return 0
    count = search_run.get("result_count", 0)
    if count is None:
        return 0
    return int(count)


def _source_from_capture(
    source_id: str,
    adapter_record: dict[str, Any],
    captured: dict[str, object],
    candidate: dict[str, object],
) -> dict[str, object]:
    authors = candidate.get("authors")
    author_or_org = "; ".join(str(item) for item in authors) if isinstance(authors, list) else ""
    if not author_or_org:
        author_or_org = str(adapter_record.get("publisher", "")).strip()
    bibliographic: dict[str, object] | None = None
    if captured.get("source_type") in ACADEMIC_SOURCE_TYPES:
        bibliographic = {
            "identifiers": dict(candidate.get("identifiers", {})),
            "status": derive_bibliographic_status(candidate),
            "version_family_id": candidate.get("version_family_id"),
            "version_role": candidate.get("version_role") or "other",
        }
    source = {
        "source_id": source_id,
        "title": str(adapter_record.get("title", "")).strip(),
        "author_or_org": author_or_org,
        "canonical_url": captured["canonical_url"],
        "file_ref": captured["file_ref"],
        "published_at": captured["published_at"],
        "publication_date_status": captured["publication_date_status"],
        "retrieved_at": captured["retrieved_at"],
        "source_type": captured["source_type"],
        "primary_class": captured["primary_class"],
        "reliability_tier": captured["reliability_tier"],
        "freshness_status": str(adapter_record.get("freshness_status", "unknown")),
        "reliability_notes": captured["reliability_notes"],
        "content_hash": captured["snapshot_sha256"],
        "bibliographic": bibliographic,
    }
    errors = validate_source_record(source)
    if errors:
        raise ValueError("invalid source record: " + "; ".join(errors))
    return source


def normalize_retrieval_records(
    records: list[dict[str, object]], *, mode: str, cache_root: Path
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """Return source, capture manifest, and audit records after validation."""
    if mode not in ALLOWED_MODES:
        raise ValueError(f"unknown retrieval mode: {mode}")
    search_runs: dict[str, dict[str, object]] = {}
    candidates: dict[str, dict[str, object]] = {}
    search_waves: dict[str, dict[str, object]] = {}
    gap_assessments: dict[str, dict[str, object]] = {}
    capture_inputs: list[dict[str, object]] = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"retrieval record {index} must be an object")
        contract_errors = validate_retrieval_input_record(record)
        if contract_errors:
            raise ValueError(f"retrieval record {index} is invalid: {'; '.join(contract_errors)}")
        adapter = str(record.get("adapter", ""))
        if adapter != mode:
            raise ValueError(f"adapter {adapter or '<missing>'} is not allowed in {mode} mode")
        kind = record.get("record_kind")
        if kind == "search_run":
            search_run_id = str(record["search_run_id"])
            if search_run_id in search_runs:
                raise ValueError(f"duplicate search_run_id {search_run_id}")
            snapshot_errors = validate_audit_snapshot(record, cache_root)
            snapshot_errors.extend(validate_search_request_snapshot(record, cache_root))
            if snapshot_errors:
                raise ValueError(f"search run {search_run_id}: {'; '.join(snapshot_errors)}")
            search_runs[search_run_id] = record
        elif kind == "candidate":
            candidate_id = str(record["candidate_id"])
            if candidate_id in candidates:
                raise ValueError(f"duplicate candidate_id {candidate_id}")
            snapshot_errors = validate_candidate_snapshots(record, cache_root)
            if snapshot_errors:
                raise ValueError(f"candidate {candidate_id}: {'; '.join(snapshot_errors)}")
            candidates[candidate_id] = record
        elif kind == "search_wave":
            wave_id = str(record["wave_id"])
            if wave_id in search_waves:
                raise ValueError(f"duplicate wave_id {wave_id}")
            search_waves[wave_id] = record
        elif kind == "gap_assessment":
            assessment_id = str(record["assessment_id"])
            if assessment_id in gap_assessments:
                raise ValueError(f"duplicate assessment_id {assessment_id}")
            gap_assessments[assessment_id] = record
        else:
            capture_inputs.append(record)

    response_uses: dict[tuple[str, str], str] = {}
    for search_run_id, search_run in search_runs.items():
        response_identity = (
            str(search_run.get("raw_artifact", "")),
            str(search_run.get("snapshot_sha256", "")),
        )
        request_identity = str(search_run.get("request_sha256", ""))
        previous = response_uses.get(response_identity)
        if previous is not None and previous != request_identity:
            raise ValueError(
                "search response snapshot is reused across different executed queries: "
                f"{search_run_id}"
            )
        response_uses[response_identity] = request_identity

    family_errors = validate_version_families(list(candidates.values()))
    if family_errors:
        raise ValueError("; ".join(family_errors))
    for candidate_id, candidate in candidates.items():
        unknown = sorted(set(candidate["search_run_ids"]) - set(search_runs))
        if unknown:
            raise ValueError(f"candidate {candidate_id} references unknown search runs: {', '.join(unknown)}")
    for wave_id, wave in search_waves.items():
        unknown_runs = sorted(set(wave["search_run_ids"]) - set(search_runs))
        if unknown_runs:
            raise ValueError(
                f"search wave {wave_id} references unknown search runs: {', '.join(unknown_runs)}"
            )
        unknown_candidates = sorted(set(wave["new_candidate_ids"]) - set(candidates))
        if unknown_candidates:
            raise ValueError(
                f"search wave {wave_id} references unknown candidates: {', '.join(unknown_candidates)}"
            )
    for assessment_id, assessment in gap_assessments.items():
        unknown_runs = sorted(set(assessment["supporting_search_run_ids"]) - set(search_runs))
        if unknown_runs:
            raise ValueError(
                f"gap assessment {assessment_id} references unknown search runs: {', '.join(unknown_runs)}"
            )
        unknown_waves = sorted(set(assessment["supporting_wave_ids"]) - set(search_waves))
        if unknown_waves:
            raise ValueError(
                f"gap assessment {assessment_id} references unknown search waves: {', '.join(unknown_waves)}"
            )
        unknown_candidates = sorted(set(assessment["screened_candidate_ids"]) - set(candidates))
        if unknown_candidates:
            raise ValueError(
                f"gap assessment {assessment_id} references unknown candidates: {', '.join(unknown_candidates)}"
            )

    by_identity: dict[str, list[tuple[dict[str, object], dict[str, object]]]] = {}
    captured_candidate_ids: set[str] = set()
    for record in capture_inputs:
        candidate_id = str(record["candidate_id"])
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise ValueError(f"capture refers to unknown candidate {candidate_id}")
        if candidate.get("disposition") != "include":
            raise ValueError(f"capture refers to {candidate.get('disposition')} candidate {candidate_id}")
        run_ids = set(record["search_run_ids"])
        unknown = sorted(run_ids - set(search_runs))
        if unknown:
            raise ValueError(f"capture {candidate_id} references unknown search runs: {', '.join(unknown)}")
        query_id = str(record["query_id"])
        if not any(search_runs[run_id].get("query_id") == query_id for run_id in run_ids):
            raise ValueError(f"capture {candidate_id} query_id is not bound to its search runs")
        captured = capture_retrieval_evidence(record, cache_root)
        family_id = candidate.get("version_family_id")
        identity = f"family:{family_id}" if family_id else f"candidate:{candidate_id}"
        by_identity.setdefault(identity, []).append((record, captured))
        captured_candidate_ids.add(candidate_id)

    missing_captures = sorted(
        candidate_id
        for candidate_id, candidate in candidates.items()
        if candidate.get("disposition") == "include" and candidate_id not in captured_candidate_ids
    )
    if missing_captures:
        raise ValueError("included candidates lack captures: " + ", ".join(missing_captures))

    sources: list[dict[str, object]] = []
    manifests: list[dict[str, object]] = []
    for index, identity in enumerate(sorted(by_identity), start=1):
        captures = by_identity[identity]
        adapter_record, captured = max(
            captures,
            key=lambda item: (
                candidates[str(item[1]["candidate_id"])].get("canonical_version") is True,
                str(item[1].get("retrieved_at", "")),
            ),
        )
        source_id = f"S{index:03d}"
        canonical_manifest = dict(captured)
        canonical_manifest["source_id"] = source_id
        candidate = candidates[str(canonical_manifest["candidate_id"])]
        sources.append(_source_from_capture(source_id, adapter_record, canonical_manifest, candidate))
        seen: set[tuple[str, str, str, str]] = set()
        for _record, item in sorted(
            captures,
            key=lambda pair: (
                str(pair[1].get("query_id", "")),
                str(pair[1].get("snapshot_sha256", "")),
                str(pair[1].get("locator", "")),
            ),
        ):
            identity_key = (
                str(item.get("query_id", "")),
                str(item.get("snapshot_sha256", "")),
                str(item.get("locator", "")),
                str(item.get("excerpt_sha256", "")),
            )
            if identity_key in seen:
                continue
            seen.add(identity_key)
            manifest = dict(item)
            manifest["source_id"] = source_id
            manifests.append(manifest)
    audit = (
        [search_runs[key] for key in sorted(search_runs)]
        + [candidates[key] for key in sorted(candidates)]
        + [search_waves[key] for key in sorted(search_waves)]
        + [gap_assessments[key] for key in sorted(gap_assessments)]
    )
    return sources, manifests, audit


def source_record(record: dict[str, Any], source_id: str) -> dict[str, Any]:
    result = dict(record)
    result["source_id"] = source_id
    return result


def merge_source_ledger(
    existing_sources: list[dict[str, Any]], incoming_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge sources monotonically while preserving every existing source ID."""
    output: list[dict[str, Any]] = []
    index_by_identity: dict[str, int] = {}
    used_ids: set[str] = set()
    maximum_id = 0
    for source in existing_sources:
        source_id = str(source.get("source_id", ""))
        if not re.fullmatch(r"S\d{3}", source_id) or source_id in used_ids:
            raise ValueError(f"existing source ledger has invalid or duplicate ID: {source_id or '<missing>'}")
        identity = source_identity(source)
        if identity in index_by_identity:
            raise ValueError(f"existing source ledger has duplicate identity: {identity}")
        errors = validate_source_record(source)
        if errors:
            raise ValueError(f"existing source {source_id} is invalid: {'; '.join(errors)}")
        used_ids.add(source_id)
        maximum_id = max(maximum_id, int(source_id[1:]))
        index_by_identity[identity] = len(output)
        output.append(dict(source))

    incoming_by_identity: dict[str, dict[str, Any]] = {}
    for record in incoming_records:
        identity = source_identity(record)
        current = incoming_by_identity.get(identity)
        if current is None or str(record.get("retrieved_at", "")) > str(current.get("retrieved_at", "")):
            incoming_by_identity[identity] = record

    for identity in sorted(incoming_by_identity):
        record = incoming_by_identity[identity]
        existing_index = index_by_identity.get(identity)
        if existing_index is not None:
            existing = output[existing_index]
            if str(record.get("retrieved_at", "")) > str(existing.get("retrieved_at", "")):
                output[existing_index] = source_record(record, str(existing["source_id"]))
            continue
        if maximum_id >= 999:
            raise ValueError("source ledger exhausted the S001-S999 ID range")
        maximum_id += 1
        output.append(source_record(record, f"S{maximum_id:03d}"))
    return output


def merge_source_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return merge_source_ledger([], records)


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"line {line_number} is not a JSON object")
        records.append(payload)
    return records


def _jsonl(records: list[dict[str, object]]) -> str:
    return b"".join(canonical_json_bytes(record) for record in records).decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_jsonl", type=Path)
    parser.add_argument("--mode", choices=sorted(ALLOWED_MODES), required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        records = _load_jsonl(args.input_jsonl)
        sources, manifests, audit = normalize_retrieval_records(
            records, mode=args.mode, cache_root=args.cache_root
        )
        if args.output_dir.exists() or args.output_dir.is_symlink():
            raise ValueError(f"output directory already exists: {args.output_dir}")
        args.output_dir.mkdir(parents=True, exist_ok=False)
        atomic_write_text(args.output_dir / "source-records.jsonl", _jsonl(sources))
        atomic_write_text(args.output_dir / "retrieval-manifest.jsonl", _jsonl(manifests))
        atomic_write_text(args.output_dir / "retrieval-audit.jsonl", _jsonl(audit))
    except (OSError, json.JSONDecodeError, SourceEvidenceError, ValueError) as exc:
        print(f"Retrieval normalization failed: {exc}", file=sys.stderr)
        return 4
    print(f"Normalized {len(sources)} source records into {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
