# 如何查文献（Literature Search Playbook）

目标：在给定主题内（如用户明确指定了时间范围，则在该范围内），**尽量完整、可复核**地找到代表性工作，并为每条记录留下来源、标识符（DOI / arXiv ID / PMID）、发表状态与核查日期。

> **时间范围规则**：本技能**没有默认时间范围**。只有用户明确要求时，才把时间范围作为约束加到检索（下文各数据源的日期参数/语法）和筛选中；用户没提就不加任何日期过滤，也不按年份排除条目。下文出现的日期参数与日期语法都只是“用户指定了时间范围时”的写法示例。报告“范围与方法”写明用户指定的范围，或“未设时间限制”。

> **检索日志**：开始前 `export SURVEY_QUERY_LOG=search_log.tsv`（或给脚本传 `--log`）。所有检索型调用（PubMed、Europe PMC search、S2 search/bulk、OpenAlex search 及其 Crossref 回退、arXiv `--query`、Crossref `title`、bioRxiv `window`、`snowball.py`、`recall_check.py` 的 recall/saturation/coverage）会把检索式**逐字**、总命中数、取回条数、时间（带 UTC 偏移）和输出文件追加到该 TSV，保证“范围与方法”里的检索可复现，不用手工补录。

> **核验日志**：按 DOI/ID 的逐条核验（Europe PMC / Crossref / bioRxiv / OpenAlex 的 `doi` 模式、arXiv `--ids/--titles`、`recall_check.py verify`）写进单独的 `verify_lookups.tsv`（`$SURVEY_LOOKUP_LOG` 或 `--lookup-log`；默认放在检索日志旁边），不混进检索日志。

> **不能只靠关键词检索**：按 §1b 的多策略流程做（必收清单 → 名称检索 → 关键词检索 → 滚雪球 → 门户/仓库挖掘 → 召回与饱和），每条候选记 `found_via`，报告写明关键词检索的召回率。

> 适用的 API 限制与行为在 2026 年会变化（例如 OpenAlex 自 2026-02 起要求 API key）。遇到与本文不一致的情况，以官方文档为准，并在报告“范围与方法”中写明实际做法。

---

## 0. 按学科选数据源（Domain-aware source sets）

先判断主题属于哪个学科，再选主力数据源；跨学科主题取并集。不要把 CS 的流程（DBLP、OpenReview、workshop、HF Papers）套到生物医学主题上，反之亦然。

| 学科 | 主力关键词检索 | 预印本 | 发表状态/元数据核对 | 领域特有资源 |
|---|---|---|---|---|
| **生命科学 / 医学 / 农学** | PubMed（`[tiab]` + MeSH `[mh]`，联盟作者 `[cn]`）、Europe PMC（摘要+全文、单位、被引数） | Europe PMC `SRC:PPR`（bioRxiv/medRxiv/Research Square…）→ `search_biorxiv.py doi` 查版本与正式版 | Crossref（在线日期）、PubMed/Europe PMC、出版社页 | 联盟/项目官网 Publications 页、数据门户（GTEx Portal、eQTL Catalogue 等，写进 `portals.json` 并做存活检查）、ClinicalTrials.gov（临床）、NCBI GEO/SRA（数据集） |
| **计算机 / AI** | Semantic Scholar、arXiv（`cat:cs.*`）、OpenAlex | arXiv | DBLP、OpenReview（录用/workshop）、ACL Anthology | Hugging Face Papers、GitHub、公司/实验室博客 |
| **物理 / 数学 / 统计** | arXiv、OpenAlex、S2 | arXiv | Crossref、期刊页、INSPIRE-HEP（高能物理）、zbMATH/MathSciNet（数学） | — |
| **化学 / 材料** | OpenAlex、Crossref、S2 | ChemRxiv、arXiv `cond-mat` | Crossref、期刊页 | 数据库与开源软件页 |
| **社会科学 / 经济** | OpenAlex、Crossref | SSRN、OSF、NBER/RePEc 工作论文 | Crossref、期刊页 | 政府/机构报告 |

生命科学主题的额外要点：
- **MeSH**：`search_pubmed.py` 会打印 PubMed 的自动查询翻译（`querytranslation`），从中可看到词被映射到哪些 MeSH 主题词；把有用的 `[mh]` 词加入检索式，并记录到日志。
- **联盟作者**：GTEx、FarmGTEx、eQTLGen 等论文的作者常是 “XX Consortium”；PubMed 用 `"GTEx Consortium"[cn]` 检索，导出时作为单个机构作者（见 §7）。
- **数据门户 ≠ 代码仓库**：门户、数据库、在线工具写进 `portals.json`（报告单列“数据门户与资源”），用 `check_urls.py` 检查链接是否还活着；仓库仍写 `repos.json`。
- **日期**：PubMed/Europe PMC 的日期有时是纸质刊期（比在线日期晚 1–3 个月）；`date` 一律用首次公开日期（预印本或在线日期），关键条目用 `search_crossref.py doi` 的 `date_online` 核对。

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
| PubMed | `[tiab]` `[mh]`（MeSH）、`[cn]`（联盟作者）、`AND/OR/NOT`、截词 `*`；（仅用户指定时间范围时）`2024:2026[dp]` | `("self-driving lab*"[tiab] OR "autonomous laborator*"[tiab])` |
| Europe PMC | `TITLE:` `ABSTRACT:` `AUTH:` `AFF:`、`SRC:PPR`（预印本）/`SRC:MED`、短语双引号；（仅用户指定时间范围时）`FIRST_PDATE:[2024-01-01 TO 2026-10-01]` | `(FarmGTEx OR PigGTEx) AND SRC:PPR` |
| Crossref | `query.bibliographic=` 适合按标题核对，不适合主题检索 | — |

4. **迭代**：首轮结果按引用数和相关性浏览前 50–100 条 → 把新出现的术语加入同义词表 → 再检索，直到新增相关条目明显减少（饱和，用 `recall_check.py saturation` 按方向判断，见 §1b）。检索式、日期、命中数自动记入 `search_log.tsv`，整理成 `search_log.md` 写进报告的“范围与方法”。
5. **总称不够用**：领域总称（“post-GWAS”“AI for science”）只能找到综述和自称属于该领域的新论文。每个方向一定要再按**具名方法/工具/数据集**检索（§1b）。

---

## 1b. 多策略检索流程（必做，不能只靠关键词检索）

**为什么**：关键词检索按相关性只取回前几百条，而经典方法论文的标题和摘要很少使用领域的总称：精细定位论文写 “Bayesian variable selection”，不写 “post-GWAS”；共定位论文写 “colocalisation”，不写 “functional follow-up”。结果是**里程碑工作恰恰最容易漏掉**。所以本技能把检索拆成 6 个必做环节，每个环节的产出都带 `found_via`，最后用必收清单量化召回率并写进报告。

| 环节 | 做什么 | 工具 | `found_via` |
|---|---|---|---|
| ① 必收清单 | **检索之前**凭领域知识写出每个方向的奠基/里程碑工作，逐条到数据库核实 | `recall_check.py verify` | `must` |
| ② 拆方向 + 具名检索 | 每个方向列出具名方法/工具/数据集/联盟/资源，逐个按名称检索 | 各 `search_*.py`，文件名 `name_*.jsonl` | `name` |
| ③ 关键词检索 | §1 的概念块检索式（总称 + 同义词） | 各 `search_*.py` | `kw:<source>` |
| ④ 滚雪球 | 综述/里程碑做种子：后向（参考文献）+ 前向（被引） | `snowball.py refs/cites` | `snowball:refs` / `snowball:cites` |
| ⑤ 门户/文档/仓库挖掘 | 联盟/门户的 Publications 页、工具文档 “How to cite”、GitHub README Citation 段 / `CITATION.cff` / R `inst/CITATION` | `snowball.py page-ids/repo-cites` | `page:<host>` / `repo-cite:<owner/repo>` |
| ⑥ 召回与饱和 | 各策略对必收清单的召回率（总体/分方向/累计）；每个方向是否饱和；成稿后的各方向来源构成 | `recall_check.py recall/saturation/coverage` | — |
| 手工补充 | 上述都没找到、但经核实确属必收的 | `search_crossref.py doi` 核实 | `manual` |

### 步骤
1. **拆方向，列具名实体**：先按 `taxonomy-and-teams.md` 拆出 6–12 个方向，每个方向写 5–20 个**具名**的方法/工具/软件包、数据集/队列、联盟/项目、数据库/门户、关键实验技术。这一步与方向分类同时做，后面会迭代。
2. **写必收清单（检索之前，独立于检索结果）**：`must_include.tsv`，列 `name / doi / title / dir / note`，每个方向 5–15 篇（奠基方法、里程碑资源、权威综述、最新代表作）。DOI 记不清就只写标题。然后：
   ```bash
   python scripts/recall_check.py verify must_include.tsv --out must_verified.tsv --jsonl cand_must.jsonl
   ```
   逐条查 Crossref（404 时查 Europe PMC）：`ok` / `resolved_by_title`（只有标题的解析出 DOI）/ `title_mismatch`（DOI 指向了别的论文）/ `doi_not_found` / `not_found`。后三种必须改正或删除：**记忆中的 DOI 常常是错的**（post-GWAS 的 148 条里有 4 条 DOI 错误），未核实的条目不能进入 works.json。核实通过的记录写进 `cand_must.jsonl`（`found_via: ["must"]`），之后参与合并。
3. **具名检索**：对第 1 步的每个实体单独检索，例如 `TITLE:"LD score regression"`（Europe PMC）、`SuSiE[tiab] AND fine-mapping[tiab]`（PubMed）、`coloc Bayesian colocalization`（S2/OpenAlex/Crossref 回退）、`"GTEx Consortium"[cn]`。每条用 `--sort "CITED desc"` 或相关性排序取前 20–50 条即可；输出命名 `name_<dir>_<n>.jsonl`。
4. **关键词检索**：照 §1 和 §2 做，输出 `pm_*.jsonl`、`ep_*.jsonl` 等。
5. **滚雪球**（§3）：后向以 3–10 篇权威综述 + 各方向里程碑为种子；前向以各方向的奠基方法为种子（`--min-seeds 2` 降噪）。
6. **门户/文档/仓库挖掘**：
   ```bash
   python scripts/snowball.py page-ids https://<consortium>/publications https://<tool-docs>/citation --out sb_page.jsonl
   python scripts/snowball.py repo-cites @data/repos.json --out sb_repo.jsonl      # 或 owner/repo …
   ```
   JS 渲染的页面（脚本只拿到空壳）用浏览器/WebFetch 打开，把找到的 DOI 写成一行一个的清单，再用 `recall_check.py verify` 或 `search_crossref.py doi` 核实。
7. **合并**：`merge_dedup.py cand_must.jsonl name_*.jsonl pm_*.jsonl ep_*.jsonl sb_*.jsonl --found-via 'name_*=name' --out candidates.jsonl --csv screening.csv`。同一工作被多个策略找到时 `found_via` 取并集；CSV 和 works 草稿都带 `found_via` 列。手工补的条目写 `found_via: ["manual"]`。
8. **召回率**：
   ```bash
   python scripts/recall_check.py recall --must must_verified.tsv \
       --pool keyword='pm_*.jsonl,ep_*.jsonl,s2_*.jsonl' --pool names='name_*.jsonl' \
       --pool snowball='sb_refs*.jsonl,sb_cites*.jsonl' --pool mining='sb_repo*.jsonl,sb_page*.jsonl' --out recall.tsv
   ```
   输出 Markdown 表（各策略召回、累计召回、各方向 `命中/总数`）和**所有策略都漏掉的清单**，同时写进检索日志（source `recall-check`）。对漏掉的条目：先按名称再检索、以它为种子再滚一轮，仍找不到才手工补（`manual`）。**关键词检索的召回率**（第一行）必须写进报告。
9. **饱和**：每轮（关键词 / 名称 / 后向 / 前向 / 挖掘）筛选后，
   ```bash
   python scripts/recall_check.py saturation --round r1-keyword='pm_*.jsonl,ep_*.jsonl' \
       --round 'r2-names@PLEIO;MR=name_pleio_*.jsonl,name_mr_*.jsonl' --round r3-refs='sb_refs*.jsonl' \
       --relevant screening.csv
   ```
   `@DIR` 标出该轮针对的方向（不标 = 针对全部）。一个方向**饱和** = 至少 2 轮针对它、已找到 ≥5 篇相关工作、且最后一轮新增相关工作 <5%。未饱和的方向继续做名称检索或以最新相关工作为种子滚雪球。时间不够可以停，但要在报告里写明哪些方向未饱和。
10. **来源构成**：成稿后 `python scripts/recall_check.py coverage <data_dir> --kw-pool 'pm_*.jsonl,ep_*.jsonl'`，输出各方向“作品数 / 各策略贡献数 / 仅靠关键词能找到的比例”的表，贴进 `narrative/scope.html`。

### 实例：post-GWAS（2026-10 测试运行）
- 主题“GWAS 之后：从关联信号到因果变异、基因与机制”，12 个方向（FM 精细定位、COLOC 共定位、TWAS、ANNO 功能注释、V2G 变异到基因、MR、QTL、DL 深度学习变异效应、EXP 实验验证、PRS、PLEIO 多效性、LIV 畜禽）。
- 当时只做了关键词检索（PubMed 14 条、Europe PMC 6 条、S2/OpenAlex/arXiv 各 1–2 条检索式，合并后 4,487 条），然后凭领域知识列了 148 个 DOI，逐条用 Crossref + Europe PMC 核实。**关键词池只覆盖其中 52 篇（35%）**，其余靠手工整理，没有做滚雪球。事后用本流程复盘（同一份 148 条清单，其中 4 条 DOI 有误、未通过核实）：

| 策略（累计） | 新增命中 | 累计召回 | 说明 |
|---|---|---|---|
| 关键词检索 | 52 | 35% | PLEIO 0/10、ANNO 1/14、MR 1/11、V2G 2/10，最差 |
| + 名称检索（只做了 PLEIO 方向，7 条） | 5 | 39% | PLEIO 0/10 → 5/10（LDSC、MTAG、Genomic SEM、LAVA、PheWAS） |
| + 后向滚雪球（3 篇综述：Schaid 2018 NRG、Gallagher 2018 AJHG、NRG 2025 精细定位综述） | 23 | 54% | FM 15/15，ANNO 1→9/14 |
| + 前向滚雪球（SuSiE、coloc、FINEMAP，各取 300 篇） | 0 | 54% | 前向主要带来新工作，对经典清单贡献小 |
| + 仓库 “cite us”（`repo-cites @repos.json`，53 个仓库） | 10 | 61% | MR 1→3/11、TWAS、COLOC |
| 最终 works.json（180 篇）中仅靠关键词能找到的 | — | 48% | ANNO 7%、MR 9%、PLEIO 9%、V2G 20%；FM 86%、LIV 80% |

- 结论：经典方法类方向（ANNO、MR、PLEIO、V2G）几乎完全依赖名称检索和滚雪球；专有名词明确的方向（FM、畜禽 FarmGTEx 系列）关键词检索就够。每个方向再做 5–10 条名称检索、各用 1–2 篇该方向综述做后向滚雪球，手工补充的部分就会缩小到个位数，而且每一篇都有可追溯的来源。

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
- 日志：`--query` 写检索日志（含总命中数），`--ids/--titles` 写核验日志；持续 429/503 时保存已取到的记录并以退出码 2 结束。
- 看 `journal_ref` 和 `comment` 字段：作者常在其中写 “Accepted to ICLR 2025”，但这只是线索，需到会议官网/OpenReview 核实。

### 2.2 Semantic Scholar Graph API（跨学科、引用网络、滚雪球）
- 搜索：`GET https://api.semanticscholar.org/graph/v1/paper/search?query=…&fields=title,externalIds,venue,year,publicationDate,authors,citationCount&limit=100`
- 布尔批量：`GET /graph/v1/paper/search/bulk?query=…&token=…`（用 `token` 翻页，最多可拉大量结果）
- 批量核对：`POST /graph/v1/paper/batch?fields=…`，body `{"ids":["ARXIV:2408.06292","DOI:10.1038/s41586-025-09640-5"]}`（每次 ≤500 个 ID）
- 引用/参考文献：`GET /graph/v1/paper/{id}/citations`、`/references`
- **限速**：无 key 时与全球匿名用户共享配额，经常 429；申请免费 key 后设置 `export S2_API_KEY=…`（请求头 `x-api-key`），按约 1 次/秒调用。
- **429 时脚本的行为**：每次调用按指数退避重试（遵守 `Retry-After`，上限 `--max-wait` 秒，共 `--retries` 次）；仍失败就**停止并保存已取到的记录**，打印替代方案，退出码 2（不再抛 traceback）。这时改用 OpenAlex / Europe PMC / Crossref 补检，并在“范围与方法”注明 S2 不可用。
- 年份过滤：仅用户指定时间范围时加 `&year=2024-2026`（脚本 `--year 2024-2026`），否则不加。
- 脚本：`python scripts/search_s2.py search|bulk|batch|refs|cites …`

### 2.3 OpenAlex（全学科开放目录，含机构与国家）
- 搜索：`GET https://api.openalex.org/works?search=…&per_page=100&cursor=*&api_key=KEY`（仅用户指定时间范围时加 `&filter=from_publication_date:2024-01-01,to_publication_date:2026-10-01`）
- 单条：`GET https://api.openalex.org/works/doi:10.1038/s41586-025-09640-5`（单条查询免费）
- **2026-02 起需要 API key**（openalex.org 注册即得，免费额度 $1/天：约 1,000 次 search 或 10,000 次 list/filter；单条查询不计费）。无 key 的调用共享按 IP 的极小额度，常见 `429 Insufficient budget`。查看余额：`https://api.openalex.org/rate-limit?api_key=KEY`。
- 优势：`authorships[].institutions` 和 `countries` 字段可直接辅助“机构/国家”判定（仍需人工复核）。
- 脚本：`OPENALEX_API_KEY=… python scripts/search_openalex.py search "…"`（用户指定时间范围时加 `--from … --to …`）
- 脚本不会挂起：429 “Insufficient budget” 立即停止；其他 429/5xx 最多重试 `--retries` 次（`Retry-After` 封顶 60 秒），整体超过 `--timeout`（默认 300 秒）就停，保存已取到的结果并以退出码 2 结束。
- **无 key / 额度耗尽时的免 key 回退**（默认 `--fallback crossref`）：同一检索式改用 Crossref `query=`（按相关性排序、cursor 翻页），记录带 `fallback_for: "openalex"`，检索日志记为 `crossref-fallback`；`doi` 模式回退到 Crossref 单条查询。拿到记录则退出码 0，一条都没有才是 2；`--fallback none` 保持旧行为。设 `SURVEY_MAILTO` 进入 polite pool。Crossref 没有机构/国家字段，回退结果用 Europe PMC/PubMed 补单位。

### 2.4 Crossref（DOI 核对、期刊/会议信息、预印本↔正式版关系）
- 单条：`GET https://api.crossref.org/works/{DOI}`；按标题核对：`GET https://api.crossref.org/works?query.bibliographic=<title>&rows=3`
- 加 `mailto=you@example.org` 进入 polite pool（更稳定）；被 429 时退避。
- `relation` 字段中的 `is-preprint-of` / `has-preprint` 可以把预印本与正式发表版本连起来。
- 脚本的 `date` 是首次公开日期（`published-online`，预印本为 `posted`），同时给出 `date_online` 与 `date_print`；用它修正来源只有纸质刊期的条目。
- 脚本：`python scripts/search_crossref.py doi 10.1038/…` / `title "…"`
- 一次可查多个 DOI，404 记为 `not_found` 不中断；输出另有 `is_preprint`、`server`、`is_preprint_of`（预印本 → 正式版 DOI）、`has_preprint`（正式版 → 预印本 DOI）、`published`，`merge_dedup.py` 用它们合并预印本与正式版。`doi` 写核验日志，`title` 写检索日志（含总命中数）；网络失败时保存已取到的记录并以退出码 2 结束。

### 2.5 bioRxiv / medRxiv（生命科学与医学预印本）
- **DOI 前缀**：2025-11 及以前为 `10.1101/YYYY.MM.DD.NNNNNN`（更早为 `10.1101/NNNNNN`），**2025-12-01 起为 openRxiv 前缀 `10.64898/YYYY.MM.DD.NNNNNN`**（medRxiv 后缀可为 8 位）。注意 `10.1101/` 也被 CSHL 期刊使用（Genome Research `10.1101/gr.…`、Genes & Dev `10.1101/gad.…`），这些不是预印本。脚本（`common.is_preprint_doi`）按此识别预印本。
- **按关键词找预印本请用 Europe PMC**：`search_europepmc.py search '…' --preprints`；再用本脚本的 `doi` 模式补版本、`corresponding_institution`（推断国家很有用）和 `published`（正式版 DOI，`merge_dedup.py` 据此合并）。
- **没有关键词搜索接口**。`https://api.biorxiv.org/details/biorxiv/2025-01-01/2025-01-31/0?category=bioinformatics` 按日期窗口（可选学科分类）分页返回全部预印本，需本地按关键词过滤。
- 单条：`/details/biorxiv/{DOI}`；是否已正式发表：`/pubs/biorxiv/{DOI}`（返回 `published_doi`、`published_journal`）。medRxiv 把 `biorxiv` 换成 `medrxiv`。
- **版本与日期**：API 对每个版本返回一行；`doi` 模式合成一条：`date` = **v1 首发日**（首次公开日期，works.json 用它），`date_latest`/`url_latest` 是最新版，另有 `version`、`versions[]`（每版日期）、`url`（指向 v1）、`server`、`published`/`published_date`。一次可查多个 DOI，写核验日志。窗口模式里只看到 v2+ 的记录带 `date_note`，提醒去查 v1。
- 日期窗口是这个 API 的取数方式，不是时间限制：用户没指定时间范围时，窗口取**整个存档**（bioRxiv 2013-11-01 / medRxiv 2019-06-01 至今，脚本不传 `--from/--to` 时自动如此），用 `--category` 缩小扫描量；用户指定了时间范围时才用该范围作窗口。
- 窗口太大时按月切片（或调大 `--max-pages`；脚本在页数上限截断时会提示未扫完）；关键词检索也可以先在 bioRxiv 网站搜索框人工检索，再用 API 补元数据。
- 脚本：`python scripts/search_biorxiv.py doi 10.64898/2026.08.30.748055`（`doi.org` 链接也可；在 bioRxiv 找不到时自动试 medRxiv）；`python scripts/search_biorxiv.py window --category … --kw "language model" --kw agent [--from … --to …]`（仅适合有时间范围或小类别的扫描）

### 2.6 PubMed（E-utilities）
- `esearch.fcgi?db=pubmed&term=…&retmode=json&retmax=500&retstart=0&sort=relevance` 分页 → `esummary.fcgi?db=pubmed&id=…`（元数据）→ `efetch.fcgi?db=pubmed&id=…&retmode=xml`（摘要、单位、MeSH、电子出版日期）。仅用户指定时间范围时加 `&datetype=pdat&mindate=2024&maxdate=2026`。ESearch 最多翻到 10,000 条，更多时按年份 `[dp]` 拆分。
- 限速：无 key 3 次/秒，`NCBI_API_KEY` 10 次/秒；建议带 `tool` 与 `email` 参数。
- MeSH 词（`[mh]`）能补全同义词；生物医学主题必查。脚本打印 PubMed 的查询翻译，可从中看到映射到的 MeSH 词。
- 脚本：`python scripts/search_pubmed.py '…[tiab]' --max 1000 --out pm.jsonl`（默认**按相关性**排序，所以 `--max` 截断时保留最相关的而不只是最新的；打印并记录总命中数；`--count-only` 只看命中数；`--no-abstracts` 跳过 EFetch；用户指定时间范围时加 `--from 2024/01/01 --to 2026/10/01`）。
- 输出：`date`（电子出版日期优先，不取未来的刊期日期）、`date_print`、`abstract`、`affiliation`（第一作者第一单位）、`country_guess`（仅提示）、`mesh`、`pmid`、`pmcid`；作者保持 PubMed 格式 “Smith AB”，联盟作者保留为一个名字。

### 2.6b Europe PMC（生命科学关键词检索 + 预印本入口）
- 端点：`https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=…&format=json&resultType=core&pageSize=1000&cursorMark=*`；无需 key。
- 覆盖 MEDLINE、PMC 全文和预印本（`SRC:PPR`：bioRxiv、medRxiv、Research Square、Preprints.org 等），返回作者单位、被引数、MeSH。
- 脚本：`python scripts/search_europepmc.py search '(FarmGTEx OR PigGTEx)' --max 500 --out ep.jsonl`；`--preprints` 只要预印本；`--count-only` 只看 hitCount；`--sort "CITED desc"` 按被引；`doi` 子命令查单条。输出字段与其他脚本一致，另有 `epmc_src`、`is_preprint`、`affiliation`、`country_guess`、`citations`。
- `date` 取电子出版日期 > `firstPublicationDate` > 纸质日期；`firstPublicationDate` 有时就是纸质刊期，关键条目用 Crossref 核对。
- `--sort` 只接受 `CITED`、`P_PDATE_D`、`FIRST_PDATE_D`、`FIRST_IDATE_D`、`PUB_YEAR`、`AUTH_FIRST` + `asc|desc`（`CITED%20desc` 这类已编码写法会自动解码）；未知字段直接报错（服务器对它只回 503）。服务器 5xx/网络失败时保存已取到的记录、打印替代方案并以退出码 2 结束。`doi` 子命令可查多个 DOI，写核验日志。
- `is_preprint` 只在 `SRC:PPR` 且没有期刊 DOI 时为真；预印本↔正式版链接：预印本的 “Preprint of” → `published_pmid`/`published`，正式版的 “Preprint in” → `preprint_epmc_ids`。

### 2.7 DBLP（**计算机科学**会议/期刊的“是否正式发表”权威来源；其他学科不用）
- `https://dblp.org/search/publ/api?q=<title words>&format=json&h=10`；作者页、会议目录页（如 `https://dblp.org/db/conf/iclr/iclr2025.html`）。
- 某些网络环境下 DBLP 会弹出反爬验证页（例如 “Making sure you're not a bot”）：此时改用浏览器人工查看，不要绕过。

### 2.8 OpenReview（**计算机科学**：ICLR / NeurIPS / TMLR 等的投稿与录用状态）
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

```bash
# 后向：种子引用了谁（找经典/早期工作）。默认 auto = 第一个有结果的来源：
#   Europe PMC（免 key，按 PMID）→ Crossref（免 key，出版社登记的参考文献）→ S2 → OpenAlex
python scripts/snowball.py refs 10.1038/s41576-018-0016-z 10.1016/j.ajhg.2018.04.002 --out sb_refs.jsonl
python scripts/snowball.py refs @must_verified.tsv --via all --out sb_refs_all.jsonl   # 合并所有来源，召回最高
# 前向：谁引用了种子（找新工作）：Europe PMC（免 key）→ S2 → OpenAlex
python scripts/snowball.py cites 10.1111/rssb.12388 10.1371/journal.pgen.1004383 --max 300 --min-seeds 2 --out sb_cites.jsonl
```
1. **种子**：3–10 篇权威综述（后向最有效）+ 每个方向 1–2 篇奠基方法（前向）。种子可以写在文件里（`@seeds.txt`，一行一个；带 `doi` 列的 TSV/CSV，如必收清单，也可以）。支持 DOI、`PMID:…`、PMCID、`arXiv:…`。
2. 输出是标准候选 JSONL（只有 PMID/DOI 的记录会批量用 Europe PMC/Crossref 补全元数据，`--no-enrich` 跳过），另有 `found_via`、`seeds`（由哪些种子带出）、`seed_count`。按 `seed_count`（被多个种子共同引用 = 强信号）再按被引数排序；前向结果很杂时用 `--min-seeds 2`。
3. 每个种子 × 方向 × 来源都写进检索日志（source `snowball-refs:europepmc` 等）。
4. **免 key 优先**：Europe PMC 的 references/citations 接口只覆盖有 PMID 的条目；Crossref 的参考文献取决于出版社是否登记（部分出版社不登记）；S2 建议设 `S2_API_KEY`；OpenAlex 需要 `OPENALEX_API_KEY`。`--via all` 把能用的来源都跑一遍取并集；`--via crossref,s2` 自定回退顺序。`search_s2.py refs|cites` 仍可用于 S2 专用场景。
5. Europe PMC 的被引列表不按被引数排序（偏新），`--max` 截断时前向结果偏向近期工作——正好用来找新进展；找经典工作靠后向。
6. 合并后照常筛选。每轮新增相关条目 <5% 时停止（`recall_check.py saturation`，见 §1b）。

## 4. 合并、去重与筛选（Dedup & screening）

```bash
python scripts/merge_dedup.py cand_must.jsonl name_*.jsonl pm_*.jsonl ep_*.jsonl sb_*.jsonl \
    --found-via 'name_*=name' --out candidates.jsonl --csv screening.csv [--link-online]
# 在 screening.csv 中填 include=1 与 dirs=KEY;KEY（第一个为主方向；可用 Excel/WPS 打开，UTF-8 BOM）
python scripts/merge_dedup.py candidates.jsonl --screened screening.csv --works-draft works_draft.json
```
- 去重键优先级：**DOI（非 arXiv DOI）> arXiv ID > 规范化标题**；同 DOI 的记录字段合并，同标题、同类（都是正式版或都是预印本）的也合并。
- **预印本还是正式版只看真实标识符**：DOI 前缀属于预印本服务器（`common.PREPRINT_DOI_PREFIXES`：bioRxiv/medRxiv `10.1101/日期…` 与 `10.64898/`、Research Square、SSRN、Preprints.org、ChemRxiv、Authorea、Qeios、arXiv 等）才是预印本；其他 DOI 一律按正式版处理，即使某个索引标成预印本（如 S2 把已发表论文的 venue 写成 bioRxiv）。
- **预印本 → 正式版合并**：预印本并入正式版记录，`doi`/`url` 用正式版；预印本的 DOI/URL/日期存 `preprint_doi`/`preprint_url`/`preprint_date`/`preprint_server`，多个预印本服务器的都列在 `preprint_dois`；`date` 取最早 = 首次公开日期；`link_method` 写明依据。依次尝试：
  1. `published-doi`：预印本记录写了正式版 DOI（bioRxiv `published`、Crossref `is-preprint-of`、Europe PMC “Preprint of” 中的 DOI）；
  2. `has-preprint`：正式版记录列出了预印本（Crossref）；
  3. `europepmc`：Europe PMC 的 PMID/PPR 链接；
  4. `fuzzy`：标题完全相同且前 5 位作者有重合，或第一作者相同、标题相似度 ≥ `--fuzzy`（默认 0.90）且正式版不早于预印本 60 天以上。0.75 以上但未合并的写进 CSV 的 `possible_published` 列，人工确认；
  5. `--link-online`：仍未链接的预印本再查 Crossref 关系与 bioRxiv `/pubs` 接口。知道正式版 DOI 但候选里没有正式版记录时，生成一条正式版“存根”（venue 来自 API，需核实）。
- **`found_via`**：每条候选记录被哪些策略找到（并集）。自带 `found_via` 的记录（`snowball.py`、`recall_check.py verify`）保留原值；其他记录按 `--found-via GLOB=LABEL`（按文件名匹配，如 `name_*=name`、`meta_*=manual`）打标，否则记为 `kw:<source>`。CSV 有 `found_via` 列（可手工改），works 草稿带 `found_via`，`build.py` 会打印汇总。
- 标题自动清理（去 HTML 标签、去末尾句点）；CSV 带 `pmid`、`first_author`、`preprint_doi`、`featured` 列，`--csv-sort citations` 让高被引的排在前面。候选上千条时，可以读标题+摘要在 Python 里整理名单，但要写明纳入标准。
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
- 预印本在 RIS 中用 `UNPB` + `PB`（服务器名），在 BibTeX 中用 `@misc`：arXiv 写 `eprint`/`archivePrefix=arXiv`，其他服务器写 `howpublished = {bioRxiv preprint doi:…}` 与 `publisher`；如需 Better BibTeX 的引用键规则，可在 Zotero 里重新生成 citation key。
- **作者格式**：`authors` 写全部作者，**不要写 “et al.”**（导出时字面的 “et al.” 会变成 BibTeX `and others`）。接受 “Smith AB”（PubMed/Europe PMC）、“Smith, Anna B.”、“Anna B. Smith”，统一导出为 “Last, First”，引用键用真正的姓。联盟/机构作者（含 Consortium、Group、Network、Project 等词，或写成 `{…}`）以及 works 的 `corporate_author` 字段导出为单个机构作者：BibTeX `{GTEx Consortium}`，RIS 不加逗号（Zotero 识别为单字段名称）。
- 博客/产品发布导出为 `@misc{… howpublished=\url{…}}` / RIS `ELEC`。
