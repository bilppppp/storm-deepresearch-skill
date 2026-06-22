# Release Checklist

## Source Gates

- [ ] `manifest.json`, `agents/interface.yaml`, `SKILL.md`, schemas, and docs agree on version and behavior.
- [ ] Unit tests, compile checks, schema checks, and `yao validate` pass through `scripts/run_checks.py --all`.
- [ ] Default workspace output, existing-target refusal, symlink escape, and monotonic ledger merge tests pass.
- [ ] Trust scan reports no unapproved permissions, secrets, unpinned dependencies, or network-capable bundled scripts.
- [ ] OpenAI, Claude, and generic conformance pass.

## Output Gates

- [ ] Adversarial fixtures fail with the documented non-zero code.
- [ ] Representative research package passes strict validation.
- [ ] Full dossiers pass `storm-research-utilization` and `report-depth`; Chinese defaults contain 8000-10000 body characters excluding references.
- [ ] A real 0.4.0 long-form dossier has been reviewed for factual density, repetition, section balance, and output-boundary behavior before any superiority claim.
- [ ] HTML contains navigation, title, all report sections, and no unresolved template values.
- [ ] PDF is structurally valid and visually inspected on every page.
- [ ] Output Lab improves on the 0.1.0 baseline with no evidence or safety regression.
- [ ] Blind review decisions are recorded separately from automated fixture scores.

## Distribution Gates

- [ ] Platform packages are generated from the current source.
- [ ] `scripts/sanitize_release_archive.py` has redacted the current skill root and user home from the generated ZIP before package verification.
- [ ] Package verification passes and hashes correspond to the current source.
- [ ] A clean temporary install simulation passes without relying on the source `.venv`.
- [ ] `dist/` contains only release artifacts; temporary renders and caches are removed.
- [ ] Migration, known limitations, rollback boundary, and changelog are current.
