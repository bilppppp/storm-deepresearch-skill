# Release Checklist

## Source Gates

- [ ] `manifest.json`, `agents/interface.yaml`, `SKILL.md`, schemas, and docs agree on version and behavior.
- [ ] Unit tests, compile checks, schema checks, and `yao validate` pass through `scripts/run_checks.py --all`.
- [ ] Default workspace output, existing-target refusal, symlink escape, immutable receipt chain, recovery commands, and monotonic ledger merge tests pass.
- [ ] Trust scan reports no unapproved permissions, secrets, unpinned dependencies, or network-capable bundled scripts.
- [ ] OpenAI, Claude, and generic conformance pass.

## Output Gates

- [ ] Adversarial fixtures fail with the documented non-zero code.
- [ ] `tests/test_incident_regressions.py` blocks placeholder sources, secondary-as-primary, full-to-reduced downgrade, unmapped facts, fake JSON, forged receipts, and modified package release.
- [ ] Representative research package passes strict validation.
- [ ] Full dossiers pass `storm-research-utilization` and `report-depth`; Chinese defaults contain 8000-10000 body characters excluding references.
- [ ] Report-depth measurements show raw, citation-marker, and net body counts; only visible net prose satisfies the minimum.
- [ ] Full dossiers contain a frozen review request, captured external reviewer provenance, transcript hash, and closed P4 revision map.
- [ ] Absence claims and evidence-strength ceilings pass their governed gates.
- [ ] A real governed full dossier has been reviewed for factual density, repetition, section balance, receipt-chain behavior, and release boundary behavior before any superiority claim.
- [ ] HTML contains navigation, title, all report sections, and no unresolved template values.
- [ ] PDF is structurally valid and visually inspected on every page.
- [ ] Output Lab improves on the 0.1.0 baseline with no evidence or safety regression.
- [ ] Blind review decisions are recorded separately from automated fixture scores.

## Distribution Gates

- [ ] Platform packages are generated from the current source with `scripts/run_checks.py --dist`.
- [ ] Registry metadata package hash matches the current Yao source-contract hash.
- [ ] `storm_research.py release` succeeds only with host-controlled Trust evidence, Yao Trust report, human approval, and required re-verification records.
- [ ] `release/` contains only the allowlisted public files and excludes `work/`, `state/`, raw retrieval inputs, claim updates, and amendment inputs.
- [ ] `scripts/sanitize_release_archive.py` has redacted the current skill root and user home from the generated ZIP before package verification.
- [ ] Package verification passes and hashes correspond to the current source; verification artifacts are in `dist/package_verification.*`.
- [ ] A clean temporary install simulation passes without relying on the source `.venv`.
- [ ] `dist/` contains only release artifacts; temporary renders and caches are removed.
- [ ] Migration, known limitations, rollback boundary, and changelog are current.
