# From Four STORM Prompts to Evidence-Governed Deep Research

## Executive Summary

The four-prompt workflow captures a useful sequence: look through several perspectives, expose disagreements, synthesize, and self-criticize. It does not reproduce the central grounding mechanism of STORM by itself. The published system retrieves sources, asks perspective-guided questions against that material, curates information, builds an outline, and then writes with citations. A reusable research skill therefore needs a retrieval boundary, source register, claim-evidence ledger, contradiction and uncertainty records, one canonical Markdown report, deterministic HTML/PDF rendering, and non-zero validation failures.

## Research Question and Scope

This report asks what must be added to the article's four-prompt idea before it can serve as an auditable research Library. It evaluates method and engineering boundaries, not the quality of a particular language model or retrieval provider.

## Method and Source Base

The review uses the NAACL 2024 STORM paper as the primary source for method, evaluation, and limitations; the Stanford OVAL repository as the primary implementation source; and the supplied article only to identify the motivating prompt-chain framing. Material statements are separately mapped to evidence in the audit package.

## Key Findings

| Finding | Confidence | Main limitation |
|---|---|---|
| Multi-perspective questioning is a retrieval-planning technique, not independent evidence. | High | The best perspective set remains domain-dependent. |
| The paper reports a threshold-based absolute increase, not a generic 25% improvement in organization quality. | High | The human study involved ten experienced Wikipedia editors. |
| Citations alone did not eliminate unsupported or over-associated statements. | High | Part of the citation analysis used model-assisted entailment checking. |
| A Library implementation needs executable evidence and export gates. | High, qualified recommendation | Structural checks cannot replace semantic review. |

## What STORM Actually Proves

STORM is more than five simulated voices. Its pre-writing stage discovers perspectives, uses them to guide questions, grounds answers in retrieved Internet sources, and curates the material into an outline. The official implementation likewise separates research, outline generation, article generation, and polishing.

The article's phrase “25 percent more organized” is too broad. In the paper's human evaluation, 45% of baseline articles and 70% of STORM articles received an organization rating of at least four. That is a 25 percentage-point absolute increase in the share crossing a specified threshold. The corresponding good-coverage share increased by 10 percentage points. Those results support the method in that evaluation setting; they do not establish that every STORM output is 25% better organized.

## Why Four Prompts Are Not Enough

A role prompt can generate plausible practitioner, academic, skeptic, economic, or historical language without retrieving a single source. If synthesis treats those voices as facts, the workflow turns diversity of phrasing into false evidence diversity.

The paper's own analysis shows why a citation list is also insufficient. Roughly 15% of generated sentences in its citation-quality analysis were unsupported, with failures including improper inferential linking, inaccurate paraphrasing, and irrelevant citations. Editors additionally identified source-bias transfer and over-association of unrelated facts. The engineering response must therefore check claim-level relationships and contradictions, not just whether a URL appears near a paragraph.

## Recommended Library Architecture

Use perspectives only to generate research questions and blind-spot checks. Route retrieval through approved host tools, an explicit provider adapter, or a closed corpus. Normalize every source into a provenance-bearing register, then atomize material facts, inferences, and recommendations in a claim-evidence ledger. Keep contradictions and freshness failures visible.

Write `report.md` once. Derive HTML through Pandoc and a strict Jinja template, then derive PDF through WeasyPrint or a documented Chromium fallback. Validate contracts, evidence closure, title and section parity, PDF text, unresolved template markers, local-path leakage, and public exposure of internal audit IDs. Required failures must return non-zero.

## Contradictions and Uncertainties

The main contradiction is between a catchy summary and the paper's narrower measurement. The resolution is not to discard the result, but to preserve the threshold, baseline, comparison, sample, and absolute percentage-point wording.

The remaining uncertainty is semantic entailment. A deterministic validator can prove that a source and locator exist, that every material fact is mapped, and that formats match. It cannot alone prove that the excerpt truly supports the exact sentence. High-impact real-world reports still need a citation audit by a capable model or human reviewer.

## Implications and Recommendations

Skill authors should treat the article as a workflow sketch, not as evidence that four prompts create PhD-level research in five minutes. The practical upgrade is to preserve its useful questions while moving authority into retrieved evidence and executable gates. This costs more time and files than a prompt chain, but it makes unsupported completion visible and repairable.

## What Would Change These Conclusions

A simpler workflow would be preferable if it could demonstrate equal claim closure, freshness handling, contradiction coverage, cross-format consistency, and adversarial performance. Conversely, new evidence that structural ledgers do not improve auditability would weaken the recommendation.

## Limitations

This package does not include provider-backed model runs. Its Output Lab uses static and deterministic command fixtures, labeled as such. It also does not automate semantic entailment; it makes the evidence surface inspectable so that semantic review can be performed explicitly.

## References

- Shao, Yijia, et al. [Assisting in Writing Wikipedia-like Articles From Scratch with Large Language Models](https://aclanthology.org/2024.naacl-long.347/). NAACL 2024.
- Stanford OVAL. [STORM: Synthesis of Topic Outlines through Retrieval and Multi-perspective Question Asking](https://github.com/stanford-oval/storm). Official repository, retrieved 2026-06-21.
- User-supplied article excerpt, used only to evaluate the four-prompt framing.
