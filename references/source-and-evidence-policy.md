# Source and Evidence Policy

`work/generations/g0001/artifacts/research/source-register.jsonl` is authoritative. `source-register.md` is a generated release view.

## Source register fields
Every source must be registered with:

| Field | Meaning |
|---|---|
| Source ID | Stable ID such as S001 or S002 |
| Title | Exact title |
| Author / Organization | Creator or publisher |
| Date | Publication or last updated date |
| Retrieved | Date accessed |
| Type | Official, paper, dataset, filing, news, expert, community, user-provided |
| Reliability tier | A, B, C, D |
| URL / file reference | Canonical URL or corpus-relative file reference |
| Used for | Claims or sections supported |
| Caveats | Bias, age, method limits, geography limits |

Academic source records also contain a nested `bibliographic` object with identifiers, verification status, version-family ID, and version role. Nonacademic sources use `bibliographic: null`. `verified` requires matching resolver evidence; an unreachable resolver cannot be treated as a successful match.

## Reliability tiers
- **A**: primary/official source, law/regulation, audited filing, dataset, standards body, peer-reviewed paper with directly relevant method.
- **B**: reputable secondary source, recognized research institution, high-quality expert analysis.
- **C**: trade blog, reputable community report, vendor content with clear bias, credible but limited case study.
- **D**: unsourced social post, anonymous anecdote, SEO content, unverifiable claim.

Tier A is not a default. A secondary synthesis cannot be marked `primary`, and search snippets cannot be Tier A evidence. If the source role is unclear, lower the tier and record the limitation.

Wikipedia and comparable encyclopedias are background sources: classify them as `encyclopedia`, `secondary`, and not Tier A. Placeholder or reserved domains, including `example.com` and `.internal`, cannot enter the source register as public URLs. Local or supplied corpus material must use a corpus-relative `file_ref`.

For full dossiers with external research allowed, user material, transcripts, local files, search snippets, community posts, and encyclopedias do not count toward the required six deep external sources. Claims about named theories, thinkers, scholarly debates, or interpretive frameworks require academic, book, expert, peer-reviewed, or reputable synthesis support beyond the user's own text.

External full dossiers additionally require an academic baseline across two scholarly discovery surfaces. Briefings may use one academic surface. Corpus-first means the supplied corpus seeds queries and screening priorities; search-fills-gap means baseline, counterevidence, and gap-fill searches still close questions the corpus cannot answer.

## Citation discipline
- A citation supports only the exact sentence it is attached to.
- Do not cite a source for a stronger claim than it makes.
- Do not cite a secondary summary when a primary source is available and practical.
- If sources conflict, cite both sides and explain the disagreement.
- If a source is old, say why it is still applicable or mark it as historical context.

## Source-method fit

Judge the shape of the specific Claim before judging whether its source and method can support it.

| Source or method | Can support | Cannot support alone |
|---|---|---|
| Official statement, product manual, or policy | Recorded features, rules, and positions | Real-world adoption effects, satisfaction, or independent effectiveness |
| User or community experience | That person's experience and signals of possible problems | Prevalence, general effectiveness, or population conclusions |
| News report or press release | That an event or statement was reported | The underlying claim's truth or a causal mechanism |
| Survey or observational study | Proportions or associations within its sample and measurements | Causal effects or unconditional population generalization |
| Experiment or quasi-experiment | Effects within its identification assumptions and measured scope | Unmeasured long-term effects or universal applicability |
| Systematic review or meta-analysis | Synthesis within the included studies | Elimination of bias, heterogeneity, or applicability limits |

- Tier, source prestige, and paper count cannot upgrade what a research method can prove.
- Multiple observational results do not automatically become causal proof.
- A question's evidence mix may be completed across multiple Claims; do not require every Claim to carry every evidence role in the question plan.
- P4 and external review must identify the concrete Claim, sentence, or source at issue. They must not reject an entire source category merely because it is nonacademic, news, or user-provided.

## Capture ceilings and absence claims

- A fact Claim cannot be stronger than the exact retrieval manifest bound by its locator. `strong` requires at least one strong full-text or official-data capture; several medium abstracts do not automatically become strong.
- Inference and recommendation strength cannot exceed the weakest premise Claim.
- One canonical source may serve multiple query IDs. Source identity is deduplicated, while each query/capture binding remains in the retrieval manifest.
- Multiple versions of one scholarly work share a version-family ID and count as one independent source. A Claim locator must match the exact captured candidate version and snapshot.
- Candidate exclusion is preserved in the internal retrieval audit. Excluded, zero-result, unmatched, or unreachable records cannot become evidence.
- Material “not found” claims use `evidence_mode=absence_search` and a matching absence-search record. Full dossiers require two discovery surfaces; high-stakes medical searches require a trial registry, bibliographic database, and at least three aliases.
- Closed-corpus searches may only conclude that evidence is absent from the supplied corpus.

## Unsupported claim handling
Unsupported claims must be one of:
1. Removed.
2. Softened and labeled as inference.
3. Moved to “hypotheses to verify”.
4. Kept only if clearly marked as unknown.

Unknown or unsupported material facts cannot remain in the released report. See [Claim-Evidence Policy](claim-evidence-policy.md).

Known stale or historical material cannot support an explicit current fact without current re-verification. An unobserved publication date or unknown freshness is a non-blocking risk for semantic review, not an evidence-closure failure: do not reject otherwise credible content or require a stock “date unknown” qualification solely for that missing adapter observation. Historical claims may remain historical when their scope is clear.
