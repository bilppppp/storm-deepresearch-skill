# Report Writing Rules

## Length and depth contract

Input size does not determine output depth. A one-sentence topic triggers more discovery; a rich packet supplies more of the spine. Unless the user explicitly requests a briefing, use the full-dossier contract in `brief.json`:

- Chinese body: `8000-10000` non-whitespace characters.
- English body: `3500-7000` words.
- Exclude the reference section from the count.
- Never satisfy the contract with repeated conclusions, generic background, oversized quotations, source lists, or fabricated examples.

If credible evidence cannot support the minimum, stop as `bounded_partial`, name the missing evidence, and do not mark the package releasable.

Before drafting, complete `research-plan.report_outline` and `storm-findings-pool.jsonl`. Give each section a distinct purpose, a length budget, the STORM question IDs it resolves, the finding IDs it uses, the Claim-Evidence IDs it uses, and at least three expansion elements.

Use `storm_research.py draft --preflight` before committing the draft when length, paragraph hashes, or citation bindings are still changing. Preflight reports the body count, paragraph previews, citation keys, and traceability errors without writing a draft receipt.

## Evidence-led expansion

Use research depth rather than verbal padding. A core section should usually move through:

1. **Claim**: state the bounded conclusion.
2. **Mechanism**: explain why or how the result occurs.
3. **Evidence**: compare the strongest direct support, including scope and method.
4. **Counterevidence**: show credible disagreement or a failed alternative explanation.
5. **Example**: make the mechanism concrete without presenting an invented case as fact.
6. **Implication**: explain what changes for the target audience.
7. **Limitation**: name where the conclusion stops applying.
8. **Change condition**: state what new evidence would revise the judgment.

Not every section needs all eight, but each planned section needs at least three and every major finding should include claim, evidence, implication, and limitation. Do not mention internal finding IDs in public prose; use them to keep the paragraph map, Claim ledger, and review inputs aligned.

## Suggested 9000-character Chinese budget

| Part | Target characters | Research used |
|---|---:|---|
| Executive summary | 600-800 | strongest findings, contradictions, decision implication |
| Question, scope, method | 700-900 | brief, source plan, boundaries |
| Multi-perspective synthesis | 1400-1800 | practitioner, academic, skeptic, incentive, historical questions |
| Evidence-ranked findings | 2800-3400 | material claims, mechanisms, direct evidence |
| Contradictions and blind spots | 900-1200 | contradiction and uncertainty ledgers |
| Implications and recommendations | 900-1200 | supported premises, tradeoffs, audience context |
| Change conditions and limitations | 500-800 | peer review, weakest links, frontier questions |

Adjust section sizes to the topic, but keep the total within the brief contract.

## Default report structure

```markdown
# Title

## Executive Summary

## Research Question and Scope

## Method and Source Base

## Key Findings

## Main Analysis

## Contradictions and Uncertainties

## Implications / Recommendations

## What Would Change These Conclusions

## Limitations

## References
```

## Style
- Write like a serious research memo, not a generic AI answer.
- Avoid “as an AI language model”, “based on my knowledge”, or “it is important to note”.
- Use direct claims, then cite or qualify them.
- Prefer specific constraints, dates, scopes, and mechanisms over broad adjectives.
- Preserve nuance without hiding the conclusion.
- Use the five perspectives as analytical lenses, not fictional quotations or authorities.
- Do not restate the executive summary as the main analysis; spend the added space on mechanism, evidence, disagreement, applicability, and decision consequences.

## Confidence labels
Use:
- **High confidence**: strong direct evidence, little credible disagreement.
- **Medium confidence**: good evidence but limited scope, indirect support, or moderate disagreement.
- **Low confidence**: weak evidence, emerging topic, sparse data, or heavy inference.

## Recommendation rules
Recommendations must identify:
- Who should act.
- What they should do.
- Under what condition.
- What evidence supports it.
- What risk or uncertainty remains.
