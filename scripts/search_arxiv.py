#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""arXiv API helper (legacy Atom API, https://info.arxiv.org/help/api/).

Rate limit (arXiv ToU): at most 1 request every 3 seconds, single connection.
This script sleeps >=3.1 s between calls and backs off exponentially on 429/503.
If arXiv keeps returning 429, stop and use the fallbacks documented in
references/literature-search.md (Semantic Scholar batch by ARXIV:id, OpenAlex,
or the arxiv.org/abs/<id> page) instead of hammering the API.

No date filter is applied unless --from/--to are given; pass them only when the user
explicitly asked for a time range.

Logging: `--query` searches are appended to the search log ($SURVEY_QUERY_LOG / --log) with
the total hit count; `--ids` / `--titles` verification goes to the separate lookup log
($SURVEY_LOOKUP_LOG, default verify_lookups.tsv next to the search log). If arXiv keeps
failing (429/503 after the retries) the records fetched so far are written and the exit code is 2.

Examples
  # keyword search, newest first, no date filter
  python search_arxiv.py --query 'abs:"scientific discovery" AND abs:agent AND cat:cs.AI' \
      --max 200 --out cand_arxiv.jsonl
  # same, restricted to a user-specified time range
  python search_arxiv.py --query 'abs:"scientific discovery" AND abs:agent AND cat:cs.AI' \
      --from 2024-01-01 --to 2026-10-01 --max 200 --out cand_arxiv.jsonl
  # verify a list of titles (one per line) -> best match each
  python search_arxiv.py --titles titles.txt --out verified.jsonl
  # fetch metadata for known IDs
  python search_arxiv.py --ids 2408.06292,2502.18864
"""
import argparse
import re
import sys
import time
import urllib.error
import xml.etree.ElementTree as ET

from common import http_get, log, log_lookup, log_query, write_jsonl, today

API = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom",
      "os": "http://a9.com/-/spec/opensearch/1.1/"}
_last = [0.0]
TOTAL = [None]


def _call(params):
    wait = 3.1 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    try:
        return http_get(API, params=params, retries=4, backoff=6)
    finally:
        _last[0] = time.time()


def parse(xml):
    root = ET.fromstring(xml)
    total = root.findtext("os:totalResults", default="0", namespaces=NS)
    out = []
    for e in root.findall("a:entry", NS):
        idurl = e.findtext("a:id", default="", namespaces=NS)
        m = re.search(r"abs/([^v]+)(v\d+)?$", idurl)
        if not m:
            continue
        aid = m.group(1)
        doi = e.findtext("arxiv:doi", default="", namespaces=NS)
        out.append(dict(
            source="arxiv",
            title=re.sub(r"\s+", " ", e.findtext("a:title", default="", namespaces=NS)).strip(),
            authors=[a.findtext("a:name", default="", namespaces=NS) for a in e.findall("a:author", NS)],
            date=e.findtext("a:published", default="", namespaces=NS)[:10],
            updated=e.findtext("a:updated", default="", namespaces=NS)[:10],
            arxiv=aid, doi=doi, url=f"https://arxiv.org/abs/{aid}",
            journal_ref=e.findtext("arxiv:journal_ref", default="", namespaces=NS),
            comment=re.sub(r"\s+", " ", e.findtext("arxiv:comment", default="", namespaces=NS)),
            categories=[c.get("term") for c in e.findall("a:category", NS)],
            abstract=re.sub(r"\s+", " ", e.findtext("a:summary", default="", namespaces=NS)).strip(),
            checked=today(),
        ))
    return int(total or 0), out


def search(query, d_from=None, d_to=None, max_results=100, sort="submittedDate", rows=None):
    q = query
    if d_from or d_to:
        f = (d_from or "1991-01-01").replace("-", "") + "0000"
        t = (d_to or "2100-01-01").replace("-", "") + "2359"
        q = f"({q}) AND submittedDate:[{f} TO {t}]"
    rows = [] if rows is None else rows
    start, page = 0, min(100, max_results)
    while start < max_results:
        total, got = parse(_call({"search_query": q, "start": start, "max_results": page,
                                  "sortBy": sort, "sortOrder": "descending"}))
        rows += got
        TOTAL[0] = total
        log(f"[arxiv] {len(rows)}/{min(total, max_results)}")
        if not got or start + page >= total:
            break
        start += page
    return rows[:max_results]


def by_ids(ids, rows=None):
    rows = [] if rows is None else rows
    for i in range(0, len(ids), 50):
        rows += parse(_call({"id_list": ",".join(ids[i:i + 50]), "max_results": 50}))[1]
    return rows


def by_titles(titles, rows=None):
    rows = [] if rows is None else rows
    for t in titles:
        clean = re.sub(r'["():]', " ", t)
        _, got = parse(_call({"search_query": f'ti:"{clean}"', "max_results": 3}))
        if not got:
            log(f"[arxiv] NOT FOUND: {t}")
            rows.append(dict(source="arxiv", query_title=t, status="not_found", checked=today()))
            continue
        best = got[0]
        best["query_title"] = t
        rows.append(best)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--query", help="raw arXiv search_query (ti:, abs:, au:, cat:, AND/OR/ANDNOT)")
    g.add_argument("--ids", help="comma-separated arXiv IDs")
    g.add_argument("--titles", help="file with one title per line to verify")
    ap.add_argument("--from", dest="d_from", help="YYYY-MM-DD; optional; no date filter unless given (pass only when the user asked for a time range)")
    ap.add_argument("--to", dest="d_to", help="YYYY-MM-DD; optional; no date filter unless given (pass only when the user asked for a time range)")
    ap.add_argument("--max", type=int, default=100)
    ap.add_argument("--sort", default="submittedDate", choices=["submittedDate", "lastUpdatedDate", "relevance"])
    ap.add_argument("--log", help="--query: search log TSV (default $SURVEY_QUERY_LOG)")
    ap.add_argument("--lookup-log", help="--ids/--titles: lookup log TSV (default $SURVEY_LOOKUP_LOG or verify_lookups.tsv)")
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    res, failed = [], ""
    try:
        if a.query:
            search(a.query, a.d_from, a.d_to, a.max, a.sort, rows=res)
        elif a.ids:
            by_ids([x.strip() for x in a.ids.split(",") if x.strip()], rows=res)
        else:
            by_titles([l.strip() for l in open(a.titles, encoding="utf-8") if l.strip()], rows=res)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ET.ParseError) as e:
        failed = f"{type(e).__name__}: {e}"
    if a.query:
        res = res[:a.max]
    write_jsonl(a.out, res)
    if a.query:
        log_query(a.log, "arxiv", a.query, TOTAL[0], len(res), a.out, sort=a.sort,
                  date=(f"{a.d_from or ''}..{a.d_to or ''}" if a.d_from or a.d_to else ""), degraded="yes" if failed else "")
    else:
        found = sum(1 for r in res if r.get("status") != "not_found")
        log_lookup(a.lookup_log, "arxiv-" + ("ids" if a.ids else "titles"), a.ids or a.titles, found, a.out)
    if failed:
        log(f"[arxiv] WARNING: stopped early ({failed}); kept {len(res)} records. Do not hammer the API: wait, or use "
            "search_s2.py batch (ARXIV:<id>) / search_openalex.py / the arxiv.org/abs page instead.")
        sys.exit(2)
