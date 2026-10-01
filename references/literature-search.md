# 如何查文献（Literature Search Playbook）

目标：在给定主题内（如用户明确指定了时间范围，则在该范围内），**尽量完整、可复核**地找到代表性工作，并为每条记录留下来源、标识符（DOI / arXiv ID / PMID）、发表状态与核查日期。

> **时间范围规则**：本技能**没有默认时间范围**。只有用户明确要求时，才把时间范围作为约束加到检索（下文各数据源的日期参数/语法）和筛选中；用户没提就不加任何日期过滤，也不按年份排除条目。下文出现的日期参数与日期语法都只是“用户指定了时间范围时”的写法示例。报告“范围与方法”写明用户指定的范围，或“未设时间限制”。

> 适用的 API 限制与行为在 2026 年会变化（例如 OpenAlex 自 2026-02 起要求 API key）。遇到与本文不一致的情况，以官方文档为准，并在报告“范围与方法”中写明实际做法。

---

## 1. 检索式设计与关键词扩展（Query design）

1. **拆概念（PICO 风格）**：把主题拆成 2–4 个概念块，例如 “智能体（agent）” × “科学发现（scientific discovery）” × “实验/实验室（experiment / laboratory）”。块内用 OR，块间用 AND。
2. **同义词扩展**（每个概念块 5–15 个词）：
   - 英文同义词、缩写、旧称/新称（`LLM agent` / `language agent` / `autonomous agent` / `AI scientist` / `co-scientist`）。
   - 上位词与下位词（`self-driving lab`、`autonomous laboratory`、`closed-loop experimentation`）。
   - 中文关键词（用于知网 / 万方 / 中文媒体）：同样列出同义词表。
   - 从“种子论文”的标题、摘要、作者关键词和 arXiv 分类中**反向抽词**；从综述论文的分类体系中抽方向名。
3. **写成各数据源的语法**（同一检索式要“翻译”多次）：

| 数据源 | 语法要点 | 例子 |
|---|---|---|
| arXiv | 字段前缀 `ti:` `abs:` `au:` `cat:`，`AND/OR/ANDNOT`，短语用双引号；（仅用户指定时间范围时）日期 `submittedDate:[YYYYMMDDHHMM TO …]` | `abs:"scientific discovery" AND (abs:agent OR abs:agents) AND cat:cs.AI` |
| Semantic Scholar `/paper/search` | 纯文本相关性检索，（仅用户指定时间范围时）`year=2024-2026`；`/paper/search/bulk` 支持 `+ | - " *` 布尔语法 | `"AI scientist" | "research agent"` |
| OpenAlex | `search=` 全文相关性；`filter=type:article`（仅用户指定时间范围时再加 `from_publication_date:…`）| `search=self-driving laboratory` |
| PubMed | `[tiab]` `[mh]`（MeSH）、`AND/OR/NOT`、截词 `*`；（仅用户指定时间范围时）`2024:2026[dp]` | `("self-driving lab*"[tiab] OR "autonomous laborator*"[tiab])` |
| Crossref | `query.bibliographic=` 适合按标题核对，不适合主题检索 | — |

4. **迭代**：首轮结果按引用数和相关性浏览前 50–100 条 → 把新出现的术语加入同义词表 → 再检索，直到新增相关条目明显减少（饱和）。把每轮的检索式、日期、命中数记入 `search_log.md`（写进报告的“范围与方法”）。

---

## 2. 各数据源怎么查（Sources & endpoints）

脚本都在 `scripts/` 下，输出统一的 JSONL 候选记录（字段：`source,title,authors,date,venue,doi,arxiv,url,abstract,citations,checked`）。所有脚本的日期参数（`--from/--to`、`--year`）都是可选的，**不传就不做日期过滤**；只在用户指定了时间范围时才传。

### 2.1 arXiv API（预印本主力，CS/物理/数学/q-bio）
- 端点：`https://export.arxiv.org/api/query?search_query=…&start=0&max_results=100&sortBy=submittedDate&sortOrder=descending`
- 按 ID：`…/api/query?id_list=2408.06292,2502.18864`
- **速率限制（arXiv API ToU）**：所有机器合计**每 3 秒不超过 1 次请求，且只用单连接**；不要多线程、不要换机器绕过。
- **429 / 503 时的退路**：
  1. 指数退避（脚本已内置：6s→12s→24s…，并遵守 `Retry-After`）。
  2. 仍然 429：停止 arXiv API，改用 **Semantic Scholar batch**（`ids:["ARXIV:2408.06292",…]`）或 **OpenAlex**（arXiv 论文也有收录）补元数据；或直接打开 `https://arxiv.org/abs/<id>` 页面人工核对。
  3. 大批量（上万条）元数据：用 OAI-PMH 或 Kaggle 上的 arXiv metadata 快照，而不是反复调用搜索 API。
- 脚本：`python scripts/search_arxiv.py --query '…' --max 200 --out cand_arxiv.jsonl`；用户指定了时间范围时再加 `--from 2024-01-01 --to 2026-10-01`；核对标题列表 `--titles titles.txt`。
- 看 `journal_ref` 和 `comment` 字段：作者常在其中写 “Accepted to ICLR 2025”，但这只是线索，需到会议官网/OpenReview 核实。

### 2.2 Semantic Scholar Graph API（跨学科、引用网络、滚雪球）
- 搜索：`GET https://api.semanticscholar.org/graph/v1/paper/search?query=…&fields=title,externalIds,venue,year,publicationDate,authors,citationCount&limit=100`
- 布尔批量：`GET /graph/v1/paper/search/bulk?query=…&token=…`（用 `token` 翻页，最多可拉大量结果）
- 批量核对：`POST /graph/v1/paper/batch?fields=…`，body `{"ids":["ARXIV:2408.06292","DOI:10.1038/s41586-025-09640-5"]}`（每次 ≤500 个 ID）
- 引用/参考文献：`GET /graph/v1/paper/{id}/citations`、`/references`
- **限速**：无 key 时与全球匿名用户共享配额，经常 429；申请免费 key 后设置 `export S2_API_KEY=…`（请求头 `x-api-key`），按约 1 次/秒调用。
- 年份过滤：仅用户指定时间范围时加 `&year=2024-2026`（脚本 `--year 2024-2026`），否则不加。
- 脚本：`python scripts/search_s2.py search|bulk|batch|refs|cites …`

### 2.3 OpenAlex（全学科开放目录，含机构与国家）
- 搜索：`GET https://api.openalex.org/works?search=…&per_page=100&cursor=*&api_key=KEY`（仅用户指定时间范围时加 `&filter=from_publication_date:2024-01-01,to_publication_date:2026-10-01`）
- 单条：`GET https://api.openalex.org/works/doi:10.1038/s41586-025-09640-5`（单条查询免费）
- **2026-02 起需要 API key**（openalex.org 注册即得，免费额度 $1/天：约 1,000 次 search 或 10,000 次 list/filter；单条查询不计费）。无 key 的调用共享按 IP 的极小额度，常见 `429 Insufficient budget`。查看余额：`https://api.openalex.org/rate-limit?api_key=KEY`。
- 优势：`authorships[].institutions` 和 `countries` 字段可直接辅助“机构/国家”判定（仍需人工复核）。
- 脚本：`OPENALEX_API_KEY=… python scripts/search_openalex.py search "…"`（用户指定时间范围时加 `--from … --to …`）

### 2.4 Crossref（DOI 核对、期刊/会议信息、预印本↔正式版关系）
- 单条：`GET https://api.crossref.org/works/{DOI}`；按标题核对：`GET https://api.crossref.org/works?query.bibliographic=<title>&rows=3`
- 加 `mailto=you@example.org` 进入 polite pool（更稳定）；被 429 时退避。
- `relation` 字段中的 `is-preprint-of` / `has-preprint` 可以把预印本与正式发表版本连起来。
- 脚本：`python scripts/search_crossref.py doi 10.1038/…` / `title "…"`

### 2.5 bioRxiv / medRxiv（生命科学与医学预印本）
- **没有关键词搜索接口**。`https://api.biorxiv.org/details/biorxiv/2025-01-01/2025-01-31/0?category=bioinformatics` 按日期窗口（可选学科分类）分页返回全部预印本，需本地按关键词过滤。
- 单条：`/details/biorxiv/{DOI}`；是否已正式发表：`/pubs/biorxiv/{DOI}`（返回 `published_doi`、`published_journal`）。medRxiv 把 `biorxiv` 换成 `medrxiv`。
- 日期窗口是这个 API 的取数方式，不是时间限制：用户没指定时间范围时，窗口取**整个存档**（bioRxiv 2013-11-01 / medRxiv 2019-06-01 至今，脚本不传 `--from/--to` 时自动如此），用 `--category` 缩小扫描量；用户指定了时间范围时才用该范围作窗口。
- 窗口太大时按月切片（或调大 `--max-pages`；脚本在页数上限截断时会提示未扫完）；关键词检索也可以先在 bioRxiv 网站搜索框人工检索，再用 API 补元数据。
- 脚本：`python scripts/search_biorxiv.py window --category … --kw "language model" --kw agent [--from … --to …]`

### 2.6 PubMed（E-utilities）
- `esearch.fcgi?db=pubmed&term=…&retmode=json&retmax=200` → `esummary.fcgi?db=pubmed&id=…`（仅用户指定时间范围时加 `&datetype=pdat&mindate=2024&maxdate=2026`）
- 限速：无 key 3 次/秒，`NCBI_API_KEY` 10 次/秒；建议带 `tool` 与 `email` 参数。
- MeSH 词（`[mh]`）能补全同义词；生物医学主题必查。
- 脚本：`python scripts/search_pubmed.py '…[tiab]'`（用户指定时间范围时加 `--from 2024/01/01 --to 2026/10/01`）

### 2.7 DBLP（计算机科学会议/期刊的“是否正式发表”权威来源）
- `https://dblp.org/search/publ/api?q=<title words>&format=json&h=10`；作者页、会议目录页（如 `https://dblp.org/db/conf/iclr/iclr2025.html`）。
- 某些网络环境下 DBLP 会弹出反爬验证页（例如 “Making sure you're not a bot”）：此时改用浏览器人工查看，不要绕过。

### 2.8 OpenReview（ICLR / NeurIPS / TMLR 等的投稿与录用状态）
- API v2：`https://api2.openreview.net/notes/search?term=<关键词>&limit=25`；按 venue：`https://api2.openreview.net/notes?content.venueid=ICLR.cc/2025/Conference`
- 用于确认“已录用 / 被拒 / 撤稿 / workshop”。录用状态以 `venue`/`venueid` 字段为准，不以作者自述为准。

### 2.9 Papers with Code → Hugging Face Papers
- Papers with Code 已于 **2025-07 停止服务**，域名跳转到 Hugging Face 的 Trending Papers。
- 替代：`https://huggingface.co/papers/trending`（按 GitHub star 增速与 HF 制品热度排序）、`https://huggingface.co/api/papers/<arXiv ID>`（单篇元数据、关联代码/模型）、`https://huggingface.co/api/papers/search?q=…`。
- 用途：找“有代码/有模型”的热门工作，补全开源仓库清单；不能当作发表状态依据。

### 2.10 Google Scholar（**只能人工**）
- 没有官方 API，服务条款禁止自动抓取：**不要写爬虫、不要用第三方抓取服务**。
- 人工用法：关键词检索 + “被引用次数”链接做前向滚雪球；“所有版本”找正式版；“引用”按钮导出 BibTeX；也可以直接用 Zotero Connector 浏览器插件保存。
- 中文文献同理：知网/万方/维普人工检索 + Zotero Connector 保存。

### 2.11 公司 / 实验室博客、新闻与产品发布
- 前沿实验室、创业公司的成果常常先（或只）以博客/白皮书发布：官方博客、技术报告页、GitHub README、新闻稿（Business Wire 等）、可信媒体（Nature News、Science、Bloomberg、Reuters 等）。
- 规则：一律标为 **“博客/产品发布（未经同行评审）”**；数字类说法（性能、融资额、估值）注明“公司自报/据某媒体报道”。
- 用 WebSearch/WebFetch 搜 `site:openai.com …`、`site:deepmind.google …` 等；被站点拦截时可改用浏览器打开公开页面。

---

## 3. 滚雪球检索（Snowballing）

1. 选 5–15 篇**种子论文**：高引综述 + 每个子方向 1–2 篇奠基/代表作。
2. **后向**（references）：`search_s2.py refs ARXIV:<id>` —— 找被种子引用的早期工作。
3. **前向**（citations）：`search_s2.py cites ARXIV:<id> --max 1000` —— 找引用种子的新工作（新进展主要来自这里）。
4. 合并后按“标题关键词命中 + 引用数”初筛（用户指定了时间范围时再按发表时间排除范围外条目），再人工读摘要。
5. 每轮新增相关条目 < 5% 时停止。

## 4. 合并、去重与筛选（Dedup & screening）

```bash
python scripts/merge_dedup.py cand_*.jsonl --out candidates.jsonl --csv screening.csv
# 在 screening.csv 中填 include=1 与 dirs=KEY;KEY（可用 Excel/WPS 打开，UTF-8 BOM）
python scripts/merge_dedup.py candidates.jsonl --screened screening.csv --works-draft works_draft.json
```
- 去重键优先级：**DOI（非 arXiv DOI）> arXiv ID > 规范化标题**；同一工作的预印本与正式版合并为一条，保留两个标识符（`doi` 与 `arxiv`）。
- `10.48550/arXiv.xxxx` 是 arXiv 自己的 DOI，按 arXiv ID 处理。
- 同名不同文（例如两个都叫 “AI-Researcher” 的仓库/论文）：靠作者与机构区分，不要只靠名字合并。
- 时间：只有用户指定了时间范围才按日期筛掉条目（以首次公开日期判断，并在“范围与方法”写明口径）；否则不按年份排除任何相关工作。

## 5. 标注发表状态（Status）

| `peer` | `status` 写法示例 | 判定依据 |
|---|---|---|
| `true` | `Nature（2025-09-23）`、`ICLR 2025`、`NeurIPS 2025`、`TMLR` | 出版社 DOI 页面 / 会议论文集 / DBLP / OpenReview 录用记录 |
| `true` | `ICLR 2025 研讨会（workshop）` | workshop 也属同行评审，但要写明 workshop |
| `false` | `arXiv 预印本`、`bioRxiv 预印本` | 只有预印本 |
| `false` | `arXiv 预印本 → Nature 2026` | 该条目本身是预印本，正式版另列或在 note 里写明 |
| `false` | `技术博客（未经同行评审）`、`产品发布（无论文）`、`公司自报` | 博客/新闻稿/产品页 |

- 只有作者自述（README/arXiv comment 写 “accepted”）而未在官方渠道查到的，写成 `ICLR 2026（据仓库 README，未核对官方名单）`，并在“注意事项”列出。
- `venue_type` 字段（`journal|conference|preprint|blog|product|report`）用于 BibTeX/RIS 导出类型。

## 6. 核查规则（Verification rules）

1. **绝不编造**：标题、作者、日期、venue、数字、链接都必须来自可打开的来源；找不到就不写，或写“未核实”。
2. **每条记录要有可点击的 `url`**（优先 DOI/出版社页 > arXiv abs 页 > 官方博客），并记录 `checked`（核查日期，YYYY-MM-DD，注明时区）。
3. 机构/国家查不到时写 `inst: "—（未核实）"`、`country: ""`，这类条目**不计入**地区统计，并在“注意事项”中列出。
4. 引用数、GitHub 星标等动态数字一律注明抓取日期。
5. 二手来源（媒体解读、第三方博客）给出的数字要标注“据 X 报道/第三方解读”，尽量回到原文核对。
6. 抽样复核：最终表格中随机抽 10% 条目，重新打开链接逐项核对。

## 7. 导出到 Zotero（BibTeX / RIS）

```bash
python scripts/export_bibtex.py <data_dir> --out out/references
# -> out/references.bib, out/references.ris, out/zotero_identifiers.txt
```
- **Zotero 导入**：文件 → 导入… → 选 `.bib` 或 `.ris` → 勾选“将导入的条目放入新的分类（collection）”。BibTeX 的 `keywords` / RIS 的 `KW` 会变成 Zotero 标签（这里是方向键，如 `LIT`、`E2E`），便于按方向筛选。
- **元数据最完整的方式**：把 `zotero_identifiers.txt` 中的 DOI / arXiv ID 粘贴到 Zotero 工具栏的“魔棒（通过标识符添加条目）”，Zotero 会自动抓取完整元数据和 PDF 链接。
- 预印本在 RIS 中用 `UNPB`，在 BibTeX 中用 `@misc` + `eprint`/`archivePrefix=arXiv`；如需 Better BibTeX 的引用键规则，可在 Zotero 里重新生成 citation key。
- 博客/产品发布导出为 `@misc{… howpublished=\url{…}}` / RIS `ELEC`。
