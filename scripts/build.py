#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render a survey data folder into ONE self-contained offline HTML file.

Usage
  python scripts/build.py examples/agent-science-mini -o out/survey.html
  python scripts/build.py DATA_DIR --check            # validate data only
  python scripts/build.py DATA_DIR --world my.geojson # use your own (e.g. officially approved) map

Data folder layout (see references/data-schema.md)
  meta.json  works.json  teams.json  repos.json  timeline.json  portals.json (optional)
  (repos.json may be absent/empty when every direction is marked "repo_expected": false, e.g. wet-lab topics)
  narrative/{summary,scope,challenges,caveats}.html

Third-party assets inlined into the output
  * scripts/vendor/echarts.min.js  Apache ECharts 5.6.0 (Apache-2.0, see vendor/NOTICE-echarts.txt)
  * world GeoJSON: NOT committed. Downloaded at build time from Natural Earth (public domain)
    into scripts/.cache/ and normalised to ISO-3166 alpha-2 names. Override with --world.
"""
import argparse
import collections
import datetime as dt
import html
import json
import math
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from countries import COUNTRIES  # noqa: E402
from common import is_preprint_doi, norm_doi  # noqa: E402

NE_URLS = [
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_{res}_admin_0_countries.geojson",
    "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@master/geojson/ne_{res}_admin_0_countries.geojson",
]
CACHE = os.path.join(HERE, ".cache")
PALETTE = ["#8b5cf6", "#0ea5e9", "#10b981", "#ef4444", "#f59e0b", "#6366f1", "#14b8a6", "#ec4899",
           "#64748b", "#b91c1c", "#84cc16", "#a16207", "#7c3aed", "#0d9488", "#db2777", "#2563eb"]

LABELS = {
 "zh": dict(
  toc="目录", sec_summary="执行摘要", sec_scope="范围、方法与计数口径", sec_timeline="发展路径",
  sec_taxonomy="方向分类体系", sec_works="代表性工作", sec_teams="团队与进展", sec_map="地区热力图",
  sec_oss="开源项目", sec_trends="开放挑战与未来趋势", sec_caveats="注意事项与未核实项", sec_refs="参考文献与资料来源",
  desc_timeline="点击阶段卡片或类别标签可筛选时间轴；点击事件可展开详情与来源链接。下方图表按时间段统计各方向代表作数量（按主方向计）。",
  desc_taxonomy="把领域划分为若干相互交叉的子方向（一项工作可属于多个方向）。点击树图中的方向节点可跳转并筛选代表作。",
  desc_works="同时收录预印本与同行评审论文，并逐条标注发表状态。可按方向、状态、年份筛选，支持关键词搜索；点击表头排序。",
  desc_teams="进展等级：{levels}。只陈述有公开来源的事实；机构自报结果单独注明。",
  desc_map="颜色深浅代表本报告收录的团队数（或代表作数）。悬停查看数字，点击国家在右侧面板查看团队、方向与代表作。计数口径见“范围与方法”。",
  desc_oss="GitHub 数据抓取于 <b>{check}</b>。活跃度按最近一次提交距检查日的天数划分：≤{t0} 天高度活跃，≤{t1} 天活跃，≤{t2} 天维护放缓，更久为停滞。点击表格行可展开架构、运行方式、依赖与局限。",
  desc_refs="由表格与时间轴中的条目自动汇总，并补充官方博客、新闻与开源仓库链接。",
  stat_works="代表性工作", stat_peer="其中同行评审", stat_teams="团队/机构", stat_repos="开源项目（已核查）", stat_countries="国家/地区",
  chart_period="代表性工作数量：按{period} × 方向", period_half="半年", period_year="年", period_quarter="季度",
  h1="上半年", h2="下半年", count_axis="条目数（按主方向）",
  all_dirs="全部方向", all_status="全部状态", peer_only="仅同行评审", pre_only="仅预印本/其他", all_years="全部年份",
  search_ph="搜索名称/机构/贡献…", count="共 {n} 条（同行评审 {p}）",
  th_date="日期", th_name="工作", th_dirs="方向", th_inst="机构", th_status="状态", th_contrib="核心贡献",
  all_regions="全部地区", all_types="全部类型", progress="进展等级", rep_works="代表作",
  map_by_team="按团队数", map_by_work="按代表作数", map_click="点击地图上的国家", teams_n="团队", works_n="代表作",
  dir_dist="方向分布", none_in_country="本报告未收录该国家/地区的团队或工作。", cty_team_title="各国团队数",
  cty_work_title="各国代表作数", radar_title="{names} 团队方向覆盖（团队数）", more="多", less="少",
  act=["高度活跃", "活跃", "维护放缓", "停滞"], stars_title="GitHub Stars Top {n}（对数坐标）",
  act_title="活跃度：距最近提交天数 vs Stars", days="天", all_cats="全部分类",
  th_repo="仓库", th_cat="分类", th_stars="Stars", th_forks="Forks", th_last="最近提交", th_rel="最近 Release",
  th_act="活跃度", th_lic="许可证", th_desc="简介", det_arch="架构/组件", det_run="如何运行", det_deps="依赖", det_lim="局限",
  source="来源 ↗", all_ev_cats="全部类别", no_events="无匹配事件", main_challenge="主要难题：",
  see_works="查看该方向代表作 →", tree_click="点击筛选代表作", lic_none="未声明", repo_ref="开源仓库",
  range_since="{start} 起", range_until="截至 {end}",
  sec_portals="数据门户与资源", desc_portals="数据门户、数据库、在线工具与浏览器（区别于开源代码仓库）。“链接状态”来自 check_urls.py 的检查结果（{checked}）；✗ 表示检查时无法访问。",
  th_portal="名称", th_kind="类型", th_org="机构", th_scope="覆盖范围/数据", th_access="访问方式", th_url="链接状态", all_kinds="全部类型",
  url_ok="✓ 可访问", url_dead="✗ 无法访问", url_blocked="? 拒绝脚本访问", url_unchecked="未检查",
  featured_only="★ 仅里程碑", featured_tip="里程碑/旗舰工作", preprint_link="预印本", act_stable="成熟稳定（低频更新）",
  oss_by_dir="各方向开源情况", oss_norepo_dirs="以实验为主、不发布代码仓库的方向", no_repo_badge="无代码仓库",
  no_repo_default="该方向以湿实验为主，通常不发布代码仓库。", alt_resources="可用的非代码资源（数据集/实验方案/数据门户/生物样本库）：",
  repos_n="{n} 个仓库", repos_none="本报告未收录该方向的仓库",
  desc_oss_none="本报告收录的方向以实验研究为主，通常不发布代码仓库，因此未收录 GitHub 仓库；各方向可用的数据集、实验方案与数据门户见下。",
  footer="本报告基于公开资料整理（检查日期 {check}）。“自报”“未核实”等标注请留意；引用时请以原始来源为准。"),
 "en": dict(
  toc="Contents", sec_summary="Executive summary", sec_scope="Scope, method & counting rules", sec_timeline="Timeline",
  sec_taxonomy="Taxonomy", sec_works="Representative works", sec_teams="Teams & progress", sec_map="Geographic heatmap",
  sec_oss="Open-source projects", sec_trends="Open challenges & trends", sec_caveats="Caveats & unverified items", sec_refs="References",
  desc_timeline="Click a phase card or category chip to filter; click an event to expand details. The chart counts works per period and primary direction.",
  desc_taxonomy="Overlapping sub-directions (a work can belong to several). Click a direction node to filter the works table.",
  desc_works="Preprints and peer-reviewed papers are both included and labelled. Filter by direction/status/year, search, click headers to sort.",
  desc_teams="Progress levels: {levels}. Facts only from public sources; self-reported claims are labelled.",
  desc_map="Colour = number of teams (or works) included in this report. Hover for counts; click a country to list teams and works.",
  desc_oss="GitHub data fetched on <b>{check}</b>. Activity by days since last commit: ≤{t0} very active, ≤{t1} active, ≤{t2} slowing, otherwise stale. Click a row for details.",
  desc_refs="Collected automatically from the tables and timeline, plus blogs, news and repositories.",
  stat_works="Representative works", stat_peer="Peer-reviewed", stat_teams="Teams", stat_repos="Repos checked", stat_countries="Countries/regions",
  chart_period="Works per {period} × direction", period_half="half-year", period_year="year", period_quarter="quarter",
  h1="H1", h2="H2", count_axis="Works (primary direction)",
  all_dirs="All directions", all_status="All status", peer_only="Peer-reviewed only", pre_only="Preprint/other only", all_years="All years",
  search_ph="Search name / institution / contribution…", count="{n} items ({p} peer-reviewed)",
  th_date="Date", th_name="Work", th_dirs="Directions", th_inst="Institution", th_status="Status", th_contrib="Contribution",
  all_regions="All regions", all_types="All types", progress="Progress", rep_works="Key works",
  map_by_team="By teams", map_by_work="By works", map_click="Click a country", teams_n="Teams", works_n="Works",
  dir_dist="Directions", none_in_country="No team or work from this country in this report.", cty_team_title="Teams per country",
  cty_work_title="Works per country", radar_title="Direction coverage: {names} (teams)", more="more", less="less",
  act=["Very active", "Active", "Slowing", "Stale"], stars_title="GitHub stars, top {n} (log scale)",
  act_title="Days since last commit vs stars", days="days", all_cats="All categories",
  th_repo="Repo", th_cat="Category", th_stars="Stars", th_forks="Forks", th_last="Last commit", th_rel="Latest release",
  th_act="Activity", th_lic="License", th_desc="Summary", det_arch="Architecture", det_run="How to run", det_deps="Dependencies", det_lim="Limitations",
  source="source ↗", all_ev_cats="All categories", no_events="No matching events", main_challenge="Key challenges: ",
  see_works="See works →", tree_click="click to filter works", lic_none="none declared", repo_ref="repository",
  range_since="since {start}", range_until="until {end}",
  sec_portals="Data portals & resources", desc_portals="Data portals, databases, web tools and browsers (as opposed to code repositories). Link status comes from check_urls.py ({checked}); ✗ = unreachable when checked.",
  th_portal="Name", th_kind="Type", th_org="Organisation", th_scope="Coverage / data", th_access="Access", th_url="Link status", all_kinds="All types",
  url_ok="✓ reachable", url_dead="✗ unreachable", url_blocked="? blocks scripts", url_unchecked="not checked",
  featured_only="★ Landmarks only", featured_tip="landmark / flagship work", preprint_link="preprint", act_stable="Mature (infrequent updates)",
  oss_by_dir="Open source by direction", oss_norepo_dirs="Experimental directions without code repositories", no_repo_badge="no code repos",
  no_repo_default="Mainly wet-lab / experimental work; code repositories are usually not released.",
  alt_resources="Non-code resources (datasets, protocols, data portals, biobanks):",
  repos_n="{n} repos", repos_none="no repository included",
  desc_oss_none="The directions covered are mainly experimental and usually do not release code, so no GitHub repositories are listed; datasets, protocols and portals per direction are shown below.",
  footer="Compiled from public sources (checked {check}). Mind the 'self-reported' / 'unverified' labels; cite original sources."),
}
DEFAULT_LEVELS = {"zh": ["原型/基准", "论文或开源系统", "高影响力发表或实验验证", "产品化/规模化应用"],
                  "en": ["prototype/benchmark", "paper or open-source system", "high-impact publication or validated result", "product/deployment"]}

errors, warnings = [], []


def err(m):
    errors.append(m)


def warn(m):
    warnings.append(m)


def load(d, name, default):
    p = os.path.join(d, name)
    if not os.path.exists(p):
        warn(f"{name} missing -> section hidden")
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [x.strip() for x in str(v).replace(",", ";").split(";") if x.strip()]


# ---------------------------------------------------------------- world map
def fetch_world(no_download=False, res="110m"):
    """res: 110m (~0.8 MB raw, no micro-states such as SG/HK) or 50m (~4.6 MB raw, includes them)."""
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"ne_{res}_admin_0_countries.geojson")
    if os.path.exists(p) and os.path.getsize(p) > 100000:
        return p
    if no_download:
        sys.exit("world map not cached and --no-download given; pass --world PATH")
    for u in NE_URLS:
        u = u.format(res=res)
        try:
            print(f"[build] downloading Natural Earth {res} countries (public domain): {u}")
            req = urllib.request.Request(u, headers={"User-Agent": "research-survey-html"})
            data = urllib.request.urlopen(req, timeout=60).read()
            json.loads(data)
            open(p, "wb").write(data)
            return p
        except Exception as e:  # try mirror
            print(f"[build]   failed: {e}")
    sys.exit("could not download world map; pass --world PATH to a GeoJSON file")


def _round(c, nd=2):
    if isinstance(c, (int, float)):
        return round(c, nd)
    return [_round(x, nd) for x in c]


def normalise_world(path, merge=None, drop=("AQ",)):
    """Return compact GeoJSON whose feature `name` is an ISO alpha-2 code where possible.

    merge: {"TW": "CN"} folds one feature's geometry into another; drop: codes to remove
    (Antarctica by default, which otherwise wastes vertical space)."""
    g = json.load(open(path, encoding="utf-8"))
    merge = merge or {}
    drop = set(drop or ())
    feats = {}
    order = []
    for f in g["features"]:
        pr = f.get("properties") or {}
        code = None
        for k in ("ISO_A2_EH", "ISO_A2", "iso_a2", "ISO3166-1-Alpha-2", "iso2"):
            v = pr.get(k)
            if v and len(str(v)) == 2 and v != "-9":
                code = str(v).upper()
                break
        if not code:  # fall back to English name lookup
            nm = pr.get("NAME") or pr.get("name") or pr.get("ADMIN") or ""
            code = next((c for c, (_, e) in COUNTRIES.items() if e == nm), nm)
        code = merge.get(code, code)
        if code in drop or pr.get("NAME") == "Antarctica" and "AQ" in drop:
            continue
        geom = f.get("geometry")
        if not geom:
            continue
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        polys = _round(polys)
        if code in feats:
            feats[code].extend(polys)
        else:
            feats[code] = list(polys)
            order.append(code)
    out = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": c},
         "geometry": {"type": "MultiPolygon", "coordinates": feats[c]}} for c in order]}
    return json.dumps(out, separators=(",", ":"))


# ---------------------------------------------------------------- validation & derivation
def repo_info(d):
    """(repo_expected, reason) for a direction. Directions whose work is wet-lab/experimental can opt out of code
    repos with `"repo_expected": false` (+ optional `"no_repo_reason"`), or the alias `"no_repo": true | "reason"`."""
    nr = d.get("no_repo")
    expected = d.get("repo_expected", True) is not False and not nr
    reason = d.get("no_repo_reason") or (nr if isinstance(nr, str) else "")
    return expected, str(reason or "").strip()


def norm_resources(v):
    """Direction `resources`: list of {name, url, kind, note} (a bare string = name only)."""
    out = []
    for x in v or []:
        x = {"name": x} if isinstance(x, str) else dict(x or {})
        out.append({k: str(x.get(k) or "").strip() for k in ("name", "url", "kind", "note")})
    return out


DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def get_time_range(meta):
    """User-specified time range as {"start"?, "end"?} with empty values dropped.

    There is NO default: an absent/empty `time_range` means no time restriction was applied."""
    tr = meta.get("time_range") or {}
    if not isinstance(tr, dict):
        return {}
    return {k: str(tr[k]).strip() for k in ("start", "end") if str(tr.get(k) or "").strip()}


def range_label(tr, L):
    """Human-readable period for the header; "" when no time range was specified."""
    s, e = tr.get("start"), tr.get("end")
    if s and e:
        return f"{s} – {e}"
    if s:
        return L["range_since"].format(start=s)
    if e:
        return L["range_until"].format(end=e)
    return ""


def _outside(date, tr):
    s, e = tr.get("start"), tr.get("end")
    return bool(date) and ((s and date[:len(s)] < s[:len(date)]) or (e and date[:len(e)] > e[:len(date)]))


def validate(meta, works, teams, repos, events, portals=()):
    dk = [d["key"] for d in meta.get("directions", [])]
    if not dk:
        err("meta.directions is empty")
    raw_tr = meta.get("time_range")
    if raw_tr not in (None, {}, "") and not isinstance(raw_tr, dict):
        err("meta.time_range must be an object {start, end} (omit it when the user set no time range)")
    tr = get_time_range(meta)
    for k, v in tr.items():
        if not DATE_RE.match(v):
            err(f"meta.time_range.{k} must be YYYY, YYYY-MM or YYYY-MM-DD")
    if tr.get("start") and tr.get("end") and tr["start"] > tr["end"]:
        err("meta.time_range.start is after meta.time_range.end")
    no_repo = set()
    for i, d in enumerate(meta.get("directions", [])):
        tag = f"directions[{i}] {d.get('key', '?')}"
        if "repo_expected" in d and not isinstance(d["repo_expected"], bool):
            err(f"{tag}: repo_expected must be true/false")
        if not repo_info(d)[0]:
            no_repo.add(d.get("key"))
        if d.get("resources") is not None and not isinstance(d["resources"], list):
            err(f"{tag}: resources must be a list of {{name, url, kind, note}}")
        else:
            for j, x in enumerate(norm_resources(d.get("resources"))):
                if not x["name"]:
                    err(f"{tag}: resources[{j}] missing 'name'")
                elif not x["url"]:
                    warn(f"{tag}: resources[{j}] {x['name']}: no 'url' (link the dataset/protocol/portal page if one exists)")
    phases = {p["key"] for p in meta.get("phases", [])}
    seen = {}
    for i, w in enumerate(works):
        tag = f"works[{i}] {w.get('name', '?')}"
        for k in ("name", "dirs", "date", "status", "url"):
            if not w.get(k):
                err(f"{tag}: missing '{k}'")
        if "peer" not in w:
            err(f"{tag}: missing 'peer' (true/false)")
        for d in as_list(w.get("dirs")):
            if d not in dk:
                err(f"{tag}: unknown direction '{d}'")
        if w.get("date") and not DATE_RE.match(w["date"]):
            err(f"{tag}: date must be YYYY, YYYY-MM or YYYY-MM-DD")
        elif tr and _outside(w.get("date", ""), tr):
            warn(f"{tag}: date {w['date']} is outside the user-specified meta.time_range")
        c = w.get("country", "")
        if c and c not in COUNTRIES:
            warn(f"{tag}: country '{c}' not in countries.py (add it for a Chinese label)")
        key = w.get("arxiv") or w.get("doi") or w.get("url")
        if key in seen:
            warn(f"{tag}: duplicate of {seen[key]} ({key})")
        seen[key] = tag
        if not w.get("checked"):
            warn(f"{tag}: no 'checked' date")
        if w.get("peer") and is_preprint_doi(w.get("doi")):
            warn(f"{tag}: peer=true but doi {w.get('doi')} is a preprint DOI (bioRxiv/medRxiv 10.1101/10.64898 …); "
                 "use the journal DOI and put the preprint in 'preprint_doi'")
        if not w.get("peer") and w.get("doi") and not is_preprint_doi(w["doi"]) and re.search(r"预印本|preprint", str(w.get("status")), re.I):
            warn(f"{tag}: status says preprint but doi {w['doi']} is not a known preprint DOI — published already?")
        if any(re.fullmatch(r"et\.? ?al\.?|等", str(a).strip(), re.I) for a in (w.get("authors") or [])):
            warn(f"{tag}: authors contains 'et al.' — list all authors (export turns a literal 'et al.' into BibTeX 'and others')")
        if w.get("date") and meta.get("check_date") and w["date"] > meta["check_date"]:
            warn(f"{tag}: date {w['date']} is after check_date (issue date in the future? use the online date)")
    for i, t in enumerate(teams):
        tag = f"teams[{i}] {t.get('name', '?')}"
        for k in ("name", "country", "type", "dirs"):
            if not t.get(k):
                err(f"{tag}: missing '{k}'")
        if t.get("country") and t["country"] not in COUNTRIES:
            warn(f"{tag}: country '{t['country']}' not in countries.py")
        if not 1 <= int(t.get("progress", 0) or 0) <= 4:
            err(f"{tag}: progress must be 1-4")
        for d in as_list(t.get("dirs")):
            if d not in dk:
                err(f"{tag}: unknown direction '{d}'")
    for i, e in enumerate(events):
        tag = f"timeline[{i}] {e.get('title', '?')}"
        for k in ("date", "title", "url"):
            if not e.get(k):
                err(f"{tag}: missing '{k}'")
        if e.get("date") and tr and _outside(e["date"], tr):
            warn(f"{tag}: date {e['date']} is outside the user-specified meta.time_range")
        if phases and e.get("phase") not in phases:
            warn(f"{tag}: phase '{e.get('phase')}' not in meta.phases")
    for i, p in enumerate(portals):
        tag = f"portals[{i}] {p.get('name', '?')}"
        for k in ("name", "url"):
            if not p.get(k):
                err(f"{tag}: missing '{k}'")
        if p.get("url_status") == "dead":
            warn(f"{tag}: url was unreachable on {p.get('url_checked', '?')} (check_urls.py) — fix the link or say so in the report")
        elif not p.get("url_checked"):
            warn(f"{tag}: url not checked yet -> run check_urls.py <data_dir> --only portals --write")
        for d in as_list(p.get("dirs")):
            if d not in dk:
                err(f"{tag}: unknown direction '{d}'")
    n_leaves = int(meta.get("tree_leaves", 4))
    for k in dk:
        nf = sum(1 for w in works if w.get("featured") and k in as_list(w.get("dirs")))
        if nf > n_leaves:
            warn(f"direction {k}: {nf} featured works but tree_leaves={n_leaves}; only the first {n_leaves} (by date) are drawn")
    if works and not any(w.get("featured") for w in works):
        warn("no work has featured=true: tree leaves are picked automatically "
             f"(tree_sort={meta.get('tree_sort', 'auto')}); mark landmark/flagship works with \"featured\": true")
    # NB: a direction with zero repos is fine (no warning) — many directions, e.g. wet-lab ones, publish no code
    for i, r in enumerate(repos):
        if not r.get("repo") or "/" not in r["repo"]:
            err(f"repos[{i}]: 'repo' must be owner/name")
        for d in as_list(r.get("dirs")):
            if d not in dk:
                err(f"repos[{i}] {r.get('repo')}: unknown direction '{d}'")
            elif d in no_repo:
                warn(f"repos[{i}] {r.get('repo')}: direction '{d}' is marked repo_expected=false but has this repo — drop the flag or the tag")
        if r.get("stars") is None:
            warn(f"repos[{i}] {r.get('repo')}: no stars yet -> run github_repos.py")


def derive(meta, works, teams, repos, events, lang, portals=()):
    L = dict(LABELS.get(lang, LABELS["zh"]))
    L.update(meta.get("labels", {}))
    check = meta.get("check_date") or dt.date.today().isoformat()
    check_d = dt.date.fromisoformat(check)
    th = meta.get("activity_thresholds", [30, 90, 365])
    acts = L["act"]
    for w in works:
        w["dirs"] = ";".join(as_list(w["dirs"]))
        w.setdefault("inst", "")
        w.setdefault("country", "")
        w.setdefault("contrib", "")
        w["peer"] = bool(w.get("peer"))
        w["featured"] = bool(w.get("featured") or w.get("landmark"))
        if w.get("preprint_doi") and not w.get("preprint_url"):
            w["preprint_url"] = "https://doi.org/" + norm_doi(w["preprint_doi"])
    for t in teams:
        t["dirs"] = ";".join(as_list(t["dirs"]))
        t["works"] = "; ".join(as_list(t.get("works"))) if isinstance(t.get("works"), list) else t.get("works", "")
        t["progress"] = int(t["progress"])
        t["regionLabel"] = t.get("region") or COUNTRIES.get(t["country"], (t["country"], t["country"]))[0 if lang == "zh" else 1]
        t.setdefault("ach", "")
    out_repos = []
    for r in repos:
        if r.get("stars") is None or r.get("exclude"):
            continue
        last = (r.get("last_commit") or r.get("pushed_at") or "")[:10]
        days = (check_d - dt.date.fromisoformat(last)).days if last else 99999
        act = acts[0] if days <= th[0] else acts[1] if days <= th[1] else acts[2] if days <= th[2] else acts[3]
        # stable=true (hand-set): mature tool, rarely updated on purpose -> not "stale" in the table
        act_label = L["act_stable"] if r.get("stable") and act == acts[3] else act
        rel = r.get("release") or {}
        if isinstance(rel, list):
            rel = {"tag": rel[0], "date": rel[1]} if rel else {}
        rel_s = "—"
        if rel.get("tag"):
            tag = rel["tag"]
            rel_s = (tag[:22] + ("…" if len(tag) > 22 else "")) + (f" ({rel.get('date', '')[:10]})" if rel.get("date") else "")
        lic = r.get("license_note") or r.get("license") or L["lic_none"]
        out_repos.append(dict(repo=r.get("canonical") or r["repo"], stars=int(r["stars"]), forks=int(r.get("forks") or 0),
                              license=lic, last=last or "—", days=days, act=act, actIdx=acts.index(act), rel=rel_s,
                              actLabel=act_label, stable=act_label != act,
                              cat=r.get("cat", "—"), what=r.get("what") or r.get("description", ""),
                              arch=r.get("arch", ""), run=r.get("run", ""), deps=r.get("deps", ""), lim=r.get("lim", ""),
                              archived=bool(r.get("archived")), dirs=";".join(as_list(r.get("dirs")))))
    out_repos.sort(key=lambda x: -x["stars"])

    # references (unique by URL)
    refs, seen = [], set()

    def add(t, u, n=""):
        if u and u not in seen:
            seen.add(u)
            refs.append(dict(t=t, l=u, n=n))
    for w in sorted(works, key=lambda x: x["date"]):
        add(w.get("title") or w["name"], w["url"], w["status"])
    for e in sorted(events, key=lambda x: x["date"]):
        add(e["title"], e["url"], e["date"])
    out_portals = []
    for p in portals:
        q = dict(p)
        q["dirs"] = ";".join(as_list(p.get("dirs")))
        for k in ("kind", "org", "scope", "access", "desc", "note", "url_status", "url_checked", "launched", "works"):
            q[k] = "; ".join(as_list(q.get(k))) if k == "works" and isinstance(q.get(k), list) else str(q.get(k) or "")
        out_portals.append(q)
    for x in meta.get("extra_refs", []):
        add(x["title"], x["url"], x.get("note", ""))
    for p in out_portals:
        add(p["name"], p["url"], p["kind"] or L["sec_portals"])
    for r in out_repos:
        add("GitHub: " + r["repo"], "https://github.com/" + r["repo"], L["repo_ref"])

    dirs = {}
    for i, d in enumerate(meta["directions"]):
        expected, reason = repo_info(d)
        dirs[d["key"]] = dict(name=d["name"], en=d.get("en", ""), short=d.get("short") or d["name"],
                              color=d.get("color") or PALETTE[i % len(PALETTE)],
                              summary=d.get("summary", ""), challenges=d.get("challenges", ""))
        if not expected:  # no-code direction: note + non-code resources (own list, then portals tagged with it)
            res = norm_resources(d.get("resources"))
            urls = {x["url"] for x in res if x["url"]}
            res += [dict(name=p["name"], url=p["url"], kind=p["kind"] or L["sec_portals"], note="")
                    for p in out_portals if d["key"] in as_list(p["dirs"]) and p["url"] not in urls]
            dirs[d["key"]].update(repo_expected=False, no_repo_note=reason, resources=res)
            for x in res:
                if x["url"]:
                    add(x["name"], x["url"], x["kind"] or L["alt_resources"].rstrip("：:"))
    cats = meta.get("event_categories", {})
    for i, c in enumerate(sorted({e.get("cat", "") for e in events} - set(cats))):
        cats[c] = PALETTE[(i + 3) % len(PALETTE)]
    names = {c: (v[0] if lang == "zh" else v[1]) for c, v in COUNTRIES.items()}
    names.update(meta.get("country_names", {}))
    cnt_team = collections.Counter(t["country"] for t in teams if t["country"])
    cnt_work = collections.Counter(w["country"] for w in works if w["country"])
    tr = get_time_range(meta)  # no time range -> chart axis spans the data's own years
    years = sorted({int(w["date"][:4]) for w in works} | {int(e["date"][:4]) for e in events})
    y0 = int(str(tr.get("start", years[0] if years else check[:4]))[:4])
    y1 = int(str(tr.get("end", years[-1] if years else check[:4]))[:4])
    y1 = max(y0, y1)
    # period: explicit meta.period wins; otherwise pick by the span (long histories -> years)
    span = y1 - y0 + 1
    period = meta.get("period") or ("year" if span > 6 else "quarter" if span <= 1 else "half")
    # taxonomy-tree leaf selection: featured works always first, then tree_sort
    ts = meta.get("tree_sort", "auto")
    if ts == "auto":
        ts = "citations" if any(w.get("citations") for w in works) else ("recent" if tr else "spread")
    levels = meta.get("progress_levels") or DEFAULT_LEVELS.get(lang, DEFAULT_LEVELS["zh"])
    radar = meta.get("radar_countries") or [c for c, _ in cnt_team.most_common(3)]
    data = dict(works=works, teams=teams, events=events, repos=out_repos, dirs=dirs, phases=meta.get("phases", []),
                cats=cats, names=names, cntTeam=cnt_team, cntWork=cnt_work, refs=refs, L=L, levels=levels,
                years=[y0, y1], period=period, radar=radar, treeSort=ts, portals=out_portals,
                portalsChecked=max((p["url_checked"] for p in out_portals if p["url_checked"]), default=""),
                taxRoot=meta.get("taxonomy_root") or meta.get("title", ""), topN=int(meta.get("repo_top_n", 30)),
                treeLeaves=int(meta.get("tree_leaves", 4)), mapCenter=meta.get("map", {}).get("center"),
                mapZoom=meta.get("map", {}).get("zoom", 1.2))
    return data, L, check, th, levels


# ---------------------------------------------------------------- render
def esc(s):
    return html.escape(str(s or ""), quote=True)


def render(d, out, world_arg=None, echarts_arg=None, no_download=False):
    meta = load(d, "meta.json", None)
    if meta is None:
        sys.exit("meta.json is required")
    works = load(d, "works.json", [])
    teams = load(d, "teams.json", [])
    all_norepo = bool(meta.get("directions")) and all(not repo_info(x)[0] for x in meta["directions"])
    repos = [] if all_norepo and not os.path.exists(os.path.join(d, "repos.json")) else load(d, "repos.json", [])
    events = load(d, "timeline.json", [])
    portals = load(d, "portals.json", []) if os.path.exists(os.path.join(d, "portals.json")) else []
    validate(meta, works, teams, repos, events, portals)
    for w in warnings:
        print("[warn]", w)
    if errors:
        for e in errors:
            print("[error]", e)
        sys.exit(f"{len(errors)} data error(s); fix them and rebuild")
    if out is None:
        print("[check] data OK")
        return
    lang = meta.get("lang", "zh-CN")[:2]
    data, L, check, th, levels = derive(meta, works, teams, repos, events, lang, portals)

    def narrative(name):
        p = os.path.join(d, "narrative", name + ".html")
        return open(p, encoding="utf-8").read() if os.path.exists(p) else ""

    echarts = open(echarts_arg or os.path.join(HERE, "vendor", "echarts.min.js"), encoding="utf-8").read()
    wp = world_arg or meta.get("map", {}).get("geojson")
    if wp and not os.path.isabs(wp) and not os.path.exists(wp):
        wp = os.path.join(d, wp)
    mp = meta.get("map", {})
    world = normalise_world(wp or fetch_world(no_download, mp.get("resolution", "110m")), mp.get("merge"), mp.get("drop", ["AQ"]))
    on_map = set(re.findall(r'"name":"([^"]+)"', world))
    missing = sorted((set(data["cntTeam"]) | set(data["cntWork"])) - on_map)
    if missing:
        print(f"[warn] counted but not drawable on this map: {missing} "
              f"(shown in bar chart/panel only; use \"map\": {{\"resolution\": \"50m\"}} or --world)")

    dir_css = "".join(f"--d-{k}:{v['color']};" for k, v in data["dirs"].items())
    dir_cards = "".join(
        f'<div class="dcard" style="--c:{v["color"]}"><div class="dh"><span class="dk">{esc(k)}</span><h3>{esc(v["name"])}</h3>'
        f'<span class="den">{esc(v["en"])}</span></div><p>{v["summary"]}</p>'
        + (f'<p class="dchal"><b>{L["main_challenge"]}</b>{v["challenges"]}</p>' if v["challenges"] else "")
        + (f'<p class="legend-note"><span class="tag nrb">{esc(L["no_repo_badge"])}</span> {esc(v["no_repo_note"] or L["no_repo_default"])}</p>'
           if v.get("repo_expected") is False else "")
        + f'<a class="dlink" href="#works" onclick="filterDir(\'{esc(k)}\')">{L["see_works"]}</a></div>'
        for k, v in data["dirs"].items())
    phase_cards = "".join(
        f'<div class="phase" data-ph="{esc(p["key"])}" onclick="setPhase(\'{esc(p["key"])}\')"><div class="pn">{esc(p["key"])}</div>'
        f'<h4>{esc(p["title"])}</h4><p>{esc(p.get("desc", ""))}</p></div>' for p in data["phases"])
    lv = "　".join(f"<b>{'①②③④'[i]}</b> {esc(x)}" for i, x in enumerate(levels))
    period = range_label(get_time_range(meta), L)  # "" when the user specified no time range
    kicker = meta.get("kicker") or ("RESEARCH SURVEY" + (f" · {period}" if period else ""))
    subs = {
        "LANG": esc(meta.get("lang", "zh-CN")), "TITLE": esc(meta.get("title", "Research Survey")),
        "TITLE_HTML": meta.get("title_html") or esc(meta.get("title", "")), "KICKER": esc(kicker),
        "SUBTITLE": meta.get("subtitle", ""), "DIRCSS": dir_css, "DIRCARDS": dir_cards, "PHASES": phase_cards,
        "SUMMARY": narrative("summary"), "SCOPE": narrative("scope"), "CHALLENGES": narrative("challenges"),
        "CAVEATS": narrative("caveats"),
        "FOOTER": meta.get("footer") or L["footer"].format(check=check),
        "DESC_TEAMS": L["desc_teams"].format(levels=lv),
        "DESC_OSS": L["desc_oss"].format(check=check, t0=th[0], t1=th[1], t2=th[2]) if data["repos"] else L["desc_oss_none"],
        "DESC_PORTALS": L["desc_portals"].format(checked=data["portalsChecked"] or L["url_unchecked"]),
    }
    for k, v in L.items():
        if isinstance(v, str):
            subs.setdefault("L_" + k, v)
    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    outh = re.sub(r"\{\{([A-Za-z_0-9]+)\}\}", lambda m: str(subs.get(m.group(1), m.group(0))), tpl)
    left = re.findall(r"\{\{[A-Za-z_0-9]+\}\}", outh)
    if left:
        warn(f"unfilled placeholders: {sorted(set(left))}")
    # inline big blobs last (they may contain '{{')
    outh = (outh.replace("/*ECHARTS*/", lambda_safe(echarts))
                .replace("/*WORLD*/", world)
                .replace("/*DATA*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, "w", encoding="utf-8").write(outh)
    print(f"[build] works={len(works)} teams={len(teams)} repos={len(data['repos'])} events={len(events)} portals={len(portals)} "
          f"refs={len(data['refs'])} -> {out} ({len(outh)/1e6:.2f} MB)")


def lambda_safe(s):
    # prevent an inlined script from closing the <script> tag early
    return s.replace("</script", "<\\/script")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_dir")
    ap.add_argument("-o", "--out", default=None, help="output HTML path")
    ap.add_argument("--check", action="store_true", help="validate data only")
    ap.add_argument("--world", help="GeoJSON path (default: Natural Earth 110m, downloaded & cached)")
    ap.add_argument("--echarts", help="path to echarts.min.js (default: scripts/vendor/echarts.min.js)")
    ap.add_argument("--no-download", action="store_true")
    a = ap.parse_args()
    if not a.check and not a.out:
        a.out = os.path.join(a.data_dir, "survey.html")
    render(a.data_dir, None if a.check else a.out, a.world, a.echarts, a.no_download)
