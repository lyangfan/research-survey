# 数据格式（Data schema）

一个综述 = 一个数据文件夹。`scripts/build.py <data_dir> -o survey.html` 读取以下文件；除 `meta.json` 外都可缺省（缺省的板块自动隐藏，章节编号与目录自动重排）。完整示例见 `examples/agent-science-mini/`。

```
<data_dir>/
  meta.json          标题、时间范围（仅用户指定时）、方向（taxonomy）、阶段、颜色、地图设置……
  works.json         代表性工作（论文/预印本/博客/产品）
  teams.json         团队/机构
  timeline.json      时间轴事件
  repos.json         开源仓库（手写字段 + github_repos.py 抓取字段）
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
| `period` | | `half`（默认）/ `year` / `quarter` |
| `taxonomy_root` | | 树图根节点文字（可含 `\n`）|
| `directions` | ✔ | `[{key,name,en,short,color,summary,challenges}]`；`key` 用短英文大写（`LIT`），`summary/challenges` 可含 HTML |
| `phases` | | `[{key:"P1",title,desc}]` 时间轴阶段卡片 |
| `event_categories` | | `{类别名: 颜色}`；未列出的类别自动配色 |
| `progress_levels` | | 4 个进展等级文案（团队卡片）|
| `activity_thresholds` | | 默认 `[30,90,365]` 天 |
| `radar_countries` | | 雷达图对比的国家，默认团队数前三 |
| `repo_top_n` / `tree_leaves` | | Stars 图条数（默认 30）/ 树图每个方向的叶子数（默认 4）|
| `map` | | `{"resolution":"110m"|"50m","merge":{"TW":"CN"},"drop":["AQ"],"zoom":1.2,"center":[lon,lat],"geojson":"path"}` |
| `country_names` | | 覆盖国家显示名 `{ "HK": "中国香港" }` |
| `extra_refs` | | `[{title,url,note}]` 额外参考资料（博客、新闻）|
| `footer` | | 页脚文字 |

## works.json（每条一项工作）

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | ✔ | 表格中显示的简称（可中文）|
| `title` | | 原文完整标题（用于 BibTeX 与悬停提示）|
| `dirs` | ✔ | 方向键列表 `["IDEA","LIT"]`，**第一个为主方向**（柱状图按主方向计）|
| `inst` | | 机构（第一/主导机构在前，`/` 分隔）；查不到写 `—（未核实）` |
| `country` | | 第一或主导机构国家代码；未核实留空（不计入地图）|
| `date` | ✔ | 首次公开日期（预印本日期优先）|
| `status` | ✔ | 发表状态文字，如 `ICLR 2025`、`arXiv 预印本`、`Nature（2025-09-23）` |
| `peer` | ✔ | 是否同行评审（bool）|
| `venue_type` | | `journal|conference|preprint|blog|product|report`（导出 BibTeX/RIS 用）|
| `venue` | | 规范 venue 名 |
| `authors` | | 作者列表（导出用）|
| `doi` / `arxiv` | | 标识符（去重、导出、Zotero 魔棒）|
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

## timeline.json

`[{date, phase, cat, title, desc, url}]`，`phase` 对应 `meta.phases[].key`，`cat` 对应 `meta.event_categories`。

## repos.json

手写字段：`repo`（owner/name）、`cat`、`what`（做什么）、`arch`（架构/组件）、`run`（如何运行）、`deps`（依赖）、`lim`（局限）、`license_note`（人工核对后的许可证说明，优先于抓取值）、`exclude`（true 则不展示）。

抓取字段（`github_repos.py` 写入，保留手写字段）：`canonical`、`stars`、`forks`、`license`、`pushed_at`、`last_commit`、`release:{tag,date}`、`archived`、`description`、`fetched_at`、`fetch_method`（`api` 或 `html+atom`）。

## 候选记录（JSONL，检索脚本的输出）

`{source,title,authors,date,venue,doi,arxiv,pmid,url,abstract,citations,checked,...}` —— `merge_dedup.py` 合并后再加 `sources`、`status_guess`、`venue_guess`。
