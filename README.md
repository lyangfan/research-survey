# research-survey-html · 研究领域调研 → 交互式 HTML 综述

一个**通用、可复用**的 Agent Skill + 独立 Python 流水线：把“某个研究方向近几年的进展”做成一份**可核查、可交互、离线可用**的单文件 HTML 综述，并配套一套**如何查文献**的方法（多数据源检索式、API 用法与限速、滚雪球、去重、发表状态标注、核查规则、导出到 Zotero）。

![preview](docs/preview.png)

*示例（`examples/agent-science-mini`，10 篇真实代表作）构建结果的首屏截图。*

生成的报告包含：吸顶目录 · 执行摘要 · 范围与方法 · 发展路径时间轴（阶段/类别筛选 + 按半年×方向柱状图）· 方向分类树图 · 可筛选/搜索/排序的代表作表（同行评审 vs 预印本）· 团队卡片 · 世界热力图（点击国家看团队与代表作）· 开源仓库 Stars/活跃度图表与详情表 · 挑战与趋势 · 注意事项 · 自动汇总的参考文献。

## 目录结构

```
SKILL.md                  Agent Skill 主文件（中文流程）
references/               详细说明：查文献、数据格式、分类与国家口径、仓库核查、构建与截图、检查清单
scripts/
  build.py                数据目录 -> 单个自包含 HTML（内联 ECharts + 地图 + 数据）
  template.html           页面模板（CSS + ECharts 交互）
  screenshot.py           Playwright 截图与渲染检查
  search_arxiv.py  search_s2.py  search_openalex.py  search_crossref.py
  search_biorxiv.py  search_pubmed.py  merge_dedup.py  export_bibtex.py  github_repos.py
  common.py  countries.py
  vendor/echarts.min.js   Apache ECharts 5.6.0（Apache-2.0，附 LICENSE/NOTICE）
examples/agent-science-mini/   示例数据集（真实条目）
docs/preview.png
```

## 用法一：作为 Agent Skill（Cursor / Claude Code 等支持 SKILL.md 的工具）

技能文件夹名必须与 `SKILL.md` 中的 `name` 一致（`research-survey-html`）：

```bash
# Cursor（全局）
git clone https://github.com/lyangfan/research-survey ~/.cursor/skills/research-survey-html
# Claude Code（全局）
git clone https://github.com/lyangfan/research-survey ~/.claude/skills/research-survey-html
# 只对某个项目生效：放到项目里的 .cursor/skills/ 或 .claude/skills/
git clone https://github.com/lyangfan/research-survey .cursor/skills/research-survey-html
```

然后直接对 Agent 说，例如：“帮我调研 2023 年以来单细胞基础模型的进展，做成交互式 HTML 报告，并导出 Zotero 可导入的参考文献”。Agent 会按 `SKILL.md` 先确认范围，再检索、核查、整理数据并构建、截图验证。

## 用法二：独立流水线

```bash
git clone https://github.com/lyangfan/research-survey && cd research-survey
pip install -r requirements.txt && python -m playwright install chromium   # 仅截图需要

# 1) 构建示例
python scripts/build.py examples/agent-science-mini -o out/agent-science-mini.html
python scripts/screenshot.py out/agent-science-mini.html --outdir out/screens   # 可加 --chrome /usr/bin/google-chrome
python scripts/export_bibtex.py examples/agent-science-mini --out out/references

# 2) 自己的主题：检索 -> 去重筛选 -> 填数据 -> 构建
export SURVEY_MAILTO=you@example.org S2_API_KEY=... OPENALEX_API_KEY=... GITHUB_TOKEN=...   # 均可选，但强烈建议
python scripts/search_arxiv.py --query 'abs:"foundation model" AND abs:"single-cell"' --from 2023-01-01 --max 300 --out cand_arxiv.jsonl
python scripts/search_s2.py search "single-cell foundation model" --year 2023- --max 300 --out cand_s2.jsonl
python scripts/search_biorxiv.py window --from 2025-01-01 --to 2025-03-31 --category bioinformatics --kw "foundation model" --out cand_brx.jsonl
python scripts/merge_dedup.py cand_*.jsonl --out candidates.jsonl --csv screening.csv
#   在 screening.csv 里填 include=1 和 dirs，然后：
python scripts/merge_dedup.py candidates.jsonl --screened screening.csv --works-draft my-survey/works_draft.json
#   复制 examples/agent-science-mini 为 my-survey，补全 meta/works/teams/timeline/repos/narrative
python scripts/github_repos.py my-survey/repos.json
python scripts/build.py my-survey --check && python scripts/build.py my-survey -o out/my-survey.html
python scripts/screenshot.py out/my-survey.html --outdir out/screens
```

检索、去重、导出与构建脚本只依赖 **Python 3.9+ 标准库**；截图需要 `playwright`。

## 数据格式（简表，完整见 [references/data-schema.md](references/data-schema.md)）

| 文件 | 每条记录的关键字段 |
|---|---|
| `meta.json` | `title`、`check_date`、`time_range`、`directions[{key,name,en,short,color,summary,challenges}]`、`phases`、`event_categories`、`map{resolution,merge}`、`extra_refs` |
| `works.json` | `name`、`title`、`dirs[]`（首个为主方向）、`inst`、`country`（ISO2）、`date`、`status`、`peer`、`venue_type`、`authors`、`doi`、`arxiv`、`url`、`contrib`、`checked` |
| `teams.json` | `name`、`country`、`region`、`type`、`dirs[]`、`works`、`progress`(1–4)、`ach` |
| `timeline.json` | `date`、`phase`、`cat`、`title`、`desc`、`url` |
| `repos.json` | 手写 `repo`、`cat`、`what`、`arch`、`run`、`deps`、`lim`、`license_note`；抓取 `stars`、`forks`、`license`、`last_commit`、`release`、`archived` |
| `narrative/*.html` | `summary`、`scope`、`challenges`、`caveats` 四段 HTML |

## 文献检索数据源一览（详见 [references/literature-search.md](references/literature-search.md)）

| 数据源 | 用途 | 访问方式 / 限制（2026） |
|---|---|---|
| arXiv API | 预印本主力 | `export.arxiv.org/api/query`；≤1 次/3 秒、单连接；429 时退避并改用 S2/OpenAlex |
| Semantic Scholar Graph API | 跨学科检索、批量核对、引用/参考文献滚雪球 | `/paper/search`、`/search/bulk`、`/paper/batch`、`/citations`、`/references`；建议申请 key |
| OpenAlex | 全学科目录、机构与国家 | `/works?search=&filter=`；2026-02 起需免费 API key，单条 DOI 查询免费 |
| Crossref | DOI、期刊/会议信息、预印本↔正式版 | `/works/{doi}`、`query.bibliographic`；加 `mailto` |
| bioRxiv / medRxiv | 生命科学/医学预印本 | `api.biorxiv.org/details/…` 按日期窗口拉取（无关键词搜索）；`/pubs/` 查正式发表 |
| PubMed E-utilities | 生物医学 | `esearch` + `esummary`；3 次/秒（有 key 10 次/秒） |
| DBLP | CS 会议/期刊是否正式发表 | `dblp.org/search/publ/api`；遇到反爬验证改为人工 |
| OpenReview | ICLR/NeurIPS/TMLR 录用状态 | `api2.openreview.net/notes…` |
| Hugging Face Papers | 有代码的热门论文（Papers with Code 已于 2025-07 停服并跳转至此） | `huggingface.co/api/papers/<arXiv ID>` |
| Google Scholar / 知网 | 补漏、前向引用 | **仅人工**，不抓取；Zotero Connector 保存 |
| 公司/实验室博客、新闻 | 产品与未发表成果 | 标注“未经同行评审 / 公司自报” |

导出：`export_bibtex.py` 生成 `.bib`、`.ris`（方向键作为 Zotero 标签）和 `zotero_identifiers.txt`（粘贴到 Zotero“魔棒”获取最完整元数据）。

## 许可证与第三方组件

- 本仓库代码与文档：**MIT**（见 [LICENSE](LICENSE)）。
- `scripts/vendor/echarts.min.js`：Apache ECharts 5.6.0，**Apache-2.0**，含源自 d3.js 的代码（BSD-3-Clause）；见 `scripts/vendor/LICENSE-echarts.txt`、`NOTICE-echarts.txt`、`LICENSE-d3.txt` 与根目录 [NOTICE](NOTICE)。生成的 HTML 内联了该文件（保留其许可证头）。
- **世界地图数据不随仓库分发**：原始流程使用的 `world.json`（来自 ECharts 示例站点）许可证不明确，因此 `build.py` 改为在**构建时**下载 [Natural Earth](https://www.naturalearthdata.com/)（公有领域）国界数据并缓存到 `scripts/.cache/`（已 git-ignore）。也可用 `--world` 指定你自己的 GeoJSON。Natural Earth 边界按实际控制线绘制、不代表任何立场；在中国大陆正式出版请使用经审核的标准地图。
- 示例数据为真实论文/仓库的事实性元数据与自写摘要，附原始链接。

---

## English

**research-survey-html** is a topic-agnostic agent skill (SKILL.md, Cursor / Claude Code style) plus a small Python pipeline for producing a comprehensive literature/field survey as a **single self-contained, offline, interactive HTML report** (sticky TOC, timeline, taxonomy tree, filterable works table, team cards, clickable world heatmap, GitHub repo charts, references). It also documents *how to search the literature*: query design and keyword expansion; arXiv (1 req / 3 s, 429 fallback), Semantic Scholar, OpenAlex (API key since Feb 2026), Crossref, bioRxiv/medRxiv, PubMed, DBLP, OpenReview, Hugging Face Papers; snowballing; DOI/arXiv de-duplication; peer-review status labelling; verification rules; and BibTeX/RIS export for Zotero.

- Install as a skill: `git clone https://github.com/lyangfan/research-survey ~/.cursor/skills/research-survey-html` (or `~/.claude/skills/research-survey-html`; the folder name must equal the skill `name`).
- Standalone: `python scripts/build.py examples/agent-science-mini -o out/demo.html && python scripts/screenshot.py out/demo.html --outdir out/screens`.
- Only the screenshot step needs a dependency (`playwright`); everything else is standard-library Python 3.9+.
- License: MIT. Bundles Apache ECharts 5.6.0 (Apache-2.0, NOTICE included). World map: Natural Earth (public domain), downloaded at build time, not committed.
