# 开源仓库核查（Open-source repo inspection）

## 1. 找仓库
- 论文首页/摘要中的 “Code: github.com/…” 链接、项目主页、Hugging Face Papers 关联代码、GitHub 搜索（`topic:`、`in:readme`）、awesome-list。
- 同名仓库要核对 owner 与论文作者是否一致；官方仓库与社区复现要区分标注。
- **追加单个仓库**：`python scripts/github_repos.py data/repos.json --add owner/name [--add https://github.com/o/r] --cat 类别 --dirs FM,COLOC --what "一句话"`——只抓取新增的条目并合并进原文件；已在文件里的会刷新（保留手写字段）而不会重复。只刷新部分条目：`--only owner/a,owner/b`。
- **反向利用**：仓库 README 的 Citation 段、`CITATION.cff`、R 包 `inst/CITATION` 列出的论文正是该工具的方法论文，用 `python scripts/snowball.py repo-cites @data/repos.json --out sb_repo.jsonl` 收集，作为文献检索的一个来源（`found_via: repo-cite:<owner/repo>`，见 `literature-search.md` §1b）。

## 2. 抓取字段（GitHub REST API）
| 字段 | 端点 / 字段名 | 用途 |
|---|---|---|
| Stars / Forks | `GET /repos/{o}/{r}` → `stargazers_count`, `forks_count` | 热度 |
| 许可证 | `license.spdx_id`（`NOASSERTION` = 自定义/无法识别，需人工看 LICENSE 文件） | 能否商用/二次分发 |
| 最近推送 | `pushed_at`（任意分支） | 活跃度（粗）|
| 最近提交 | `GET /repos/{o}/{r}/commits?per_page=1` → `commit.committer.date`（默认分支） | 活跃度（准）|
| 最近 Release | `GET /repos/{o}/{r}/releases/latest` → `tag_name`, `published_at`（404 = 无 release） | 成熟度 |
| 归档 | `archived` | 是否停止维护 |
| 重定向 | `full_name` 与输入不同 = 仓库改名/迁移 | 用规范名 |

- **限速**：匿名 60 次/小时/IP；`export GITHUB_TOKEN=…`（只需公开仓库只读权限的 fine-grained token）后 5,000 次/小时。
- **退路**：被 403/429 限速时，`github_repos.py` 自动改为抓取公开页面 + `https://github.com/{o}/{r}/commits.atom` 与 `/releases.atom`（原始综述就是这样抓的）。这种解析依赖页面结构，可能失效，务必人工抽查几条。
- 许可证以仓库根目录 LICENSE 文件为准；自定义许可证（如含 “AI 生成论文需声明” 条款、Commons Clause、CC BY-NC）写进 `license_note`。

- 回退模式下页面没显示许可证时，脚本会读取 `raw.githubusercontent.com/<repo>/HEAD/LICENSE`（及 `LICENSE.md`、`COPYING`、R 包的 `DESCRIPTION`）推断 SPDX，并注明“from LICENSE file / from DESCRIPTION”；仍需抽查。

## 3. 活跃度分级（默认，可在 meta 中改阈值）
距检查日的最近提交天数：≤30 高度活跃；≤90 活跃；≤365 维护放缓；>365 停滞。归档仓库另加 `archived` 标签。
- “停滞”只表示很久没有提交。对功能完备、刻意保持稳定的成熟工具（如 tensorQTL、LeafCutter 这类广泛使用的方法实现），在 `repos.json` 设 `"stable": true`，表格显示“成熟稳定（低频更新）”（图表仍按天数着色），并在 `lim` 里写明维护现状。

## 1b. 没有代码的方向：不要硬凑仓库
- 湿实验/实验型方向（组织与样本采集、生物样本库、动物/细胞/类器官实验、临床队列、测序数据生产、实验方案开发）通常**不发布代码仓库**。找不到官方仓库是正常结果，不要用无关工具、通用分析包、个人脚本或社区复现充数。
- 在 `meta.directions[]` 中设 `"repo_expected": false` + 一句 `no_repo_reason`；把时间花在**非代码资源**上，写进该方向的 `resources`：数据集（dbGaP/EGA/GEO/SRA/ENA 登录号、联盟数据发布页）、实验方案（SOP、protocols.io、论文 Methods/补充材料）、数据门户与浏览器、生物样本库/样本资源（需申请的写明访问方式）。同时是门户的写进 `portals.json` 并标 `dirs`，会自动列入。
- 该方向里确有代码的工作（如配套分析流程）照常写进 `repos.json`；此时说明该方向“有代码”，去掉 `repo_expected: false`（`--check` 会提示这种矛盾）。
- 给仓库加 `dirs` 后，开源板块会按方向显示仓库数；某个方向零仓库不会报警，页面写“本报告未收录该方向的仓库”。

## 3b. 数据门户（不是仓库）
门户、数据库、在线工具（GTEx Portal、eQTL Catalogue、物种门户、网页服务器）写进 `portals.json`，不要塞进 `repos.json` 或 summary 表格。`python scripts/check_urls.py <data_dir> --only portals --write` 检查链接并把状态写回，页面显示 ✓/?/✗ 与检查日期。

## 4. 每个仓库人工填写
`what`（做什么）、`arch`（架构/主要组件）、`run`（安装与运行命令，来自 README）、`deps`（硬件/语言/API 依赖）、`lim`（局限：维护状态、许可证限制、安全风险如执行 LLM 生成代码需沙箱）。README 原文可先存到 `readmes/` 目录再摘要。
