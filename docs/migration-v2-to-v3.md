# Migration from 2.x to 3.0.0

Version 3.0 keeps the `storm_research.py ingest RUN_DIR --input-jsonl FILE` command, but intentionally breaks the JSONL record contract. A 2.x capture-only row cannot show which searches ran, which candidates were rejected, whether a scholarly identity resolved, or whether two URLs are versions of the same work. Version 3.0 requires those facts before a full dossier can advance.

## Contract changes

The ingest file is now a strict union of three record kinds:

1. `search_run` records the query, aliases, discovery surface, pass kind, result count, status, and result snapshot.
2. `candidate` records screening disposition, bibliographic identifiers, resolver evidence, and version-family membership.
3. `capture` records the exact included version, query binding, content snapshot, locator, excerpt, and evidence ceiling.

Successful ingest creates one new runtime artifact: `research/retrieval-audit.jsonl`. It is internal, generation-scoped, bound into `20-retrieval.json`, and excluded from public release. Academic source-register rows also gain a nested `bibliographic` object; nonacademic rows use `bibliographic: null`.

External full dossiers must complete an academic baseline across at least two scholarly surfaces. Briefings may use one surface but must verify every academic source they cite. Corpus input seeds queries; it does not suppress baseline, counterevidence, or gap-fill search.

## Adapter changes

Custom host or provider adapters must:

- save immutable snapshots for every search run and resolver check;
- emit stable `SRnnn` search-run and `Knnn` candidate IDs;
- connect candidates to every applicable search run;
- distinguish `unmatched` from `unreachable`;
- preserve excluded candidates and reasons;
- normalize DOI, PMID, arXiv, Semantic Scholar, and OpenAlex IDs when available;
- group preprint, conference, journal, book, or report versions into a version family;
- emit captures only for included candidates and bind the exact candidate version.

Host tools still own network execution. The skill does not add an implicit crawler or provider dependency.

## Before and after

A 2.x adapter emitted only a capture row:

```json
{"query_id":"Q001","url":"https://doi.org/10.1000/example","final_url":"https://publisher.example/paper","file_ref":null,"title":"Example Paper","publisher":"Example Journal","published_at":"2025-01-02","publication_date_status":"known","retrieved_at":"2026-07-03T08:05:00Z","content_excerpt":"Exact evidence text.","content_locator":"section:Results","locator_type":"section","adapter":"host","adapter_run_id":"host-001","capture_level":"full_text","evidence_strength_ceiling":"strong","raw_artifact":"evidence-cache/paper.html","observed_status":200,"content_type":"text/html","source_type":"peer_reviewed_paper","primary_class":"primary","reliability_tier":"A","freshness_status":"current","reliability_notes":"Directly inspected peer-reviewed result."}
```

A 3.0 adapter emits the search, candidate, then capture. The referenced files and hashes below are illustrative; real hashes must match the saved bytes.

```jsonl
{"record_kind":"search_run","search_run_id":"SR001","query_id":"Q001","adapter":"host","pass_kind":"baseline","surface":"OpenAlex","surface_class":"scholarly_index","query":"example treatment outcome","aliases":["example treatment"],"searched_at":"2026-07-03T08:00:00Z","result_count":1,"execution_status":"completed","raw_artifact":"evidence-cache/search-SR001.json","snapshot_sha256":"0000000000000000000000000000000000000000000000000000000000000000","limitations":[]}
{"record_kind":"candidate","candidate_id":"K001","adapter":"host","search_run_ids":["SR001"],"title":"Example Paper","authors":["A. Researcher"],"year":2025,"venue":"Example Journal","url":"https://doi.org/10.1000/example","identifiers":{"doi":"10.1000/example","pmid":null,"arxiv_id":null,"semantic_scholar_id":null,"openalex_id":"W123"},"resolver_outcomes":[{"resolver":"Crossref","status":"matched","query_basis":"doi","matched_identifier":"10.1000/example","returned_title":"Example Paper","returned_authors":["A. Researcher"],"returned_year":2025,"metadata_match":true,"checked_at":"2026-07-03T08:02:00Z","raw_artifact":"evidence-cache/resolver-K001.json","snapshot_sha256":"1111111111111111111111111111111111111111111111111111111111111111","reason":"DOI and metadata match."}],"disposition":"include","screening_reason":"Directly addresses Q001 and full text is inspectable.","version_family_id":"W001","version_role":"journal","relationship_basis":"exact_identifier"}
{"record_kind":"capture","candidate_id":"K001","search_run_ids":["SR001"],"query_id":"Q001","url":"https://doi.org/10.1000/example","final_url":"https://publisher.example/paper","file_ref":null,"title":"Example Paper","publisher":"Example Journal","published_at":"2025-01-02","publication_date_status":"known","retrieved_at":"2026-07-03T08:05:00Z","content_excerpt":"Exact evidence text.","content_locator":"section:Results","locator_type":"section","adapter":"host","adapter_run_id":"host-001","capture_level":"full_text","evidence_strength_ceiling":"strong","raw_artifact":"evidence-cache/paper.html","observed_status":200,"content_type":"text/html","source_type":"peer_reviewed_paper","primary_class":"primary","reliability_tier":"A","freshness_status":"current","reliability_notes":"Directly inspected peer-reviewed result."}
```

See `schemas/retrieval-record.schema.json` for the authoritative field contract. Do not copy the illustrative hashes.

## Existing runs and rollback

Do not hand-edit old artifacts or fabricate a 3.0 audit for a 2.x run. Existing runs remain bound to the package and receipt hashes that created them. Start a new 3.0 run to use the new academic retrieval gates.

To interpret or repair a 2.x run, use the archived 2.0.0 package. Rolling back the executable does not downgrade a 3.0 run; 3.0 receipts and retrieval audits remain governed by 3.0.
