#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export works.json (and optional timeline/extra refs) to BibTeX, RIS and a Zotero identifier list.

Outputs (prefix via --out, default ./references):
  references.bib            @article / @inproceedings / @misc(eprint=arXiv) / @online-style @misc
  references.ris            RIS (JOUR / CPAPER / UNPB / ELEC) with KW tags = direction keys
  zotero_identifiers.txt    one DOI or arXiv ID per line -> Zotero "Add Item by Identifier" (magic wand)

Zotero import
  File -> Import… -> choose references.bib or .ris -> tick "Place imported collections and items
  into new collection". Tags come from `keywords` (BibTeX) / KW (RIS). For the most complete
  metadata paste zotero_identifiers.txt into the magic-wand box instead (Zotero fetches it).

  python export_bibtex.py examples/agent-science-mini --out out/references
"""
import argparse
import json
import os
import re
import unicodedata

from common import norm_arxiv, norm_doi

PREPRINT_RE = re.compile(r"arxiv|预印本|preprint|biorxiv|medrxiv", re.I)


def ascii_slug(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]", "", s)


def kind(w):
    vt = (w.get("venue_type") or "").lower()
    if vt in ("journal", "conference", "preprint", "blog", "product", "repo", "report"):
        return vt
    if w.get("peer"):
        st = (w.get("status") or "") + " " + (w.get("venue") or "")
        return "conference" if re.search(r"ICLR|NeurIPS|ICML|ACL|EMNLP|NAACL|CVPR|ICCV|ECCV|AAAI|IJCAI|KDD|SIGIR|WWW|Conference|Proceedings|研讨会|workshop", st, re.I) else "journal"
    if norm_arxiv(w.get("arxiv") or w.get("url")) or PREPRINT_RE.search(w.get("status") or ""):
        return "preprint"
    return "blog"


def bib_escape(s):
    return str(s or "").replace("\\", "\\textbackslash{}").replace("&", "\\&").replace("%", "\\%").replace("#", "\\#").replace("_", "\\_")


def key_for(w, used):
    au = (w.get("authors") or [""])[0]
    last = ascii_slug(au.split()[-1] if au else "") or ascii_slug((w.get("inst") or "").split("/")[0])[:12] or "anon"
    yr = (w.get("date") or "")[:4]
    first = next((ascii_slug(t) for t in re.split(r"\s+", w.get("title") or w.get("name") or "") if len(ascii_slug(t)) > 3), "work")
    k = f"{last.lower()}{yr}{first.lower()}"
    base, i = k, 1
    while k in used:
        i += 1
        k = f"{base}{chr(96 + i)}"
    used.add(k)
    return k


def to_bib(w, key):
    kd = kind(w)
    title = w.get("title") or w.get("name")
    ax = norm_arxiv(w.get("arxiv") or w.get("url"))
    doi = norm_doi(w.get("doi") or (w.get("url") if "doi.org" in (w.get("url") or "") else ""))
    f = {"title": "{" + bib_escape(title) + "}", "year": (w.get("date") or "")[:4]}
    if w.get("authors"):
        f["author"] = " and ".join(bib_escape(a) for a in w["authors"])
    elif w.get("inst"):
        f["author"] = "{" + bib_escape(w["inst"]) + "}"
    if len(w.get("date") or "") >= 7:
        f["month"] = str(int(w["date"][5:7]))
    venue = w.get("venue") or re.sub(r"（.*?）|\(.*?\)", "", w.get("status") or "").strip()
    if kd == "journal":
        typ = "article"
        f["journal"] = bib_escape(venue)
    elif kd == "conference":
        typ = "inproceedings"
        f["booktitle"] = bib_escape(venue)
    else:
        typ = "misc"
        if kd == "preprint" and ax:
            f.update(eprint=ax, archiveprefix="arXiv")
            f["howpublished"] = f"arXiv preprint arXiv:{ax}"
        elif kd != "preprint":
            f["howpublished"] = "\\url{" + (w.get("url") or "") + "}"
    for k in ("volume", "pages", "number"):
        if w.get(k):
            f[k] = str(w[k])
    if doi:
        f["doi"] = doi
    if w.get("url"):
        f["url"] = w["url"]
    if ax and kd != "preprint":
        f["eprint"], f["archiveprefix"] = ax, "arXiv"
    note = "; ".join(x for x in [w.get("status"), ("checked " + w["checked"]) if w.get("checked") else ""] if x)
    if note:
        f["note"] = bib_escape(note)
    if w.get("dirs"):
        f["keywords"] = ", ".join(w["dirs"] if isinstance(w["dirs"], list) else w["dirs"].split(";"))
    body = ",\n".join(f"  {k} = {{{v}}}" if not v.startswith("{") else f"  {k} = {v}" for k, v in f.items() if v)
    return f"@{typ}{{{key},\n{body}\n}}\n"


def to_ris(w):
    kd = kind(w)
    ty = {"journal": "JOUR", "conference": "CPAPER", "preprint": "UNPB"}.get(kd, "ELEC")
    lines = [f"TY  - {ty}", f"TI  - {w.get('title') or w.get('name')}"]
    for a in w.get("authors") or []:
        lines.append(f"AU  - {a}")
    if not w.get("authors") and w.get("inst"):
        lines.append(f"AU  - {w['inst']}")
    d = w.get("date") or ""
    lines.append(f"PY  - {d[:4]}")
    if len(d) >= 7:
        lines.append(f"DA  - {d.replace('-', '/')}")
    venue = w.get("venue") or ""
    if kd == "journal" and venue:
        lines.append(f"JO  - {venue}")
    elif kd == "conference" and venue:
        lines.append(f"T2  - {venue}")
    elif kd == "preprint":
        lines.append("PB  - " + (venue if venue and venue != "arXiv" else "arXiv"))
    for k, tag in (("volume", "VL"), ("pages", "SP")):
        if w.get(k):
            lines.append(f"{tag}  - {w[k]}")
    doi = norm_doi(w.get("doi"))
    if doi:
        lines.append(f"DO  - {doi}")
    if w.get("url"):
        lines.append(f"UR  - {w['url']}")
    for k in (w.get("dirs") if isinstance(w.get("dirs"), list) else (w.get("dirs") or "").split(";")):
        if k:
            lines.append(f"KW  - {k}")
    note = "; ".join(x for x in [w.get("status"), w.get("contrib"), ("checked " + w["checked"]) if w.get("checked") else ""] if x)
    if note:
        lines.append(f"N1  - {note}")
    lines.append("ER  - ")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_dir", help="folder containing works.json")
    ap.add_argument("--out", default="references", help="output prefix")
    a = ap.parse_args()
    works = json.load(open(os.path.join(a.data_dir, "works.json"), encoding="utf-8"))
    used, bib, ris, ids = set(), [], [], []
    for w in sorted(works, key=lambda x: x.get("date", "")):
        bib.append(to_bib(w, key_for(w, used)))
        ris.append(to_ris(w))
        doi, ax = norm_doi(w.get("doi")), norm_arxiv(w.get("arxiv") or w.get("url"))
        if doi or ax:
            ids.append(doi or f"arXiv:{ax}")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    open(a.out + ".bib", "w", encoding="utf-8").write("\n".join(bib))
    open(a.out + ".ris", "w", encoding="utf-8").write("\n".join(ris))
    open(os.path.join(os.path.dirname(os.path.abspath(a.out)), "zotero_identifiers.txt"), "w").write("\n".join(ids) + "\n")
    print(f"{len(bib)} entries -> {a.out}.bib / {a.out}.ris ; {len(ids)} identifiers -> zotero_identifiers.txt")
