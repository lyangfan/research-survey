# -*- coding: utf-8 -*-
"""Shared helpers: polite HTTP GET with retry/backoff, simple ID normalisation, JSONL IO.

Only the Python standard library is used so the fetch helpers run anywhere.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = os.environ.get(
    "SURVEY_UA",
    "research-survey-html/1.0 (+https://github.com/lyangfan/research-survey; mailto:"
    + os.environ.get("SURVEY_MAILTO", "anonymous@example.com") + ")",
)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def http_get(url, params=None, headers=None, retries=4, backoff=3.0, timeout=40, data=None):
    """GET (or POST when data is given) with exponential backoff on 429/5xx.

    Honours a Retry-After header when the server sends one. Returns the decoded body text.
    Raises the last error when every retry fails.
    """
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    last = None
    for i in range(retries + 1):
        try:
            body = None
            if data is not None:
                body = json.dumps(data).encode() if not isinstance(data, (bytes, str)) else (data.encode() if isinstance(data, str) else data)
                h.setdefault("Content-Type", "application/json")
            req = urllib.request.Request(url, data=body, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504) and i < retries:
                ra = e.headers.get("Retry-After")
                wait = float(ra) if ra and ra.isdigit() else backoff * (2 ** i)
                log(f"[http] {e.code} on {url[:90]}… retry in {wait:.0f}s")
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            if i < retries:
                time.sleep(backoff * (2 ** i))
                continue
            raise
    raise last


def get_json(url, **kw):
    return json.loads(http_get(url, **kw))


ARXIV_RE = re.compile(r"(?:arxiv[:/ ]|abs/|pdf/)?(\d{4}\.\d{4,5})(v\d+)?", re.I)
DOI_RE = re.compile(r"(10\.\d{4,9}/[^\s\"<>]+)", re.I)


def norm_arxiv(s):
    if not s:
        return ""
    m = ARXIV_RE.search(str(s))
    return m.group(1) if m else ""


def norm_doi(s):
    if not s:
        return ""
    m = DOI_RE.search(str(s))
    return m.group(1).rstrip(".,;)").lower() if m else ""


def norm_title(s):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (s or "").lower())


def dedup_key(rec):
    """Priority: DOI (non-arXiv) > arXiv ID > normalised title."""
    doi = norm_doi(rec.get("doi"))
    ax = norm_arxiv(rec.get("arxiv") or rec.get("url") or "")
    if doi and not doi.startswith("10.48550/arxiv."):
        return "doi:" + doi
    if ax:
        return "arxiv:" + ax
    if doi:
        return "arxiv:" + doi.split("arxiv.")[-1]
    return "title:" + norm_title(rec.get("title"))


def write_jsonl(path, rows):
    out = sys.stdout if path in (None, "-") else open(path, "w", encoding="utf-8")
    for r in rows:
        out.write(json.dumps(r, ensure_ascii=False) + "\n")
    if out is not sys.stdout:
        out.close()
        log(f"wrote {len(rows)} records -> {path}")


def read_records(path):
    """Read .jsonl or .json (list) records."""
    with open(path, encoding="utf-8") as f:
        txt = f.read().strip()
    if not txt:
        return []
    if txt[0] == "[":
        return json.loads(txt)
    return [json.loads(l) for l in txt.splitlines() if l.strip()]


def today():
    return time.strftime("%Y-%m-%d")
