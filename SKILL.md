---
name: research-survey-html
description: Use when the user asks for a comprehensive literature or field survey (调研/综述/领域梳理) on any research topic, delivered as a visual, interactive, self-contained HTML report — includes how to search and verify literature, build taxonomy/teams/map/portal/repo sections, export references to Zotero, and screenshot-check the result.
---

# 研究领域调研 → 交互式 HTML 报告

把“某个研究方向的进展”做成一份**可核查、可交互、离线可用**的单文件 HTML 综述：时间轴、方向分类树、可筛选的代表作表、团队卡片、世界热力图（点击国家看名单）、数据门户表、开源仓库图表、参考文献，并导出 BibTeX/RIS 供 Zotero 导入。

本文件所在目录记为 `SKILL_DIR`。脚本在 `SKILL_DIR/scripts/`，详细说明在 `SKILL_DIR/references/`，示例数据在 `SKILL_DIR/examples/agent-science-mini/`。检索与构建只依赖 Python 3.9+ 标准库；截图需要 `playwright`。

## 0. 先问清范围（一次问完；除时间范围外，用户没说的给默认值并写进报告）
1. **主题**与边界（包含/不包含什么，相邻领域怎么处理），以及**所属学科**（决定用哪套数据源，见第 1 步）。
2. **时间范围**：**没有默认值，不要自行加任何时间限制**（不要默认“最近几年”，也不要主动提议某个时间窗口）。
   - 只有用户**明确给出**时间范围（如“2023 年以来”“近三年”“2024-01 至今”）时，才把它换算成具体日期（相对说法以今天为基准），写进 `meta.time_range`，并作为约束用于检索（`--from/--to`、`--year`、各数据源的日期语法）和筛选。
   - 用户没提：检索时**不传任何日期参数**、筛选时**不按日期排除**，早期与近期工作一视同仁，按相关性与重要性取舍；`meta.json` 不写 `time_range`。
   - 报告“范围与方法”写明：用户指定的时间范围，或“未设时间限制”。
3. **是否收录预印本**（默认收录，逐条标注状态）；是否收录博客/产品/新闻。
4. **输出语言**（默认与用户一致，如简体中文 + 英文术语）与读者（导师、组会、自己入门）。
5. **规模与板块**：代表作数量（默认 50–150）、是否需要团队/地图/数据门户/开源仓库板块；输出路径；是否导出 Zotero。

## 1. 查文献（如何查文献）→ 详见 [references/literature-search.md](references/literature-search.md)
**只靠关键词检索是不够的**：经典方法论文的标题/摘要往往不含领域的总称（如 “post-GWAS”），按相关性只取前几百条时大量里程碑工作根本不在池中（post-GWAS 实测：关键词检索只覆盖了预先列出的 148 篇必收工作中的 52 篇，35%）。因此第 1 步必须按下面的**多策略检索流程**做，每个策略的产出都要记 `found_via`，并在“范围与方法”里报告召回率。

1. **拆方向 + 写必收清单（检索之前）**：先把领域拆成 6–12 个方向，每个方向列出**具名**的方法/工具/数据集/联盟/资源（如精细定位：SuSiE、FINEMAP、CAVIAR、PolyFun；共定位：coloc、eCAVIAR、enloc），再凭自己的领域知识写 `must_include.tsv`（`name / doi / title / dir / note`，每方向 5–15 篇奠基与里程碑工作，DOI 不确定就只写标题）。`scripts/recall_check.py verify must_include.tsv --out must_verified.tsv --jsonl cand_must.jsonl` 逐条到 Crossref/Europe PMC 核对（DOI 是否存在、标题是否一致；只有标题的解析出 DOI）；`doi_not_found`/`title_mismatch` 要改正或删除，**不能凭记忆收录未核实的条目**。
2. **设计检索式并记日志**：拆成 2–4 个概念块，每块扩展同义词/缩写/上下位词/中文词；从种子论文和综述反向抽词；按各数据源语法分别改写。先 `export SURVEY_QUERY_LOG=search_log.tsv`：所有检索脚本（PubMed/Europe PMC/S2/OpenAlex/arXiv/Crossref/bioRxiv 窗口/滚雪球/召回检查）把每条检索式**逐字**、命中总数和时间追加进去（写进“范围与方法”）；按 DOI/ID 的逐条核验写进单独的 `verify_lookups.tsv`（`$SURVEY_LOOKUP_LOG`，默认与检索日志同目录），不污染检索日志。
3. **按学科选数据源做关键词检索**（脚本输出统一 JSONL 候选；日期参数一律可选、默认不做日期过滤，**只有用户指定了时间范围**才加 `--from/--to`，S2 用 `--year`）：
   - **生命科学/医学**：PubMed `scripts/search_pubmed.py '…[tiab] OR …[mh]' --max 1000`（按相关性分页取回，自动取摘要/第一单位/MeSH，打印总命中数和 MeSH 映射）；Europe PMC `scripts/search_europepmc.py search '…'`（含期刊 + 预印本、单位与被引数；`--preprints` = `SRC:PPR`，是按关键词找 bioRxiv/medRxiv 的入口；`--sort "CITED desc"`，字段写错会直接报错而不是 503）；bioRxiv/medRxiv `scripts/search_biorxiv.py doi …`（`date` = **v1 首发日**，另给 `date_latest`/`versions`、通讯单位、`published` 正式版 DOI；窗口模式要扫全库，不适合无时间限制的关键词检索）；联盟/项目官网的 Publications 页与数据门户（门户写进 `portals.json`）；按需 OpenAlex/Crossref。联盟作者（如 “GTEx Consortium”）用 PubMed `[cn]` 检索。
   - **计算机/AI**：arXiv `scripts/search_arxiv.py --query 'abs:"…" AND cat:cs.AI'`（**≤1 次/3 秒、单连接**；持续 429 就停）；Semantic Scholar `scripts/search_s2.py search|bulk|batch|refs|cites`（建议设 `S2_API_KEY`；429 会退避重试，仍失败则保存已取到的结果并以退出码 2 结束，改用 OpenAlex/Europe PMC）；DBLP、OpenReview 核对会议录用；Hugging Face Papers 找有代码的工作。
   - **通用/其他学科**：OpenAlex `scripts/search_openalex.py search …`（2026-02 起需 `OPENALEX_API_KEY`；无 key 或额度耗尽时**自动改用 Crossref 免 key 检索**（`--fallback crossref`，记录带 `fallback_for: openalex`，日志记为 `crossref-fallback`），单条 DOI 查询免费）、Crossref `scripts/search_crossref.py doi|title …`（设 `SURVEY_MAILTO`）、S2；再加该学科自己的数据库。
   - Google Scholar、知网：**只人工检索**，不写爬虫；用 Zotero Connector 保存。公司/实验室博客、新闻：用 WebSearch/WebFetch，标为“未经同行评审/公司自报”。
4. **按名称检索（必做）**：对第 1 步列出的每个具名方法/工具/数据集/联盟单独检索（`TITLE:"LD score regression"`、`SuSiE fine-mapping`、`coloc Bayesian colocalization`、`"GTEx Consortium"[cn]`），文件名用 `name_*.jsonl` 以便标记来源。post-GWAS 实测：多效性方向关键词检索 0/10，7 条名称检索后 5/10。
5. **滚雪球（必做）**：以 3–10 篇权威综述/里程碑为种子，`scripts/snowball.py refs <DOI…> --out sb_refs.jsonl`（后向：Europe PMC 免 key → Crossref 参考文献 → S2 → OpenAlex，`--via all` 合并所有来源）、`scripts/snowball.py cites <DOI…> --max 300 --min-seeds 2 --out sb_cites.jsonl`（前向，找新工作；被多个种子共同引用/共同引用多个种子的排前面）。post-GWAS 实测：3 篇精细定位/后 GWAS 综述的后向滚雪球把必收清单召回率从 35% 提到 51%，精细定位方向 15/15。
6. **挖掘门户、文档与仓库（必做）**：`scripts/snowball.py page-ids <URL…>` 从联盟/门户的 Publications 页、工具文档的 “How to cite” 页提取 DOI/PMID/arXiv ID；`scripts/snowball.py repo-cites owner/repo … | @repos.json` 从 GitHub README 的 Citation 段、`CITATION.cff`、R 包 `inst/CITATION` 提取“请引用”的论文。JS 渲染的页面用浏览器/WebFetch 读出来，把 DOI 存成文本再处理。
7. **合并去重与筛选**：`scripts/merge_dedup.py cand_*.jsonl name_*.jsonl sb_*.jsonl cand_must.jsonl --found-via 'name_*=name' --out candidates.jsonl --csv screening.csv [--csv-sort citations] [--link-online]` → 在 CSV 中填 `include=1`、`dirs`（**第一个为主方向**），里程碑填 `featured=1` → `--screened screening.csv --works-draft works_draft.json` 生成 works 草稿（带 `found_via`）。去重键：DOI（非 arXiv DOI）> arXiv ID > 规范化标题。**预印本与正式版合并为一条**：依次用 bioRxiv `published`/Crossref `is-preprint-of`/`has-preprint`/Europe PMC “Preprint of/in” 链接、同标题 + 共同作者或同第一作者 + 标题相似度 ≥0.90 的模糊匹配，`--link-online` 再查 Crossref 与 bioRxiv API；合并后正式版 DOI 为 `doi`，预印本 DOI/URL/日期存 `preprint_doi`/`preprint_url`/`preprint_date`，`date` 取最早公开日期，`link_method` 说明依据，疑似但未合并的写在 `possible_published` 列供人工确认。只有用户指定了时间范围才按日期排除条目。
8. **召回率与饱和度（必做，写进报告）**：`scripts/recall_check.py recall --must must_verified.tsv --pool keyword='pm_*.jsonl,ep_*.jsonl' --pool names='name_*.jsonl' --pool snowball='sb_*.jsonl' --out recall.tsv` 按策略（累计）和方向报告必收清单的召回率并列出所有策略都漏掉的条目（按名称再找，找不到才手工补并记 `found_via: ["manual"]`）；`recall_check.py saturation --round r1=… --round 'r2-names@PLEIO=…' --relevant screening.csv` 判断每个方向是否饱和（≥2 轮针对该方向的检索，且最后一轮新增相关条目 <5%），未饱和的方向继续按名称检索/从最新相关工作滚雪球；成稿后 `recall_check.py coverage <data_dir> --kw-pool '…'` 输出各方向的来源构成表（可直接贴进 `scope.html`）。
9. **标注状态**：`peer: true` 仅限官方渠道可查的期刊/会议（含 workshop，需写明）；预印本、博客、产品、公司自报一律 `peer: false` 并在 `status` 写清楚；预印本 DOI 前缀：bioRxiv/medRxiv `10.1101/YYYY.MM.DD.…`（2025-11 前）与 `10.64898/…`（2025-12-01 起），以及 Research Square、SSRN、Preprints.org、ChemRxiv、arXiv 等（`common.PREPRINT_DOI_PREFIXES`），`build.py --check` 会提示 `peer: true` 却是预印本 DOI 的条目；只有作者自述的录用写“据 README，未核对官方名单”。
10. **核查规则**：绝不编造；每条要有可点击 `url` 和 `checked` 日期；`date` = **首次公开日期**（预印本取 **v1** 日期——`search_biorxiv.py doi` 的 `date`，不是最新版本；期刊取在线日期，不是纸质刊期，可用 `search_crossref.py doi` 的 `date_online` 核对）；机构/国家查不到写“—（未核实）”、`country` 留空、不计入地图（脚本给的 `country_guess` 只是提示）；动态数字注明抓取日期；最终抽查 10%。
11. **导出 Zotero**：`scripts/export_bibtex.py <data_dir> --out out/references` → `.bib`、`.ris`（方向键成为标签）和 `zotero_identifiers.txt`（粘贴到 Zotero“魔棒”最完整）。`authors` 写**全部作者**、不要写 “et al.”；“Smith AB”（PubMed 格式）、“Anna B. Smith”、“Smith, Anna” 都能正确导出；联盟作者（“GTEx Consortium”）或 `corporate_author` 字段导出为单个机构作者。

## 2. 方向分类、团队与国家 → 详见 [references/taxonomy-and-teams.md](references/taxonomy-and-teams.md)
- 自下而上卡片分组 + 对照 2–4 篇综述命名；6–12 个方向，可交叉，但 `dirs` 第一个为**主方向**；每个方向写现状与主要难题；按里程碑划 3–6 个阶段。
- **里程碑**：每个方向挑 1–3 个奠基/旗舰工作标 `"featured": true`（不超过 `tree_leaves`）。树图每个方向的叶子：① 以该方向为**主方向**（`dirs` 第一个，或 `primary_dir`）的里程碑全部显示；② 再按 `meta.tree_sort` 补本方向的其他工作（默认 `auto`：有 `citations` 按被引数，没有时间范围时按时间均匀取样，否则取最新）；③ 交叉标注的工作只填剩余空位（虚线灰色，`meta.tree_cross: "none"` 可关闭）；④ 放不下的显示为“+N 篇 → 代表作表”叶子（点击筛选表格）。所以一个工作只会以里程碑身份出现在它的主方向下，不会挤掉别的方向的里程碑。
- 团队粒度到课题组/研究部门；进展等级 1–4；只写有来源的事实。
- 国家用 ISO alpha-2。**团队数**按团队主要所在地（跨国公司按成果主要团队所在地）；**代表作数**按第一/主导机构（联盟论文按牵头/通讯单位，无法唯一确定则不计）；地区口径（如香港）写进报告，地图可用 `map.merge` 合并。

## 3. 数据门户与开源仓库 → 详见 [references/repo-inspection.md](references/repo-inspection.md)
- **数据门户/数据库/在线工具 ≠ 代码仓库**：写进 `portals.json`（名称、URL、类型、机构、覆盖范围、访问方式），用 `scripts/check_urls.py <data_dir> --only portals --write` 做存活检查（HEAD→GET、带超时；结果显示在报告里），也可 `check_urls.py <data_dir>` 检查全部链接（出版商 cookie 重定向循环会带 cookie 重试，仍循环则记为 blocked 而不是 dead）。
- 仓库：`scripts/github_repos.py <data_dir>/repos.json`（追加单个仓库：`--add owner/name --cat … --dirs FM --what "…"`，只抓取新增的条目，已存在的会刷新而不重复；只刷新部分：`--only a/b,c/d`）：GitHub API 取 stars、forks、`license.spdx_id`、`pushed_at`、默认分支最近提交、latest release、archived（设 `GITHUB_TOKEN`；匿名 60 次/小时）；被限速时自动回退到公开页面 + Atom，并从原始 LICENSE/DESCRIPTION 文件推断许可证。人工补 `what/arch/run/deps/lim`，自定义许可证写 `license_note`，可加 `dirs`（方向键）让报告显示“各方向开源情况”。活跃度：≤30/90/365 天分四档；功能已完备、刻意低频更新的成熟工具设 `"stable": true`，表格显示“成熟稳定”而不是“停滞”。
- **不是每个方向都有代码**：湿实验/实验型方向（样本采集、组织库、动物/细胞实验、临床队列等）通常不发布代码仓库，**不要硬凑仓库**（不要把无关工具、个人脚本或社区复现塞进去充数）。在 `meta.directions[]` 里给这类方向设 `"repo_expected": false` 和一句 `no_repo_reason`，改为收集**非代码资源**写进该方向的 `resources`（数据集、实验方案/protocols、数据门户、生物样本库，`{name,url,kind,note}`）；打了该方向 `dirs` 的门户会自动列入。报告的开源板块对这些方向只显示一句说明和资源清单，不显示空条目；`--check` 不会因方向没有仓库而报警（某方向零仓库本身也不会报警）。整个主题都是湿实验时可以不写 `repos.json`。

## 4. 生成 HTML → 详见 [references/data-schema.md](references/data-schema.md)、[references/html-build-and-verify.md](references/html-build-and-verify.md)
1. 新建数据目录（可复制 `examples/agent-science-mini/` 再替换内容）：`meta.json`、`works.json`、`teams.json`、`timeline.json`、`repos.json`、可选 `portals.json`、`narrative/{summary,scope,challenges,caveats}.html`。
2. 写 narrative：执行摘要（5–8 条关键发现，每条有事实和来源）、范围与方法（时间范围：用户指定的范围或“未设时间限制”；来源、检索式与命中数；**用了哪些检索策略**（关键词/名称检索/滚雪球/门户与仓库挖掘/必收清单/手工补充）、**关键词检索对必收清单的召回率**（总体与各方向）、各方向饱和情况与来源构成表；预印本与正式版的合并规则；状态标注、计数口径、核查日期与时区）、挑战与趋势、注意事项与未核实项（含失效链接）。
3. `python scripts/build.py <data_dir> --check`，修完 error、看过 warning 后 `python scripts/build.py <data_dir> -o out/survey.html`。输出单个自包含 HTML（内联 ECharts 与地图，离线可用）；缺省的板块自动隐藏、目录自动编号；未写 `meta.period` 时柱状图按数据跨度自动选年/半年/季度。

## 5. 截图验证（交付前必做）
`python scripts/screenshot.py out/survey.html --outdir out/screens`：浏览器依次尝试 Playwright 自带 Chromium → 缓存目录里的其他 Chromium 版本/headless shell → 系统 Chrome/Chromium → 自动执行 `python -m playwright install chromium`（`--no-install` 关闭；也可 `--chrome PATH`）；检查 console 报错、横向溢出、空图表，截取首屏和**所有可见板块**（含摘要、范围、趋势、注意事项），长板块另按视口切成 `_p1/_p2…` 便于阅读。**逐张查看**：中文无方块字、地图着色且点击面板有内容、所有图表渲染、表格行数正确、长标签没有被截断；代表作表的日期与标题不重叠（窄屏下自动变为卡片，可用 `--width 800` 再截一次）；无代码方向在开源板块显示说明而不是空条目。有问题修数据/模板后重建。

## 6. 交付
给用户：HTML 路径、截图、`references.bib/.ris`、数据目录（便于以后增补）、检索日志（`search_log.tsv`）、核验日志（`verify_lookups.tsv`）、必收清单与召回率表（`must_verified.tsv`、`recall.tsv`）；在回复里说明核查日期（带时区）、收录规模、主要局限与未核实项。

## 注意事项 → 详见 [references/quality-checklist.md](references/quality-checklist.md)
- 收录偏向英文与高影响力来源，地图/排名只代表样本；预印本状态、门户可用性与星标会变，以核查日期为准。
- 不抓取 Google Scholar，不绕过限速/反爬；API 规则会变化，以官方文档为准。
- 媒体与公司自报数字要标注来源；不要把预印本写成“已发表”。
- Natural Earth 地图边界不代表政治立场；在中国大陆正式出版请用经审核的标准地图（`--world`）。首次构建需联网下载地图（之后用缓存），离线环境用 `--world`。
- 内联的 ECharts 为 Apache-2.0，分发 HTML 时保留其版权声明（模板已含注释，见 NOTICE）。
