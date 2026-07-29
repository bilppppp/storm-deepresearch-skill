# STORM DeepResearch 使用手册

本文面向需要直接运行或集成 `storm-deepresearch-skill` 的开发者和 Agent 宿主。README 负责快速入口；本文说明当前 `3.1.0` CLI 的完整本地研究流程。字段定义以 `schemas/` 为准，证据和质量判断以 `references/` 为准。

## 1. 环境与基本变量

运行要求：

- Python 3.11+
- Pandoc：Markdown 转语义 HTML
- WeasyPrint 或 Chrome/Chromium：HTML 转 PDF
- `uv`：推荐，但不是运行时强制依赖

```bash
SKILL_ROOT=/path/to/storm-deepresearch-skill
PY="$SKILL_ROOT/.venv/bin/python"
WORKSPACE=/path/to/user-workspace
```

运行时依赖位于 `requirements.lock`；开发和完整离线检查使用 `requirements-dev.lock`；`requirements-ci.txt` 用于供应链扫描。

所有新自动化都应调用 `scripts/storm_research.py`。不要把大段正文、转录或 JSON 嵌入临时 Python runner；先写入 UTF-8 文件、JSON 或 JSONL，再交给分阶段 CLI。确需运行宿主脚本时，可使用：

```bash
"$PY" "$SKILL_ROOT/scripts/agent_run_guard.py" \
  --timeout 1800 /path/to/host_runner.py
```

## 2. 选择研究模式

| Profile | 用途 |
| --- | --- |
| `default_full_dossier` | 默认完整研究；strict STORM P1–P4、学术基线、独立外审、Markdown/HTML/PDF。 |
| `critique_deepresearch` | 电影、书、文章或观点评论；额外覆盖理论、反证、接受史和历史比较。 |
| `closed_corpus` | 只使用用户提供的文件或 URL；证据不足时停止，不用模型记忆补事实。 |
| `briefing` | 用户明确要求短简报时使用，并提供 `--briefing-reason`。 |

用户未选择或明确要求默认时，使用 `default_full_dossier`。不要把完整研究自动降级为 briefing。已有 run 使用 `status`、`explain` 和恢复命令，不要重新 `init`。

## 3. 创建 Run

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" init \
  --topic "研究主题" \
  --question "需要回答的核心问题" \
  --workspace "$WORKSPACE" \
  --output research-run \
  --research-profile default_full_dossier \
  --profile-selection-mode user_requested_default \
  --profile-selection-evidence "用户明确要求默认完整研究"

RUN_DIR="$WORKSPACE/output/storm-deepresearch/research-run"
```

`init` 只创建新目录；目标已存在时失败，不覆盖或续写旧 run。中文 full dossier 默认要求 `8000–10000` 净正文字符，参考文献、链接地址、引用标记和 Markdown 控制符不计入。

## 4. P1 与研究计划

先生成至少五个真正不同的视角、研究问题和来源计划。视角只负责发现问题，不提供事实。

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" lens-perspectives "$RUN_DIR" \
  --input-json storm-lens-perspectives.json

"$PY" "$SKILL_ROOT/scripts/storm_research.py" plan "$RUN_DIR" \
  --plan-json research-plan.json \
  --source-plan-json source-plan.json
```

完整研究至少需要十个问题、六个 evidence-planned sections，并为每类来源声明 `can_prove` 与 `cannot_prove`。外部 full dossier 还要规划跨至少两个学术发现面的 academic baseline。

## 5. 检索、捕获与 Ingest

仓库脚本不主动联网。宿主负责搜索和捕获，再把三类记录写入符合 `schemas/retrieval-record.schema.json` 的 JSONL：

- `search_run`：查询、别名、检索面、pass kind、结果数和原始结果快照。
- `candidate`：候选、纳入/排除、书目身份、resolver 结果和版本家族。
- `capture`：真实 URL 或文件、snapshot、locator、excerpt 和证据强度上限。

单来源和批量辅助命令：

```bash
SOURCE_URL=/replace/with/the/actual/captured/url

"$PY" "$SKILL_ROOT/scripts/storm_research.py" capture-source "$RUN_DIR" \
  --query-id Q001 \
  --url "$SOURCE_URL" \
  --snapshot captured-page.html \
  --title "Source title" \
  --publisher "Publisher" \
  --content-excerpt "Exact excerpt present in the snapshot" \
  --source-type secondary_synthesis \
  --primary-class secondary \
  --reliability-tier B \
  --reliability-notes "Why this source supports the scoped conclusion"

"$PY" "$SKILL_ROOT/scripts/storm_research.py" ingest-dir "$RUN_DIR" \
  --input-dir captured-sources \
  --to retrieval-inputs.jsonl
```

提交完整检索记录：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" ingest "$RUN_DIR" \
  --input-jsonl retrieval-records.jsonl
```

Matched academic resolver 必须绑定 Crossref、OpenAlex、Semantic Scholar、PubMed 或 arXiv 的提供方原始响应；模型整理的 DOI/title/year 小对象不是 resolver 证据。搜索卡片和 snippet 可发现候选，但不能闭合 material Claim。

## 6. Findings、P2、P3 与 Evidence

Findings 把 tasklet、来源、locator、限制和候选 Claim 连接起来：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" findings "$RUN_DIR" \
  --findings-jsonl findings.jsonl

"$PY" "$SKILL_ROOT/scripts/storm_research.py" lens-conflicts "$RUN_DIR" \
  --input-json storm-lens-conflicts.json

"$PY" "$SKILL_ROOT/scripts/storm_research.py" lens-outline "$RUN_DIR" \
  --input-json storm-lens-outline.json
```

P2 的每个 blind spot 和 resolver question 必须处置为 `new_retrieval`、`uncertainty` 或 `out_of_scope`。`new_retrieval` 会阻止 P3，需用 `amend` 建立新 generation 后补检索。

提交 Claims、矛盾、不确定性和报告提纲：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" evidence "$RUN_DIR" \
  --claims claims.jsonl \
  --contradictions contradictions.json \
  --uncertainties uncertainties.json \
  --report-outline report-outline.json
```

完整研究至少需要 12 个 material Claims。事实需要直接、可定位证据；推断需要已支持前提；建议需要适用条件和取舍。“未发现证据”类 material Claim 还要提交 `--absence-searches absence-searches.jsonl`。

方法适配先看具体结论，再看来源能力：

- 官方资料支持已记录的规则、功能和立场，不单独证明真实效果。
- 用户经历支持个案，不证明发生率或普遍效果。
- 新闻支持“被报道”，不替代原始证据或因果证明。
- 调查和观察性研究通常支持样本范围内的比例或关联，不自动支持因果。
- 实验、准实验和综述仍受识别假设、样本、随访、异质性和适用范围限制。
- 日期未知只触发非阻塞语义风险；已知过期材料不能支持明确当前事实。

完整决策表见[来源与证据策略](../references/source-and-evidence-policy.md)。

## 7. Draft 与段落映射

每个事实段落都要映射到 Claim、source 和 citation key。报告正文不要手写 References；脚本会从 source register 生成。

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" build-paragraph-map "$RUN_DIR" \
  --draft-md draft.md \
  --sidecar-jsonl paragraph-sidecar.jsonl \
  --to paragraph-map.jsonl

"$PY" "$SKILL_ROOT/scripts/storm_research.py" draft "$RUN_DIR" \
  --draft-md draft.md \
  --paragraph-map-jsonl paragraph-map.jsonl \
  --preflight

"$PY" "$SKILL_ROOT/scripts/storm_research.py" draft "$RUN_DIR" \
  --draft-md draft.md \
  --paragraph-map-jsonl paragraph-map.jsonl
```

`--preflight` 只检查正文长度、段落、Claim 和引用绑定，不写 draft receipt。

## 8. P4 与独立外审

P4 检查具体 Claim 或句子的结论形态、方法、样本、时间、地域、外推和反证。关闭或明确 waiver 所有 P4 修复动作后，再冻结候选：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" lens-review "$RUN_DIR" \
  --input-json storm-lens-red-team.json

"$PY" "$SKILL_ROOT/scripts/storm_research.py" review-prepare "$RUN_DIR" \
  --candidate-md report.md \
  --candidate-map reviewed-paragraph-map.jsonl \
  --revision-map revision-map.json
```

`review-prepare` 会生成不可变的 `review-candidate/`、可读 `review-context.md` 和 `review-request.json`，并返回 `author_may_continue=false`。此后必须启动真正隔离的外部模型入口或交给人工 reviewer；作者不能制造 review provenance。

Reviewer 将以下文件写入同一个、同时位于 run 和 Skill 之外的提交目录：

- `claim-reviews.jsonl`
- `report-audit.jsonl`
- `fact-checks.jsonl`
- `conflict-reviews.jsonl`
- `draft-audit.jsonl`
- `reviewer-transcript.txt`
- `reviewer-execution.json`

外部执行元数据只填写执行类型、reviewer 身份、execution ID，以及外部模型的 provider/model/runner。context ID、时间、hash、lineage 和 attestation 由 harness 生成。

```bash
REVIEW_SUBMISSION=/path/outside/run-and-skill/review-submission

"$PY" "$SKILL_ROOT/scripts/storm_research.py" review "$RUN_DIR" \
  --claim-reviews "$REVIEW_SUBMISSION/claim-reviews.jsonl" \
  --report-audit "$REVIEW_SUBMISSION/report-audit.jsonl" \
  --fact-checks "$REVIEW_SUBMISSION/fact-checks.jsonl" \
  --conflict-reviews "$REVIEW_SUBMISSION/conflict-reviews.jsonl" \
  --draft-audit "$REVIEW_SUBMISSION/draft-audit.jsonl" \
  --revised-md report.md \
  --revised-paragraph-map-jsonl reviewed-paragraph-map.jsonl \
  --revision-map revision-map.json \
  --review-provenance "$REVIEW_SUBMISSION/reviewer-execution.json" \
  --review-transcript "$REVIEW_SUBMISSION/reviewer-transcript.txt"
```

Material Claim 或关键段落的实质证据问题会阻止 review；局部、非 material 问题保留为 warning 和 required action，不阻止整份报告。

## 9. Render、Validate 与本地交付

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" render "$RUN_DIR" \
  --template "$SKILL_ROOT/templates/report.html.j2"

"$PY" "$SKILL_ROOT/scripts/storm_research.py" validate "$RUN_DIR"

"$PY" "$SKILL_ROOT/scripts/storm_research.py" status "$RUN_DIR"
```

只有 `status.local_delivery_ready=true` 才表示 full dossier 已完成本地验证。`evidence_ready`、`drafted`、`reviewed` 和 `rendered` 都是中间状态。

将最终文件复制到浅层交付目录：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" collect "$RUN_DIR" \
  --to "$WORKSPACE/output/storm-deepresearch/final-report"
```

`collect` 只复制通过验证的 Markdown、HTML、PDF 和 validation report。不要直接写 harness-owned `current/`，也不要把 `_build` 文件作为最终交付。

## 10. 公开 Release

本地查看和交付 Markdown/HTML/PDF 不需要人工签署。只有要创建公开研究发布包时才运行：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" release "$RUN_DIR" \
  --trust /path/to/host-trust-evidence.json \
  --registry /path/to/registry-package.json \
  --approval /path/to/human-approval.json \
  --reverification /path/to/reverification-records.jsonl
```

Release 要求 validation、Trust、Registry hash、必要的来源再验证和 human approval。普通 Git commit/push、Skill ZIP 构建和本地 `collect` 不使用这套研究报告 release 签署。

## 11. 状态、失败与恢复

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" status "$RUN_DIR"
"$PY" "$SKILL_ROOT/scripts/storm_research.py" explain "$RUN_DIR"
"$PY" "$SKILL_ROOT/scripts/storm_research.py" doctor "$RUN_DIR"
"$PY" "$SKILL_ROOT/scripts/storm_research.py" repair-plan "$RUN_DIR"
```

- `retry`：仅重试当前失败或待处理阶段。
- `amend`：经批准后创建新 generation，不改写旧 receipt。
- `repair-plan`：生成修复建议，不创建通过 receipt。
- 旧 run 不静默迁移；使用创建该 run 的版本解释或按迁移指南处理。

退出码：

| Code | 含义 |
| ---: | --- |
| `0` | 必需检查通过 |
| `4` | 文件、Schema 或跨文件契约失败 |
| `5` | 来源、证据闭合、时效或矛盾处理失败 |
| `6` | 模板、HTML/PDF、指纹或格式一致性失败 |
| `7` | 路径、内部 ID、凭证或公共输出安全失败 |
| `8` | receipt chain、阶段前置或修订边界失败 |
| `9` | Trust、Registry、approval、re-verification 或 release allowlist 失败 |

## 12. 核心输出

权威状态按 generation 保存：

```text
work/generations/g0001/inputs/
work/generations/g0001/artifacts/
state/generations/g0001/receipts/
```

常用文件：

- `research/retrieval-audit.jsonl`：检索、筛选、resolver、版本家族和 capture 审计。
- `research/storm-findings-pool.jsonl`：tasklet 到 finding、来源和 Claim 的桥接。
- `research/claim-evidence-ledger.jsonl`：Claim 权威账本。
- `research/review-request.json` 与 `review-candidate/review-context.md`：独立外审交接。
- `report.md`：唯一公共内容真源。
- `exports/report.html`、`exports/report.pdf`：派生格式。
- `validation/validation-report.json`：机器可读验证结果。
- `state/generations/g0001/receipts/*.json`：阶段 receipt chain。

完整路径规则见[输出路径策略](../references/output-path-policy.md)。

## 13. 开发、测试与打包

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/run_checks.py --all
.venv/bin/python scripts/run_checks.py --dist
```

- `--all`：单元测试、编译、schema、Yao validate/lint/governance/resource-boundary。
- `--dist`：生成并验证平台 adapter 和 `dist/storm-deepresearch-skill.zip`。
- 公开某次研究报告包使用 `storm_research.py release`，不要与 Skill ZIP 打包混为一条流程。

正式打包检查见[发布检查表](release-checklist.md)。

## 14. 规则与迁移索引

- [研究协议](../references/research-protocol.md)
- [质量门禁](../references/quality-gates.md)
- [来源与证据策略](../references/source-and-evidence-policy.md)
- [检索适配器](../references/retrieval-adapters.md)
- [Claim–Evidence 策略](../references/claim-evidence-policy.md)
- [STORM Lens Prompt Pack](../references/storm-lens-prompt-pack.md)
- [报告写作规则](../references/report-writing.md)
- [导出流程](../references/export-workflow.md)
- [输出路径策略](../references/output-path-policy.md)
- [2.x 到 3.0 迁移](migration-v2-to-v3.md)
- [1.1 到 2.0 迁移](migration-v1.1-to-v2.0.md)
