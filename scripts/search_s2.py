#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Semantic Scholar Graph API helper (https://api.semanticscholar.org/api-docs/graph).

Without a key you share a global anonymous pool and will often see HTTP 429.
Request a free key (https://www.semanticscholar.org/product/api#api-key-form) and
export S2_API_KEY=...; with a key keep to ~1 request/second (this script sleeps 1.1 s).

Sub-commands
  search  relevance search          GET  /graph/v1/paper/search?query=..[&year=2024-2026]
  bulk    boolean bulk search       GET  /graph/v1/paper/search/bulk?query=..&token=..
  batch   metadata for known IDs    POST /graph/v1/paper/batch  {"ids":["ARXIV:2408.06292","DOI:10.1038/.."]}
  refs    backward snowball         GET  /graph/v1/paper/{id}/references
  cites   forward snowball          GET  /graph/v1/paper/{id}/citations

HTTP 429 handling: every call is retried with exponential backoff (honouring Retry-After,
capped by --max-wait); if the API still refuses after --retries attempts the script STOPS
GRACEFULLY: it writes the records fetched so far, prints a warning with fallbacks (OpenAlex,
Europe PMC, Crossref, or set S2_API_KEY) and exits with code 2 instead of a traceback.

No year filter is applied unless --year is given; pass it only when the user explicitly
asked for a time range.

Examples
  python search_s2.py search "autonomous scientific discovery agent" --max 200 --out s2.jsonl
  python search_s2.py search "autonomous scientific discovery agent" --year 2024-2026 --max 200   # user-specified range
  python search_s2.py bulk '"AI scientist" | "research agent"' --out bulk.jsonl
  python search_s2.py batch --ids ARXIV:2408.06292,DOI:10.1038/s41586-025-09640-5 --out verified.jsonl
  python search_s2.py cites ARXIV:2408.06292 --max 500 --out snowball_fwd.jsonl
"""
import argparse
import json
import os
import sys
import time
import urllib.error

from common import get_json, http_get, log, log_query, write_jsonl, today

BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = "title,externalIds,venue,publicationVenue,year,publicationDate,authors,citationCount,publicationTypes,journal,url,abstract"
_last = [0.0]
RETRY = {"retries": 5, "backoff": 5, "max_wait": 90}
DEGRADED = []  # messages about calls that failed after all retries


class Degraded(Exception):
    pass


def _call(fn, url, **kw):
    """get_json/http_get with retry/backoff; raise Degraded (caught by callers) on persistent 429/5xx."""
    try:
        return fn(url, headers=_hdr(), retries=RETRY["retries"], backoff=RETRY["backoff"], max_wait=RETRY["max_wait"], **kw)
    except urllib.error.HTTPError as e:
        if e.code in (429, 500, 502, 503, 504):
            msg = f"HTTP {e.code} after {RETRY['retries']} retries on {url.split('?')[0]}"
            DEGRADED.append(msg)
            raise Degraded(msg)
        raise
    except (urllib.error.URLError, TimeoutError) as e:
        msg = f"network error after retries: {e}"
        DEGRADED.append(msg)
        raise Degraded(msg)


def _hdr():
    k = os.environ.get("S2_API_KEY")
    return {"x-api-key": k} if k else {}


def _throttle():
    w = 1.1 - (time.time() - _last[0])
    if w > 0:
        time.sleep(w)
    _last[0] = time.time()


def norm(p, src="s2"):
    if not p:
        return None
    ex = p.get("externalIds") or {}
    venue = (p.get("publicationVenue") or {}).get("name") or p.get("venue") or ""
    return dict(
        source=src, s2id=p.get("paperId"), title=p.get("title"),
        authors=[a.get("name") for a in (p.get("authors") or [])],
        date=p.get("publicationDate") or (str(p.get("year")) if p.get("year") else ""),
        year=p.get("year"), venue=venue, types=p.get("publicationTypes") or [],
        doi=ex.get("DOI", ""), arxiv=ex.get("ArXiv", ""), pmid=ex.get("PubMed", ""),
        dblp=ex.get("DBLP", ""), citations=p.get("citationCount"),
        url=p.get("url"), abstract=p.get("abstract") or "", checked=today())


TOTAL = [None]


def search(q, year=None, max_n=100):
    rows, off = [], 0
    while off < max_n:
        _throttle()
        params = {"query": q, "fields": FIELDS, "limit": min(100, max_n - off), "offset": off}
        if year:
            params["year"] = year
        try:
            d = _call(get_json, BASE + "/paper/search", params=params)
        except Degraded:
            break
        TOTAL[0] = d.get("total", TOTAL[0])
        rows += [norm(p) for p in d.get("data", [])]
        log(f"[s2] {len(rows)}/{d.get('total')}")
        if "next" not in d:
            break
        off = d["next"]
    return rows


def bulk(q, year=None, max_n=1000):
    rows, token = [], None
    while len(rows) < max_n:
        _throttle()
        params = {"query": q, "fields": FIELDS}
        if year:
            params["year"] = year
        if token:
            params["token"] = token
        try:
            d = _call(get_json, BASE + "/paper/search/bulk", params=params)
        except Degraded:
            break
        TOTAL[0] = d.get("total", TOTAL[0])
        rows += [norm(p) for p in d.get("data", [])]
        log(f"[s2 bulk] {len(rows)}/{d.get('total')}")
        token = d.get("token")
        if not token:
            break
    return rows[:max_n]


def batch(ids):
    rows = []
    for i in range(0, len(ids), 400):
        _throttle()
        chunk = ids[i:i + 400]
        try:
            txt = _call(http_get, BASE + "/paper/batch", params={"fields": FIELDS}, data={"ids": chunk})
        except Degraded:
            break
        for q, p in zip(chunk, json.loads(txt)):
            r = norm(p) or dict(source="s2", status="not_found", checked=today())
            r["query_id"] = q
            rows.append(r)
    return rows


def graph(pid, kind, max_n=1000):
    key = "citedPaper" if kind == "references" else "citingPaper"
    rows, off = [], 0
    while off < max_n:
        _throttle()
        try:
            d = _call(get_json, f"{BASE}/paper/{pid}/{kind}",
                      params={"fields": FIELDS, "limit": min(1000, max_n - off), "offset": off})
        except Degraded:
            break
        rows += [norm(x.get(key), "s2-" + kind) for x in d.get("data", []) if x.get(key)]
        if "next" not in d:
            break
        off = d["next"]
    for r in rows:
        r["seed"] = pid
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["search", "bulk", "batch", "refs", "cites"])
    ap.add_argument("query", nargs="?", help="query text / paper id (ARXIV:..., DOI:..., S2 id)")
    ap.add_argument("--ids", help="comma-separated ids for batch, or @file with one id per line")
    ap.add_argument("--year", help="e.g. 2024-2026 or 2024-; optional; no date filter unless given (pass only when the user asked for a time range)")
    ap.add_argument("--max", type=int, default=100)
    ap.add_argument("--retries", type=int, default=5, help="retries per call on 429/5xx (default 5)")
    ap.add_argument("--max-wait", type=float, default=90, help="max seconds to sleep per retry (default 90)")
    ap.add_argument("--log", help="append query + hit count to this TSV (default $SURVEY_QUERY_LOG)")
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    RETRY.update(retries=a.retries, max_wait=a.max_wait)
    if a.cmd == "search":
        res = search(a.query, a.year, a.max)
    elif a.cmd == "bulk":
        res = bulk(a.query, a.year, a.max)
    elif a.cmd == "batch":
        ids = open(a.ids[1:]).read().split() if a.ids.startswith("@") else a.ids.split(",")
        res = batch([i.strip() for i in ids if i.strip()])
    else:
        res = graph(a.query, "references" if a.cmd == "refs" else "citations", a.max)
    res = [r for r in res if r]
    write_jsonl(a.out, res)
    if a.cmd in ("search", "bulk"):
        log_query(a.log, "s2-" + a.cmd, a.query, TOTAL[0], len(res), a.out, year=a.year, degraded="yes" if DEGRADED else "")
    if DEGRADED:
        log(f"[s2] WARNING: stopped early ({DEGRADED[-1]}); kept {len(res)} records fetched so far.")
        log("[s2] Fallbacks: set S2_API_KEY (free key), retry later, or use search_openalex.py / "
            "search_europepmc.py / search_crossref.py for the same query or IDs.")
        sys.exit(2)
