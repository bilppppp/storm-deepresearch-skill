#!/usr/bin/env python3
"""Run the governed STORM DeepResearch stage harness."""
from __future__ import annotations

import argparse
import re
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Sequence

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
from scripts.harness_io import (
    atomic_promote,
    atomic_write_text,
    atomic_write_json,
    canonical_json_bytes,
    compute_skill_package_hash,
    sha256_file,
)
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
    verify_stage_precondition,
)
from scripts.source_evidence import SourceEvidenceError, resolve_snapshot
from scripts.validate_evidence import validate_claim_closure


SCRIPT_INTERFACE = "cli"
SCRIPT_INTERFACE_REASON = "The only supported public command surface for governed research stages."
ROOT = Path(__file__).resolve().parents[1]
EXIT_OK = 0
EXIT_CONTRACT = 4
EXIT_EVIDENCE = 5
EXIT_STAGE = 8


class CLIContractError(ValueError):
    """Raised when caller input does not satisfy a governed stage contract."""


class RetrievalGateError(ValueError):
    """Raised when captured retrieval evidence cannot close the plan."""


class EvidenceGateError(ValueError):
    """Raised when Claims and outline do not form a closed evidence set."""


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
    return {
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
    )
    print(f"Initialized {output}")
    return EXIT_OK


def validate_plan_bundle(
    plan: dict[str, object], source_plan: dict[str, object], brief: dict[str, object]
) -> None:
    errors = validate_research_plan(plan, brief, set())
    errors.extend(validate_source_plan(source_plan))
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


def _promote_plan_artifacts(
    layout: RunLayout,
    generation: int,
    plan: dict[str, object],
    source_plan: dict[str, object],
) -> tuple[Path, Path]:
    staging = package_child(
        layout.root, f"work/.staging/g{generation:04d}/plan-{uuid.uuid4().hex}"
    )
    staging.mkdir(parents=True, exist_ok=False)
    staged_plan = staging / "research-plan.json"
    staged_source_plan = staging / "source-plan.json"
    atomic_write_json(staged_plan, plan)
    atomic_write_json(staged_source_plan, source_plan)
    plan_path = layout.artifact(generation, "research/research-plan.json")
    source_plan_path = layout.artifact(generation, "research/source-plan.json")
    atomic_promote(staged_plan, plan_path)
    atomic_promote(staged_source_plan, source_plan_path)
    staging.rmdir()
    return plan_path, source_plan_path


def _refresh_current_plan_view(
    layout: RunLayout, plan: dict[str, object], source_plan: dict[str, object]
) -> None:
    root = package_child(layout.root, "current/research")
    atomic_write_json(root / "research-plan.json", plan)
    atomic_write_json(root / "source-plan.json", source_plan)


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
    plan_path, source_plan_path = _promote_plan_artifacts(
        layout, generation, plan, source_plan
    )
    brief_path = layout.generation_input(generation, "brief.json")
    commit_stage_receipt(
        layout,
        generation=generation,
        stage=Stage.PLAN,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts={"inputs/brief.json": sha256_file(brief_path)},
        output_paths=[plan_path, source_plan_path],
    )
    _refresh_current_plan_view(layout, plan, source_plan)
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
        contradictions = load_json(args.contradictions)
        uncertainties = load_json(args.uncertainties)
        outline = load_json(args.report_outline)
    except (ContractError, ValueError) as exc:
        raise EvidenceGateError(str(exc)) from exc
    research_plan_path = layout.artifact(generation, "research/research-plan.json")
    source_path = layout.artifact(generation, "research/source-register.jsonl")
    manifest_path = layout.artifact(generation, "research/retrieval-manifest.jsonl")
    research_plan = load_json(research_plan_path)
    sources = load_jsonl(source_path)
    manifests = load_jsonl(manifest_path)
    question_ids = {
        str(item.get("question_id"))
        for item in research_plan.get("questions", [])
        if isinstance(item, dict)
    }
    claim_ids = {str(item.get("claim_id")) for item in claims}
    errors = validate_report_outline(outline, brief, question_ids, claim_ids)
    errors.extend(validate_claim_closure(claims, sources, outline, manifests))
    errors.extend(_validate_contradictions(contradictions, claims))
    errors.extend(_validate_uncertainties(uncertainties))
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
    commit_stage_receipt(
        layout,
        generation=generation,
        stage=Stage.EVIDENCE,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts={
            "artifacts/research/research-plan.json": sha256_file(research_plan_path),
            "artifacts/research/source-register.jsonl": sha256_file(source_path),
            "artifacts/research/retrieval-manifest.jsonl": sha256_file(manifest_path),
        },
        output_paths=outputs,
    )
    _refresh_current_evidence_view(layout, claims, contradictions, uncertainties, outline)
    print(f"Closed {len(claims)} Claims in {layout.root}")
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

    evidence = subparsers.add_parser("evidence", help="Validate and commit Claims and report outline.")
    evidence.add_argument("run_dir", type=Path)
    evidence.add_argument("--claims", type=Path, required=True)
    evidence.add_argument("--contradictions", type=Path, required=True)
    evidence.add_argument("--uncertainties", type=Path, required=True)
    evidence.add_argument("--report-outline", type=Path, required=True)
    evidence.set_defaults(handler=command_evidence)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (StagePreconditionError, ReceiptError) as exc:
        print(f"Stage failed: {exc}", file=sys.stderr)
        return EXIT_STAGE
    except (RetrievalGateError, EvidenceGateError) as exc:
        print(f"Evidence failed: {exc}", file=sys.stderr)
        return EXIT_EVIDENCE
    except (CLIContractError, ContractError, OutputPathError, OSError) as exc:
        print(f"Contract failed: {exc}", file=sys.stderr)
        return EXIT_CONTRACT


if __name__ == "__main__":
    raise SystemExit(main())
