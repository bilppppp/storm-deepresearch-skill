# STORM Article Workflow Mapping

The motivating article contributes four useful reasoning stages. This Library keeps those stages but replaces prompt-chain memory with auditable artifacts. The reusable stage prompts live in [storm-lens-prompt-pack.md](storm-lens-prompt-pack.md).

| Article stage | Library artifact and phase | Preserved idea | Safety and depth upgrade |
|---|---|---|---|
| Multi-perspective scan | `research-plan.json`, `perspective-questions.md`; protocol phases 2-3 | Practitioner, academic, skeptic, incentive, and historical lenses expose different questions | Personas never supply evidence; retrieved or user-approved sources answer the questions |
| Contradiction map | `contradiction-ledger.json`, `contradiction-map.md`; phase 5 | Direct conflicts, consensus, blind spots, and resolution questions are explicit | Agreement is not treated as truth; every conclusion still requires Claim-Evidence closure |
| Synthesis | `research-plan.report_outline`, `report-claim-map.json`, `report.md`; phase 6 | Rank findings, connect perspectives, identify implications and frontier questions | Every answered question and material claim is assigned to an evidence-led section and length budget |
| Peer review | `peer-review.md`, uncertainty ledger, strict validators; phase 7 | Confidence, weakest link, bias, missing perspective, and required revision | Self-review cannot certify itself; deterministic gates and evidence locators decide release readiness |

## What is intentionally not copied

- Do not ask simulated experts for evidence from model memory.
- Do not infer truth from five-way agreement.
- Do not turn confidence scores into factual support.
- Do not stop at a short briefing when the brief promises a full dossier.

The four prompts remain the conceptual skeleton and should run at their proper phases: perspective discovery before retrieval, contradiction mapping after findings, synthesis after conflicts, and red-team review after draft. Retrieval, ledgers, report outlining, export, and non-zero validation make that skeleton a reusable research system.
