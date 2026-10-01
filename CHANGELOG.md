# Changelog

## 2026-10-01 · v1.4 — fixes from the post-GWAS test run; multi-strategy retrieval

A run of v1.3 on "post-GWAS: from association signals to causal variants, genes and mechanisms" (12 directions, 180 works, no time limit) logged 9 issues in `skill_test_notes.md`, and showed that keyword search alone surfaced only 51–52 of the first 148 hand-listed landmark DOIs (35%). This release fixes the issues and makes non-keyword retrieval mandatory.

### Retrieval: never rely on keyword search alone (new, mandatory)
- New workflow step (SKILL.md §1, `references/literature-search.md` §1b, with post-GWAS as the worked example): ① decompose the field into directions and list **named** methods/tools/datasets/consortia per direction; ② write a **must-include list** from your own knowledge *before* searching and verify every entry against Crossref / Europe PMC; ③ **tool-name queries** (`TITLE:"LD score regression"`, `SuSiE fine-mapping`, `coloc Bayesian colocalization`) besides the umbrella-term keyword queries; ④ **backward + forward citation snowballing** from reviews/landmarks; ⑤ **mining** consortium/portal publication pages, tool docs "how to cite" pages and GitHub "cite us" sections; ⑥ **recall** of each strategy against the must-include list (overall, cumulative, per direction), a **per-direction saturation** check and a per-direction source table; every work records **`found_via`**.
- New `scripts/snowball.py`: `refs` / `cites` (Europe PMC keyless → Crossref reference lists keyless → Semantic Scholar → OpenAlex; `--via auto|all|list`; seeds as DOI/PMID/PMCID/arXiv or `@file`, incl. the must-include TSV), `repo-cites` (README Citation sections, `CITATION.cff`, R `inst/CITATION`, `@repos.json`), `page-ids` (DOIs/PMIDs/arXiv IDs on web pages); batch enrichment to full records; output carries `found_via`, `seeds`, `seed_count` (co-citation ranking, `--min-seeds`); every call is logged.
- New `scripts/recall_check.py`: `verify` (must-include list → `ok` / `resolved_by_title` / `title_mismatch` / `doi_not_found`; verified records as `found_via: ["must"]` JSONL), `recall` (Markdown table per strategy and direction, misses list, per-work TSV, logged), `saturation` (rounds `LABEL[@DIRS]=FILES`; a direction is saturated after ≥2 targeted rounds, ≥5 relevant works and <5% new in the last round), `coverage` (per-direction counts by `found_via` strategy and share findable by keyword search alone — a table for `scope.html`).
- `merge_dedup.py`: `found_via` is unioned across duplicates; records without it get `--found-via GLOB=LABEL` (e.g. `name_*=name`) or `kw:<source>`; CSV column + works draft carry it. `build.py` prints a `found_via` summary and hints when none / only keyword search is recorded; validates its type.
- Smoke test on the post-GWAS seeds (same 148-DOI list): keyword pool 52 (35%) → + 7 PLEIO name queries 57 (39%) → + backward snowball from 3 reviews 80 (54%; FM 15/15) → + forward snowball 80 → + repo "cite us" of 53 repos 90 (61%); in the final 180 works only 48% were findable by keyword search (ANNO 7%, MR 9%, PLEIO 9%).
- `quality-checklist.md`: the "scope & methods" section must state the strategies used, keyword-search recall against the must-include list (overall and per direction), saturation per direction, the per-direction source table, manual additions, and must-include entries corrected/dropped.

### Fixes for the logged issues
1. **bioRxiv/medRxiv dates** — `search_biorxiv.py doi` collapses the version rows: `date` = **v1** date (first public), plus `date_v1`, `date_latest`, `version`, `versions[]`, `url` (v1), `url_latest`, `server` ("bioRxiv"/"medRxiv"), `published_date`; accepts several DOIs; window records seen only as v2+ get a `date_note`.
2. **Preprint ↔ journal merge; journal DOIs misread as preprints** — preprint vs journal is decided from real DOI prefixes only (`common.PREPRINT_DOI_PREFIXES`: bioRxiv/medRxiv 10.1101 date-shaped and 10.64898, Research Square, SSRN, Preprints.org, ChemRxiv, Authorea, Qeios, arXiv, OSF family, TechRxiv, JMIR, SciELO, PeerJ, EGUsphere …), so Adv Sci / Bioinformatics / Genome Research DOIs are journals even if an index flags them. `merge_dedup.py` links preprints to journal versions via bioRxiv `published`, Crossref `is-preprint-of` / `has-preprint` (new fields in `search_crossref.py`), Europe PMC "Preprint of / in" (new `published_pmid` / `preprint_epmc_ids` in `search_europepmc.py`), then fuzzy title + author matching with a date guard; `--link-online` asks Crossref / bioRxiv for the rest and creates journal stubs. Merged records keep `preprint_doi`, `preprint_url`, `preprint_date`, `preprint_server`, `preprint_dois`, `link_method`; near misses go to `possible_published`. Europe PMC `is_preprint` only for PPR records without a journal DOI. Tested: AlphaGenome bioRxiv → Nature merged; pig compendium bioRxiv + Research Square → journal.
3. **Taxonomy tree landmark rule** — per direction: all landmarks whose **primary** direction it is (`dirs[0]` or new `primary_dir`; `meta.tree_featured_overflow: show|cap`) → the direction's own works by `tree_sort` → cross-tagged works only fill free slots (dashed grey, tooltip names the primary; `meta.tree_cross: fill|none`) → a clickable "+N 篇 → 代表作表" leaf. cTWAS now stays under TWAS at `tree_leaves=5`. `--check` counts featured works by primary direction and warns when a direction only has cross-tagged landmarks. Bar chart uses the primary direction. Fixed a squashed tree render (chart initialised before its height was set); the tree height also reserves room for wrapped direction names, the root label is hidden below 520 px width, and the tree re-lays out only on width changes with stable node names (full-page screenshots used to catch nodes mid-animation or leave ghost labels).
4. **Europe PMC 503 traceback / unchecked `--sort`** — `--sort` is URL-decoded and validated (CITED, P_PDATE_D, FIRST_PDATE_D, FIRST_IDATE_D, PUB_YEAR, AUTH_FIRST + asc/desc; unknown → clear error, exit 1); HTTP/network errors keep partial results and exit 2 with fallbacks.
5. **Incomplete / polluted query log** — arXiv `--query`, Crossref `title`, bioRxiv `window`, OpenAlex Crossref fallback, snowball and recall checks now write the search log; DOI/ID verification (`doi` modes, arXiv `--ids/--titles`, `recall_check.py verify`) goes to a separate lookup log (`$SURVEY_LOOKUP_LOG`, default `verify_lookups.tsv` next to the search log).
6. **Redirect loops reported dead** — `check_urls.py` retries a 3xx loop with a cookie jar ("ok only with cookies"), otherwise reports `blocked` (opens in a browser), not `dead`.
7. **Adding one repo** — `github_repos.py repos.json --add owner/name|URL [--add …] --cat --dirs --what`: fetches only the new entries, merges them, refreshes (not duplicates) existing ones; `--only a/b,c/d` refreshes a subset.
8. **OpenAlex without a key** — `search_openalex.py --fallback crossref` (default): keyless Crossref relevance search with cursor paging (records tagged `fallback_for: "openalex"`, logged as `crossref-fallback`), DOI mode falls back to a Crossref lookup; exit 0 when records were obtained; polite-pool `mailto` tips.
9. Small issues — long direction names wrap without a stray ")" (brackets/closing punctuation stay attached); no-repo resource cards go last and span the full row (resource list in two columns) instead of stretching neighbours; `screenshot.py` finds bundled → cached other Chromium revisions / headless shell → system Chrome, and otherwise runs `playwright install chromium` itself (`--no-install`); scrollable tables (works table) are additionally captured by scrolling inside the container (`NN_works_table_s2.png` …, `--table-slices`).

### Other
- `common.parse_author` accepts non-Latin-1 initials (e.g. "Avsec Ž"); `surname_key()`, `lookup_log_path()`, `log_lookup()` helpers.
- `search_crossref.py` / `search_europepmc.py` / `search_biorxiv.py` / `search_arxiv.py` accept several DOIs/IDs and exit 2 with partial results on network failure.
- Docs updated: SKILL.md, README (zh/en), literature-search, data-schema (`primary_dir`, `found_via`, `preprint_date`, `tree_cross`, `tree_featured_overflow`), taxonomy-and-teams (tree rule), html-build-and-verify (browser order, table slices, redirect loops), repo-inspection (`--add`, repo-cites), quality-checklist.

## 2026-10-01 · v1.3 — works-table overlap fix, directions without code

### Report
- **Fixed: dates overlapping work titles in "代表性工作".** Cause: the works table used `table-layout: fixed` with a hard-coded 72 px date column (52 px of content after padding) and `white-space: nowrap`, while "2026-08-06" needs ~70 px in Noto Sans CJK and more in PingFang SC / Microsoft YaHei / DejaVu or with larger user fonts, so the date spilled into the title cell (2.7 px of slack with the reference font, −6.5 px = overlap with a wider one). The date column is now sized from the font's own digit width (`calc(9.5ch + 24px)`), the date can wrap at the hyphen as a last resort instead of overflowing, the other columns are proportional, and when the table container is ≤760 px wide every work becomes a card (date + status on top, then title, directions, institution, contribution) instead of squeezing the contribution column to one character.
- Taxonomy tree is width-aware: margins come from measured label widths, leaf labels truncate with … (full name in the tooltip) and direction names wrap at narrow widths; re-laid out on resize.
- **Directions without code repositories** (wet-lab / experimental): `meta.directions[]` gains `repo_expected: false` (alias `no_repo: true | "reason"`), `no_repo_reason` and `resources: [{name,url,kind,note}]` (datasets, protocols, data portals, biobanks; portals whose `dirs` include the direction are added automatically). The open-source section shows a short note + the resource list for them instead of empty entries; with no repos at all the section keeps only these notes (charts/table hidden); direction cards carry a "无代码仓库" badge.
- `repos.json` entries may carry `dirs`: the open-source section then shows per-direction repo counts (click to filter the table) and tags rows with their directions.
- `--check`: a direction with zero repos never warns; `repos.json` may be absent when every direction is `repo_expected: false`; errors for a non-boolean `repo_expected`, malformed `resources` or unknown repo `dirs`; warning when a repo is tagged with a no-repo direction or a resource has no URL.
- Docs (SKILL.md, data-schema, repo-inspection, quality-checklist, taxonomy-and-teams, html-build-and-verify): don't force repositories for wet-lab/experimental directions; cover datasets, protocols, portals and biobanks instead; check the works table at desktop and ~800 px width.

## 2026-10-01 · v1.2 — fixes from a real test run (GTEx & FarmGTEx survey)

A full run of the skill on a life-science topic ("GTEx 与 FarmGTEx", no time limit, 110 works) surfaced 27 issues. This release fixes most of them.

### Taxonomy / report
- **Landmarks are no longer lost** (tree leaves used to be "peer-reviewed + newest", so GTEx v8, CattleGTEx 2022 … vanished without a time range): works can be marked `"featured": true` (shown first, ★, "★ 仅里程碑" filter); remaining leaves follow `meta.tree_sort` = `auto` (citations if present, else evenly spread over time when no time range, else newest) / `citations` / `spread` / `recent`. `--check` warns when nothing is featured or a direction has more featured works than `tree_leaves`.
- `meta.period` is chosen automatically from the data span when omitted (>6 years → `year`, 1 year → `quarter`, else `half`).
- New optional **`portals.json`** → "数据门户与资源" section (type filter, organisation, coverage, access, link status) and portal links in the references.
- Status pills wrap into rounded rectangles instead of ovals (wider status column); Stars chart uses `containLabel` + middle-ellipsis for long `owner/repo` names (full name in tooltip); country bar chart labels no longer clipped; taxonomy leaf labels truncate by display width (CJK = 2).
- `repos.json` `"stable": true` shows "成熟稳定（低频更新）" instead of "停滞" for mature tools.
- Works table links the merged preprint (`preprint_doi` / `preprint_url`).
- `build.py --check` also warns about: `peer: true` with a preprint DOI, "preprint" status with a journal DOI, a literal "et al." in `authors`, dates after `check_date`, dead / unchecked portal links.

### Search scripts
- `search_pubmed.py`: ESearch paging with `retstart`, relevance sort by default (so `--max` keeps the most relevant, not only the newest), total hit count + PubMed query translation (MeSH mapping) logged, EFetch abstracts / first affiliation / MeSH / electronic date, `date` never a future issue date, `--count-only`, `--no-abstracts`, group authors kept.
- New `search_europepmc.py` (Europe PMC REST, cursor paging, `--preprints` = `SRC:PPR`, hitCount, affiliations, citations, `doi` lookup) with the same JSONL fields.
- New reproducible **query log**: `--log FILE` or `$SURVEY_QUERY_LOG` (PubMed, Europe PMC, S2 search/bulk, OpenAlex search) records the verbatim query, hit count, retrieved count, time and output file.
- `search_s2.py`: HTTP 429 → backoff retries (`--retries`, `--max-wait`), then graceful stop: keeps records fetched so far, prints fallbacks, exit code 2 (no traceback).
- `search_openalex.py`: never hangs — "Insufficient budget" 429 stops immediately, bounded retries, `Retry-After` capped, overall `--timeout` (default 300 s), partial results kept, exit code 2.
- `common.http_get`: `max_wait` cap and `deadline`; fails fast on quota-exhausted 429 bodies.
- bioRxiv/medRxiv **`10.64898/`** DOIs (openRxiv, from 2025-12-01) recognised alongside date-shaped `10.1101/` DOIs (CSHL journal DOIs such as `10.1101/gr.…` are not preprints) in merge, export and checks; `search_biorxiv.py doi` accepts doi.org URLs and falls back to medRxiv; docs point keyword searches to Europe PMC.
- `search_crossref.py`: `date` = published-online/posted (first public date), plus `date_online` / `date_print`.
- `merge_dedup.py`: preprint→published merge via bioRxiv `published` (`preprint_doi` kept), earliest date kept, titles cleaned (HTML, trailing period), CSV gains `featured`, `first_author`, `pmid`, `preprint_doi` and `--csv-sort citations`; works draft uses the right preprint server name, `venue_type`, `pmid`, `citations`, `country_guess` (hint only).
- `countries.guess_country()` affiliation → ISO2 hint used by PubMed / Europe PMC output.

### Export
- `export_bibtex.py`: parses "Smith AB" (PubMed), "Smith, Anna" and "Anna Smith"; writes "Last, First"; cite keys use the real surname; consortium / group authors and `corporate_author` become one corporate author (`{GTEx Consortium}` in BibTeX, no comma in RIS); "et al." → `and others`; non-arXiv preprints get `howpublished`/`publisher` (bioRxiv, medRxiv …); `preprint_doi` goes into the note; titles double-braced to keep capitalisation.

### Repos, links, screenshots
- New `check_urls.py`: HEAD→GET with timeout, ok / blocked / dead classification, TSV/JSON report, `--write` stores status in `portals.json`.
- `github_repos.py`: in the HTML/Atom fallback, licenses are inferred from raw LICENSE / COPYING / R `DESCRIPTION`.
- `screenshot.py`: uses bundled Chromium or auto-detects system Chrome/Chromium/Edge; captures **every** visible section (incl. summary, scope, trends, caveats, portals) and slices tall sections into viewport-sized images.

### Docs
- SKILL.md and `references/literature-search.md`: domain-aware source sets (life sciences vs CS vs others), Europe PMC, MeSH / consortium-author tips, first-public-date rule, preprint DOI prefixes, author-format rules, consortium counting rule, featured landmarks, portals and link checks. The "no default time range" rule is unchanged.

### Not changed (by design)
- The Natural Earth world map is still downloaded on first build and cached (`--world` / `--no-download` for offline use).

## 2026-10-01 · v1.1
- Removed the default time range: date filters are applied only when the user explicitly asks; otherwise the report says "未设时间限制".

## 2026-10-01 · v1.0
- Initial release: literature-search playbook + JSON → interactive single-file HTML survey pipeline.
