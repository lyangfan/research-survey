#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bioRxiv / medRxiv API helper (https://api.biorxiv.org).

The API has NO keyword search: it returns all preprints in a date window (100 per page,
cursor pagination), optionally filtered by subject category. This script pages through the
window and keeps records whose title/abstract match your keywords locally.
It can also look up whether a preprint was later published (pubs endpoint -> published_doi).

DATES in `doi` mode: the API returns one record per version. `date` is the FIRST public date
(v1 posting date, as the survey rules require); `date_latest` / `version` describe the newest
version, `versions` lists every version with its date, and `url` points to v1 (`url_latest` to the
newest). `server` is the display name ("bioRxiv" / "medRxiv"). In `window` mode each record is the
version posted inside the window: a record with version > 1 carries `date_note` — run `doi` mode
on it to get the v1 date.

KEYWORD SEARCH: the window mode has to download every record in the window, so a no-time-limit
keyword search means scanning the whole archive (hundreds of thousands of records) — usually
impractical. For topic searches use Europe PMC instead, which indexes bioRxiv/medRxiv:
  python search_europepmc.py search '"your topic"' --preprints --out ep_ppr.jsonl
then use `doi` mode here for version, corresponding institution and published-version details.

DOIs: bioRxiv/medRxiv used 10.1101/YYYY.MM.DD.NNNNNN until Nov 2025 and the openRxiv prefix
10.64898/YYYY.MM.DD.NNNNNN(NN) from 2025-12-01; both work in `doi` mode (a doi.org URL is fine,
and the other server is tried automatically when the DOI is not found on --server).

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
  python search_biorxiv.py doi 10.64898/2026.08.30.748055 10.1101/2025.06.25.661532 --out brx.jsonl

Logging: `window` scans are appended to the search log ($SURVEY_QUERY_LOG / --log); `doi`
lookups go to the separate lookup log ($SURVEY_LOOKUP_LOG, default verify_lookups.tsv next to
the search log) so verification does not pollute the list of searches.
"""
import argparse
import datetime as dt
import json
import re
import time

import sys
import urllib.error

from common import get_json, log, log_lookup, log_query, norm_doi, write_jsonl, today

BASE = "https://api.biorxiv.org"
# first posting dates; used as the window start when no --from is given (= no time filter)
ARCHIVE_START = {"biorxiv": "2013-11-01", "medrxiv": "2019-06-01"}


SERVER_NAME = {"biorxiv": "bioRxiv", "medrxiv": "medRxiv"}


def norm(c, server):
    doi = c.get("doi", "")
    srv = c.get("server") or SERVER_NAME.get(server, server)
    v = str(c.get("version") or "1")
    r = dict(
        source=server, server=srv, title=c.get("title"),
        authors=[a.strip() for a in (c.get("authors") or "").split(";") if a.strip()],
        corresponding_institution=c.get("author_corresponding_institution", ""), date=c.get("date"),
        version=v, category=c.get("category"), type=c.get("type", ""), doi=doi,
        url=f"https://www.{server}.org/content/{doi}v{v}",
        published=(c.get("published") if c.get("published") not in (None, "NA") else ""),
        abstract=c.get("abstract", ""), status="preprint", is_preprint=True, venue=srv, checked=today())
    if v != "1":
        r["date_note"] = f"date of v{v}; run `search_biorxiv.py doi {doi}` for the v1 (first public) date"
    return r


def collapse_versions(coll, server):
    """One record per DOI from a list of version records: v1 date as `date`, newest metadata."""
    vs = sorted(coll, key=lambda c: (int(c.get("version") or 1), c.get("date") or ""))
    first, last = vs[0], vs[-1]
    r = norm(last, server)
    r.pop("date_note", None)
    r.update(date=first.get("date"), date_v1=first.get("date"), date_latest=last.get("date"),
             version=str(last.get("version") or "1"),
             versions=[{"version": str(c.get("version")), "date": c.get("date")} for c in vs],
             url=f"https://www.{server}.org/content/{r['doi']}v{first.get('version') or 1}",
             url_latest=f"https://www.{server}.org/content/{r['doi']}v{last.get('version') or 1}")
    if not r["published"]:  # older versions sometimes carry the published DOI when the newest does not
        r["published"] = next((c["published"] for c in reversed(vs) if c.get("published") not in (None, "", "NA")), "")
    return r


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
    doi = norm_doi(doi) or doi
    rec = None
    for srv in [server] + [s for s in ARCHIVE_START if s != server]:
        coll = get_json(f"{BASE}/details/{srv}/{doi}").get("collection", [])
        if coll:
            server, rec = srv, collapse_versions(coll, srv)
            break
    if not rec:
        log(f"[biorxiv] {doi}: not found on bioRxiv or medRxiv")
        return []
    p = get_json(f"{BASE}/pubs/{server}/{doi}").get("collection", [])
    if p:
        rec["published"] = p[0].get("published_doi", "") or rec["published"]
        rec["published_journal"] = p[0].get("published_journal", "")
        rec["published_date"] = p[0].get("published_date", "")
    log(f"[{server}] {doi}: v1 {rec['date_v1']}, latest v{rec['version']} {rec['date_latest']}"
        + (f", published {rec['published']} ({rec.get('published_journal', '')})" if rec["published"] else ""))
    return [rec]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["window", "doi"])
    ap.add_argument("doi", nargs="*", help="doi mode: one or more DOIs (or doi.org URLs)")
    ap.add_argument("--server", default="biorxiv", choices=["biorxiv", "medrxiv"])
    ap.add_argument("--from", dest="d_from", help="YYYY-MM-DD; optional, default = archive start (no time filter); "
                    "pass only when the user asked for a time range")
    ap.add_argument("--to", dest="d_to", help="YYYY-MM-DD; optional, default = today")
    ap.add_argument("--category", help="e.g. bioinformatics, neuroscience, synthetic_biology")
    ap.add_argument("--kw", action="append", default=[], help="keyword (repeatable)")
    ap.add_argument("--any", action="store_true", help="keep if ANY keyword matches (default ALL)")
    ap.add_argument("--max-pages", type=int, default=200)
    ap.add_argument("--log", help="window mode: search log TSV (default $SURVEY_QUERY_LOG)")
    ap.add_argument("--lookup-log", help="doi mode: lookup log TSV (default $SURVEY_LOOKUP_LOG or verify_lookups.tsv)")
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    res, failed = [], ""
    try:
        if a.cmd == "window":
            res = window(a.server, a.d_from, a.d_to, a.category, a.kw, "any" if a.any else "all", a.max_pages)
        else:
            if not a.doi:
                ap.error("doi mode needs at least one DOI")
            for d in a.doi:
                got = by_doi(a.server, d)
                res += got
                log_lookup(a.lookup_log, "biorxiv-doi", norm_doi(d) or d, len(got), a.out)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        failed = f"{type(e).__name__}: {e}"
    write_jsonl(a.out, res)
    if a.cmd == "window":
        q = " AND ".join(a.kw) if not a.any else " OR ".join(a.kw)
        log_query(a.log, "biorxiv-window", q or "(no keywords)", None, len(res), a.out, server=a.server,
                  category=a.category, window=f"{a.d_from or ARCHIVE_START[a.server]}..{a.d_to or ''}",
                  degraded="yes" if failed else "")
    if failed:
        log(f"[biorxiv] WARNING: stopped early ({failed}); kept {len(res)} records. Retry later or use "
            "search_europepmc.py (SRC:PPR) / search_crossref.py doi for the same records.")
        sys.exit(2)
