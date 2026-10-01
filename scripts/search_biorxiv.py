#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bioRxiv / medRxiv API helper (https://api.biorxiv.org).

The API has NO keyword search: it returns all preprints in a date window (100 per page,
cursor pagination), optionally filtered by subject category. This script pages through the
window and keeps records whose title/abstract match your keywords locally.
It can also look up whether a preprint was later published (pubs endpoint -> published_doi).

The date window is how this API pages, not a time restriction: without --from/--to the window
is the WHOLE archive (server launch -> today), i.e. no time filter. Pass --from/--to only when
the user explicitly asked for a time range; narrow a full-archive scan with --category instead.

Endpoints used
  /details/{server}/{from}/{to}/{cursor}[?category=bioinformatics]
  /details/{server}/{doi}                     single preprint (all versions)
  /pubs/{server}/{doi}                        published-article link for one preprint

Examples
  # no time restriction: scan the whole archive of one category
  python search_biorxiv.py window --server biorxiv --category bioinformatics \
      --kw "large language model" --kw agent --max-pages 1000 --out brx.jsonl
  # user-specified time range
  python search_biorxiv.py window --server biorxiv --from 2025-01-01 --to 2025-03-31 \
      --category bioinformatics --kw "large language model" --kw agent --out brx.jsonl
  python search_biorxiv.py doi 10.1101/2024.12.31.630767
"""
import argparse
import datetime as dt
import json
import re
import time

from common import get_json, log, write_jsonl, today

BASE = "https://api.biorxiv.org"
# first posting dates; used as the window start when no --from is given (= no time filter)
ARCHIVE_START = {"biorxiv": "2013-11-01", "medrxiv": "2019-06-01"}


def norm(c, server):
    doi = c.get("doi", "")
    return dict(
        source=server, title=c.get("title"), authors=[a.strip() for a in (c.get("authors") or "").split(";") if a.strip()],
        corresponding_institution=c.get("author_corresponding_institution", ""), date=c.get("date"),
        version=c.get("version"), category=c.get("category"), doi=doi,
        url=f"https://www.{server}.org/content/{doi}v{c.get('version', '1')}",
        published=(c.get("published") if c.get("published") not in (None, "NA") else ""),
        abstract=c.get("abstract", ""), status="preprint", checked=today())


def window(server, d_from=None, d_to=None, category=None, kws=(), mode="all", max_pages=200):
    d_from = d_from or ARCHIVE_START[server]
    d_to = d_to or dt.date.today().isoformat()
    log(f"[{server}] window {d_from} .. {d_to}" + (f" category={category}" if category else ""))
    rows, cursor, pages, total = [], 0, 0, 0
    pats = [re.compile(re.escape(k), re.I) for k in kws]
    while pages < max_pages:
        url = f"{BASE}/details/{server}/{d_from}/{d_to}/{cursor}"
        d = get_json(url, params={"category": category} if category else None, backoff=5)
        coll = d.get("collection", [])
        msg = (d.get("messages") or [{}])[0]
        for c in coll:
            text = (c.get("title", "") + " " + c.get("abstract", ""))
            hits = [bool(p.search(text)) for p in pats]
            if not pats or (all(hits) if mode == "all" else any(hits)):
                rows.append(norm(c, server))
        total = int(msg.get("total", 0) or 0)
        cursor += len(coll)
        pages += 1
        log(f"[{server}] scanned {cursor}/{total}, kept {len(rows)}")
        if not coll or cursor >= total:
            break
        time.sleep(0.5)
    if total and cursor < total:
        log(f"[{server}] WARNING: stopped at --max-pages {max_pages} after {cursor}/{total} records; "
            f"the window was NOT fully scanned (raise --max-pages, add --category, or slice by month)")
    return rows


def by_doi(server, doi):
    d = get_json(f"{BASE}/details/{server}/{doi}")
    rows = [norm(c, server) for c in d.get("collection", [])][-1:]
    p = get_json(f"{BASE}/pubs/{server}/{doi}").get("collection", [])
    if rows and p:
        rows[0]["published"] = p[0].get("published_doi", "")
        rows[0]["published_journal"] = p[0].get("published_journal", "")
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["window", "doi"])
    ap.add_argument("doi", nargs="?")
    ap.add_argument("--server", default="biorxiv", choices=["biorxiv", "medrxiv"])
    ap.add_argument("--from", dest="d_from", help="YYYY-MM-DD; optional, default = archive start (no time filter); "
                    "pass only when the user asked for a time range")
    ap.add_argument("--to", dest="d_to", help="YYYY-MM-DD; optional, default = today")
    ap.add_argument("--category", help="e.g. bioinformatics, neuroscience, synthetic_biology")
    ap.add_argument("--kw", action="append", default=[], help="keyword (repeatable)")
    ap.add_argument("--any", action="store_true", help="keep if ANY keyword matches (default ALL)")
    ap.add_argument("--max-pages", type=int, default=200)
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    if a.cmd == "window":
        res = window(a.server, a.d_from, a.d_to, a.category, a.kw, "any" if a.any else "all", a.max_pages)
    else:
        res = by_doi(a.server, a.doi)
    write_jsonl(a.out, res)
