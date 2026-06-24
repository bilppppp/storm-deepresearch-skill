#!/usr/bin/env python3
"""Run the governed STORM DeepResearch stage harness."""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contract_io import (
    ContractError,
    load_json,
    load_jsonl,
    validate_amendment,
    validate_brief,
    validate_conflict_review_record,
    validate_finding_record,
    validate_report_outline,
    validate_research_plan,
    validate_tasklet_record,
    validate_source_plan,
)
from scripts.harness_io import (
    atomic_copy_file,
    atomic_promote,
    atomic_write_text,
    atomic_write_json,
    canonical_json_bytes,
    canonical_json_sha256,
    compute_skill_package_hash,
    sha256_file,
)
from scripts.export_report import DEFAULT_CHROME, RenderError, export_report, markdown_title
from scripts.governed_release import ReleaseGateError, release_run
from scripts.normalize_retrieval import normalize_retrieval_records
from scripts.merge_claim_ledger import merge_claim_records
from scripts.output_paths import OutputPathError, package_child, select_new_output_dir
from scripts.run_state import (
    ReceiptError,
    RunLayout,
    Stage,
    StagePreconditionError,
    commit_stage_receipt,
    create_generation,
    latest_generation,
    receipt_chain_status,
    verify_stage_precondition,
)
from scripts.report_traceability import (
    body_length,
    citation_index,
    extract_paragraphs,
    generate_references,
    has_handwritten_references,
    validate_report_traceability,
    validate_review_set,
)
from scripts.source_evidence import SourceEvidenceError, resolve_snapshot
from scripts.validate_evidence import validate_claim_closure
from scripts.validate_package import _public_safety_checks, validate_and_commit, validate_governed_run


SCRIPT_INTERFACE = "cli"
SCRIPT_INTERFACE_REASON = "The only supported public command surface for governed research stages."
ROOT = Path(__file__).resolve().parents[1]
EXIT_OK = 0
EXIT_CONTRACT = 4
EXIT_EVIDENCE = 5
EXIT_EXPORT = 6
EXIT_STAGE = 8
EXIT_RELEASE = 9
MIN_FULL_DOSSIER_DEEP_EXTERNAL_SOURCES = 6
USER_MATERIAL_SOURCE_CLASS_MARKERS = {
    "attachment", "closed", "corpus", "file", "input", "local", "provided",
    "supplied", "transcript", "user", "转录", "用户", "口述", "语料",
}
USER_MATERIAL_SOURCE_MARKERS = {
    "blogger voice", "local-corpus", "supplied", "transcript", "user",
    "转录", "用户", "口述",
}
SHALLOW_SOURCE_TYPES = {"community", "encyclopedia", "search_result"}
USER_SOURCE_TYPES = {"user_provided_file"}
THEORY_CLAIM_TERMS = {
    "adorno", "agamben", "arendt", "benjamin", "camus", "foucault",
    "horkheimer", "kant", "marx", "tolstoy",
    "阿多诺", "阿甘本", "阿伦特", "霍克海默", "康德", "马克思",
    "福柯", "加缪", "托尔斯泰", "文化工业", "生命政治", "平庸之恶",
    "世界公民", "反抗者", "战争与和平",
}
THEORY_SOURCE_TYPES = {
    "academic", "book", "expert", "peer_reviewed_paper", "secondary_synthesis",
}


class CLIContractError(ValueError):
    """Raised when caller input does not satisfy a governed stage contract."""


class RetrievalGateError(ValueError):
    """Raised when captured retrieval evidence cannot close the plan."""


class EvidenceGateError(ValueError):
    """Raised when Claims and outline do not form a closed evidence set."""


class DraftGateError(ValueError):
    """Raised when a draft cannot be traced to governed Claims and citations."""


class ReviewGateError(ValueError):
    """Raised when independent semantic review is incomplete or non-passing."""


class RenderStageError(ValueError):
    """Raised when canonical formats cannot be rendered without downgrade."""


def infer_language(topic: str, question: str, requested: str) -> str:
    if requested != "auto":
        return requested
    return "zh-CN" if re.search(r"[\u3400-\u9fff]", topic + question) else "en"


def default_length_contract(language: str, depth_level: str) -> dict[str, object]:
    if language == "zh-CN":
        ranges = {
            "briefing": (1500, 2000, 2500),
            "standard_report": (5000, 6000, 7000),
            "full_dossier": (8000, 9000, 10000),
        }
        unit = "characters"
    else:
        ranges = {
            "briefing": (800, 1200, 1800),
            "standard_report": (2200, 3000, 4000),
            "full_dossier": (3500, 5000, 7000),
        }
        unit = "words"
    minimum, target, maximum = ranges[depth_level]
    return {
        "unit": unit,
        "minimum": minimum,
        "target": target,
        "maximum": maximum,
        "content_standard": "evidence_led",
    }


def build_brief_v2(args: argparse.Namespace) -> dict[str, object]:
    topic = args.topic.strip()
    question = args.question.strip()
    language = infer_language(topic, question, args.language)
    briefing_reason = str(getattr(args, "briefing_reason", "") or "").strip()
    if args.depth_level == "briefing" and not briefing_reason:
        raise CLIContractError("briefing depth requires --briefing-reason with explicit user request evidence")
    if args.depth_level != "briefing" and briefing_reason:
        raise CLIContractError("--briefing-reason is only valid with --depth-level briefing")
    length_contract = default_length_contract(language, args.depth_level)
    length_overridden = args.min_units is not None or args.max_units is not None
    if args.min_units is not None:
        length_contract["minimum"] = args.min_units
    if args.max_units is not None:
        length_contract["maximum"] = args.max_units
    minimum = int(length_contract["minimum"])
    maximum = int(length_contract["maximum"])
    if minimum > maximum:
        raise CLIContractError("min-units cannot exceed max-units")
    if length_overridden:
        length_contract["target"] = (minimum + maximum) // 2
    brief = {
        "schema_version": "2.0",
        "topic": topic,
        "research_question": question,
        "user_goal": args.user_goal,
        "audience": args.audience,
        "depth_level": args.depth_level,
        "report_language": language,
        "length_contract": length_contract,
        "geography": args.geography,
        "timeframe": args.timeframe,
        "source_policy": args.source_policy,
        "freshness_policy": {
            "as_of": args.as_of or date.today().isoformat(),
            "max_age_days": args.max_age_days,
        },
        "retrieval_mode": args.retrieval_mode,
        "output_mode": args.output_mode,
        "uncertainty_tolerance": args.uncertainty_tolerance,
        "high_stakes": args.high_stakes,
        "user_materials": list(args.user_material),
        "assumptions": list(args.assumption),
    }
    if briefing_reason:
        brief["briefing_reason"] = briefing_reason
    return brief


def validate_or_raise(errors: list[str]) -> None:
    if errors:
        raise CLIContractError("; ".join(errors))


def create_run_layout(root: Path) -> RunLayout:
    if root.exists() or root.is_symlink():
        raise OutputPathError(f"output directory already exists: {root}")
    root.mkdir(parents=True, exist_ok=False)
    layout = RunLayout(root)
    create_generation(layout, 1)
    return layout


def write_generation_input(
    layout: RunLayout, generation: int, name: str, payload: object
) -> Path:
    path = layout.generation_input(generation, name)
    atomic_write_json(path, payload)
    return path


def refresh_current_brief_view(layout: RunLayout, generation: int) -> None:
    authoritative = load_json(layout.generation_input(generation, "brief.json"))
    atomic_write_json(package_child(layout.root, "brief.json"), authoritative)


def verify_current_brief_view(layout: RunLayout, generation: int) -> dict[str, object]:
    authoritative_path = layout.generation_input(generation, "brief.json")
    current_path = package_child(layout.root, "brief.json")
    if not current_path.is_file() or current_path.is_symlink():
        raise StagePreconditionError("brief view is missing or unsafe")
    if sha256_file(authoritative_path) != sha256_file(current_path):
        raise StagePreconditionError("brief view does not match authoritative generation input")
    return load_json(authoritative_path)


def initialize_at_output(
    topic: str,
    question: str,
    output: Path,
    *,
    language: str = "auto",
    depth_level: str = "full_dossier",
    minimum_units: int | None = None,
    maximum_units: int | None = None,
    output_mode: str = "full",
    high_stakes: bool = False,
    briefing_reason: str = "",
) -> RunLayout:
    args = argparse.Namespace(
        topic=topic,
        question=question,
        language=language,
        depth_level=depth_level,
        min_units=minimum_units,
        max_units=maximum_units,
        user_goal="Build an evidence-grounded answer",
        audience="General reader",
        geography="global",
        timeframe="current",
        source_policy="external_allowed",
        as_of=None,
        max_age_days=365,
        retrieval_mode="host",
        output_mode=output_mode,
        uncertainty_tolerance="low",
        high_stakes=high_stakes,
        briefing_reason=briefing_reason,
        user_material=[],
        assumption=[],
    )
    brief = build_brief_v2(args)
    validate_or_raise(validate_brief(brief))
    package_hash = compute_skill_package_hash(ROOT)
    layout = create_run_layout(output)
    brief_path = write_generation_input(layout, 1, "brief.json", brief)
    refresh_current_brief_view(layout, 1)
    commit_stage_receipt(
        layout,
        generation=1,
        stage=Stage.INIT,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts={},
        output_paths=[brief_path],
    )
    return layout


def command_init(args: argparse.Namespace) -> int:
    output = select_new_output_dir(
        args.topic.strip(),
        workspace=args.workspace,
        output_root=args.output_root,
        output=args.output,
    )
    initialize_at_output(
        args.topic.strip(),
        args.question.strip(),
        output,
        language=args.language,
        depth_level=args.depth_level,
        minimum_units=args.min_units,
        maximum_units=args.max_units,
        output_mode=args.output_mode,
        high_stakes=args.high_stakes,
        briefing_reason=args.briefing_reason,
    )
    print(f"Initialized {output}")
    return EXIT_OK


def validate_plan_bundle(
    plan: dict[str, object], source_plan: dict[str, object], brief: dict[str, object]
) -> None:
    errors = validate_research_plan(plan, brief, set())
    errors.extend(validate_source_plan(source_plan))
    errors.extend(validate_source_depth_plan(source_plan, brief, plan))
    questions = plan.get("questions") if isinstance(plan.get("questions"), list) else []
    source_questions = source_plan.get("questions") if isinstance(source_plan.get("questions"), list) else []
    plan_ids = {str(item.get("question_id")) for item in questions if isinstance(item, dict)}
    source_ids = {str(item.get("query_id")) for item in source_questions if isinstance(item, dict)}
    if plan_ids != source_ids:
        errors.append("source plan must cover every research question exactly once")
    source_classes = source_plan.get("source_classes") if isinstance(source_plan.get("source_classes"), list) else []
    class_ids = {str(item.get("class_id")) for item in source_classes if isinstance(item, dict)}
    for item in source_questions:
        if not isinstance(item, dict):
            continue
        unknown = set(item.get("required_source_classes", [])) - class_ids
        if unknown:
            errors.append(f"source question {item.get('query_id')} references unknown source classes")
    if brief.get("depth_level") == "full_dossier":
        perspectives = plan.get("perspectives") if isinstance(plan.get("perspectives"), list) else []
        if len(set(perspectives)) < 5:
            errors.append("full_dossier requires at least five perspectives")
        if len(questions) < 10:
            errors.append("full_dossier requires at least ten research questions")
    validate_or_raise(errors)


def _is_full_external_dossier(brief: dict[str, object]) -> bool:
    return (
        brief.get("depth_level") == "full_dossier"
        and brief.get("source_policy") != "closed_corpus"
        and brief.get("retrieval_mode") != "closed_corpus"
    )


def _source_class_text(source_class: dict[str, object]) -> str:
    parts: list[str] = []
    for key in ("class_id", "name"):
        parts.append(str(source_class.get(key, "")))
    for key in ("can_prove", "cannot_prove"):
        value = source_class.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return " ".join(parts).casefold()


def _is_user_material_source_class(source_class: dict[str, object]) -> bool:
    text = _source_class_text(source_class)
    return any(marker in text for marker in USER_MATERIAL_SOURCE_CLASS_MARKERS)


def validate_source_depth_plan(
    source_plan: dict[str, object],
    brief: dict[str, object],
    plan: dict[str, object],
) -> list[str]:
    if not _is_full_external_dossier(brief):
        return []
    errors: list[str] = []
    source_classes = [
        item for item in source_plan.get("source_classes", [])
        if isinstance(item, dict)
    ]
    external_class_ids = {
        str(item.get("class_id"))
        for item in source_classes
        if not _is_user_material_source_class(item)
    }
    if not external_class_ids:
        errors.append("full_dossier external research requires source classes beyond user, transcript, or closed corpus material")
    source_questions = [
        item for item in source_plan.get("questions", [])
        if isinstance(item, dict)
    ]
    external_questions = [
        item for item in source_questions
        if set(str(class_id) for class_id in item.get("required_source_classes", [])) & external_class_ids
    ]
    required_external_questions = max(3, len(source_questions) // 2)
    if len(external_questions) < required_external_questions:
        errors.append("full_dossier external research requires at least half of source questions to require external source classes")
    budget = plan.get("retrieval_budget") if isinstance(plan.get("retrieval_budget"), dict) else {}
    if isinstance(budget.get("max_sources"), int) and budget["max_sources"] < MIN_FULL_DOSSIER_DEEP_EXTERNAL_SOURCES:
        errors.append(
            f"full_dossier external research requires retrieval_budget.max_sources >= {MIN_FULL_DOSSIER_DEEP_EXTERNAL_SOURCES}"
        )
    return errors


def build_storm_tasklets(
    plan: dict[str, object], source_plan: dict[str, object]
) -> list[dict[str, object]]:
    """Convert STORM questions into executable research tasklets."""
    source_by_question = {
        str(item.get("query_id")): item
        for item in source_plan.get("questions", [])
        if isinstance(item, dict)
    }
    tasklets: list[dict[str, object]] = []
    for index, question in enumerate(plan.get("questions", []), start=1):
        if not isinstance(question, dict):
            continue
        question_id = str(question.get("question_id", ""))
        source_question = source_by_question.get(question_id, {})
        tasklets.append({
            "schema_version": "2.0",
            "tasklet_id": f"T{index:03d}",
            "question_id": question_id,
            "perspective": str(question.get("perspective", "")),
            "question": str(question.get("text", "")),
            "evidence_need": str(source_question.get("evidence_need", "")),
            "required_source_classes": list(source_question.get("required_source_classes", [])),
            "status": "planned",
            "output_contract": [
                "finding_id",
                "summary",
                "source_ids",
                "evidence_locators",
                "claim_ids",
                "limitations",
            ],
        })
    return tasklets


def validate_storm_tasklets(
    tasklets: list[dict[str, object]],
    plan: dict[str, object],
    source_plan: dict[str, object],
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
    tasklet_question_ids: set[str] = set()
    tasklet_ids: set[str] = set()
    for index, tasklet in enumerate(tasklets, start=1):
        errors.extend(f"tasklet {index}: {item}" for item in validate_tasklet_record(tasklet))
        tasklet_id = str(tasklet.get("tasklet_id", ""))
        if tasklet_id in tasklet_ids:
            errors.append(f"duplicate tasklet_id {tasklet_id}")
        tasklet_ids.add(tasklet_id)
        question_id = str(tasklet.get("question_id", ""))
        tasklet_question_ids.add(question_id)
        if question_id not in question_ids:
            errors.append(f"tasklet {tasklet_id} references unknown research question {question_id}")
        if question_id not in source_question_ids:
            errors.append(f"tasklet {tasklet_id} lacks source-plan coverage")
    missing = sorted(question_ids - tasklet_question_ids)
    if missing:
        errors.append("storm tasklets must cover every research question: " + ", ".join(missing))
    return errors


def _promote_plan_artifacts(
    layout: RunLayout,
    generation: int,
    plan: dict[str, object],
    source_plan: dict[str, object],
    tasklets: list[dict[str, object]],
) -> tuple[Path, Path, Path]:
    staging = package_child(
        layout.root, f"work/.staging/g{generation:04d}/plan-{uuid.uuid4().hex}"
    )
    staging.mkdir(parents=True, exist_ok=False)
    staged_plan = staging / "research-plan.json"
    staged_source_plan = staging / "source-plan.json"
    staged_tasklets = staging / "storm-tasklets.jsonl"
    atomic_write_json(staged_plan, plan)
    atomic_write_json(staged_source_plan, source_plan)
    atomic_write_text(staged_tasklets, _jsonl_text(tasklets))
    plan_path = layout.artifact(generation, "research/research-plan.json")
    source_plan_path = layout.artifact(generation, "research/source-plan.json")
    tasklet_path = layout.artifact(generation, "research/storm-tasklets.jsonl")
    atomic_promote(staged_plan, plan_path)
    atomic_promote(staged_source_plan, source_plan_path)
    atomic_promote(staged_tasklets, tasklet_path)
    staging.rmdir()
    return plan_path, source_plan_path, tasklet_path


def _refresh_current_plan_view(
    layout: RunLayout,
    plan: dict[str, object],
    source_plan: dict[str, object],
    tasklets: list[dict[str, object]],
) -> None:
    root = package_child(layout.root, "current/research")
    atomic_write_json(root / "research-plan.json", plan)
    atomic_write_json(root / "source-plan.json", source_plan)
    atomic_write_text(root / "storm-tasklets.jsonl", _jsonl_text(tasklets))


def command_plan(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.PLAN, package_hash)
    brief = verify_current_brief_view(layout, generation)
    plan = load_json(args.plan_json)
    source_plan = load_json(args.source_plan_json)
    validate_plan_bundle(plan, source_plan, brief)
    tasklets = build_storm_tasklets(plan, source_plan)
    tasklet_errors = validate_storm_tasklets(tasklets, plan, source_plan)
    if tasklet_errors:
        raise CLIContractError("; ".join(dict.fromkeys(tasklet_errors)))
    plan_path, source_plan_path, tasklet_path = _promote_plan_artifacts(
        layout, generation, plan, source_plan, tasklets
    )
    brief_path = layout.generation_input(generation, "brief.json")
    commit_stage_receipt(
        layout,
        generation=generation,
        stage=Stage.PLAN,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts={"inputs/brief.json": sha256_file(brief_path)},
        output_paths=[plan_path, source_plan_path, tasklet_path],
    )
    _refresh_current_plan_view(layout, plan, source_plan, tasklets)
    print(f"Planned {layout.root}")
    return EXIT_OK


def _jsonl_text(records: list[dict[str, object]]) -> str:
    return b"".join(canonical_json_bytes(record) for record in records).decode("utf-8")


def _promote_retrieval_artifacts(
    layout: RunLayout,
    generation: int,
    sources: list[dict[str, object]],
    manifests: list[dict[str, object]],
) -> tuple[Path, Path]:
    staging = package_child(
        layout.root, f"work/.staging/g{generation:04d}/retrieval-{uuid.uuid4().hex}"
    )
    staging.mkdir(parents=True, exist_ok=False)
    staged_sources = staging / "source-register.jsonl"
    staged_manifest = staging / "retrieval-manifest.jsonl"
    atomic_write_text(staged_sources, _jsonl_text(sources))
    atomic_write_text(staged_manifest, _jsonl_text(manifests))
    source_path = layout.artifact(generation, "research/source-register.jsonl")
    manifest_path = layout.artifact(generation, "research/retrieval-manifest.jsonl")
    atomic_promote(staged_sources, source_path)
    atomic_promote(staged_manifest, manifest_path)
    staging.rmdir()
    return source_path, manifest_path


def _refresh_current_retrieval_view(
    layout: RunLayout,
    sources: list[dict[str, object]],
    manifests: list[dict[str, object]],
) -> None:
    root = package_child(layout.root, "current/research")
    atomic_write_text(root / "source-register.jsonl", _jsonl_text(sources))
    atomic_write_text(root / "retrieval-manifest.jsonl", _jsonl_text(manifests))


def _is_user_material_source(source: dict[str, object]) -> bool:
    source_type = str(source.get("source_type", "")).casefold()
    if source_type in USER_SOURCE_TYPES:
        return True
    text = " ".join(
        str(source.get(key, ""))
        for key in ("title", "author_or_org", "canonical_url", "file_ref", "reliability_notes")
    ).casefold()
    return any(marker in text for marker in USER_MATERIAL_SOURCE_MARKERS)


def _is_deep_external_source(source: dict[str, object]) -> bool:
    if _is_user_material_source(source):
        return False
    if not str(source.get("canonical_url") or "").startswith(("http://", "https://")):
        return False
    source_type = str(source.get("source_type", "")).casefold()
    if source_type in SHALLOW_SOURCE_TYPES:
        return False
    return True


def validate_retrieval_depth(
    sources: list[dict[str, object]], brief: dict[str, object]
) -> list[str]:
    if not _is_full_external_dossier(brief):
        return []
    deep_external = [source for source in sources if _is_deep_external_source(source)]
    if len(deep_external) < MIN_FULL_DOSSIER_DEEP_EXTERNAL_SOURCES:
        return [
            "full_dossier external research requires at least "
            f"{MIN_FULL_DOSSIER_DEEP_EXTERNAL_SOURCES} non-user, non-encyclopedia external sources"
        ]
    return []


def command_ingest(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.RETRIEVAL, package_hash)
    brief = verify_current_brief_view(layout, generation)
    try:
        records = load_jsonl(args.input_jsonl)
        sources, manifests = normalize_retrieval_records(
            records,
            mode=str(brief["retrieval_mode"]),
            cache_root=layout.evidence_cache(generation, "."),
        )
    except (ContractError, SourceEvidenceError, ValueError) as exc:
        raise RetrievalGateError(str(exc)) from exc
    source_plan_path = layout.artifact(generation, "research/source-plan.json")
    source_plan = load_json(source_plan_path)
    planned_ids = {
        str(item.get("query_id"))
        for item in source_plan.get("questions", [])
        if isinstance(item, dict)
    }
    covered_ids = {str(item.get("query_id")) for item in manifests}
    missing = sorted(planned_ids - covered_ids)
    if missing:
        raise RetrievalGateError(
            "retrieval evidence does not cover planned questions: " + ", ".join(missing)
        )
    depth_errors = validate_retrieval_depth(sources, brief)
    if depth_errors:
        raise RetrievalGateError("; ".join(depth_errors))
    source_path, manifest_path = _promote_retrieval_artifacts(
        layout, generation, sources, manifests
    )
    plan_path = layout.artifact(generation, "research/research-plan.json")
    snapshot_paths = [
        resolve_snapshot(
            layout.evidence_cache(generation, "."), str(item["snapshot_ref"])
        )
        for item in manifests
    ]
    commit_stage_receipt(
        layout,
        generation=generation,
        stage=Stage.RETRIEVAL,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts={
            "artifacts/research/research-plan.json": sha256_file(plan_path),
            "artifacts/research/source-plan.json": sha256_file(source_plan_path),
        },
        output_paths=[source_path, manifest_path, *snapshot_paths],
    )
    _refresh_current_retrieval_view(layout, sources, manifests)
    print(f"Ingested {len(sources)} sources into {layout.root}")
    return EXIT_OK


def _manifest_by_source_id(manifests: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for manifest in manifests:
        result.setdefault(str(manifest.get("source_id", "")), []).append(manifest)
    return result


def validate_findings_pool(
    findings: list[dict[str, object]],
    tasklets: list[dict[str, object]],
    sources: list[dict[str, object]],
    manifests: list[dict[str, object]],
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
    manifests_by_source = _manifest_by_source_id(manifests)
    finding_ids: set[str] = set()
    usable_tasklets: set[str] = set()
    for index, finding in enumerate(findings, start=1):
        errors.extend(f"finding {index}: {item}" for item in validate_finding_record(finding))
        finding_id = str(finding.get("finding_id", ""))
        if finding_id in finding_ids:
            errors.append(f"duplicate finding_id {finding_id}")
        finding_ids.add(finding_id)
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
            source_manifests = manifests_by_source.get(source_id, [])
            if not any(
                str(manifest.get("snapshot_sha256")) == str(locator.get("snapshot_sha256"))
                for manifest in source_manifests
            ):
                errors.append(f"finding {finding_id} locator snapshot does not bind source {source_id}")
        if finding.get("status") == "usable":
            usable_tasklets.add(tasklet_id)
    if require_tasklet_coverage:
        missing = sorted(set(tasklet_by_id) - usable_tasklets)
        if missing:
            errors.append("findings pool must cover every STORM tasklet: " + ", ".join(missing))
    return errors


def validate_findings_claim_links(
    claims: list[dict[str, object]],
    findings: list[dict[str, object]],
) -> list[str]:
    usable_findings = [
        finding for finding in findings if finding.get("status") == "usable"
    ]
    by_claim: dict[str, list[dict[str, object]]] = {}
    for finding in usable_findings:
        for claim_id in finding.get("claim_ids", []):
            by_claim.setdefault(str(claim_id), []).append(finding)
    errors: list[str] = []
    for claim in claims:
        if not claim.get("material"):
            continue
        claim_id = str(claim.get("claim_id", ""))
        claim_sources = {str(source_id) for source_id in claim.get("supporting_source_ids", [])}
        linked = by_claim.get(claim_id, [])
        if not linked:
            errors.append(f"material claim {claim_id} is not linked to a usable STORM finding")
            continue
        if not any(claim_sources & {str(source_id) for source_id in finding.get("source_ids", [])} for finding in linked):
            errors.append(f"material claim {claim_id} finding link does not share supporting sources")
    return errors


def findings_coverage(
    tasklets: list[dict[str, object]], findings: list[dict[str, object]]
) -> dict[str, object]:
    usable = [finding for finding in findings if finding.get("status") == "usable"]
    covered_tasklets = sorted({str(finding.get("tasklet_id")) for finding in usable})
    all_tasklets = sorted(str(tasklet.get("tasklet_id")) for tasklet in tasklets)
    claim_ids = sorted({
        str(claim_id)
        for finding in usable
        for claim_id in finding.get("claim_ids", [])
    })
    return {
        "schema_version": "2.0",
        "tasklets_total": len(tasklets),
        "tasklets_with_usable_findings": len(covered_tasklets),
        "usable_findings": len(usable),
        "missing_tasklet_ids": sorted(set(all_tasklets) - set(covered_tasklets)),
        "claim_ids_linked": claim_ids,
        "created_at": _utc_now(),
    }


def _write_findings_artifacts(
    layout: RunLayout,
    generation: int,
    findings: list[dict[str, object]],
    coverage: dict[str, object],
) -> tuple[Path, Path]:
    findings_path = layout.artifact(generation, "research/storm-findings-pool.jsonl")
    coverage_path = layout.artifact(generation, "research/finding-coverage.json")
    atomic_write_text(findings_path, _jsonl_text(findings))
    atomic_write_json(coverage_path, coverage)
    current = package_child(layout.root, "current/research")
    atomic_write_text(current / "storm-findings-pool.jsonl", _jsonl_text(findings))
    atomic_write_json(current / "finding-coverage.json", coverage)
    return findings_path, coverage_path


def command_findings(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.EVIDENCE, package_hash)
    if layout.receipt(generation, Stage.EVIDENCE).exists():
        raise StagePreconditionError("cannot modify findings after evidence receipt exists")
    brief = verify_current_brief_view(layout, generation)
    try:
        findings = load_jsonl(args.findings_jsonl)
    except ContractError as exc:
        raise EvidenceGateError(str(exc)) from exc
    plan = load_json(layout.artifact(generation, "research/research-plan.json"))
    source_plan = load_json(layout.artifact(generation, "research/source-plan.json"))
    tasklets = load_jsonl(layout.artifact(generation, "research/storm-tasklets.jsonl"))
    sources = load_jsonl(layout.artifact(generation, "research/source-register.jsonl"))
    manifests = load_jsonl(layout.artifact(generation, "research/retrieval-manifest.jsonl"))
    errors = validate_storm_tasklets(tasklets, plan, source_plan)
    errors.extend(validate_findings_pool(
        findings, tasklets, sources, manifests,
        require_tasklet_coverage=_is_full_external_dossier(brief),
    ))
    if errors:
        raise EvidenceGateError("; ".join(dict.fromkeys(errors)))
    coverage = findings_coverage(tasklets, findings)
    _write_findings_artifacts(layout, generation, findings, coverage)
    print(f"Registered {len(findings)} STORM findings in {layout.root}")
    return EXIT_OK


def _validate_contradictions(
    payload: dict[str, object], claims: list[dict[str, object]]
) -> list[str]:
    errors: list[str] = []
    if set(payload) != {"schema_version", "conflicts"} or payload.get("schema_version") != "2.0":
        return ["contradiction ledger has invalid top-level contract"]
    conflicts = payload.get("conflicts")
    if not isinstance(conflicts, list):
        return ["contradiction ledger conflicts must be an array"]
    conflict_claim_ids: set[str] = set()
    fields = {"conflict_id", "claim_id", "source_ids", "analysis", "resolution_status", "change_condition"}
    for index, conflict in enumerate(conflicts, start=1):
        if not isinstance(conflict, dict) or set(conflict) != fields:
            errors.append(f"contradiction {index} has invalid fields")
            continue
        claim_id = str(conflict.get("claim_id", ""))
        conflict_claim_ids.add(claim_id)
        if not str(conflict.get("analysis", "")).strip():
            errors.append(f"contradiction {index} requires analysis")
        if not isinstance(conflict.get("source_ids"), list) or len(conflict["source_ids"]) < 2:
            errors.append(f"contradiction {index} requires opposing source IDs")
    for claim in claims:
        if claim.get("status") == "contested" and claim.get("claim_id") not in conflict_claim_ids:
            errors.append(f"contested claim {claim.get('claim_id')} is missing from contradiction ledger")
    return errors


def _validate_uncertainties(payload: dict[str, object]) -> list[str]:
    if set(payload) != {"schema_version", "uncertainties"} or payload.get("schema_version") != "2.0":
        return ["uncertainty ledger has invalid top-level contract"]
    records = payload.get("uncertainties")
    if not isinstance(records, list):
        return ["uncertainty ledger uncertainties must be an array"]
    fields = {"uncertainty_id", "claim_id", "description", "impact", "next_evidence"}
    errors = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict) or set(record) != fields:
            errors.append(f"uncertainty {index} has invalid fields")
        elif not all(str(record.get(field, "")).strip() for field in ("uncertainty_id", "description", "impact", "next_evidence")):
            errors.append(f"uncertainty {index} has empty required fields")
    return errors


def _claim_needs_theory_source(claim: dict[str, object]) -> bool:
    text = str(claim.get("claim_text", "")).casefold()
    return any(term.casefold() in text for term in THEORY_CLAIM_TERMS)


def _is_theory_source(source: dict[str, object]) -> bool:
    if _is_user_material_source(source):
        return False
    source_type = str(source.get("source_type", "")).casefold()
    return source_type in THEORY_SOURCE_TYPES


def validate_theory_claim_sources(
    claims: list[dict[str, object]],
    sources: list[dict[str, object]],
    brief: dict[str, object],
) -> list[str]:
    if not _is_full_external_dossier(brief):
        return []
    diagnostics = theory_claim_diagnostics(claims, sources, brief)
    return [
        f"theory claim {item['claim_id']} requires academic, book, expert, or peer-reviewed support beyond user material"
        for item in diagnostics["theory_claims"]
        if not item["ok"]
    ]


def _matched_theory_terms(claim: dict[str, object]) -> list[str]:
    text = str(claim.get("claim_text", "")).casefold()
    return sorted(
        term for term in THEORY_CLAIM_TERMS if term.casefold() in text
    )


def theory_claim_diagnostics(
    claims: list[dict[str, object]],
    sources: list[dict[str, object]],
    brief: dict[str, object],
) -> dict[str, object]:
    source_by_id = {str(source.get("source_id")): source for source in sources}
    records: list[dict[str, object]] = []
    if not _is_full_external_dossier(brief):
        return {"ok": True, "skipped": True, "reason": "not a full external dossier", "theory_claims": records}
    for claim in claims:
        if not claim.get("material") or not _claim_needs_theory_source(claim):
            continue
        supporting = [
            source_by_id.get(str(source_id))
            for source_id in claim.get("supporting_source_ids", [])
        ]
        source_rows = [
            {
                "source_id": str(source.get("source_id", "")),
                "source_type": str(source.get("source_type", "")),
                "primary_class": str(source.get("primary_class", "")),
                "reliability_tier": str(source.get("reliability_tier", "")),
                "is_theory_source": _is_theory_source(source),
            }
            for source in supporting if source
        ]
        ok = any(row["is_theory_source"] for row in source_rows)
        records.append({
            "claim_id": str(claim.get("claim_id", "")),
            "matched_terms": _matched_theory_terms(claim),
            "supporting_sources": source_rows,
            "required_source_types": sorted(THEORY_SOURCE_TYPES),
            "ok": ok,
        })
    return {
        "ok": all(item["ok"] for item in records),
        "skipped": False,
        "theory_claims": records,
    }


def _promote_evidence_artifacts(
    layout: RunLayout,
    generation: int,
    claims: list[dict[str, object]],
    contradictions: dict[str, object],
    uncertainties: dict[str, object],
    outline: dict[str, object],
) -> list[Path]:
    staging = package_child(
        layout.root, f"work/.staging/g{generation:04d}/evidence-{uuid.uuid4().hex}"
    )
    staging.mkdir(parents=True, exist_ok=False)
    staged = {
        "claim-evidence-ledger.jsonl": _jsonl_text(claims),
        "contradiction-ledger.json": None,
        "uncertainty-ledger.json": None,
        "report-outline.json": None,
    }
    atomic_write_text(staging / "claim-evidence-ledger.jsonl", staged["claim-evidence-ledger.jsonl"] or "")
    atomic_write_json(staging / "contradiction-ledger.json", contradictions)
    atomic_write_json(staging / "uncertainty-ledger.json", uncertainties)
    atomic_write_json(staging / "report-outline.json", outline)
    outputs: list[Path] = []
    for name in staged:
        destination = layout.artifact(generation, f"research/{name}")
        atomic_promote(staging / name, destination)
        outputs.append(destination)
    staging.rmdir()
    return outputs


def _refresh_current_evidence_view(
    layout: RunLayout,
    claims: list[dict[str, object]],
    contradictions: dict[str, object],
    uncertainties: dict[str, object],
    outline: dict[str, object],
) -> None:
    root = package_child(layout.root, "current/research")
    atomic_write_text(root / "claim-evidence-ledger.jsonl", _jsonl_text(claims))
    atomic_write_json(root / "contradiction-ledger.json", contradictions)
    atomic_write_json(root / "uncertainty-ledger.json", uncertainties)
    atomic_write_json(root / "report-outline.json", outline)


def command_evidence(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.EVIDENCE, package_hash)
    brief = verify_current_brief_view(layout, generation)
    try:
        incoming_claims = load_jsonl(args.claims)
        claims = merge_claim_records([], incoming_claims)
    except (ContractError, ValueError) as exc:
        raise EvidenceGateError(str(exc)) from exc
    source_path = layout.artifact(generation, "research/source-register.jsonl")
    sources = load_jsonl(source_path)
    if getattr(args, "preflight_theory", False):
        payload = theory_claim_diagnostics(claims, sources, brief)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK if payload["ok"] else EXIT_EVIDENCE
    missing_arguments = [
        name for name, value in (
            ("--contradictions", args.contradictions),
            ("--uncertainties", args.uncertainties),
            ("--report-outline", args.report_outline),
        ) if value is None
    ]
    if missing_arguments:
        raise CLIContractError(
            "evidence requires " + ", ".join(missing_arguments)
        )
    try:
        contradictions = load_json(args.contradictions)
        uncertainties = load_json(args.uncertainties)
        outline = load_json(args.report_outline)
    except ContractError as exc:
        raise EvidenceGateError(str(exc)) from exc
    research_plan_path = layout.artifact(generation, "research/research-plan.json")
    source_plan_path = layout.artifact(generation, "research/source-plan.json")
    tasklet_path = layout.artifact(generation, "research/storm-tasklets.jsonl")
    findings_path = layout.artifact(generation, "research/storm-findings-pool.jsonl")
    coverage_path = layout.artifact(generation, "research/finding-coverage.json")
    manifest_path = layout.artifact(generation, "research/retrieval-manifest.jsonl")
    research_plan = load_json(research_plan_path)
    source_plan = load_json(source_plan_path)
    manifests = load_jsonl(manifest_path)
    question_ids = {
        str(item.get("question_id"))
        for item in research_plan.get("questions", [])
        if isinstance(item, dict)
    }
    claim_ids = {str(item.get("claim_id")) for item in claims}
    errors = validate_report_outline(outline, brief, question_ids, claim_ids)
    errors.extend(validate_claim_closure(claims, sources, outline, manifests))
    errors.extend(validate_theory_claim_sources(claims, sources, brief))
    errors.extend(_validate_contradictions(contradictions, claims))
    errors.extend(_validate_uncertainties(uncertainties))
    tasklets: list[dict[str, object]] = []
    findings: list[dict[str, object]] = []
    if _is_full_external_dossier(brief):
        missing_research_pool = False
        for required_path, label in (
            (tasklet_path, "storm tasklets"),
            (findings_path, "storm findings pool"),
            (coverage_path, "finding coverage"),
        ):
            if not required_path.is_file() or required_path.is_symlink():
                errors.append(f"full_dossier requires {label} before evidence")
                missing_research_pool = True
        if not missing_research_pool:
            tasklets = load_jsonl(tasklet_path)
            findings = load_jsonl(findings_path)
            errors.extend(validate_storm_tasklets(tasklets, research_plan, source_plan))
            errors.extend(validate_findings_pool(
                findings, tasklets, sources, manifests, require_tasklet_coverage=True
            ))
            errors.extend(validate_findings_claim_links(claims, findings))
    if brief.get("depth_level") == "full_dossier":
        material_claims = [claim for claim in claims if claim.get("material")]
        sections = outline.get("sections") if isinstance(outline.get("sections"), list) else []
        if len(material_claims) < 12:
            errors.append("full_dossier requires at least twelve material claims")
        if len(sections) < 6:
            errors.append("full_dossier requires at least six evidence-planned sections")
    if errors:
        raise EvidenceGateError("; ".join(dict.fromkeys(errors)))
    outputs = _promote_evidence_artifacts(
        layout, generation, claims, contradictions, uncertainties, outline
    )
    evidence_inputs = {
        "artifacts/research/research-plan.json": sha256_file(research_plan_path),
        "artifacts/research/source-plan.json": sha256_file(source_plan_path),
        "artifacts/research/source-register.jsonl": sha256_file(source_path),
        "artifacts/research/retrieval-manifest.jsonl": sha256_file(manifest_path),
        "artifacts/research/storm-tasklets.jsonl": sha256_file(tasklet_path),
    }
    if findings_path.is_file() and not findings_path.is_symlink():
        evidence_inputs["artifacts/research/storm-findings-pool.jsonl"] = sha256_file(findings_path)
    if coverage_path.is_file() and not coverage_path.is_symlink():
        evidence_inputs["artifacts/research/finding-coverage.json"] = sha256_file(coverage_path)
    commit_stage_receipt(
        layout,
        generation=generation,
        stage=Stage.EVIDENCE,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts=evidence_inputs,
        output_paths=outputs,
    )
    _refresh_current_evidence_view(layout, claims, contradictions, uncertainties, outline)
    print(f"Closed {len(claims)} Claims in {layout.root}")
    return EXIT_OK


def _promote_draft_artifacts(
    layout: RunLayout,
    generation: int,
    report: str,
    paragraph_map: list[dict[str, object]],
    citations: dict[str, dict[str, object]],
) -> list[Path]:
    staging = package_child(
        layout.root, f"work/.staging/g{generation:04d}/draft-{uuid.uuid4().hex}"
    )
    (staging / "drafts").mkdir(parents=True, exist_ok=False)
    (staging / "research").mkdir()
    atomic_write_text(staging / "drafts/report-v1.md", report)
    atomic_write_text(staging / "research/paragraph-map.jsonl", _jsonl_text(paragraph_map))
    atomic_write_json(staging / "research/citation-index.json", {
        "schema_version": "2.0",
        "citations": {
            key: str(source.get("source_id")) for key, source in citations.items()
        },
    })
    destinations = [
        layout.artifact(generation, "drafts/report-v1.md"),
        layout.artifact(generation, "research/paragraph-map.jsonl"),
        layout.artifact(generation, "research/citation-index.json"),
    ]
    sources = [
        staging / "drafts/report-v1.md",
        staging / "research/paragraph-map.jsonl",
        staging / "research/citation-index.json",
    ]
    for source, destination in zip(sources, destinations, strict=True):
        atomic_promote(source, destination)
    (staging / "drafts").rmdir()
    (staging / "research").rmdir()
    staging.rmdir()
    return destinations


def _refresh_current_draft_view(
    layout: RunLayout,
    report: str,
    paragraph_map: list[dict[str, object]],
    citations: dict[str, dict[str, object]],
) -> None:
    atomic_write_text(package_child(layout.root, "current/drafts/report-v1.md"), report)
    research = package_child(layout.root, "current/research")
    atomic_write_text(research / "paragraph-map.jsonl", _jsonl_text(paragraph_map))
    atomic_write_json(research / "citation-index.json", {
        "schema_version": "2.0",
        "citations": {
            key: str(source.get("source_id")) for key, source in citations.items()
        },
    })


def _preview_text(value: str, limit: int = 80) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def _paragraph_summary(paragraph: object) -> dict[str, object]:
    return {
        "index": getattr(paragraph, "index"),
        "locator": getattr(paragraph, "locator"),
        "heading": getattr(paragraph, "heading"),
        "sha256": getattr(paragraph, "sha256"),
        "preview": _preview_text(getattr(paragraph, "text")),
    }


def _error_locator(error: str) -> str | None:
    match = re.search(r"paragraph:\d+", error)
    return match.group(0) if match else None


def draft_preflight_report(
    brief: dict[str, object],
    draft_text: str,
    paragraph_map: list[dict[str, object]],
    claims: list[dict[str, object]],
    sources: list[dict[str, object]],
) -> dict[str, object]:
    errors: list[str] = []
    handwritten_references = has_handwritten_references(draft_text)
    if handwritten_references:
        errors.append("draft contains a hand-written References body")
    report = generate_references(draft_text, sources)
    traceability_errors = validate_report_traceability(report, paragraph_map, claims, sources)
    errors.extend(traceability_errors)
    length_contract = brief.get("length_contract") if isinstance(brief.get("length_contract"), dict) else {}
    unit = str(length_contract.get("unit", "words"))
    measured = body_length(report, unit)
    minimum = int(length_contract.get("minimum", 1))
    maximum = int(length_contract.get("maximum", 0))
    if measured < minimum or measured > maximum:
        errors.append(f"draft body length {measured} {unit} is outside {minimum}-{maximum}")
    paragraphs = extract_paragraphs(report)
    paragraph_by_locator = {
        str(getattr(paragraph, "locator")): paragraph for paragraph in paragraphs
    }
    error_rows = []
    for error in dict.fromkeys(errors):
        locator = _error_locator(error)
        paragraph = paragraph_by_locator.get(locator or "")
        error_rows.append({
            "message": error,
            "locator": locator,
            "paragraph": _paragraph_summary(paragraph) if paragraph else None,
        })
    return {
        "ok": not errors,
        "mode": "draft-preflight",
        "length": {
            "measured": measured,
            "unit": unit,
            "minimum": minimum,
            "maximum": maximum,
            "within_range": minimum <= measured <= maximum,
            "references_excluded": True,
        },
        "handwritten_references": handwritten_references,
        "paragraph_count": len(paragraphs),
        "mapped_paragraph_count": len(paragraph_map),
        "paragraphs": [_paragraph_summary(paragraph) for paragraph in paragraphs],
        "citation_keys": sorted(citation_index(sources).keys()),
        "errors": error_rows,
    }


def command_draft(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.DRAFT, package_hash)
    brief = verify_current_brief_view(layout, generation)
    draft_text = args.draft_md.read_text(encoding="utf-8")
    paragraph_map = load_jsonl(args.paragraph_map_jsonl)
    claim_path = layout.artifact(generation, "research/claim-evidence-ledger.jsonl")
    source_path = layout.artifact(generation, "research/source-register.jsonl")
    outline_path = layout.artifact(generation, "research/report-outline.json")
    claims = load_jsonl(claim_path)
    sources = load_jsonl(source_path)
    if getattr(args, "preflight", False):
        payload = draft_preflight_report(brief, draft_text, paragraph_map, claims, sources)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK if payload["ok"] else EXIT_EVIDENCE
    if has_handwritten_references(draft_text):
        raise DraftGateError("draft contains a hand-written References body")
    report = generate_references(draft_text, sources)
    errors = validate_report_traceability(report, paragraph_map, claims, sources)
    length_contract = brief.get("length_contract") if isinstance(brief.get("length_contract"), dict) else {}
    unit = str(length_contract.get("unit", "words"))
    measured = body_length(report, unit)
    minimum = int(length_contract.get("minimum", 1))
    maximum = int(length_contract.get("maximum", 0))
    if measured < minimum or measured > maximum:
        errors.append(
            f"draft body length {measured} {unit} is outside {minimum}-{maximum}"
        )
    if errors:
        raise DraftGateError("; ".join(dict.fromkeys(errors)))
    citations = citation_index(sources)
    outputs = _promote_draft_artifacts(
        layout, generation, report, paragraph_map, citations
    )
    commit_stage_receipt(
        layout,
        generation=generation,
        stage=Stage.DRAFT,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts={
            "artifacts/research/claim-evidence-ledger.jsonl": sha256_file(claim_path),
            "artifacts/research/source-register.jsonl": sha256_file(source_path),
            "artifacts/research/report-outline.json": sha256_file(outline_path),
        },
        output_paths=outputs,
    )
    _refresh_current_draft_view(layout, report, paragraph_map, citations)
    print(f"Drafted {layout.root}")
    return EXIT_OK


def _validate_revision_map(
    payload: dict[str, object], reviews: list[dict[str, object]]
) -> list[str]:
    if set(payload) != {"schema_version", "revisions"} or payload.get("schema_version") != "2.0":
        return ["revision map has invalid top-level contract"]
    revisions = payload.get("revisions")
    if not isinstance(revisions, list):
        return ["revision map revisions must be an array"]
    errors: list[str] = []
    target_actions = {
        str(review.get("target_sha256")): str(review.get("required_action"))
        for review in reviews if review.get("required_action") != "none"
    }
    applied: set[str] = set()
    fields = {"before_sha256", "after_sha256", "action", "status", "reason"}
    for index, revision in enumerate(revisions, start=1):
        if not isinstance(revision, dict) or set(revision) != fields:
            errors.append(f"revision {index} has invalid fields")
            continue
        before = str(revision.get("before_sha256", ""))
        if before not in target_actions:
            errors.append(f"revision {index} does not resolve a review action")
        elif revision.get("action") != target_actions[before]:
            errors.append(f"revision {index} action does not match review")
        if revision.get("status") != "applied":
            errors.append(f"revision {index} is not applied")
        applied.add(before)
    missing = sorted(set(target_actions) - applied)
    if missing:
        errors.append("required review revisions are not applied")
    return errors


def _validate_review_set(
    report: str,
    claims: list[dict[str, object]],
    claim_reviews: list[dict[str, object]],
    paragraph_reviews: list[dict[str, object]],
) -> list[str]:
    return validate_review_set(report, claims, claim_reviews, paragraph_reviews)


def _validate_conflict_review_set(
    contradictions: dict[str, object],
    reviews: list[dict[str, object]],
) -> list[str]:
    errors: list[str] = []
    if not reviews:
        return ["contradiction ledger lacks independent conflict review"]
    review_ids: set[str] = set()
    ledger_reviewed = False
    for index, review in enumerate(reviews, start=1):
        errors.extend(f"conflict review {index}: {item}" for item in validate_conflict_review_record(review))
        review_id = str(review.get("review_id", ""))
        if review_id in review_ids:
            errors.append(f"duplicate conflict review ID {review_id}")
        review_ids.add(review_id)
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


def _load_optional_jsonl(path: Path | None) -> list[dict[str, object]]:
    return [] if path is None else load_jsonl(path)


def _require_full_review_inputs(args: argparse.Namespace, brief: dict[str, object]) -> None:
    if not _is_full_external_dossier(brief):
        return
    missing = [
        name for name, value in (
            ("--fact-checks", args.fact_checks),
            ("--conflict-reviews", args.conflict_reviews),
            ("--draft-audit", args.draft_audit),
        ) if value is None
    ]
    if missing:
        raise CLIContractError("full_dossier review requires " + ", ".join(missing))


def _peer_review_markdown(summary: dict[str, object]) -> str:
    return (
        "# Peer Review\n\n"
        f"- Reviewer: {summary['reviewer_run_id']}\n"
        f"- Claim reviews: {summary['claim_reviews']}\n"
        f"- Paragraph audits: {summary['paragraph_reviews']}\n"
        f"- Fact checks: {summary.get('fact_checks', 0)}\n"
        f"- Conflict reviews: {summary.get('conflict_reviews', 0)}\n"
        f"- Draft audits: {summary.get('draft_audits', 0)}\n"
        f"- Decision: {summary['decision']}\n"
    )


def _promote_review_artifacts(
    layout: RunLayout,
    generation: int,
    report: str,
    paragraph_map: list[dict[str, object]],
    revision_map: dict[str, object],
    peer_review: dict[str, object],
) -> list[Path]:
    staging = package_child(
        layout.root, f"work/.staging/g{generation:04d}/review-{uuid.uuid4().hex}"
    )
    (staging / "research").mkdir(parents=True, exist_ok=False)
    atomic_write_text(staging / "report.md", report)
    atomic_write_text(
        staging / "research/reviewed-paragraph-map.jsonl", _jsonl_text(paragraph_map)
    )
    atomic_write_json(staging / "research/revision-map.json", revision_map)
    atomic_write_json(staging / "research/peer-review.json", peer_review)
    atomic_write_text(
        staging / "research/peer-review.md", _peer_review_markdown(peer_review["summary"])
    )
    relative_paths = [
        "report.md", "research/reviewed-paragraph-map.jsonl", "research/revision-map.json",
        "research/peer-review.json", "research/peer-review.md",
    ]
    outputs = []
    for relative in relative_paths:
        destination = layout.artifact(generation, relative)
        atomic_promote(staging / relative, destination)
        outputs.append(destination)
    (staging / "research").rmdir()
    staging.rmdir()
    return outputs


def command_review(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.REVIEW, package_hash)
    brief = verify_current_brief_view(layout, generation)
    _require_full_review_inputs(args, brief)
    report = args.revised_md.read_text(encoding="utf-8")
    paragraph_map = load_jsonl(args.revised_paragraph_map_jsonl)
    claim_reviews = load_jsonl(args.claim_reviews)
    paragraph_reviews = load_jsonl(args.report_audit)
    fact_checks = _load_optional_jsonl(args.fact_checks)
    conflict_reviews = _load_optional_jsonl(args.conflict_reviews)
    draft_audits = _load_optional_jsonl(args.draft_audit)
    revision_map = load_json(args.revision_map)
    claim_path = layout.artifact(generation, "research/claim-evidence-ledger.jsonl")
    source_path = layout.artifact(generation, "research/source-register.jsonl")
    contradiction_path = layout.artifact(generation, "research/contradiction-ledger.json")
    draft_path = layout.artifact(generation, "drafts/report-v1.md")
    draft_map_path = layout.artifact(generation, "research/paragraph-map.jsonl")
    claims = load_jsonl(claim_path)
    sources = load_jsonl(source_path)
    contradictions = load_json(contradiction_path)
    errors = validate_report_traceability(report, paragraph_map, claims, sources)
    errors.extend(_validate_review_set(report, claims, claim_reviews, paragraph_reviews))
    if fact_checks or draft_audits:
        errors.extend(_validate_review_set(report, claims, fact_checks, draft_audits))
    if conflict_reviews:
        errors.extend(_validate_conflict_review_set(contradictions, conflict_reviews))
    errors.extend(_validate_revision_map(
        revision_map,
        [*claim_reviews, *paragraph_reviews, *fact_checks, *draft_audits],
    ))
    if errors:
        raise ReviewGateError("; ".join(dict.fromkeys(errors)))
    reviewer_ids = sorted({
        str(review["reviewer_run_id"])
        for review in [*claim_reviews, *paragraph_reviews, *fact_checks, *draft_audits, *conflict_reviews]
    })
    summary = {
        "reviewer_run_id": ", ".join(reviewer_ids),
        "claim_reviews": len(claim_reviews),
        "paragraph_reviews": len(paragraph_reviews),
        "fact_checks": len(fact_checks),
        "conflict_reviews": len(conflict_reviews),
        "draft_audits": len(draft_audits),
        "decision": "passed",
    }
    peer_review = {
        "schema_version": "2.0",
        "summary": summary,
        "claim_reviews": claim_reviews,
        "paragraph_reviews": paragraph_reviews,
        "fact_checks": fact_checks,
        "conflict_reviews": conflict_reviews,
        "draft_audits": draft_audits,
    }
    outputs = _promote_review_artifacts(
        layout, generation, report, paragraph_map, revision_map, peer_review
    )
    commit_stage_receipt(
        layout,
        generation=generation,
        stage=Stage.REVIEW,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts={
            "artifacts/drafts/report-v1.md": sha256_file(draft_path),
            "artifacts/research/paragraph-map.jsonl": sha256_file(draft_map_path),
            "artifacts/research/claim-evidence-ledger.jsonl": sha256_file(claim_path),
            "artifacts/research/source-register.jsonl": sha256_file(source_path),
        },
        output_paths=outputs,
    )
    atomic_write_text(package_child(layout.root, "current/report.md"), report)
    atomic_write_json(package_child(layout.root, "current/research/peer-review.json"), peer_review)
    atomic_write_text(
        package_child(layout.root, "current/research/peer-review.md"),
        _peer_review_markdown(summary),
    )
    print(f"Reviewed {layout.root}")
    return EXIT_OK


def command_render(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.RENDER, package_hash)
    brief = verify_current_brief_view(layout, generation)
    report_path = layout.artifact(generation, "report.md")
    report = report_path.read_text(encoding="utf-8")
    staging = package_child(
        layout.root, f"work/.staging/g{generation:04d}/render-{uuid.uuid4().hex}"
    )
    try:
        result = export_report(
            report_path,
            staging,
            title=markdown_title(report),
            template_path=args.template,
            pandoc=args.pandoc,
            chrome=args.chrome,
            require_pdf=brief.get("output_mode") == "full",
            pdf_renderer=args.pdf_renderer,
        )
    except (OSError, RenderError, RuntimeError) as exc:
        raise RenderStageError(str(exc)) from exc
    exports_destination = layout.artifact(generation, "exports")
    validation_destination = layout.artifact(generation, "validation")
    atomic_promote(staging / "exports", exports_destination)
    atomic_promote(staging / "validation", validation_destination)
    staging.rmdir()
    html_path = exports_destination / result.html_path.name
    pdf_path = exports_destination / "report.pdf"
    manifest_path = validation_destination / result.manifest_path.name
    outputs = [html_path, manifest_path]
    if pdf_path.is_file():
        outputs.append(pdf_path)
    reviewed_map = layout.artifact(generation, "research/reviewed-paragraph-map.jsonl")
    peer_review = layout.artifact(generation, "research/peer-review.json")
    commit_stage_receipt(
        layout,
        generation=generation,
        stage=Stage.RENDER,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts={
            "artifacts/report.md": sha256_file(report_path),
            "artifacts/research/reviewed-paragraph-map.jsonl": sha256_file(reviewed_map),
            "artifacts/research/peer-review.json": sha256_file(peer_review),
        },
        output_paths=outputs,
    )
    current_exports = package_child(layout.root, "current/exports")
    current_validation = package_child(layout.root, "current/validation")
    current_exports.mkdir(parents=True, exist_ok=True)
    current_validation.mkdir(parents=True, exist_ok=True)
    for source, destination in (
        (html_path, current_exports / "report.html"),
        (manifest_path, current_validation / "render-manifest.json"),
    ):
        if destination.exists():
            destination.unlink()
        atomic_copy_file(source, destination)
    if pdf_path.is_file():
        destination = current_exports / "report.pdf"
        if destination.exists():
            destination.unlink()
        atomic_copy_file(pdf_path, destination)
    print(f"Rendered {layout.root} with {result.pdf_renderer}")
    return EXIT_OK


def command_validate(args: argparse.Namespace) -> int:
    checks, exit_code = validate_and_commit(args.run_dir)
    for check in checks:
        stream = sys.stderr if check.status == "fail" else sys.stdout
        print(f"[{check.status.upper()}] {check.check_id}: {check.message}", file=stream)
    return exit_code


def _collect_files(artifacts: Path) -> list[str]:
    candidates = [
        "report.md",
        "exports/report.html",
        "exports/report.pdf",
        "validation/validation-report.json",
        "validation/validation-report.md",
    ]
    return [relative for relative in candidates if (artifacts / relative).is_file()]


def command_collect(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.RELEASE, package_hash)
    artifacts = layout.generation_root(generation) / "artifacts"
    validation_report_path = layout.artifact(generation, "validation/validation-report.json")
    validation_report = load_json(validation_report_path)
    if not validation_report.get("ok"):
        raise CLIContractError("collect requires a passing validation report")
    public_checks, public_code = _public_safety_checks(artifacts)
    if public_code:
        failures = [
            f"{check.check_id}: {check.message}"
            for check in public_checks if check.status == "fail"
        ]
        raise CLIContractError("collect blocked by public safety checks: " + "; ".join(failures))
    target_root = args.to.expanduser()
    if target_root.exists() or target_root.is_symlink():
        raise OutputPathError(f"collect target already exists: {target_root}")
    target_root.mkdir(parents=True, exist_ok=False)
    copied: dict[str, str] = {}
    for relative in _collect_files(artifacts):
        source = artifacts / relative
        destination = package_child(target_root, relative)
        atomic_copy_file(source, destination)
        copied[relative] = sha256_file(destination)
    manifest = {
        "schema_version": "1.0",
        "run_dir": str(layout.root),
        "generation": generation,
        "source_validation_report_sha256": sha256_file(validation_report_path),
        "files": copied,
    }
    atomic_write_json(package_child(target_root, "collect-manifest.json"), manifest)
    print(json.dumps({
        "ok": True,
        "collected_to": str(target_root.resolve()),
        "files": copied,
    }, ensure_ascii=False, indent=2))
    return EXIT_OK


def command_release(args: argparse.Namespace) -> int:
    try:
        release = release_run(
            args.run_dir,
            trust_path=args.trust,
            registry_path=args.registry,
            approval_path=args.approval,
            reverification_path=args.reverification,
        )
    except (ContractError, OSError) as exc:
        raise ReleaseGateError(str(exc)) from exc
    print(f"Released {release}")
    return EXIT_OK


def _stage_values() -> tuple[str, ...]:
    return tuple(stage.value for stage in Stage)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _status_payload(run_dir: Path) -> dict[str, object]:
    layout = RunLayout(run_dir)
    generation = latest_generation(layout)
    if generation is None:
        return {
            "schema_version": "2.0",
            "run_dir": str(layout.root),
            "generation": None,
            "state": "empty",
            "last_valid_stage": None,
            "next_stage": "init",
            "invalid_stage": None,
            "error": None,
            "invalidated_artifacts": [],
            "receipts": [],
        }
    package_hash = compute_skill_package_hash(ROOT)
    status = receipt_chain_status(layout, generation, package_hash)
    return {
        "schema_version": "2.0",
        "run_dir": str(layout.root),
        **status,
    }


def _print_json(payload: dict[str, object]) -> None:
    sys.stdout.write(canonical_json_bytes(payload).decode("utf-8"))


def command_status(args: argparse.Namespace) -> int:
    _print_json(_status_payload(args.run_dir))
    return EXIT_OK


def command_explain(args: argparse.Namespace) -> int:
    status = _status_payload(args.run_dir)
    failed_stage = status.get("invalid_stage") or status.get("next_stage")
    error = status.get("error") or f"{failed_stage} has not been run"
    repair_command = (
        "run is already released"
        if failed_stage is None
        else f"storm-research retry {status['run_dir']} --stage {failed_stage}"
    )
    _print_json({
        "schema_version": "2.0",
        "run_dir": status["run_dir"],
        "generation": status["generation"],
        "state": status["state"],
        "failed_stage": failed_stage,
        "failed_checks": [] if failed_stage is None else [error],
        "invalidated_artifacts": status.get("invalidated_artifacts", []),
        "repair_command": repair_command,
    })
    return EXIT_OK


def _repair_actions_from_checks(checks: list[object], fallback_stage: object) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    for index, check in enumerate(checks, start=1):
        status = getattr(check, "status", "")
        if status != "fail":
            continue
        actions.append({
            "action_id": f"R{index:03d}",
            "stage": fallback_stage,
            "check_id": getattr(check, "check_id", ""),
            "path": getattr(check, "path", ""),
            "reason": getattr(check, "message", ""),
            "repair_command": getattr(check, "repair_command", ""),
        })
    return actions


def command_repair_plan(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    status = _status_payload(layout.root)
    generation = latest_generation(layout)
    checks: list[object] = []
    validation_exit_code = None
    if generation is not None:
        package_hash = compute_skill_package_hash(ROOT)
        try:
            checks, validation_exit_code = validate_governed_run(layout, generation, package_hash)
        except (ReceiptError, ContractError, OutputPathError, OSError, ValueError) as exc:
            validation_exit_code = EXIT_STAGE
            checks = []
            status["error"] = str(exc)
    failed_stage = status.get("invalid_stage") or status.get("next_stage")
    actions = _repair_actions_from_checks(checks, failed_stage)
    if not actions and failed_stage is not None:
        actions.append({
            "action_id": "R001",
            "stage": failed_stage,
            "check_id": "receipt-stage",
            "path": "state/generations/*/receipts/",
            "reason": status.get("error") or f"{failed_stage} has not been run",
            "repair_command": f"storm_research.py retry {layout.root} --stage {failed_stage}",
        })
    payload = {
        "schema_version": "2.0",
        "run_dir": str(layout.root),
        "generation": generation,
        "state": status.get("state"),
        "target_stage": failed_stage,
        "validation_exit_code": validation_exit_code,
        "actions": actions,
        "created_at": _utc_now(),
    }
    output = args.to or package_child(layout.root, "current/repair-plan.json")
    atomic_write_json(output, payload)
    _print_json(payload)
    return EXIT_OK


def command_retry(args: argparse.Namespace) -> int:
    status = _status_payload(args.run_dir)
    expected = status.get("next_stage")
    if expected is None:
        raise StagePreconditionError("run has no failed or pending stage to retry")
    if args.stage != expected:
        raise StagePreconditionError(
            f"retry must target current failed stage {expected}; got {args.stage}"
        )
    _print_json({
        "schema_version": "2.0",
        "run_dir": status["run_dir"],
        "generation": status["generation"],
        "retry_stage": args.stage,
        "accepted": True,
        "reason": status.get("error") or f"{args.stage} is the next required stage",
    })
    return EXIT_OK


def _amendment_digest(payload: dict[str, object]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "amendment_sha256"}
    return canonical_json_sha256(unsigned)


def command_amend(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    status = _status_payload(layout.root)
    if status.get("state") == "invalid":
        raise StagePreconditionError(f"cannot amend invalid receipt chain: {status.get('error')}")
    if status.get("last_valid_stage") == Stage.RELEASE.value:
        raise StagePreconditionError("released runs cannot be amended in place")
    changes_payload = load_json(args.changes_json)
    if not changes_payload:
        raise CLIContractError("amendment changes must be a non-empty object")
    brief = load_json(layout.generation_input(generation, "brief.json"))
    unknown = sorted(set(changes_payload) - set(brief))
    if unknown:
        raise CLIContractError("amendment references unknown brief fields: " + ", ".join(unknown))
    if (
        brief.get("depth_level") == "full_dossier"
        and brief.get("output_mode") == "full"
        and changes_payload.get("output_mode") == "reduced"
    ):
        raise StagePreconditionError("full dossier cannot be amended to reduced output")
    new_brief = dict(brief)
    changes: list[dict[str, object]] = []
    for field, after in sorted(changes_payload.items()):
        before = brief.get(field)
        if before == after:
            continue
        new_brief[field] = after
        changes.append({
            "field": field,
            "before": before,
            "after": after,
            "reason": args.reason,
        })
    if not changes:
        raise CLIContractError("amendment does not change the brief")
    validate_or_raise(validate_brief(new_brief))
    to_generation = generation + 1
    amendment = {
        "schema_version": "2.0",
        "run_id": layout.root.name,
        "from_generation": generation,
        "to_generation": to_generation,
        "changes": changes,
        "initiator": args.initiator,
        "user_approval_evidence": args.approval_evidence,
        "invalidation_start_stage": Stage.PLAN.value,
        "created_at": _utc_now(),
        "amendment_sha256": "0" * 64,
    }
    amendment["amendment_sha256"] = _amendment_digest(amendment)
    validate_or_raise(validate_amendment(amendment))
    package_hash = compute_skill_package_hash(ROOT)
    create_generation(layout, to_generation)
    brief_path = write_generation_input(layout, to_generation, "brief.json", new_brief)
    amendment_path = write_generation_input(layout, to_generation, "amendment.json", amendment)
    refresh_current_brief_view(layout, to_generation)
    commit_stage_receipt(
        layout,
        generation=to_generation,
        stage=Stage.INIT,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts={},
        output_paths=[brief_path, amendment_path],
    )
    print(f"Amended {layout.root} generation {to_generation}")
    return EXIT_OK


def command_import_legacy(args: argparse.Namespace) -> int:
    legacy = args.legacy_package.expanduser().resolve()
    if legacy.is_symlink() or not legacy.is_dir():
        raise CLIContractError(f"legacy package is missing or unsafe: {legacy}")
    brief = load_json(legacy / "brief.json")
    plan = load_json(legacy / "research/research-plan.json")
    source_plan = load_json(legacy / "research/source-plan.json")
    validate_or_raise(validate_brief(brief))
    validate_plan_bundle(plan, source_plan, brief)
    output = select_new_output_dir(
        str(brief.get("topic", "legacy-import")),
        workspace=args.workspace,
        output_root=args.output_root,
        output=args.output,
    )
    layout = create_run_layout(output)
    import_record = {
        "schema_version": "2.0",
        "status": "legacy_imported",
        "source_package_name": legacy.name,
        "imported_at": _utc_now(),
        "files": {
            "brief.json": sha256_file(legacy / "brief.json"),
            "research/research-plan.json": sha256_file(legacy / "research/research-plan.json"),
            "research/source-plan.json": sha256_file(legacy / "research/source-plan.json"),
        },
        "next_required_stage": Stage.RETRIEVAL.value,
    }
    package_hash = compute_skill_package_hash(ROOT)
    brief_path = write_generation_input(layout, 1, "brief.json", brief)
    import_path = write_generation_input(layout, 1, "legacy-import.json", import_record)
    refresh_current_brief_view(layout, 1)
    commit_stage_receipt(
        layout,
        generation=1,
        stage=Stage.INIT,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts={},
        output_paths=[brief_path, import_path],
    )
    tasklets = build_storm_tasklets(plan, source_plan)
    tasklet_errors = validate_storm_tasklets(tasklets, plan, source_plan)
    if tasklet_errors:
        raise CLIContractError("; ".join(dict.fromkeys(tasklet_errors)))
    plan_path, source_plan_path, tasklet_path = _promote_plan_artifacts(
        layout, 1, plan, source_plan, tasklets
    )
    commit_stage_receipt(
        layout,
        generation=1,
        stage=Stage.PLAN,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts={"inputs/brief.json": sha256_file(brief_path)},
        output_paths=[plan_path, source_plan_path, tasklet_path],
    )
    _refresh_current_plan_view(layout, plan, source_plan, tasklets)
    print(f"Imported legacy package into {layout.root}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a new governed research run.")
    init.add_argument("--topic", required=True)
    init.add_argument("--question", required=True)
    init.add_argument("--workspace", type=Path, default=Path.cwd())
    init.add_argument("--output-root", type=Path)
    init.add_argument("--output", type=Path)
    init.add_argument("--language", choices=("auto", "zh-CN", "en"), default="auto")
    init.add_argument("--depth-level", choices=("briefing", "standard_report", "full_dossier"), default="full_dossier")
    init.add_argument("--briefing-reason", default="")
    init.add_argument("--min-units", type=int)
    init.add_argument("--max-units", type=int)
    init.add_argument("--user-goal", default="Build an evidence-grounded answer")
    init.add_argument("--audience", default="General reader")
    init.add_argument("--geography", default="global")
    init.add_argument("--timeframe", default="current")
    init.add_argument("--source-policy", choices=("external_allowed", "closed_corpus", "primary_only"), default="external_allowed")
    init.add_argument("--as-of")
    init.add_argument("--max-age-days", type=int, default=365)
    init.add_argument("--retrieval-mode", choices=("host", "provider", "closed_corpus"), default="host")
    init.add_argument("--output-mode", choices=("full", "reduced"), default="full")
    init.add_argument("--uncertainty-tolerance", choices=("low", "medium", "high"), default="low")
    init.add_argument("--high-stakes", action="store_true")
    init.add_argument("--user-material", action="append", default=[])
    init.add_argument("--assumption", action="append", default=[])
    init.set_defaults(handler=command_init)

    plan = subparsers.add_parser("plan", help="Validate and commit research plans.")
    plan.add_argument("run_dir", type=Path)
    plan.add_argument("--plan-json", type=Path, required=True)
    plan.add_argument("--source-plan-json", type=Path, required=True)
    plan.set_defaults(handler=command_plan)

    ingest = subparsers.add_parser("ingest", help="Validate and commit captured retrieval evidence.")
    ingest.add_argument("run_dir", type=Path)
    ingest.add_argument("--input-jsonl", type=Path, required=True)
    ingest.set_defaults(handler=command_ingest)

    findings = subparsers.add_parser("findings", help="Validate and register STORM finding pool before evidence.")
    findings.add_argument("run_dir", type=Path)
    findings.add_argument("--findings-jsonl", type=Path, required=True)
    findings.set_defaults(handler=command_findings)

    evidence = subparsers.add_parser("evidence", help="Validate and commit Claims and report outline.")
    evidence.add_argument("run_dir", type=Path)
    evidence.add_argument("--claims", type=Path, required=True)
    evidence.add_argument("--contradictions", type=Path)
    evidence.add_argument("--uncertainties", type=Path)
    evidence.add_argument("--report-outline", type=Path)
    evidence.add_argument("--preflight-theory", action="store_true")
    evidence.set_defaults(handler=command_evidence)

    draft = subparsers.add_parser("draft", help="Validate and commit a traceable report draft.")
    draft.add_argument("run_dir", type=Path)
    draft.add_argument("--draft-md", type=Path, required=True)
    draft.add_argument("--paragraph-map-jsonl", type=Path, required=True)
    draft.add_argument("--preflight", action="store_true")
    draft.set_defaults(handler=command_draft)

    review = subparsers.add_parser("review", help="Apply independent semantic review.")
    review.add_argument("run_dir", type=Path)
    review.add_argument("--claim-reviews", type=Path, required=True)
    review.add_argument("--report-audit", type=Path, required=True)
    review.add_argument("--fact-checks", type=Path)
    review.add_argument("--conflict-reviews", type=Path)
    review.add_argument("--draft-audit", type=Path)
    review.add_argument("--revised-md", type=Path, required=True)
    review.add_argument("--revised-paragraph-map-jsonl", type=Path, required=True)
    review.add_argument("--revision-map", type=Path, required=True)
    review.set_defaults(handler=command_review)

    render = subparsers.add_parser("render", help="Render canonical Markdown to governed formats.")
    render.add_argument("run_dir", type=Path)
    render.add_argument("--template", type=Path, default=ROOT / "templates/report.html.j2")
    render.add_argument("--pandoc", default="pandoc")
    render.add_argument("--pdf-renderer", choices=("auto", "weasyprint", "chromium", "none"), default="auto")
    render.add_argument("--chrome", type=Path, default=DEFAULT_CHROME)
    render.set_defaults(handler=command_render)

    validate = subparsers.add_parser("validate", help="Recompute all offline governed gates.")
    validate.add_argument("run_dir", type=Path)
    validate.set_defaults(handler=command_validate)

    collect = subparsers.add_parser("collect", help="Copy validated local deliverables without creating a release.")
    collect.add_argument("run_dir", type=Path)
    collect.add_argument("--to", type=Path, required=True)
    collect.set_defaults(handler=command_collect)

    release = subparsers.add_parser("release", help="Build a Trust-approved public release package.")
    release.add_argument("run_dir", type=Path)
    release.add_argument("--trust", type=Path)
    release.add_argument("--registry", type=Path)
    release.add_argument("--approval", type=Path)
    release.add_argument("--reverification", type=Path)
    release.set_defaults(handler=command_release)

    amend = subparsers.add_parser("amend", help="Create a new generation from an approved brief amendment.")
    amend.add_argument("run_dir", type=Path)
    amend.add_argument("--changes-json", type=Path, required=True)
    amend.add_argument("--initiator", required=True)
    amend.add_argument("--approval-evidence", required=True)
    amend.add_argument("--reason", default="User-approved scope amendment")
    amend.set_defaults(handler=command_amend)

    retry = subparsers.add_parser("retry", help="Authorize retry of the current failed or pending stage.")
    retry.add_argument("run_dir", type=Path)
    retry.add_argument("--stage", choices=_stage_values(), required=True)
    retry.set_defaults(handler=command_retry)

    status = subparsers.add_parser("status", help="Report the latest valid governed receipt chain.")
    status.add_argument("run_dir", type=Path)
    status.set_defaults(handler=command_status)

    explain = subparsers.add_parser("explain", help="Explain the first failed or pending governed stage.")
    explain.add_argument("run_dir", type=Path)
    explain.set_defaults(handler=command_explain)

    repair_plan = subparsers.add_parser("repair-plan", help="Write structured repair actions for the current failing gate.")
    repair_plan.add_argument("run_dir", type=Path)
    repair_plan.add_argument("--to", type=Path)
    repair_plan.set_defaults(handler=command_repair_plan)

    legacy = subparsers.add_parser("import-legacy", help="Import a 0.4.x package without fabricating retrieval evidence.")
    legacy.add_argument("--legacy-package", type=Path, required=True)
    legacy.add_argument("--workspace", type=Path, default=Path.cwd())
    legacy.add_argument("--output-root", type=Path)
    legacy.add_argument("--output", type=Path)
    legacy.set_defaults(handler=command_import_legacy)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (StagePreconditionError, ReceiptError) as exc:
        print(f"Stage failed: {exc}", file=sys.stderr)
        return EXIT_STAGE
    except (RetrievalGateError, EvidenceGateError, DraftGateError, ReviewGateError) as exc:
        print(f"Evidence failed: {exc}", file=sys.stderr)
        return EXIT_EVIDENCE
    except RenderStageError as exc:
        print(f"Render failed: {exc}", file=sys.stderr)
        return EXIT_EXPORT
    except ReleaseGateError as exc:
        print(f"Release blocked: {exc}", file=sys.stderr)
        return EXIT_RELEASE
    except (CLIContractError, ContractError, OutputPathError, OSError) as exc:
        print(f"Contract failed: {exc}", file=sys.stderr)
        return EXIT_CONTRACT


if __name__ == "__main__":
    raise SystemExit(main())
