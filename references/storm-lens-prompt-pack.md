# STORM Lens Prompt Pack

Use these prompts to preserve the original STORM-style exploration inside the governed harness. They are not evidence. They generate questions, tensions, synthesis plans, and review actions that must be converted into tasklets, findings, Claims, and receipts.

## Operating Rule

Never run all four prompts before retrieval. Use each prompt at its proper phase:

1. Prompt 1 runs before retrieval to create perspective questions.
2. Retrieval and `findings` answer those questions with sources.
3. Prompt 2 runs after first findings to map evidence-backed conflicts, consensus candidates, and blind spots.
4. Prompt 3 runs after conflicts and findings to build `research-plan.report_outline`.
5. Prompt 4 runs after a draft to red-team the report and route repairs back to retrieval, evidence, outline, or draft.

In `storm_lens_mode=strict`, each prompt must also produce a `schemas/storm-lens-artifact.schema.json` artifact and register it through the matching helper command:

- P1: `storm_research.py lens-perspectives RUN_DIR --input-json storm-lens-perspectives.json`
- P2: `storm_research.py lens-conflicts RUN_DIR --input-json storm-lens-conflicts.json`
- P3: `storm_research.py lens-outline RUN_DIR --input-json storm-lens-outline.json`
- P4: `storm_research.py lens-review RUN_DIR --input-json storm-lens-red-team.json`

The helper artifacts are not final research evidence. They prove phase order and bind prompt outputs to later receipts.

## Prompt 1 — Perspective Discovery

Run before search. Output perspective briefs, research questions, evidence needs, likely sources, and blind spots. Do not answer factual questions from memory.

```text
You are building a STORM-style research plan for:

Topic:
{topic}

User angle or thesis:
{user_goal}

Generate domain-adapted perspectives. Use the default lenses below unless another lens is clearly better for the topic. For each lens, produce:

1. The lens's core concern.
2. Two or more concrete research questions.
3. What evidence would answer each question.
4. Search queries or source classes to pursue.
5. What this lens might miss.

Do not provide final answers. Do not cite model memory. These perspectives create tasklets; sources answer them.
```

Default lens cards:

```text
Practitioner:
What would happen when someone tries to use this in the real world?
Where does the workflow, institution, market, or tool break under operational pressure?

Academic / Scientist:
What concepts need sharper definitions?
What would count as valid evidence, and what methods or measurements are weak?

Skeptic / Critic:
What claim sounds plausible but may be wrong?
What evidence would falsify the main story?
Where might the user, source, or field be overclaiming?

Economist / Incentive Analyst:
Who benefits if this story is accepted?
Who pays the cost?
Which incentives could distort the evidence, narrative, or adoption path?

Historian / Comparativist:
You have seen similar patterns before.
Where has this happened in another era, institution, market, technology, or cultural moment?
What did people misunderstand at the time?
Which analogy is useful, and which analogy is tempting but misleading?
```

Output target:

```text
research-plan.questions[]
source-plan.questions[]
storm-tasklets.jsonl
```

## Prompt 2 — Evidence-Grounded Contradiction Map

Run after first retrieval and findings. Do not compare imagined perspectives; compare evidence-backed findings and candidate Claims.

```text
Using only the findings, sources, and candidate Claims already registered:

1. Where do two or more perspectives directly contradict each other?
   List each conflict with the specific evidence-backed claims that clash.

2. Which perspective currently has the strongest evidence?
   Which has the weakest? Explain using source quality, directness, freshness, and locator strength.

3. What is the one question that, if answered, would resolve the biggest contradiction?
   Convert it into a new retrieval tasklet if it matters to the report.

4. What does every perspective appear to agree on?
   Treat this as a consensus candidate, not truth. It still needs Claim-Evidence closure.

5. What topic did none of the perspectives address?
   Treat this as a blind spot. If the blind spot could change the conclusion, create a new perspective or tasklet.

For every blind spot and resolver question, emit one `resolution_action` with the original text, a reason, and exactly one disposition:
- `new_retrieval`: the report cannot proceed; create a new generation and retrieve.
- `uncertainty`: bind an uncertainty-ledger ID.
- `out_of_scope`: explain why it is outside the approved question.
```

Output target:

```text
contradiction-ledger.json
uncertainty-ledger.json
additional storm-tasklets when needed
storm-lens-conflicts.output.resolution_actions[]
```

## Prompt 3 — Synthesis Outline

Run after findings, contradiction mapping, and any resolver search. This prompt builds the outline; it does not write unsupported prose.

```text
Build a synthesis plan from the evidence-backed findings.

1. Rank findings by evidential strength, surprise, and importance to the user goal.
2. Identify the central thesis that is best supported by the current evidence.
3. Identify which contradictions must remain visible in the final report.
4. Identify which uncertainties limit the conclusion.
5. Create sections that each resolve named perspective questions.
6. For each section, list the Claim IDs, finding IDs, evidence needs, and expansion elements it must use.
7. Allocate the length budget across sections so the full dossier is substantive rather than padded.

Do not hide weak evidence. Do not convert unresolved questions into confident conclusions.
```

Output target:

```text
research-plan.report_outline
draft section plan
```

## Prompt 4 — Red-Team Review

Run after `draft`. This prompt produces repair actions, not release approval.

```text
Review the draft as an adversarial STORM editor.

1. What is the weakest important claim in the report?
2. Which paragraph sounds more certain than its evidence allows?
3. Which perspective is underrepresented or caricatured?
4. Did the report confuse analogy, interpretation, or consensus with evidence?
5. Is any citation attached to a sentence it does not actually support?
6. What missing source, if found, would most improve the report?
7. What should be revised, downgraded, removed, or sent back to retrieval?

Route each problem to one repair path:
- retrieval
- findings
- evidence ledger
- contradiction ledger
- outline
- draft
- render/validation

Each repair action must include `action_id`, target kind/ID, the target's before SHA-256, action, `required` or `waived` disposition, and reason. Do not mark an action applied inside Prompt 4; application is proven later by `revision-map.json` before `review-prepare` freezes the candidate.
```

Output target:

```text
peer-review.json
peer-review.md
repair-plan.json when validation fails
review-request.json after repairs close
```

## Guardrail

The original STORM voice is allowed to be vivid. The governed harness decides what is true.

Perspectives may generate hypotheses, analogies, and blind spots. Only registered sources, evidence locators, findings, and Claims may support report conclusions.
