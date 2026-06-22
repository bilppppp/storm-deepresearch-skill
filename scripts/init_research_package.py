#!/usr/bin/env python3
"""Initialize an explicit, empty STORM DeepResearch output package."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

try:
    from .output_paths import OutputPathError, select_new_output_dir
except ImportError:
    from output_paths import OutputPathError, select_new_output_dir


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def initialize(
    topic: str,
    question: str,
    output: Path,
    *,
    language: str = "auto",
    depth_level: str = "full_dossier",
    minimum_units: int | None = None,
    maximum_units: int | None = None,
) -> None:
    if output.exists():
        raise OutputPathError(f"output directory already exists: {output}")
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise OutputPathError(f"output directory already exists: {output}") from exc
    research = output / "research"
    exports = output / "exports"
    validation = output / "validation"
    for directory in (research, exports, validation):
        directory.mkdir()
    today = date.today().isoformat()
    report_language = infer_language(topic, question, language)
    length_contract = default_length_contract(report_language, depth_level)
    if minimum_units is not None:
        length_contract["minimum"] = minimum_units
    if maximum_units is not None:
        length_contract["maximum"] = maximum_units
    minimum = int(length_contract["minimum"])
    maximum = int(length_contract["maximum"])
    if minimum > maximum:
        raise ValueError("minimum_units cannot exceed maximum_units")
    length_contract["target"] = (minimum + maximum) // 2
    write_json(output / "brief.json", {
        "schema_version": "1.0",
        "package_state": "initialized",
        "topic": topic,
        "research_question": question,
        "user_goal": "Build an evidence-grounded answer",
        "audience": "General reader",
        "decision_context": "",
        "depth_level": depth_level,
        "report_language": report_language,
        "length_contract": length_contract,
        "geography": "global",
        "timeframe": "current",
        "source_policy": "external_allowed",
        "freshness_policy": {"as_of": today, "max_age_days": 365},
        "retrieval_mode": "host",
        "output_mode": "full",
        "uncertainty_tolerance": "low",
        "user_materials": [],
        "assumptions": [],
    })
    write_json(research / "research-plan.json", {
        "schema_version": "1.0", "status": "initialized", "perspectives": [], "questions": [],
        "source_priorities": [], "stopping_conditions": [],
        "retrieval_budget": {"max_queries": 20, "max_sources": 40},
        "report_outline": {
            "status": "initialized",
            "unit": length_contract["unit"],
            "minimum": length_contract["minimum"],
            "target": length_contract["target"],
            "maximum": length_contract["maximum"],
            "sections": [],
        },
    })
    (research / "source-register.jsonl").write_text("", encoding="utf-8")
    (research / "claim-evidence-ledger.jsonl").write_text("", encoding="utf-8")
    write_json(research / "report-claim-map.json", {"schema_version": "1.0", "mappings": []})
    write_json(research / "contradiction-ledger.json", {"schema_version": "1.0", "conflicts": []})
    (research / "source-register.md").write_text("# Source Register\n\nNo sources registered.\n", encoding="utf-8")
    (research / "evidence-map.md").write_text("# Evidence Map\n\nNo claims registered.\n", encoding="utf-8")
    (research / "perspective-questions.md").write_text("# Perspective Questions\n\nResearch planning has not started.\n", encoding="utf-8")
    (research / "contradiction-map.md").write_text("# Contradiction Map\n\nNo conflicts assessed.\n", encoding="utf-8")
    (research / "uncertainty-ledger.md").write_text("# Uncertainty Ledger\n\nEvidence collection has not started.\n", encoding="utf-8")
    (research / "peer-review.md").write_text("# Peer Review\n\nA draft is not available for review.\n", encoding="utf-8")
    (output / "report.md").write_text(f"# {topic}\n\nResearch has not started.\n", encoding="utf-8")
    write_json(validation / "validation-report.json", {
        "schema_version": "1.0", "ok": False, "package_state": "initialized", "checks": [],
        "summary": {"passed": 0, "warnings": 0, "failed": 0},
    })
    (validation / "validation-report.md").write_text("# Validation Report\n\nPackage initialized; release validation has not run.\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="User workspace used for the default output root (default: current directory).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help="Approved output root (default: <workspace>/output/storm-deepresearch).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="New run directory name inside the output root, or an absolute child of that root.",
    )
    parser.add_argument("--language", choices=("auto", "zh-CN", "en"), default="auto")
    parser.add_argument(
        "--depth-level",
        choices=("briefing", "standard_report", "full_dossier"),
        default="full_dossier",
    )
    parser.add_argument("--min-units", type=int)
    parser.add_argument("--max-units", type=int)
    args = parser.parse_args()
    try:
        output = select_new_output_dir(
            args.topic.strip(),
            workspace=args.workspace,
            output_root=args.output_root,
            output=args.output,
        )
        initialize(
            args.topic.strip(),
            args.question.strip(),
            output,
            language=args.language,
            depth_level=args.depth_level,
            minimum_units=args.min_units,
            maximum_units=args.max_units,
        )
    except (OutputPathError, OSError, ValueError) as exc:
        print(f"Initialization failed: {exc}", file=sys.stderr)
        return 4
    print(f"Initialized {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
