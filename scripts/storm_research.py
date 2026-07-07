#!/usr/bin/env python3
"""Run the governed STORM DeepResearch stage harness."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import shutil
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contract_io import (
    ContractError,
    MAX_REVIEW_ROLES,
    REVIEW_ISSUE_STAGE,
    load_json,
    load_jsonl,
    max_review_rubric_binding,
    validate_amendment,
    validate_brief,
    validate_conflict_review_record,
    validate_finding_record,
    validate_report_outline,
    validate_research_plan,
    validate_tasklet_record,
    validate_storm_review_analysis,
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
from scripts.normalize_retrieval import (
    independent_source_identity,
    normalize_retrieval_records,
    validate_captured_retrieval_artifacts,
    validate_retrieval_audit as validate_retrieval_audit_contract,
)
from scripts.merge_claim_ledger import merge_claim_records
from scripts.output_paths import OutputPathError, package_child, select_new_output_dir
from scripts.run_state import (
    ReceiptError,
    RunLayout,
    Stage,
    StagePreconditionError,
    append_journal_event,
    commit_stage_receipt,
    create_generation,
    latest_generation,
    receipt_chain_status,
    verify_stage_precondition,
)
from scripts.report_traceability import (
    body_length,
    cited_sources_in_body,
    citation_index,
    extract_paragraphs,
    generate_references,
    has_handwritten_references,
    mapping_directives,
    quote_limit_errors,
    quoted_length,
    strip_mapping_comments,
    validate_paragraph_record,
    validate_report_traceability,
    validate_review_set,
)
from scripts.source_evidence import (
    SourceEvidenceError,
    capture_retrieval_evidence,
    normalized_snapshot_text,
    resolve_snapshot,
)
from scripts.validate_evidence import (
    validate_absence_searches,
    validate_claim_closure,
    validate_material_capture_depth,
)
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
ASSURANCE_TARGETS = {"artifact_contract", "captured_host_execution"}
RUN_INTENTS = {"user_delivery", "diagnostic_rehearsal"}
MAXIMAL_COMPLETENESS_CONTRACT = {
    "completion_policy": "coverage_and_saturation",
    "discovery_surface_policy": "domain_adaptive_with_mandatory_counterevidence",
    "surface_applicability_required": True,
    "tasklet_closure_required": True,
    "storm_gap_closure_required": True,
    "material_novelty_window": 2,
    "final_integrity_required": True,
    "review_policy": "concern_driven_until_clear",
}
AUDIT_BOILERPLATE_PATTERNS = (
    re.compile(r"这条可审计来源"),
    re.compile(r"该段把这条公开引用定位为证据图谱"),
    re.compile(r"this auditable source", re.IGNORECASE),
    re.compile(r"this source record", re.IGNORECASE),
)
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
STORM_LENS_PROMPT_PACK = ROOT / "references/storm-lens-prompt-pack.md"
STORM_LENS_FILES = {
    "P1": ("storm-lens-perspectives.json", "before_retrieval"),
    "P2": ("storm-lens-conflicts.json", "after_findings"),
    "P3": ("storm-lens-outline.json", "after_conflicts"),
    "P4": ("storm-lens-red-team.json", "after_draft"),
}
STORM_LENS_OUTPUT_FIELDS = {
    "P1": {"perspectives", "question_ids", "source_class_ids", "notes"},
    "P2": {"finding_ids", "conflict_claim_ids", "consensus_candidates", "blind_spots", "resolver_questions", "resolution_actions"},
    "P3": {"section_ids", "claim_ids", "finding_ids", "contradiction_ids", "uncertainty_ids", "length_budget_note"},
    "P4": {"target_kind", "target_sha256", "weakest_claim_ids", "overstated_paragraphs", "missing_perspectives", "citation_support_issues", "repair_actions"},
}
INIT_RESEARCH_PROFILES = {
    "auto",
    "default_full_dossier",
    "maximal_full_dossier",
    "strict_storm_lens",
    "critique_deepresearch",
    "closed_corpus",
    "briefing",
    "repair_existing_run",
}
BRIEF_RESEARCH_PROFILES = {
    "default_full_dossier",
    "maximal_full_dossier",
    "critique_deepresearch",
    "closed_corpus",
    "briefing",
    "custom",
}
LEGACY_RESEARCH_PROFILE_ALIASES = {
    "strict_storm_lens": "default_full_dossier",
}
PROFILE_SELECTION_MODES = {
    "user_selected",
    "user_requested_default",
    "defaulted_after_prompt",
}
BAD_CAPTURE_MARKERS = {
    "checking if the site connection is secure",
    "access denied",
    "enable javascript",
    "just a moment",
    "please enable cookies",
    "403 forbidden",
    "载入中",
    "正在加载",
    "请稍候",
    "访问被拒绝",
}
CAPTURE_MIN_NORMALIZED_CHARS = 80
CRITIQUE_SEARCH_DIMENSIONS = {
    "user_claim": (
        "user claim", "user argument", "supplied interpretation", "viewer claim",
        "观后感", "用户观点", "原始观点", "评论观点", "论点抽取",
    ),
    "support": (
        "support", "supporting evidence", "evidence for", "confirm", "supports",
        "支持证据", "正方证据", "印证", "佐证",
    ),
    "counterevidence": (
        "counter", "contradict", "against", "weakest evidence", "alternative reading",
        "反证", "反驳", "矛盾", "相反证据", "不同解读",
    ),
    "theory_framework": (
        "theory", "framework", "academic", "scholar", "concept", "criticism",
        "理论", "框架", "学术", "概念", "批评理论",
    ),
    "reception_criticism": (
        "reception", "review", "critic", "audience", "discourse", "debate",
        "评论", "影评", "接受史", "观众", "争议", "讨论",
    ),
    "historical_comparison": (
        "historical", "history", "precedent", "comparison", "similar pattern", "blind spot",
        "历史", "先例", "比较", "同类", "类似模式", "盲点",
    ),
}
PROFILE_DEFAULTS = {
    "default_full_dossier": {
        "depth_level": "full_dossier",
        "source_policy": "external_allowed",
        "retrieval_mode": "host",
        "output_mode": "full",
        "storm_lens_mode": "strict",
    },
    "maximal_full_dossier": {
        "depth_level": "full_dossier",
        "source_policy": "external_allowed",
        "retrieval_mode": "host",
        "output_mode": "full",
        "storm_lens_mode": "strict",
    },
    "critique_deepresearch": {
        "depth_level": "full_dossier",
        "source_policy": "external_allowed",
        "retrieval_mode": "host",
        "output_mode": "full",
        "storm_lens_mode": "strict",
    },
    "closed_corpus": {
        "depth_level": "full_dossier",
        "source_policy": "closed_corpus",
        "retrieval_mode": "closed_corpus",
        "output_mode": "full",
        "storm_lens_mode": "advisory",
    },
    "briefing": {
        "depth_level": "briefing",
        "source_policy": "external_allowed",
        "retrieval_mode": "host",
        "output_mode": "full",
        "storm_lens_mode": "advisory",
    },
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


def infer_language(
    topic: str, question: str, requested: str, *, research_profile: str = "auto"
) -> str:
    if requested != "auto":
        return requested
    if research_profile == "maximal_full_dossier":
        return "zh-CN"
    return "zh-CN" if re.search(r"[\u3400-\u9fff]", topic + question) else "en"


def default_length_contract(
    language: str, depth_level: str, *, policy: str = "bounded"
) -> dict[str, object]:
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
    if policy == "open_ended":
        return {
            "unit": unit,
            "policy": "open_ended",
            "content_standard": "evidence_led",
        }
    minimum, target, maximum = ranges[depth_level]
    return {
        "unit": unit,
        "policy": "bounded",
        "minimum": minimum,
        "target": target,
        "maximum": maximum,
        "content_standard": "evidence_led",
    }


def _profile_value(args: argparse.Namespace, field: str, profile: str) -> str:
    explicit = getattr(args, field, None)
    if profile == "auto":
        fallback = {
            "depth_level": "full_dossier",
            "source_policy": "external_allowed",
            "retrieval_mode": "host",
            "output_mode": "full",
            "storm_lens_mode": "strict",
        }[field]
        return str(explicit or fallback)
    if profile == "briefing" and field == "output_mode" and explicit in {"full", "reduced"}:
        return str(explicit)
    expected = str(PROFILE_DEFAULTS[profile][field])
    if explicit is not None and explicit != expected:
        flag = field.replace("_", "-")
        raise CLIContractError(f"--{flag} conflicts with --research-profile {profile}; expected {expected}")
    return expected


def _derived_research_profile(values: dict[str, str]) -> str:
    for profile, defaults in PROFILE_DEFAULTS.items():
        if all(values[key] == expected for key, expected in defaults.items()):
            return profile
    return "custom"


def _profile_prompt_file(args: argparse.Namespace) -> Path | None:
    prompt_file = getattr(args, "profile_prompt_file", None)
    if prompt_file is None:
        return None
    path = Path(prompt_file).expanduser()
    if path.is_symlink() or not path.is_file():
        raise CLIContractError("--profile-prompt-file must be a regular file")
    if not path.read_text(encoding="utf-8").strip():
        raise CLIContractError("--profile-prompt-file must not be empty")
    return path


def _profile_selection_evidence_file(args: argparse.Namespace) -> Path | None:
    evidence_file = getattr(args, "profile_selection_evidence_file", None)
    if evidence_file is None:
        return None
    path = Path(evidence_file).expanduser()
    if path.is_symlink() or not path.is_file():
        raise CLIContractError("--profile-selection-evidence-file must be a regular file")
    if not path.read_text(encoding="utf-8").strip():
        raise CLIContractError("--profile-selection-evidence-file must not be empty")
    return path


def build_brief_v2(args: argparse.Namespace) -> dict[str, object]:
    topic = args.topic.strip()
    question = args.question.strip()
    requested_profile = str(getattr(args, "research_profile", "auto") or "auto")
    if requested_profile not in INIT_RESEARCH_PROFILES:
        raise CLIContractError("research_profile is invalid")
    if requested_profile == "repair_existing_run":
        raise CLIContractError("repair_existing_run uses status/explain/retry on an existing run; do not call init")
    profile = LEGACY_RESEARCH_PROFILE_ALIASES.get(requested_profile, requested_profile)
    if profile == "auto" and getattr(args, "depth_level", None) == "briefing":
        profile = "briefing"
    values = {
        "depth_level": _profile_value(args, "depth_level", profile),
        "source_policy": _profile_value(args, "source_policy", profile),
        "retrieval_mode": _profile_value(args, "retrieval_mode", profile),
        "output_mode": _profile_value(args, "output_mode", profile),
        "storm_lens_mode": _profile_value(args, "storm_lens_mode", profile),
    }
    effective_profile = _derived_research_profile(values) if profile == "auto" else profile
    language = infer_language(
        topic, question, args.language, research_profile=effective_profile
    )
    briefing_reason = str(getattr(args, "briefing_reason", "") or "").strip()
    if values["depth_level"] == "briefing" and not briefing_reason:
        raise CLIContractError("briefing depth requires --briefing-reason with explicit user request evidence")
    if values["depth_level"] != "briefing" and briefing_reason:
        raise CLIContractError("--briefing-reason is only valid with --depth-level briefing")
    profile_selection_mode = str(getattr(args, "profile_selection_mode", "") or "").strip()
    profile_selection_evidence = str(getattr(args, "profile_selection_evidence", "") or "").strip()
    if profile_selection_mode not in PROFILE_SELECTION_MODES:
        raise CLIContractError(
            "profile selection requires --profile-selection-mode "
            "(user_selected, user_requested_default, or defaulted_after_prompt)"
        )
    if not profile_selection_evidence:
        raise CLIContractError("profile selection requires --profile-selection-evidence")
    prompt_file = _profile_prompt_file(args)
    if profile_selection_mode == "defaulted_after_prompt" and prompt_file is None:
        raise CLIContractError(
            "defaulted_after_prompt requires --profile-prompt-file with the actual menu shown to the user"
        )
    if profile_selection_mode != "defaulted_after_prompt" and prompt_file is not None:
        raise CLIContractError("--profile-prompt-file is only valid with defaulted_after_prompt")
    assurance_target = str(getattr(args, "assurance_target", "") or "").strip()
    if assurance_target not in ASSURANCE_TARGETS:
        raise CLIContractError(
            "init requires --assurance-target artifact_contract or captured_host_execution"
        )
    run_intent = str(getattr(args, "run_intent", "user_delivery") or "user_delivery").strip()
    if run_intent not in RUN_INTENTS:
        raise CLIContractError("run_intent is invalid")
    evidence_file = _profile_selection_evidence_file(args)
    if assurance_target == "captured_host_execution" and evidence_file is None:
        raise CLIContractError(
            "captured_host_execution profile selection requires --profile-selection-evidence-file"
        )
    length_policy = "open_ended" if effective_profile == "maximal_full_dossier" else "bounded"
    if length_policy == "open_ended" and (args.min_units is not None or args.max_units is not None):
        raise CLIContractError("maximal_full_dossier uses open-ended length; do not pass --min-units or --max-units")
    length_contract = default_length_contract(language, values["depth_level"], policy=length_policy)
    length_overridden = args.min_units is not None or args.max_units is not None
    if length_policy == "bounded":
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
    profile_selection: dict[str, object] = {
        "mode": profile_selection_mode,
        "selected_profile": effective_profile,
        "evidence": profile_selection_evidence,
        "available_profiles": sorted(BRIEF_RESEARCH_PROFILES),
    }
    if prompt_file is not None:
        profile_selection.update({
            "prompt_ref": "inputs/profile-selection-prompt.txt",
            "prompt_sha256": sha256_file(prompt_file),
        })
    if evidence_file is not None:
        profile_selection.update({
            "evidence_ref": "inputs/profile-selection-evidence.txt",
            "evidence_sha256": sha256_file(evidence_file),
        })
    brief = {
        "schema_version": "2.0",
        "topic": topic,
        "research_question": question,
        "user_goal": args.user_goal,
        "audience": args.audience,
        "research_profile": effective_profile,
        "profile_selection": profile_selection,
        "assurance_target": assurance_target,
        "run_intent": run_intent,
        "depth_level": values["depth_level"],
        "report_language": language,
        "length_contract": length_contract,
        "geography": args.geography,
        "timeframe": args.timeframe,
        "source_policy": values["source_policy"],
        "freshness_policy": {
            "as_of": args.as_of or date.today().isoformat(),
            "max_age_days": args.max_age_days,
        },
        "retrieval_mode": values["retrieval_mode"],
        "output_mode": values["output_mode"],
        "storm_lens_mode": values["storm_lens_mode"],
        "uncertainty_tolerance": args.uncertainty_tolerance,
        "high_stakes": args.high_stakes,
        "user_materials": list(args.user_material),
        "assumptions": list(args.assumption),
    }
    if effective_profile == "critique_deepresearch" and not any(
        "critique_deepresearch profile" in item for item in brief["assumptions"]
    ):
        brief["assumptions"].append(
            "critique_deepresearch profile: extract researchable claims from the user's interpretation before background lookup."
        )
    if effective_profile == "maximal_full_dossier":
        brief["maximal_completeness_contract"] = dict(MAXIMAL_COMPLETENESS_CONTRACT)
    if briefing_reason:
        brief["briefing_reason"] = briefing_reason
    return brief


def validate_or_raise(errors: list[str]) -> None:
    if errors:
        raise CLIContractError("; ".join(errors))


def _storm_lens_mode(brief: dict[str, object]) -> str:
    return str(brief.get("storm_lens_mode", "advisory"))


def _storm_lens_artifact_path(layout: RunLayout, generation: int, prompt_id: str) -> Path:
    return layout.artifact(generation, f"research/{STORM_LENS_FILES[prompt_id][0]}")


def _storm_lens_logical_path(prompt_id: str) -> str:
    return f"artifacts/research/{STORM_LENS_FILES[prompt_id][0]}"


def _is_sha256(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value)))


def _is_iso_datetime(value: object) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _string_list(value: object, field: str, *, pattern: str | None = None) -> list[str]:
    if not isinstance(value, list):
        return [f"{field} must be an array"]
    errors: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{field} must contain non-empty strings")
            break
        if pattern and not re.fullmatch(pattern, item):
            errors.append(f"{field} contains invalid ID: {item}")
            break
    return errors


def validate_storm_lens_artifact(
    payload: dict[str, Any],
    *,
    prompt_id: str,
    expected_inputs: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    expected_fields = {
        "schema_version", "prompt_id", "prompt_pack_sha256", "phase",
        "input_artifacts", "output", "created_at",
    }
    if set(payload) != expected_fields:
        errors.append("storm lens artifact has invalid top-level fields")
        return errors
    if payload.get("schema_version") != "2.0":
        errors.append("storm lens artifact schema_version must be 2.0")
    if payload.get("prompt_id") != prompt_id:
        errors.append(f"storm lens artifact prompt_id must be {prompt_id}")
    if payload.get("phase") != STORM_LENS_FILES[prompt_id][1]:
        errors.append(f"storm lens artifact phase must be {STORM_LENS_FILES[prompt_id][1]}")
    if payload.get("prompt_pack_sha256") != sha256_file(STORM_LENS_PROMPT_PACK):
        errors.append("storm lens artifact prompt_pack_sha256 does not match prompt pack")
    inputs = payload.get("input_artifacts")
    if not isinstance(inputs, dict) or set(inputs) != set(expected_inputs):
        errors.append("storm lens artifact input_artifacts do not match required phase inputs")
    elif any(inputs[path] != digest for path, digest in expected_inputs.items()):
        errors.append("storm lens artifact input_artifacts hash mismatch")
    output = payload.get("output")
    if not isinstance(output, dict) or set(output) != STORM_LENS_OUTPUT_FIELDS[prompt_id]:
        errors.append(f"storm lens {prompt_id} output has invalid fields")
        return errors
    if not _is_iso_datetime(payload.get("created_at")):
        errors.append("storm lens artifact created_at must be an ISO datetime")

    if prompt_id == "P1":
        errors.extend(_string_list(output.get("perspectives"), "perspectives"))
        errors.extend(_string_list(output.get("question_ids"), "question_ids", pattern=r"Q\d{3}"))
        errors.extend(_string_list(output.get("source_class_ids"), "source_class_ids"))
        if not isinstance(output.get("notes"), str):
            errors.append("notes must be a string")
    elif prompt_id == "P2":
        errors.extend(_string_list(output.get("finding_ids"), "finding_ids", pattern=r"F\d{3}"))
        errors.extend(_string_list(output.get("conflict_claim_ids"), "conflict_claim_ids", pattern=r"C\d{3}"))
        for field in ("consensus_candidates", "blind_spots", "resolver_questions"):
            errors.extend(_string_list(output.get(field), field))
        actions = output.get("resolution_actions")
        if not isinstance(actions, list):
            errors.append("resolution_actions must be an array")
        else:
            expected_texts = {
                *(str(item) for item in output.get("blind_spots", [])),
                *(str(item) for item in output.get("resolver_questions", [])),
            }
            observed_texts: set[str] = set()
            for index, action in enumerate(actions, start=1):
                fields = {"action_id", "item_kind", "text", "disposition", "uncertainty_id", "reason"}
                if not isinstance(action, dict) or set(action) != fields:
                    errors.append(f"resolution_action {index} has invalid fields")
                    continue
                observed_texts.add(str(action.get("text", "")))
                if action.get("item_kind") not in {"blind_spot", "resolver_question"}:
                    errors.append(f"resolution_action {index} item_kind is invalid")
                if action.get("disposition") not in {"new_retrieval", "uncertainty", "out_of_scope"}:
                    errors.append(f"resolution_action {index} disposition is invalid")
                if action.get("disposition") == "uncertainty":
                    if not re.fullmatch(r"U\d{3}", str(action.get("uncertainty_id", ""))):
                        errors.append(f"resolution_action {index} requires uncertainty_id")
                elif action.get("uncertainty_id") is not None:
                    errors.append(f"resolution_action {index} uncertainty_id must be null")
                if not str(action.get("reason", "")).strip():
                    errors.append(f"resolution_action {index} requires reason")
            if observed_texts != expected_texts:
                errors.append("every blind spot and resolver question requires exactly one resolution action")
    elif prompt_id == "P3":
        errors.extend(_string_list(output.get("section_ids"), "section_ids", pattern=r"SEC\d{2}"))
        errors.extend(_string_list(output.get("claim_ids"), "claim_ids", pattern=r"C\d{3}"))
        errors.extend(_string_list(output.get("finding_ids"), "finding_ids", pattern=r"F\d{3}"))
        errors.extend(_string_list(output.get("contradiction_ids"), "contradiction_ids"))
        errors.extend(_string_list(output.get("uncertainty_ids"), "uncertainty_ids"))
        if not isinstance(output.get("length_budget_note"), str) or not output.get("length_budget_note"):
            errors.append("length_budget_note must be a non-empty string")
    elif prompt_id == "P4":
        if output.get("target_kind") != "draft":
            errors.append("target_kind must be draft")
        if not _is_sha256(output.get("target_sha256")):
            errors.append("target_sha256 must be a SHA-256 value")
        errors.extend(_string_list(output.get("weakest_claim_ids"), "weakest_claim_ids", pattern=r"C\d{3}"))
        for field in ("overstated_paragraphs", "missing_perspectives", "citation_support_issues"):
            errors.extend(_string_list(output.get(field), field))
        repairs = output.get("repair_actions")
        if not isinstance(repairs, list):
            errors.append("repair_actions must be an array")
        else:
            for index, repair in enumerate(repairs, start=1):
                fields = {
                    "action_id", "target_kind", "target_id", "before_sha256",
                    "action", "disposition", "reason",
                }
                if not isinstance(repair, dict) or set(repair) != fields:
                    errors.append(f"repair_action {index} has invalid fields")
                    continue
                if not all(isinstance(repair.get(field), str) and repair.get(field) for field in fields):
                    errors.append(f"repair_action {index} fields must be non-empty strings")
                if repair.get("target_kind") not in {"draft", "paragraph", "claim"}:
                    errors.append(f"repair_action {index} target_kind is invalid")
                if not _is_sha256(repair.get("before_sha256")):
                    errors.append(f"repair_action {index} before_sha256 is invalid")
                if repair.get("disposition") not in {"required", "waived"}:
                    errors.append(f"repair_action {index} disposition must be required or waived")
    return errors


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


def write_generation_text_input(
    layout: RunLayout, generation: int, name: str, value: str
) -> Path:
    path = layout.generation_input(generation, name)
    atomic_write_text(path, value)
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
    source_policy: str | None = "external_allowed",
    retrieval_mode: str | None = "host",
    output_mode: str | None = "full",
    storm_lens_mode: str | None = None,
    research_profile: str = "auto",
    user_goal: str = "Build an evidence-grounded answer",
    audience: str = "General reader",
    geography: str = "global",
    timeframe: str = "current",
    as_of: str | None = None,
    max_age_days: int = 365,
    uncertainty_tolerance: str = "low",
    high_stakes: bool = False,
    briefing_reason: str = "",
    user_material: Sequence[str] = (),
    assumption: Sequence[str] = (),
    profile_selection_mode: str | None = None,
    profile_selection_evidence: str = "",
    profile_selection_evidence_file: Path | None = None,
    profile_prompt_file: Path | None = None,
    assurance_target: str | None = None,
    run_intent: str = "user_delivery",
) -> RunLayout:
    args = argparse.Namespace(
        topic=topic,
        question=question,
        language=language,
        depth_level=depth_level,
        min_units=minimum_units,
        max_units=maximum_units,
        user_goal=user_goal,
        audience=audience,
        geography=geography,
        timeframe=timeframe,
        source_policy=source_policy,
        as_of=as_of,
        max_age_days=max_age_days,
        retrieval_mode=retrieval_mode,
        output_mode=output_mode,
        storm_lens_mode=storm_lens_mode,
        research_profile=research_profile,
        uncertainty_tolerance=uncertainty_tolerance,
        high_stakes=high_stakes,
        briefing_reason=briefing_reason,
        user_material=list(user_material),
        assumption=list(assumption),
        profile_selection_mode=profile_selection_mode,
        profile_selection_evidence=profile_selection_evidence,
        profile_selection_evidence_file=profile_selection_evidence_file,
        profile_prompt_file=profile_prompt_file,
        assurance_target=assurance_target,
        run_intent=run_intent,
    )
    brief = build_brief_v2(args)
    validate_or_raise(validate_brief(brief))
    package_hash = compute_skill_package_hash(ROOT)
    layout = create_run_layout(output)
    prompt_path: Path | None = None
    prompt_source = _profile_prompt_file(args)
    if prompt_source is not None:
        prompt_path = write_generation_text_input(
            layout, 1, "profile-selection-prompt.txt",
            prompt_source.read_text(encoding="utf-8"),
        )
    evidence_path: Path | None = None
    evidence_source = _profile_selection_evidence_file(args)
    if evidence_source is not None:
        evidence_path = write_generation_text_input(
            layout, 1, "profile-selection-evidence.txt",
            evidence_source.read_text(encoding="utf-8"),
        )
    brief_path = write_generation_input(layout, 1, "brief.json", brief)
    refresh_current_brief_view(layout, 1)
    output_paths = [brief_path]
    if prompt_path is not None:
        output_paths.append(prompt_path)
    if evidence_path is not None:
        output_paths.append(evidence_path)
    commit_stage_receipt(
        layout,
        generation=1,
        stage=Stage.INIT,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts={},
        output_paths=output_paths,
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
        source_policy=args.source_policy,
        retrieval_mode=args.retrieval_mode,
        output_mode=args.output_mode,
        storm_lens_mode=args.storm_lens_mode,
        research_profile=args.research_profile,
        user_goal=args.user_goal,
        audience=args.audience,
        geography=args.geography,
        timeframe=args.timeframe,
        as_of=args.as_of,
        max_age_days=args.max_age_days,
        uncertainty_tolerance=args.uncertainty_tolerance,
        high_stakes=args.high_stakes,
        briefing_reason=args.briefing_reason,
        user_material=args.user_material,
        assumption=args.assumption,
        profile_selection_mode=args.profile_selection_mode,
        profile_selection_evidence=args.profile_selection_evidence,
        profile_selection_evidence_file=args.profile_selection_evidence_file,
        profile_prompt_file=args.profile_prompt_file,
        assurance_target=args.assurance_target,
        run_intent=args.run_intent,
    )
    print(f"Initialized {output}")
    return EXIT_OK


def validate_plan_bundle(
    plan: dict[str, object], source_plan: dict[str, object], brief: dict[str, object]
) -> None:
    errors = validate_research_plan(plan, brief, set())
    errors.extend(validate_source_plan(source_plan))
    errors.extend(validate_source_depth_plan(source_plan, brief, plan))
    errors.extend(validate_critique_source_plan(source_plan, brief))
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


def _generation_logical_path(layout: RunLayout, generation: int, logical_path: str) -> Path:
    return package_child(layout.generation_root(generation), logical_path)


def _hash_inputs(layout: RunLayout, generation: int, logical_paths: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for logical_path in logical_paths:
        path = _generation_logical_path(layout, generation, logical_path)
        if not path.is_file() or path.is_symlink():
            raise StagePreconditionError(f"missing storm lens input artifact: {logical_path}")
        result[logical_path] = sha256_file(path)
    return result


def _storm_lens_expected_inputs(
    layout: RunLayout, generation: int, prompt_id: str
) -> dict[str, str]:
    if prompt_id == "P1":
        return _hash_inputs(layout, generation, ["inputs/brief.json"])
    if prompt_id == "P2":
        return _hash_inputs(layout, generation, [
            "artifacts/research/storm-findings-pool.jsonl",
            "artifacts/research/finding-coverage.json",
            "artifacts/research/source-register.jsonl",
            "artifacts/research/retrieval-manifest.jsonl",
        ])
    if prompt_id == "P3":
        return _hash_inputs(layout, generation, [
            "artifacts/research/storm-findings-pool.jsonl",
            _storm_lens_logical_path("P2"),
        ])
    if prompt_id == "P4":
        return _hash_inputs(layout, generation, [
            "artifacts/drafts/report-v1.md",
            "artifacts/research/paragraph-map.jsonl",
        ])
    raise CLIContractError(f"unknown STORM lens prompt: {prompt_id}")


def _validate_p1_against_plan(
    lens: dict[str, Any],
    plan: dict[str, object],
    source_plan: dict[str, object],
) -> list[str]:
    output = lens.get("output") if isinstance(lens.get("output"), dict) else {}
    lens_questions = set(str(item) for item in output.get("question_ids", []))
    plan_questions = {
        str(item.get("question_id"))
        for item in plan.get("questions", [])
        if isinstance(item, dict)
    }
    errors: list[str] = []
    if not plan_questions <= lens_questions:
        errors.append("storm lens P1 must cover every planned research question")
    lens_source_classes = set(str(item) for item in output.get("source_class_ids", []))
    source_classes = {
        str(item.get("class_id"))
        for item in source_plan.get("source_classes", [])
        if isinstance(item, dict)
    }
    if not source_classes <= lens_source_classes:
        errors.append("storm lens P1 must cover every source class")
    return errors


def _validate_p2_against_research_state(
    lens: dict[str, Any],
    findings: list[dict[str, object]],
    contradictions: dict[str, object],
    uncertainties: dict[str, object],
) -> list[str]:
    output = lens.get("output") if isinstance(lens.get("output"), dict) else {}
    finding_ids = {
        str(finding.get("finding_id"))
        for finding in findings
        if isinstance(finding, dict)
    }
    conflict_claim_ids = set(str(item) for item in output.get("conflict_claim_ids", []))
    errors = [
        f"storm lens P2 references unknown finding {finding_id}"
        for finding_id in output.get("finding_ids", [])
        if str(finding_id) not in finding_ids
    ]
    for conflict in contradictions.get("conflicts", []):
        if isinstance(conflict, dict):
            claim_id = str(conflict.get("claim_id", ""))
            if claim_id and claim_id not in conflict_claim_ids:
                errors.append(f"contradiction {claim_id} is not represented in storm lens P2")
    uncertainty_ids = {
        str(item.get("uncertainty_id"))
        for item in uncertainties.get("uncertainties", [])
        if isinstance(item, dict)
    }
    for action in output.get("resolution_actions", []):
        if not isinstance(action, dict):
            continue
        if action.get("disposition") == "new_retrieval":
            errors.append(
                f"P2 action {action.get('action_id')} requires new retrieval; amend the run before P3/evidence"
            )
        if action.get("disposition") == "uncertainty" and str(action.get("uncertainty_id")) not in uncertainty_ids:
            errors.append(f"P2 action {action.get('action_id')} references unknown uncertainty")
    return errors


def _validate_p3_against_evidence_inputs(
    lens: dict[str, Any],
    outline: dict[str, object],
    claims: list[dict[str, object]],
    findings: list[dict[str, object]],
) -> list[str]:
    output = lens.get("output") if isinstance(lens.get("output"), dict) else {}
    lens_sections = set(str(item) for item in output.get("section_ids", []))
    outline_sections = {
        str(section.get("section_id"))
        for section in outline.get("sections", [])
        if isinstance(section, dict)
    }
    errors: list[str] = []
    if not outline_sections <= lens_sections:
        errors.append("storm lens P3 must cover every outline section")
    lens_claims = set(str(item) for item in output.get("claim_ids", []))
    material_claims = {
        str(claim.get("claim_id"))
        for claim in claims
        if isinstance(claim, dict) and claim.get("material")
    }
    if not material_claims <= lens_claims:
        errors.append("storm lens P3 must cover every material Claim")
    finding_ids = {
        str(finding.get("finding_id"))
        for finding in findings
        if isinstance(finding, dict)
    }
    for finding_id in output.get("finding_ids", []):
        if str(finding_id) not in finding_ids:
            errors.append(f"storm lens P3 references unknown finding {finding_id}")
    return errors


def _validate_p4_against_draft(
    lens: dict[str, Any],
    draft_path: Path,
) -> list[str]:
    output = lens.get("output") if isinstance(lens.get("output"), dict) else {}
    if output.get("target_sha256") != sha256_file(draft_path):
        return ["storm lens P4 target_sha256 must match draft report-v1.md"]
    return []


def _load_valid_lens_artifact(
    path: Path,
    *,
    prompt_id: str,
    expected_inputs: dict[str, str],
) -> dict[str, Any]:
    payload = load_json(path)
    errors = validate_storm_lens_artifact(
        payload, prompt_id=prompt_id, expected_inputs=expected_inputs
    )
    if errors:
        raise CLIContractError("; ".join(dict.fromkeys(errors)))
    return payload


def _optional_lens_inputs(
    layout: RunLayout,
    generation: int,
    prompt_id: str,
    expected_inputs: dict[str, str],
    *,
    required: bool,
) -> tuple[dict[str, Any] | None, dict[str, str]]:
    path = _storm_lens_artifact_path(layout, generation, prompt_id)
    if not path.is_file() or path.is_symlink():
        if required:
            raise StagePreconditionError(
                f"strict STORM lens mode requires {_storm_lens_logical_path(prompt_id)}"
            )
        return None, {}
    payload = _load_valid_lens_artifact(
        path, prompt_id=prompt_id, expected_inputs=expected_inputs
    )
    return payload, {_storm_lens_logical_path(prompt_id): sha256_file(path)}


def _write_storm_lens_artifact(
    layout: RunLayout, generation: int, prompt_id: str, payload: dict[str, Any]
) -> Path:
    path = _storm_lens_artifact_path(layout, generation, prompt_id)
    atomic_write_json(path, payload)
    atomic_write_json(package_child(layout.root, f"current/research/{path.name}"), payload)
    return path


def _command_lens(args: argparse.Namespace, prompt_id: str) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    if prompt_id == "P1":
        verify_stage_precondition(layout, generation, Stage.PLAN, package_hash)
        if layout.receipt(generation, Stage.PLAN).exists():
            raise StagePreconditionError("cannot register P1 after plan receipt exists")
    elif prompt_id in {"P2", "P3"}:
        verify_stage_precondition(layout, generation, Stage.EVIDENCE, package_hash)
        if layout.receipt(generation, Stage.EVIDENCE).exists():
            raise StagePreconditionError(f"cannot register {prompt_id} after evidence receipt exists")
    else:
        verify_stage_precondition(layout, generation, Stage.REVIEW, package_hash)
        if layout.receipt(generation, Stage.REVIEW).exists():
            raise StagePreconditionError("cannot register P4 after review receipt exists")
    expected_inputs = _storm_lens_expected_inputs(layout, generation, prompt_id)
    payload = _load_valid_lens_artifact(
        args.input_json, prompt_id=prompt_id, expected_inputs=expected_inputs
    )
    if prompt_id == "P3":
        p2 = load_json(_storm_lens_artifact_path(layout, generation, "P2"))
        pending = [
            str(item.get("action_id")) for item in p2.get("output", {}).get("resolution_actions", [])
            if isinstance(item, dict) and item.get("disposition") == "new_retrieval"
        ]
        if pending:
            raise StagePreconditionError(
                "P2 requires a new retrieval generation before P3: " + ", ".join(pending)
            )
    payload["created_at"] = _utc_now()
    if prompt_id == "P4":
        draft_path = layout.artifact(generation, "drafts/report-v1.md")
        errors = _validate_p4_against_draft(payload, draft_path)
        if errors:
            raise CLIContractError("; ".join(errors))
    path = _write_storm_lens_artifact(layout, generation, prompt_id, payload)
    print(f"Registered STORM lens {prompt_id} artifact: {path}")
    return EXIT_OK


def command_lens_perspectives(args: argparse.Namespace) -> int:
    return _command_lens(args, "P1")


def command_lens_conflicts(args: argparse.Namespace) -> int:
    return _command_lens(args, "P2")


def command_lens_outline(args: argparse.Namespace) -> int:
    return _command_lens(args, "P3")


def command_lens_review(args: argparse.Namespace) -> int:
    return _command_lens(args, "P4")


def _is_full_external_dossier(brief: dict[str, object]) -> bool:
    return (
        brief.get("depth_level") == "full_dossier"
        and brief.get("source_policy") != "closed_corpus"
        and brief.get("retrieval_mode") != "closed_corpus"
    )


def _is_maximal_full_dossier(brief: dict[str, object]) -> bool:
    return brief.get("research_profile") == "maximal_full_dossier"


def _run_intent(brief: dict[str, object]) -> str:
    return str(brief.get("run_intent") or "user_delivery")


def _is_diagnostic_rehearsal(brief: dict[str, object]) -> bool:
    return _run_intent(brief) == "diagnostic_rehearsal"


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


def _source_plan_surface_buckets(source_plan: dict[str, object]) -> set[str]:
    buckets: set[str] = set()
    for question in source_plan.get("questions", []):
        if not isinstance(question, dict):
            continue
        requirements = question.get("search_requirements")
        if isinstance(requirements, dict):
            for surface in requirements.get("required_surfaces", []):
                bucket = _surface_bucket(surface)
                if bucket:
                    buckets.add(bucket)
        for field in ("question", "evidence_need"):
            bucket = _surface_bucket(question.get(field))
            if bucket:
                buckets.add(bucket)
    for source_class in source_plan.get("source_classes", []):
        if isinstance(source_class, dict):
            bucket = _surface_bucket(_source_class_text(source_class))
            if bucket:
                buckets.add(bucket)
    return buckets


def _audit_surface_buckets(audit: list[dict[str, object]]) -> set[str]:
    buckets: set[str] = set()
    for record in audit:
        if record.get("record_kind") != "search_run":
            continue
        for field in ("surface_class", "surface", "pass_kind"):
            bucket = _surface_bucket(record.get(field))
            if bucket:
                buckets.add(bucket)
    return buckets


def _source_class_text(source_class: dict[str, object]) -> str:
    parts: list[str] = []
    for key in ("class_id", "name"):
        parts.append(str(source_class.get(key, "")))
    for key in ("can_prove", "cannot_prove"):
        value = source_class.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return " ".join(parts).casefold()


def _source_question_text(question: dict[str, object]) -> str:
    parts: list[str] = []
    for key in ("query_id", "question", "evidence_need"):
        parts.append(str(question.get(key, "")))
    value = question.get("required_source_classes")
    if isinstance(value, list):
        parts.extend(str(item) for item in value)
    return " ".join(parts).casefold()


def _is_user_material_source_class(source_class: dict[str, object]) -> bool:
    text = _source_class_text(source_class)
    return any(marker in text for marker in USER_MATERIAL_SOURCE_CLASS_MARKERS)


def validate_critique_source_plan(
    source_plan: dict[str, object],
    brief: dict[str, object],
) -> list[str]:
    if brief.get("research_profile") != "critique_deepresearch":
        return []
    questions = [
        item for item in source_plan.get("questions", [])
        if isinstance(item, dict)
    ]
    source_classes = [
        item for item in source_plan.get("source_classes", [])
        if isinstance(item, dict)
    ]
    combined = [
        *(_source_question_text(item) for item in questions),
        *(_source_class_text(item) for item in source_classes),
    ]
    errors: list[str] = []
    for dimension, markers in CRITIQUE_SEARCH_DIMENSIONS.items():
        if not any(marker.casefold() in text for text in combined for marker in markers):
            errors.append(f"critique_deepresearch source plan missing search dimension: {dimension}")
    if len(questions) < len(CRITIQUE_SEARCH_DIMENSIONS):
        errors.append(
            "critique_deepresearch source plan requires at least one planned question per required search dimension"
        )
    return errors


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
    academic_class_ids = {
        str(item.get("class_id"))
        for item in source_classes
        if "academic" in _source_class_text(item) or "scholar" in _source_class_text(item)
    }
    if not academic_class_ids:
        errors.append("full_dossier requires an academic source class")
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
    if _is_maximal_full_dossier(brief):
        applicability = source_plan.get("surface_applicability")
        if not isinstance(applicability, list) or not applicability:
            errors.append("maximal_full_dossier requires a surface applicability matrix")
            applicability = []
        required_matrix = {
            str(item.get("surface"))
            for item in applicability
            if isinstance(item, dict) and item.get("applicability") == "required"
        }
        planned_surfaces = {
            str(surface)
            for question in source_questions
            if isinstance(question.get("search_requirements"), dict)
            for surface in question["search_requirements"].get("required_surfaces", [])
        }
        missing_matrix = sorted(planned_surfaces - required_matrix)
        if missing_matrix:
            errors.append(
                "maximal source-plan surfaces are absent from applicability matrix: "
                + ", ".join(missing_matrix)
            )
        if not any(_surface_bucket(item) == "counterevidence" for item in required_matrix):
            errors.append("maximal_full_dossier requires counterevidence in the surface applicability matrix")
        if brief.get("high_stakes"):
            high_stakes_questions = [
                item for item in source_questions
                if isinstance(item.get("search_requirements"), dict)
                and len(item["search_requirements"].get("aliases", [])) >= 3
            ]
            if not high_stakes_questions:
                errors.append("maximal_full_dossier high-stakes source plan requires at least three aliases")
            if not any("trial" in item.casefold() or "registry" in item.casefold() for item in required_matrix):
                errors.append("maximal_full_dossier high-stakes applicability matrix requires a trial registry")
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
    p1_expected_inputs = _storm_lens_expected_inputs(layout, generation, "P1")
    p1, p1_receipt_inputs = _optional_lens_inputs(
        layout, generation, "P1", p1_expected_inputs,
        required=_storm_lens_mode(brief) == "strict",
    )
    if p1:
        p1_errors = _validate_p1_against_plan(p1, plan, source_plan)
        if p1_errors:
            raise CLIContractError("; ".join(dict.fromkeys(p1_errors)))
    plan_path, source_plan_path, tasklet_path = _promote_plan_artifacts(
        layout, generation, plan, source_plan, tasklets
    )
    brief_path = layout.generation_input(generation, "brief.json")
    plan_inputs = {"inputs/brief.json": sha256_file(brief_path)}
    plan_inputs.update(p1_receipt_inputs)
    commit_stage_receipt(
        layout,
        generation=generation,
        stage=Stage.PLAN,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts=plan_inputs,
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
    audit: list[dict[str, object]],
) -> tuple[Path, Path, Path]:
    staging = package_child(
        layout.root, f"work/.staging/g{generation:04d}/retrieval-{uuid.uuid4().hex}"
    )
    staging.mkdir(parents=True, exist_ok=False)
    staged_sources = staging / "source-register.jsonl"
    staged_manifest = staging / "retrieval-manifest.jsonl"
    staged_audit = staging / "retrieval-audit.jsonl"
    atomic_write_text(staged_sources, _jsonl_text(sources))
    atomic_write_text(staged_manifest, _jsonl_text(manifests))
    atomic_write_text(staged_audit, _jsonl_text(audit))
    source_path = layout.artifact(generation, "research/source-register.jsonl")
    manifest_path = layout.artifact(generation, "research/retrieval-manifest.jsonl")
    audit_path = layout.artifact(generation, "research/retrieval-audit.jsonl")
    atomic_promote(staged_sources, source_path)
    atomic_promote(staged_manifest, manifest_path)
    atomic_promote(staged_audit, audit_path)
    staging.rmdir()
    return source_path, manifest_path, audit_path


def _refresh_current_retrieval_view(
    layout: RunLayout,
    sources: list[dict[str, object]],
    manifests: list[dict[str, object]],
    audit: list[dict[str, object]],
) -> None:
    root = package_child(layout.root, "current/research")
    atomic_write_text(root / "source-register.jsonl", _jsonl_text(sources))
    atomic_write_text(root / "retrieval-manifest.jsonl", _jsonl_text(manifests))
    atomic_write_text(root / "retrieval-audit.jsonl", _jsonl_text(audit))


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
    sources: list[dict[str, object]], brief: dict[str, object],
    audit: list[dict[str, object]] | None = None,
) -> list[str]:
    if not _is_full_external_dossier(brief):
        return []
    deep_external = [source for source in sources if _is_deep_external_source(source)]
    independent = {independent_source_identity(source) for source in deep_external}
    if _is_maximal_full_dossier(brief):
        errors: list[str] = []
        if audit is not None:
            if brief.get("high_stakes"):
                surfaces = [
                    str(record.get("surface", "")).casefold()
                    for record in audit
                    if record.get("record_kind") == "search_run"
                ]
                surface_classes = [
                    str(record.get("surface_class", "")).casefold()
                    for record in audit
                    if record.get("record_kind") == "search_run"
                ]
                buckets = _audit_surface_buckets(audit)
                has_literature = (
                    any("pubmed" in item for item in surfaces)
                    or "literature_database" in surface_classes
                )
                has_registry = "official_or_registry" in buckets
                if not has_literature or not has_registry:
                    errors.append("maximal_full_dossier high-stakes retrieval requires literature database and trial registry surfaces")
        return errors
    if len(independent) < MIN_FULL_DOSSIER_DEEP_EXTERNAL_SOURCES:
        return [
            "full_dossier independent source depth requires at least "
            f"{MIN_FULL_DOSSIER_DEEP_EXTERNAL_SOURCES} non-user, non-encyclopedia external sources"
        ]
    return []


def validate_maximal_report_source_coverage(
    report: str,
    sources: list[dict[str, object]],
    brief: dict[str, object],
) -> list[str]:
    if not _is_maximal_full_dossier(brief):
        return []
    return []


def audit_boilerplate_errors(text: str, label: str) -> list[str]:
    matches = sum(len(pattern.findall(text)) for pattern in AUDIT_BOILERPLATE_PATTERNS)
    if matches < 2:
        return []
    return [
        f"{label} uses source-register audit boilerplate as prose; synthesize findings instead"
    ]


def validate_material_claim_prose(
    claims: list[dict[str, object]], brief: dict[str, object]
) -> list[str]:
    if not _is_maximal_full_dossier(brief):
        return []
    claim_ids = [
        str(claim.get("claim_id"))
        for claim in claims
        if claim.get("material") and any(
            pattern.search(str(claim.get("claim_text", "")))
            for pattern in AUDIT_BOILERPLATE_PATTERNS
        )
    ]
    if not claim_ids:
        return []
    return [
        "maximal_full_dossier material claims cannot be source-register boilerplate: "
        + ", ".join(claim_ids[:10])
    ]


def _infer_content_type(path: Path, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    guessed, _encoding = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    if path.suffix.casefold() in {".md", ".markdown", ".txt"}:
        return "text/plain"
    return "application/octet-stream"


def _capture_warnings(normalized_text: str) -> list[str]:
    lowered = normalized_text.casefold()
    warnings = [
        f"captured content contains bad-capture marker: {marker}"
        for marker in sorted(BAD_CAPTURE_MARKERS)
        if marker in lowered
    ]
    if len(normalized_text) < CAPTURE_MIN_NORMALIZED_CHARS:
        warnings.append(
            f"captured content is short after normalization: {len(normalized_text)} characters"
        )
    return warnings


def _default_excerpt(normalized_text: str) -> str:
    return normalized_text[:280].strip()


def _planned_query_ids(layout: RunLayout, generation: int) -> set[str]:
    source_plan = load_json(layout.artifact(generation, "research/source-plan.json"))
    return {
        str(item.get("query_id"))
        for item in source_plan.get("questions", [])
        if isinstance(item, dict)
    }


def _copy_capture_snapshot(
    layout: RunLayout, generation: int, source_path: Path
) -> tuple[str, Path]:
    source = source_path.expanduser().resolve()
    if source.is_symlink() or not source.is_file():
        raise CLIContractError(f"snapshot is missing or unsafe: {source_path}")
    suffix = source.suffix if source.suffix else ".txt"
    relative = f"captured/{uuid.uuid4().hex}-{source.name}"
    destination = layout.evidence_cache(generation, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise CLIContractError(f"capture destination already exists: {relative}")
    shutil.copy2(source, destination)
    return relative, destination


def _capture_record_payload(
    layout: RunLayout,
    generation: int,
    raw: dict[str, object],
    *,
    snapshot_base: Path | None,
    allow_warning: bool,
) -> tuple[dict[str, object], list[str]]:
    snapshot_value = raw.get("snapshot") or raw.get("snapshot_path") or raw.get("raw_artifact")
    if not isinstance(snapshot_value, str) or not snapshot_value.strip():
        raise CLIContractError("capture source requires snapshot or snapshot_path")
    snapshot_path = Path(snapshot_value)
    if not snapshot_path.is_absolute() and snapshot_base is not None:
        snapshot_path = snapshot_base / snapshot_path
    snapshot_ref, copied_snapshot = _copy_capture_snapshot(layout, generation, snapshot_path)
    content_type = _infer_content_type(copied_snapshot, str(raw.get("content_type") or "") or None)
    normalized_text = normalized_snapshot_text(copied_snapshot, content_type)
    warnings = _capture_warnings(normalized_text)
    if warnings and not allow_warning:
        raise RetrievalGateError("; ".join(warnings))
    retrieved_at = str(raw.get("retrieved_at") or _utc_now())
    url = str(raw.get("url") or "").strip()
    file_ref_value = raw.get("file_ref")
    file_ref = str(file_ref_value).strip() if file_ref_value is not None else ""
    adapter = str(raw.get("adapter") or load_json(layout.generation_input(generation, "brief.json")).get("retrieval_mode"))
    publication_date_status = str(
        raw.get("publication_date_status")
        or ("known" if raw.get("published_at") else "unknown")
    )
    query_id = str(raw.get("query_id", ""))
    suffix = query_id[1:] if re.fullmatch(r"Q\d{3}", query_id) else "001"
    candidate_id = str(raw.get("candidate_id") or f"K{suffix}")
    search_run_ids = raw.get("search_run_ids")
    if not isinstance(search_run_ids, list) or not search_run_ids:
        search_run_ids = [f"SR{suffix}"]
    record: dict[str, object] = {
        "record_kind": "capture",
        "candidate_id": candidate_id,
        "search_run_ids": list(search_run_ids),
        "query_id": query_id,
        "final_url": str(raw.get("final_url") or url) if url else None,
        "file_ref": None if url else file_ref,
        "title": str(raw.get("title", "")).strip(),
        "publisher": str(raw.get("publisher") or raw.get("author_or_org") or "").strip(),
        "published_at": raw.get("published_at") if publication_date_status == "known" else None,
        "publication_date_status": publication_date_status,
        "retrieved_at": retrieved_at,
        "content_excerpt": str(raw.get("content_excerpt") or _default_excerpt(normalized_text)).strip(),
        "content_locator": str(raw.get("content_locator") or raw.get("locator") or "text:1").strip(),
        "locator_type": str(raw.get("locator_type") or "text").strip(),
        "adapter": adapter,
        "adapter_run_id": str(raw.get("adapter_run_id") or "manual-capture").strip(),
        "capture_level": str(raw.get("capture_level") or ("full_text" if url else "user_file")).strip(),
        "evidence_strength_ceiling": str(raw.get("evidence_strength_ceiling") or "medium").strip(),
        "raw_artifact": snapshot_ref,
        "observed_status": int(raw.get("observed_status") or 200) if url else None,
        "content_type": content_type,
        "source_type": str(raw.get("source_type") or "secondary_synthesis").strip(),
        "primary_class": str(raw.get("primary_class") or "secondary").strip(),
        "reliability_tier": str(raw.get("reliability_tier") or "B").strip(),
        "freshness_status": str(raw.get("freshness_status") or "unknown").strip(),
        "reliability_notes": str(raw.get("reliability_notes") or "Captured source; reliability not independently upgraded.").strip(),
    }
    if url:
        record["url"] = url
    try:
        capture_retrieval_evidence(record, layout.evidence_cache(generation, "."))
    except SourceEvidenceError as exc:
        raise RetrievalGateError(str(exc)) from exc
    return record, warnings


def _manual_audit_records(
    capture: dict[str, object], cache_root: Path
) -> list[dict[str, object]]:
    search_run_id = str(capture["search_run_ids"][0])
    snapshot_ref = str(capture["raw_artifact"])
    snapshot = resolve_snapshot(cache_root, snapshot_ref)
    adapter = str(capture["adapter"])
    closed = adapter == "closed_corpus"
    request_payload = {
        "query_id": str(capture["query_id"]),
        "surface": "supplied-corpus" if closed else "manual-capture",
        "query": str(capture.get("title", "manual capture")),
        "aliases": [str(capture.get("title", "manual capture"))],
    }
    request_ref = f"manual-request-{search_run_id}.json"
    request_path = cache_root / request_ref
    atomic_write_text(
        request_path,
        json.dumps(request_payload, ensure_ascii=False, sort_keys=True) + "\n",
    )
    search = {
        "record_kind": "search_run",
        "search_run_id": search_run_id,
        "query_id": str(capture["query_id"]),
        "adapter": adapter,
        "pass_kind": "corpus" if closed else "baseline",
        "surface": request_payload["surface"],
        "surface_class": "local_corpus" if closed else "web",
        "query": request_payload["query"],
        "aliases": request_payload["aliases"],
        "searched_at": str(capture["retrieved_at"]),
        "result_count": 1,
        "execution_status": "completed",
        "request_artifact": request_ref,
        "request_sha256": sha256_file(request_path),
        "raw_artifact": snapshot_ref,
        "snapshot_sha256": sha256_file(snapshot),
        "limitations": ["Manual capture does not establish exhaustive search coverage."],
    }
    candidate = {
        "record_kind": "candidate",
        "candidate_id": str(capture["candidate_id"]),
        "adapter": adapter,
        "search_run_ids": list(capture["search_run_ids"]),
        "title": str(capture["title"]),
        "authors": [str(capture["publisher"])],
        "year": int(str(capture["published_at"])[:4]) if capture.get("published_at") else None,
        "venue": str(capture["publisher"]),
        "url": capture.get("url") or capture.get("final_url"),
        "identifiers": {
            "doi": None,
            "pmid": None,
            "arxiv_id": None,
            "semantic_scholar_id": None,
            "openalex_id": None,
        },
        "resolver_outcomes": [{
            "resolver": "manual-capture",
            "status": "skipped",
            "query_basis": "metadata",
            "matched_identifier": None,
            "returned_title": None,
            "returned_authors": [],
            "returned_year": None,
            "metadata_match": False,
            "checked_at": str(capture["retrieved_at"]),
            "raw_artifact": None,
            "snapshot_sha256": None,
            "reason": "No external bibliographic resolver was supplied.",
        }],
        "disposition": "include",
        "screening_reason": "Manually captured against the planned research question.",
        "version_family_id": None,
        "version_role": None,
        "relationship_basis": None,
        "canonical_version": True,
    }
    return [search, candidate, capture]


def _write_capture_records(path: Path, records: list[dict[str, object]], *, append: bool) -> None:
    if path.exists() and not append:
        raise CLIContractError(f"capture output already exists: {path}")
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, existing + _jsonl_text(records))


def _retrieval_helper_warning(layout: RunLayout, generation: int) -> tuple[str, list[str]]:
    brief = verify_current_brief_view(layout, generation)
    if (
        brief.get("research_profile") == "maximal_full_dossier"
        and brief.get("assurance_target") == "captured_host_execution"
    ):
        return (
            "insufficient_for_max_captured",
            [
                "capture-source/ingest-dir only create low-fidelity manual capture records.",
                "Max captured retrieval still needs typed search_run, candidate screening, resolver outcomes, publisher/full-text capture, search_wave/gap_assessment, retrieval-preflight, and retrieval-prepare.",
            ],
        )
    return "not_checked", []


def command_capture_source(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.RETRIEVAL, package_hash)
    if layout.receipt(generation, Stage.RETRIEVAL).exists():
        raise StagePreconditionError("cannot capture retrieval inputs after retrieval receipt exists")
    if args.query_id not in _planned_query_ids(layout, generation):
        raise CLIContractError(f"query_id is not in source plan: {args.query_id}")
    raw = {
        "query_id": args.query_id,
        "url": args.url,
        "file_ref": args.file_ref,
        "snapshot": str(args.snapshot),
        "title": args.title,
        "publisher": args.publisher,
        "published_at": args.published_at,
        "publication_date_status": args.publication_date_status,
        "retrieved_at": args.retrieved_at,
        "content_excerpt": args.content_excerpt,
        "content_locator": args.content_locator,
        "locator_type": args.locator_type,
        "adapter": args.adapter,
        "adapter_run_id": args.adapter_run_id,
        "capture_level": args.capture_level,
        "evidence_strength_ceiling": args.evidence_strength_ceiling,
        "observed_status": args.observed_status,
        "content_type": args.content_type,
        "source_type": args.source_type,
        "primary_class": args.primary_class,
        "reliability_tier": args.reliability_tier,
        "freshness_status": args.freshness_status,
        "reliability_notes": args.reliability_notes,
    }
    if bool(args.url) == bool(args.file_ref):
        raise CLIContractError("capture-source requires exactly one of --url or --file-ref")
    record, warnings = _capture_record_payload(
        layout, generation, raw, snapshot_base=None, allow_warning=args.allow_warning
    )
    target = args.to or package_child(layout.root, "current/research/retrieval-inputs.jsonl")
    records = _manual_audit_records(record, layout.evidence_cache(generation, "."))
    _write_capture_records(target, records, append=args.append or target.exists())
    max_compatibility, helper_warnings = _retrieval_helper_warning(layout, generation)
    _print_json({
        "schema_version": "2.0",
        "mode": "capture-source",
        "record_count": len(records),
        "output_jsonl": str(target),
        "max_compatibility": max_compatibility,
        "warnings": [*warnings, *helper_warnings],
    })
    return EXIT_OK


def command_ingest_dir(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.RETRIEVAL, package_hash)
    if layout.receipt(generation, Stage.RETRIEVAL).exists():
        raise StagePreconditionError("cannot build retrieval inputs after retrieval receipt exists")
    input_dir = args.input_dir.expanduser().resolve()
    if input_dir.is_symlink() or not input_dir.is_dir():
        raise CLIContractError(f"input directory is missing or unsafe: {args.input_dir}")
    manifest = args.manifest_jsonl or input_dir / "sources.jsonl"
    records = load_jsonl(manifest)
    planned_ids = _planned_query_ids(layout, generation)
    captured: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    for index, raw in enumerate(records, start=1):
        query_id = str(raw.get("query_id", ""))
        if query_id not in planned_ids:
            raise CLIContractError(f"source manifest row {index} query_id is not in source plan: {query_id}")
        record, row_warnings = _capture_record_payload(
            layout, generation, raw, snapshot_base=input_dir, allow_warning=args.allow_warning
        )
        captured.extend(_manual_audit_records(record, layout.evidence_cache(generation, ".")))
        if row_warnings:
            warnings.append({"row": index, "query_id": query_id, "warnings": row_warnings})
    target = args.to or package_child(layout.root, "current/research/retrieval-inputs.jsonl")
    _write_capture_records(target, captured, append=args.append or target.exists())
    max_compatibility, helper_warnings = _retrieval_helper_warning(layout, generation)
    _print_json({
        "schema_version": "2.0",
        "mode": "ingest-dir",
        "record_count": len(captured),
        "output_jsonl": str(target),
        "max_compatibility": max_compatibility,
        "warnings": [*warnings, *helper_warnings],
    })
    return EXIT_OK


def _retrieval_record_id(record: dict[str, object]) -> str:
    if record.get("record_kind") == "gap_assessment":
        return str(record.get("assessment_id"))
    return str(record.get("search_run_id") or record.get("candidate_id") or record.get("wave_id"))


def _retrieval_expected_record_ids(audit: list[dict[str, object]]) -> list[str]:
    return sorted(
        _retrieval_record_id(record)
        for record in audit
        if record.get("record_kind") in {"search_run", "candidate", "search_wave", "gap_assessment"}
    )


def _retrieval_record_counts(audit: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in audit:
        kind = str(record.get("record_kind"))
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _blocking_debt_path(layout: RunLayout, generation: int) -> Path:
    return layout.artifact(generation, "research/blocking-debt-ledger.json")


def _write_blocking_debt_ledger(
    layout: RunLayout,
    generation: int,
    *,
    stage: str,
    errors: list[str],
    input_artifacts: dict[str, str],
    measurements: dict[str, object],
) -> Path:
    unique_errors = list(dict.fromkeys(str(item) for item in errors if str(item).strip()))
    payload = {
        "schema_version": "2.0",
        "run_intent": "diagnostic_rehearsal",
        "status": "completed_with_blockers",
        "not_valid_for": [
            "user_delivery",
            "real_host_execution_claim",
            "public_release",
            "validated_captured_host_execution",
        ],
        "debts": [{
            "debt_id": "BD001",
            "stage": stage,
            "severity": "blocking",
            "errors": unique_errors,
            "input_artifacts": input_artifacts,
            "measurements": measurements,
            "disposition": "diagnostic_rehearsal_only",
            "release_blocking": True,
            "validation_blocking": True,
            "created_at": _utc_now(),
        }],
    }
    path = _blocking_debt_path(layout, generation)
    atomic_write_json(path, payload)
    atomic_write_json(package_child(layout.root, "current/research/blocking-debt-ledger.json"), payload)
    append_journal_event(layout, {
        "event": "diagnostic_debt_recorded",
        "generation": generation,
        "stage": stage,
        "debt_count": len(payload["debts"]),
        "error_count": len(unique_errors),
        "recorded_at": payload["debts"][0]["created_at"],
    })
    return path


def _retrieval_preflight_payload(
    layout: RunLayout, generation: int, input_jsonl: Path
) -> dict[str, object]:
    brief = verify_current_brief_view(layout, generation)
    errors: list[str] = []
    sources: list[dict[str, object]] = []
    manifests: list[dict[str, object]] = []
    audit: list[dict[str, object]] = []
    try:
        records = load_jsonl(input_jsonl)
        sources, manifests, audit = normalize_retrieval_records(
            records,
            mode=str(brief["retrieval_mode"]),
            cache_root=layout.evidence_cache(generation, "."),
        )
    except (ContractError, SourceEvidenceError, ValueError) as exc:
        errors.append(str(exc))
    if not errors:
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
            errors.append("retrieval evidence does not cover planned questions: " + ", ".join(missing))
        errors.extend(validate_retrieval_audit_contract(audit, manifests, sources, source_plan, brief))
        if (
            brief.get("research_profile") == "maximal_full_dossier"
            and brief.get("assurance_target") == "captured_host_execution"
        ):
            errors.extend(validate_captured_retrieval_artifacts(
                audit, layout.evidence_cache(generation, ".")
            ))
        errors.extend(validate_retrieval_depth(sources, brief, audit))
    return {
        "schema_version": "2.0",
        "stage": "retrieval",
        "ok": not errors,
        "errors": list(dict.fromkeys(errors)),
        "expected_record_ids": _retrieval_expected_record_ids(audit),
        "record_counts": _retrieval_record_counts(audit),
        "assurance_target": brief.get("assurance_target"),
        "research_profile": brief.get("research_profile"),
        "receipt_written": False,
    }


def command_retrieval_preflight(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.RETRIEVAL, package_hash)
    _print_json(_retrieval_preflight_payload(layout, generation, args.input_jsonl))
    return EXIT_OK


def command_retrieval_prepare(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.RETRIEVAL, package_hash)
    brief = verify_current_brief_view(layout, generation)
    if brief.get("assurance_target") != "captured_host_execution":
        raise CLIContractError("retrieval-prepare is only valid for captured_host_execution")
    preflight = _retrieval_preflight_payload(layout, generation, args.input_jsonl)
    if not preflight["ok"]:
        raise RetrievalGateError("retrieval-preflight failed: " + "; ".join(preflight["errors"]))
    transcript = args.transcript.read_text(encoding="utf-8")
    transcript_errors = _execution_transcript_errors(transcript, label="retrieval")
    if transcript_errors:
        raise CLIContractError("; ".join(transcript_errors))
    payload = {
        "schema_version": "2.0",
        "provenance_id": "EPROV-" + uuid.uuid4().hex[:12],
        "stage": "retrieval",
        "execution_kind": "host_execution",
        "context_id": args.context_id,
        "provider": args.provider,
        "model": args.model,
        "runner": args.runner,
        "execution_id": args.execution_id,
        "started_at": args.started_at,
        "completed_at": args.completed_at,
        "transcript_sha256": sha256_file(args.transcript),
        "input_artifacts": {
            "artifacts/research/execution/retrieval-input.jsonl": sha256_file(args.input_jsonl)
        },
        "record_ids": preflight["expected_record_ids"],
        "provider_signed": False,
    }
    atomic_write_json(args.to, payload)
    _print_json({
        "schema_version": "2.0",
        "ok": True,
        "provenance": str(args.to),
        "record_count": len(payload["record_ids"]),
        "record_ids": payload["record_ids"],
    })
    return EXIT_OK


def command_ingest(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.RETRIEVAL, package_hash)
    brief = verify_current_brief_view(layout, generation)
    diagnostic_allowed = bool(getattr(args, "allow_diagnostic_debt", False)) and _is_diagnostic_rehearsal(brief)
    try:
        records = load_jsonl(args.input_jsonl)
        sources, manifests, audit = normalize_retrieval_records(
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
    errors: list[str] = []
    if missing:
        errors.append(
            "retrieval evidence does not cover planned questions: " + ", ".join(missing)
        )
    audit_errors = validate_retrieval_audit_contract(
        audit, manifests, sources, source_plan, brief
    )
    errors.extend(audit_errors)
    if (
        brief.get("research_profile") == "maximal_full_dossier"
        and brief.get("assurance_target") == "captured_host_execution"
    ):
        execution_artifact_errors = validate_captured_retrieval_artifacts(
            audit, layout.evidence_cache(generation, ".")
        )
        errors.extend(execution_artifact_errors)
    plan_receipt = load_json(layout.receipt(generation, Stage.PLAN))
    plan_completed = _parse_datetime(plan_receipt.get("completed_at"))
    now = datetime.now(timezone.utc)
    skew = timedelta(minutes=5)
    timestamp_errors = []
    for manifest in manifests:
        retrieved = _parse_datetime(manifest.get("retrieved_at"))
        if not retrieved or not plan_completed or retrieved < plan_completed - skew or retrieved > now + skew:
            timestamp_errors.append(
                f"retrieval {manifest.get('query_id')} timestamp is outside the plan-ingest window"
            )
    for record in audit:
        timestamp_field = {
            "search_run": "searched_at",
            "search_wave": "created_at",
            "gap_assessment": "created_at",
        }.get(str(record.get("record_kind")))
        if timestamp_field:
            observed = _parse_datetime(record.get(timestamp_field))
            if not observed or not plan_completed or observed < plan_completed - skew or observed > now + skew:
                timestamp_errors.append(
                    f"retrieval audit record {record.get('search_run_id') or record.get('wave_id')} timestamp is outside the plan-ingest window"
                )
        if record.get("record_kind") == "candidate":
            for outcome in record.get("resolver_outcomes", []):
                if not isinstance(outcome, dict) or outcome.get("status") == "skipped":
                    continue
                observed = _parse_datetime(outcome.get("checked_at"))
                if not observed or not plan_completed or observed < plan_completed - skew or observed > now + skew:
                    timestamp_errors.append(
                        f"candidate {record.get('candidate_id')} resolver timestamp is outside the plan-ingest window"
                    )
    if timestamp_errors:
        errors.extend(timestamp_errors)
    depth_errors = validate_retrieval_depth(sources, brief, audit)
    errors.extend(depth_errors)
    errors = list(dict.fromkeys(errors))
    if errors and not diagnostic_allowed:
        raise RetrievalGateError("; ".join(errors))
    expected_record_ids = _retrieval_expected_record_ids(audit)
    prepared_execution = _prepare_execution_capture(
        brief,
        stage="retrieval",
        provenance_path=args.execution_provenance,
        transcript_path=args.execution_transcript,
        predecessor_completed_at=plan_receipt.get("completed_at"),
        expected_inputs={
            "artifacts/research/execution/retrieval-input.jsonl": sha256_file(args.input_jsonl)
        },
        expected_record_ids=expected_record_ids,
    )
    source_path, manifest_path, audit_path = _promote_retrieval_artifacts(
        layout, generation, sources, manifests, audit
    )
    plan_path = layout.artifact(generation, "research/research-plan.json")
    snapshot_paths = [
        resolve_snapshot(
            layout.evidence_cache(generation, "."), str(item["snapshot_ref"])
        )
        for item in manifests
    ]
    audit_snapshot_refs: set[str] = set()
    for record in audit:
        if record.get("record_kind") == "search_run":
            audit_snapshot_refs.add(str(record["raw_artifact"]))
            audit_snapshot_refs.add(str(record["request_artifact"]))
        elif record.get("record_kind") == "candidate":
            for outcome in record.get("resolver_outcomes", []):
                if isinstance(outcome, dict) and outcome.get("status") != "skipped":
                    audit_snapshot_refs.add(str(outcome["raw_artifact"]))
    snapshot_paths.extend(
        resolve_snapshot(layout.evidence_cache(generation, "."), ref)
        for ref in sorted(audit_snapshot_refs)
    )
    snapshot_paths = list(dict.fromkeys(snapshot_paths))
    stage_outputs = [source_path, manifest_path, audit_path, *snapshot_paths]
    debt_outputs: list[Path] = []
    if errors:
        debt_path = _write_blocking_debt_ledger(
            layout,
            generation,
            stage="retrieval",
            errors=errors,
            input_artifacts={
                "retrieval_input_jsonl": sha256_file(args.input_jsonl),
            },
            measurements={
                "expected_record_ids": expected_record_ids,
                "record_counts": _retrieval_record_counts(audit),
                "planned_query_count": len(planned_ids),
                "covered_query_count": len(covered_ids),
                "missing_query_ids": missing,
            },
        )
        debt_outputs.append(debt_path)
    execution_inputs: list[Path] = []
    if prepared_execution is not None:
        retrieval_input_copy = layout.artifact(
            generation, "research/execution/retrieval-input.jsonl"
        )
        atomic_copy_file(args.input_jsonl, retrieval_input_copy)
        execution_inputs.append(retrieval_input_copy)
    execution_outputs = _write_execution_capture(
        layout,
        generation,
        stage="retrieval",
        prepared=prepared_execution,
        output_paths=stage_outputs,
    )
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
        output_paths=[*stage_outputs, *debt_outputs, *execution_inputs, *execution_outputs],
    )
    _refresh_current_retrieval_view(layout, sources, manifests, audit)
    if errors:
        print(
            f"Diagnostic ingest recorded {len(errors)} blocking retrieval debts in {layout.root}"
        )
    else:
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
    audit: list[dict[str, object]],
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
    unresolved_tasklets: set[str] = set()
    gap_fill_queries = {
        str(item.get("query_id"))
        for item in audit
        if item.get("record_kind") == "search_run"
        and item.get("pass_kind") == "gap_fill"
        and item.get("execution_status") in {"completed", "zero_results"}
    }
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
        elif finding.get("status") == "needs_more_evidence":
            question_id = str(finding.get("question_id", ""))
            if question_id not in gap_fill_queries:
                errors.append(
                    f"finding {finding_id} needs_more_evidence requires a completed gap_fill search"
                )
            else:
                unresolved_tasklets.add(tasklet_id)
    if require_tasklet_coverage:
        missing = sorted(set(tasklet_by_id) - usable_tasklets - unresolved_tasklets)
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
    tasklets: list[dict[str, object]],
    findings: list[dict[str, object]],
    audit: list[dict[str, object]],
    manifests: list[dict[str, object]],
) -> dict[str, object]:
    usable = [finding for finding in findings if finding.get("status") == "usable"]
    covered_tasklets = sorted({str(finding.get("tasklet_id")) for finding in usable})
    all_tasklets = sorted(str(tasklet.get("tasklet_id")) for tasklet in tasklets)
    claim_ids = sorted({
        str(claim_id)
        for finding in usable
        for claim_id in finding.get("claim_ids", [])
    })
    unresolved_tasklets = sorted({
        str(finding.get("tasklet_id"))
        for finding in findings
        if finding.get("status") == "needs_more_evidence"
    })
    gap_fill_required = sorted({
        str(finding.get("question_id"))
        for finding in findings
        if finding.get("status") == "needs_more_evidence"
    })
    gap_fill_completed = sorted({
        str(record.get("query_id"))
        for record in audit
        if record.get("record_kind") == "search_run"
        and record.get("pass_kind") == "gap_fill"
        and record.get("execution_status") in {"completed", "zero_results"}
    })
    candidate_ids_by_source: dict[str, set[str]] = {}
    for manifest in manifests:
        candidate_ids_by_source.setdefault(
            str(manifest.get("source_id")), set()
        ).add(str(manifest.get("candidate_id")))
    wave_rows: list[dict[str, object]] = []
    finding_by_id = {
        str(finding.get("finding_id")): finding for finding in usable
    }
    for wave in audit:
        if wave.get("record_kind") != "search_wave":
            continue
        new_candidate_ids = {
            str(item) for item in wave.get("new_candidate_ids", [])
        }
        candidate_finding_ids = {
            str(finding.get("finding_id"))
            for finding in usable
            if any(
                candidate_ids_by_source.get(str(source_id), set()) & new_candidate_ids
                for source_id in finding.get("source_ids", [])
            )
        }
        submitted_finding_ids = {
            str(item) for item in wave.get("new_finding_ids", [])
        }
        new_finding_ids = sorted(
            candidate_finding_ids
            | (submitted_finding_ids & set(finding_by_id))
        )
        new_source_ids = sorted({
            str(manifest.get("source_id"))
            for manifest in manifests
            if str(manifest.get("candidate_id")) in new_candidate_ids
        })
        new_contradiction_ids = sorted({
            str(item) for item in wave.get("new_contradiction_ids", [])
            if re.fullmatch(r"X\d{3}", str(item))
        })
        new_uncertainty_ids = sorted({
            str(item) for item in wave.get("new_uncertainty_ids", [])
            if re.fullmatch(r"U\d{3}", str(item))
        })
        finding_claim_ids = {
            str(claim_id)
            for finding_id in new_finding_ids
            for claim_id in finding_by_id[finding_id].get("claim_ids", [])
        }
        changed_claim_ids = sorted({
            str(item) for item in wave.get("changed_claim_ids", [])
            if re.fullmatch(r"C\d{3}", str(item))
        } | finding_claim_ids)
        independent_claim_changes = set(changed_claim_ids) - finding_claim_ids
        material_delta = (
            len(new_finding_ids)
            + len(new_contradiction_ids)
            + len(new_uncertainty_ids)
            + len(independent_claim_changes)
        )
        submitted_delta = wave.get("material_delta")
        declaration_errors: list[str] = []
        if submitted_delta is not None and submitted_delta != material_delta:
            declaration_errors.append(
                f"{wave.get('wave_id')} submitted material_delta does not recompute"
            )
        submitted_sources = {str(item) for item in wave.get("new_source_ids", [])}
        if submitted_sources and submitted_sources != set(new_source_ids):
            declaration_errors.append(
                f"{wave.get('wave_id')} submitted new_source_ids do not recompute"
            )
        wave_rows.append({
            "wave_id": str(wave.get("wave_id")),
            "gap_id": str(wave.get("gap_id")),
            "question_ids": list(wave.get("question_ids", [])),
            "search_run_ids": list(wave.get("search_run_ids", [])),
            "new_candidate_ids": sorted(new_candidate_ids),
            "new_source_ids": new_source_ids,
            "new_usable_finding_ids": new_finding_ids,
            "new_contradiction_ids": new_contradiction_ids,
            "new_uncertainty_ids": new_uncertainty_ids,
            "changed_claim_ids": changed_claim_ids,
            "submitted_material_delta": submitted_delta,
            "material_delta": material_delta,
            "declaration_errors": declaration_errors,
        })
    waves_by_gap: dict[str, list[dict[str, object]]] = {}
    for wave in wave_rows:
        waves_by_gap.setdefault(str(wave["gap_id"]), []).append(wave)
    declarations = {
        str(item.get("gap_id")): item
        for item in audit
        if item.get("record_kind") == "gap_assessment"
    }
    saturation_assessments: list[dict[str, object]] = []
    for gap_id in sorted(set(waves_by_gap) | set(declarations)):
        waves = waves_by_gap.get(gap_id, [])
        ordered = sorted(waves, key=lambda item: str(item["wave_id"]))
        declaration = declarations.get(gap_id)
        declared_state = str((declaration or {}).get("terminal_state", "open"))
        supporting_ids = [str(item) for item in (declaration or {}).get("supporting_wave_ids", [])]
        supporting = [item for item in ordered if str(item["wave_id"]) in supporting_ids]
        saturated = (
            declared_state == "saturated"
            and len(supporting) >= 2
            and all(int(item["material_delta"]) == 0 for item in supporting[-2:])
        )
        terminal_state = (
            "saturated" if saturated else
            declared_state if declared_state in {
                "bounded_corpus_exhausted", "access_limited_uncertainty", "out_of_scope"
            } else "open"
        )
        saturation_assessments.append({
            "gap_id": gap_id,
            "terminal_state": terminal_state,
            "supporting_wave_ids": supporting_ids,
            "material_deltas": [int(item["material_delta"]) for item in supporting],
            "question_ids": sorted({
                str(question_id) for item in supporting
                for question_id in item.get("question_ids", [])
            }),
            "uncertainty_id": (declaration or {}).get("uncertainty_id"),
            "review_concern_id": (declaration or {}).get("review_concern_id"),
            "raw_result_count": (declaration or {}).get("raw_result_count"),
            "deduplicated_candidate_count": (declaration or {}).get("deduplicated_candidate_count"),
            "screened_candidate_ids": list((declaration or {}).get("screened_candidate_ids", [])),
            "result_windows_retrieved": (declaration or {}).get("result_windows_retrieved"),
            "total_result_windows": (declaration or {}).get("total_result_windows"),
            "enumeration_complete": (declaration or {}).get("enumeration_complete"),
            "access_limitations": list((declaration or {}).get("access_limitations", []))
            if isinstance((declaration or {}).get("access_limitations"), list)
            else None,
            "reason": (
                str(declaration.get("reason")) if declaration and terminal_state != "open"
                else "The gap lacks a valid declared terminal assessment."
            ),
        })
    return {
        "schema_version": "2.0",
        "tasklets_total": len(tasklets),
        "tasklets_with_usable_findings": len(covered_tasklets),
        "usable_findings": len(usable),
        "missing_tasklet_ids": sorted(
            set(all_tasklets) - set(covered_tasklets) - set(unresolved_tasklets)
        ),
        "claim_ids_linked": claim_ids,
        "academic_baseline_complete": any(
            record.get("record_kind") == "search_run"
            and record.get("pass_kind") == "baseline"
            and record.get("surface_class") == "scholarly_index"
            and record.get("execution_status") in {"completed", "zero_results"}
            for record in audit
        ),
        "corpus_seeded_question_ids": sorted({
            str(record.get("query_id"))
            for record in audit
            if record.get("record_kind") == "search_run" and record.get("pass_kind") == "corpus"
        }),
        "gap_fill_required_query_ids": gap_fill_required,
        "gap_fill_completed_query_ids": gap_fill_completed,
        "zero_result_search_run_ids": sorted({
            str(record.get("search_run_id"))
            for record in audit
            if record.get("record_kind") == "search_run"
            and record.get("execution_status") == "zero_results"
        }),
        "unreachable_search_run_ids": sorted({
            str(record.get("search_run_id"))
            for record in audit
            if record.get("record_kind") == "search_run"
            and record.get("execution_status") == "unreachable"
        }),
        "unresolved_tasklet_ids": unresolved_tasklets,
        "search_waves": wave_rows,
        "saturation_assessments": saturation_assessments,
        "created_at": _utc_now(),
    }


def validate_maximal_saturation(
    brief: dict[str, object], coverage: dict[str, object]
) -> list[str]:
    if not _is_maximal_full_dossier(brief):
        return []
    errors: list[str] = []
    for wave in coverage.get("search_waves", []):
        if isinstance(wave, dict):
            errors.extend(str(item) for item in wave.get("declaration_errors", []))
    if coverage.get("missing_tasklet_ids"):
        errors.append("maximal_full_dossier requires every STORM tasklet to have a disposition")
    assessments = coverage.get("saturation_assessments")
    if not isinstance(assessments, list) or not assessments:
        return errors + [
            "maximal_full_dossier requires retrieval saturation assessments; source count cannot close Max"
        ]
    for assessment in assessments:
        if not isinstance(assessment, dict):
            errors.append("maximal saturation assessment must be an object")
            continue
        if assessment.get("terminal_state") not in {
            "saturated", "bounded_corpus_exhausted",
            "access_limited_uncertainty", "out_of_scope",
        }:
            errors.append(
                f"{assessment.get('gap_id')} lacks a valid terminal gap disposition"
            )
        if assessment.get("terminal_state") == "bounded_corpus_exhausted":
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
                    f"{assessment.get('gap_id')} bounded corpus exhaustion requires complete result-window enumeration"
                )
            if not isinstance(assessment.get("access_limitations"), list) or not all(
                isinstance(item, str) for item in assessment.get("access_limitations", [])
            ):
                errors.append(
                    f"{assessment.get('gap_id')} bounded corpus exhaustion requires access-limit disclosure"
                )
        if assessment.get("terminal_state") == "access_limited_uncertainty" and not assessment.get("uncertainty_id"):
            errors.append(f"{assessment.get('gap_id')} access limitation lacks uncertainty binding")
    terminal_questions = {
        str(question_id)
        for assessment in assessments if isinstance(assessment, dict)
        for question_id in assessment.get("question_ids", [])
        if assessment.get("terminal_state") != "open"
    }
    unresolved_questions = {
        str(item) for item in coverage.get("gap_fill_required_query_ids", [])
    }
    missing_questions = sorted(unresolved_questions - terminal_questions)
    if missing_questions:
        errors.append(
            "maximal unresolved tasklets lack terminal gap assessments: "
            + ", ".join(missing_questions)
        )
    return list(dict.fromkeys(errors))


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
    recorded_at = _utc_now()
    for finding in findings:
        finding["created_at"] = recorded_at
    plan = load_json(layout.artifact(generation, "research/research-plan.json"))
    source_plan = load_json(layout.artifact(generation, "research/source-plan.json"))
    tasklets = load_jsonl(layout.artifact(generation, "research/storm-tasklets.jsonl"))
    sources = load_jsonl(layout.artifact(generation, "research/source-register.jsonl"))
    manifests = load_jsonl(layout.artifact(generation, "research/retrieval-manifest.jsonl"))
    audit = load_jsonl(layout.artifact(generation, "research/retrieval-audit.jsonl"))
    errors = validate_storm_tasklets(tasklets, plan, source_plan)
    errors.extend(validate_findings_pool(
        findings, tasklets, sources, manifests, audit,
        require_tasklet_coverage=_is_full_external_dossier(brief),
    ))
    if errors:
        raise EvidenceGateError("; ".join(dict.fromkeys(errors)))
    coverage = findings_coverage(tasklets, findings, audit, manifests)
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
    fields = {
        "uncertainty_id", "claim_id", "question_ids", "tasklet_ids",
        "description", "impact", "next_evidence",
    }
    errors = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict) or set(record) != fields:
            errors.append(f"uncertainty {index} has invalid fields")
        elif not all(str(record.get(field, "")).strip() for field in ("uncertainty_id", "description", "impact", "next_evidence")):
            errors.append(f"uncertainty {index} has empty required fields")
        else:
            for field, pattern in (("question_ids", r"Q\d{3}"), ("tasklet_ids", r"T\d{3}")):
                values = record.get(field)
                if not isinstance(values, list) or not all(re.fullmatch(pattern, str(item)) for item in values):
                    errors.append(f"uncertainty {index} has invalid {field}")
            if not record.get("claim_id") and not record.get("question_ids") and not record.get("tasklet_ids"):
                errors.append(f"uncertainty {index} must bind a claim, question, or tasklet")
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
    absence_searches: list[dict[str, object]],
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
    if absence_searches:
        absence_path = layout.artifact(generation, "research/absence-search-ledger.jsonl")
        atomic_write_text(absence_path, _jsonl_text(absence_searches))
        outputs.append(absence_path)
    staging.rmdir()
    return outputs


def _refresh_current_evidence_view(
    layout: RunLayout,
    claims: list[dict[str, object]],
    contradictions: dict[str, object],
    uncertainties: dict[str, object],
    outline: dict[str, object],
    absence_searches: list[dict[str, object]],
) -> None:
    root = package_child(layout.root, "current/research")
    atomic_write_text(root / "claim-evidence-ledger.jsonl", _jsonl_text(claims))
    atomic_write_json(root / "contradiction-ledger.json", contradictions)
    atomic_write_json(root / "uncertainty-ledger.json", uncertainties)
    atomic_write_json(root / "report-outline.json", outline)
    if absence_searches:
        atomic_write_text(root / "absence-search-ledger.jsonl", _jsonl_text(absence_searches))


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
        absence_searches = load_jsonl(args.absence_searches) if args.absence_searches else []
    except ContractError as exc:
        raise EvidenceGateError(str(exc)) from exc
    research_plan_path = layout.artifact(generation, "research/research-plan.json")
    source_plan_path = layout.artifact(generation, "research/source-plan.json")
    tasklet_path = layout.artifact(generation, "research/storm-tasklets.jsonl")
    findings_path = layout.artifact(generation, "research/storm-findings-pool.jsonl")
    coverage_path = layout.artifact(generation, "research/finding-coverage.json")
    manifest_path = layout.artifact(generation, "research/retrieval-manifest.jsonl")
    audit_path = layout.artifact(generation, "research/retrieval-audit.jsonl")
    research_plan = load_json(research_plan_path)
    source_plan = load_json(source_plan_path)
    manifests = load_jsonl(manifest_path)
    audit = load_jsonl(audit_path)
    question_ids = {
        str(item.get("question_id"))
        for item in research_plan.get("questions", [])
        if isinstance(item, dict)
    }
    claim_ids = {str(item.get("claim_id")) for item in claims}
    errors = validate_report_outline(outline, brief, question_ids, claim_ids)
    errors.extend(validate_claim_closure(claims, sources, outline, manifests))
    errors.extend(validate_absence_searches(claims, absence_searches, sources, manifests, brief))
    errors.extend(validate_theory_claim_sources(claims, sources, brief))
    errors.extend(validate_material_claim_prose(claims, brief))
    if _is_maximal_full_dossier(brief):
        errors.extend(validate_material_capture_depth(claims, manifests))
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
                findings, tasklets, sources, manifests, audit,
                require_tasklet_coverage=True,
            ))
            errors.extend(validate_findings_claim_links(claims, findings))
            coverage = load_json(coverage_path)
            errors.extend(validate_maximal_saturation(brief, coverage))
            uncertainty_ids = {
                str(record.get("uncertainty_id"))
                for record in uncertainties.get("uncertainties", [])
                if isinstance(record, dict)
            }
            for assessment in coverage.get("saturation_assessments", []):
                if not isinstance(assessment, dict):
                    continue
                if assessment.get("terminal_state") == "access_limited_uncertainty" and str(assessment.get("uncertainty_id")) not in uncertainty_ids:
                    errors.append(
                        f"{assessment.get('gap_id')} access limitation is not registered in uncertainty ledger"
                    )
            unresolved = set(str(item) for item in coverage.get("unresolved_tasklet_ids", []))
            uncertainty_bindings: dict[str, int] = {}
            for record in uncertainties.get("uncertainties", []):
                if not isinstance(record, dict):
                    continue
                for tasklet_id in record.get("tasklet_ids", []):
                    key = str(tasklet_id)
                    uncertainty_bindings[key] = uncertainty_bindings.get(key, 0) + 1
            for tasklet_id in sorted(unresolved):
                count = uncertainty_bindings.get(tasklet_id, 0)
                if count == 0:
                    errors.append(f"unresolved tasklet {tasklet_id} is absent from uncertainty ledger")
                elif count > 1:
                    errors.append(f"unresolved tasklet {tasklet_id} appears in multiple uncertainty records")
    strict_lens = _storm_lens_mode(brief) == "strict"
    p2_path = _storm_lens_artifact_path(layout, generation, "P2")
    p3_path = _storm_lens_artifact_path(layout, generation, "P3")
    p2_receipt_inputs: dict[str, str] = {}
    p3_receipt_inputs: dict[str, str] = {}
    if strict_lens or p2_path.is_file() or p3_path.is_file():
        p2_expected_inputs = _storm_lens_expected_inputs(layout, generation, "P2")
        p2, p2_receipt_inputs = _optional_lens_inputs(
            layout, generation, "P2", p2_expected_inputs, required=strict_lens,
        )
        if p2:
            if not findings:
                findings = load_jsonl(findings_path)
            errors.extend(_validate_p2_against_research_state(p2, findings, contradictions, uncertainties))
    if strict_lens or p3_path.is_file():
        p3_expected_inputs = _storm_lens_expected_inputs(layout, generation, "P3")
        p3, p3_receipt_inputs = _optional_lens_inputs(
            layout, generation, "P3", p3_expected_inputs, required=strict_lens,
        )
        if p3:
            if not findings:
                findings = load_jsonl(findings_path)
            errors.extend(_validate_p3_against_evidence_inputs(p3, outline, claims, findings))
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
        layout, generation, claims, contradictions, uncertainties, outline, absence_searches
    )
    evidence_inputs = {
        "artifacts/research/research-plan.json": sha256_file(research_plan_path),
        "artifacts/research/source-plan.json": sha256_file(source_plan_path),
        "artifacts/research/source-register.jsonl": sha256_file(source_path),
        "artifacts/research/retrieval-manifest.jsonl": sha256_file(manifest_path),
        "artifacts/research/retrieval-audit.jsonl": sha256_file(audit_path),
        "artifacts/research/storm-tasklets.jsonl": sha256_file(tasklet_path),
    }
    if findings_path.is_file() and not findings_path.is_symlink():
        evidence_inputs["artifacts/research/storm-findings-pool.jsonl"] = sha256_file(findings_path)
    if coverage_path.is_file() and not coverage_path.is_symlink():
        evidence_inputs["artifacts/research/finding-coverage.json"] = sha256_file(coverage_path)
    evidence_inputs.update(p2_receipt_inputs)
    evidence_inputs.update(p3_receipt_inputs)
    commit_stage_receipt(
        layout,
        generation=generation,
        stage=Stage.EVIDENCE,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts=evidence_inputs,
        output_paths=outputs,
    )
    _refresh_current_evidence_view(layout, claims, contradictions, uncertainties, outline, absence_searches)
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


def _source_key_by_id(sources: list[dict[str, object]]) -> dict[str, str]:
    return {
        str(source.get("source_id")): key
        for key, source in citation_index(sources).items()
    }


def _sidecar_directives(path: Path) -> dict[str, dict[str, object]]:
    records = load_jsonl(path)
    result: dict[str, dict[str, object]] = {}
    for index, record in enumerate(records, start=1):
        locator = str(record.get("text_locator") or "")
        if not locator and record.get("paragraph_index") is not None:
            locator = f"paragraph:{record['paragraph_index']}"
        if not locator:
            raise CLIContractError(f"paragraph map sidecar row {index} lacks text_locator")
        result[locator] = record
    return result


def _paragraph_type_for_claim(claim: dict[str, object] | None) -> str:
    claim_type = str((claim or {}).get("claim_type", "factual"))
    return "factual" if claim_type == "fact" else claim_type


def _build_paragraph_record(
    paragraph: object,
    directive: dict[str, object],
    claims_by_id: dict[str, dict[str, object]],
    source_key_by_id: dict[str, str],
) -> dict[str, object]:
    claim_ids = [str(item) for item in directive.get("claim_ids", [])]
    unknown_claims = sorted(set(claim_ids) - set(claims_by_id))
    if unknown_claims:
        raise CLIContractError("paragraph directive references unknown claims: " + ", ".join(unknown_claims))
    source_ids = [str(item) for item in directive.get("source_ids", [])]
    if not source_ids:
        collected: list[str] = []
        for claim_id in claim_ids:
            claim = claims_by_id[claim_id]
            collected.extend(str(item) for item in claim.get("supporting_source_ids", []))
            collected.extend(str(item) for item in claim.get("contradicting_source_ids", []))
        source_ids = list(dict.fromkeys(collected))
    unknown_sources = sorted(set(source_ids) - set(source_key_by_id))
    if unknown_sources:
        raise CLIContractError("paragraph directive references unknown sources: " + ", ".join(unknown_sources))
    citation_keys = [str(item) for item in directive.get("citation_keys", [])]
    if not citation_keys:
        citation_keys = [source_key_by_id[source_id] for source_id in source_ids if source_id in source_key_by_id]
    first_claim = claims_by_id.get(claim_ids[0]) if claim_ids else None
    paragraph_type = str(directive.get("paragraph_type") or _paragraph_type_for_claim(first_claim))
    return {
        "schema_version": "2.0",
        "paragraph_sha256": getattr(paragraph, "sha256"),
        "paragraph_type": paragraph_type,
        "claim_ids": claim_ids,
        "source_ids": source_ids,
        "citation_keys": citation_keys,
        "text_locator": getattr(paragraph, "locator"),
    }


def _inline_directives_by_locator(draft_text: str) -> dict[str, dict[str, object]]:
    directives = mapping_directives(draft_text)
    paragraphs = extract_paragraphs(strip_mapping_comments(draft_text))
    if len(directives) != len(paragraphs):
        raise CLIContractError(
            f"inline storm-map directives must match paragraph count: {len(directives)} directives for {len(paragraphs)} paragraphs"
        )
    return {
        getattr(paragraph, "locator"): directive
        for paragraph, directive in zip(paragraphs, directives, strict=True)
    }


def build_paragraph_map_records(
    draft_text: str,
    directives_by_locator: dict[str, dict[str, object]],
    claims: list[dict[str, object]],
    sources: list[dict[str, object]],
) -> list[dict[str, object]]:
    claims_by_id = {str(claim.get("claim_id")): claim for claim in claims}
    source_key_by_id = _source_key_by_id(sources)
    records: list[dict[str, object]] = []
    for paragraph in extract_paragraphs(strip_mapping_comments(draft_text)):
        directive = directives_by_locator.get(getattr(paragraph, "locator"))
        if directive is None:
            raise CLIContractError(f"paragraph lacks mapping directive: {getattr(paragraph, 'locator')}")
        record = _build_paragraph_record(paragraph, directive, claims_by_id, source_key_by_id)
        errors = validate_paragraph_record(record)
        if errors:
            raise CLIContractError(f"{getattr(paragraph, 'locator')}: {'; '.join(errors)}")
        records.append(record)
    return records


def command_build_paragraph_map(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.DRAFT, package_hash)
    if layout.receipt(generation, Stage.DRAFT).exists():
        raise StagePreconditionError("cannot build paragraph map after draft receipt exists")
    draft_text = args.draft_md.read_text(encoding="utf-8")
    directives = (
        _sidecar_directives(args.sidecar_jsonl)
        if args.sidecar_jsonl
        else _inline_directives_by_locator(draft_text)
    )
    claims = load_jsonl(layout.artifact(generation, "research/claim-evidence-ledger.jsonl"))
    sources = load_jsonl(layout.artifact(generation, "research/source-register.jsonl"))
    records = build_paragraph_map_records(draft_text, directives, claims, sources)
    report = generate_references(draft_text, sources)
    errors = validate_report_traceability(report, records, claims, sources)
    if errors:
        raise DraftGateError("; ".join(dict.fromkeys(errors)))
    target = args.to or args.draft_md.with_name("paragraph-map.jsonl")
    if target.exists() or target.is_symlink():
        raise CLIContractError(f"paragraph map output already exists: {target}")
    atomic_write_text(target, _jsonl_text(records))
    _print_json({
        "schema_version": "2.0",
        "mode": "build-paragraph-map",
        "paragraph_count": len(records),
        "output_jsonl": str(target),
    })
    return EXIT_OK


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
    errors.extend(audit_boilerplate_errors(report, "draft"))
    errors.extend(validate_maximal_report_source_coverage(report, sources, brief))
    length_contract = brief.get("length_contract") if isinstance(brief.get("length_contract"), dict) else {}
    unit = str(length_contract.get("unit", "words"))
    measured = body_length(report, unit)
    policy = str(length_contract.get("policy", "bounded"))
    minimum = length_contract.get("minimum") if policy == "bounded" else None
    maximum = length_contract.get("maximum") if policy == "bounded" else None
    if policy == "bounded":
        lower = int(minimum or 1)
        upper = int(maximum or 0)
        if measured < lower or measured > upper:
            errors.append(f"draft body length {measured} {unit} is outside {lower}-{upper}")
    errors.extend(quote_limit_errors(report, unit))
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
            "policy": policy,
            "measured": measured,
            "unit": unit,
            "minimum": minimum,
            "maximum": maximum,
            "within_range": True if policy == "open_ended" else int(minimum or 1) <= measured <= int(maximum or 0),
            "references_excluded": True,
            "quoted_blocks_excluded": True,
            "quoted": quoted_length(report, unit),
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
    errors.extend(audit_boilerplate_errors(report, "draft"))
    errors.extend(validate_maximal_report_source_coverage(report, sources, brief))
    length_contract = brief.get("length_contract") if isinstance(brief.get("length_contract"), dict) else {}
    unit = str(length_contract.get("unit", "words"))
    measured = body_length(report, unit)
    if str(length_contract.get("policy", "bounded")) == "bounded":
        minimum = int(length_contract.get("minimum", 1))
        maximum = int(length_contract.get("maximum", 0))
        if measured < minimum or measured > maximum:
            errors.append(
                f"draft body length {measured} {unit} is outside {minimum}-{maximum}"
            )
    elif str(length_contract.get("policy")) != "open_ended":
        errors.append(
            "draft length_contract.policy must be bounded or open_ended"
        )
    errors.extend(quote_limit_errors(report, unit))
    if errors:
        raise DraftGateError("; ".join(dict.fromkeys(errors)))
    evidence_receipt = load_json(layout.receipt(generation, Stage.EVIDENCE))
    prepared_execution = _prepare_execution_capture(
        brief,
        stage="draft",
        provenance_path=args.execution_provenance,
        transcript_path=args.execution_transcript,
        predecessor_completed_at=evidence_receipt.get("completed_at"),
        expected_inputs={
            "artifacts/research/execution/draft-input.md": sha256_file(args.draft_md),
            "artifacts/research/execution/draft-paragraph-map-input.jsonl": sha256_file(args.paragraph_map_jsonl),
        },
        expected_record_ids=sorted(str(claim.get("claim_id")) for claim in claims),
    )
    citations = citation_index(sources)
    outputs = _promote_draft_artifacts(
        layout, generation, report, paragraph_map, citations
    )
    execution_inputs: list[Path] = []
    if prepared_execution is not None:
        draft_input_copy = layout.artifact(
            generation, "research/execution/draft-input.md"
        )
        map_input_copy = layout.artifact(
            generation, "research/execution/draft-paragraph-map-input.jsonl"
        )
        atomic_copy_file(args.draft_md, draft_input_copy)
        atomic_copy_file(args.paragraph_map_jsonl, map_input_copy)
        execution_inputs.extend([draft_input_copy, map_input_copy])
    execution_outputs = _write_execution_capture(
        layout,
        generation,
        stage="draft",
        prepared=prepared_execution,
        output_paths=outputs,
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
        output_paths=[*outputs, *execution_inputs, *execution_outputs],
    )
    _refresh_current_draft_view(layout, report, paragraph_map, citations)
    print(f"Drafted {layout.root}")
    return EXIT_OK


def _validate_revision_map(
    payload: dict[str, object],
    repair_actions: list[dict[str, object]],
    *,
    draft_sha256: str,
    candidate_sha256: str,
    review_concerns: dict[str, dict[str, object]] | None = None,
) -> list[str]:
    if set(payload) != {"schema_version", "revisions"} or payload.get("schema_version") != "2.0":
        return ["revision map has invalid top-level contract"]
    revisions = payload.get("revisions")
    if not isinstance(revisions, list):
        return ["revision map revisions must be an array"]
    errors: list[str] = []
    target_actions = {
        str(action.get("action_id")): action for action in repair_actions
        if isinstance(action, dict)
    }
    applied: set[str] = set()
    fields = {"action_id", "before_sha256", "after_sha256", "action", "status", "reason"}
    for index, revision in enumerate(revisions, start=1):
        if not isinstance(revision, dict) or set(revision) != fields:
            errors.append(f"revision {index} has invalid fields")
            continue
        action_id = str(revision.get("action_id", ""))
        action = target_actions.get(action_id)
        if action is None:
            if not re.fullmatch(r"RC\d{3}", action_id):
                errors.append(f"revision {index} does not resolve a review action")
                continue
            if revision.get("status") not in {"applied", "waived", "preserved_as_uncertainty"}:
                errors.append(f"revision {index} review concern status is invalid")
            if not _is_sha256(revision.get("before_sha256")) or not _is_sha256(revision.get("after_sha256")):
                errors.append(f"revision {index} review concern hashes are invalid")
            if revision.get("status") == "applied" and revision.get("before_sha256") == revision.get("after_sha256"):
                errors.append(f"revision {index} applied review concern did not change its target")
            if not str(revision.get("action", "")).strip():
                errors.append(f"revision {index} review concern action is required")
            if revision.get("status") != "applied" and not str(revision.get("reason", "")).strip():
                errors.append(f"revision {index} review concern terminal reason is required")
            concern = (review_concerns or {}).get(action_id)
            if review_concerns is not None and concern is None:
                errors.append(f"revision {index} does not match a registered review concern")
            elif concern is not None:
                if revision.get("before_sha256") != concern.get("target_sha256"):
                    errors.append(f"revision {index} before_sha256 does not match review concern target")
                if revision.get("action") != concern.get("required_action"):
                    errors.append(f"revision {index} action does not match review concern")
                terminal = str(concern.get("terminal_disposition", ""))
                expected_status = {
                    "addressed": "applied",
                    "waived": "waived",
                    "preserved_as_uncertainty": "preserved_as_uncertainty",
                }.get(terminal)
                if expected_status and revision.get("status") != expected_status:
                    errors.append(f"revision {index} status does not match review concern closure")
            applied.add(action_id)
            continue
        if revision.get("before_sha256") != action.get("before_sha256"):
            errors.append(f"revision {index} before_sha256 does not match P4 action")
        if revision.get("action") != action.get("action"):
            errors.append(f"revision {index} action does not match P4 action")
        required_status = "applied" if action.get("disposition") == "required" else "waived"
        if revision.get("status") != required_status:
            errors.append(f"revision {index} must be {required_status}")
        if required_status == "waived" and not str(revision.get("reason", "")).strip():
            errors.append(f"revision {index} waiver requires a reason")
        if action.get("target_kind") == "draft":
            if revision.get("before_sha256") != draft_sha256:
                errors.append(f"revision {index} draft before_sha256 mismatch")
            if required_status == "applied" and revision.get("after_sha256") != candidate_sha256:
                errors.append(f"revision {index} draft after_sha256 mismatch")
        if not _is_sha256(revision.get("after_sha256")):
            errors.append(f"revision {index} after_sha256 is invalid")
        applied.add(action_id)
    missing = sorted(set(target_actions) - applied)
    if missing:
        errors.append("P4 repair actions are not closed in revision map")
    return errors


def _review_concerns_by_id(loop: dict[str, object] | None) -> dict[str, dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    if not isinstance(loop, dict):
        return grouped
    for round_record in loop.get("rounds", []):
        if not isinstance(round_record, dict):
            continue
        for concern in round_record.get("required_concerns", []):
            if not isinstance(concern, dict):
                continue
            concern_id = str(concern.get("concern_id", ""))
            if not re.fullmatch(r"RC\d{3}", concern_id):
                continue
            current = grouped.setdefault(concern_id, dict(concern))
            if concern.get("disposition") in {"addressed", "waived", "preserved_as_uncertainty"}:
                current["terminal_disposition"] = concern.get("disposition")
                current["terminal_reason"] = concern.get("reason")
    return grouped


def _review_block_path(layout: RunLayout, generation: int) -> Path:
    return package_child(
        layout.root, f"state/generations/g{generation:04d}/review-blocked.json"
    )


def _open_review_concerns(loop: dict[str, object] | None) -> dict[str, dict[str, object]]:
    opened: dict[str, dict[str, object]] = {}
    terminal: set[str] = set()
    if not isinstance(loop, dict):
        return opened
    for round_record in loop.get("rounds", []):
        if not isinstance(round_record, dict):
            continue
        for concern in round_record.get("required_concerns", []):
            if not isinstance(concern, dict):
                continue
            concern_id = str(concern.get("concern_id", ""))
            if concern.get("disposition") == "open" and re.fullmatch(r"RC\d{3}", concern_id):
                opened[concern_id] = concern
            elif concern.get("disposition") in {
                "addressed", "waived", "preserved_as_uncertainty",
            }:
                terminal.add(concern_id)
    return {key: value for key, value in opened.items() if key not in terminal}


def _persist_review_block(
    layout: RunLayout,
    generation: int,
    loop: dict[str, object],
    errors: list[str],
    *,
    provenance: dict[str, object],
    request: dict[str, object],
    review_output_sha256: str,
    transcript_path: Path,
) -> None:
    concerns = _open_review_concerns(loop)
    if not concerns:
        return
    path = _review_block_path(layout, generation)
    required_stages = {
        concern_id: str(concern.get("required_stage") or "review")
        for concern_id, concern in sorted(concerns.items())
    }
    rounds = [item for item in loop.get("rounds", []) if isinstance(item, dict)]
    blocked_round_sha256 = str(rounds[-1].get("round_sha256", "")) if rounds else ""
    payload: dict[str, object] = {
        "schema_version": "2.0",
        "generation": generation,
        "review_loop_sha256": canonical_json_sha256(loop),
        "blocked_round_sha256": blocked_round_sha256,
        "review_request_sha256": str(request.get("request_sha256", "")),
        "review_provenance_sha256": canonical_json_sha256(provenance),
        "review_output_sha256": review_output_sha256,
        "review_transcript_sha256": sha256_file(transcript_path),
        "blocking_issue_ids": sorted(concerns),
        "required_stages": required_stages,
        "validation_errors": list(dict.fromkeys(errors)),
        "created_at": _utc_now(),
        "block_sha256": "0" * 64,
    }
    payload["block_sha256"] = canonical_json_sha256({
        key: value for key, value in payload.items() if key != "block_sha256"
    })
    if path.exists() or path.is_symlink():
        existing = load_json(path)
        if existing.get("review_loop_sha256") == payload["review_loop_sha256"]:
            return
        raise ReviewGateError(
            "review blocker record is immutable; create a new generation before re-review"
        )
    atomic_write_json(path, payload)
    append_journal_event(layout, {
        "event": "review_blocked",
        "generation": generation,
        "blocking_issue_ids": sorted(concerns),
        "block_sha256": payload["block_sha256"],
        "recorded_at": payload["created_at"],
    })


def _review_round_bindings(layout: RunLayout, through_generation: int) -> dict[int, dict[str, str]]:
    bindings: dict[int, dict[str, str]] = {}
    for generation in range(1, through_generation + 1):
        draft_receipt_path = layout.receipt(generation, Stage.DRAFT)
        request_path = layout.artifact(generation, "research/review-request.json")
        if not draft_receipt_path.is_file() or not request_path.is_file():
            continue
        draft_receipt = load_json(draft_receipt_path)
        request = load_json(request_path)
        item = {
            "draft_receipt_sha256": str(draft_receipt.get("receipt_sha256", "")),
            "review_request_sha256": str(request.get("request_sha256", "")),
        }
        block_path = _review_block_path(layout, generation)
        if block_path.is_file() and not block_path.is_symlink():
            block = load_json(block_path)
            item["blocked_round_sha256"] = str(block.get("blocked_round_sha256", ""))
        bindings[generation] = item
    return bindings


def _review_request_digest(payload: dict[str, object]) -> str:
    return canonical_json_sha256({key: value for key, value in payload.items() if key != "request_sha256"})


def command_review_prepare(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    generation = latest_generation(layout)
    if generation is None:
        raise StagePreconditionError("run has no generation")
    package_hash = compute_skill_package_hash(ROOT)
    verify_stage_precondition(layout, generation, Stage.REVIEW, package_hash)
    brief = verify_current_brief_view(layout, generation)
    if _captured_execution_required(brief):
        draft_provenance_path = layout.artifact(
            generation, "research/execution/draft-provenance.json"
        )
        if not draft_provenance_path.is_file() or draft_provenance_path.is_symlink():
            raise StagePreconditionError(
                "captured_host_execution review requires draft execution provenance"
            )
        draft_provenance = load_json(draft_provenance_path)
        if args.author_context_id != draft_provenance.get("context_id"):
            raise ReviewGateError(
                "review author context must match captured draft execution context"
            )
    p4_path = _storm_lens_artifact_path(layout, generation, "P4")
    p4, _ = _optional_lens_inputs(
        layout, generation, "P4", _storm_lens_expected_inputs(layout, generation, "P4"),
        required=_storm_lens_mode(brief) == "strict",
    )
    report = args.candidate_md.read_text(encoding="utf-8")
    paragraph_map = load_jsonl(args.candidate_map)
    revision_map = load_json(args.revision_map)
    claims = load_jsonl(layout.artifact(generation, "research/claim-evidence-ledger.jsonl"))
    sources = load_jsonl(layout.artifact(generation, "research/source-register.jsonl"))
    errors = validate_report_traceability(report, paragraph_map, claims, sources)
    repairs = list((p4 or {}).get("output", {}).get("repair_actions", []))
    draft_path = layout.artifact(generation, "drafts/report-v1.md")
    errors.extend(_validate_revision_map(
        revision_map, repairs,
        draft_sha256=sha256_file(draft_path),
        candidate_sha256=sha256_file(args.candidate_md),
    ))
    if errors:
        raise ReviewGateError("; ".join(dict.fromkeys(errors)))
    candidate_root = layout.artifact(generation, "review-candidate")
    request_path = layout.artifact(generation, "research/review-request.json")
    if request_path.exists() or request_path.is_symlink() or candidate_root.exists() or candidate_root.is_symlink():
        raise StagePreconditionError(
            "external review request is immutable; amend the run before preparing another candidate"
        )
    destinations = {
        "artifacts/review-candidate/report.md": candidate_root / "report.md",
        "artifacts/review-candidate/paragraph-map.jsonl": candidate_root / "paragraph-map.jsonl",
        "artifacts/review-candidate/revision-map.json": candidate_root / "revision-map.json",
    }
    for source, destination in (
        (args.candidate_md, destinations["artifacts/review-candidate/report.md"]),
        (args.candidate_map, destinations["artifacts/review-candidate/paragraph-map.jsonl"]),
        (args.revision_map, destinations["artifacts/review-candidate/revision-map.json"]),
    ):
        atomic_copy_file(source, destination)
    input_paths = {
        "artifacts/drafts/report-v1.md": draft_path,
        "artifacts/research/storm-lens-red-team.json": p4_path,
        "artifacts/research/claim-evidence-ledger.jsonl": layout.artifact(generation, "research/claim-evidence-ledger.jsonl"),
        "artifacts/research/source-register.jsonl": layout.artifact(generation, "research/source-register.jsonl"),
        "artifacts/research/contradiction-ledger.json": layout.artifact(generation, "research/contradiction-ledger.json"),
    }
    request: dict[str, object] = {
        "schema_version": "2.0",
        "request_id": f"RREQ-{uuid.uuid4().hex}",
        "run_id": layout.root.name,
        "generation": generation,
        "author_context_id": args.author_context_id,
        "created_at": _utc_now(),
        "input_artifacts": {key: sha256_file(path) for key, path in sorted(input_paths.items())},
        "candidate_artifacts": {key: sha256_file(path) for key, path in sorted(destinations.items())},
    }
    request["request_sha256"] = _review_request_digest(request)
    atomic_write_json(request_path, request)
    atomic_write_json(package_child(layout.root, "current/research/review-request.json"), request)
    print(f"Prepared external review request: {request_path}")
    return EXIT_OK


def _review_output_digest(payload: dict[str, list[dict[str, object]]]) -> str:
    return canonical_json_sha256(payload)


def _parse_datetime(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


EXECUTION_DECLARATION_FIELDS = {
    "schema_version", "provenance_id", "stage", "execution_kind",
    "context_id", "provider", "model", "runner", "execution_id",
    "started_at", "completed_at", "transcript_sha256", "input_artifacts",
    "record_ids", "provider_signed",
}


def _captured_execution_required(brief: dict[str, object]) -> bool:
    return brief.get("assurance_target") == "captured_host_execution"


def _execution_transcript_errors(text: str, *, label: str) -> list[str]:
    nonempty = [line.strip() for line in text.splitlines() if line.strip()]
    errors: list[str] = []
    if len(text.strip()) < 200:
        errors.append(f"{label} transcript must contain at least 200 characters")
    if len(nonempty) < 3:
        errors.append(f"{label} transcript must contain at least three non-empty lines")
    return errors


def _prepare_execution_capture(
    brief: dict[str, object],
    *,
    stage: str,
    provenance_path: Path | None,
    transcript_path: Path | None,
    predecessor_completed_at: object,
    expected_inputs: dict[str, str],
    expected_record_ids: list[str],
) -> tuple[dict[str, object], str] | None:
    required = _captured_execution_required(brief)
    if not required:
        if provenance_path is not None or transcript_path is not None:
            raise CLIContractError(
                "execution provenance is only accepted when assurance_target is captured_host_execution"
            )
        return None
    if provenance_path is None or transcript_path is None:
        raise CLIContractError(
            f"captured_host_execution {stage} requires --execution-provenance and --execution-transcript"
        )
    declaration = load_json(provenance_path)
    errors: list[str] = []
    if set(declaration) != EXECUTION_DECLARATION_FIELDS:
        errors.append(f"{stage} execution provenance has invalid fields")
    if declaration.get("schema_version") != "2.0":
        errors.append(f"{stage} execution provenance schema_version must be 2.0")
    if declaration.get("stage") != stage:
        errors.append(f"{stage} execution provenance stage mismatch")
    if declaration.get("execution_kind") != "host_execution":
        errors.append(f"{stage} execution provenance requires host_execution")
    if declaration.get("provider_signed") is not False:
        errors.append(f"{stage} execution provenance provider_signed must be false")
    for field in ("provenance_id", "context_id", "provider", "model", "runner", "execution_id"):
        if not isinstance(declaration.get(field), str) or not str(declaration.get(field, "")).strip():
            errors.append(f"{stage} execution provenance {field} is required")
    if not str(declaration.get("provenance_id", "")).startswith("EPROV-"):
        errors.append(f"{stage} execution provenance provenance_id is invalid")
    if declaration.get("input_artifacts") != expected_inputs:
        errors.append(f"{stage} execution provenance input artifact hashes do not match")
    if declaration.get("record_ids") != expected_record_ids:
        errors.append(f"{stage} execution provenance record_ids do not match")
    transcript = transcript_path.read_text(encoding="utf-8")
    if declaration.get("transcript_sha256") != sha256_file(transcript_path):
        errors.append(f"{stage} execution provenance transcript hash mismatch")
    errors.extend(_execution_transcript_errors(transcript, label=stage))
    predecessor = _parse_datetime(predecessor_completed_at)
    started = _parse_datetime(declaration.get("started_at"))
    completed = _parse_datetime(declaration.get("completed_at"))
    now = datetime.now(timezone.utc)
    if not predecessor or not started or not completed:
        errors.append(f"{stage} execution provenance timestamps are invalid")
    elif not (predecessor <= started < completed <= now + timedelta(minutes=5)):
        errors.append(f"{stage} execution provenance timestamps are not causal")
    if errors:
        raise CLIContractError("; ".join(dict.fromkeys(errors)))
    return declaration, transcript


def _write_execution_capture(
    layout: RunLayout,
    generation: int,
    *,
    stage: str,
    prepared: tuple[dict[str, object], str] | None,
    output_paths: list[Path],
) -> list[Path]:
    if prepared is None:
        return []
    declaration, transcript = prepared
    execution_root = layout.artifact(generation, "research/execution")
    transcript_path = execution_root / f"{stage}-transcript.txt"
    provenance_path = execution_root / f"{stage}-provenance.json"
    atomic_write_text(transcript_path, transcript)
    payload = dict(declaration)
    payload["transcript_ref"] = f"artifacts/research/execution/{stage}-transcript.txt"
    payload["output_artifacts"] = {
        path.relative_to(layout.generation_root(generation)).as_posix(): sha256_file(path)
        for path in output_paths
    }
    atomic_write_json(provenance_path, payload)
    return [provenance_path, transcript_path]


def _validate_review_provenance(
    provenance: dict[str, object],
    request: dict[str, object],
    review_output_sha256: str,
    transcript_path: Path,
    reviews: list[dict[str, object]],
    *,
    strict_execution: bool = False,
    review_loop: dict[str, object] | None = None,
) -> list[str]:
    fields = {
        "schema_version", "provenance_id", "review_session_id", "execution_kind",
        "author_context_id", "reviewer_context_id", "reviewer_identity", "provider",
        "model", "runner", "execution_id", "request_sha256", "review_output_sha256",
        "transcript_ref", "transcript_sha256", "started_at", "completed_at",
        "isolation_attestation", "review_sessions",
    }
    if set(provenance) != fields:
        return ["review provenance has invalid fields"]
    errors: list[str] = []
    if provenance.get("schema_version") != "2.0":
        errors.append("review provenance schema_version must be 2.0")
    if provenance.get("execution_kind") not in {"external_model", "human"}:
        errors.append("review provenance requires external_model or human execution")
    if provenance.get("author_context_id") != request.get("author_context_id"):
        errors.append("review provenance author context mismatch")
    if provenance.get("author_context_id") == provenance.get("reviewer_context_id"):
        errors.append("reviewer context must differ from author context")
    if provenance.get("request_sha256") != request.get("request_sha256"):
        errors.append("review provenance request hash mismatch")
    if provenance.get("review_output_sha256") != review_output_sha256:
        errors.append("review provenance output hash mismatch")
    if provenance.get("transcript_ref") != "artifacts/research/reviewer-transcript.txt":
        errors.append("review provenance transcript_ref is invalid")
    if provenance.get("transcript_sha256") != sha256_file(transcript_path):
        errors.append("review provenance transcript hash mismatch")
    if provenance.get("isolation_attestation") is not True:
        errors.append("review provenance lacks isolation attestation")
    transcript_bytes = transcript_path.read_bytes()
    sessions = provenance.get("review_sessions")
    observed_sessions: set[tuple[str, str, str, str, str, str]] = set()
    ranges: list[tuple[int, int]] = []
    session_fields = {
        "round_id", "generation", "round_sha256", "reviewer_role", "context_id", "execution_id",
        "start_byte", "end_byte", "sha256",
    }
    if not isinstance(sessions, list) or not sessions:
        errors.append("review provenance requires review_sessions")
        sessions = []
    for index, session in enumerate(sessions, start=1):
        if not isinstance(session, dict) or set(session) != session_fields:
            errors.append(f"review provenance session {index} has invalid fields")
            continue
        start, end = session.get("start_byte"), session.get("end_byte")
        if not isinstance(start, int) or not isinstance(end, int) or not (0 <= start < end <= len(transcript_bytes)):
            errors.append(f"review provenance session {index} byte range is invalid")
            continue
        if any(start < prior_end and prior_start < end for prior_start, prior_end in ranges):
            errors.append(f"review provenance session {index} overlaps another transcript segment")
        ranges.append((start, end))
        if hashlib.sha256(transcript_bytes[start:end]).hexdigest() != session.get("sha256"):
            errors.append(f"review provenance session {index} transcript segment hash mismatch")
        observed_sessions.add((
            str(session.get("round_id")), str(session.get("generation")),
            str(session.get("round_sha256")), str(session.get("reviewer_role")),
            str(session.get("context_id")), str(session.get("execution_id")),
        ))
    if review_loop:
        expected_sessions: set[tuple[str, str, str, str, str, str]] = set()
        for round_record in review_loop.get("rounds", []):
            if not isinstance(round_record, dict):
                continue
            if round_record.get("generation") != request.get("generation"):
                continue
            round_id = str(round_record.get("round_id"))
            for panel_review in round_record.get("panel_reviews", []):
                if isinstance(panel_review, dict):
                    expected_sessions.add((
                        round_id, str(round_record.get("generation")),
                        str(round_record.get("round_sha256")), str(panel_review.get("reviewer_role")),
                        str(panel_review.get("reviewer_context_id")),
                        str(panel_review.get("execution_id")),
                    ))
            editor = round_record.get("editor_review")
            if isinstance(editor, dict):
                expected_sessions.add((
                    round_id, str(round_record.get("generation")),
                    str(round_record.get("round_sha256")), "editor_synthesizer", str(editor.get("context_id")),
                    str(editor.get("execution_id")),
                ))
        if observed_sessions != expected_sessions:
            errors.append("review provenance sessions do not match panel and editor executions")
    for field in ("provenance_id", "review_session_id", "reviewer_context_id", "reviewer_identity", "execution_id"):
        if not isinstance(provenance.get(field), str) or not provenance.get(field):
            errors.append(f"review provenance {field} is required")
    if provenance.get("execution_kind") == "external_model":
        for field in ("provider", "model", "runner"):
            if not isinstance(provenance.get(field), str) or not provenance.get(field):
                errors.append(f"external model review requires {field}")
    started = _parse_datetime(provenance.get("started_at"))
    completed = _parse_datetime(provenance.get("completed_at"))
    created = _parse_datetime(request.get("created_at"))
    if not started or not completed or not created or not (created <= started <= completed):
        errors.append("review provenance timestamps are not causal")
    if strict_execution:
        if started and completed and started >= completed:
            errors.append("captured review execution must have a non-zero causal time window")
        errors.extend(
            _execution_transcript_errors(
                transcript_path.read_text(encoding="utf-8"), label="review"
            )
        )
    session_id = str(provenance.get("review_session_id", ""))
    author_id = str(provenance.get("author_context_id", ""))
    for review in reviews:
        if review.get("reviewer_run_id") != session_id:
            errors.append(f"review {review.get('review_id')} is not bound to review session")
        if review.get("author_run_id") != author_id:
            errors.append(f"review {review.get('review_id')} author context mismatch")
        reviewed = _parse_datetime(review.get("reviewed_at"))
        if started and completed and (not reviewed or not (started <= reviewed <= completed)):
            errors.append(f"review {review.get('review_id')} timestamp is outside review session")
    return list(dict.fromkeys(errors))


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
            ("--review-provenance", args.review_provenance),
            ("--review-transcript", args.review_transcript),
        ) if value is None
    ]
    if _is_maximal_full_dossier(brief) and args.review_loop is None:
        missing.append("--review-loop")
    if missing:
        raise CLIContractError("full_dossier review requires " + ", ".join(missing))


REVIEW_SUBJECT_PATHS = {
    "claims": "research/claim-evidence-ledger.jsonl",
    "sources": "research/source-register.jsonl",
    "findings": "research/storm-findings-pool.jsonl",
    "contradictions": "research/contradiction-ledger.json",
    "uncertainties": "research/uncertainty-ledger.json",
    "p2": "research/storm-lens-conflicts.json",
    "p3": "research/storm-lens-outline.json",
    "p4": "research/storm-lens-red-team.json",
    "retrieval_audit": "research/retrieval-audit.jsonl",
    "finding_coverage": "research/finding-coverage.json",
}


def review_subject_artifact_hashes(
    layout: RunLayout,
    generation: int,
    candidate_md: Path,
    candidate_map: Path,
    revision_map: Path,
) -> dict[str, str]:
    paths = {
        "report": candidate_md,
        "paragraph_map": candidate_map,
        "revision_map": revision_map,
        **{
            key: layout.artifact(generation, relative)
            for key, relative in REVIEW_SUBJECT_PATHS.items()
        },
    }
    missing = [key for key, path in paths.items() if not path.is_file() or path.is_symlink()]
    if missing:
        raise ReviewGateError(
            "review subject is missing governed artifacts: " + ", ".join(sorted(missing))
        )
    return {
        key: sha256_file(path) for key, path in sorted(paths.items())
    }


def review_subject_sha256(
    layout: RunLayout,
    generation: int,
    candidate_md: Path,
    candidate_map: Path,
    revision_map: Path,
) -> str:
    return canonical_json_sha256(review_subject_artifact_hashes(
        layout, generation, candidate_md, candidate_map, revision_map
    ))


def _review_round_digest(round_record: dict[str, object]) -> str:
    return canonical_json_sha256({
        key: value for key, value in round_record.items() if key != "round_sha256"
    })


def _review_reason_is_specific(value: object) -> bool:
    text = str(value or "").strip()
    if len(text) < 80:
        return False
    generic = {
        "check source closure", "check evidence strength", "check domain coverage",
        "check strongest counterargument", "re-review accepts the candidate",
    }
    return text.rstrip(".").casefold() not in generic


def _validate_review_loop_contract(
    loop: dict[str, object],
    *,
    final_candidate_sha256: str,
    final_review_subject_sha256: str,
    revision_map_sha256: str,
    material_claim_ids: set[str],
    revision_action_ids: set[str],
    p4_action_ids: set[str],
    required_gap_review_ids: set[str],
    required_gap_review_targets: list[set[str]] | None = None,
    high_stakes: bool,
    author_context_id: str,
    skill_package_sha256: str,
    uncertainty_records: dict[str, dict[str, object]] | None = None,
    report_binding_ids: set[str] | None = None,
    current_generation: int | None = None,
    round_bindings: dict[int, dict[str, str]] | None = None,
    final_review_subject_artifacts: dict[str, str] | None = None,
) -> list[str]:
    fields = {"schema_version", "policy", "rounds", "final_integrity", "summary"}
    errors: list[str] = []
    if set(loop) != fields:
        return ["review-loop.json has invalid fields"]
    if loop.get("schema_version") != "2.0":
        errors.append("review-loop.json schema_version must be 2.0")
    if loop.get("policy") != "concern_driven_until_clear":
        errors.append("review-loop.json policy must be concern_driven_until_clear")
    rounds = loop.get("rounds")
    final_integrity = loop.get("final_integrity")
    summary = loop.get("summary")
    if not isinstance(rounds, list) or not rounds:
        errors.append("maximal_full_dossier requires at least one substantive panel review")
        rounds = []
    if not isinstance(final_integrity, dict):
        errors.append("review-loop.json final_integrity must be an object")
        final_integrity = {}
    if not isinstance(summary, dict):
        errors.append("review-loop.json summary must be an object")
        summary = {}
    if summary.get("round_count") != len(rounds):
        errors.append("review-loop.json summary round_count must match rounds")
    if summary.get("final_editor_decision") != "accept":
        errors.append("maximal_full_dossier review loop final editor decision must be accept")
    if summary.get("unresolved_concerns") != 0:
        errors.append("maximal_full_dossier review loop must have zero unresolved concerns")
    if summary.get("final_candidate_sha256") != final_candidate_sha256:
        errors.append("review-loop.json final candidate hash mismatch")
    if summary.get("final_review_subject_sha256") != final_review_subject_sha256:
        errors.append("review-loop.json final review subject hash mismatch")
    if not isinstance(summary.get("terminal_reason"), str) or not str(summary.get("terminal_reason", "")).strip():
        errors.append("review-loop.json terminal_reason is required")
    required_roles = MAX_REVIEW_ROLES
    opened_concerns: set[str] = set()
    terminal_concerns: set[str] = set()
    terminal_gap_targets: dict[str, str] = {}
    concern_contracts: dict[str, dict[str, object]] = {}
    linked_p4_actions: set[str] = set()
    previous_subject: str | None = None
    previous_storm_analysis_sha256: str | None = None
    previous_generation: int | None = None
    previous_subject_artifacts: dict[str, str] | None = None
    previous_open_concerns: list[dict[str, object]] = []
    for index, round_record in enumerate(rounds, start=1):
        if not isinstance(round_record, dict):
            errors.append(f"review loop round {index} must be an object")
            continue
        round_fields = {
            "round_id", "candidate_sha256", "review_subject_sha256",
            "panel_reviews", "editor_decision", "editor_review",
            "required_concerns", "revision_map_sha256", "re_review_result",
            "unresolved_concerns", "generation", "draft_receipt_sha256",
            "review_request_sha256", "review_subject_artifacts", "round_sha256",
        }
        if set(round_record) != round_fields:
            errors.append(f"review loop round {index} has invalid fields")
            continue
        round_generation = round_record.get("generation")
        if not isinstance(round_generation, int) or round_generation < 1:
            errors.append(f"review loop round {index} generation is invalid")
        elif previous_generation is not None and round_generation <= previous_generation:
            errors.append("review rounds must use distinct increasing generations")
        previous_generation = round_generation if isinstance(round_generation, int) else previous_generation
        if _review_round_digest(round_record) != round_record.get("round_sha256"):
            errors.append(f"review loop round {index} round_sha256 mismatch")
        subject_artifacts = round_record.get("review_subject_artifacts")
        expected_subject_keys = {"report", "paragraph_map", "revision_map", *REVIEW_SUBJECT_PATHS}
        if (
            not isinstance(subject_artifacts, dict)
            or set(subject_artifacts) != expected_subject_keys
            or not all(_is_sha256(value) for value in subject_artifacts.values())
        ):
            errors.append(f"review loop round {index} review_subject_artifacts are invalid")
            subject_artifacts = {}
        elif canonical_json_sha256(subject_artifacts) != round_record.get("review_subject_sha256"):
            errors.append(f"review loop round {index} subject manifest hash mismatch")
        bindings = (round_bindings or {}).get(round_generation, {}) if isinstance(round_generation, int) else {}
        if (
            round_record.get("draft_receipt_sha256") != bindings.get("draft_receipt_sha256")
            or round_record.get("review_request_sha256") != bindings.get("review_request_sha256")
        ):
            errors.append(f"review loop round {index} is not bound to its generation receipts")
        if index < len(rounds) and round_record.get("round_sha256") != bindings.get("blocked_round_sha256"):
            errors.append(f"review loop round {index} lacks an immutable blocked review receipt")
        if previous_subject_artifacts is not None and previous_open_concerns:
            changed = {
                key for key in expected_subject_keys
                if previous_subject_artifacts.get(key) != subject_artifacts.get(key)
            }
            for concern in previous_open_concerns:
                stage = str(concern.get("required_stage", ""))
                required_components = {
                    "retrieval": {"retrieval_audit", "sources", "findings", "finding_coverage"},
                    "evidence": {"claims", "contradictions", "uncertainties", "finding_coverage"},
                    "draft": {"report", "paragraph_map", "revision_map", "p3", "p4"},
                }.get(stage, set())
                if required_components and not changed.intersection(required_components):
                    errors.append(
                        f"review concern {concern.get('concern_id')} did not change its required upstream artifacts"
                    )
        previous_subject_artifacts = dict(subject_artifacts)
        if not _is_sha256(round_record.get("candidate_sha256")):
            errors.append(f"review loop round {index} candidate_sha256 is invalid")
        subject_hash = str(round_record.get("review_subject_sha256", ""))
        if not _is_sha256(subject_hash):
            errors.append(f"review loop round {index} review_subject_sha256 is invalid")
        if previous_subject and round_record.get("required_concerns") and subject_hash == previous_subject:
            errors.append(f"review loop round {index} reused the prior review subject")
        previous_subject = subject_hash
        decision = str(round_record.get("editor_decision"))
        if decision not in {"accept", "minor_revision", "major_revision", "reject"}:
            errors.append(f"review loop round {index} editor_decision is invalid")
        panel = round_record.get("panel_reviews")
        panel_contexts: list[str] = []
        panel_executions: list[str] = []
        if not isinstance(panel, list):
            errors.append(f"review loop round {index} panel_reviews must be an array")
            panel = []
        else:
            roles = {
                str(item.get("reviewer_role"))
                for item in panel
                if isinstance(item, dict)
            }
            missing_roles = sorted(required_roles - roles)
            if missing_roles:
                errors.append(
                    f"review loop round {index} missing reviewer roles: "
                    + ", ".join(missing_roles)
                )
            for panel_review in panel:
                if not isinstance(panel_review, dict):
                    errors.append(f"review loop round {index} panel review must be an object")
                    continue
                panel_fields = {
                    "reviewer_role", "decision", "reason", "rubric_id",
                    "rubric_sha256", "reviewed_subject_sha256",
                    "reviewer_context_id", "execution_id", "concerns", "storm_analysis",
                }
                if set(panel_review) != panel_fields:
                    errors.append(f"review loop round {index} panel review has invalid fields")
                    continue
                role = str(panel_review.get("reviewer_role"))
                if not _review_reason_is_specific(panel_review.get("reason")):
                    errors.append(f"review loop {role} reason is generic or too short")
                expected_rubric_id, expected_rubric_sha256 = max_review_rubric_binding(
                    role, skill_package_sha256
                )
                if not str(panel_review.get("rubric_id", "")).strip() or not _is_sha256(panel_review.get("rubric_sha256")):
                    errors.append(f"review loop {role} rubric binding is invalid")
                elif (
                    panel_review.get("rubric_id") != expected_rubric_id
                    or panel_review.get("rubric_sha256") != expected_rubric_sha256
                ):
                    errors.append(
                        f"review loop {role} rubric hash does not match the committed role rubric"
                    )
                if panel_review.get("reviewed_subject_sha256") != subject_hash:
                    errors.append(f"review loop {role} reviewed the wrong subject")
                context_id = str(panel_review.get("reviewer_context_id", ""))
                execution_id = str(panel_review.get("execution_id", ""))
                if not context_id or context_id == author_context_id:
                    errors.append(f"review loop {role} context is missing or not isolated from author")
                if not execution_id:
                    errors.append(f"review loop {role} execution_id is required")
                panel_contexts.append(context_id)
                panel_executions.append(execution_id)
                if panel_review.get("decision") not in {"accept", "minor_revision", "major_revision", "reject"}:
                    errors.append(f"review loop {role} decision is invalid")
                if not isinstance(panel_review.get("concerns"), list):
                    errors.append(f"review loop {role} concerns must be an array")
                storm_analysis = panel_review.get("storm_analysis")
                if role == "storm_synthesis_reviewer":
                    errors.extend(validate_storm_review_analysis(storm_analysis))
                    if isinstance(storm_analysis, dict):
                        storm_digest = canonical_json_sha256(storm_analysis)
                        if previous_storm_analysis_sha256 == storm_digest:
                            errors.append(
                                "storm_synthesis_reviewer copied the prior round audit instead of re-reviewing the changed subject"
                            )
                        previous_storm_analysis_sha256 = storm_digest
                elif storm_analysis is not None:
                    errors.append(f"review loop {role} must not submit storm_analysis")
            if len(panel_contexts) != len(set(panel_contexts)):
                errors.append("panel reviewer contexts must be distinct")
            if len(panel_executions) != len(set(panel_executions)):
                errors.append("panel reviewer executions must be distinct")
        editor_review = round_record.get("editor_review")
        editor_fields = {"context_id", "execution_id", "decision", "reason", "concern_ids"}
        if not isinstance(editor_review, dict) or set(editor_review) != editor_fields:
            errors.append(f"review loop round {index} editor_review has invalid fields")
            editor_review = {}
        else:
            editor_context = str(editor_review.get("context_id", ""))
            if not editor_context or editor_context == author_context_id or editor_context in set(panel_contexts):
                errors.append(f"review loop round {index} editor context is not isolated")
            if not str(editor_review.get("execution_id", "")).strip():
                errors.append(f"review loop round {index} editor execution_id is required")
            if not _review_reason_is_specific(editor_review.get("reason")):
                errors.append(f"review loop round {index} editor reason is generic or too short")
        concerns = round_record.get("required_concerns")
        if not isinstance(concerns, list):
            errors.append(f"review loop round {index} required_concerns must be an array")
            concerns = []
        concern_ids: set[str] = set()
        for concern in concerns:
            if not isinstance(concern, dict):
                errors.append(f"review loop round {index} concern must be an object")
                continue
            concern_fields = {
                "concern_id", "reviewer_role", "severity", "target_kind", "target_id",
                "target_sha256", "evidence_or_locator", "problem", "required_action",
                "acceptance_test", "origin_action_ids", "issue_type", "required_stage",
                "uncertainty_id", "report_binding", "disposition", "reason",
            }
            if set(concern) != concern_fields:
                errors.append(f"review loop round {index} concern has invalid fields")
                continue
            concern_id = str(concern.get("concern_id", ""))
            concern_ids.add(concern_id)
            current = concern_contracts.setdefault(concern_id, dict(concern))
            for field in ("reviewer_role", "severity", "target_kind", "target_id", "target_sha256", "required_action", "acceptance_test"):
                if current.get(field) != concern.get(field):
                    errors.append(f"review loop concern {concern_id} changed its contract across rounds")
            if not re.fullmatch(r"RC\d{3}", concern_id):
                errors.append(f"review loop concern {concern_id} has invalid ID")
            if concern.get("reviewer_role") not in required_roles:
                errors.append(f"review loop concern {concern_id} has invalid reviewer role")
            if concern.get("severity") not in {"blocker", "major", "minor"}:
                errors.append(f"review loop concern {concern_id} has invalid severity")
            if not _is_sha256(concern.get("target_sha256")):
                errors.append(f"review loop concern {concern_id} target hash is invalid")
            for field in ("target_kind", "target_id", "evidence_or_locator", "problem", "required_action", "acceptance_test"):
                if not str(concern.get(field, "")).strip():
                    errors.append(f"review loop concern {concern_id} requires {field}")
            issue_type = str(concern.get("issue_type", ""))
            required_stage = str(concern.get("required_stage", ""))
            expected_stage = REVIEW_ISSUE_STAGE.get(issue_type)
            if expected_stage is None or required_stage != expected_stage:
                errors.append(
                    f"review loop concern {concern_id} requires issue_type and required_stage with deterministic routing"
                )
            origin_action_ids = concern.get("origin_action_ids")
            if not isinstance(origin_action_ids, list) or not all(
                re.fullmatch(r"RA\d{3}", str(item)) for item in origin_action_ids
            ) or len(origin_action_ids) != len(set(str(item) for item in origin_action_ids)):
                errors.append(f"review loop concern {concern_id} has invalid origin_action_ids")
            else:
                linked_p4_actions.update(str(item) for item in origin_action_ids)
            disposition = concern.get("disposition")
            if disposition == "open":
                opened_concerns.add(concern_id)
            elif disposition in {"addressed", "waived", "preserved_as_uncertainty"}:
                terminal_concerns.add(concern_id)
                if (
                    concern.get("reviewer_role") == "domain_reviewer"
                    and concern.get("target_kind") in {"gap", "gap_assessment"}
                    and str(concern.get("target_id", "")).strip()
                ):
                    terminal_gap_targets[
                        f"{concern.get('target_kind')}:{concern.get('target_id')}"
                    ] = concern_id
                if not str(concern.get("reason", "")).strip():
                    errors.append(f"review loop concern {concern_id} terminal disposition lacks reason")
                if disposition == "waived" and high_stakes and concern.get("severity") in {"blocker", "major"}:
                    errors.append(f"high-stakes concern {concern_id} cannot be waived")
                if disposition == "preserved_as_uncertainty":
                    uncertainty_id = str(concern.get("uncertainty_id") or "")
                    report_binding = str(concern.get("report_binding") or "")
                    uncertainty = (uncertainty_records or {}).get(uncertainty_id)
                    if (
                        not re.fullmatch(r"U\d{3}", uncertainty_id)
                        or uncertainty is None
                        or not report_binding
                        or report_binding not in (report_binding_ids or set())
                        or (
                            concern.get("target_kind") == "claim"
                            and uncertainty.get("claim_id") != concern.get("target_id")
                        )
                    ):
                        errors.append(
                            f"review loop concern {concern_id} preserved uncertainty requires uncertainty_id and report binding"
                        )
                elif concern.get("uncertainty_id") is not None or concern.get("report_binding") is not None:
                    errors.append(
                        f"review loop concern {concern_id} uncertainty fields are only valid for preserved_as_uncertainty"
                    )
            else:
                errors.append(f"review loop concern {concern_id} disposition is invalid")
        panel_concern_ids = {
            str(concern.get("concern_id"))
            for item in panel if isinstance(item, dict)
            for concern in item.get("concerns", []) if isinstance(concern, dict)
        }
        if panel_concern_ids != concern_ids:
            errors.append(f"review loop round {index} editor concern matrix does not match panel concerns")
        open_severities = {
            str(concern.get("severity")) for concern in concerns
            if isinstance(concern, dict) and concern.get("disposition") == "open"
        }
        expected_decision = (
            "reject" if "blocker" in open_severities else
            "major_revision" if "major" in open_severities else
            "minor_revision" if "minor" in open_severities else "accept"
        )
        if decision != expected_decision:
            errors.append(f"review loop round {index} editor decision conflicts with open concerns")
        if editor_review:
            if editor_review.get("decision") != decision:
                errors.append(f"review loop round {index} editor review decision mismatch")
            if set(str(item) for item in editor_review.get("concern_ids", [])) != concern_ids:
                errors.append(f"review loop round {index} editor review omitted panel concerns")
        if index < len(rounds):
            if round_record.get("revision_map_sha256") != revision_map_sha256:
                errors.append(f"review loop round {index} revision_map_sha256 mismatch")
            if round_record.get("re_review_result") not in {"pending", "requires_re_review"}:
                errors.append(f"review loop round {index} re_review_result must require re-review")
            if not concern_ids:
                errors.append(f"review loop round {index} must record the concerns that triggered re-review")
            if round_record.get("unresolved_concerns") != len([
                item for item in concerns if isinstance(item, dict) and item.get("disposition") == "open"
            ]):
                errors.append(f"review loop round {index} unresolved concern count mismatch")
        else:
            if current_generation is not None and round_generation != current_generation:
                errors.append("review loop final round must bind the current generation")
            if (
                final_review_subject_artifacts is not None
                and subject_artifacts != final_review_subject_artifacts
            ):
                errors.append("review loop final round subject artifacts mismatch")
            if round_record.get("candidate_sha256") != final_candidate_sha256:
                errors.append("review loop final round candidate hash mismatch")
            expected_re_review = "pass" if len(rounds) > 1 else "not_required"
            if round_record.get("re_review_result") != expected_re_review:
                errors.append(f"review loop final round re_review_result must be {expected_re_review}")
            if round_record.get("unresolved_concerns") != 0:
                errors.append("review loop final round must have zero unresolved concerns")
        previous_open_concerns = [
            item for item in concerns
            if isinstance(item, dict) and item.get("disposition") == "open"
        ]
    missing_revisions = sorted(opened_concerns - revision_action_ids)
    if missing_revisions:
        errors.append("review concerns are missing from revision map: " + ", ".join(missing_revisions))
    unclosed = sorted(opened_concerns - terminal_concerns)
    if unclosed:
        errors.append("review concerns remain unresolved after re-review: " + ", ".join(unclosed))
    missing_p4_links = sorted(p4_action_ids - linked_p4_actions)
    if missing_p4_links:
        errors.append("P4 repair actions are absent from the review concern matrix: " + ", ".join(missing_p4_links))
    missing_gap_reviews = sorted(required_gap_review_ids - terminal_concerns)
    if missing_gap_reviews:
        errors.append("gap terminal assessments lack closed independent review: " + ", ".join(missing_gap_reviews))
    for target_options in required_gap_review_targets or []:
        if not set(target_options) & set(terminal_gap_targets):
            errors.append(
                "terminal gap disposition requires independent review closure: "
                + " or ".join(sorted(target_options))
            )
    wrong_gap_reviewers = sorted(
        concern_id for concern_id in required_gap_review_ids & terminal_concerns
        if concern_contracts.get(concern_id, {}).get("reviewer_role") != "domain_reviewer"
    )
    if wrong_gap_reviewers:
        errors.append(
            "gap terminal assessments require domain reviewer acceptance: "
            + ", ".join(wrong_gap_reviewers)
        )
    integrity_fields = {
        "review_subject_sha256", "status", "checked_claim_ids", "regression_issues",
    }
    if set(final_integrity) != integrity_fields:
        errors.append("review-loop.json final_integrity has invalid fields")
    else:
        if final_integrity.get("review_subject_sha256") != final_review_subject_sha256:
            errors.append("final integrity reviewed the wrong subject")
        if final_integrity.get("status") != "pass" or final_integrity.get("regression_issues") != []:
            errors.append("final integrity must pass with zero regression issues")
        if set(str(item) for item in final_integrity.get("checked_claim_ids", [])) != material_claim_ids:
            errors.append("final integrity must check every material Claim")
    return list(dict.fromkeys(errors))


def _peer_review_markdown(summary: dict[str, object]) -> str:
    return (
        "# Peer Review\n\n"
        f"- Reviewer: {summary['reviewer_run_id']}\n"
        f"- Claim reviews: {summary['claim_reviews']}\n"
        f"- Paragraph audits: {summary['paragraph_reviews']}\n"
        f"- Fact checks: {summary.get('fact_checks', 0)}\n"
        f"- Conflict reviews: {summary.get('conflict_reviews', 0)}\n"
        f"- Draft audits: {summary.get('draft_audits', 0)}\n"
        f"- P4 repair actions: {summary.get('p4_repair_actions', 0)}\n"
        f"- Review loop policy: {summary.get('review_loop_policy', 'single_pass_external_review')}\n"
        f"- Decision: {summary['decision']}\n"
    )


def _promote_review_artifacts(
    layout: RunLayout,
    generation: int,
    report: str,
    paragraph_map: list[dict[str, object]],
    revision_map: dict[str, object],
    peer_review: dict[str, object],
    provenance: dict[str, object],
    transcript_path: Path,
    review_loop: dict[str, object] | None = None,
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
    if review_loop is not None:
        atomic_write_json(staging / "research/review-loop.json", review_loop)
    atomic_write_json(staging / "research/reviewer-provenance.json", provenance)
    shutil.copyfile(transcript_path, staging / "research/reviewer-transcript.txt")
    atomic_write_text(
        staging / "research/peer-review.md", _peer_review_markdown(peer_review["summary"])
    )
    relative_paths = [
        "report.md", "research/reviewed-paragraph-map.jsonl", "research/revision-map.json",
        "research/peer-review.json", "research/peer-review.md",
        "research/reviewer-provenance.json", "research/reviewer-transcript.txt",
    ]
    if review_loop is not None:
        relative_paths.append("research/review-loop.json")
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
    review_loop = load_json(args.review_loop) if args.review_loop else None
    if args.review_provenance is None or args.review_transcript is None:
        raise CLIContractError("full_dossier review requires --review-provenance and --review-transcript")
    provenance = load_json(args.review_provenance)
    claim_path = layout.artifact(generation, "research/claim-evidence-ledger.jsonl")
    source_path = layout.artifact(generation, "research/source-register.jsonl")
    contradiction_path = layout.artifact(generation, "research/contradiction-ledger.json")
    draft_path = layout.artifact(generation, "drafts/report-v1.md")
    draft_map_path = layout.artifact(generation, "research/paragraph-map.jsonl")
    claims = load_jsonl(claim_path)
    sources = load_jsonl(source_path)
    contradictions = load_json(contradiction_path)
    request_path = layout.artifact(generation, "research/review-request.json")
    if not request_path.is_file() or request_path.is_symlink():
        raise StagePreconditionError("review requires review-prepare and research/review-request.json")
    request = load_json(request_path)
    if request.get("request_sha256") != _review_request_digest(request):
        raise ReviewGateError("review request hash mismatch")
    candidate_paths = {
        "artifacts/review-candidate/report.md": args.revised_md,
        "artifacts/review-candidate/paragraph-map.jsonl": args.revised_paragraph_map_jsonl,
        "artifacts/review-candidate/revision-map.json": args.revision_map,
    }
    expected_candidates = request.get("candidate_artifacts")
    if not isinstance(expected_candidates, dict) or any(
        expected_candidates.get(key) != sha256_file(path)
        for key, path in candidate_paths.items()
    ):
        raise ReviewGateError("review inputs do not match prepared candidate hashes")
    errors = validate_report_traceability(report, paragraph_map, claims, sources)
    errors.extend(_validate_review_set(report, claims, claim_reviews, paragraph_reviews))
    if fact_checks or draft_audits:
        errors.extend(_validate_review_set(report, claims, fact_checks, draft_audits))
    if conflict_reviews:
        errors.extend(_validate_conflict_review_set(contradictions, conflict_reviews))
    p4_path = _storm_lens_artifact_path(layout, generation, "P4")
    p4: dict[str, Any] | None = None
    p4_receipt_inputs: dict[str, str] = {}
    if _storm_lens_mode(brief) == "strict" or p4_path.is_file():
        p4_expected_inputs = _storm_lens_expected_inputs(layout, generation, "P4")
        p4, p4_receipt_inputs = _optional_lens_inputs(
            layout, generation, "P4", p4_expected_inputs,
            required=_storm_lens_mode(brief) == "strict",
        )
        if p4:
            errors.extend(_validate_p4_against_draft(p4, draft_path))
    repairs = list((p4 or {}).get("output", {}).get("repair_actions", []))
    errors.extend(_validate_revision_map(
        revision_map, repairs,
        draft_sha256=sha256_file(draft_path),
        candidate_sha256=sha256_file(args.revised_md),
        review_concerns=_review_concerns_by_id(review_loop),
    ))
    review_output_payload = {
        "claim_reviews": claim_reviews,
        "paragraph_reviews": paragraph_reviews,
        "fact_checks": fact_checks,
        "conflict_reviews": conflict_reviews,
        "draft_audits": draft_audits,
        "review_loop": review_loop or {},
    }
    all_reviews = [*claim_reviews, *paragraph_reviews, *fact_checks, *draft_audits, *conflict_reviews]
    errors.extend(_validate_review_provenance(
        provenance, request, _review_output_digest(review_output_payload),
        args.review_transcript, all_reviews,
        strict_execution=_captured_execution_required(brief),
        review_loop=review_loop,
    ))
    if _is_maximal_full_dossier(brief):
        if review_loop is None:
            errors.append("maximal_full_dossier requires review-loop.json")
        else:
            subject_artifacts = review_subject_artifact_hashes(
                layout, generation, args.revised_md,
                args.revised_paragraph_map_jsonl, args.revision_map,
            )
            subject_hash = canonical_json_sha256(subject_artifacts)
            revision_action_ids = {
                str(item.get("action_id"))
                for item in revision_map.get("revisions", [])
                if isinstance(item, dict)
            }
            terminal_gap_review_ids: set[str] = set()
            terminal_gap_review_targets: list[set[str]] = []
            for item in load_jsonl(layout.artifact(generation, "research/retrieval-audit.jsonl")):
                if item.get("record_kind") != "gap_assessment" or item.get("terminal_state") not in {
                    "saturated", "bounded_corpus_exhausted",
                    "access_limited_uncertainty", "out_of_scope",
                }:
                    continue
                review_concern_id = item.get("review_concern_id")
                if review_concern_id:
                    terminal_gap_review_ids.add(str(review_concern_id))
                else:
                    terminal_gap_review_targets.append({
                        f"gap_assessment:{item.get('assessment_id')}",
                        f"gap:{item.get('gap_id')}",
                    })
            errors.extend(_validate_review_loop_contract(
                review_loop,
                final_candidate_sha256=sha256_file(args.revised_md),
                final_review_subject_sha256=subject_hash,
                revision_map_sha256=sha256_file(args.revision_map),
                material_claim_ids={
                    str(claim.get("claim_id")) for claim in claims
                    if claim.get("material")
                },
                revision_action_ids=revision_action_ids,
                p4_action_ids={str(item.get("action_id")) for item in repairs},
                required_gap_review_ids=terminal_gap_review_ids,
                required_gap_review_targets=terminal_gap_review_targets,
                high_stakes=bool(brief.get("high_stakes")),
                author_context_id=str(request.get("author_context_id", "")),
                skill_package_sha256=package_hash,
                uncertainty_records={
                    str(item.get("uncertainty_id")): item
                    for item in load_json(
                        layout.artifact(generation, "research/uncertainty-ledger.json")
                    ).get("uncertainties", [])
                    if isinstance(item, dict)
                },
                report_binding_ids={
                    *(
                        str(item.get("paragraph_locator"))
                        for item in paragraph_map if isinstance(item, dict)
                    ),
                    *(
                        f"claim:{claim.get('claim_id')}"
                        for claim in claims if isinstance(claim, dict)
                    ),
                },
                current_generation=generation,
                round_bindings=_review_round_bindings(layout, generation),
                final_review_subject_artifacts=subject_artifacts,
            ))
    if errors:
        if _is_maximal_full_dossier(brief) and isinstance(review_loop, dict):
            _persist_review_block(
                layout, generation, review_loop, errors,
                provenance=provenance, request=request,
                review_output_sha256=_review_output_digest(review_output_payload),
                transcript_path=args.review_transcript,
            )
        raise ReviewGateError("; ".join(dict.fromkeys(errors)))
    reviewer_ids = sorted({
        str(review["reviewer_run_id"])
        for review in [*claim_reviews, *paragraph_reviews, *fact_checks, *draft_audits, *conflict_reviews]
    })
    review_loop_policy = (
        "concern_driven_until_clear"
        if brief.get("research_profile") == "maximal_full_dossier"
        else "single_pass_external_review"
    )
    summary = {
        "reviewer_run_id": ", ".join(reviewer_ids),
        "claim_reviews": len(claim_reviews),
        "paragraph_reviews": len(paragraph_reviews),
        "fact_checks": len(fact_checks),
        "conflict_reviews": len(conflict_reviews),
        "draft_audits": len(draft_audits),
        "p4_repair_actions": len(repairs),
        "review_loop_policy": review_loop_policy,
        "decision": "passed",
        "assurance": "captured external review",
        "provenance_id": provenance.get("provenance_id"),
    }
    peer_review = {
        "schema_version": "2.0",
        "summary": summary,
        "claim_reviews": claim_reviews,
        "paragraph_reviews": paragraph_reviews,
        "fact_checks": fact_checks,
        "conflict_reviews": conflict_reviews,
        "draft_audits": draft_audits,
        "reviewer_provenance": provenance,
    }
    outputs = _promote_review_artifacts(
        layout, generation, report, paragraph_map, revision_map, peer_review,
        provenance, args.review_transcript, review_loop,
    )
    review_inputs = {
        "artifacts/drafts/report-v1.md": sha256_file(draft_path),
        "artifacts/research/paragraph-map.jsonl": sha256_file(draft_map_path),
        "artifacts/research/claim-evidence-ledger.jsonl": sha256_file(claim_path),
        "artifacts/research/source-register.jsonl": sha256_file(source_path),
        "artifacts/research/review-request.json": sha256_file(request_path),
        "artifacts/review-candidate/report.md": sha256_file(args.revised_md),
        "artifacts/review-candidate/paragraph-map.jsonl": sha256_file(args.revised_paragraph_map_jsonl),
        "artifacts/review-candidate/revision-map.json": sha256_file(args.revision_map),
    }
    review_inputs.update(p4_receipt_inputs)
    commit_stage_receipt(
        layout,
        generation=generation,
        stage=Stage.REVIEW,
        package_hash=package_hash,
        validator_hash=sha256_file(Path(__file__)),
        input_artifacts=review_inputs,
        output_paths=outputs,
    )
    atomic_write_text(package_child(layout.root, "current/report.md"), report)
    atomic_write_json(package_child(layout.root, "current/research/peer-review.json"), peer_review)
    if review_loop is not None:
        atomic_write_json(package_child(layout.root, "current/research/review-loop.json"), review_loop)
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


def _collect_files(artifacts: Path, *, include_audit: bool) -> list[str]:
    candidates = [
        "report.md",
        "exports/report.html",
        "exports/report.pdf",
        "validation/validation-report.json",
        "validation/validation-report.md",
    ]
    if include_audit:
        candidates.extend([
            "research/research-plan.json",
            "research/source-plan.json",
            "research/storm-tasklets.jsonl",
            "research/retrieval-audit.jsonl",
            "research/retrieval-manifest.jsonl",
            "research/source-register.jsonl",
            "research/storm-findings-pool.jsonl",
            "research/finding-coverage.json",
            "research/claim-evidence-ledger.jsonl",
            "research/contradiction-ledger.json",
            "research/uncertainty-ledger.json",
            "research/report-outline.json",
            "research/peer-review.json",
            "research/review-loop.json",
            "research/execution/retrieval-provenance.json",
            "research/execution/retrieval-transcript.txt",
            "research/execution/draft-provenance.json",
            "research/execution/draft-transcript.txt",
            "research/review-provenance.json",
            "research/review-transcript.txt",
        ])
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
    assurance_level = validation_report.get("assurance_level")
    if assurance_level not in {
        "validated_artifact_contract_only", "validated_captured_host_execution"
    }:
        raise CLIContractError("collect requires an explicit validated assurance level")
    if (
        assurance_level != "validated_captured_host_execution"
        and not args.allow_artifact_contract
    ):
        raise CLIContractError(
            "collect requires validated_captured_host_execution; "
            "use --allow-artifact-contract only for fixtures or harness acceptance"
        )
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
    include_audit = assurance_level == "validated_captured_host_execution"
    for relative in _collect_files(artifacts, include_audit=include_audit):
        source = artifacts / relative
        target_relative = (
            f"audit/{relative}" if include_audit and relative.startswith("research/") else relative
        )
        destination = package_child(target_root, target_relative)
        atomic_copy_file(source, destination)
        copied[target_relative] = sha256_file(destination)
    manifest = {
        "schema_version": "1.0",
        "run_dir": str(layout.root),
        "generation": generation,
        "source_validation_report_sha256": sha256_file(validation_report_path),
        "assurance_level": assurance_level,
        "artifact_contract_override": bool(args.allow_artifact_contract),
        "audit_bundle_included": include_audit,
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
    payload = {
        "schema_version": "2.0",
        "run_dir": str(layout.root),
        **status,
    }
    brief_path = layout.generation_input(generation, "brief.json")
    blockers: set[str] = set()
    required_stages: dict[str, str] = {}
    if brief_path.is_file() and load_json(brief_path).get("research_profile") == "maximal_full_dossier":
        coverage_path = layout.artifact(generation, "research/finding-coverage.json")
        if coverage_path.is_file():
            coverage = load_json(coverage_path)
            blockers.update(
                str(item.get("gap_id"))
                for item in coverage.get("saturation_assessments", [])
                if isinstance(item, dict) and item.get("terminal_state") == "open"
            )
        loop_path = layout.artifact(generation, "research/review-loop.json")
        if loop_path.is_file():
            opened: set[str] = set()
            terminal: set[str] = set()
            for round_record in load_json(loop_path).get("rounds", []):
                if not isinstance(round_record, dict):
                    continue
                for concern in round_record.get("required_concerns", []):
                    if not isinstance(concern, dict):
                        continue
                    concern_id = str(concern.get("concern_id", ""))
                    if concern.get("disposition") == "open":
                        opened.add(concern_id)
                    elif concern.get("disposition") in {"addressed", "waived", "preserved_as_uncertainty"}:
                        terminal.add(concern_id)
            blockers.update(opened - terminal)
        review_block_path = _review_block_path(layout, generation)
        if review_block_path.is_file() and not review_block_path.is_symlink():
            review_block = load_json(review_block_path)
            expected_block_sha = canonical_json_sha256({
                key: value for key, value in review_block.items() if key != "block_sha256"
            })
            if review_block.get("block_sha256") == expected_block_sha:
                blockers.update(str(item) for item in review_block.get("blocking_issue_ids", []))
                required_stages.update({
                    str(key): str(value)
                    for key, value in review_block.get("required_stages", {}).items()
                })
    if blockers and payload.get("state") != "invalid":
        payload["state"] = "blocked_with_unresolved_issues"
        payload["blocking_issue_ids"] = sorted(blockers)
        payload["blocking_required_stages"] = {
            key: required_stages.get(key, "review") for key in sorted(blockers)
        }
    return payload


def _print_json(payload: dict[str, object]) -> None:
    sys.stdout.write(canonical_json_bytes(payload).decode("utf-8"))


def command_status(args: argparse.Namespace) -> int:
    _print_json(_status_payload(args.run_dir))
    return EXIT_OK


def command_explain(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    status = _status_payload(args.run_dir)
    generation = latest_generation(layout)
    failed_stage = status.get("invalid_stage") or status.get("next_stage")
    error = status.get("error") or f"{failed_stage} has not been run"
    if status.get("state") == "blocked_with_unresolved_issues" and status.get("blocking_issue_ids"):
        repair_command = (
            f"storm-research amend {status['run_dir']} --resume-blocked-review "
            "--initiator <reviewer-or-user> --approval-evidence <approval-evidence> "
            '--reason "Resume blocked review cycle"'
        )
    else:
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
        "blocking_issue_ids": status.get("blocking_issue_ids", []),
        "blocking_required_stages": status.get("blocking_required_stages", {}),
        "invalidated_artifacts": status.get("invalidated_artifacts", []),
        "repair_command": repair_command,
        "suggestions": (
            _doctor_suggestions_for_run(layout, generation, failed_stage)
            if generation is not None else _doctor_suggestions(failed_stage)
        ),
    })
    return EXIT_OK


def _doctor_suggestions_for_run(
    layout: RunLayout, generation: int, next_stage: object
) -> list[str]:
    stage = str(next_stage or "")
    brief = verify_current_brief_view(layout, generation)
    if stage == "retrieval" and (
        brief.get("research_profile") == "maximal_full_dossier"
        and brief.get("assurance_target") == "captured_host_execution"
    ):
        return [
            "build typed retrieval JSONL with search_run, candidate, capture, search_wave, and gap_assessment records",
            "do not rely on capture-source/ingest-dir alone for Max captured retrieval",
            "run storm_research.py retrieval-preflight RUN_DIR --input-jsonl retrieval-records.jsonl",
            "run storm_research.py retrieval-prepare RUN_DIR --input-jsonl retrieval-records.jsonl --transcript retrieval-transcript.txt --context-id ... --provider ... --model ... --runner ... --execution-id ... --started-at ... --completed-at ... --to retrieval-execution.json",
            "run storm_research.py ingest RUN_DIR --input-jsonl retrieval-records.jsonl --execution-provenance retrieval-execution.json --execution-transcript retrieval-transcript.txt",
        ]
    return _doctor_suggestions(next_stage)


def _doctor_suggestions(next_stage: object) -> list[str]:
    stage = str(next_stage or "")
    suggestions = {
        "retrieval": [
            "use capture-source or ingest-dir to build retrieval-inputs.jsonl",
            "run storm_research.py ingest RUN_DIR --input-jsonl retrieval-inputs.jsonl",
        ],
        "evidence": [
            "run findings before evidence for full dossiers",
            "use evidence --preflight-theory before committing Claims",
        ],
        "draft": [
            "use build-paragraph-map to generate paragraph-map.jsonl",
            "run draft --preflight before committing the draft receipt",
        ],
        "review": [
            "provide independent claim reviews, paragraph audit, fact checks, conflict reviews, and draft audit for full dossiers",
        ],
        "render": [
            "render only after review passes; full dossiers cannot downgrade to reduced output",
        ],
        "validation": [
            "run validate and repair failed checks with repair-plan",
        ],
    }
    return suggestions.get(stage, ["run status or explain to inspect the receipt chain"])


def _artifact_status(layout: RunLayout, generation: int) -> list[dict[str, object]]:
    required = [
        "inputs/brief.json",
        "artifacts/research/research-plan.json",
        "artifacts/research/source-plan.json",
        "artifacts/research/storm-tasklets.jsonl",
        "artifacts/research/source-register.jsonl",
        "artifacts/research/retrieval-manifest.jsonl",
        "artifacts/research/storm-findings-pool.jsonl",
        "artifacts/research/claim-evidence-ledger.jsonl",
        "artifacts/drafts/report-v1.md",
        "artifacts/report.md",
        "artifacts/exports/report.html",
        "artifacts/exports/report.pdf",
        "artifacts/validation/validation-report.json",
    ]
    root = layout.generation_root(generation)
    rows: list[dict[str, object]] = []
    for logical in required:
        path = package_child(root, logical)
        rows.append({
            "path": logical,
            "exists": path.is_file() and not path.is_symlink(),
            "unsafe_symlink": path.is_symlink(),
        })
    return rows


def command_doctor(args: argparse.Namespace) -> int:
    layout = RunLayout(args.run_dir)
    status = _status_payload(layout.root)
    generation = latest_generation(layout)
    checks: list[dict[str, object]] = []
    validation_exit_code = None
    validation_error = None
    if generation is not None:
        package_hash = compute_skill_package_hash(ROOT)
        try:
            raw_checks, validation_exit_code = validate_governed_run(layout, generation, package_hash)
            checks = [
                {
                    "check_id": getattr(check, "check_id", ""),
                    "status": getattr(check, "status", ""),
                    "message": getattr(check, "message", ""),
                    "path": getattr(check, "path", ""),
                    "repair_command": getattr(check, "repair_command", ""),
                }
                for check in raw_checks if getattr(check, "status", "") != "pass"
            ]
        except (ReceiptError, ContractError, OutputPathError, OSError, ValueError) as exc:
            validation_exit_code = EXIT_STAGE
            validation_error = str(exc)
    next_stage = status.get("invalid_stage") or status.get("next_stage")
    _print_json({
        "schema_version": "2.0",
        "mode": "doctor",
        "run_dir": str(layout.root),
        "generation": generation,
        "status": status,
        "artifact_status": _artifact_status(layout, generation) if generation else [],
        "validation_exit_code": validation_exit_code,
        "validation_error": validation_error,
        "failed_checks": checks,
        "suggested_next_actions": (
            _doctor_suggestions_for_run(layout, generation, next_stage)
            if generation is not None else _doctor_suggestions(next_stage)
        ),
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
    brief = load_json(layout.generation_input(generation, "brief.json"))
    new_brief = dict(brief)
    changes: list[dict[str, object]] = []
    invalidation_start_stage = Stage.PLAN.value
    if args.resume_blocked_review:
        block_path = _review_block_path(layout, generation)
        if not block_path.is_file() or block_path.is_symlink():
            raise StagePreconditionError("run has no immutable blocked review to resume")
        block = load_json(block_path)
        expected_block_sha = canonical_json_sha256({
            key: value for key, value in block.items() if key != "block_sha256"
        })
        if block.get("block_sha256") != expected_block_sha:
            raise StagePreconditionError("blocked review digest does not recompute")
        stage_rank = {stage.value: index for index, stage in enumerate(Stage)}
        routed = [
            str(value) for value in block.get("required_stages", {}).values()
            if str(value) in stage_rank
        ]
        invalidation_start_stage = min(
            routed or [Stage.REVIEW.value], key=lambda value: stage_rank[value]
        )
        changes.append({
            "field": "review_cycle",
            "before": block["block_sha256"],
            "after": f"generation:{generation + 1}",
            "reason": args.reason,
        })
    else:
        changes_payload = load_json(args.changes_json)
        if not changes_payload:
            raise CLIContractError("amendment changes must be a non-empty object")
        unknown = sorted(set(changes_payload) - set(brief))
        if unknown:
            raise CLIContractError("amendment references unknown brief fields: " + ", ".join(unknown))
        if (
            brief.get("depth_level") == "full_dossier"
            and brief.get("output_mode") == "full"
            and changes_payload.get("output_mode") == "reduced"
        ):
            raise StagePreconditionError("full dossier cannot be amended to reduced output")
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
        "invalidation_start_stage": invalidation_start_stage,
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
    init.add_argument("--research-profile", choices=tuple(sorted(INIT_RESEARCH_PROFILES)), default="auto")
    init.add_argument("--profile-selection-mode", choices=tuple(sorted(PROFILE_SELECTION_MODES)))
    init.add_argument("--profile-selection-evidence", default="")
    init.add_argument("--profile-selection-evidence-file", type=Path)
    init.add_argument("--profile-prompt-file", type=Path)
    init.add_argument("--assurance-target", choices=tuple(sorted(ASSURANCE_TARGETS)))
    init.add_argument("--run-intent", choices=tuple(sorted(RUN_INTENTS)), default="user_delivery")
    init.add_argument("--depth-level", choices=("briefing", "standard_report", "full_dossier"))
    init.add_argument("--briefing-reason", default="")
    init.add_argument("--min-units", type=int)
    init.add_argument("--max-units", type=int)
    init.add_argument("--user-goal", default="Build an evidence-grounded answer")
    init.add_argument("--audience", default="General reader")
    init.add_argument("--geography", default="global")
    init.add_argument("--timeframe", default="current")
    init.add_argument("--source-policy", choices=("external_allowed", "closed_corpus", "primary_only"))
    init.add_argument("--as-of")
    init.add_argument("--max-age-days", type=int, default=365)
    init.add_argument("--retrieval-mode", choices=("host", "provider", "closed_corpus"))
    init.add_argument("--output-mode", choices=("full", "reduced"))
    init.add_argument("--storm-lens-mode", choices=("advisory", "strict"))
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

    lens_perspectives = subparsers.add_parser("lens-perspectives", help="Register Prompt 1 perspective artifact before plan.")
    lens_perspectives.add_argument("run_dir", type=Path)
    lens_perspectives.add_argument("--input-json", type=Path, required=True)
    lens_perspectives.set_defaults(handler=command_lens_perspectives)

    capture = subparsers.add_parser("capture-source", help="Copy and preflight one source snapshot into retrieval input JSONL.")
    capture.add_argument("run_dir", type=Path)
    capture.add_argument("--query-id", required=True)
    capture.add_argument("--url")
    capture.add_argument("--file-ref")
    capture.add_argument("--snapshot", type=Path, required=True)
    capture.add_argument("--title", required=True)
    capture.add_argument("--publisher", required=True)
    capture.add_argument("--published-at")
    capture.add_argument("--publication-date-status", choices=("known", "unknown"))
    capture.add_argument("--retrieved-at")
    capture.add_argument("--content-excerpt")
    capture.add_argument("--content-locator")
    capture.add_argument("--locator-type")
    capture.add_argument("--adapter", choices=("host", "provider", "closed_corpus"))
    capture.add_argument("--adapter-run-id")
    capture.add_argument(
        "--capture-level",
        choices=("full_text", "abstract", "metadata", "official_data", "user_file", "search_snippet"),
    )
    capture.add_argument("--evidence-strength-ceiling", choices=("strong", "medium", "weak", "background"))
    capture.add_argument("--observed-status", type=int)
    capture.add_argument("--content-type")
    capture.add_argument("--source-type")
    capture.add_argument("--primary-class", choices=("primary", "secondary"))
    capture.add_argument("--reliability-tier", choices=("A", "B", "C", "D"))
    capture.add_argument("--freshness-status", choices=("current", "stale", "historical", "unknown"))
    capture.add_argument("--reliability-notes")
    capture.add_argument("--to", type=Path)
    capture.add_argument("--append", action="store_true")
    capture.add_argument("--allow-warning", action="store_true")
    capture.set_defaults(handler=command_capture_source)

    ingest_dir = subparsers.add_parser("ingest-dir", help="Build retrieval input JSONL from a directory manifest.")
    ingest_dir.add_argument("run_dir", type=Path)
    ingest_dir.add_argument("--input-dir", type=Path, required=True)
    ingest_dir.add_argument("--manifest-jsonl", type=Path)
    ingest_dir.add_argument("--to", type=Path)
    ingest_dir.add_argument("--append", action="store_true")
    ingest_dir.add_argument("--allow-warning", action="store_true")
    ingest_dir.set_defaults(handler=command_ingest_dir)

    preflight = subparsers.add_parser("retrieval-preflight", help="Validate retrieval JSONL without writing receipts.")
    preflight.add_argument("run_dir", type=Path)
    preflight.add_argument("--input-jsonl", type=Path, required=True)
    preflight.set_defaults(handler=command_retrieval_preflight)

    prepare = subparsers.add_parser("retrieval-prepare", help="Write captured-host retrieval provenance for a preflighted JSONL.")
    prepare.add_argument("run_dir", type=Path)
    prepare.add_argument("--input-jsonl", type=Path, required=True)
    prepare.add_argument("--transcript", type=Path, required=True)
    prepare.add_argument("--context-id", required=True)
    prepare.add_argument("--provider", required=True)
    prepare.add_argument("--model", required=True)
    prepare.add_argument("--runner", required=True)
    prepare.add_argument("--execution-id", required=True)
    prepare.add_argument("--started-at", required=True)
    prepare.add_argument("--completed-at", required=True)
    prepare.add_argument("--to", type=Path, required=True)
    prepare.set_defaults(handler=command_retrieval_prepare)

    ingest = subparsers.add_parser("ingest", help="Validate and commit captured retrieval evidence.")
    ingest.add_argument("run_dir", type=Path)
    ingest.add_argument("--input-jsonl", type=Path, required=True)
    ingest.add_argument("--execution-provenance", type=Path)
    ingest.add_argument("--execution-transcript", type=Path)
    ingest.add_argument("--allow-diagnostic-debt", action="store_true")
    ingest.set_defaults(handler=command_ingest)

    findings = subparsers.add_parser("findings", help="Validate and register STORM finding pool before evidence.")
    findings.add_argument("run_dir", type=Path)
    findings.add_argument("--findings-jsonl", type=Path, required=True)
    findings.set_defaults(handler=command_findings)

    lens_conflicts = subparsers.add_parser("lens-conflicts", help="Register Prompt 2 conflict artifact after findings.")
    lens_conflicts.add_argument("run_dir", type=Path)
    lens_conflicts.add_argument("--input-json", type=Path, required=True)
    lens_conflicts.set_defaults(handler=command_lens_conflicts)

    lens_outline = subparsers.add_parser("lens-outline", help="Register Prompt 3 outline artifact after conflicts.")
    lens_outline.add_argument("run_dir", type=Path)
    lens_outline.add_argument("--input-json", type=Path, required=True)
    lens_outline.set_defaults(handler=command_lens_outline)

    evidence = subparsers.add_parser("evidence", help="Validate and commit Claims and report outline.")
    evidence.add_argument("run_dir", type=Path)
    evidence.add_argument("--claims", type=Path, required=True)
    evidence.add_argument("--contradictions", type=Path)
    evidence.add_argument("--uncertainties", type=Path)
    evidence.add_argument("--report-outline", type=Path)
    evidence.add_argument("--absence-searches", type=Path)
    evidence.add_argument("--preflight-theory", action="store_true")
    evidence.set_defaults(handler=command_evidence)

    paragraph_map = subparsers.add_parser("build-paragraph-map", help="Generate paragraph-map.jsonl from storm-map directives or sidecar JSONL.")
    paragraph_map.add_argument("run_dir", type=Path)
    paragraph_map.add_argument("--draft-md", type=Path, required=True)
    paragraph_map.add_argument("--sidecar-jsonl", type=Path)
    paragraph_map.add_argument("--to", type=Path)
    paragraph_map.set_defaults(handler=command_build_paragraph_map)

    draft = subparsers.add_parser("draft", help="Validate and commit a traceable report draft.")
    draft.add_argument("run_dir", type=Path)
    draft.add_argument("--draft-md", type=Path, required=True)
    draft.add_argument("--paragraph-map-jsonl", type=Path, required=True)
    draft.add_argument("--execution-provenance", type=Path)
    draft.add_argument("--execution-transcript", type=Path)
    draft.add_argument("--preflight", action="store_true")
    draft.set_defaults(handler=command_draft)

    review_prepare = subparsers.add_parser("review-prepare", help="Freeze a candidate and create an external review handoff.")
    review_prepare.add_argument("run_dir", type=Path)
    review_prepare.add_argument("--candidate-md", type=Path, required=True)
    review_prepare.add_argument("--candidate-map", type=Path, required=True)
    review_prepare.add_argument("--revision-map", type=Path, required=True)
    review_prepare.add_argument("--author-context-id", required=True)
    review_prepare.set_defaults(handler=command_review_prepare)

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
    review.add_argument("--review-provenance", type=Path)
    review.add_argument("--review-transcript", type=Path)
    review.add_argument("--review-loop", type=Path)
    review.set_defaults(handler=command_review)

    lens_review = subparsers.add_parser("lens-review", help="Register Prompt 4 red-team artifact after draft.")
    lens_review.add_argument("run_dir", type=Path)
    lens_review.add_argument("--input-json", type=Path, required=True)
    lens_review.set_defaults(handler=command_lens_review)

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
    collect.add_argument("--allow-artifact-contract", action="store_true")
    collect.set_defaults(handler=command_collect)

    release = subparsers.add_parser("release", help="Build a Trust-approved public release package.")
    release.add_argument("run_dir", type=Path)
    release.add_argument("--trust", type=Path)
    release.add_argument("--registry", type=Path)
    release.add_argument("--approval", type=Path)
    release.add_argument("--reverification", type=Path)
    release.set_defaults(handler=command_release)

    amend = subparsers.add_parser("amend", help="Create a new generation from an approved brief or blocked-review amendment.")
    amend.add_argument("run_dir", type=Path)
    amend_mode = amend.add_mutually_exclusive_group(required=True)
    amend_mode.add_argument("--changes-json", type=Path)
    amend_mode.add_argument("--resume-blocked-review", action="store_true")
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

    doctor = subparsers.add_parser("doctor", help="Summarize run health, failed checks, artifacts, and next actions.")
    doctor.add_argument("run_dir", type=Path)
    doctor.set_defaults(handler=command_doctor)

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
