# STORM DeepResearch Skill

当前版本：`3.1.0`

## 是什么

`storm-deepresearch-skill` 是一个面向 Agent 的证据驱动深度研究 Skill。它用 STORM 多视角生成研究问题，通过来源登记、学术检索、Claim–Evidence 绑定、独立语义外审和 receipt chain 约束研究过程，最终生成并验证一致的 Markdown、HTML 和 PDF 报告。

它适合研究报告、文献综述、行业分析和决策研究；不适合快速事实查询、简单摘要、无证据角色扮演，或个性化医疗、法律、投资建议。

## 能做什么

- 保留至少五个真正不同的 STORM 视角，把视角转化为可检索问题，而不是把角色观点当证据。
- 同时处理官方资料、学术论文、行业材料、新闻、用户材料和封闭语料。
- 核验 DOI、PMID、arXiv、OpenAlex、Semantic Scholar 等学术身份，并归并论文版本。
- 对外部完整研究执行 academic baseline，在 `retrieval-audit.jsonl` 记录 bibliographic 身份、corpus-seeded 检索和 gap-fill。
- 记录检索、候选筛选、来源快照、精确 excerpt 和 locator，拒绝假来源或不可检查证据。
- 区分事实、推断、建议、矛盾和未知项，检查来源类型、研究方法、样本、时间和地域是否支持具体结论。
- 将报告段落绑定到 Claim 和来源，由真正隔离的外部模型或人工 reviewer 完成语义外审。
- 从单一报告真源渲染 Markdown、HTML 和 PDF，并验证证据闭环、路径安全、格式一致性和正文深度。
- 支持本地验证后 `collect` 交付；只有公开研究包才需要额外的 Trust、Registry 和人工 release approval。

## 安装

要求：Python 3.11+、Pandoc，以及 WeasyPrint 或 Chrome/Chromium。推荐使用 `uv`。

```bash
git clone https://github.com/bilppppp/storm-deepresearch-skill.git
cd storm-deepresearch-skill

uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements-dev.lock

pandoc --version
.venv/bin/python scripts/run_checks.py --all
```

把仓库放入或链接到宿主推荐的 skills 目录，然后通过 `$storm-deepresearch-skill` 调用。不同宿主的安装目录和启用方式不同；不要复制 `.venv`、`dist`、`output` 或研究运行产物。

也可以直接让 Agent 安装：

```text
请把 https://github.com/bilppppp/storm-deepresearch-skill.git 安装为本地 Skill，
使用 Python 3.11 创建 .venv，安装 requirements-dev.lock，
检查 Pandoc，并运行 .venv/bin/python scripts/run_checks.py --all。
完成后告诉我安装路径、调用方式和验证结果。
```

## 快速开始

最简单的使用方式是直接交给支持本地 Skill 的 Agent：

```text
使用 $storm-deepresearch-skill，按 default_full_dossier 研究：
“生成式 AI 如何改变知识工作者的入门岗位与能力要求？”
```

直接使用 CLI 时，先创建全新 run：

```bash
SKILL_ROOT=/path/to/storm-deepresearch-skill
PY="$SKILL_ROOT/.venv/bin/python"
WORKSPACE=/path/to/user-workspace

"$PY" "$SKILL_ROOT/scripts/storm_research.py" init \
  --topic "生成式 AI 与知识工作" \
  --question "生成式 AI 如何改变知识工作者的入门岗位与能力要求？" \
  --workspace "$WORKSPACE" \
  --output ai-knowledge-work \
  --research-profile default_full_dossier \
  --profile-selection-mode user_requested_default \
  --profile-selection-evidence "用户明确要求默认完整研究"

RUN_DIR="$WORKSPACE/output/storm-deepresearch/ai-knowledge-work"
"$PY" "$SKILL_ROOT/scripts/storm_research.py" status "$RUN_DIR"
```

完整流程是：

```text
init → P1/plan → retrieval/ingest → findings → P2/P3 → evidence
→ draft/P4 → review-prepare → 独立 review → render → validate → collect
```

各阶段输入、命令、外审交接、故障恢复、输出结构和发布边界见[使用手册](docs/usage-guide.md)。证据、检索和质量规则以 [`references/`](references/) 中的当前策略为准。
