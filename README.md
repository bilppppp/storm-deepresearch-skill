# STORM DeepResearch Skill

`storm-deepresearch-skill` 是一个证据驱动的 governed 深度研究 harness。它保留 STORM 的多视角提问思想，但不把角色观点当证据：视角只生成检索问题，事实必须进入来源登记和 Claim-Evidence 账本，每个阶段必须写入可重算 receipt，最终从单一 `report.md` 渲染并验证 Markdown、HTML 和 PDF。

当前版本：`1.1.0`

## 能做什么

- 研究报告、文献综述、行业分析和决策简报。
- 基于用户文件、URL 或封闭语料完成可审计研究。
- 区分事实、推断、建议、矛盾和未知项。
- 生成来源登记、STORM tasklets、findings pool、证据账本、报告映射和验证报告。
- 通过 `storm_research.py` 的 init、plan、ingest、findings、evidence、draft、review、render、validate、release 阶段推进，关键阶段由 receipt chain 约束，findings 作为 evidence 的必要前提被绑定进 evidence receipt。
- 以 `report.md` 为唯一内容真源，导出一致的 HTML/PDF。
- 默认中文完整研究为 `8000–10000` 正文字符；输入长度只改变检索量，不会自动把成品压缩成摘要。
- 强制将已回答的 STORM 问题和材料性 Claim 映射到 `research-plan.report_outline`，避免研究停留在中间产物。
- 对空证据、假引用、过期证据、占位符、本地路径泄漏、缺失 PDF 和格式漂移返回非零退出码。
- 默认在用户工作区的 `output/storm-deepresearch/` 下创建独立运行目录；已存在目标、路径逃逸和符号链接逃逸都会失败。
- 初始化不会覆盖既有研究包；来源登记采用保留既有 ID 的原子合并，研究账本不能被重新初始化截断。
- 公开 release 需要通过离线 validation、Yao Trust 报告、Registry hash 匹配、必要的来源再验证和 human approval。

它不适合快速事实查询、简单摘要、无证据角色扮演或个性化医疗、法律、投资建议。

## 运行要求

- Python 3.11+
- Pandoc（Markdown 到语义 HTML）
- WeasyPrint 或 Chrome/Chromium（HTML 到 PDF）
- `uv` 可选，但以下安装命令已在本项目验证

## 安装

在项目根目录执行：

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements-dev.lock
pandoc --version
.venv/bin/python scripts/run_checks.py --all
```

运行时依赖使用 `requirements.lock`；开发、测试和 Yao 检查使用 `requirements-dev.lock`。`requirements-ci.txt` 是供供应链扫描使用的精确依赖清单。

把此目录放入或链接到 Agent 的 skills 根目录后，通过 `$storm-deepresearch-skill` 显式调用。不同宿主的技能目录并不统一；以宿主的本地 skill 安装说明为准，不要复制 `.venv`、`dist` 或生成的研究输出。

语义契约覆盖 OpenAI、Claude、Agent Skills、VS Code 和 generic。`agent-skills` 是中立源格式；分发阶段为 OpenAI、Claude、VS Code 和 generic 生成适配器。

## 快速开始

所有新自动化都应调用 `scripts/storm_research.py`。旧的 `init_research_package.py`、`normalize_retrieval.py`、`merge_claim_ledger.py`、`export_report.py` 保留为兼容或内部 worker，不再是推荐入口。

```bash
SKILL_ROOT=/path/to/storm-deepresearch-skill
PY="$SKILL_ROOT/.venv/bin/python"
WORKSPACE=/path/to/user-workspace
```

宿主 agent 不应生成包含大段转录文本、报告正文或 JSON 块的单体 Python runner。大文本必须先写入 UTF-8 文件、JSON 或 JSONL，再由下面的分阶段命令读取。若宿主确实生成了临时 runner，必须先用 guard 运行；guard 会在执行前编译检查、实时输出，并在超时后终止子进程：

```bash
"$PY" "$SKILL_ROOT/scripts/agent_run_guard.py" --timeout 1800 /path/to/host_runner.py
```

如果 guard 输出 `RUNNER_SYNTAX_ERROR`，不要继续运行该 runner；这通常表示引号、编码或大段文本替换已经损坏。`RUNNER_TIMEOUT` 表示某个子命令超时，需用 `storm_research.py status "$RUN_DIR"` 查看最后通过的 receipt，再从对应阶段修复。

### 1. Init

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" init \
  --topic "AI Agent Skill 的工程化评估" \
  --question "怎样证明一个 Skill 的输出可靠、可复现且可发布？" \
  --workspace "$WORKSPACE" \
  --output research-run
```

该命令创建 `$WORKSPACE/output/storm-deepresearch/research-run/`、`work/generations/g0001/inputs/brief.json` 和 `state/generations/g0001/receipts/00-init.json`。目标一旦存在会以退出码 `4` 停止。

```bash
RUN_DIR="$WORKSPACE/output/storm-deepresearch/research-run"
```

中文 full dossier 默认为 `8000–10000` characters，英文为 `3500–7000` words。只有用户明确要求简报时才使用 `--depth-level briefing`，并且必须同时提供 `--briefing-reason "用户明确要求简报的证据"`；宿主默认降级到 briefing 会在 init 阶段失败。

默认 `storm_lens_mode` 是 `advisory`：必须遵循 STORM Lens Prompt Pack，但不额外要求 lens artifacts。需要证明四个 STORM prompt 按阶段发生时，在 init 加 `--storm-lens-mode strict`；strict run 会要求四个 `storm-lens-*.json` helper artifact，并把它们绑定进后续 receipts。

### 2. Plan

宿主或 agent 先生成 `research-plan.json` 和 `source-plan.json`，再提交：

```bash
# strict mode only: register Prompt 1 artifact before plan
"$PY" "$SKILL_ROOT/scripts/storm_research.py" lens-perspectives "$RUN_DIR" \
  --input-json storm-lens-perspectives.json
```

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" plan "$RUN_DIR" \
  --plan-json research-plan.json \
  --source-plan-json source-plan.json
```

`plan` 必须覆盖 STORM 多视角问题、source classes、停止条件和 `report_outline` 所需的问题闭环。full dossier 且非 `closed_corpus` 时，source plan 不能只依赖用户转录、封闭语料或本地材料：至少一半问题要要求外部 source classes，且 `retrieval_budget.max_sources` 不得低于 `6`。成功后会自动生成 `research/storm-tasklets.jsonl`，每个 STORM 问题变成后续 findings 的最小执行单元。

生成 plan 时先使用 [STORM Lens Prompt Pack](references/storm-lens-prompt-pack.md)：Prompt 1 只生成视角、研究问题和证据需求；检索和 findings 完成后再用 Prompt 2 做证据支持的矛盾地图；Prompt 3 只在 findings 和矛盾处理后生成 `report_outline`；Prompt 4 只在 draft 后做 red-team review。不要先把四条 STORM prompt 一次性跑完再联网搜索。

### 3. Ingest

内置脚本不会主动联网。宿主检索结果必须符合 `schemas/retrieval-record.schema.json`，包含真实 URL 或闭合语料文件引用、快照 hash、locator 和 excerpt：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" ingest "$RUN_DIR" \
  --input-jsonl retrieval-records.jsonl
```

`host` 是默认检索模式；`provider` 只在用户明确配置凭证时使用；`closed_corpus` 只使用指定文件或 URL。占位符域名、`.internal` 伪来源、无快照、secondary-as-primary、Wikipedia 伪装成 primary/Tier A 和 blanket Tier A 会在 ingest 阶段失败。full dossier 的外部研究至少需要 `6` 个非用户、非百科的外部来源；Wikipedia 可作背景线索，但不能替代 deep research。

### 4. Findings

检索后先提交 findings pool，把每个 tasklet 的可用发现、来源和候选 Claim 绑定起来：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" findings "$RUN_DIR" \
  --findings-jsonl findings.jsonl
```

full dossier 要求每个 `storm-tasklets.jsonl` 里的 tasklet 至少有一个 `usable` finding。后续 evidence 阶段会要求材料性 Claim 链接到 usable finding，且 finding 与 Claim 必须共享 supporting source。

strict mode 下，findings 后必须先注册 Prompt 2 和 Prompt 3 artifacts，不能把 contradictions、uncertainties、outline 和 claims 一次性批处理进 evidence：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" lens-conflicts "$RUN_DIR" \
  --input-json storm-lens-conflicts.json

"$PY" "$SKILL_ROOT/scripts/storm_research.py" lens-outline "$RUN_DIR" \
  --input-json storm-lens-outline.json
```

### 5. Evidence

提交 Claim、矛盾、不确定性和报告大纲：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" evidence "$RUN_DIR" \
  --claims claims.jsonl \
  --contradictions contradictions.json \
  --uncertainties uncertainties.json \
  --report-outline report-outline.json
```

材料性事实必须有可定位证据；推断必须指出已支持前提；建议必须写明适用条件和取舍。涉及阿伦特、福柯、康德、马克思、文化工业、生命政治等理论框架的 material claim，必须由 academic、book、expert、peer_reviewed_paper 或 secondary_synthesis 类型来源支撑，用户观后感、转录文本或百科页面不能单独闭合。full dossier 至少需要 5 个视角、10 个问题、6 个 evidence-planned sections 和 12 个 material claims。

提交完整 evidence 前，可以先定位理论来源问题；该命令只诊断、不写 receipt：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" evidence "$RUN_DIR" \
  --claims claims.jsonl \
  --preflight-theory
```

### 6. Draft

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" draft "$RUN_DIR" \
  --draft-md draft.md \
  --paragraph-map-jsonl paragraph-map.jsonl
```

`draft.md` 不能手写 References。每个 factual paragraph 必须映射到 Claim、source 和 citation key；脚本会从 source register 生成 References。

反复调正文长度和 paragraph-map 时先跑 preflight；它会输出正文计数、段落预览、citation keys 和可定位错误，不写 `40-draft.json`：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" draft "$RUN_DIR" \
  --draft-md draft.md \
  --paragraph-map-jsonl paragraph-map.jsonl \
  --preflight
```

### 7. Review

独立审阅者输出 claim reviews、paragraph audit、修订文档和 revision map。full dossier 还必须提供 fact checks、conflict reviews 和 draft audit：

```bash
# strict mode only: register Prompt 4 artifact after draft and before review
"$PY" "$SKILL_ROOT/scripts/storm_research.py" lens-review "$RUN_DIR" \
  --input-json storm-lens-red-team.json
```

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" review "$RUN_DIR" \
  --claim-reviews claim-reviews.jsonl \
  --report-audit report-audit.jsonl \
  --fact-checks fact-checks.jsonl \
  --conflict-reviews conflict-reviews.jsonl \
  --draft-audit draft-audit.jsonl \
  --revised-md report.md \
  --revised-paragraph-map-jsonl reviewed-paragraph-map.jsonl \
  --revision-map revision-map.json
```

### 8. Render

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" render "$RUN_DIR" \
  --template "$SKILL_ROOT/templates/report.html.j2"
```

完整模式必须生成 PDF。full dossier 不能在 PDF 失败后通过 `amend` 降级到 reduced output。

### 9. Validate

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" validate "$RUN_DIR"
```

成功时写入 `state/generations/g0001/receipts/70-validation.json`。失败不会写通过 receipt，也不会把 `validation-report.json` 伪装成成功。

验证或 receipt 失败后，可以生成结构化修复计划；它只写 `current/repair-plan.json`，不写 receipt：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" repair-plan "$RUN_DIR"
```

本地使用可把已验证成品收集到浅层目录；`collect` 需要通过 validation，只复制 `report.md`、HTML、PDF 和 validation report，不替代 public `release`：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" collect "$RUN_DIR" \
  --to "$WORKSPACE/output/storm-deepresearch/final-report"
```

### 10. Release

公开发布需要宿主控制的 Trust evidence、Registry metadata、human approval，且当前性过期来源需要 re-verification records：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" release "$RUN_DIR" \
  --trust /path/to/host-trust-evidence.json \
  --registry /path/to/registry-package.json \
  --approval /path/to/human-approval.json \
  --reverification /path/to/reverification-records.jsonl
```

`release/` 只包含 allowlist 成品文件；`work/`、`state/`、retrieval inputs、claim updates 和 amendment inputs 不会进入发布包。

退出码：

| 退出码 | 含义 |
|---:|---|
| `0` | 全部必需检查通过 |
| `4` | 文件、JSON Schema 或跨文件契约失败 |
| `5` | 来源、证据闭合、时效性或矛盾处理失败 |
| `6` | 模板、HTML/PDF、指纹或跨格式一致性失败 |
| `7` | 本地路径、内部 ID 或公共输出安全失败 |
| `8` | receipt chain、阶段前置条件或重试/修订边界失败 |
| `9` | Trust、Registry、human approval、re-verification 或 release allowlist 失败 |

路径、覆盖和账本规则见 [输出路径策略](references/output-path-policy.md)。HTML、PDF、审计 Markdown 和验证报告属于派生产物，可以在包内重新生成；两个 JSONL 权威账本都必须通过保留既有记录的合并器更新。

## 输出结构

完整契约见 [示例输出树](examples/example-output-tree.md)。权威文件位于 `work/generations/g0001/` 和 `state/generations/g0001/receipts/`；根目录 `brief.json` 与 `current/` 是只读便利视图。

核心文件包括：

- `work/generations/g0001/inputs/brief.json`：范围、时效、检索和输出模式。
- `work/generations/g0001/artifacts/research/research-plan.json`：视角、问题、预算和停止条件。
- `work/generations/g0001/artifacts/research/storm-tasklets.jsonl`：每个 STORM 问题对应的执行单元。
- `work/generations/g0001/artifacts/research/storm-lens-*.json`：strict mode 下四个 STORM prompt 的 phase-bound helper artifact。
- `work/generations/g0001/artifacts/research/storm-findings-pool.jsonl`：可用发现、来源、locator 和候选 Claim 绑定。
- `work/generations/g0001/artifacts/research/finding-coverage.json`：tasklet 与 finding 覆盖摘要。
- `work/generations/g0001/artifacts/research/report-outline.json`：问题/Claim 到章节及篇幅预算的闭环。
- `work/generations/g0001/artifacts/research/source-register.jsonl`：来源权威账本。
- `work/generations/g0001/artifacts/research/claim-evidence-ledger.jsonl`：事实、推断、建议和证据状态。
- `work/generations/g0001/artifacts/research/reviewed-paragraph-map.jsonl`：公共报告段落到内部 claim/source/citation 的映射。
- `work/generations/g0001/artifacts/report.md`：唯一内容真源。
- `work/generations/g0001/artifacts/exports/report.html`、`report.pdf`：确定性派生物。
- `work/generations/g0001/artifacts/validation/render-manifest.json`：跨格式哈希和章节指纹。
- `work/generations/g0001/artifacts/validation/validation-report.json`：机器可读验证判定。
- `state/generations/g0001/receipts/*.json`：不可跳过的阶段 receipt chain。
- `current/repair-plan.json`：失败后可选生成的结构化修复计划，不是权威 receipt。
- `release/`：通过 Trust 和 human approval 后生成的严格 allowlist 发布投影。

可直接查看通过严格验证的 [代表性研究包](examples/validated-output/) 和 [PDF](examples/validated-output/exports/report.pdf)。

## 开发与发布门禁

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/run_checks.py --all
```

`--all` 运行单元测试、编译检查、schema 检查和 Yao Meta Skill 验证。Yao 的 Output Lab、Trust、Conformance、Packaging 和安装模拟证据保存在 `reports/`；最终 release 还必须运行 `storm_research.py release` 并绑定外部 trust、registry、re-verification 和 human approval。发布步骤见 [发布检查表](docs/release-checklist.md)。

Yao 生成 ZIP 后、执行 package verification 前，先净化归档中的本机路径：

```bash
.venv/bin/python scripts/sanitize_release_archive.py \
  dist/storm-deepresearch-skill.zip \
  --redact-root "$PWD"
```

该命令保留 ZIP 结构和二进制条目，将项目根路径替换为 `$SKILL_ROOT`、用户主目录替换为 `$HOME`；存在不安全条目或未完成净化时非零退出。

## 版本迁移与回滚

0.4.0 到 1.0.0 的 governed harness、receipt chain、recovery commands 和 legacy import 变化见 [迁移指南](docs/migration-v0.4-to-v1.0.md)。更早版本的迁移文档保留在 `docs/`。

## 设计来源

- STORM：多视角问题发现、检索、信息整理和带引用写作。
- DeepResearch：来源优先、拒绝幻觉、显式不确定性和证据闭合。
- `yao-tutorial-skill`：成品化交付与多格式输出。
- Yao Meta Skill：接口、schema、评估、治理、打包与安装门禁。
