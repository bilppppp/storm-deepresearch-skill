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
    validate_brief,
    validate_research_plan,
    validate_source_plan,
)
from scripts.harness_io import (
    atomic_promote,
    atomic_write_json,
    compute_skill_package_hash,
    sha256_file,
)
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


SCRIPT_INTERFACE = "cli"
SCRIPT_INTERFACE_REASON = "The only supported public command surface for governed research stages."
ROOT = Path(__file__).resolve().parents[1]
EXIT_OK = 0
EXIT_CONTRACT = 4
EXIT_STAGE = 8


class CLIContractError(ValueError):
    """Raised when caller input does not satisfy a governed stage contract."""


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
        outline = plan.get("report_outline") if isinstance(plan.get("report_outline"), dict) else {}
        sections = outline.get("sections") if isinstance(outline.get("sections"), list) else []
        if len(set(perspectives)) < 5:
            errors.append("full_dossier requires at least five perspectives")
        if len(questions) < 10:
            errors.append("full_dossier requires at least ten research questions")
        if len(sections) < 6:
            errors.append("full_dossier requires at least six planned sections")
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (StagePreconditionError, ReceiptError) as exc:
        print(f"Stage failed: {exc}", file=sys.stderr)
        return EXIT_STAGE
    except (CLIContractError, ContractError, OutputPathError, OSError) as exc:
        print(f"Contract failed: {exc}", file=sys.stderr)
        return EXIT_CONTRACT


if __name__ == "__main__":
    raise SystemExit(main())
