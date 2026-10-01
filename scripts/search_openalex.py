#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenAlex works search (https://developers.openalex.org/).

Since Feb 2026 OpenAlex expects an API key (free account -> openalex.org/settings/api).
export OPENALEX_API_KEY=...  Free key = $1/day budget (~1,000 searches or ~10,000 list/filter
calls; single-work lookups by DOI/ID are free). Keyless calls share a tiny per-IP budget and
may return 429 "Insufficient budget". Check usage: https://api.openalex.org/rate-limit?api_key=KEY

Examples
  python search_openalex.py search "autonomous scientific discovery" --from 2024-01-01 --to 2026-10-01 --max 200
  python search_openalex.py search "self-driving laboratory" --filter type:article,is_oa:true
  python search_openalex.py doi 10.1038/s41586-025-09640-5
"""
import argparse
import os

from common import get_json, log, write_jsonl, today

BASE = "https://api.openalex.org"


def _p(extra):
    p = dict(extra)
    if os.environ.get("OPENALEX_API_KEY"):
        p["api_key"] = os.environ["OPENALEX_API_KEY"]
    if os.environ.get("SURVEY_MAILTO"):
        p["mailto"] = os.environ["SURVEY_MAILTO"]
    return p


def inv_abstract(inv):
    if not inv:
        return ""
    pos = sorted((i, w) for w, idx in inv.items() for i in idx)
    return " ".join(w for _, w in pos)


def norm(w):
    ids = w.get("ids") or {}
    loc = w.get("primary_location") or {}
    src = (loc.get("source") or {})
    doi = (w.get("doi") or "").replace("https://doi.org/", "")
    arxiv = ""
    for l in w.get("locations") or []:
        u = (l.get("landing_page_url") or "")
        if "arxiv.org/abs/" in u:
            arxiv = u.split("abs/")[-1].split("v")[0]
    return dict(
        source="openalex", openalex=w.get("id"), title=w.get("title"),
        authors=[a.get("author", {}).get("display_name") for a in w.get("authorships") or []],
        institutions=sorted({i.get("display_name") for a in w.get("authorships") or [] for i in a.get("institutions") or [] if i.get("display_name")}),
        countries=sorted({c for a in w.get("authorships") or [] for c in a.get("countries") or []}),
        date=w.get("publication_date"), year=w.get("publication_year"), venue=src.get("display_name") or "",
        venue_type=src.get("type") or "", type=w.get("type"), doi=doi, arxiv=arxiv, pmid=ids.get("pmid", ""),
        citations=w.get("cited_by_count"), url=loc.get("landing_page_url") or (w.get("doi") or ""),
        abstract=inv_abstract(w.get("abstract_inverted_index")), checked=today())


def search(q, d_from=None, d_to=None, extra_filter=None, max_n=100):
    filt = []
    if d_from:
        filt.append(f"from_publication_date:{d_from}")
    if d_to:
        filt.append(f"to_publication_date:{d_to}")
    if extra_filter:
        filt.append(extra_filter)
    rows, cursor = [], "*"
    while cursor and len(rows) < max_n:
        params = {"search": q, "per_page": min(100, max_n - len(rows)), "cursor": cursor}
        if filt:
            params["filter"] = ",".join(filt)
        d = get_json(BASE + "/works", params=_p(params), backoff=5)
        rows += [norm(w) for w in d.get("results", [])]
        cursor = (d.get("meta") or {}).get("next_cursor")
        log(f"[openalex] {len(rows)}/{(d.get('meta') or {}).get('count')}")
        if not d.get("results"):
            break
    return rows[:max_n]


def by_doi(doi):
    return [norm(get_json(f"{BASE}/works/doi:{doi}", params=_p({})))]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["search", "doi"])
    ap.add_argument("query")
    ap.add_argument("--from", dest="d_from")
    ap.add_argument("--to", dest="d_to")
    ap.add_argument("--filter", help="extra OpenAlex filter, e.g. type:article,is_oa:true")
    ap.add_argument("--max", type=int, default=100)
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    res = search(a.query, a.d_from, a.d_to, a.filter, a.max) if a.cmd == "search" else by_doi(a.query)
    write_jsonl(a.out, res)
