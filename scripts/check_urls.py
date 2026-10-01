#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""URL liveness check for a survey data folder (or any list of URLs). Standard library only.

For each URL: HEAD with a timeout (redirects followed); if the server rejects HEAD
(400/403/405/501…) or HEAD fails, retry once with a small GET. Classifies the result as
  ok        2xx/3xx after redirects
  blocked   401/403/429 or a bot wall — page probably exists but refuses scripts (check by hand)
  dead      404/410, other 4xx/5xx, DNS failure, connection refused, timeout
and prints a table; exit code 1 when any URL is dead (use --no-fail to always exit 0).

Sources collected from a data folder: works[].url (+ preprint_url), portals[].url,
timeline[].url, meta.extra_refs[].url, teams[].url, and repos (https://github.com/<repo>).

  python check_urls.py my-survey                         # check everything in the folder
  python check_urls.py my-survey --only portals --write  # store status in portals.json (shown in the HTML)
  python check_urls.py https://gtexportal.org https://www.farmgtex.org
  python check_urls.py urls.txt --out url_report.tsv --timeout 15
"""
import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (compatible; research-survey-html link checker; +https://github.com/lyangfan/research-survey)"
BLOCKED = {401, 403, 429, 999}


def _req(url, method, timeout):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "*/*",
                                                              **({"Range": "bytes=0-2047"} if method == "GET" else {})})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if method == "GET":
            r.read(2048)
        return r.status, r.geturl(), time.time() - t0


def check(url, timeout=12):
    res = dict(url=url, status=None, final_url="", state="dead", error="", ms=None, checked=time.strftime("%Y-%m-%d"))
    if not url or not url.startswith(("http://", "https://")):
        res.update(error="not an http(s) URL")
        return res
    for method in ("HEAD", "GET"):
        try:
            code, final, dt = _req(url, method, timeout)
            res.update(status=code, final_url=final if final != url else "", ms=int(dt * 1000), error="")
            res["state"] = "ok" if code < 400 else ("blocked" if code in BLOCKED else "dead")
            return res
        except urllib.error.HTTPError as e:
            res.update(status=e.code, error=f"HTTP {e.code}")
            if method == "HEAD" and e.code not in (404, 410):
                continue  # many servers reject HEAD; try GET
            res["state"] = "blocked" if e.code in BLOCKED else "dead"
            return res
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
            reason = getattr(e, "reason", e)
            res.update(status=None, error=f"{type(reason).__name__}: {reason}"[:160])
            if method == "HEAD":
                continue
    return res


def collect(data_dir, only=None):
    """(url, where) pairs from a survey data folder."""
    def load(name, default):
        p = os.path.join(data_dir, name)
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default
    out = []
    if only in (None, "works"):
        for w in load("works.json", []):
            out += [(w.get("url"), "works: " + str(w.get("name")))] + ([(w["preprint_url"], "works(preprint): " + str(w.get("name")))] if w.get("preprint_url") else [])
    if only in (None, "portals"):
        for p in load("portals.json", []):
            out.append((p.get("url"), "portals: " + str(p.get("name"))))
    if only in (None, "timeline"):
        out += [(e.get("url"), "timeline: " + str(e.get("title"))) for e in load("timeline.json", [])]
    if only in (None, "teams"):
        out += [(t.get("url"), "teams: " + str(t.get("name"))) for t in load("teams.json", []) if t.get("url")]
    if only in (None, "refs"):
        out += [(x.get("url"), "extra_refs: " + str(x.get("title"))) for x in load("meta.json", {}).get("extra_refs", [])]
    if only in (None, "repos"):
        out += [("https://github.com/" + (r.get("canonical") or r["repo"]), "repos") for r in load("repos.json", []) if r.get("repo")]
    seen, uniq = set(), []
    for u, w in out:
        if u and u not in seen:
            seen.add(u)
            uniq.append((u, w))
    return uniq


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="+", help="data folder, a .txt file with one URL per line, or URLs")
    ap.add_argument("--only", choices=["works", "portals", "timeline", "teams", "refs", "repos"], help="data folder: one source only")
    ap.add_argument("--timeout", type=float, default=12, help="seconds per request (default 12)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", help="write a TSV (or .json) report")
    ap.add_argument("--write", action="store_true", help="store url_status/url_checked in <data_dir>/portals.json")
    ap.add_argument("--no-fail", action="store_true", help="exit 0 even when dead links are found")
    a = ap.parse_args()
    items, data_dir = [], None
    for t in a.targets:
        if os.path.isdir(t):
            data_dir = t
            items += collect(t, a.only)
        elif os.path.isfile(t):
            items += [(l.strip(), os.path.basename(t)) for l in open(t, encoding="utf-8") if l.strip() and not l.startswith("#")]
        else:
            items.append((t, "arg"))
    print(f"checking {len(items)} URLs (timeout {a.timeout:.0f}s, {a.workers} workers)…", file=sys.stderr)
    with ThreadPoolExecutor(max(1, a.workers)) as ex:
        results = list(ex.map(lambda it: dict(check(it[0], a.timeout), where=it[1]), items))
    icon = {"ok": "✓", "blocked": "?", "dead": "✗"}
    for r in sorted(results, key=lambda r: ("dead", "blocked", "ok").index(r["state"])):
        print(f"{icon[r['state']]} {r['state']:<7} {str(r['status'] or '-'):>4} {r['url']}"
              + (f"  -> {r['final_url']}" if r["final_url"] else "") + (f"  [{r['error']}]" if r["error"] else "")
              + f"  ({r['where']})")
    n = {s: sum(r["state"] == s for r in results) for s in ("ok", "blocked", "dead")}
    print(f"\nsummary: {n['ok']} ok, {n['blocked']} blocked (check by hand), {n['dead']} dead", file=sys.stderr)
    if a.out:
        if a.out.endswith(".json"):
            json.dump(results, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        else:
            with open(a.out, "w", encoding="utf-8") as f:
                f.write("state\tstatus\turl\tfinal_url\terror\twhere\tchecked\n")
                for r in results:
                    f.write("\t".join(str(r.get(k) or "") for k in ("state", "status", "url", "final_url", "error", "where", "checked")) + "\n")
        print(f"report -> {a.out}", file=sys.stderr)
    if a.write and data_dir and os.path.exists(os.path.join(data_dir, "portals.json")):
        p = os.path.join(data_dir, "portals.json")
        portals = json.load(open(p, encoding="utf-8"))
        by = {r["url"]: r for r in results}
        for x in portals:
            r = by.get(x.get("url"))
            if r:
                x["url_status"] = r["state"]
                x["url_http"] = r["status"]
                x["url_checked"] = r["checked"]
        json.dump(portals, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"updated url_status in {p}", file=sys.stderr)
    sys.exit(0 if a.no_fail or not n["dead"] else 1)
