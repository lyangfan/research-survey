#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PubMed via NCBI E-utilities (https://www.ncbi.nlm.nih.gov/books/NBK25501/).

Rate limit: 3 req/s without key, 10 req/s with NCBI_API_KEY. ESearch (paged with retstart)
-> ESummary (metadata) -> EFetch XML (abstract, first-author affiliation, MeSH terms,
electronic publication date). EFetch is on by default; --no-abstracts skips it.

* Logs the total hit count (esearch `count`) and PubMed's automatic query translation (shows
  the MeSH terms it mapped your words to) to stderr, and appends them to the query log
  (--log FILE or $SURVEY_QUERY_LOG) so the search is reproducible.
* Sort defaults to relevance, so --max keeps the most relevant records rather than only the
  newest (important when no time range was set). Use --sort pub_date for newest first.
* `date` = first public date: the electronic publication date when PubMed has one, else the
  issue date; never a future issue date (`date_print` keeps the issue date for reference).
* Authors are kept in PubMed form ("Smith AB"); group authors ("GTEx Consortium") are kept
  as one name. export_bibtex.py understands both.

No date filter is applied unless --from/--to are given; pass them only when the user
explicitly asked for a time range.

Examples
  python search_pubmed.py '"large language model"[tiab] AND agent[tiab]' --max 200
  python search_pubmed.py '"large language model"[tiab] AND agent[tiab]' --from 2024/01/01 --to 2026/10/01   # user-specified range
  python search_pubmed.py '("GTEx Consortium"[cn] OR GTEx[ti])' --max 1000 --out pm_gtex.jsonl --log search_log.tsv
  python search_pubmed.py 'eQTL[ti] AND (pig[tiab] OR cattle[tiab])' --count-only
"""
import argparse
import datetime as dt
import os
import re
import time
import xml.etree.ElementTree as ET

from common import clean_title, get_json, http_get, log, log_query, today, write_jsonl
from countries import guess_country

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _p(extra, json_mode=True):
    p = dict(extra, tool="research-survey-html")
    if json_mode:
        p["retmode"] = "json"
    if os.environ.get("NCBI_API_KEY"):
        p["api_key"] = os.environ["NCBI_API_KEY"]
    if os.environ.get("SURVEY_MAILTO"):
        p["email"] = os.environ["SURVEY_MAILTO"]
    return p


def _pause():
    time.sleep(0.12 if os.environ.get("NCBI_API_KEY") else 0.4)


def _ymd(s):
    """'2019 Jun 15' / '2019/06/15 00:00' / '2019 Jun' / '2019' -> 'YYYY[-MM[-DD]]' ('' if unparsable)."""
    s = (s or "").strip()
    m = re.match(r"(\d{4})[/-](\d{1,2})(?:[/-](\d{1,2}))?", s)
    if m:
        y, mo, d = m.group(1), int(m.group(2)), m.group(3)
        return f"{y}-{mo:02d}" + (f"-{int(d):02d}" if d else "")
    m = re.match(r"(\d{4})(?:\s+([A-Za-z]{3})[a-z]*(?:\s+(\d{1,2}))?)?", s)
    if not m:
        return ""
    y, mo, d = m.group(1), MON.get((m.group(2) or "").lower()), m.group(3)
    return y + (f"-{mo:02d}" if mo else "") + (f"-{int(d):02d}" if mo and d else "")


def esearch(term, d_from=None, d_to=None, max_n=100, sort="relevance", page=500):
    """Page through ESearch with retstart. Returns (ids, count, querytranslation)."""
    ids, count, qt, start = [], None, "", 0
    while True:
        n = min(page, max_n - len(ids))
        if n <= 0 and count is not None:
            break
        p = {"db": "pubmed", "term": term, "retmax": max(n, 0), "retstart": start, "sort": sort or "relevance"}
        if d_from or d_to:
            p.update(datetype="pdat", mindate=d_from or "1800", maxdate=d_to or "3000")
        r = get_json(BASE + "/esearch.fcgi", params=_p(p))["esearchresult"]
        if count is None:
            count, qt = int(r.get("count", 0)), r.get("querytranslation", "")
            log(f"[pubmed] total hits (count) = {count}")
            if qt:
                log(f"[pubmed] query translation: {qt}")
        got = r.get("idlist", [])
        ids += got
        start += len(got)
        if not got or start >= count or len(ids) >= max_n:
            break
        if start >= 9999:  # ESearch cannot page past 10,000 records
            log("[pubmed] WARNING: ESearch stops at 10,000 records; split the query (e.g. by [dp] year) to get the rest")
            break
        _pause()
    return ids[:max_n], count or 0, qt


def esummary(ids):
    rows = {}
    for i in range(0, len(ids), 200):
        _pause()
        res = get_json(BASE + "/esummary.fcgi", params=_p({"db": "pubmed", "id": ",".join(ids[i:i + 200])}), data=None)["result"]
        for pid in res.get("uids", []):
            r = res[pid]
            aid = {x["idtype"]: x["value"] for x in r.get("articleids", [])}
            authors = [a["name"] for a in r.get("authors", []) if a.get("name")]
            sort_d = (r.get("sortpubdate") or "")[:10].replace("/", "-")
            ep, pp = _ymd(r.get("epubdate")), _ymd(r.get("pubdate"))
            rows[pid] = dict(source="pubmed", pmid=pid, title=clean_title(r.get("title")), authors=authors,
                             date=_first_date(ep, pp, sort_d), date_print=pp, date_epub=ep,
                             venue=r.get("fulljournalname"), venue_abbr=r.get("source"),
                             volume=r.get("volume", ""), issue=r.get("issue", ""), pages=r.get("pages", ""),
                             doi=aid.get("doi", ""), pmcid=aid.get("pmc", ""),
                             types=r.get("pubtype", []), url=f"https://pubmed.ncbi.nlm.nih.gov/{pid}/", checked=today())
    return rows


def _first_date(*cands):
    """Earliest parsable candidate that is not in the future (future issue dates are common)."""
    now = dt.date.today().isoformat()
    ok = sorted(c for c in cands if c and c[:len(c)] <= now[:len(c)])
    if ok:
        # prefer the most specific among those sharing the earliest month
        first = ok[0][:7]
        return max((c for c in ok if c[:7] == first), key=len)
    return next((c for c in cands if c), "")


def efetch(ids):
    """Abstract, affiliations, MeSH, electronic date, collective names from EFetch XML."""
    out = {}
    for i in range(0, len(ids), 200):
        _pause()
        xml = http_get(BASE + "/efetch.fcgi", params=_p({"db": "pubmed", "id": ",".join(ids[i:i + 200]), "retmode": "xml"}, json_mode=False))
        root = ET.fromstring(xml)
        for art in root.iter("PubmedArticle"):
            pid = art.findtext(".//PMID", default="")
            a = art.find(".//Article")
            if a is None:
                continue
            abst = " ".join(
                ((t.get("Label") + ": ") if t.get("Label") else "") + "".join(t.itertext()).strip()
                for t in a.findall("./Abstract/AbstractText"))
            affs = []
            for au in a.findall("./AuthorList/Author"):
                affs.append([x.text or "" for x in au.findall("./AffiliationInfo/Affiliation")])
            first_aff = next((x[0] for x in affs if x), "")
            ed = a.find("./ArticleDate[@DateType='Electronic']")
            epub = ""
            if ed is not None:
                y, m, d = (ed.findtext(k, default="") for k in ("Year", "Month", "Day"))
                epub = "-".join(x.zfill(2) if j else x for j, x in enumerate([y, m, d]) if x)
            mesh = [m.findtext("DescriptorName", default="") for m in art.findall(".//MeshHeadingList/MeshHeading")]
            corp = [c.text for c in a.findall("./AuthorList/Author/CollectiveName") if c.text]
            out[pid] = dict(abstract=abst, affiliation=first_aff, affiliations=sorted({y for x in affs for y in x})[:30],
                            date_epub=epub, mesh=[m for m in mesh if m], corporate_authors=corp)
    return out


def search(term, d_from=None, d_to=None, max_n=100, sort="relevance", abstracts=True, count_only=False):
    ids, count, qt = esearch(term, d_from, d_to, max_n if not count_only else 0, sort)
    if count_only:
        return [], count, qt
    log(f"[pubmed] retrieving {len(ids)} of {count}")
    summ = esummary(ids)
    extra = efetch(ids) if abstracts and ids else {}
    rows = []
    for pid in ids:
        r = summ.get(pid)
        if not r:
            continue
        x = extra.get(pid)
        if x:
            r["abstract"], r["affiliation"], r["mesh"] = x["abstract"], x["affiliation"], x["mesh"]
            r["affiliations"] = x["affiliations"]
            if x["date_epub"]:
                r["date_epub"] = x["date_epub"]
                r["date"] = _first_date(x["date_epub"], r["date"])
            r["country_guess"] = guess_country(x["affiliation"])
            for c in x["corporate_authors"]:
                if c not in r["authors"]:
                    r["authors"].append(c)
        rows.append(r)
    return rows, count, qt


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("term")
    ap.add_argument("--from", dest="d_from", help="YYYY/MM/DD; optional; no date filter unless given (pass only when the user asked for a time range)")
    ap.add_argument("--to", dest="d_to", help="YYYY/MM/DD; optional; no date filter unless given (pass only when the user asked for a time range)")
    ap.add_argument("--max", type=int, default=100, help="max records to retrieve (paged, ESearch limit 10,000)")
    ap.add_argument("--sort", default="relevance", choices=["relevance", "pub_date", "first_author", "journal"],
                    help="default relevance: --max keeps the most relevant, not only the newest")
    ap.add_argument("--no-abstracts", action="store_true", help="skip EFetch (no abstract/affiliation/MeSH)")
    ap.add_argument("--count-only", action="store_true", help="only print the total hit count")
    ap.add_argument("--log", help="append query + hit count to this TSV (default $SURVEY_QUERY_LOG)")
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    rows, count, qt = search(a.term, a.d_from, a.d_to, a.max, a.sort, not a.no_abstracts, a.count_only)
    log_query(a.log, "pubmed", a.term, count, len(rows), a.out if not a.count_only else "",
              sort=a.sort, date=(f"{a.d_from or ''}..{a.d_to or ''}" if a.d_from or a.d_to else ""), translation=qt)
    if a.count_only:
        print(count)
    else:
        write_jsonl(a.out, rows)
