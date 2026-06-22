# Failure Cases

These failures remain visible because a validator that only demonstrates success cannot prove anti-hallucination behavior.

| Case | Expected exit | Protected invariant |
|---|---:|---|
| Empty evidence | `5` | A release needs at least one material evidence-backed claim. |
| Fabricated source ID | `5` | Every cited source ID exists in the source register. |
| Stale current evidence | `5` | A current claim cannot rely on stale support. |
| Missing full-mode PDF | `6` | Full mode requires a structurally valid PDF. |
| Unresolved template marker | `6` | Public outputs contain no template placeholders. |
| Local path leak | `7` | Public outputs expose no local filesystem path. |
| Existing run reinitialization | `4` | Canonical ledgers are never truncated by initialization. |
| Output-root or package symlink escape | `7` | Resolved writes remain inside the approved root and package. |
| Failed source merge | `4` | Invalid incoming retrieval data leaves the existing source ledger byte-for-byte unchanged. |
| Failed Claim merge | `4` | Invalid Claim updates cannot modify or delete prior Claim records. |

The cases are implemented under `tests/fixtures/` and asserted in `tests/test_validate_package.py`. The validator must write a structured report and return the listed non-zero code; emitting a partial artifact is not a pass.
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
