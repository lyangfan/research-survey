#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge candidate files from several sources, de-duplicate, guess publication status.

Dedup key priority: DOI (non-arXiv DOI) > arXiv ID > normalised title. When the same paper
comes from several sources, fields are merged (first non-empty wins, sources are listed).
Status guess (MUST be confirmed by a human before it goes into works.json):
  peer-reviewed  venue is a journal/conference (not arXiv/bioRxiv/medRxiv/SSRN/Research Square)
  preprint       arXiv / bioRxiv / medRxiv / no venue
Outputs
  --out candidates.jsonl    merged records
  --csv screening.csv       one row per paper with empty include/dirs/notes columns for screening
  --works-draft draft.json  works.json skeleton for the records you mark include=1 in the CSV

Examples
  python merge_dedup.py cand_arxiv.jsonl s2.jsonl openalex.jsonl --out candidates.jsonl --csv screening.csv
  python merge_dedup.py candidates.jsonl --screened screening.csv --works-draft works_draft.json
"""
import argparse
import csv
import json
import re

from common import dedup_key, norm_arxiv, norm_doi, read_records, write_jsonl, log, today

PREPRINT_VENUES = re.compile(r"arxiv|biorxiv|medrxiv|ssrn|research square|preprints\.org|chemrxiv|openreview\.net$|^$", re.I)


def guess_status(r):
    v = (r.get("venue") or "").strip()
    jr = r.get("journal_ref") or ""
    if jr:
        return "peer-reviewed?", jr
    if v and not PREPRINT_VENUES.search(v):
        return "peer-reviewed?", v
    if r.get("published"):  # bioRxiv published DOI
        return "peer-reviewed?", "published: " + r["published"]
    return "preprint", v or ("arXiv" if r.get("arxiv") else "")


def merge(files):
    by = {}
    order = []
    for f in files:
        for r in read_records(f):
            if r.get("status") == "not_found" or not r.get("title"):
                continue
            r["doi"] = norm_doi(r.get("doi"))
            r["arxiv"] = norm_arxiv(r.get("arxiv") or "")
            k = dedup_key(r)
            if k not in by:
                by[k] = dict(r, sources=[r.get("source", "?")])
                order.append(k)
                continue
            m = by[k]
            for kk, vv in r.items():
                if vv and not m.get(kk):
                    m[kk] = vv
            if r.get("venue") and PREPRINT_VENUES.search(m.get("venue") or "") and not PREPRINT_VENUES.search(r["venue"]):
                m["venue"] = r["venue"]  # prefer a real venue over "arXiv.org"
            m["sources"] = sorted(set(m["sources"]) | {r.get("source", "?")})
    # second pass: a DOI-keyed record and an arXiv-keyed record of the same title
    seen_t = {}
    out = []
    for k in order:
        r = by[k]
        t = re.sub(r"[^0-9a-z]+", "", (r.get("title") or "").lower())
        if t in seen_t and t:
            m = seen_t[t]
            for kk, vv in r.items():
                if vv and not m.get(kk):
                    m[kk] = vv
            m["sources"] = sorted(set(m["sources"]) | set(r["sources"]))
            continue
        seen_t[t] = r
        out.append(r)
    for r in out:
        r["status_guess"], r["venue_guess"] = guess_status(r)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default="candidates.jsonl")
    ap.add_argument("--csv")
    ap.add_argument("--screened", help="screening CSV with include=1 rows")
    ap.add_argument("--works-draft")
    a = ap.parse_args()
    recs = merge(a.files)
    log(f"merged -> {len(recs)} unique records")
    write_jsonl(a.out, recs)
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["key", "include", "dirs", "title", "date", "venue_guess", "status_guess", "doi", "arxiv", "citations", "sources", "url", "notes"])
            for r in sorted(recs, key=lambda x: str(x.get("date") or ""), reverse=True):
                w.writerow([dedup_key(r), "", "", r.get("title"), r.get("date"), r.get("venue_guess"), r.get("status_guess"),
                            r.get("doi"), r.get("arxiv"), r.get("citations", ""), "|".join(r["sources"]), r.get("url"), ""])
        log(f"screening sheet -> {a.csv} (fill include=1 and dirs=KEY;KEY)")
    if a.works_draft:
        if not a.screened:
            raise SystemExit("--works-draft needs --screened screening.csv")
        keep = {row["key"]: row for row in csv.DictReader(open(a.screened, encoding="utf-8-sig")) if row.get("include", "").strip() == "1"}
        draft = []
        for r in recs:
            row = keep.get(dedup_key(r))
            if not row:
                continue
            peer = r["status_guess"].startswith("peer")
            draft.append(dict(name=r["title"], title=r["title"], dirs=[d for d in row.get("dirs", "").split(";") if d],
                              inst="", country="", date=(r.get("date") or "")[:7], status=r["venue_guess"] if peer else "arXiv 预印本",
                              peer=peer, venue=r.get("venue", ""), authors=r.get("authors", []), doi=r.get("doi", ""),
                              arxiv=r.get("arxiv", ""), url=r.get("url") or (f"https://arxiv.org/abs/{r['arxiv']}" if r.get("arxiv") else ""),
                              contrib="", checked=today(), note="TODO: verify status/venue, fill inst/country/contrib"))
        json.dump(draft, open(a.works_draft, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        log(f"works draft ({len(draft)}) -> {a.works_draft}")
