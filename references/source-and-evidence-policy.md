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

Fresh current claims past the brief's freshness window require host-supplied re-verification before public release. Historical claims may remain historical, but must be labeled as such.
