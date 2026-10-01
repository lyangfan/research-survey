#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Citation snowballing and identifier harvesting — the non-keyword retrieval strategies.

Keyword search alone misses many classic works (methods papers rarely use the field's umbrella
term). This script implements the other mandatory strategies of references/literature-search.md §1b:

  refs        BACKWARD snowball: works cited BY the seeds (reviews / landmark papers)
  cites       FORWARD snowball: works citing the seeds
  repo-cites  DOIs / arXiv IDs / PMIDs in GitHub repos' README "Citation" sections and CITATION.cff
  page-ids    DOIs / PMIDs / arXiv IDs on web pages (consortium "Publications" pages, tool docs,
              portal "how to cite" pages)

Seeds: DOIs (or PMID:123 / PMCID / arXiv:2401.00001) as arguments or @file (one per line;
a TSV/CSV with a `doi` column, e.g. the must-include list, also works).

Sources for refs/cites (--via, default auto = first source that answers, in this order):
  refs : europepmc (keyless, PMID-based) -> crossref (keyless, publisher-deposited reference lists)
         -> s2 (S2_API_KEY recommended) -> openalex (OPENALEX_API_KEY)
  cites: europepmc (keyless) -> s2 -> openalex
--via all unions every source (slower, best recall); --via crossref,s2 = your own fallback order.
Europe PMC / Crossref hits that only carry a PMID or DOI are enriched to full records in batches
(Europe PMC search by EXT_ID / DOI) unless --no-enrich.

Output: standard candidate JSONL (same fields as the search scripts) plus
  found_via   ["snowball:refs"] / ["snowball:cites"] / ["repo-cite:<owner/repo>"] / ["page:<host>"]
  seeds       the seed IDs that led to the record;  seed_count = len(seeds)
Records are ranked by seed_count (co-citation by several seeds = strong signal), then citations.
--min-seeds 2 keeps only works linked to >= 2 seeds (useful for noisy forward snowballing).
Every seed x direction x source is appended to the search log ($SURVEY_QUERY_LOG / --log) as
source "snowball-refs:<via>" etc., so the method section can report what was done.

Examples
  python snowball.py refs 10.1038/s41576-018-0016-z 10.1038/s41588-018-0160-6 --out sb_refs.jsonl
  python snowball.py cites @seeds.txt --max 300 --min-seeds 2 --out sb_cites.jsonl
  python snowball.py refs @must_include.tsv --via all --out sb_refs_all.jsonl
  python snowball.py repo-cites stephenslab/susieR chr1swallace/coloc --out sb_repo.jsonl
  python snowball.py repo-cites @data/repos.json --out sb_repo.jsonl
  python snowball.py page-ids https://www.farmgtex.org/ https://gtexportal.org/home/publicationsPage --out sb_pages.jsonl
"""
import argparse
import html
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse

from common import (DOI_RE, clean_title, get_json, http_get, log, log_query, norm_arxiv, norm_doi, today,
                    write_jsonl)

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
NET_ERR = (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError)


# ---------------------------------------------------------------- seeds
def read_seeds(args):
    out = []
    for a in args:
        if a.startswith("@"):
            path = a[1:]
            if path.endswith(".json"):
                data = json.load(open(path, encoding="utf-8"))
                for x in data if isinstance(data, list) else []:
                    if isinstance(x, dict):
                        out.append(x.get("repo") or x.get("doi") or x.get("pmid") or x.get("arxiv") or "")
                    else:
                        out.append(str(x))
                continue
            txt = open(path, encoding="utf-8-sig").read()
            first = txt.splitlines()[0] if txt.strip() else ""
            if "\t" in first or ("," in first and "doi" in first.lower()):
                dl = "\t" if "\t" in first else ","
                for row in csv.DictReader(txt.splitlines(), delimiter=dl):
                    row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                    out.append(row.get("doi") or (("PMID:" + row["pmid"]) if row.get("pmid") else "") or row.get("arxiv", ""))
            else:
                out += [l.split("#")[0].strip() for l in txt.splitlines()]
        else:
            out.append(a)
    return [x for x in dict.fromkeys(s.strip() for s in out) if x]


def seed_kind(s):
    if re.match(r"(?i)^pmid:\s*\d+$", s) or re.fullmatch(r"\d{5,9}", s):
        return "pmid", re.sub(r"\D", "", s)
    if re.match(r"(?i)^pmc\d+$", s):
        return "pmcid", s.upper()
    if norm_doi(s):
        return "doi", norm_doi(s)
    if norm_arxiv(s):
        return "arxiv", norm_arxiv(s)
    return "unknown", s


# ---------------------------------------------------------------- Europe PMC
def epmc_id(seed):
    """(source, id) of a seed in Europe PMC, e.g. ('MED', '29618420'), or None."""
    k, v = seed_kind(seed)
    if k == "pmid":
        return "MED", v
    q = {"doi": f'DOI:"{v}"', "pmcid": f"PMCID:{v}", "arxiv": f'DOI:"10.48550/arxiv.{v}"'}.get(k)
    if not q:
        return None
    d = get_json(EPMC + "/search", params={"query": q, "format": "json", "pageSize": 3}, retries=3, backoff=4)
    res = (d.get("resultList") or {}).get("result") or []
    res.sort(key=lambda r: r.get("source") != "MED")
    return (res[0]["source"], res[0]["id"]) if res else None


def epmc_link(seed, kind, max_n):
    sid = epmc_id(seed)
    if not sid:
        return None
    key, item = ("referenceList", "reference") if kind == "refs" else ("citationList", "citation")
    ep = "references" if kind == "refs" else "citations"
    rows, page = [], 1
    while len(rows) < max_n:
        d = get_json(f"{EPMC}/{sid[0]}/{sid[1]}/{ep}", params={"format": "json", "pageSize": 1000, "page": page},
                     retries=3, backoff=4)
        got = (d.get(key) or {}).get(item) or []
        for x in got:
            rows.append(dict(source="europepmc-" + kind, title=clean_title(x.get("title") or x.get("unstructured") or ""),
                             authors=[a.strip() for a in (x.get("authorString") or "").rstrip(".").split(",") if a.strip()],
                             date=str(x.get("pubYear") or ""), venue=x.get("journalAbbreviation") or "",
                             doi=norm_doi(x.get("doi")), pmid=x.get("id") if x.get("source") == "MED" else "",
                             epmc_src=x.get("source", ""), epmc_id=x.get("id", ""), citations=x.get("citedByCount"),
                             checked=today()))
        hit = int(d.get("hitCount") or 0)
        if not got or len(rows) >= hit:
            break
        page += 1
    return rows[:max_n]


def epmc_enrich(rows):
    """Replace thin Europe PMC / Crossref link records by full Europe PMC records (batched)."""
    from search_europepmc import norm as ep_norm
    need = [r for r in rows if r.get("_thin", True) and (r.get("pmid") or r.get("doi"))]
    full = {}
    for i in range(0, len(need), 80):
        chunk = need[i:i + 80]
        terms = [f"EXT_ID:{r['pmid']} AND SRC:MED" if r.get("pmid") else f'DOI:"{r["doi"]}"' for r in chunk]
        q = " OR ".join(f"({t})" for t in terms)
        try:
            d = get_json(EPMC + "/search", params={"query": q, "format": "json", "resultType": "core", "pageSize": 1000},
                         retries=3, backoff=4)
        except NET_ERR as e:
            log(f"[snowball] enrich batch failed ({e}); keeping thin records")
            continue
        for x in (d.get("resultList") or {}).get("result") or []:
            r = ep_norm(x)
            if r.get("pmid"):
                full["pmid:" + str(r["pmid"])] = r
            if r.get("doi"):
                full["doi:" + r["doi"]] = r
        time.sleep(0.3)
    out = []
    for r in rows:
        f = full.get("pmid:" + str(r.get("pmid"))) if r.get("pmid") else None
        f = f or (full.get("doi:" + r["doi"]) if r.get("doi") else None)
        if f:
            f = dict(f)
            for k in ("found_via", "seeds"):
                f[k] = r.get(k)
            out.append(f)
        else:
            out.append(r)
    log(f"[snowball] enriched {sum(1 for r in out if r.get('source') == 'europepmc')}/{len(rows)} records via Europe PMC")
    return out


# ---------------------------------------------------------------- Crossref (backward only)
def crossref_refs(seed, max_n):
    k, v = seed_kind(seed)
    if k != "doi":
        return None
    from search_crossref import BASE as CR, _p as cr_p
    m = get_json(f"{CR}/works/{urllib.parse.quote(v)}", params=cr_p({}), retries=3, backoff=4)["message"]
    refs = m.get("reference") or []
    if not refs:
        return None
    rows = []
    for x in refs[:max_n]:
        t = x.get("article-title") or x.get("volume-title") or x.get("unstructured") or ""
        rows.append(dict(source="crossref-refs", title=clean_title(t), authors=[x["author"]] if x.get("author") else [],
                         date=str(x.get("year") or ""), venue=x.get("journal-title") or "", doi=norm_doi(x.get("DOI")),
                         checked=today()))
    return rows


# ---------------------------------------------------------------- S2 / OpenAlex
def s2_link(seed, kind, max_n):
    import search_s2 as s2
    k, v = seed_kind(seed)
    pid = {"doi": "DOI:", "pmid": "PMID:", "arxiv": "ARXIV:", "pmcid": "PMCID:"}.get(k, "") + v
    s2.RETRY.update(retries=2, max_wait=30)
    rows = s2.graph(pid, "references" if kind == "refs" else "citations", max_n)
    if not rows and s2.DEGRADED:
        raise urllib.error.URLError(s2.DEGRADED[-1])
    for r in rows:
        r["_thin"] = False
    return rows


def openalex_link(seed, kind, max_n):
    import search_openalex as oa
    k, v = seed_kind(seed)
    if k not in ("doi", "pmid"):
        return None
    oa.OPT.update(retries=1, timeout=120)
    w = oa._get(f"{oa.BASE}/works/{'doi:' + v if k == 'doi' else 'pmid:' + v}", oa._p({}))
    if not w:
        raise urllib.error.URLError(oa.STATE["degraded"] or "openalex unavailable")
    wid = w["id"].rsplit("/", 1)[-1]
    rows = []
    if kind == "refs":
        ids = [x.rsplit("/", 1)[-1] for x in w.get("referenced_works") or []][:max_n]
        for i in range(0, len(ids), 50):
            d = oa._get(oa.BASE + "/works", oa._p({"filter": "openalex:" + "|".join(ids[i:i + 50]), "per_page": 50}))
            if d is None:
                break
            rows += [oa.norm(x) for x in d.get("results", [])]
    else:
        cursor = "*"
        while cursor and len(rows) < max_n:
            d = oa._get(oa.BASE + "/works", oa._p({"filter": f"cites:{wid}", "per_page": min(200, max_n - len(rows)), "cursor": cursor}))
            if d is None:
                break
            rows += [oa.norm(x) for x in d.get("results", [])]
            cursor = (d.get("meta") or {}).get("next_cursor") if d.get("results") else None
    for r in rows:
        r["_thin"] = False
    return rows


VIA = {"refs": ["europepmc", "crossref", "s2", "openalex"], "cites": ["europepmc", "s2", "openalex"]}


def link_one(seed, kind, via, max_n):
    fn = {"europepmc": lambda: epmc_link(seed, kind, max_n), "crossref": lambda: crossref_refs(seed, max_n),
          "s2": lambda: s2_link(seed, kind, max_n), "openalex": lambda: openalex_link(seed, kind, max_n)}[via]
    try:
        return fn(), ""
    except NET_ERR as e:
        return None, f"{type(e).__name__}: {str(e)[:120]}"


def snowball(seeds, kind, vias, mode, max_n, log_path, out):
    acc, seen_any = {}, False
    for s in seeds:
        got_any = False
        for via in vias:
            rows, err = link_one(s, kind, via, max_n)
            n = len(rows or [])
            log(f"[snowball] {kind} {s} via {via}: " + (f"{n} records" if rows is not None else f"n/a ({err or 'not indexed'})"))
            log_query(log_path, f"snowball-{kind}:{via}", s, n if rows is not None else None, n, out,
                      kind="snowball", degraded="yes" if err else "")
            if rows:
                got_any = True
                for r in rows:
                    r["doi"] = norm_doi(r.get("doi"))
                    key = ("doi:" + r["doi"]) if r.get("doi") else ("pmid:" + str(r["pmid"])) if r.get("pmid") else \
                        ("t:" + re.sub(r"[^0-9a-z]", "", (r.get("title") or "").lower())[:120])
                    if key in ("t:",):
                        continue
                    m = acc.setdefault(key, dict(r, seeds=[], found_via=[f"snowball:{kind}"]))
                    if s not in m["seeds"]:
                        m["seeds"].append(s)
                    for kk, vv in r.items():
                        if vv and not m.get(kk):
                            m[kk] = vv
                    m["_thin"] = m.get("_thin", True) and r.get("_thin", True)
                if mode == "auto":
                    break
            time.sleep(0.3)
        seen_any = seen_any or got_any
        if not got_any:
            log(f"[snowball] {kind} {s}: no source returned links (not indexed, or all sources unavailable)")
    return list(acc.values()), seen_any


# ---------------------------------------------------------------- repo-cites / page-ids
PMID_RE = re.compile(r"(?:PMID|pubmed(?:\.ncbi\.nlm\.nih\.gov)?)[:/\s]*?(\d{6,9})", re.I)


DOI_TAIL = re.compile(r"(\.full|\.pdf|\.abstract|/full|/abstract|/pdf|\.html?)+$", re.I)


def ids_in_text(txt):
    txt = html.unescape(txt)  # "&gt;" / "&amp;" would otherwise stick to a DOI
    dois = {norm_doi(m.group(1)) for m in DOI_RE.finditer(txt)}
    dois = {DOI_TAIL.sub("", d.rstrip(".,;)}]>'\"")) for d in dois if d}
    axs = {m.group(1) for m in re.finditer(r"arxiv(?:\.org/(?:abs|pdf)/|:\s*)(\d{4}\.\d{4,5})", txt, re.I)}
    pmids = {m.group(1) for m in PMID_RE.finditer(txt)}
    return sorted(dois), sorted(axs), sorted(pmids)


def fetch_text(url, quiet404=False):
    try:
        return http_get(url, retries=1, timeout=30, headers={"User-Agent": "Mozilla/5.0 (research-survey-html snowball)"})
    except NET_ERR as e:
        if not (quiet404 and getattr(e, "code", None) == 404):
            log(f"[snowball] {url}: {e}")
        return ""


def repo_texts(repo):
    repo = re.sub(r"^https?://github\.com/", "", repo).strip("/").removesuffix(".git")
    texts = []
    for name in ("README.md", "README.rst", "README", "README.txt", "CITATION.cff", "inst/CITATION", "CITATION.bib",
                 "CITATION"):
        t = fetch_text(f"https://raw.githubusercontent.com/{repo}/HEAD/{name}", quiet404=True)
        if t and not t.startswith("404"):
            texts.append(t)
    return repo, "\n".join(texts)


def id_records(ids_by_origin, tag):
    """{origin: (dois, arxivs, pmids)} -> thin records (enriched later)."""
    acc = {}
    for origin, (dois, axs, pmids) in ids_by_origin.items():
        for kind, vals in (("doi", dois), ("arxiv", axs), ("pmid", pmids)):
            for v in vals:
                key = f"{kind}:{v}"
                r = acc.setdefault(key, dict(source=tag, title="", doi=v if kind == "doi" else "",
                                             arxiv=v if kind == "arxiv" else "", pmid=v if kind == "pmid" else "",
                                             seeds=[], found_via=[], checked=today()))
                r["seeds"].append(origin)
                fv = f"{tag}:{origin}"
                if fv not in r["found_via"]:
                    r["found_via"].append(fv)
    return list(acc.values())


def enrich_ids(rows):
    """Full metadata for bare IDs: Europe PMC for DOIs/PMIDs, then Crossref for DOIs still missing."""
    rows = epmc_enrich(rows)
    from search_crossref import by_doi as cr_by_doi
    out = []
    for r in rows:
        if not r.get("title") and r.get("doi"):
            try:
                c = cr_by_doi(r["doi"])[0]
                c.update(found_via=r["found_via"], seeds=r["seeds"])
                r = c
            except NET_ERR:
                pass
            time.sleep(0.2)
        if not r.get("title") and r.get("arxiv"):
            r["title"] = f"arXiv:{r['arxiv']} (title not fetched — run search_arxiv.py --ids)"
            r["url"] = f"https://arxiv.org/abs/{r['arxiv']}"
        out.append(r)
    return out


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["refs", "cites", "repo-cites", "page-ids"])
    ap.add_argument("items", nargs="+", help="seed IDs / @file (refs, cites); owner/repo or @repos.json (repo-cites); URLs (page-ids)")
    ap.add_argument("--via", default="auto", help="auto | all | comma list (fallback order) of europepmc,crossref,s2,openalex")
    ap.add_argument("--max", type=int, default=1000, help="max links per seed and source (default 1000)")
    ap.add_argument("--min-seeds", type=int, default=1, help="keep records linked to at least this many seeds")
    ap.add_argument("--no-enrich", action="store_true", help="do not fetch full metadata for bare PMIDs/DOIs")
    ap.add_argument("--log", help="search log TSV (default $SURVEY_QUERY_LOG)")
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    items = read_seeds(a.items)
    if not items:
        raise SystemExit("no seeds / items given")
    ok = True
    if a.cmd in ("refs", "cites"):
        vias = VIA[a.cmd] if a.via in ("auto", "all") else [v.strip() for v in a.via.split(",") if v.strip()]
        bad = [v for v in vias if v not in VIA[a.cmd]]
        if bad:
            raise SystemExit(f"--via {bad} not available for {a.cmd} (choose from {VIA[a.cmd]})")
        rows, ok = snowball(items, a.cmd, vias, "all" if a.via == "all" else "auto", a.max, a.log, a.out)
        if not a.no_enrich:
            rows = epmc_enrich(rows)
    else:
        origins = {}
        tag = "repo-cite" if a.cmd == "repo-cites" else "page"
        for it in items:
            if a.cmd == "repo-cites":
                origin, txt = repo_texts(it)
            else:
                origin, txt = urllib.parse.urlparse(it).netloc or it, fetch_text(it)
            ids = ids_in_text(txt)
            log(f"[snowball] {it}: {len(ids[0])} DOIs, {len(ids[1])} arXiv IDs, {len(ids[2])} PMIDs")
            log_query(a.log, f"snowball-{a.cmd}", it, sum(map(len, ids)), sum(map(len, ids)), a.out, kind="harvest")
            if any(ids):
                prev = origins.get(origin, ([], [], []))
                origins[origin] = tuple(sorted(set(p) | set(q)) for p, q in zip(prev, ids))
        rows = id_records(origins, tag)
        ok = bool(rows)
        if not a.no_enrich:
            rows = enrich_ids(rows)
    for r in rows:
        r.pop("_thin", None)
        r["seed_count"] = len(r.get("seeds") or [])
    rows = [r for r in rows if r["seed_count"] >= a.min_seeds and (r.get("title") or r.get("doi"))]
    rows.sort(key=lambda r: (-r["seed_count"], -(int(r.get("citations") or 0))))
    write_jsonl(a.out, rows)
    log(f"[snowball] {a.cmd}: {len(rows)} unique records from {len(items)} seeds/items"
        + (f" (min-seeds {a.min_seeds})" if a.min_seeds > 1 else ""))
    if not ok:
        log("[snowball] WARNING: nothing could be fetched (sources unavailable or seeds not indexed)")
        sys.exit(2)
