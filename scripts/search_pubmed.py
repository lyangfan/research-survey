#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PubMed via NCBI E-utilities (https://www.ncbi.nlm.nih.gov/books/NBK25501/).

Rate limit: 3 req/s without key, 10 req/s with NCBI_API_KEY. ESearch -> ESummary.

No date filter is applied unless --from/--to are given; pass them only when the user
explicitly asked for a time range.

Examples
  python search_pubmed.py '"large language model"[tiab] AND agent[tiab]' --max 200
  python search_pubmed.py '"large language model"[tiab] AND agent[tiab]' --from 2024/01/01 --to 2026/10/01   # user-specified range
  python search_pubmed.py '("self-driving lab*"[tiab] OR "autonomous laborator*"[tiab])' --out pm.jsonl
"""
import argparse
import os
import time

from common import get_json, log, write_jsonl, today

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _p(extra):
    p = dict(extra, retmode="json", tool="research-survey-html")
    if os.environ.get("NCBI_API_KEY"):
        p["api_key"] = os.environ["NCBI_API_KEY"]
    if os.environ.get("SURVEY_MAILTO"):
        p["email"] = os.environ["SURVEY_MAILTO"]
    return p


def search(term, d_from=None, d_to=None, max_n=100):
    p = {"db": "pubmed", "term": term, "retmax": max_n, "sort": "pub_date"}
    if d_from or d_to:
        p.update(datetype="pdat", mindate=d_from or "1900", maxdate=d_to or "3000")
    ids = get_json(BASE + "/esearch.fcgi", params=_p(p))["esearchresult"]["idlist"]
    log(f"[pubmed] {len(ids)} ids")
    rows = []
    for i in range(0, len(ids), 200):
        time.sleep(0.4)
        res = get_json(BASE + "/esummary.fcgi", params=_p({"db": "pubmed", "id": ",".join(ids[i:i + 200])}))["result"]
        for pid in res.get("uids", []):
            r = res[pid]
            aid = {x["idtype"]: x["value"] for x in r.get("articleids", [])}
            rows.append(dict(source="pubmed", pmid=pid, title=r.get("title"),
                             authors=[a["name"] for a in r.get("authors", [])], date=r.get("sortpubdate", "")[:10].replace("/", "-"),
                             venue=r.get("fulljournalname"), doi=aid.get("doi", ""), pmcid=aid.get("pmc", ""),
                             types=r.get("pubtype", []), url=f"https://pubmed.ncbi.nlm.nih.gov/{pid}/", checked=today()))
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("term")
    ap.add_argument("--from", dest="d_from", help="YYYY/MM/DD; optional; no date filter unless given (pass only when the user asked for a time range)")
    ap.add_argument("--to", dest="d_to", help="YYYY/MM/DD; optional; no date filter unless given (pass only when the user asked for a time range)")
    ap.add_argument("--max", type=int, default=100)
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    write_jsonl(a.out, search(a.term, a.d_from, a.d_to, a.max))
