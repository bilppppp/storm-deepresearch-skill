# Reference Synthesis

Skill: `storm-deepresearch-skill`
- Description: Use for source-grounded deep research that needs multi-perspective question generation, claim-evidence traceability, contradiction and uncertainty handling, and validated Markdown, HTML, and PDF deliverables. Trigger for research reports, literature or industry reviews, decision briefs, and supplied document or URL corpora where factual reliability matters. Do not use for quick lookup, unsupported expert role-play, simple summarization, or short-answer tasks.
- Intent confidence: `100/100` (`high`)

## Live GitHub Benchmarks

- No live GitHub benchmarks are attached yet.

## Curated World-Class Pattern Tracks

### Official workflow product ergonomics
- Type: `official`
- Evidence mode: `curated-pattern-track`
- Why relevant: This track matches: review.
- Borrow: Borrow a first-time operator flow that explains itself before it asks for more structure.
- Avoid: Do not mimic product polish that adds UI bulk without improving clarity.

### Human-in-the-loop verification
- Type: `research`
- Evidence mode: `curated-pattern-track`
- Why relevant: This track matches: review, audit.
- Borrow: Borrow a review checkpoint wherever trust matters more than raw speed.
- Avoid: Do not force every skill through heavyweight review when the risk is low.

### Outcome-backwards design
- Type: `principles`
- Evidence mode: `curated-pattern-track`
- Why relevant: This track matches: output, deliverable.
- Borrow: Borrow the habit of designing from the required hand-back output backwards.
- Avoid: Do not start with architecture terms before the deliverable is concrete.

## Borrow Now

- Borrow a first-time operator flow that explains itself before it asks for more structure.
- Borrow a review checkpoint wherever trust matters more than raw speed.
- Borrow the habit of designing from the required hand-back output backwards.

## Avoid Now

- Do not mimic product polish that adds UI bulk without improving clarity.
- Do not force every skill through heavyweight review when the risk is low.
- Do not start with architecture terms before the deliverable is concrete.

## Pattern Gate

- Summary: 3 accepted, 0 deferred using threshold 4/4.
- Acceptance threshold: `4/4`
- Accepted patterns:
  - **Official workflow product ergonomics**: 4/4 (recurrence, generativity, distinctiveness, boundary)
  - **Human-in-the-loop verification**: 4/4 (recurrence, generativity, distinctiveness, boundary)
  - **Outcome-backwards design**: 4/4 (recurrence, generativity, distinctiveness, boundary)

## Default Recommendation

- Summary: Start by borrowing this pattern: Borrow a first-time operator flow that explains itself before it asks for more structure. Avoid this for the first pass: Do not mimic product polish that adds UI bulk without improving clarity.
- Why: There is a real design conflict to resolve: The stated preference leans lightweight or speed-first, while the benchmark mix leans toward governance, review, or heavier evaluation structure.
- User decision required: `True`

## Visibility Mode

- Mode: `explicit`
- Reasons: design_conflict
- User note: Surface the recommendation because intent is still settling or there is a real design conflict that needs a user call.
- Reviewer note: Keep the full benchmark and synthesis evidence visible for authors and reviewers.

## Conflict Check

- **lightweight_vs_governance**: The stated preference leans lightweight or speed-first, while the benchmark mix leans toward governance, review, or heavier evaluation structure.

## Quality Lift Thesis

- Use GitHub repositories for concrete package and workflow patterns.
- Use curated official or commercial tracks for entrypoint and operator ergonomics.
- Use research tracks to justify the smallest evaluation loop that still catches regressions.
- Use principle tracks to keep the package small, boundary-aware, and outcome-driven.

## Decision Prompt

Use the recommendation by default. Only surface the underlying benchmark tradeoffs when intent is uncertain or a real design conflict needs a deliberate call.
