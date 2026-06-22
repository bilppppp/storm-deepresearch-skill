# Current Package Baseline

Captured on 2026-06-21 before implementation.

- Snapshot: `../storm-deepresearch-skill-v0.1.0-snapshot`
- Snapshot aggregate SHA-256: `a99ed1275f68ac3d3d9bf144da9aad212bf292d55dcf0cc9574b0c5602cd7678`
- Snapshot comparison: `diff -qr` returned zero differences.
- Yao validation: failed as expected.
- Governance score: `42/100` (`draft`).
- System stability profile: `59/100` (`fragile`).
- Initial-load estimate: `2049` tokens against a `1000`-token production default.
- Known validator defect: missing PDF and empty evidence could still exit zero.
- Known exporter defect: fallback HTML could leak Jinja markers and flatten Markdown tables.

This file records baseline evidence only. It is not a release-readiness claim.
