# STORM DeepResearch Skill

`storm-deepresearch-skill` 是一个证据驱动的 governed 深度研究 harness。它保留 STORM 的多视角提问思想，但不把角色观点当证据：视角只生成检索问题，事实必须进入来源登记和 Claim-Evidence 账本，每个阶段必须写入可重算 receipt，最终从单一 `report.md` 渲染并验证 Markdown、HTML 和 PDF。

当前版本：`3.1.0`

## 能做什么

- 研究报告、文献综述、行业分析和决策简报。
- 基于用户文件、URL 或封闭语料完成可审计研究。
- 区分事实、推断、建议、矛盾和未知项。
- 生成来源登记、STORM tasklets、findings pool、证据账本、报告映射和验证报告。
- 通过 `storm_research.py` 的 init、plan、ingest、findings、evidence、draft、review、render、validate、release 阶段推进，关键阶段由 receipt chain 约束，findings 作为 evidence 的必要前提被绑定进 evidence receipt。
- 以 `report.md` 为唯一内容真源，导出一致的 HTML/PDF。
- 默认中文完整研究为 `8000–10000` 净正文字符；参考文献、脚注键、链接地址、图片标记和 Markdown 控制符不计入字数；输入长度只改变检索量，不会自动把成品压缩成摘要。
- full dossier 必须先冻结 review candidate，再由外部模型会话或人工 reviewer 提交可重算 provenance；`independent: true` 或两个不同字符串不再足以通过。
- 同一来源可以回答多个 query；Source 去重与问题覆盖分离，Claim 强度不能超过精确 locator 对应的 capture ceiling。
- 先判断具体 Claim 是记录事实、关联、因果、外推、推断还是建议，再检查来源类型、研究方法、样本、时间、地域和捕获层级是否足以支持；Tier、来源声望和论文数量不能升级方法本身的证明能力。
- 外部 full dossier 强制完成 academic baseline：先记录搜索运行，再筛选候选文献、核验 bibliographic 身份、归并论文版本，最后捕获可引用正文。
- 用户语料采用 corpus-seeded 检索，不会替代学术基线；未闭合问题必须进入 gap-fill 或不确定性账本。
- “未发现证据”类 material Claim 必须声明 `absence_search` 并提交别名、检索面、结果数和来源快照。
- 强制将已回答的 STORM 问题和材料性 Claim 映射到 `research-plan.report_outline`，避免研究停留在中间产物。
- 对空证据、假或不可检查的来源、material Claim 无证据、关键引用不支持、已知过期材料支撑明确当前事实、危险结论越界、凭证或本地路径泄漏、缺失 PDF 和格式漂移返回非零退出码。仅因 adapter 没观察到发布日期不会失败。
- 默认在用户工作区的 `output/storm-deepresearch/` 下创建独立运行目录；已存在目标、路径逃逸和符号链接逃逸都会失败。
- 初始化不会覆盖既有研究包；来源登记采用保留既有 ID 的原子合并，研究账本不能被重新初始化截断。
- 公开研究包 release 需要通过离线 validation、Yao Trust 报告、Registry hash 匹配、必要的来源再验证和 human approval；本地 `render`、`validate`、查看 HTML/PDF 和普通 Git 提交不需要真人 release 签署。
- `default_full_dossier` 的正常本地终点是 `status.local_delivery_ready=true`。`evidence_ready`、`drafted`、`reviewed` 和 `rendered` 都是中间状态，不能宣告最终交付。

它不适合快速事实查询、简单摘要、无证据角色扮演或个性化医疗、法律、投资建议。

## 运行要求

- Python 3.11+
- Pandoc（Markdown 到语义 HTML）
- WeasyPrint 或 Chrome/Chromium（HTML 到 PDF）
- `uv` 可选，但以下安装命令已在本项目验证

## 安装

### 手动安装

先把仓库克隆到本地，然后在项目根目录执行：

```bash
git clone https://github.com/bilppppp/storm-deepresearch-skill.git
cd storm-deepresearch-skill
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements-dev.lock
pandoc --version
.venv/bin/python scripts/run_checks.py --all
```

运行时依赖使用 `requirements.lock`；开发、测试和 Yao 检查使用 `requirements-dev.lock`。`requirements-ci.txt` 是供供应链扫描使用的精确依赖清单。

把此目录放入或链接到 Agent 的 skills 根目录后，通过 `$storm-deepresearch-skill` 显式调用。不同宿主的技能目录并不统一；以宿主的本地 skill 安装说明为准，不要复制 `.venv`、`dist` 或生成的研究输出。

语义契约覆盖 OpenAI、Claude、Agent Skills、VS Code 和 generic。`agent-skills` 是中立源格式；分发阶段为 OpenAI、Claude、VS Code 和 generic 生成适配器。

### 交给 Agent 安装

也可以把 GitHub 链接直接交给 Codex、Claude Code、OpenCode 或其他支持本地 skills 的 agent，让宿主按自己的规则安装。可直接使用下面这段提示词：

```text
帮我安装 https://github.com/bilppppp/storm-deepresearch-skill.git 作为本地 agent skill。

要求：
1. 先 clone 仓库到你当前宿主推荐的 skills 目录；如果宿主没有固定 skills 目录，请先告诉我你准备放到哪里。
2. 不要复制或提交 .venv、dist、output、work、state、release、__pycache__、.pytest_cache 等生成物。
3. 在 skill 根目录创建 Python 3.11 虚拟环境，并安装依赖：
   uv venv --python 3.11 .venv
   uv pip install --python .venv/bin/python -r requirements-dev.lock
4. 检查 Pandoc 是否可用：pandoc --version。若缺失，请告诉我需要先安装 Pandoc；full PDF 还需要 WeasyPrint 或 Chrome/Chromium。
5. 运行验证：.venv/bin/python scripts/run_checks.py --all。
6. 如果宿主需要平台 adapter 或 zip 包，再运行：.venv/bin/python scripts/run_checks.py --dist。
7. 安装完成后告诉我 SKILL_ROOT、调用方式、验证结果，以及是否生成了 dist/storm-deepresearch-skill.zip。
```

这不是仓库内置的一键安装命令，而是一个可审计的安装协议：当前代码真实提供的是 `SKILL.md`、`manifest.json`、`agents/interface.yaml`、分阶段 CLI、Yao 验证和 `--dist` 打包入口；Codex、Claude Code、OpenCode 的 skills 目录、启用方式和权限模型由各自宿主决定。

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
  --output research-run \
  --research-profile default_full_dossier \
  --profile-selection-mode user_requested_default \
  --profile-selection-evidence "用户明确要求按默认 full_dossier 运行"
```

该命令创建 `$WORKSPACE/output/storm-deepresearch/research-run/`、`work/generations/g0001/inputs/brief.json` 和 `state/generations/g0001/receipts/00-init.json`。目标一旦存在会以退出码 `4` 停止。`init` 现在要求 profile intake 证据；缺少 `--profile-selection-mode` 或 `--profile-selection-evidence` 会以退出码 `4` 停止，避免宿主跳过用户确认。

```bash
RUN_DIR="$WORKSPACE/output/storm-deepresearch/research-run"
```

中文 full dossier 默认为 `8000–10000` net body characters，英文为 `3500–7000` net body words。`report-depth` 排除参考文献区、脚注键、链接地址、图片标记和 Markdown 控制符；validation report 同时记录 `raw_body`、`citation_markers` 和 `net_body`，只有 `net_body` 用于门禁。只有用户明确要求简报时才使用 `--depth-level briefing`，并且必须同时提供 `--briefing-reason "用户明确要求简报的证据"`；宿主默认降级到 briefing 会在 init 阶段失败。

默认 `storm_lens_mode` 是 `strict`：`default_full_dossier` 和 `critique_deepresearch` 都必须让四个 STORM prompt 产生 `storm-lens-*.json` helper artifact，并把它们绑定进后续 receipts。`advisory` 只用于显式兼容或短 briefing，不再是完整研究默认值。

### 可选运行方式

宿主必须把 `research_profile` 作为用户选项展示，或从用户原话中提取明确选择。若用户只说“运行这个 skill 研究 xxx”，主菜单只展示两个选项：**完整深度研究（推荐）**和**短简报**。完整深度研究映射到 `default_full_dossier`，并强制 strict STORM P1-P4；不再把 `strict_storm_lens` 作为第二个重复选项。如果用户不选、说默认、或已经明确“按默认 full_dossier”，使用 `default_full_dossier` 继续执行，不要降级到 `briefing`。无论哪种情况，都必须在 `init` 写入 `profile_selection`：

| mode | 使用条件 |
| --- | --- |
| `user_selected` | 用户从菜单或文字中选择了具体 profile，例如 `briefing` 或场景化高级 profile。 |
| `user_requested_default` | 用户明确说“默认”“full_dossier”或等价表达。 |
| `defaulted_after_prompt` | 宿主已经展示选择菜单，用户没有选择或要求按默认继续。 |

| 选项 | CLI 映射 | 使用场景 |
| --- | --- | --- |
| `default_full_dossier` | `--research-profile default_full_dossier --profile-selection-mode user_requested_default --profile-selection-evidence "用户明确要求默认完整研究"` | **推荐选项。**完整研究、strict STORM P1-P4、host retrieval、外部审查和完整格式输出。 |
| `critique_deepresearch` | `--research-profile critique_deepresearch --profile-selection-mode user_selected --profile-selection-evidence "用户选择 critique_deepresearch"` | 电影、书、文章观后感或评论；先抽取用户观点，再检索支持、反驳、理论、评论接受史和历史比较。source plan 缺任一维度会在 plan 阶段失败。 |
| `closed_corpus` | `--research-profile closed_corpus --profile-selection-mode user_selected --profile-selection-evidence "用户选择 closed_corpus"` | 只使用用户提供的文件或封闭语料，不联网，不用模型记忆补事实。 |
| `briefing` | `--research-profile briefing --profile-selection-mode user_selected --profile-selection-evidence "用户明确选择 briefing" --briefing-reason "用户明确要求简报"` | 用户明确只要短简报。 |
| `repair_existing_run` | 不调用 `init`；先运行 `status` / `explain` | 修复已有 run，禁止重新初始化或覆盖账本。 |

`critique_deepresearch`、`closed_corpus` 和 `repair_existing_run` 是根据输入形态出现的高级选项，不与主菜单的深度/简报选择并列。旧命令 `--research-profile strict_storm_lens` 仍可调用，但新 run 会把它归一化为 `default_full_dossier`；生成的 brief 和用户可见 options 都只记录规范名称。

等价提示词示例：

```text
运行 $SKILL_ROOT，按默认 full_dossier 做研究。
如果需要选择运行方式，请默认使用 default_full_dossier；不要使用 briefing，除非我明确要求简报。
我的研究内容是：xxx
```

```text
运行 $SKILL_ROOT，选择完整深度研究（推荐）。
使用 default_full_dossier，并让 Prompt 1/2/3/4 分别产生 lens artifact 并绑定进 receipts，不要把四条 prompt 一次性跑完。
我的研究内容是：xxx
```

```text
运行 $SKILL_ROOT，使用 critique_deepresearch。
不要只查背景；先从我的观点中抽取可研究问题，再检索支持、反驳、理论、争议和同类比较。
我的观后感/评论是：xxx
```

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

每个问题还要声明 `search_requirements`：别名、检索面、是否需要学术证据、是否由用户语料提供 corpus-seeded 查询，以及纳入/排除标准。外部 full dossier 至少有一个问题要求 academic source class，并完成跨两个学术发现面的 academic baseline；briefing 可只用一个学术面，但引用的学术来源仍必须完成书目核验。

生成 plan 时先使用 [STORM Lens Prompt Pack](references/storm-lens-prompt-pack.md)：Prompt 1 只生成视角、研究问题和证据需求；检索和 findings 完成后再用 Prompt 2 做证据支持的矛盾地图；Prompt 3 只在 findings 和矛盾处理后生成 `report_outline`；Prompt 4 只在 draft 后做 red-team review。不要先把四条 STORM prompt 一次性跑完再联网搜索。

### 3. Ingest

内置脚本不会主动联网，网络调用始终由宿主工具或用户批准的 provider 执行。宿主把一次检索的三类记录写入同一个、符合 `schemas/retrieval-record.schema.json` 的 JSONL，再交给现有 `ingest` 命令：

- `search_run`：查询、别名、检索面、pass kind、结果数和原始结果快照。
- `candidate`：候选文献、纳入/排除决定、DOI/PMID/arXiv/OpenAlex/Semantic Scholar 身份、resolver 结果和版本家族。
- `capture`：真实 URL 或语料文件、精确 snapshot、locator、excerpt 和证据强度上限。

```bash
# single source helper; copies the snapshot into evidence-cache and writes retrieval-inputs.jsonl
"$PY" "$SKILL_ROOT/scripts/storm_research.py" capture-source "$RUN_DIR" \
  --query-id Q001 \
  --url "https://www.nist.gov/replace-with-real-source" \
  --snapshot captured-page.html \
  --title "Source title" \
  --publisher "Publisher or author" \
  --content-excerpt "Exact excerpt present in the captured file" \
  --source-type secondary_synthesis \
  --primary-class secondary \
  --reliability-tier B \
  --reliability-notes "Why this source is usable for the specific claim"

# batch helper; reads sources.jsonl from the directory and produces retrieval-inputs.jsonl
"$PY" "$SKILL_ROOT/scripts/storm_research.py" ingest-dir "$RUN_DIR" \
  --input-dir captured-sources \
  --to retrieval-inputs.jsonl
```

`capture-source` 和 `ingest-dir` 不写 receipt；它们只生成并预检后续 `ingest` 要吃的 JSONL。常见坏抓取页，例如 `Checking if the site connection is secure`、`Access denied`、`载入中`、过短正文，会默认失败；确实要保留时必须显式加 `--allow-warning`。

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" ingest "$RUN_DIR" \
  --input-jsonl retrieval-records.jsonl
```

`host` 是默认检索模式；`provider` 只在用户明确配置凭证时使用；`closed_corpus` 只使用指定文件或 URL。占位符域名、`.internal` 伪来源、无快照、secondary-as-primary、Wikipedia 伪装成 primary/Tier A 和 blanket Tier A 会在 ingest 阶段失败。full dossier 的外部研究至少需要 `6` 个非用户、非百科的外部来源；Wikipedia 可作背景线索，但不能替代 deep research。

成功 ingest 会生成内部、receipt-bound 的 `research/retrieval-audit.jsonl`，保留 search run、候选筛选、resolver、版本家族和快照哈希；它不会进入公开 release。academic resolver 标为 `matched` 时，快照必须是可解析的 Crossref、OpenAlex、Semantic Scholar、PubMed 或 arXiv 提供方原始响应，identifier、title、authors 和 year 必须与 outcome 一致；模型整理的 DOI/title/year 小对象不能充当响应。`unreachable` 表示检索面不可达，不等于 `unmatched`。同一论文的预印本、会议版和期刊版会合并进一个 version family，不能冒充多个独立来源。零结果只证明该次查询没有返回候选，不能直接证明某事实不存在。

### 4. Findings

检索后先提交 findings pool，把每个 tasklet 的可用发现、来源和候选 Claim 绑定起来：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" findings "$RUN_DIR" \
  --findings-jsonl findings.jsonl
```

full dossier 要求每个 `storm-tasklets.jsonl` 里的 tasklet 至少有一个 `usable` finding。后续 evidence 阶段会要求材料性 Claim 链接到 usable finding，且 finding 与 Claim 必须共享 supporting source。

若 finding 标为 `needs_more_evidence`，必须先执行并登记 `gap-fill` search run；仍无法闭合的 tasklet 只能进入 uncertainty ledger 或明确 out of scope。corpus-seeded 搜索先提取用户语料中的术语、作者和主张，但仍须按 plan 完成 baseline、counterevidence 和必要的 gap-fill。

strict mode 下，findings 后必须先注册 Prompt 2 和 Prompt 3 artifacts，不能把 contradictions、uncertainties、outline 和 claims 一次性批处理进 evidence：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" lens-conflicts "$RUN_DIR" \
  --input-json storm-lens-conflicts.json

"$PY" "$SKILL_ROOT/scripts/storm_research.py" lens-outline "$RUN_DIR" \
  --input-json storm-lens-outline.json
```

Prompt 2 的每个 blind spot 和 resolver question 都必须写入 `resolution_actions`，处置为 `new_retrieval`、`uncertainty` 或 `out_of_scope`。`new_retrieval` 会阻止 Prompt 3，必须通过 `amend` 建立新 generation 后补检索。

### 5. Evidence

提交 Claim、矛盾、不确定性和报告大纲：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" evidence "$RUN_DIR" \
  --claims claims.jsonl \
  --contradictions contradictions.json \
  --uncertainties uncertainties.json \
  --report-outline report-outline.json
```

若 material Claim 表述“未发现证据”“尚无临床试验”等 absence 结论，还必须添加 `--absence-searches absence-searches.jsonl`。full dossier 至少覆盖两个独立检索面；高风险医疗研究还必须覆盖试验注册库、文献数据库和至少三个别名。

材料性事实必须有可定位证据；推断必须指出已支持前提；建议必须写明适用条件和取舍。涉及阿伦特、福柯、康德、马克思、文化工业、生命政治等理论框架的 material claim，必须由 academic、book、expert、peer_reviewed_paper 或 secondary_synthesis 类型来源支撑，用户观后感、转录文本或百科页面不能单独闭合。full dossier 至少需要 5 个视角、10 个问题、6 个 evidence-planned sections 和 12 个 material claims。

#### 证据层级与方法适配

方法适配先看具体结论形态，再看来源能证明什么。官方说明可以证明已记录的功能、规则和立场，不能单独证明真实采用效果；用户或社区经历可以证明个案，不能推出发生率；新闻可以证明某事件或说法被报道，不能替代原始证据；调查和观察性研究通常支持样本与测量范围内的比例或关联，不能自动升级为因果；实验、准实验、系统综述和 Meta 分析仍受识别假设、测量、随访、异质性及适用范围约束。完整六类决策表见[来源与证据策略](references/source-and-evidence-policy.md)。

- Tier、来源声望、论文数量和多个同向观察性结果都不能升级研究方法的证明能力。
- 问题所需的多类证据可以由多个 Claim 共同完成，不要求每个 Claim 覆盖所有 evidence roles。
- 已知 stale 或不适合当前事实的 historical 材料支撑明确当前结论时失败；发布日期或 freshness 未观察到时只产生非阻塞风险提示，由语义审查结合内容和版本信号判断。
- 日期未知不要求 Claim 改为 `qualified`，也不要求作者添加“日期未知”等模板句。

规则按影响分为三类：

| 级别 | 适用问题 |
|---|---|
| 硬失败 | 假或不可检查的来源；material Claim 无证据；关键引用不支持；危险的方法越界；已知过期材料支撑明确当前事实；凭证、本地路径或网络安全泄漏 |
| 警告、限定或语义判断 | 日期未知；样本、方法、地域或长期适用性信息不完整；观察性结论需要收窄为关联；用户经历需要收窄为个案；来源只能支持更窄的结论；问题层面的证据组合有缺口 |
| 仅内部诊断 | pass 顺序、时间窗、Selection hash、ID、路径、timestamp 和 receipt 记账；不据此生成方法覆盖率或报告质量分数 |

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

`draft.md` 不能手写 References、参考文献、参考资料、资料来源或 Sources。每个 factual paragraph 必须映射到 Claim、source 和 citation key；脚本会从 source register 生成 References。字数门禁只统计这些参考文献区之前的净正文，不能用来源清单撑过最低字数。

可以先用 sidecar 或内联 `storm-map` 注释生成 `paragraph-map.jsonl`，减少手工同步 paragraph hash、Claim、source 和 citation key 的错误：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" build-paragraph-map "$RUN_DIR" \
  --draft-md draft.md \
  --sidecar-jsonl paragraph-sidecar.jsonl \
  --to paragraph-map.jsonl
```

sidecar 最小格式是一行一个段落映射，例如 `{"text_locator":"paragraph:1","claim_ids":["C001"]}`；脚本会从 Claim ledger 和 source register 推导 source IDs 和 citation keys。内联格式为 `<!-- storm-map: claims=C001; type=factual -->`，命令会在生成最终报告前剥离这些注释。

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

先应用或明确 waiver 所有 P4 repair actions，再冻结候选报告：

```bash
"$PY" "$SKILL_ROOT/scripts/storm_research.py" review-prepare "$RUN_DIR" \
  --candidate-md report.md \
  --candidate-map reviewed-paragraph-map.jsonl \
  --revision-map revision-map.json
```

`review-prepare` 还会在同一冻结目录生成 `review-candidate/review-context.md`，并输出机器可读的 `review_handoff_required=true`、`author_may_continue=false`。它把用户问题、source plan 的 `can_prove/cannot_prove`、Claim 与来源、准确 capture excerpt、矛盾、不确定性和 P4 问题投影为可读材料；它不做方法分类或评分。宿主必须把整个 `review-candidate/` 与 `research/review-request.json` 交给真正隔离的外部模型入口或人工 reviewer，不能只给哈希。若宿主不能启动独立 actor，应报告外审等待。

reviewer 把所有语义审阅 JSONL、transcript 和一个最小执行元数据文件写入同一目录；该目录必须同时位于 run 和 Skill 之外。执行元数据只需要 `execution_kind`、`reviewer_identity`、`execution_id`，外部模型再加 `provider`、`model`、`runner`。不得让作者在 run 的 `_build/reviewer/` 中伪造提交。`review` 在回收时生成 context/session ID、绑定哈希、时间窗和 attestation；调用者不填写这些字段。例如：

```json
{"execution_kind":"external_model","reviewer_identity":"external reviewer","execution_id":"provider-run-42","provider":"configured-provider","model":"configured-model","runner":"host-review-adapter"}
```

reviewer 使用现有 `verdict`、`reason`、`allowable_scope`、`required_action` 和 `findings` 判断具体 Claim/句子的方法适配。日期未知本身不能决定 verdict，也不能按“非学术”“新闻”或“用户来源”等类别整体否决。

每个 material Claim 和正文段落仍必须有语义审查记录。material Claim 的非 `supported` verdict 继续阻止 review。对段落审查，`material=true` 只用于会改变核心答案、关键综合或行动建议，或者构成安全风险的实质性证据问题；这类目标的非 `supported` verdict 会阻止 review。局部措辞、可进一步限定但不改变核心判断的问题使用 `material=false`：记录和修复动作保留在 `peer-review.json`，review 命令输出 warning，但不阻止整份报告。不得为过 gate 把关键问题标成非 material。

```bash
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

full dossier 不接受 `self_review`。当前保证等级是“外部提交边界已捕获并绑定”；它不是供应商签名，也不把自报 context ID 或 attestation 当作隔离证明。

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
"$PY" "$SKILL_ROOT/scripts/storm_research.py" doctor "$RUN_DIR"

"$PY" "$SKILL_ROOT/scripts/storm_research.py" repair-plan "$RUN_DIR"
```

本地使用可把已验证成品收集到浅层目录；`collect` 需要通过 validation，只复制 `report.md`、HTML、PDF 和 validation report，不替代 public `release`。`current/` 是 harness-owned 便利视图，宿主不得用 `cp`、重定向或编辑器直接写入，也不得把 `_build` 或 validation 前的文件作为最终交付。只有 `status.local_delivery_ready=true` 后成功执行 `collect`，才可以向用户宣告本地 full dossier 完成：

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
- `work/generations/g0001/artifacts/research/retrieval-audit.jsonl`：内部检索、筛选、书目解析与版本归并审计；绑定 retrieval receipt，不进入 release。
- `work/generations/g0001/artifacts/research/claim-evidence-ledger.jsonl`：事实、推断、建议和证据状态。
- `work/generations/g0001/artifacts/research/reviewed-paragraph-map.jsonl`：公共报告段落到内部 claim/source/citation 的映射。
- `work/generations/g0001/artifacts/research/review-request.json`：冻结候选报告、输入哈希和 author context 的外部审查 handoff。
- `work/generations/g0001/artifacts/review-candidate/review-context.md`：供 reviewer 直接阅读的冻结问题、证据边界、Claim、capture、反证和 P4 上下文。
- `work/generations/g0001/artifacts/research/reviewer-provenance.json`：harness 从外部提交边界生成的执行身份、时间窗、transcript 和审阅输出绑定；不是 provider signature。
- `work/generations/g0001/artifacts/report.md`：唯一内容真源。
- `work/generations/g0001/artifacts/exports/report.html`、`report.pdf`：确定性派生物。
- `work/generations/g0001/artifacts/validation/render-manifest.json`：跨格式哈希和章节指纹。
- `work/generations/g0001/artifacts/validation/validation-report.json`：机器可读验证判定。
- `state/generations/g0001/receipts/*.json`：不可跳过的阶段 receipt chain。
- `current/repair-plan.json`：失败后可选生成的结构化修复计划，不是权威 receipt。
- `release/`：通过 Trust 和 human approval 后生成的严格 allowlist 发布投影。

可查看 [历史格式示例](examples/validated-output/) 和 [PDF](examples/validated-output/exports/report.pdf)。该目录只用于说明旧版交付物布局，不代表 3.1.0 的 academic retrieval、bibliographic、screening、version-family、gap-fill 和 evidence-method-fit 合同；3.1.0 成品必须以本次运行的 `validation-report.json` 为准。

## 开发与发布门禁

这里有三种不同的完成动作，不应混为一条流水线：

| 动作 | 最小要求 | 是否需要 human release approval |
|---|---|---|
| 普通 Git commit / push | 审查 diff，运行与改动相关的最小离线测试 | 否 |
| 构建并发布 Skill ZIP | `--all`、`--dist`、package verification；发布到 registry 时再做对应审计 | 否，除非目标平台另有要求 |
| 公开某次研究报告包 | 该 run 已通过 review、render、validate，并完成 Trust、registry、必要的来源再验证和 release approval | 是 |

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/run_checks.py --all
.venv/bin/python scripts/run_checks.py --dist
```

`--all` 运行单元测试、编译检查、schema 检查，以及 Yao 的 validate、lint、governance 和 resource-boundary 检查。这个项目明确采用 `2200` initial-load token 上限，以容纳 evidence-method-fit 等会改变执行行为的规则；当前实测约 `2062`，不会为了满足 Yao 的通用 `1300` 默认值而删掉关键安全和质量判断。`--dist` 是正式技能包构建入口：它调用 Yao package 生成 openai/claude/generic/vscode 四个平台 adapter，创建 `dist/storm-deepresearch-skill.zip`，净化归档中的本机路径，并把 ZIP 收窄为显式运行时 allowlist，然后执行 package verification。安装 ZIP 只保留 `SKILL.md`、README、LICENSE、manifest、运行依赖、`agents/interface.yaml`、权限策略、references、schemas、核心运行脚本和 HTML 模板；平台 adapter 位于 `dist/targets/` 并与 ZIP 一起验证。tests、evals、reports、docs、examples、registry、release 工具及本地输出不会进入安装包。

源码仓库的 `reports/` 只保留当前离线验证直接读取的四个 JSON：Trust、架构维护性、Python 兼容性和 Registry audit。它们使用 `$SKILL_ROOT` 或相对路径；生成的 package verification 留在被忽略的 `dist/`，不进入安装包。最终研究报告 release 仍须运行 `storm_research.py release` 并绑定外部 trust、registry、re-verification 和 human approval。发布步骤见 [发布检查表](docs/release-checklist.md)。

如果手动调用 Yao package，执行 package verification 前仍需净化归档中的本机路径：

```bash
.venv/bin/python scripts/sanitize_release_archive.py \
  dist/storm-deepresearch-skill.zip \
  --redact-root "$PWD" \
  --exclude-prefix storm-deepresearch-skill/output/ \
  --exclude-name .DS_Store \
  --runtime-only
```

该命令保留 ZIP 结构和二进制条目，将项目根路径替换为 `$SKILL_ROOT`、用户主目录替换为 `$HOME`，并排除非运行时文件、本地运行产物与 Finder 元数据；存在不安全条目或未完成净化时非零退出。

## 版本迁移与回滚

2.x 到 3.0.0 的检索输入、academic baseline 和内部审计变化见 [3.0 迁移指南](docs/migration-v2-to-v3.md)。1.1.0 到 2.0.0 的外部审查、净正文、absence-search 和时间因果变化见 [2.0 迁移指南](docs/migration-v1.1-to-v2.0.md)。旧 run 不会静默迁移；必须由创建该 run 的版本解释。

## 设计来源

- STORM：多视角问题发现、检索、信息整理和带引用写作。
- DeepResearch：来源优先、拒绝幻觉、显式不确定性和证据闭合。
- `yao-tutorial-skill`：成品化交付与多格式输出。
- Yao Meta Skill：接口、schema、评估、治理、打包与安装门禁。
