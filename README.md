# STORM DeepResearch Skill

`storm-deepresearch-skill` 是一个证据驱动的深度研究 Library。它保留 STORM 的多视角提问思想，但不把角色观点当证据：视角只生成检索问题，事实必须进入来源登记和 Claim-Evidence 账本，最终从单一 `report.md` 渲染并验证 Markdown、HTML 和 PDF。

当前版本：`0.4.0`

## 能做什么

- 研究报告、文献综述、行业分析和决策简报。
- 基于用户文件、URL 或封闭语料完成可审计研究。
- 区分事实、推断、建议、矛盾和未知项。
- 生成来源登记、证据账本、报告映射和验证报告。
- 以 `report.md` 为唯一内容真源，导出一致的 HTML/PDF。
- 默认中文完整研究为 `8000–10000` 正文字符；输入长度只改变检索量，不会自动把成品压缩成摘要。
- 强制将已回答的 STORM 问题和材料性 Claim 映射到 `research-plan.report_outline`，避免研究停留在中间产物。
- 对空证据、假引用、过期证据、占位符、本地路径泄漏、缺失 PDF 和格式漂移返回非零退出码。
- 默认在用户工作区的 `output/storm-deepresearch/` 下创建独立运行目录；已存在目标、路径逃逸和符号链接逃逸都会失败。
- 初始化不会覆盖既有研究包；来源登记采用保留既有 ID 的原子合并，研究账本不能被重新初始化截断。

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

### 1. 初始化研究包

```bash
SKILL_ROOT=/path/to/storm-deepresearch-skill
WORKSPACE=/path/to/user-workspace

"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/init_research_package.py" \
  --topic "AI Agent Skill 的工程化评估" \
  --question "怎样证明一个 Skill 的输出可靠、可复现且可发布？" \
  --workspace "$WORKSPACE"
```

该命令默认创建 `$WORKSPACE/output/storm-deepresearch/<topic-slug>-<timestamp>/` 并打印实际路径。以下示例用 `RUN_DIR` 表示该路径。需要稳定名称时使用 `--output research-run`；它仍然必须是输出根目录的新子目录。

目标一旦存在，初始化会以退出码 `4` 停止，不会覆盖或清空其中的来源、Claim 或矛盾记录。`--output-root` 只能用于用户明确批准的替代根目录；所有路径都会在解析符号链接后重新校验。

该命令会根据主题语言选择默认长度：中文 full dossier 为 `8000–10000` characters，英文为 `3500–7000` words。只有用户明确要求简报时才使用 `--depth-level briefing`；也可用 `--language`、`--min-units` 和 `--max-units` 明确覆盖。

### 2. 明确检索模式

编辑 `$RUN_DIR/brief.json`：

- `host`：宿主 Agent 使用已获准的搜索或浏览工具，默认模式。
- `provider`：仅在用户明确配置外部提供商时使用，凭证只能来自环境变量。
- `closed_corpus`：只使用指定文件或 URL，不扩展外部语料。

内置脚本不会主动联网。宿主检索结果必须符合 `schemas/retrieval-record.schema.json`，再归一化为来源记录：

```bash
"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/normalize_retrieval.py" adapter-output.jsonl \
  --mode host \
  --package "$RUN_DIR"
```

归一化器不会重建来源登记：它保留既有 `source_id`，按 canonical URL 或相对文件引用合并更新，为新来源递增分配 ID，并在完整合并成功后原子替换文件。输入或合并失败时，原账本保持不变。

### 3. 建立证据并写报告

按照 [研究协议](references/research-protocol.md) 填充研究计划、来源登记、Claim-Evidence 账本、矛盾和不确定性记录。写作前必须完成 `research-plan.report_outline`：为每个章节分配篇幅、STORM 问题、Claim 和展开要素。材料性事实必须有可定位证据；推断必须指出已支持前提；建议必须写明适用条件和取舍。

`research/source-register.jsonl` 与 `research/claim-evidence-ledger.jsonl` 是权威数据，Markdown 审计表是生成视图：

```bash
"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/merge_claim_ledger.py" claim-updates.jsonl \
  --package "$RUN_DIR"

"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/render_audit_views.py" "$RUN_DIR"
```

Claim 合并器要求输入完整的 Claim 记录：新 ID 追加，同 ID 显式修订，但不会删除未出现在本次输入中的既有 Claim；校验或写入失败时原账本不变。

### 4. 从唯一真源导出

```bash
"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/export_report.py" "$RUN_DIR" \
  --template "$SKILL_ROOT/templates/report.html.j2" \
  --title "AI Agent Skill 的工程化评估" \
  --require-pdf
```

完整模式必须生成 PDF。只有 `brief.json` 明确设置 `"output_mode": "reduced"` 时，才允许没有 PDF。

### 5. 严格验证

```bash
"$SKILL_ROOT/.venv/bin/python" "$SKILL_ROOT/scripts/run_checks.py" --package "$RUN_DIR"
```

退出码：

| 退出码 | 含义 |
|---:|---|
| `0` | 全部必需检查通过 |
| `4` | 文件、JSON Schema 或跨文件契约失败 |
| `5` | 来源、证据闭合、时效性或矛盾处理失败 |
| `6` | 模板、HTML/PDF、指纹或跨格式一致性失败 |
| `7` | 本地路径、内部 ID 或公共输出安全失败 |

除非 `validation/` 本身通过符号链接逃逸包边界，验证器都会写入 `validation/validation-report.json` 和 `.md`；失败不会以零退出码伪装成功。

路径、覆盖和账本规则见 [输出路径策略](references/output-path-policy.md)。HTML、PDF、审计 Markdown 和验证报告属于派生产物，可以在包内重新生成；两个 JSONL 权威账本都必须通过保留既有记录的合并器更新。

## 输出结构

完整契约见 [示例输出树](examples/example-output-tree.md)。核心文件包括：

- `brief.json`：范围、时效、检索和输出模式。
- `research/research-plan.json`：视角、问题、预算和停止条件。
- `research/research-plan.json` 中的 `report_outline`：问题/Claim 到章节及篇幅预算的闭环。
- `research/source-register.jsonl`：来源权威账本。
- `research/claim-evidence-ledger.jsonl`：事实、推断、建议和证据状态。
- `research/report-claim-map.json`：公共报告段落到内部 claim 的映射。
- `report.md`：唯一内容真源。
- `exports/report.html`、`report.pdf`：确定性派生物。
- `validation/render-manifest.json`：跨格式哈希和章节指纹。
- `validation/validation-report.json`：机器可读发布判定。

可直接查看通过严格验证的 [代表性研究包](examples/validated-output/) 和 [PDF](examples/validated-output/exports/report.pdf)。

## 开发与发布门禁

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/run_checks.py --all
```

`--all` 运行单元测试、编译检查、schema 检查和 Yao Meta Skill 验证。Yao 的 Output Lab、Trust、Conformance、Packaging 和安装模拟证据保存在 `reports/`；发布步骤见 [发布检查表](docs/release-checklist.md)。

Yao 生成 ZIP 后、执行 package verification 前，先净化归档中的本机路径：

```bash
.venv/bin/python scripts/sanitize_release_archive.py \
  dist/storm-deepresearch-skill.zip \
  --redact-root "$PWD"
```

该命令保留 ZIP 结构和二进制条目，将项目根路径替换为 `$SKILL_ROOT`、用户主目录替换为 `$HOME`；存在不安全条目或未完成净化时非零退出。

## 版本迁移与回滚

0.3.0 到 0.4.0 的路径、初始化、归一化和导出 CLI 变化见 [迁移指南](docs/migration-v0.3-to-v0.4.md)。更早版本的迁移文档保留在 `docs/`。

## 设计来源

- STORM：多视角问题发现、检索、信息整理和带引用写作。
- DeepResearch：来源优先、拒绝幻觉、显式不确定性和证据闭合。
- `yao-tutorial-skill`：成品化交付与多格式输出。
- Yao Meta Skill：接口、schema、评估、治理、打包与安装门禁。
