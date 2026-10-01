# 数据格式（Data schema）

一个综述 = 一个数据文件夹。`scripts/build.py <data_dir> -o survey.html` 读取以下文件；除 `meta.json` 外都可缺省（缺省的板块自动隐藏，章节编号与目录自动重排）。完整示例见 `examples/agent-science-mini/`。

```
<data_dir>/
  meta.json          标题、时间范围（仅用户指定时）、方向（taxonomy）、阶段、颜色、地图设置……
  works.json         代表性工作（论文/预印本/博客/产品）
  teams.json         团队/机构
  timeline.json      时间轴事件
  repos.json         开源仓库（手写字段 + github_repos.py 抓取字段；所有方向都 repo_expected=false 时可省略）
  portals.json       数据门户/数据库/在线工具（可选；check_urls.py 写入链接状态）
  narrative/
    summary.html     执行摘要（HTML 片段，可用 .kf-grid/.kf 卡片、<b id="s-works"></b> 自动填数字）
    scope.html       范围（时间范围：用户指定的范围或“未设时间限制”）、方法、计数口径
    challenges.html  开放挑战与趋势（可用 .two-col / ol.nice）
    caveats.html     注意事项与未核实项
```

日期一律 `YYYY`、`YYYY-MM` 或 `YYYY-MM-DD`；国家一律 **ISO 3166-1 alpha-2**（`US`、`CN`、`GB`…，中文名见 `scripts/countries.py`，可扩展）。

## meta.json

| 字段 | 必填 | 说明 |
|---|---|---|
| `title` | ✔ | 页面标题（`<title>`）|
| `title_html` | | 大标题 HTML，可用 `<span>` 渐变高亮 |
| `kicker` / `subtitle` | | 顶部小标签 / 副标题（HTML）。`kicker` 缺省时自动生成：有 `time_range` 显示 `RESEARCH SURVEY · 起 – 止`，没有则只显示 `RESEARCH SURVEY` |
| `lang` | | `zh-CN`（默认）或 `en`，决定界面文案；`labels` 可逐项覆盖（键见 `build.py` 的 `LABELS`）|
| `check_date` | ✔ | 资料核查日期，也是仓库活跃度的基准日 |
| `time_range` | | **仅当用户明确指定了时间范围时填写**，如 `{"start":"2024-01","end":"2026-10"}`（可只写 `start` 或 `end`）；决定柱状图横轴，`--check` 会提示落在范围外的条目。**没有默认值**：用户没指定就整个省略，表示未设时间限制，此时柱状图横轴按数据中最早到最晚年份自动确定，页面不显示时间段 |
| `period` | | `half` / `year` / `quarter`。省略时按数据跨度自动选：>6 年用 `year`，只有 1 年用 `quarter`，否则 `half` |
| `taxonomy_root` | | 树图根节点文字（可含 `\n`）|
| `directions` | ✔ | `[{key,name,en,short,color,summary,challenges}]`；`key` 用短英文大写（`LIT`），`summary/challenges` 可含 HTML。可选：`repo_expected`、`no_repo_reason`、`resources`（见下）|
| `phases` | | `[{key:"P1",title,desc}]` 时间轴阶段卡片 |
| `event_categories` | | `{类别名: 颜色}`；未列出的类别自动配色 |
| `progress_levels` | | 4 个进展等级文案（团队卡片）|
| `activity_thresholds` | | 默认 `[30,90,365]` 天 |
| `radar_countries` | | 雷达图对比的国家，默认团队数前三 |
| `repo_top_n` / `tree_leaves` | | Stars 图条数（默认 30）/ 树图每个方向的叶子数（默认 4）|
| `tree_sort` | | 树图里补位的普通叶子怎么选（主方向的 `featured: true` 作品**总是先放**）：`auto`（默认：works 有 `citations` 就按被引数；否则未设时间范围时用 `spread`，设了时间范围用 `recent`）/ `citations` / `spread`（同行评审作品按时间均匀取样，早期里程碑与近期工作都在）/ `recent`（同行评审优先、最新优先）|
| `tree_cross` | | `fill`（默认）= 本方向主方向作品不够 `tree_leaves` 时，用交叉标注（`dirs` 里有该方向但不是第一个）的作品补空位，显示为虚线灰色叶子；`none` = 不补 |
| `tree_featured_overflow` | | `show`（默认）= 主方向里程碑超过 `tree_leaves` 也全部画出；`cap` = 最多画 `tree_leaves` 个（按日期），其余计入“+N 篇”叶子 |
| `map` | | `{"resolution":"110m"|"50m","merge":{"TW":"CN"},"drop":["AQ"],"zoom":1.2,"center":[lon,lat],"geojson":"path"}` |
| `country_names` | | 覆盖国家显示名 `{ "HK": "中国香港" }` |
| `extra_refs` | | `[{title,url,note}]` 额外参考资料（博客、新闻）|
| `footer` | | 页脚文字 |

### 没有代码仓库的方向（`directions[]` 可选字段）

湿实验/实验型方向（样本采集与组织库、动物或细胞实验、临床队列、测序数据生产等）通常不发布代码，不要为它们硬凑仓库。

| 字段 | 说明 |
|---|---|
| `repo_expected` | `false` = 该方向按惯例不发布代码仓库（默认 `true`）。别名：`"no_repo": true` 或 `"no_repo": "原因"` |
| `no_repo_reason` | 一句话原因，显示在开源板块和方向卡片上；缺省为“该方向以湿实验为主，通常不发布代码仓库。” |
| `resources` | 非代码资源 `[{name, url, kind, note}]`（`kind` 如 `数据集`、`实验方案`、`数据门户`、`生物样本库`；也可只写名称字符串）。`portals.json` 中 `dirs` 含该方向的门户会自动补进来；有 URL 的资源加入参考文献 |

效果：开源板块出现“各方向开源情况”（仓库带 `dirs` 时，每个方向显示仓库数，点击筛选表格）或“以实验为主、不发布代码仓库的方向”（仓库不带 `dirs` 时只列这些方向），无代码方向只显示说明 + 资源清单，不显示空的图表/表格条目；一个仓库都没有时板块只保留这些说明。`--check`：方向没有仓库**不报警**（无论是否标记）；`repo_expected` 不是布尔值、`resources` 缺 `name` 报 error，缺 `url` 提示；仓库的 `dirs` 指向标了 `repo_expected: false` 的方向会提示矛盾。

```json
{"key": "BIO", "name": "组织样本采集与生物样本库", "short": "样本库", "repo_expected": false,
 "no_repo_reason": "该方向以湿实验与样本采集为主，通常不发布代码仓库。",
 "resources": [{"name": "GTEx Tissue Harvesting SOP", "url": "https://…", "kind": "实验方案"},
               {"name": "dbGaP phs000424", "url": "https://…", "kind": "数据集", "note": "受控访问"}]}
```

## works.json（每条一项工作）

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | ✔ | 表格中显示的简称（可中文）|
| `title` | | 原文完整标题（用于 BibTeX 与悬停提示）|
| `dirs` | ✔ | 方向键列表 `["IDEA","LIT"]`，**第一个为主方向**（柱状图、树图里程碑按主方向计）|
| `primary_dir` | | 可选，显式指定主方向（覆盖 `dirs` 第一个；不在 `dirs` 里时自动加入并提示）|
| `inst` | | 机构（第一/主导机构在前，`/` 分隔）；查不到写 `—（未核实）` |
| `country` | | 第一或主导机构国家代码；未核实留空（不计入地图）|
| `date` | ✔ | **首次公开日期**：预印本 **v1** 日期优先（`search_biorxiv.py doi` 的 `date`），否则期刊**在线**日期（不是纸质刊期；可用 `search_crossref.py doi` 的 `date_online` 核对）|
| `status` | ✔ | 发表状态文字，如 `ICLR 2025`、`arXiv 预印本`、`Nature（2025-09-23）` |
| `peer` | ✔ | 是否同行评审（bool）|
| `venue_type` | | `journal|conference|preprint|blog|product|report`（导出 BibTeX/RIS 用）|
| `venue` | | 规范 venue 名 |
| `authors` | | **全部**作者（导出用），不要截断成 “et al.”。“Smith AB”（PubMed）、“Smith, Anna B.”、“Anna B. Smith” 均可；联盟作者写原名（如 `GTEx Consortium`），导出为单个机构作者 |
| `corporate_author` | | 字符串或列表：作为机构作者放在作者列表最前（如 `"FarmGTEx Consortium"`），已在 `authors` 中的不重复 |
| `featured` | | `true` = 里程碑/旗舰工作：在**主方向**的树枝上一定显示（见 `tree_featured_overflow`）、名称前加 ★、可用“★ 仅里程碑”筛选 |
| `doi` / `arxiv` | | 标识符（去重、导出、Zotero 魔棒）；已发表的工作写**正式版** DOI |
| `preprint_doi` / `preprint_url` / `preprint_date` | | 已发表工作对应的预印本（bioRxiv `10.1101/…` / `10.64898/…`、Research Square 等）及其 v1 日期；表格显示“[预印本]”链接，导出写进 note。`merge_dedup.py` 会自动填（另有 `preprint_server`、`preprint_dois`、`link_method`，可保留也可删）|
| `found_via` | 建议 | 这条工作是哪些检索策略找到的，列表：`kw:<source>`（关键词检索）、`name`（具名检索）、`snowball:refs` / `snowball:cites`、`repo-cite:<owner/repo>`、`page:<host>`、`must`（必收清单）、`manual`（手工补充）。`merge_dedup.py --works-draft` 自动带出；`build.py` 打印汇总，`recall_check.py coverage` 据此出各方向来源构成表 |
| `pmid` / `citations` | | PubMed ID / 被引数（带抓取日期写进 note；`tree_sort: citations` 用）|
| `url` | ✔ | 可点击链接 |
| `contrib` | | 一句话核心贡献（中文）|
| `checked` | 建议 | 核查日期 |
| `note` / `volume` / `pages` | | 备注 / 卷 / 页码 |

## teams.json

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | ✔ | 团队名（实验室/公司/课题组）|
| `country` | ✔ | 计数国家代码（口径见 `taxonomy-and-teams.md`）|
| `region` | | 显示用地区（如 `中国（香港）`），缺省用国家中文名 |
| `type` | ✔ | 高校 / 企业 / 企业研究院 / 创业公司 / 非营利研究机构 / 政府/国家实验室 … |
| `dirs` | ✔ | 方向键列表 |
| `works` | | 代表作（字符串或列表）|
| `progress` | ✔ | 1–4 进展等级 |
| `ach` | | 主要进展（有来源的事实）|
| `url` | | 团队主页 |

## portals.json（可选：数据门户、数据库、在线工具）

与 `repos.json` 分开：门户不是代码仓库，没有 stars，但对数据驱动的领域（如 GTEx Portal、eQTL Catalogue、各物种 FarmGTEx 站点）是核心资源。存在且非空时页面显示“数据门户与资源”板块，并把门户加入参考文献。

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` / `url` | ✔ | 名称 / 链接 |
| `kind` | | 类型，如 `数据门户`、`数据库`、`在线工具`、`浏览器`、`联盟网站`（用于筛选标签）|
| `org` | | 维护机构 |
| `scope` | | 覆盖范围/提供的数据（物种、组织、样本数、数据类型）|
| `access` | | 访问方式与许可（网页浏览、下载、需申请 dbGaP/AnVIL 等）|
| `dirs` / `launched` / `works` / `desc` / `note` | | 方向键 / 上线时间或版本 / 相关代表作 / 说明 / 备注 |
| `url_status` / `url_http` / `url_checked` | | 由 `check_urls.py <data_dir> --only portals --write` 写入：`ok` / `blocked`（拒绝脚本，需人工看）/ `dead`；页面显示为 ✓ / ? / ✗ |

## timeline.json

`[{date, phase, cat, title, desc, url}]`，`phase` 对应 `meta.phases[].key`，`cat` 对应 `meta.event_categories`。

## repos.json

手写字段：`repo`（owner/name）、`cat`、`dirs`（可选，方向键列表；有了它开源板块按方向统计仓库数并可按方向筛选，未知方向报 error）、`what`（做什么）、`arch`（架构/组件）、`run`（如何运行）、`deps`（依赖）、`lim`（局限）、`license_note`（人工核对后的许可证说明，优先于抓取值）、`exclude`（true 则不展示）、`stable`（true = 功能完备、刻意低频更新的成熟工具：超过停滞阈值时表格显示“成熟稳定（低频更新）”而不是“停滞”）。

抓取字段（`github_repos.py` 写入，保留手写字段）：`canonical`、`stars`、`forks`、`license`、`pushed_at`、`last_commit`、`release:{tag,date}`、`archived`、`description`、`fetched_at`、`fetch_method`（`api` 或 `html+atom`）。

## 候选记录（JSONL，检索脚本的输出）

`{source,title,authors,date,venue,doi,arxiv,pmid,url,abstract,citations,checked,...}` —— 生命科学脚本另有 `affiliation`、`country_guess`（仅提示，需人工确认）、`mesh`、`date_print`/`date_epub`；`merge_dedup.py` 合并后再加 `sources`、`status_guess`、`venue_guess`、`found_via`，以及预印本合并字段 `preprint_doi`/`preprint_url`/`preprint_date`/`preprint_server`/`preprint_dois`/`link_method`（疑似未合并的在 `possible_published`）。Crossref 记录有 `is_preprint_of`/`has_preprint`，bioRxiv `doi` 模式有 `date_v1`/`date_latest`/`versions`/`published`，Europe PMC 有 `published_pmid`/`preprint_epmc_ids`，`snowball.py` 输出有 `seeds`/`seed_count`，OpenAlex 的 Crossref 回退记录有 `fallback_for`。
