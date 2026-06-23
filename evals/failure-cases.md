# Failure Cases

These failures remain visible because a validator that only demonstrates success cannot prove anti-hallucination behavior. Each `###` case below is counted by the benchmark reproducibility report.

### Empty evidence

- Expected exit: `5`
- Protected invariant: A release needs at least one material evidence-backed claim.

### Fabricated source ID

- Expected exit: `5`
- Protected invariant: Every cited source ID exists in the source register.

### Stale current evidence

- Expected exit: `5`
- Protected invariant: A current claim cannot rely on stale support.

### Missing full-mode PDF

- Expected exit: `6`
- Protected invariant: Full mode requires a structurally valid PDF.

### Unresolved template marker

- Expected exit: `6`
- Protected invariant: Public outputs contain no template placeholders.

### Local path leak

- Expected exit: `7`
- Protected invariant: Public outputs expose no local filesystem path.

### Existing run reinitialization

- Expected exit: `4`
- Protected invariant: Canonical ledgers are never truncated by initialization.

### Output-root or package symlink escape

- Expected exit: `7`
- Protected invariant: Resolved writes remain inside the approved root and package.

### Failed source merge

- Expected exit: `4`
- Protected invariant: Invalid incoming retrieval data leaves the existing source ledger byte-for-byte unchanged.

### Failed Claim merge

- Expected exit: `4`
- Protected invariant: Invalid Claim updates cannot modify or delete prior Claim records.

### Governed placeholder source

- Expected exit: `5`
- Protected invariant: Placeholder URLs cannot become registered sources.

### Governed secondary-as-primary

- Expected exit: `5`
- Protected invariant: Secondary synthesis cannot be classified as primary Tier A evidence.

### Governed full-to-reduced

- Expected exit: `8`
- Protected invariant: A full dossier cannot be downgraded to reduced output after PDF failure.

### Governed unmapped factual paragraph

- Expected exit: `5`
- Protected invariant: New factual paragraphs require Claim, source, and citation mapping.

### Governed fake JSON

- Expected exit: `4`
- Protected invariant: Markdown or placeholder text cannot satisfy JSON contracts.

### Governed forged receipt

- Expected exit: `8`
- Protected invariant: Receipt status cannot bypass digest and artifact hash verification.

### Governed modified package

- Expected exit: `9`
- Protected invariant: Release requires matching package, registry, trust, and approval evidence.

The cases are implemented under `tests/fixtures/` and asserted in `tests/test_validate_package.py`. The validator must write a structured report and return the listed non-zero code; emitting a partial artifact is not a pass.

The governed bypass incident cases are recorded under `tests/fixtures/governed/gemini-bypass-redacted/`, asserted in `tests/test_incident_regressions.py`, and mirrored as output-eval prompts under `evals/output/`. They are redacted descriptors, not copies of private raw output.
# Long-form depth failures

- A full Chinese dossier below 8000 body characters must fail `report-depth` with exit `6`.
- References, source tables, quotations, and repeated summaries must not be used to satisfy the body-length contract.
- An answered perspective question absent from `research-plan.report_outline` must fail `storm-research-utilization`.
- A full dossier with fewer than five perspectives, ten questions, six planned sections, or twelve material claims must remain unreleasable.

# Output boundary failures

- A run path outside the resolved output root must fail before creating files.
- An existing run directory must fail before reading or writing its ledgers.
- An `exports/`, `research/`, or `validation/` symlink that resolves outside the package must fail with exit `7`.
- New source records must preserve existing IDs; a failed parse or merge must not alter the source register.
- Claim updates may add or explicitly revise IDs but cannot delete omitted records; failed validation leaves the ledger unchanged.
