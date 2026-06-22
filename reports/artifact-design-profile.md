# Artifact Design Profile

Skill: `storm-deepresearch-skill`
Design system: `metric editorial`

## Primary Artifact Direction

**Report or brief**

High-trust editorial report with a clear first-screen thesis, compact evidence blocks, and decisions separated from supporting detail.

## Matched Artifact Families

### Report or brief
- Matched keywords: report, brief, memo
- Score: `3`
- Direction: High-trust editorial report with a clear first-screen thesis, compact evidence blocks, and decisions separated from supporting detail.

### Review viewer
- Matched keywords: review, audit
- Score: `2`
- Direction: Side-by-side reviewer studio with explicit tradeoffs, evidence readiness, and fast paths for approving, blocking, or requesting one focused fix.

### Dashboard or metrics page
- Matched keywords: metric, table
- Score: `2`
- Direction: Metric-first dashboard with stable dimensions, short labels, visible deltas, and narrative callouts only where they change interpretation.

### Code, CLI, or implementation guide
- Matched keywords: script
- Score: `1`
- Direction: Execution-focused technical artifact with environment assumptions, copyable commands, expected outputs, and side effects made explicit.

## Layout Patterns To Prefer

- thesis
- evidence blocks
- decision table
- risks
- next actions
- summary
- variant comparison
- evidence

## Design Tokens

### Type
- Use a distinctive display face or serif for major claims when the artifact is editorial.
- Use a restrained sans for dense body text and technical details.
- Use mono only for metadata, paths, commands, labels, and evidence tags.

### Color
- Choose colors from the artifact's domain, brand, or evidence mood.
- Do not default to Kami parchment, purple gradients, or generic SaaS blue unless the content justifies it.
- Keep accent color limited to decisions, active states, risk, or section anchors.

### Spacing
- Prefer clear grid rhythm over floating decorative cards.
- Increase whitespace around decisions and shrink whitespace around supporting metadata.
- Split dense content instead of shrinking type or adding scroll traps.

### Components
- Use cards for grouped evidence, tables for comparisons, callouts for decisions, and timelines for sequence.
- Avoid cards inside cards.
- Keep reviewer-only detail visible but visually quieter than user-facing guidance.

## Quality Gates

- Keep the first screen useful without requiring the reader to parse every detail.
- Use tables only for comparisons; move explanations below the table.
- Keep source notes readable without flooding the body with markers.
- Make differences visible instead of hiding them in prose.
- Separate author-facing recommendations from reviewer-only evidence.
- Surface conflicts clearly and keep routine benchmark synthesis quiet.
- Avoid paragraph-heavy table cells.
- Keep charts tied to one analytical question each.

## Anti-Patterns

- Do not copy Kami's fixed parchment background as a default.
- Do not use generic purple gradients, glass cards, or stock SaaS hero sections unless the content calls for them.
- Do not let Markdown tables become the default shape for every comparison or explanation.
- Do not turn reviewer evidence into user-facing clutter.
- Do not invent screenshots, citations, charts, or UI states.

## Reviewer Note

Use this profile to judge whether the generated artifacts feel designed for their job, not merely rendered.
