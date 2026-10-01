---
name: research-survey-html
description: Use when the user asks for a comprehensive literature or field survey (调研/综述/领域梳理) on any research topic, delivered as a visual, interactive, self-contained HTML report — includes how to search and verify literature, build taxonomy/teams/map/repo sections, export references to Zotero, and screenshot-check the result.
---

# 研究领域调研 → 交互式 HTML 报告

把“某个研究方向近几年的进展”做成一份**可核查、可交互、离线可用**的单文件 HTML 综述：时间轴、方向分类树、可筛选的代表作表、团队卡片、世界热力图（点击国家看名单）、开源仓库图表、参考文献，并导出 BibTeX/RIS 供 Zotero 导入。

本文件所在目录记为 `SKILL_DIR`。脚本在 `SKILL_DIR/scripts/`，详细说明在 `SKILL_DIR/references/`，示例数据在 `SKILL_DIR/examples/agent-science-mini/`。检索与构建只依赖 Python 3.9+ 标准库；截图需要 `playwright`。

## 0. 先问清范围（一次问完，用户没说的给默认值并写进报告）
1. **主题**与边界（包含/不包含什么，相邻领域怎么处理）。
2. **时间范围**（默认最近 2–3 年，截止今天）；更早的工作只作一句背景。
3. **是否收录预印本**（默认收录，逐条标注状态）；是否收录博客/产品/新闻。
4. **输出语言**（默认与用户一致，如简体中文 + 英文术语）与读者（导师、组会、自己入门）。
5. **规模与板块**：代表作数量（默认 50–150）、是否需要团队/地图/开源仓库板块；输出路径；是否导出 Zotero。

## 1. 查文献（如何查文献）→ 详见 [references/literature-search.md](references/literature-search.md)
1. **设计检索式**：拆成 2–4 个概念块，每块扩展同义词/缩写/上下位词/中文词；从种子论文和综述反向抽词；按各数据源语法分别改写；记录每轮检索式、日期、命中数（写进“范围与方法”）。
2. **多源检索**（脚本输出统一 JSONL 候选）：
   - arXiv：`scripts/search_arxiv.py --query 'abs:"…" AND cat:cs.AI' --from … --to …`（**≤1 次/3 秒、单连接**；持续 429 就停，改用 Semantic Scholar batch / OpenAlex / abs 页面核对）。
   - Semantic Scholar：`scripts/search_s2.py search|bulk|batch|refs|cites`（建议设 `S2_API_KEY`）。
   - OpenAlex：`scripts/search_openalex.py search …`（2026-02 起需 `OPENALEX_API_KEY`，单条 DOI 查询免费）。
   - Crossref：`scripts/search_crossref.py doi|title …`（DOI/venue 核对，设 `SURVEY_MAILTO`）。
   - bioRxiv/medRxiv：`scripts/search_biorxiv.py window --category … --kw …`（API 无关键词搜索，按日期窗口拉取后本地过滤；`/pubs/` 查是否已正式发表）。
   - PubMed：`scripts/search_pubmed.py '…[tiab]'`。
   - DBLP、OpenReview：核对 CS 会议是否录用（端点见参考文档）。
   - Hugging Face Papers（Papers with Code 已于 2025-07 停服并跳转至此）：找有代码的热门工作。
   - Google Scholar、知网：**只人工检索**，不写爬虫；用 Zotero Connector 保存。
   - 公司/实验室博客、新闻：用 WebSearch/WebFetch，标为“未经同行评审/公司自报”。
3. **滚雪球**：5–15 篇种子论文做后向（refs）+ 前向（cites），新增相关条目 <5% 时停止。
4. **合并去重与筛选**：`scripts/merge_dedup.py cand_*.jsonl --out candidates.jsonl --csv screening.csv` → 在 CSV 中填 `include=1` 和 `dirs` → `--screened screening.csv --works-draft works_draft.json` 生成 works 草稿。去重键：DOI（非 arXiv DOI）> arXiv ID > 规范化标题；预印本与正式版合并为一条。
5. **标注状态**：`peer: true` 仅限官方渠道可查的期刊/会议（含 workshop，需写明）；预印本、博客、产品、公司自报一律 `peer: false` 并在 `status` 写清楚；只有作者自述的录用写“据 README，未核对官方名单”。
6. **核查规则**：绝不编造；每条要有可点击 `url` 和 `checked` 日期；机构/国家查不到写“—（未核实）”、`country` 留空、不计入地图；动态数字注明抓取日期；最终抽查 10%。
7. **导出 Zotero**：`scripts/export_bibtex.py <data_dir> --out out/references` → `.bib`、`.ris`（方向键成为标签）和 `zotero_identifiers.txt`（粘贴到 Zotero“魔棒”最完整）。

## 2. 方向分类、团队与国家 → 详见 [references/taxonomy-and-teams.md](references/taxonomy-and-teams.md)
- 自下而上卡片分组 + 对照 2–4 篇综述命名；6–12 个方向，可交叉，但 `dirs` 第一个为**主方向**；每个方向写现状与主要难题；按里程碑划 3–6 个阶段。
- 团队粒度到课题组/研究部门；进展等级 1–4；只写有来源的事实。
- 国家用 ISO alpha-2。**团队数**按团队主要所在地（跨国公司按成果主要团队所在地）；**代表作数**按第一/主导机构；主导者不唯一则不计。地区口径（如香港）写进报告，地图可用 `map.merge` 合并。

## 3. 开源仓库 → 详见 [references/repo-inspection.md](references/repo-inspection.md)
`scripts/github_repos.py <data_dir>/repos.json`：GitHub API 取 stars、forks、`license.spdx_id`、`pushed_at`、默认分支最近提交、latest release、archived（设 `GITHUB_TOKEN`；匿名 60 次/小时）；被限速时自动回退到公开页面 + commits/releases Atom。人工补 `what/arch/run/deps/lim`，自定义许可证写 `license_note`。活跃度：≤30/90/365 天分四档。

## 4. 生成 HTML → 详见 [references/data-schema.md](references/data-schema.md)、[references/html-build-and-verify.md](references/html-build-and-verify.md)
1. 新建数据目录（可复制 `examples/agent-science-mini/` 再替换内容）：`meta.json`、`works.json`、`teams.json`、`timeline.json`、`repos.json`、`narrative/{summary,scope,challenges,caveats}.html`。
2. 写 narrative：执行摘要（5–8 条关键发现，每条有事实和来源）、范围与方法（时间、来源、检索方式、状态标注、计数口径、核查日期与时区）、挑战与趋势、注意事项与未核实项。
3. `python scripts/build.py <data_dir> --check`，修完 error 后 `python scripts/build.py <data_dir> -o out/survey.html`。输出单个自包含 HTML（内联 ECharts 与地图，离线可用）；缺省的板块自动隐藏、目录自动编号。

## 5. 截图验证（交付前必做）
`python scripts/screenshot.py out/survey.html --outdir out/screens [--chrome /usr/bin/google-chrome]`：检查 console 报错、横向溢出、空图表并截取各板块。**逐张查看**：中文无方块字、地图着色且点击面板有内容、所有图表渲染、表格行数正确。有问题修数据/模板后重建。

## 6. 交付
给用户：HTML 路径、截图、`references.bib/.ris`、数据目录（便于以后增补）、检索日志；在回复里说明核查日期（带时区）、收录规模、主要局限与未核实项。

## 注意事项 → 详见 [references/quality-checklist.md](references/quality-checklist.md)
- 收录偏向英文与高影响力来源，地图/排名只代表样本；预印本状态与星标会变，以核查日期为准。
- 不抓取 Google Scholar，不绕过限速/反爬；API 规则会变化，以官方文档为准。
- 媒体与公司自报数字要标注来源；不要把预印本写成“已发表”。
- Natural Earth 地图边界不代表政治立场；在中国大陆正式出版请用经审核的标准地图（`--world`）。
- 内联的 ECharts 为 Apache-2.0，分发 HTML 时保留其版权声明（模板已含注释，见 NOTICE）。
