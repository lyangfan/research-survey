#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch / refresh GitHub stats for repos.json (keeps your hand-written fields).

Primary: GitHub REST API (set GITHUB_TOKEN for 5,000 req/h; anonymous = 60 req/h per IP)
  GET /repos/{owner}/{repo}                 stargazers_count, forks_count, license.spdx_id,
                                            pushed_at, archived, description, default_branch, full_name
  GET /repos/{owner}/{repo}/commits?per_page=1      latest commit on default branch
  GET /repos/{owner}/{repo}/releases/latest         tag_name, published_at (404 = no release)
Fallback when rate-limited (403/429): public HTML page + commits.atom / releases.atom feeds
(this is how the original survey was fetched; parse is best-effort and may break if GitHub
changes its markup — always spot-check a few repos by hand).

Usage
  python github_repos.py data/repos.json                  # update in place
  python github_repos.py repos.txt --out data/repos.json  # owner/name per line -> new file
  python github_repos.py data/repos.json --html-only      # skip the API
"""
import argparse
import html as H
import json
import os
import re
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor

from common import http_get, log, today

API = "https://api.github.com"


class RateLimited(Exception):
    pass


def _api(path):
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    try:
        return json.loads(http_get(API + path, headers=h, retries=0))
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise RateLimited(str(e))
        if e.code == 404:
            return None
        raise


def via_api(repo):
    r = _api(f"/repos/{repo}")
    if r is None:
        return {"status": "404"}
    d = dict(canonical=r["full_name"], stars=r["stargazers_count"], forks=r["forks_count"],
             license=((r.get("license") or {}).get("spdx_id") or None), pushed_at=r.get("pushed_at"),
             archived=r.get("archived", False), description=r.get("description") or "",
             homepage=r.get("homepage") or "", language=r.get("language"), topics=r.get("topics", []),
             created_at=r.get("created_at"))
    if d["license"] == "NOASSERTION":
        d["license"] = "Other（需人工核对 LICENSE 文件）"
    c = _api(f"/repos/{d['canonical']}/commits?per_page=1")
    if c:
        d["last_commit"] = c[0]["commit"]["committer"]["date"]
    rel = _api(f"/repos/{d['canonical']}/releases/latest")
    d["release"] = {"tag": rel.get("tag_name") or rel.get("name"), "date": rel.get("published_at")} if rel else None
    d["fetch_method"] = "api"
    return d


def _get(url):
    try:
        return http_get(url, retries=2, headers={"User-Agent": "Mozilla/5.0"})
    except urllib.error.HTTPError as e:
        return f"__HTTP{e.code}__"


def via_html(repo):
    h = _get(f"https://github.com/{repo}")
    if h.startswith("__HTTP"):
        return {"status": h.strip("_")}
    d = {"fetch_method": "html+atom"}
    m = re.search(r'id="repo-stars-counter-star"[^>]*title="([\d,]+)"', h)
    d["stars"] = int(m.group(1).replace(",", "")) if m else None
    m = re.search(r'id="repo-network-counter"[^>]*title="([\d,]+)"', h)
    d["forks"] = int(m.group(1).replace(",", "")) if m else None
    m = re.search(r'<meta property="og:url" content="https://github.com/([^"]*)"', h)
    d["canonical"] = m.group(1) if m else repo
    m = re.search(r'<meta property="og:description" content="([^"]*)"', h)
    d["description"] = H.unescape(m.group(1)).split(" - ")[0] if m else ""
    lic = re.findall(r'octicon-law[^<]*</svg>\s*([^<\n]+?)\s*<', h)
    d["license"] = lic[0].strip().replace(" license", "") if lic else None
    d["archived"] = "This repository has been archived" in h
    a = _get(f"https://github.com/{d['canonical']}/commits.atom")
    m = re.search(r"<entry>.*?<updated>([^<]+)", a, re.S)
    d["last_commit"] = m.group(1) if m else None
    r = _get(f"https://github.com/{d['canonical']}/releases.atom")
    m = re.search(r"<entry>.*?<updated>([^<]+)</updated>.*?<title>([^<]+)</title>", r, re.S)
    d["release"] = {"tag": H.unescape(m.group(2).strip()), "date": m.group(1)} if m else None
    return d


def fetch(repo, html_only=False, state={"api": True}):
    if not html_only and state["api"]:
        try:
            return via_api(repo)
        except RateLimited:
            if state["api"]:
                log("[github] API rate-limited -> falling back to HTML/Atom scraping (set GITHUB_TOKEN to avoid)")
            state["api"] = False
    time.sleep(0.5)
    return via_html(repo)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="repos.json (list of objects with 'repo') or .txt (owner/name per line)")
    ap.add_argument("--out", help="output path (default: update src in place if .json)")
    ap.add_argument("--html-only", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if a.src.endswith(".json"):
        items = json.load(open(a.src, encoding="utf-8"))
    else:
        items = [{"repo": l.strip()} for l in open(a.src) if l.strip() and not l.startswith("#")]
    workers = 1 if not a.html_only else a.workers
    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(lambda it: fetch(it["repo"], a.html_only), items))
    for it, d in zip(items, res):
        if d.get("status"):
            it["fetch_status"] = d["status"]
            log(f"  {it['repo']}: {d['status']} (moved/deleted? check manually)")
            continue
        it.update({k: v for k, v in d.items() if v is not None or k in ("release",)})
        it["fetched_at"] = today()
        it.pop("fetch_status", None)
        log(f"  {it['repo']}: ⭐{it.get('stars')} forks {it.get('forks')} lic {it.get('license')} last {str(it.get('last_commit') or it.get('pushed_at'))[:10]} rel {(it.get('release') or {}).get('tag')} [{it['fetch_method']}]")
    out = a.out or (a.src if a.src.endswith(".json") else "repos.json")
    json.dump(items, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log(f"wrote {len(items)} repos -> {out}")
