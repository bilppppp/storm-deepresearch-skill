# Promotion Decisions

## Decision

Promote `storm-deepresearch-skill` from `0.3.0` to `0.4.0` for local Library use.

- Engineering review: pass
- Unit tests: 66/66
- Yao validation and five-target conformance: pass
- Package, install, runtime permission, and registry checks: pass
- Previous seven-case blind human review: complete
- Human review of a real workspace-scoped 8000-10000-character 0.4.0 dossier: pending

## Added Release Gates

1. New runs default below `<workspace>/output/storm-deepresearch/`.
2. Existing run directories fail before any ledger write.
3. Resolved symlink paths cannot escape the output root or package.
4. Source-register merges preserve IDs and commit atomically.
5. Claim-ledger merges preserve omitted records and commit atomically.
6. Export and validation writes are fixed package children.

## Evidence Boundary

This decision promotes the local engineering contract. It does not claim that an actual long-form provider output has passed human qualitative review, provider holdout comparison, native client permission enforcement, broad production adoption, or world-class superiority.

## Next Review

Review the first real 0.4.0 full dossier for factual density, repetition, section balance, cross-agent workspace placement, and ledger preservation.
