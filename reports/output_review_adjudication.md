# Output Review Adjudication

This report adjudicates reviewer choices from the blind A/B output review pack against the separate answer key.

- Pairs: `7`
- Judgments: `0`
- Pending: `7`
- Agreement rate: `n/a`
- Invalid decisions: `0`
- Answer keys revealed: `0`
- Pending/invalid answers hidden: `7`
- Reviewer checklist: `0` ready / `7` total
- Reviewer metadata present: `false`
- Blind review attested: `false`
- Raw content excluded: `true`
- Ready for human evidence: `false`

No reviewer decisions recorded yet.

Generate a template with `--write-template`, fill `winner_variant` with `A` or `B`, then rerun adjudication.
Expected winners stay hidden until a valid reviewer decision is recorded.

## Case Adjudication

| Case | Reviewer | Expected | Status | Confidence | Reason |
| --- | --- | --- | --- | ---: | --- |
| governed-placeholder-source-refusal | pending | hidden | pending |  |  |
| governed-downgrade-output-refusal | pending | hidden | pending |  |  |
| governed-padding-refusal | pending | hidden | pending |  |  |
| governed-validator-edit-refusal | pending | hidden | pending |  |  |
| governed-release-without-trust-refusal | pending | hidden | pending |  |  |
| near-neighbor-simple-lookup | pending | hidden | pending |  |  |
| closed-corpus-boundary | pending | hidden | pending |  |  |

## Reviewer Checklist

| Case | Readiness | Answer key | Decision file |
| --- | --- | --- | --- |
| `governed-placeholder-source-refusal` | `awaiting-decision` | `hidden` | `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_review_decisions.json` |
| `governed-downgrade-output-refusal` | `awaiting-decision` | `hidden` | `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_review_decisions.json` |
| `governed-padding-refusal` | `awaiting-decision` | `hidden` | `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_review_decisions.json` |
| `governed-validator-edit-refusal` | `awaiting-decision` | `hidden` | `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_review_decisions.json` |
| `governed-release-without-trust-refusal` | `awaiting-decision` | `hidden` | `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_review_decisions.json` |
| `near-neighbor-simple-lookup` | `awaiting-decision` | `hidden` | `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_review_decisions.json` |
| `closed-corpus-boundary` | `awaiting-decision` | `hidden` | `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_review_decisions.json` |

### governed-placeholder-source-refusal

- readiness: `awaiting-decision`
- blocking reason: Reviewer has not selected A or B yet; answer key remains hidden.
- answer key visible: `false`
- blind pack: `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_blind_review_pack.json`
- decisions: `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_review_decisions.json`

#### Commands

- prepare_review_kit: `python3 scripts/yao.py output-review-kit`
- write_template: `python3 scripts/adjudicate_output_review.py --write-template`
- import_decisions: `python3 scripts/yao.py output-review-import --input <reviewer-decisions.json> --blind-review-attested --run-adjudication`
- adjudicate: `python3 scripts/yao.py output-review`
- refresh_review_studio: `python3 scripts/yao.py review-studio .`

#### Required Fields

- winner_variant: A or B after reading only the blind review pack.
- confidence: Optional number from 0 to 1.
- reason: Required rationale; do not reveal baseline or with-skill labels before adjudication.
- reviewer: Human reviewer name or review group at the decision-file top level.
- reviewed_at: Review date or timestamp at the decision-file top level.
- reviewer_attestation.blind_review_completed_before_answer_key: True only after the reviewer has completed choices before opening the answer key.
- reviewer_attestation.answer_key_not_opened_before_decisions: True only when the answer key was not opened before decisions were recorded.

#### Privacy Contract

- Do not paste raw private user data into the decision reason.
- Do not open the answer key before reviewer choices are recorded.
- Leave winner_variant blank when the reviewer is not ready to decide.

### governed-downgrade-output-refusal

- readiness: `awaiting-decision`
- blocking reason: Reviewer has not selected A or B yet; answer key remains hidden.
- answer key visible: `false`
- blind pack: `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_blind_review_pack.json`
- decisions: `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_review_decisions.json`

#### Commands

- prepare_review_kit: `python3 scripts/yao.py output-review-kit`
- write_template: `python3 scripts/adjudicate_output_review.py --write-template`
- import_decisions: `python3 scripts/yao.py output-review-import --input <reviewer-decisions.json> --blind-review-attested --run-adjudication`
- adjudicate: `python3 scripts/yao.py output-review`
- refresh_review_studio: `python3 scripts/yao.py review-studio .`

#### Required Fields

- winner_variant: A or B after reading only the blind review pack.
- confidence: Optional number from 0 to 1.
- reason: Required rationale; do not reveal baseline or with-skill labels before adjudication.
- reviewer: Human reviewer name or review group at the decision-file top level.
- reviewed_at: Review date or timestamp at the decision-file top level.
- reviewer_attestation.blind_review_completed_before_answer_key: True only after the reviewer has completed choices before opening the answer key.
- reviewer_attestation.answer_key_not_opened_before_decisions: True only when the answer key was not opened before decisions were recorded.

#### Privacy Contract

- Do not paste raw private user data into the decision reason.
- Do not open the answer key before reviewer choices are recorded.
- Leave winner_variant blank when the reviewer is not ready to decide.

### governed-padding-refusal

- readiness: `awaiting-decision`
- blocking reason: Reviewer has not selected A or B yet; answer key remains hidden.
- answer key visible: `false`
- blind pack: `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_blind_review_pack.json`
- decisions: `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_review_decisions.json`

#### Commands

- prepare_review_kit: `python3 scripts/yao.py output-review-kit`
- write_template: `python3 scripts/adjudicate_output_review.py --write-template`
- import_decisions: `python3 scripts/yao.py output-review-import --input <reviewer-decisions.json> --blind-review-attested --run-adjudication`
- adjudicate: `python3 scripts/yao.py output-review`
- refresh_review_studio: `python3 scripts/yao.py review-studio .`

#### Required Fields

- winner_variant: A or B after reading only the blind review pack.
- confidence: Optional number from 0 to 1.
- reason: Required rationale; do not reveal baseline or with-skill labels before adjudication.
- reviewer: Human reviewer name or review group at the decision-file top level.
- reviewed_at: Review date or timestamp at the decision-file top level.
- reviewer_attestation.blind_review_completed_before_answer_key: True only after the reviewer has completed choices before opening the answer key.
- reviewer_attestation.answer_key_not_opened_before_decisions: True only when the answer key was not opened before decisions were recorded.

#### Privacy Contract

- Do not paste raw private user data into the decision reason.
- Do not open the answer key before reviewer choices are recorded.
- Leave winner_variant blank when the reviewer is not ready to decide.

### governed-validator-edit-refusal

- readiness: `awaiting-decision`
- blocking reason: Reviewer has not selected A or B yet; answer key remains hidden.
- answer key visible: `false`
- blind pack: `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_blind_review_pack.json`
- decisions: `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_review_decisions.json`

#### Commands

- prepare_review_kit: `python3 scripts/yao.py output-review-kit`
- write_template: `python3 scripts/adjudicate_output_review.py --write-template`
- import_decisions: `python3 scripts/yao.py output-review-import --input <reviewer-decisions.json> --blind-review-attested --run-adjudication`
- adjudicate: `python3 scripts/yao.py output-review`
- refresh_review_studio: `python3 scripts/yao.py review-studio .`

#### Required Fields

- winner_variant: A or B after reading only the blind review pack.
- confidence: Optional number from 0 to 1.
- reason: Required rationale; do not reveal baseline or with-skill labels before adjudication.
- reviewer: Human reviewer name or review group at the decision-file top level.
- reviewed_at: Review date or timestamp at the decision-file top level.
- reviewer_attestation.blind_review_completed_before_answer_key: True only after the reviewer has completed choices before opening the answer key.
- reviewer_attestation.answer_key_not_opened_before_decisions: True only when the answer key was not opened before decisions were recorded.

#### Privacy Contract

- Do not paste raw private user data into the decision reason.
- Do not open the answer key before reviewer choices are recorded.
- Leave winner_variant blank when the reviewer is not ready to decide.

### governed-release-without-trust-refusal

- readiness: `awaiting-decision`
- blocking reason: Reviewer has not selected A or B yet; answer key remains hidden.
- answer key visible: `false`
- blind pack: `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_blind_review_pack.json`
- decisions: `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_review_decisions.json`

#### Commands

- prepare_review_kit: `python3 scripts/yao.py output-review-kit`
- write_template: `python3 scripts/adjudicate_output_review.py --write-template`
- import_decisions: `python3 scripts/yao.py output-review-import --input <reviewer-decisions.json> --blind-review-attested --run-adjudication`
- adjudicate: `python3 scripts/yao.py output-review`
- refresh_review_studio: `python3 scripts/yao.py review-studio .`

#### Required Fields

- winner_variant: A or B after reading only the blind review pack.
- confidence: Optional number from 0 to 1.
- reason: Required rationale; do not reveal baseline or with-skill labels before adjudication.
- reviewer: Human reviewer name or review group at the decision-file top level.
- reviewed_at: Review date or timestamp at the decision-file top level.
- reviewer_attestation.blind_review_completed_before_answer_key: True only after the reviewer has completed choices before opening the answer key.
- reviewer_attestation.answer_key_not_opened_before_decisions: True only when the answer key was not opened before decisions were recorded.

#### Privacy Contract

- Do not paste raw private user data into the decision reason.
- Do not open the answer key before reviewer choices are recorded.
- Leave winner_variant blank when the reviewer is not ready to decide.

### near-neighbor-simple-lookup

- readiness: `awaiting-decision`
- blocking reason: Reviewer has not selected A or B yet; answer key remains hidden.
- answer key visible: `false`
- blind pack: `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_blind_review_pack.json`
- decisions: `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_review_decisions.json`

#### Commands

- prepare_review_kit: `python3 scripts/yao.py output-review-kit`
- write_template: `python3 scripts/adjudicate_output_review.py --write-template`
- import_decisions: `python3 scripts/yao.py output-review-import --input <reviewer-decisions.json> --blind-review-attested --run-adjudication`
- adjudicate: `python3 scripts/yao.py output-review`
- refresh_review_studio: `python3 scripts/yao.py review-studio .`

#### Required Fields

- winner_variant: A or B after reading only the blind review pack.
- confidence: Optional number from 0 to 1.
- reason: Required rationale; do not reveal baseline or with-skill labels before adjudication.
- reviewer: Human reviewer name or review group at the decision-file top level.
- reviewed_at: Review date or timestamp at the decision-file top level.
- reviewer_attestation.blind_review_completed_before_answer_key: True only after the reviewer has completed choices before opening the answer key.
- reviewer_attestation.answer_key_not_opened_before_decisions: True only when the answer key was not opened before decisions were recorded.

#### Privacy Contract

- Do not paste raw private user data into the decision reason.
- Do not open the answer key before reviewer choices are recorded.
- Leave winner_variant blank when the reviewer is not ready to decide.

### closed-corpus-boundary

- readiness: `awaiting-decision`
- blocking reason: Reviewer has not selected A or B yet; answer key remains hidden.
- answer key visible: `false`
- blind pack: `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_blind_review_pack.json`
- decisions: `/Users/gravity/Documents/Codex/2026-06-21/https-github-com-yaojingang-yao-meta/work/storm-deepresearch-skill-v1/reports/output_review_decisions.json`

#### Commands

- prepare_review_kit: `python3 scripts/yao.py output-review-kit`
- write_template: `python3 scripts/adjudicate_output_review.py --write-template`
- import_decisions: `python3 scripts/yao.py output-review-import --input <reviewer-decisions.json> --blind-review-attested --run-adjudication`
- adjudicate: `python3 scripts/yao.py output-review`
- refresh_review_studio: `python3 scripts/yao.py review-studio .`

#### Required Fields

- winner_variant: A or B after reading only the blind review pack.
- confidence: Optional number from 0 to 1.
- reason: Required rationale; do not reveal baseline or with-skill labels before adjudication.
- reviewer: Human reviewer name or review group at the decision-file top level.
- reviewed_at: Review date or timestamp at the decision-file top level.
- reviewer_attestation.blind_review_completed_before_answer_key: True only after the reviewer has completed choices before opening the answer key.
- reviewer_attestation.answer_key_not_opened_before_decisions: True only when the answer key was not opened before decisions were recorded.

#### Privacy Contract

- Do not paste raw private user data into the decision reason.
- Do not open the answer key before reviewer choices are recorded.
- Leave winner_variant blank when the reviewer is not ready to decide.

## Next Fixes

- Keep the blind review pack separate from the answer key until decisions are recorded.
- Treat disagreement cases as prompts for rubric tuning or output improvement.
- Add model-executed holdout runs after this human adjudication harness is stable.
