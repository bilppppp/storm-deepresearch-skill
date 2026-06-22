# Reference Scan

Skill: `storm-deepresearch-skill`

## Why This Step Exists

Use a short benchmark pass before authoring the package in depth. External benchmark objects should define the pattern ceiling. Local files are used afterward only to calibrate fit, privacy, naming, and compatibility.

## Current Skill Anchor

- Title: `STORM DeepResearch`
- Description: Use for source-grounded deep research that needs multi-perspective question generation, claim-evidence traceability, contradiction and uncertainty handling, and validated Markdown, HTML, and PDF deliverables. Trigger for research reports, literature or industry reviews, decision briefs, and supplied document or URL corpora where factual reliability matters. Do not use for quick lookup, unsupported expert role-play, simple summarization, or short-answer tasks.

## Scan Focus

- **Evaluation pattern**: This skill already carries eval assets, so benchmark how top examples define trigger boundaries and quality gates.
- **Execution pattern**: There is deterministic logic in scripts, so compare how strong references separate prose from executable steps.
- **Portability pattern**: The package carries neutral metadata, so scan how good references preserve semantics across targets without forking source.
- **Method pattern**: Use the core job description as the anchor for comparison: Use for source-grounded deep research that needs multi-perspective question generation, claim-evidence traceability, contradiction and uncertainty handling, and validated Markdown, HTML, and PDF deliverables. Trigger for research reports, literature or industry reviews, decision briefs, and supplied document or URL corpora where factual reliability matters. Do not use for quick lookup, unsupported expert role-play, simple summarization, or short-answer tasks.

## Priority Rule

- External benchmark objects set the pattern ceiling. User references refine taste and standards. Local files only calibrate fit, risk, and compatibility.

## External Benchmark Objects

- No explicit external benchmark objects recorded yet.
- Recommended: capture 2 to 5 external references at most.
- Suggested mix: one method reference, one structure reference, one execution or portability reference.

## User-Supplied References

- No user-supplied references recorded yet.
- Ask whether the user has a repo, product, page, workflow, or prompt example worth learning from.
- Treat these as pattern references only, not as text to be copied.

## Local Fit Check

- No local constraints recorded yet.
- Use this section for naming collisions, private dependencies, compatibility limits, or existing library conventions.

## Borrow Plan

- External benchmark first: let high-quality public references define the upper bound for method, structure, execution, or portability.
- User references second: use them to understand taste, standards, and directional preferences without copying source phrasing.
- Local fit third: use local assets only to detect naming conflicts, private dependencies, or compatibility constraints.
- Borrow patterns, not prose: extract loops, boundaries, metadata, and operator flow without copying source-specific language.
- Keep the package light: reject any borrowed pattern that increases context cost faster than it increases reliability.

## Non-Goals

- Do not copy source prose or branding into the new skill.
- Do not import gates that cost more context than they save.
- Do not use benchmark scanning to justify scope creep.
- Do not let local historical habits outrank stronger public benchmarks.
