#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge candidate files from several sources, de-duplicate, link preprints to their published
versions, guess publication status.

Dedup key priority: DOI (non-arXiv DOI) > arXiv ID > normalised title. When the same paper
comes from several sources, fields are merged (first non-empty wins, sources are listed).

Preprint vs journal ("kind") — decided by real identifiers only:
  * a DOI with a known preprint-server prefix (common.PREPRINT_DOI_PREFIXES: bioRxiv/medRxiv
    10.1101/YYYY.MM.DD.… and 10.64898/…, Research Square, SSRN, Authorea, Qeios, arXiv …) -> preprint
  * any other DOI -> journal/proceedings, even if an index flags it as a preprint or reports the
    venue "bioRxiv" (Semantic Scholar does that for published papers); exception: a DOI with an
    unknown prefix whose own record is flagged preprint AND names a preprint server as venue
  * no DOI: arXiv ID / preprint-server venue / preprint flag -> preprint; a real venue -> journal

Preprint -> published linking (each preprint is merged INTO its journal record; the journal DOI
becomes `doi`/`url`, the preprint's DOI/URL/date go to `preprint_doi`/`preprint_url`/`preprint_date`,
`date` = earliest date = first public date; `link_method` says how the link was found):
  1. published-doi  the preprint names its journal DOI: bioRxiv/medRxiv API `published`
                    (search_biorxiv.py doi), Crossref `is-preprint-of` (search_crossref.py doi),
                    or a DOI in Europe PMC's "Preprint of" reference
  2. has-preprint   the journal record lists the preprint: Crossref `has-preprint`
  3. europepmc      Europe PMC commentCorrectionList: preprint "Preprint of" -> journal PMID,
                    journal "Preprint in" -> PPR id (search_europepmc.py fills both)
  4. fuzzy          identical title + a shared author among the first five, or
                    same first-author surname + title similarity >= --fuzzy (default 0.90) and the
                    journal version not >60 days older than the preprint. 0.75-threshold scores are
                    NOT merged but reported in `possible_published` (CSV column) for a human check.
  5. --link-online  (optional, network) for preprints still unlinked: Crossref /works/{doi}
                    `is-preprint-of`, then the bioRxiv/medRxiv API `published` field. A journal DOI
                    found this way that is not among the candidates turns the preprint into a
                    journal record stub (venue from the API; verify it).
A preprint whose journal DOI is known but whose journal record is absent becomes such a stub too.
Records from different preprint servers (bioRxiv + Research Square) of one paper all merge into
the journal record (`preprint_dois` lists them; `preprint_doi` is the earliest).

Status guess (MUST be confirmed by a human before it goes into works.json):
  peer-reviewed?  journal kind (venue from the record, else "DOI 10.xxxx/…")
  preprint        preprint kind (server name from DOI prefix / venue)

Titles are cleaned (HTML tags removed, trailing period dropped).
Outputs
  --out candidates.jsonl    merged records
  --csv screening.csv       one row per paper with empty include/featured/dirs/found_via/notes columns
  --works-draft draft.json  works.json skeleton for the records you mark include=1 in the CSV
                            (carries `found_via` = retrieval strategies, from the CSV column if
                            filled, else from the records' `found_via` / sources)

found_via (which retrieval strategy surfaced each work; merged as a union across duplicates):
  records that carry it keep it (snowball.py: snowball:refs / snowball:cites / repo-cite:… / page:…;
  recall_check.py verify: must); other records get the label of the first matching
  --found-via GLOB=LABEL (file-name glob, e.g. 'name_*=name' for tool-name queries,
  'meta_*=manual' for hand-added DOI lookups), else "kw:<source>" (keyword search).

Examples
  python merge_dedup.py cand_arxiv.jsonl s2.jsonl openalex.jsonl --out candidates.jsonl --csv screening.csv
  python merge_dedup.py ep_*.jsonl pm_*.jsonl brx.jsonl --link-online --out candidates.jsonl --csv screening.csv
  python merge_dedup.py candidates.jsonl --screened screening.csv --works-draft works_draft.json
  python merge_dedup.py cand_*.jsonl --csv screening.csv --csv-sort citations   # most-cited first
"""
import argparse
import csv
import difflib
import fnmatch
import json
import os
import re
import time
import urllib.error
import urllib.parse

from common import (PREPRINT_SERVER_RE, clean_title, dedup_key, get_json, is_preprint_doi, is_rxiv_doi, norm_arxiv,
                    norm_doi, norm_title, preprint_server, read_records, surname_key, write_jsonl, log, today)

PREPRINT_VENUES = re.compile(PREPRINT_SERVER_RE.pattern + r"|openreview\.net$|^$", re.I)
# fields that describe the preprint itself and must not leak into the journal record when merging
PREPRINT_ONLY = {"is_preprint", "epmc_src", "epmc_id", "status", "venue", "url", "types", "type", "version",
                 "versions", "published", "published_journal", "published_pmid", "published_ref", "published_date",
                 "is_preprint_of", "category", "date_first", "date_epub", "date_print", "date_v1", "date_latest",
                 "date_note", "url_latest", "server", "venue_type", "doi", "pmid", "pmcid", "citations", "date",
                 "title", "journal_ref", "relation", "has_preprint", "preprint_epmc_ids"}


def is_preprint_rec(r):
    """Preprint vs journal from real identifiers (see module docstring)."""
    doi, venue = norm_doi(r.get("doi")), (r.get("venue") or "").strip()
    flagged = bool(r.get("is_preprint")) or r.get("epmc_src") == "PPR"
    if doi:
        if is_preprint_doi(doi):
            return True
        return flagged and bool(venue) and bool(PREPRINT_SERVER_RE.search(venue)) and not r.get("journal_ref")
    if r.get("journal_ref"):
        return False
    if r.get("arxiv") or flagged:
        return True
    return not venue or bool(PREPRINT_VENUES.search(venue))


def guess_status(r):
    v = (r.get("venue") or "").strip()
    jr = r.get("journal_ref") or ""
    doi = r.get("doi") or ""
    if r.get("_pre"):
        return "preprint", preprint_server(doi, v, r.get("url") or "") or (r.get("server") or "") or v or "preprint"
    if jr:
        return "peer-reviewed?", jr
    if v and not PREPRINT_VENUES.search(v):
        return "peer-reviewed?", v
    if r.get("published_journal"):
        return "peer-reviewed?", r["published_journal"]
    return "peer-reviewed?", ("DOI " + doi) if doi else "unknown venue"


def _merge_same(m, r):
    for kk, vv in r.items():
        if vv and not m.get(kk):
            m[kk] = vv
    if r.get("date") and m.get("date") and str(r["date"]) < str(m["date"]):
        m["date"] = r["date"]  # first public date
    if r.get("venue") and PREPRINT_VENUES.search(m.get("venue") or "") and not PREPRINT_VENUES.search(r["venue"]):
        m["venue"] = r["venue"]  # prefer a real venue over "arXiv.org" / S2's "bioRxiv"
    for k in ("is_preprint_of", "has_preprint", "preprint_epmc_ids", "found_via"):
        if r.get(k):
            m[k] = sorted(set(m.get(k) or []) | set(r[k] if isinstance(r[k], list) else [r[k]]))
    m["sources"] = sorted(set(m["sources"]) | set(r.get("sources") or [r.get("source", "?")]))


def absorb(j, p, how):
    """Merge preprint record p into journal record j."""
    pdoi = norm_doi(p.get("doi"))
    pdate = str(p.get("date_v1") or p.get("date") or "")
    pre = dict(doi=pdoi, url=p.get("url") or (("https://doi.org/" + pdoi) if pdoi else ""), date=pdate,
               server=preprint_server(pdoi, p.get("venue") or "", p.get("url") or "") or p.get("server") or "",
               arxiv=p.get("arxiv") or "")
    lst = j.setdefault("_preprints", [])
    lst.append(pre)
    lst.sort(key=lambda x: x["date"] or "9999")
    first = lst[0]
    if first["doi"]:
        j["preprint_doi"] = first["doi"]
    if first["url"]:
        j["preprint_url"] = first["url"]
    if first["date"]:
        j["preprint_date"] = first["date"]
    if first["server"]:
        j["preprint_server"] = first["server"]
    if len([x for x in lst if x["doi"]]) > 1:
        j["preprint_dois"] = [x["doi"] for x in lst if x["doi"]]
    for k, v in p.items():  # fill gaps (authors, abstract, affiliations, arXiv ID …), never the identity fields
        if k not in PREPRINT_ONLY and not k.startswith("_") and v and not j.get(k):
            j[k] = v
    if pdate and (not j.get("date") or pdate < str(j["date"])):
        j["date"] = pdate  # date = first public date (the preprint)
    if p.get("citations"):
        j["preprint_citations"] = (j.get("preprint_citations") or 0) + int(p["citations"] or 0)
    j["link_method"] = ";".join(sorted(set(filter(None, (j.get("link_method") or "").split(";"))) | {how}))
    j["sources"] = sorted(set(j["sources"]) | set(p["sources"]))
    if p.get("found_via"):
        j["found_via"] = sorted(set(j.get("found_via") or []) | set(p["found_via"]))


def to_stub(p, pubdoi, how, journal=""):
    """Preprint whose journal version is known but not among the candidates -> journal record stub."""
    p["preprint_doi"], p["preprint_url"] = norm_doi(p.get("doi")), p.get("url", "")
    p["preprint_date"] = str(p.get("date_v1") or p.get("date") or "")
    p["preprint_server"] = preprint_server(p["preprint_doi"], p.get("venue") or "", p.get("url") or "")
    p["doi"], p["url"] = pubdoi, "https://doi.org/" + pubdoi
    p["venue"] = journal or p.get("published_journal") or ""
    for k in ("is_preprint", "epmc_src", "status", "server"):
        p.pop(k, None)
    p["_pre"] = False
    p["link_method"] = how + " (journal record not in candidates: verify venue/date)"


def published_dois(p):
    out = [norm_doi(p.get("published"))] + [norm_doi(x) for x in (p.get("is_preprint_of") or [])]
    return [d for d in dict.fromkeys(out) if d and not is_preprint_doi(d)]


def online_link(p, cache):
    """Crossref is-preprint-of, then bioRxiv/medRxiv `published`, for one preprint DOI ('' if none)."""
    doi = norm_doi(p.get("doi"))
    if not doi:
        return "", ""
    if doi in cache:
        return cache[doi]
    res = ("", "")
    try:
        from search_crossref import BASE as CR, _p as cr_p
        m = get_json(f"{CR}/works/{urllib.parse.quote(doi)}", params=cr_p({}), retries=2, backoff=3)["message"]
        pub = [norm_doi(x.get("id")) for x in ((m.get("relation") or {}).get("is-preprint-of") or []) if x.get("id-type") == "doi"]
        pub = [d for d in pub if d and not is_preprint_doi(d)]
        if pub:
            res = (pub[0], "crossref-relation")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, KeyError, ValueError):
        pass
    if not res[0] and is_rxiv_doi(doi):
        for srv in ("biorxiv", "medrxiv"):
            try:
                coll = get_json(f"https://api.biorxiv.org/pubs/{srv}/{doi}", retries=2, backoff=3).get("collection") or []
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
                coll = []
            if coll and coll[0].get("published_doi"):
                res = (norm_doi(coll[0]["published_doi"]), "biorxiv-api")
                break
    cache[doi] = res
    time.sleep(0.2)
    return res


def first_surname(r):
    a = [x for x in (r.get("authors") or []) if x]
    return surname_key(a[0]) if a else ""


def author_set(r, n=5):
    return {k for k in (surname_key(x) for x in (r.get("authors") or [])[:n] if x) if k and len(k) > 1} - {"consortium"}


def file_label(f, rules):
    base = os.path.basename(f)
    for pat, label in rules or []:
        if fnmatch.fnmatch(base, pat) or fnmatch.fnmatch(f, pat):
            return label
    return None


def merge(files, fuzzy=0.90, link_online=False, link_max=500, fv_rules=None):
    by, order = {}, []
    for f in files:
        flabel = file_label(f, fv_rules)
        for r in read_records(f):
            if r.get("status") == "not_found" or not r.get("title"):
                continue
            r["doi"] = norm_doi(r.get("doi"))
            r["arxiv"] = norm_arxiv(r.get("arxiv") or "")
            r["title"] = clean_title(r.get("title"))
            if r.get("found_via") and not isinstance(r["found_via"], list):
                r["found_via"] = [x for x in re.split(r"[;|,]\s*", str(r["found_via"])) if x]
            if not r.get("found_via"):
                r["found_via"] = [flabel or "kw:" + str(r.get("source") or "?")]
            r.setdefault("sources", [r.get("source", "?")])
            k = dedup_key(r)
            if k not in by:
                by[k] = dict(r)
                order.append(k)
            else:
                _merge_same(by[k], r)
    recs = [by[k] for k in order]
    for r in recs:
        r["_pre"] = is_preprint_rec(r)

    # --- same normalised title, same kind, no conflicting DOIs (e.g. arXiv record + S2 record)
    seen, tmp = {}, []
    for r in recs:
        t = norm_title(r.get("title"))
        m = seen.get((t, r["_pre"])) if len(t) > 15 else None
        if m and not (m.get("doi") and r.get("doi") and m["doi"] != r["doi"]) and \
                (not first_surname(m) or not first_surname(r) or first_surname(m) == first_surname(r)):
            _merge_same(m, r)
            continue
        seen[(t, r["_pre"])] = r
        tmp.append(r)
    recs = tmp

    jour = [r for r in recs if not r["_pre"]]
    pres = [r for r in recs if r["_pre"]]
    idx_doi = {r["doi"]: r for r in jour if r.get("doi")}
    idx_pmid = {str(r["pmid"]): r for r in jour if r.get("pmid")}
    has_pre = {}
    for j in jour:
        for d in j.get("has_preprint") or []:
            has_pre.setdefault(norm_doi(d), j)
        for e in j.get("preprint_epmc_ids") or []:
            has_pre.setdefault("epmc:" + str(e), j)
    by_author, by_title = {}, {}
    for j in jour:
        by_author.setdefault(first_surname(j), []).append(j)
        by_title.setdefault(norm_title(j.get("title")), []).append(j)

    absorbed, stubs, stats = set(), [], {}
    cache = {}
    n_online = 0

    def link(p, j, how):
        absorb(j, p, how)
        absorbed.add(id(p))
        stats[how] = stats.get(how, 0) + 1

    for p in pres:
        pubs = published_dois(p)
        tgt = next((idx_doi[d] for d in pubs if d in idx_doi), None)
        if tgt:
            link(p, tgt, "published-doi")
            continue
        tgt = has_pre.get(p.get("doi") or "-") or has_pre.get("epmc:" + str(p.get("epmc_id") or "-"))
        if tgt:
            link(p, tgt, "has-preprint" if p.get("doi") in has_pre else "europepmc")
            continue
        if p.get("published_pmid") and str(p["published_pmid"]) in idx_pmid:
            link(p, idx_pmid[str(p["published_pmid"])], "europepmc")
            continue
        # identical title + at least one shared author among the first five (handles a consortium
        # listed first on one version only)
        t = norm_title(p.get("title"))
        same = [j for j in by_title.get(t, []) if len(t) > 25 and author_set(j) & author_set(p)]
        if len(same) == 1:
            link(p, same[0], "fuzzy")
            same[0].setdefault("link_note", []).append(f"same title + shared author with {p.get('doi') or p.get('arxiv')}")
            continue
        # fuzzy: same first author + similar title
        best, score = None, 0.0
        for j in by_author.get(first_surname(p), []) if first_surname(p) else []:
            if p.get("date") and j.get("date") and str(j["date"])[:10] < str(p["date"])[:10]:
                # journal version clearly older than the preprint -> not its published version
                try:
                    import datetime as _dt
                    a = _dt.date.fromisoformat((str(j["date"]) + "-01-01")[:10])
                    b = _dt.date.fromisoformat((str(p["date"]) + "-01-01")[:10])
                    if (b - a).days > 60:
                        continue
                except ValueError:
                    pass
            s = difflib.SequenceMatcher(None, t, norm_title(j.get("title"))).ratio()
            if s > score:
                best, score = j, s
        if best is not None and score >= fuzzy:
            link(p, best, "fuzzy")
            best.setdefault("link_note", []).append(f"fuzzy {score:.2f} with {p.get('doi') or p.get('arxiv') or p.get('title')[:40]}")
            continue
        if best is not None and score >= 0.75:
            p["possible_published"] = f"{best.get('doi') or best.get('title')[:60]} (title sim {score:.2f}, same first author — check)"
        if pubs:
            stubs.append((p, pubs[0], "published-doi"))
            continue
        if link_online and p.get("doi") and n_online < link_max:
            n_online += 1
            d, how = online_link(p, cache)
            if d:
                if d in idx_doi:
                    link(p, idx_doi[d], how)
                else:
                    stubs.append((p, d, how))
    if link_online:
        log(f"[merge] --link-online: queried {n_online} preprint DOIs")
    out = [r for r in recs if id(r) not in absorbed]
    # stubs: several preprints of the same journal paper -> one stub
    stub_by = {}
    for p, d, how in stubs:
        if d in stub_by:
            absorb(stub_by[d], p, how)
            out.remove(p)
            continue
        to_stub(p, d, how)
        stub_by[d] = p
        stats["stub:" + how] = stats.get("stub:" + how, 0) + 1
    for r in out:
        r.pop("_preprints", None)
        if isinstance(r.get("link_note"), list):
            r["link_note"] = "; ".join(r["link_note"])
        r["status_guess"], r["venue_guess"] = guess_status(r)
        r["is_preprint"] = bool(r.pop("_pre"))
        if not r["is_preprint"]:
            r.pop("status", None) if r.get("status") == "preprint" else None
    log(f"[merge] preprint->published links: {stats or 'none'}")
    return out


def found_via_of(r):
    fv = list(r.get("found_via") or [])
    return fv or sorted({"db:" + s for s in r.get("sources") or []})


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default="candidates.jsonl")
    ap.add_argument("--csv")
    ap.add_argument("--csv-sort", default="date", choices=["date", "citations", "title"],
                    help="row order of the screening CSV (default date, newest first)")
    ap.add_argument("--fuzzy", type=float, default=0.90, help="title similarity for a fuzzy preprint->published merge (same first author)")
    ap.add_argument("--link-online", action="store_true",
                    help="query Crossref (is-preprint-of) and the bioRxiv API for preprints still unlinked")
    ap.add_argument("--link-max", type=int, default=500, help="max preprints to look up with --link-online")
    ap.add_argument("--found-via", action="append", default=[], metavar="GLOB=LABEL",
                    help="found_via label for records from files matching GLOB that carry none "
                         "(e.g. 'name_*=name', 'meta_*=manual'); default kw:<source>")
    ap.add_argument("--screened", help="screening CSV with include=1 rows")
    ap.add_argument("--works-draft")
    a = ap.parse_args()
    rules = []
    for x in a.found_via:
        if "=" not in x:
            raise SystemExit(f"--found-via expects GLOB=LABEL, got {x!r}")
        rules.append(tuple(x.split("=", 1)))
    recs = merge(a.files, a.fuzzy, a.link_online, a.link_max, rules)
    log(f"merged -> {len(recs)} unique records")
    write_jsonl(a.out, recs)
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["key", "include", "featured", "dirs", "title", "first_author", "date", "venue_guess", "status_guess",
                        "doi", "preprint_doi", "link_method", "possible_published", "arxiv", "pmid", "citations", "sources",
                        "found_via", "url", "notes"])
            sk = {"date": lambda x: str(x.get("date") or ""), "title": lambda x: (x.get("title") or "").lower(),
                  "citations": lambda x: int(x.get("citations") or 0)}[a.csv_sort]
            for r in sorted(recs, key=sk, reverse=a.csv_sort != "title"):
                w.writerow([dedup_key(r), "", "", "", r.get("title"), (r.get("authors") or [""])[0], r.get("date"),
                            r.get("venue_guess"), r.get("status_guess"), r.get("doi"), r.get("preprint_doi", ""),
                            r.get("link_method", ""), r.get("possible_published", ""), r.get("arxiv"),
                            r.get("pmid", ""), r.get("citations", ""), "|".join(r["sources"]),
                            ";".join(r.get("found_via") or []), r.get("url"), ""])
        log(f"screening sheet -> {a.csv} (fill include=1 and dirs=KEY;KEY; primary direction first)")
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
            srv = "" if peer else (preprint_server(r.get("doi"), r.get("venue") or "", r.get("url") or "") or r.get("venue_guess") or "arXiv")
            fv = [x for x in re.split(r"[;|]\s*", row.get("found_via") or "") if x] or found_via_of(r)
            d = dict(name=r["title"], title=r["title"], dirs=[d for d in re.split(r"[;,]\s*", row.get("dirs", "")) if d],
                     featured=row.get("featured", "").strip() in ("1", "y", "yes", "true"),
                     inst="", country="", date=(r.get("date") or "")[:10],
                     status=r["venue_guess"] if peer else f"{srv} 预印本", peer=peer,
                     venue_type="journal" if peer else "preprint", venue=r.get("venue", "") if peer else srv,
                     authors=[x for x in r.get("authors", []) if x], doi=r.get("doi", ""), arxiv=r.get("arxiv", ""),
                     url=r.get("url") or (f"https://arxiv.org/abs/{r['arxiv']}" if r.get("arxiv") else ""),
                     contrib="", found_via=fv, checked=today(), note="TODO: verify status/venue/date, fill inst/country/contrib")
            for k in ("pmid", "preprint_doi", "preprint_url", "citations", "affiliation", "country_guess"):
                if r.get(k):
                    d[k] = r[k]
            draft.append(d)
        json.dump(draft, open(a.works_draft, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        log(f"works draft ({len(draft)}) -> {a.works_draft}")
