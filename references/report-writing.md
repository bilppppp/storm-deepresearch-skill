# Report Writing Rules

## Length and depth contract

Input size does not determine output depth. A one-sentence topic triggers more discovery; a rich packet supplies more of the spine. Unless the user explicitly requests a briefing or the advanced maximal profile, use the bounded full-dossier contract in `brief.json`:

- Chinese net body: `8000-10000` non-whitespace characters.
- English net body: `3500-7000` words.
- Exclude bibliography/source sections, footnote keys, link destinations, image markers, HTML tags, and Markdown control syntax from the count. Preserve visible link text and inline-code content.
- Exclude Markdown blockquotes and fenced code from the count; long quoted blocks are supporting evidence, not original analysis.
- Never satisfy the contract with repeated conclusions, generic background, oversized quotations, source lists, or fabricated examples.

If credible evidence cannot support the minimum, stop as `bounded_partial`, name the missing evidence, and do not mark the package releasable.

When the user explicitly selects `maximal_full_dossier`, `brief.length_contract.policy` is `open_ended`: there is no minimum, target, maximum, source quota, or candidate quota. Plan section depth and evidence needs before drafting. Continue only while a recomputed search wave changes a material Claim, contradiction, uncertainty, locator, mechanism, or section; stop only after every tasklet and P2 gap has a terminal disposition and review finds no material omission. Open-ended does not relax quote limits, paragraph mapping, Claim-Evidence closure, PDF/HTML parity, P4 repairs, external review provenance, or release gates. A review concern routed to draft must visibly change the bound report/paragraph/revision hashes; `preserved_as_uncertainty` must appear at its bound paragraph or Claim. Synthesize by mechanism, controversy, chronology, and implication. Repeated phrases such as "这条可审计来源是..." or "this source record..." belong in ledgers, not public prose; citation accumulation that does not change the argument is not research depth.

Before drafting, complete `research-plan.report_outline` and `storm-findings-pool.jsonl`. Give each section a distinct purpose, a length budget, the STORM question IDs it resolves, the finding IDs it uses, the Claim-Evidence IDs it uses, and at least three expansion elements.

Use `storm_research.py build-paragraph-map` to generate paragraph mappings from sidecar JSONL or `storm-map` comments, then run `storm_research.py draft --preflight` before committing the draft when length, paragraph hashes, or citation bindings are still changing. Preflight reports the net body count, excluded quote count, paragraph previews, citation keys, and traceability errors without writing a draft receipt.

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

Adjust section sizes to the topic, but keep the total within the bounded brief contract unless `maximal_full_dossier` explicitly selected open-ended depth.

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
