# Changelog

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
