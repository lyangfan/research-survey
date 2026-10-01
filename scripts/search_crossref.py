#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crossref REST API helper (https://api.crossref.org) — DOI verification & venue lookup.

`date` is the first public date (published-online, or `posted` for preprints) rather than the
print issue date; `date_online` / `date_print` are both kept. Use `doi` mode to fix dates of
records whose source only had the issue date (Europe PMC / PubMed often do).

No key needed. Add SURVEY_MAILTO=you@example.org to join the "polite" pool (faster, fewer 429s).

Examples
  python search_crossref.py doi 10.1038/s41586-025-09640-5
  python search_crossref.py title "Accelerating scientific discovery with Co-Scientist" --rows 3
  python search_crossref.py title "self-driving laboratory" --rows 50 --out cr.jsonl
  # --from only when the user explicitly asked for a time range (no date filter by default)
  python search_crossref.py title "self-driving laboratory" --from 2024-01-01 --rows 50 --out cr.jsonl
"""
import argparse
import os
import urllib.parse

from common import get_json, write_jsonl, today

BASE = "https://api.crossref.org"


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


def norm(m):
    return dict(
        source="crossref", title=(m.get("title") or [""])[0],
        authors=[(" ".join(filter(None, [a.get("given"), a.get("family")])) or a.get("name", "")) for a in m.get("author") or []],
        date=_date(m), date_online=_dp(m, "published-online") or _dp(m, "posted"), date_print=_dp(m, "published-print"),
        venue=(m.get("container-title") or [""])[0], type=m.get("type"),
        publisher=m.get("publisher"), doi=(m.get("DOI") or "").lower(), url=m.get("URL"),
        volume=m.get("volume", ""), issue=m.get("issue", ""), pages=m.get("page", ""),
        relation=list((m.get("relation") or {}).keys()),  # e.g. is-preprint-of / has-preprint
        checked=today())


def by_doi(doi):
    return [norm(get_json(f"{BASE}/works/{urllib.parse.quote(doi)}", params=_p({}), backoff=5)["message"])]


def by_title(t, rows=5, d_from=None):
    params = {"query.bibliographic": t, "rows": rows}
    if d_from:
        params["filter"] = f"from-pub-date:{d_from}"
    d = get_json(BASE + "/works", params=_p(params), backoff=5)
    return [norm(m) for m in d["message"]["items"]]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["doi", "title"])
    ap.add_argument("query")
    ap.add_argument("--rows", type=int, default=5)
    ap.add_argument("--from", dest="d_from", help="YYYY-MM-DD; optional; no date filter unless given (pass only when the user asked for a time range)")
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    write_jsonl(a.out, by_doi(a.query) if a.cmd == "doi" else by_title(a.query, a.rows, a.d_from))
