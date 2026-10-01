#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crossref REST API helper (https://api.crossref.org) — DOI verification & venue lookup.

`date` is the first public date (published-online, or `posted` for preprints) rather than the
print issue date; `date_online` / `date_print` are both kept. Use `doi` mode to fix dates of
records whose source only had the issue date (Europe PMC / PubMed often do).

No key needed. Add SURVEY_MAILTO=you@example.org to join the "polite" pool (faster, fewer 429s).

Preprint <-> published: `is_preprint_of` (on a preprint: the journal DOI(s)) and `has_preprint`
(on a journal article: the preprint DOI(s)) come from Crossref's `relation` field; `published`
repeats the first journal DOI for preprints so merge_dedup.py can merge the two versions.
`is_preprint` / `server` are set for posted-content preprints (e.g. bioRxiv, Research Square).

Logging: `title` searches are appended to the search log ($SURVEY_QUERY_LOG / --log); `doi`
lookups go to the separate lookup log ($SURVEY_LOOKUP_LOG, default verify_lookups.tsv next to
the search log), so verification does not pollute the list of searches.

Examples
  python search_crossref.py doi 10.1038/s41586-025-09640-5
  python search_crossref.py doi 10.1101/2025.06.25.661532 10.1038/s41586-025-10014-0 --out cr.jsonl
  python search_crossref.py title "Accelerating scientific discovery with Co-Scientist" --rows 3
  python search_crossref.py title "self-driving laboratory" --rows 50 --out cr.jsonl
  # --from only when the user explicitly asked for a time range (no date filter by default)
  python search_crossref.py title "self-driving laboratory" --from 2024-01-01 --rows 50 --out cr.jsonl
"""
import argparse
import os
import sys
import urllib.error
import urllib.parse

from common import get_json, is_preprint_doi, log, log_lookup, log_query, norm_doi, write_jsonl, today

BASE = "https://api.crossref.org"
TOTAL = [None]


def _p(extra):
    p = dict(extra)
    if os.environ.get("SURVEY_MAILTO"):
        p["mailto"] = os.environ["SURVEY_MAILTO"]
    return p


def _dp(m, k):
    dp = (m.get(k) or {}).get("date-parts")
    if dp and dp[0] and dp[0][0]:
        return "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(dp[0]))
    return ""


def _date(m):
    """First public date = published-online (or posted, for preprints) when Crossref has it;
    the print issue date is often 1-3 months later. Falls back to print / issued / created."""
    for k in ("published-online", "posted", "published-print", "issued", "created"):
        d = _dp(m, k)
        if d:
            return d
    return ""


def _rel(m, key):
    return [norm_doi(x.get("id")) for x in ((m.get("relation") or {}).get(key) or [])
            if x.get("id-type") == "doi" and norm_doi(x.get("id"))]


def norm(m):
    doi = (m.get("DOI") or "").lower()
    pre_of, has_pre = _rel(m, "is-preprint-of"), _rel(m, "has-preprint")
    is_pre = m.get("subtype") == "preprint" or is_preprint_doi(doi)
    inst = [i.get("name") for i in (m.get("institution") or []) if i.get("name")]
    r = dict(
        source="crossref", title=(m.get("title") or [""])[0],
        authors=[(" ".join(filter(None, [a.get("given"), a.get("family")])) or a.get("name", "")) for a in m.get("author") or []],
        date=_date(m), date_online=_dp(m, "published-online") or _dp(m, "posted"), date_print=_dp(m, "published-print"),
        venue=(m.get("container-title") or [""])[0] or (inst[0] if is_pre and inst else ""), type=m.get("type"),
        publisher=m.get("publisher"), doi=doi, url=m.get("URL"),
        volume=m.get("volume", ""), issue=m.get("issue", ""), pages=m.get("page", ""),
        relation=list((m.get("relation") or {}).keys()),  # e.g. is-preprint-of / has-preprint
        is_preprint_of=pre_of, has_preprint=has_pre, is_preprint=bool(is_pre),
        checked=today())
    if is_pre:
        r["server"] = inst[0] if inst else ""
        pub = [d for d in pre_of if not is_preprint_doi(d)]
        if pub:
            r["published"] = pub[0]
    return r


def by_doi(doi):
    return [norm(get_json(f"{BASE}/works/{urllib.parse.quote(doi)}", params=_p({}), backoff=5)["message"])]


def by_title(t, rows=5, d_from=None):
    params = {"query.bibliographic": t, "rows": rows}
    if d_from:
        params["filter"] = f"from-pub-date:{d_from}"
    d = get_json(BASE + "/works", params=_p(params), backoff=5)
    TOTAL[0] = d["message"].get("total-results")
    return [norm(m) for m in d["message"]["items"]]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["doi", "title"])
    ap.add_argument("query", nargs="+", help="doi: one or more DOIs; title: the title / query text (quote it)")
    ap.add_argument("--rows", type=int, default=5)
    ap.add_argument("--from", dest="d_from", help="YYYY-MM-DD; optional; no date filter unless given (pass only when the user asked for a time range)")
    ap.add_argument("--log", help="title mode: search log TSV (default $SURVEY_QUERY_LOG)")
    ap.add_argument("--lookup-log", help="doi mode: lookup log TSV (default $SURVEY_LOOKUP_LOG or verify_lookups.tsv)")
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    res, failed = [], ""
    if a.cmd == "doi":
        for d in a.query:
            try:
                got = by_doi(norm_doi(d) or d)
            except urllib.error.HTTPError as e:
                got = []
                if e.code == 404:
                    log(f"[crossref] {d}: not found (404)")
                else:
                    failed = f"HTTP {e.code} on {d}"
            except (urllib.error.URLError, TimeoutError) as e:
                got, failed = [], f"{type(e).__name__} on {d}: {e}"
            res += got
            log_lookup(a.lookup_log, "crossref-doi", norm_doi(d) or d, len(got), a.out)
            if failed:
                break
    else:
        q = " ".join(a.query)
        try:
            res = by_title(q, a.rows, a.d_from)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            failed = f"{type(e).__name__}: {e}"
        log_query(a.log, "crossref-title", q, TOTAL[0], len(res), a.out, rows=a.rows, date=a.d_from or "",
                  degraded="yes" if failed else "")
    write_jsonl(a.out, res)
    if failed:
        log(f"[crossref] WARNING: stopped early ({failed}); kept {len(res)} records. Set SURVEY_MAILTO, retry later, "
            "or use search_openalex.py doi / search_europepmc.py doi.")
        sys.exit(2)
