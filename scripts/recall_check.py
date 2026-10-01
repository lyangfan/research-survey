#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Must-include checklist, recall measurement, saturation and coverage — so a survey never relies
on keyword search alone (references/literature-search.md §1b).

  verify      check every entry of the must-include list (written BEFORE searching, from your own
              knowledge of the field) against Crossref / Europe PMC: DOI exists? title matches?
              title-only entries are resolved to a DOI. Writes a verified TSV (+ JSONL records with
              found_via=["must"] that merge_dedup.py can ingest). Lookups go to the lookup log.
  recall      how many must-include works each retrieval strategy found: --pool LABEL=FILES (repeatable,
              globs allowed), per direction and cumulative in the given order (e.g. keyword ->
              +names -> +snowball). Lists the misses. One line per strategy goes to the search log.
  saturation  new records / new relevant records per round (--round LABEL[@DIR;DIR]=FILES in order),
              per direction. A round scoped with @DIRS (e.g. names@PLEIO) only counts for those
              directions; unscoped rounds count for all. A direction is "saturated" when >= 2 rounds
              targeted it, it has >= --min-works (5) relevant works, and the last round added
              < --threshold (default 5%) of its relevant works so far.
              Relevant = include=1 rows of a screening CSV (screen each round first), works.json,
              or a must list.
  coverage    for a finished data folder: per (primary) direction, how many works came from which
              strategy (works[].found_via), and — with --kw-pool — how many keyword search alone found.
              Prints a Markdown table for narrative/scope.html.

Must-include list format (TSV or CSV, header recommended; '#' lines are comments):
  name    doi    title    dir    note
  SuSiE   10.1111/rssb.12388   A simple new approach to variable selection…   FM   landmark
Plain lines (one DOI or one title per line) also work. `dir` = direction key (for per-direction recall).

Matching: DOI (also preprint_doi / published / preprint_dois) > PMID > arXiv ID > normalised title
(exact, then similarity >= --fuzzy, default 0.92).

Examples
  python recall_check.py verify must_include.tsv --out must_verified.tsv --jsonl cand_must.jsonl
  python recall_check.py recall --must must_verified.tsv --pool keyword='search/pm_*.jsonl,search/ep_*.jsonl' \
      --pool names=search/name_*.jsonl --pool snowball=search/sb_*.jsonl --out recall.tsv
  python recall_check.py saturation --round r1-keyword='pm_*.jsonl' --round 'r2-names@PLEIO;MR=name_*.jsonl' \
      --round r3-refs=sb_refs.jsonl --round r4-cites=sb_cites.jsonl --relevant screening.csv
  python recall_check.py coverage my-survey --kw-pool 'search/pm_*.jsonl,search/ep_*.jsonl'
"""
import argparse
import collections
import csv
import difflib
import glob
import json
import os
import re
import time
import urllib.error

from common import (log, log_lookup, log_query, norm_arxiv, norm_doi, norm_title, read_records, write_jsonl)

NET_ERR = (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError)


# ---------------------------------------------------------------- IO
def read_must(path):
    txt = open(path, encoding="utf-8-sig").read()
    lines = [l for l in txt.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    if not lines:
        return []
    first = lines[0]
    dl = "\t" if "\t" in first else ("," if "," in first and re.search(r"\b(doi|title|name)\b", first, re.I) else None)
    out = []
    if dl and re.search(r"\b(doi|title|name)\b", first, re.I):
        for row in csv.DictReader(lines, delimiter=dl):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            out.append(dict(name=row.get("name", ""), doi=norm_doi(row.get("doi")), title=row.get("title", ""),
                            dir=row.get("dir") or row.get("dirs", "").split(";")[0], pmid=row.get("pmid", ""),
                            arxiv=norm_arxiv(row.get("arxiv", "")), note=row.get("note", ""),
                            status=row.get("status", "")))
    else:
        for l in lines:
            l = l.strip()
            d = norm_doi(l)
            out.append(dict(name="", doi=d, title="" if d else l, dir="", pmid="", arxiv="", note="", status=""))
    return out


def expand(spec):
    """'a.jsonl,b*.jsonl' -> existing files (glob)."""
    files = []
    for part in spec.split(","):
        part = part.strip()
        if part:
            hit = sorted(glob.glob(part))
            files += hit if hit else ([part] if os.path.exists(part) else [])
    return files


def labeled(specs):
    out = []
    for s in specs:
        label, _, files = s.partition("=") if "=" in s else (os.path.basename(s), "", s)
        fl = expand(files)
        if not fl:
            log(f"[recall] WARNING: no files match {files!r} for {label}")
        out.append((label, fl))
    return out


def load_pool(files):
    recs = []
    for f in files:
        if f.endswith(".csv"):
            for row in csv.DictReader(open(f, encoding="utf-8-sig")):
                recs.append(dict(title=row.get("title"), doi=row.get("doi"), pmid=row.get("pmid"), arxiv=row.get("arxiv"),
                                 preprint_doi=row.get("preprint_doi"), include=row.get("include"), dirs=row.get("dirs")))
        else:
            data = read_records(f)
            recs += data if isinstance(data, list) else []
    return recs


# ---------------------------------------------------------------- matching
class Index:
    def __init__(self, recs):
        self.ids, self.titles = {}, {}
        for i, r in enumerate(recs):
            for d in [r.get("doi"), r.get("preprint_doi"), r.get("published")] + list(r.get("preprint_dois") or []):
                d = norm_doi(d)
                if d:
                    self.ids.setdefault("doi:" + d, i)
            if r.get("pmid"):
                self.ids.setdefault("pmid:" + str(r["pmid"]).strip(), i)
            ax = norm_arxiv(r.get("arxiv") or "")
            if ax:
                self.ids.setdefault("arxiv:" + ax, i)
            t = norm_title(r.get("title") or r.get("name"))
            if len(t) > 12:
                self.titles.setdefault(t, i)
        self.tlist = list(self.titles.items())

    def find(self, m, fuzzy=0.92):
        for k in (("doi:" + m["doi"]) if m.get("doi") else None, ("pmid:" + m["pmid"]) if m.get("pmid") else None,
                  ("arxiv:" + m["arxiv"]) if m.get("arxiv") else None):
            if k and k in self.ids:
                return self.ids[k], "id"
        t = norm_title(m.get("title"))
        if len(t) <= 12:
            return None, ""
        if t in self.titles:
            return self.titles[t], "title"
        best, score = None, 0.0
        sm = difflib.SequenceMatcher(None, "", t)
        for tt, i in self.tlist:
            if abs(len(tt) - len(t)) > 0.25 * len(t):
                continue
            sm.set_seq1(tt)
            if sm.real_quick_ratio() < fuzzy or sm.quick_ratio() < fuzzy:
                continue
            s = sm.ratio()
            if s > score:
                best, score = i, s
        return (best, f"fuzzy {score:.2f}") if best is not None and score >= fuzzy else (None, "")


# ---------------------------------------------------------------- verify
def cmd_verify(a):
    from search_crossref import by_doi as cr_doi, by_title as cr_title
    from search_europepmc import by_doi as ep_doi
    must = read_must(a.must)
    rows, recs = [], []
    for m in must:
        st, rec, sim = "", None, ""
        try:
            if m["doi"]:
                try:
                    rec = cr_doi(m["doi"])[0]
                except urllib.error.HTTPError as e:
                    if e.code != 404:
                        raise
                    got, _, _ = ep_doi(m["doi"])
                    rec = got[0] if got else None
                if not rec:
                    st = "doi_not_found"
                elif m["title"]:
                    s = difflib.SequenceMatcher(None, norm_title(m["title"]), norm_title(rec.get("title"))).ratio()
                    sim = f"{s:.2f}"
                    st = "ok" if s >= 0.8 else "title_mismatch"
                else:
                    st = "ok"
            elif m["title"]:
                cands = cr_title(m["title"], rows=3)
                best = max(cands, key=lambda c: difflib.SequenceMatcher(None, norm_title(m["title"]), norm_title(c.get("title"))).ratio(), default=None)
                s = difflib.SequenceMatcher(None, norm_title(m["title"]), norm_title(best.get("title"))).ratio() if best else 0
                sim = f"{s:.2f}"
                if best and s >= 0.85:
                    rec, st = best, "resolved_by_title"
                else:
                    st = "not_found"
            else:
                st = "empty"
        except NET_ERR as e:
            st = f"lookup_failed ({type(e).__name__})"
        log_lookup(a.lookup_log, "must-verify", m["doi"] or m["title"][:80], 1 if rec else 0, a.out)
        row = dict(m, status=st, title_sim=sim, doi=(rec or {}).get("doi") or m["doi"],
                   title=m["title"] or (rec or {}).get("title", ""), found_title=(rec or {}).get("title", ""),
                   venue=(rec or {}).get("venue", ""), date=(rec or {}).get("date", ""))
        rows.append(row)
        if rec and st in ("ok", "resolved_by_title"):
            recs.append(dict(rec, found_via=["must"], must_name=m["name"], must_dir=m["dir"]))
        log(f"[verify] {st:<18} {m['name'] or m['doi'] or m['title'][:50]}")
        time.sleep(0.15)
    cols = ["name", "doi", "title", "dir", "status", "title_sim", "found_title", "venue", "date", "note"]
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    if a.jsonl:
        write_jsonl(a.jsonl, recs)
    c = collections.Counter(r["status"].split(" ")[0] for r in rows)
    log(f"[verify] {len(rows)} entries: " + ", ".join(f"{k}={v}" for k, v in c.most_common()) + f" -> {a.out}")
    log("[verify] fix or drop doi_not_found / title_mismatch / not_found entries before measuring recall")


# ---------------------------------------------------------------- recall
def pct(n, d):
    return f"{100.0 * n / d:.0f}%" if d else "—"


def cmd_recall(a):
    must = [m for m in read_must(a.must) if not m.get("status") or m["status"] in ("ok", "resolved_by_title")]
    pools = labeled(a.pool)
    found = {}  # label -> set(idx of must)
    how = collections.defaultdict(dict)
    cum, cum_sets = set(), []
    for label, files in pools:
        idx = Index(load_pool(files))
        hit = set()
        for i, m in enumerate(must):
            j, why = idx.find(m, a.fuzzy)
            if j is not None:
                hit.add(i)
                how[i][label] = why
        found[label] = hit
        cum |= hit
        cum_sets.append((label, set(cum)))
    dirs = sorted({m["dir"] or "—" for m in must})
    n = len(must)
    print(f"\nmust-include recall ({n} verified works; matched by DOI/PMID/arXiv, then title)\n")
    print("| strategy | found | recall | cumulative | " + " | ".join(dirs) + " |")
    print("|---|---|---|---|" + "---|" * len(dirs))
    for (label, files), (_, cs) in zip(pools, cum_sets):
        per = []
        for d in dirs:
            ids = [i for i, m in enumerate(must) if (m["dir"] or "—") == d]
            per.append(f"{sum(1 for i in ids if i in found[label])}/{len(ids)}")
        print(f"| {label} | {len(found[label])} | {pct(len(found[label]), n)} | {len(cs)} ({pct(len(cs), n)}) | " + " | ".join(per) + " |")
        log_query(a.log, "recall-check", label, len(found[label]), n, a.out or "", recall=pct(len(found[label]), n),
                  cumulative=pct(len(cs), n), files=len(files), kind="recall")
    miss = [m for i, m in enumerate(must) if i not in cum]
    if miss:
        print(f"\nmissed by every strategy ({len(miss)}) — search for them by name / snowball from them / add by hand (found_via manual):")
        for m in miss:
            print(f"  [{m['dir'] or '—'}] {m['name'] or m['title'][:70]}  {m['doi']}")
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["name", "doi", "dir"] + [l for l, _ in pools] + ["found_by_any"])
            for i, m in enumerate(must):
                w.writerow([m["name"] or m["title"][:80], m["doi"], m["dir"]] + [how[i].get(l, "") for l, _ in pools] + [int(i in cum)])
        log(f"[recall] per-work table -> {a.out}")


# ---------------------------------------------------------------- saturation
def relevant_set(path):
    """Relevant works with their direction: screening CSV (include=1), works.json, or a must list."""
    out = []
    if path.endswith(".csv"):
        for row in csv.DictReader(open(path, encoding="utf-8-sig")):
            if (row.get("include") or "").strip() == "1":
                out.append(dict(doi=norm_doi(row.get("doi")), pmid=row.get("pmid") or "", arxiv=norm_arxiv(row.get("arxiv") or ""),
                                title=row.get("title") or "", dir=(row.get("dirs") or "—").split(";")[0] or "—"))
    elif path.endswith(".json"):
        for w in json.load(open(path, encoding="utf-8")):
            ds = w.get("dirs") if isinstance(w.get("dirs"), list) else str(w.get("dirs") or "").split(";")
            out.append(dict(doi=norm_doi(w.get("doi")), pmid=str(w.get("pmid") or ""), arxiv=norm_arxiv(w.get("arxiv") or ""),
                            title=w.get("title") or w.get("name") or "", dir=w.get("primary_dir") or (ds[0] if ds else "—")))
            if w.get("preprint_doi"):
                out[-1]["alt"] = norm_doi(w["preprint_doi"])
    else:
        out = [dict(m, dir=m["dir"] or "—") for m in read_must(path)]
    return out


def rkey(r):
    d = norm_doi(r.get("doi"))
    return ("doi:" + d) if d else ("pmid:" + str(r["pmid"])) if r.get("pmid") else ("t:" + norm_title(r.get("title"))[:100])


def cmd_saturation(a):
    rounds = []
    for label, files in labeled(a.round):
        name, _, scope = label.partition("@")
        rounds.append((name, set(x for x in re.split(r"[;,]", scope) if x), files))
    rel = relevant_set(a.relevant) if a.relevant else []
    seen, rel_found = set(), set()
    dirs = sorted({r["dir"] for r in rel})
    print("\n| round | records | new records | " + ("new relevant | cumulative relevant | " if rel else "")
          + " | ".join(dirs) + (" |" if dirs else "|"))
    print("|---|---|---|" + ("---|---|" if rel else "") + "---|" * len(dirs))
    hist = collections.defaultdict(list)  # dir -> [(round, new, cumulative)] for rounds targeting it
    for name, scope, files in rounds:
        recs = load_pool(files)
        keys = {rkey(r) for r in recs}
        new = keys - seen
        seen |= keys
        idx = Index(recs)
        new_rel = set()
        for i, r in enumerate(rel):
            if i in rel_found:
                continue
            j, _ = idx.find(r, a.fuzzy)
            if j is None and r.get("alt"):
                j, _ = idx.find(dict(r, doi=r["alt"]), a.fuzzy)
            if j is not None:
                new_rel.add(i)
        rel_found |= new_rel
        per = []
        for d in dirs:
            tot_d = sum(1 for r in rel if r["dir"] == d)
            nd = sum(1 for i in new_rel if rel[i]["dir"] == d)
            cd = sum(1 for i in rel_found if rel[i]["dir"] == d)
            if scope and d not in scope:
                per.append(f"· +{nd}" if nd else "·")
                continue
            hist[d].append((name, nd, cd))
            flag = " ✓sat" if len(hist[d]) > 1 and cd >= a.min_works and nd / cd < a.threshold else ""
            per.append(f"+{nd} ({cd}/{tot_d}){flag}")
        print(f"| {name}{' @' + ','.join(sorted(scope)) if scope else ''} | {len(keys)} | {len(new)} | "
              + (f"{len(new_rel)} | {len(rel_found)}/{len(rel)} | " if rel else "") + " | ".join(per) + (" |" if per else "|"))
        log_query(a.log, "saturation", name + ("@" + ",".join(sorted(scope)) if scope else ""), len(new), len(keys), "",
                  new_relevant=len(new_rel) if rel else "",
                  cumulative_relevant=f"{len(rel_found)}/{len(rel)}" if rel else "", kind="saturation")
    if rel:
        sat = [d for d in dirs if len(hist[d]) > 1 and hist[d][-1][2] >= a.min_works
               and hist[d][-1][1] / hist[d][-1][2] < a.threshold]
        print(f"\nsaturated (>= 2 rounds targeted the direction, >= {a.min_works} relevant works found, and the last "
              f"round added < {a.threshold:.0%} of them): {', '.join(sat) or 'none'}")
        rest = [d for d in dirs if d not in sat]
        if rest:
            print("NOT saturated — run another targeted round (names / snowball from the newest relevant works), "
                  "label it LABEL@DIR: " + ", ".join(f"{d} ({len(hist[d])} round{'s' if len(hist[d]) != 1 else ''})" for d in rest))


# ---------------------------------------------------------------- coverage
def cmd_coverage(a):
    works = json.load(open(os.path.join(a.data_dir, "works.json"), encoding="utf-8"))
    meta = json.load(open(os.path.join(a.data_dir, "meta.json"), encoding="utf-8"))
    order = [d["key"] for d in meta.get("directions", [])]
    kw_idx = Index(load_pool(expand(a.kw_pool))) if a.kw_pool else None
    rows = collections.OrderedDict((k, collections.Counter()) for k in order)
    fams = collections.Counter()
    no_fv = 0
    for w in works:
        ds = w.get("dirs") if isinstance(w.get("dirs"), list) else str(w.get("dirs") or "").split(";")
        d = w.get("primary_dir") or (ds[0] if ds else "—")
        c = rows.setdefault(d, collections.Counter())
        c["works"] += 1
        fv = w.get("found_via") or []
        fv = fv if isinstance(fv, list) else [x for x in re.split(r"[;|]\s*", str(fv)) if x]
        if not fv:
            no_fv += 1
        for fam in sorted({x.split(":")[0] for x in fv}):
            c[fam] += 1
            fams[fam] += 1
        if kw_idx is not None:
            m = dict(doi=norm_doi(w.get("doi")), pmid=str(w.get("pmid") or ""), arxiv=norm_arxiv(w.get("arxiv") or ""),
                     title=w.get("title") or "")
            j, _ = kw_idx.find(m, a.fuzzy)
            if j is None and w.get("preprint_doi"):
                j, _ = kw_idx.find(dict(m, doi=norm_doi(w["preprint_doi"])), a.fuzzy)
            if j is not None:
                c["in_kw_pool"] += 1
    cols = [f for f, _ in fams.most_common()]
    head = ["direction", "works"] + cols + (["keyword search alone"] if kw_idx else [])
    print("\n| " + " | ".join(head) + " |\n|" + "---|" * len(head))
    tot = collections.Counter()
    for d, c in rows.items():
        if not c["works"]:
            continue
        tot.update(c)
        print("| " + " | ".join([d, str(c["works"])] + [str(c[f]) for f in cols]
                                + ([f"{c['in_kw_pool']} ({pct(c['in_kw_pool'], c['works'])})"] if kw_idx else [])) + " |")
    print("| **all** | " + " | ".join([str(tot["works"])] + [str(tot[f]) for f in cols]
                                      + ([f"{tot['in_kw_pool']} ({pct(tot['in_kw_pool'], tot['works'])})"] if kw_idx else [])) + " |")
    if no_fv:
        print(f"\n{no_fv}/{len(works)} works have no found_via — record the strategy for each work (see data-schema.md).")
    if kw_idx is not None:
        log_query(a.log, "coverage", a.data_dir, tot["in_kw_pool"], tot["works"], "", kind="coverage",
                  keyword_recall=pct(tot["in_kw_pool"], tot["works"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="verify the must-include list against Crossref / Europe PMC")
    v.add_argument("must")
    v.add_argument("--out", default="must_verified.tsv")
    v.add_argument("--jsonl", help="also write verified records (found_via=must) as candidate JSONL")
    v.add_argument("--lookup-log")
    r = sub.add_parser("recall", help="recall of each strategy vs the must-include list")
    r.add_argument("--must", required=True)
    r.add_argument("--pool", action="append", required=True, help="LABEL=FILES (comma list, globs ok); repeat in order")
    r.add_argument("--out", help="per-work TSV")
    s = sub.add_parser("saturation", help="new (relevant) records per round, per direction")
    s.add_argument("--round", action="append", required=True, help="LABEL[@DIR;DIR]=FILES; repeat in order")
    s.add_argument("--relevant", help="screening CSV (include=1), works.json or a must list")
    s.add_argument("--threshold", type=float, default=0.05)
    s.add_argument("--min-works", type=int, default=5, help="a direction with fewer relevant works found is never saturated")
    c = sub.add_parser("coverage", help="per-direction strategy counts for a data folder")
    c.add_argument("data_dir")
    c.add_argument("--kw-pool", help="keyword-search candidate files (comma list, globs ok)")
    for p in (r, s, c):
        p.add_argument("--fuzzy", type=float, default=0.92)
        p.add_argument("--log", help="search log TSV (default $SURVEY_QUERY_LOG)")
    a = ap.parse_args()
    {"verify": cmd_verify, "recall": cmd_recall, "saturation": cmd_saturation, "coverage": cmd_coverage}[a.cmd](a)
