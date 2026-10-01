#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenAlex works search (https://developers.openalex.org/).

Since Feb 2026 OpenAlex expects an API key (free account -> openalex.org/settings/api).
export OPENALEX_API_KEY=...  Free key = $1/day budget (~1,000 searches or ~10,000 list/filter
calls; single-work lookups by DOI/ID are free). Keyless calls share a tiny per-IP budget and
may return 429 "Insufficient budget". Check usage: https://api.openalex.org/rate-limit?api_key=KEY

Polite pool: every call carries mailto=$SURVEY_MAILTO (set it; a warning is printed when it is
missing) and the api_key when $OPENALEX_API_KEY is set.

Never hangs: each call retries at most --retries times with exponential backoff (Retry-After
capped at 60 s), the whole run stops after --timeout seconds (default 300), and a 429
"Insufficient budget" stops at once (the budget refills daily, retrying cannot help).

KEYLESS FALLBACK (--fallback, default crossref): when OpenAlex stops early (no key / budget used
up / persistent 429 or 5xx), the same query is run against Crossref's keyless, all-discipline
`query=` search (polite pool via SURVEY_MAILTO; same --from/--to; `doi` mode falls back to a
Crossref DOI lookup). Fallback records keep Crossref's fields plus `fallback_for: "openalex"`
(no institutions/countries/abstracts — fill those from other sources); the search log gets a
separate `crossref-fallback` line. Records fetched from OpenAlex before it stopped are kept.
Exit code: 0 when OpenAlex or the fallback returned records, 2 when nothing could be fetched.
--fallback none restores the old behaviour (stop, write what was fetched, exit 2).

No date filter is applied unless --from/--to are given; pass them only when the user
explicitly asked for a time range.

Examples
  python search_openalex.py search "autonomous scientific discovery" --max 200
  python search_openalex.py search "autonomous scientific discovery" --from 2024-01-01 --to 2026-10-01   # user-specified range
  python search_openalex.py search "self-driving laboratory" --filter type:article,is_oa:true
  python search_openalex.py doi 10.1038/s41586-025-09640-5
  python search_openalex.py search "fine-mapping GWAS" --fallback none    # no Crossref fallback
"""
import argparse
import os
import sys
import time
import urllib.error

from common import get_json, log, log_lookup, log_query, norm_doi, write_jsonl, today

BASE = "https://api.openalex.org"
OPT = {"retries": 3, "timeout": 300.0}
STATE = {"t0": time.time(), "degraded": "", "total": None}


def _get(url, params):
    """get_json with bounded retries and an overall deadline; None (+ STATE['degraded']) on failure."""
    left = OPT["timeout"] - (time.time() - STATE["t0"])
    if left <= 0:
        STATE["degraded"] = f"--timeout {OPT['timeout']:.0f}s reached"
        return None
    try:
        return get_json(url, params=params, backoff=5, retries=OPT["retries"], max_wait=60, deadline=left, timeout=min(40, max(5, left)))
    except urllib.error.HTTPError as e:
        body = getattr(e, "body_text", "")[:200]
        STATE["degraded"] = f"HTTP {e.code} {body.strip()}"
        if e.code == 429 and "budget" in body.lower():
            STATE["degraded"] += " -> daily budget exhausted; set OPENALEX_API_KEY or wait until tomorrow"
        if e.code in (429, 500, 502, 503, 504):
            return None
        raise
    except (urllib.error.URLError, TimeoutError) as e:
        STATE["degraded"] = f"network error: {e}"
        return None


_warned = []


def _p(extra):
    p = dict(extra)
    if os.environ.get("OPENALEX_API_KEY"):
        p["api_key"] = os.environ["OPENALEX_API_KEY"]
    if os.environ.get("SURVEY_MAILTO"):
        p["mailto"] = os.environ["SURVEY_MAILTO"]  # polite pool
    elif not _warned:
        _warned.append(1)
        log("[openalex] tip: export SURVEY_MAILTO=you@example.org (polite pool; also used by the Crossref fallback)")
    if not os.environ.get("OPENALEX_API_KEY") and len(_warned) < 2:
        _warned.append(2)
        log("[openalex] no OPENALEX_API_KEY: keyless calls share a tiny per-IP daily budget; "
            "the Crossref fallback takes over if it is used up")
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
        d = _get(BASE + "/works", _p(params))
        if d is None:
            break
        STATE["total"] = (d.get("meta") or {}).get("count")
        rows += [norm(w) for w in d.get("results", [])]
        cursor = (d.get("meta") or {}).get("next_cursor")
        log(f"[openalex] {len(rows)}/{(d.get('meta') or {}).get('count')}")
        if not d.get("results"):
            break
    return rows[:max_n]


def by_doi(doi):
    d = _get(f"{BASE}/works/doi:{doi}", _p({}))
    return [norm(d)] if d else []


# ---------------------------------------------------------------- keyless fallback (Crossref)
def crossref_search(q, d_from=None, d_to=None, max_n=100):
    """Crossref keyword search (keyless, all disciplines, polite pool via SURVEY_MAILTO)."""
    from search_crossref import BASE as CR, _p as cr_p, norm as cr_norm
    filt = [f"from-pub-date:{d_from}"] if d_from else []
    if d_to:
        filt.append(f"until-pub-date:{d_to}")
    rows, cursor, total = [], "*", None
    while cursor and len(rows) < max_n:
        # NB: with cursor paging Crossref drops relevance order unless sort=relevance is explicit
        params = {"query": q, "rows": min(100, max_n - len(rows)), "cursor": cursor, "sort": "relevance", "order": "desc"}
        if filt:
            params["filter"] = ",".join(filt)
        try:
            d = get_json(CR + "/works", params=cr_p(params), backoff=5, retries=3, max_wait=60)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            log(f"[crossref-fallback] stopped: {e}")
            break
        msg = d.get("message") or {}
        total = msg.get("total-results", total)
        items = msg.get("items") or []
        rows += [dict(cr_norm(m), fallback_for="openalex") for m in items]
        log(f"[crossref-fallback] {len(rows)}/{total}")
        cursor = msg.get("next-cursor") if items else None
    return rows[:max_n], total


def crossref_doi(doi):
    from search_crossref import by_doi as cr_by_doi
    try:
        return [dict(r, fallback_for="openalex") for r in cr_by_doi(doi)]
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        log(f"[crossref-fallback] {doi}: {e}")
        return []


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["search", "doi"])
    ap.add_argument("query")
    ap.add_argument("--from", dest="d_from", help="YYYY-MM-DD; optional; no date filter unless given (pass only when the user asked for a time range)")
    ap.add_argument("--to", dest="d_to", help="YYYY-MM-DD; optional; no date filter unless given (pass only when the user asked for a time range)")
    ap.add_argument("--filter", help="extra OpenAlex filter, e.g. type:article,is_oa:true (not applied to the fallback)")
    ap.add_argument("--max", type=int, default=100)
    ap.add_argument("--retries", type=int, default=3, help="retries per call on 429/5xx (default 3)")
    ap.add_argument("--timeout", type=float, default=300, help="overall time limit in seconds (default 300)")
    ap.add_argument("--fallback", choices=["crossref", "none"], default="crossref",
                    help="what to do when OpenAlex stops early (no key / budget used up / 429): default crossref")
    ap.add_argument("--log", help="append query + hit count to this TSV (default $SURVEY_QUERY_LOG)")
    ap.add_argument("--lookup-log", help="doi mode: lookup log TSV (default $SURVEY_LOOKUP_LOG or verify_lookups.tsv)")
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    OPT.update(retries=a.retries, timeout=a.timeout)
    date = f"{a.d_from or ''}..{a.d_to or ''}" if a.d_from or a.d_to else ""
    res = search(a.query, a.d_from, a.d_to, a.filter, a.max) if a.cmd == "search" else by_doi(a.query)
    if a.cmd == "search":
        log_query(a.log, "openalex", a.query, STATE["total"], len(res), a.out, filter=a.filter,
                  date=date, degraded="yes" if STATE["degraded"] else "")
    fb = []
    if STATE["degraded"]:
        log(f"[openalex] WARNING: stopped early ({STATE['degraded']}); kept {len(res)} OpenAlex records.")
        if a.fallback == "crossref":
            if a.cmd == "search":
                log("[openalex] falling back to Crossref keyword search (keyless) for the same query…")
                fb, total = crossref_search(a.query, a.d_from, a.d_to, max(0, a.max - len(res)))
                log_query(a.log, "crossref-fallback", a.query, total, len(fb), a.out, fallback_for="openalex", date=date)
            else:
                log("[openalex] falling back to a Crossref DOI lookup…")
                fb = crossref_doi(norm_doi(a.query) or a.query)
        seen = {r.get("doi") for r in res if r.get("doi")}
        res += [r for r in fb if not r.get("doi") or r["doi"] not in seen]
    if a.cmd == "doi":
        log_lookup(a.lookup_log, "openalex-doi" + ("+crossref" if fb else ""), norm_doi(a.query) or a.query, len(res), a.out)
    write_jsonl(a.out, res)
    if STATE["degraded"]:
        if fb:
            log(f"[openalex] {len(fb)} records came from the Crossref fallback (fallback_for=openalex): no institutions, "
                "countries or abstracts — complete them from Europe PMC / PubMed / S2, and say so in 'scope & method'.")
        else:
            log("[openalex] Fallbacks: search_europepmc.py / search_pubmed.py / search_crossref.py title; set OPENALEX_API_KEY.")
            if not res:
                sys.exit(2)
