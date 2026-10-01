#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Europe PMC REST API search (https://europepmc.org/RestfulWebService) — no key needed.

Best keyword entry point for the life sciences: one index covers PubMed/MEDLINE (SRC:MED),
PMC full text, AND preprints (SRC:PPR: bioRxiv, medRxiv, Research Square, Preprints.org …),
with author affiliations, citation counts and full-text search. The bioRxiv API has no
keyword search, so use `SRC:PPR` here to find bioRxiv/medRxiv preprints by topic, then
`search_biorxiv.py doi …` for version / published-version details.

* Cursor paging (cursorMark, 1000 per page); logs hitCount and appends query + hitCount
  + time to the query log (--log FILE or $SURVEY_QUERY_LOG) so every query is reproducible.
* Same JSONL fields as the other search scripts, plus pmid, pmcid, epmc_src (MED/PMC/PPR …),
  affiliation (first author), country_guess (hint only), is_preprint, mesh, cited_by.
* `date` = first public date: electronic publication date, else firstPublicationDate, else the
  print date. firstPublicationDate is sometimes the print issue date when no e-date is known:
  confirm key dates with `search_crossref.py doi …` (date_online = published-online).
* Authors are kept in PubMed form ("Smith AB"); group authors ("GTEx Consortium") stay one name.

Query syntax (https://europepmc.org/searchsyntax): AND/OR/NOT, "phrases", TITLE:, ABSTRACT:,
AUTH:, AFF:, SRC:PPR (preprints), SRC:MED, PUB_TYPE:review, OPEN_ACCESS:y, FIRST_PDATE:[a TO b].
No date filter is applied unless --from/--to are given; pass them only when the user explicitly
asked for a time range.

Examples
  python search_europepmc.py search '(FarmGTEx OR PigGTEx OR CattleGTEx OR ChickenGTEx)' --max 500 --out ep_farm.jsonl
  python search_europepmc.py search 'TITLE:"GTEx" OR ABSTRACT:"GTEx Consortium"' --preprints --out ep_ppr.jsonl
  python search_europepmc.py search '"single-cell eQTL"' --from 2023-01-01 --to 2026-10-01   # user-specified range
  python search_europepmc.py search 'GTEx' --count-only
  python search_europepmc.py doi 10.1126/science.aaz1776
"""
import argparse

from common import clean_title, get_json, log, log_query, norm_doi, today, write_jsonl
from countries import guess_country

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def _first_date(epub, first, printd):
    """Electronic date > firstPublicationDate > print date. Print dates are issue dates
    (often 'YYYY-MM-01'), so they only win when they are a whole month earlier."""
    best = epub or first or printd
    if printd and best and printd[:7] < best[:7]:
        best = printd
    return best


def norm(r):
    src = r.get("source", "")
    ji = r.get("journalInfo") or {}
    aus = (r.get("authorList") or {}).get("author") or []
    authors, affs = [], []
    for a in aus:
        authors.append(a.get("fullName") or a.get("collectiveName") or " ".join(filter(None, [a.get("lastName"), a.get("initials")])))
        for x in ((a.get("authorAffiliationDetailsList") or {}).get("authorAffiliation") or []):
            if x.get("affiliation"):
                affs.append(x["affiliation"])
    first_aff = next((x.get("affiliation") for x in (((aus[0].get("authorAffiliationDetailsList") or {}).get("authorAffiliation") or []) if aus else [])
                      if x.get("affiliation")), "") or r.get("affiliation", "")
    is_pre = src == "PPR" or "Preprint" in ((r.get("pubTypeList") or {}).get("pubType") or [])
    venue = ((ji.get("journal") or {}).get("title") or (r.get("bookOrReportDetails") or {}).get("publisher") or "")
    doi = norm_doi(r.get("doi"))
    epub = r.get("electronicPublicationDate", "")
    first = r.get("firstPublicationDate", "")
    printd = ji.get("printPublicationDate", "")
    if printd and printd.endswith("-00"):
        printd = printd[:7].rstrip("-0") if printd[5:7] == "00" else printd[:7]
    return dict(
        source="europepmc", epmc_src=src, epmc_id=r.get("id"), title=clean_title(r.get("title")),
        authors=[a for a in authors if a], date=_first_date(epub, first, printd), date_first=first,
        date_epub=epub, date_print=printd, venue=venue or ("preprint" if is_pre else ""),
        volume=ji.get("volume", ""), issue=ji.get("issue", ""), pages=r.get("pageInfo", ""),
        doi=doi, pmid=r.get("pmid", ""), pmcid=r.get("pmcid", ""),
        url=("https://doi.org/" + doi) if doi else f"https://europepmc.org/article/{src}/{r.get('id')}",
        abstract=clean_title(r.get("abstractText") or ""), citations=r.get("citedByCount"),
        types=(r.get("pubTypeList") or {}).get("pubType") or [], is_preprint=is_pre,
        status="preprint" if is_pre else "",
        mesh=[m.get("descriptorName") for m in ((r.get("meshHeadingList") or {}).get("meshHeading") or []) if m.get("descriptorName")],
        affiliation=first_aff, affiliations=sorted(set(affs))[:30], country_guess=guess_country(first_aff),
        checked=today())


def search(query, d_from=None, d_to=None, preprints=False, max_n=100, sort=None, count_only=False):
    q = query
    if preprints:
        q = f"({q}) AND SRC:PPR"
    if d_from or d_to:
        q = f"({q}) AND FIRST_PDATE:[{d_from or '1800-01-01'} TO {d_to or '3000-12-31'}]"
    rows, cursor, hits = [], "*", None
    while True:
        params = {"query": q, "format": "json", "resultType": "core", "cursorMark": cursor,
                  "pageSize": 1 if count_only else min(1000, max(1, max_n - len(rows)))}
        if sort:
            params["sort"] = sort
        d = get_json(BASE + "/search", params=params, backoff=5, retries=4, max_wait=60)
        if hits is None:
            hits = int(d.get("hitCount") or 0)
            log(f"[europepmc] hitCount = {hits}  query: {q}")
            if count_only:
                break
        res = (d.get("resultList") or {}).get("result") or []
        rows += [norm(r) for r in res]
        log(f"[europepmc] {len(rows)}/{hits}")
        nxt = d.get("nextCursorMark")
        if not res or not nxt or nxt == cursor or len(rows) >= max_n:
            break
        cursor = nxt
    return rows[:max_n], hits or 0, q


def by_doi(doi):
    rows, hits, q = search(f'DOI:"{norm_doi(doi)}"', max_n=5)
    return rows, hits, q


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["search", "doi"])
    ap.add_argument("query")
    ap.add_argument("--preprints", action="store_true", help="restrict to preprints (adds AND SRC:PPR)")
    ap.add_argument("--from", dest="d_from", help="YYYY-MM-DD; optional; no date filter unless given (pass only when the user asked for a time range)")
    ap.add_argument("--to", dest="d_to", help="YYYY-MM-DD; optional; no date filter unless given (pass only when the user asked for a time range)")
    ap.add_argument("--sort", help='e.g. "CITED desc" or "FIRST_PDATE_D desc" (default: relevance)')
    ap.add_argument("--max", type=int, default=100)
    ap.add_argument("--count-only", action="store_true", help="only print hitCount")
    ap.add_argument("--log", help="append query + hitCount to this TSV (default $SURVEY_QUERY_LOG)")
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    if a.cmd == "search":
        rows, hits, q = search(a.query, a.d_from, a.d_to, a.preprints, a.max, a.sort, a.count_only)
    else:
        rows, hits, q = by_doi(a.query)
    log_query(a.log, "europepmc", q, hits, len(rows), "" if a.count_only else a.out, sort=a.sort)
    if a.count_only:
        print(hits)
    else:
        write_jsonl(a.out, rows)
