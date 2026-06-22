# Prompt Quality Profile

Skill: `storm-deepresearch-skill`
Relevance: `prompt-heavy`
Overall quality score: `89.0/100`

## Primary Task Family

**Prompt engineering**
- Matched keywords: prompt, role, format

## Complexity

- Band: `expert`
- Score: `25`
- Reason: multiple task families plus governance, evaluation, or expert-level constraints

## Need Model

- Explicit Need: Turn a research topic or supplied corpus into a source-grounded, auditable deep-research package instead of a four-prompt role-play transcript.
- Implicit Need: The reusable skill needs a stable role, task, and output contract rather than a one-off prompt.
- Scenario: A research topic or decision question, User-supplied articles, papers, URLs, notes, or a closed corpus, Audience, geography, timeframe, freshness, and output constraints
- User Level: infer from examples and standards; ask only if it changes output depth
- Success Standard: 100 percent material fact evidence closure, Explicit fact, inference, recommendation, contradiction, and uncertainty labeling, One canonical Markdown source with cross-format consistency, Adversarial evaluation, baseline comparison, trust checks, and install simulation

## RTF To Skill Mapping

- Role: Use a prompt engineer role only when role design materially improves execution.
- Task: Map Role, Task, and Format into skill behavior rather than copying a large prompt template.
- Format: Return a compact prompt contract plus tests, quality matrix, and usage notes.

## Quality Matrix

### Completeness — 95/100
- Matched signals: output, constraint
- Repair: Name missing inputs, outputs, constraints, or success standards before deepening the package.

### Clarity — 80/100
- Matched signals: none
- Repair: Replace broad verbs with observable actions and define what done means.

### Consistency — 85/100
- Matched signals: consistent
- Repair: Check that role, task, format, exclusions, and examples do not contradict each other.

### Practicality — 95/100
- Matched signals: action, use, workflow
- Repair: Add runnable steps, examples, or verification cues instead of abstract advice.

### Specificity — 90/100
- Matched signals: audience, domain
- Repair: Anchor wording in the user's audience, domain nouns, and target outcome.

## Matched Task Families

### Prompt engineering
- Score: `3`
- Keywords: prompt, role, format
- Role: Use a prompt engineer role only when role design materially improves execution.
- Task: Map Role, Task, and Format into skill behavior rather than copying a large prompt template.
- Format: Return a compact prompt contract plus tests, quality matrix, and usage notes.

### Analytical reasoning
- Score: `1`
- Keywords: decision
- Role: Use an analyst role that separates evidence, inference, uncertainty, and recommendation.
- Task: State assumptions, compare alternatives, and make the decision path inspectable.
- Format: Return findings, evidence, tradeoffs, recommendation, and residual risks.

### Execution operation
- Score: `1`
- Keywords: workflow
- Role: Use an operator role with explicit boundaries, inputs, outputs, and failure handling.
- Task: Convert the job into ordered steps with validation checks and stop conditions.
- Format: Return a runbook-like handoff with commands, checks, owners, and next actions when relevant.

### Dialogue interaction
- Score: `1`
- Keywords: support
- Role: Use a conversational role that asks only high-leverage questions and remembers the user's goal.
- Task: Clarify intent, resolve uncertainty, and converge toward a recommendation instead of a long option list.
- Format: Return concise prompts, decision points, and reviewer-visible assumptions.

## Self-Repair Checks

- Check explicit need, implicit need, scenario, user level, and success standard before deepening.
- Map Role, Task, and Format into skill behavior, not decorative prompt labels.
- Ask one focused clarification only when missing information changes the package boundary.
- Add tests or examples for prompt-heavy behavior before treating it as reusable.
- Keep prompt methodology in references and reports instead of bloating SKILL.md.

## Reviewer Note

Use this profile when the package depends on prompt behavior, role design, output contracts, or conversation quality.
