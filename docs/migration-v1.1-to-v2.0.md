# Migration from 1.1.0 to 2.0.0

Version 2.0 intentionally rejects 1.1 shortcuts. Existing runs remain auditable with the archived 1.1 package; do not edit their receipts or package hash.

For a new 2.0 run:

1. Add `evidence_mode` and `absence_search_id` to every Claim. Use `premise` for inference/recommendation and `absence_search` only with a matching search ledger.
2. Add `resolution_actions` to Prompt 2. A `new_retrieval` disposition requires `amend` and a new generation before Prompt 3.
3. Replace old P4 repair records with target IDs, before hashes, action, disposition, and reason; close them in the revision map.
4. Run `review-prepare` after P4 repairs, then obtain an isolated external-model or human review with provenance and transcript hashes.
5. Re-run render and validation. The report-depth minimum now uses visible net prose, not citation keys or Markdown syntax.

There is no legacy flag that makes a 1.1 run releasable under 2.0. Re-run or create an amended generation with fresh evidence and review.
