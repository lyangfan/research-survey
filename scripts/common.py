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


# 429 bodies that mean "quota used up for the day" -> retrying cannot help, fail fast
QUOTA_RE = re.compile(r"insufficient budget|quota (exceeded|exhausted)|daily (limit|quota)", re.I)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def http_get(url, params=None, headers=None, retries=4, backoff=3.0, timeout=40, data=None,
             max_wait=120, deadline=None):
    """GET (or POST when data is given) with exponential backoff on 429/5xx.

    Honours a Retry-After header when the server sends one, but never sleeps longer than
    `max_wait` seconds per retry, and gives up once `deadline` seconds (total, default from
    $SURVEY_HTTP_DEADLINE, else unlimited) have passed, so a quota-exhausted API cannot hang a
    run for many minutes. Returns the decoded body text. Raises the last error when every
    retry fails.
    """
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    if deadline is None and os.environ.get("SURVEY_HTTP_DEADLINE"):
        deadline = float(os.environ["SURVEY_HTTP_DEADLINE"])
    t0 = time.time()
    last = None

    def _sleep_or_give_up(wait):
        wait = min(wait, max_wait)
        if deadline is not None and time.time() - t0 + wait > deadline:
            return False
        time.sleep(wait)
        return True

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
            try:
                e.body_text = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                e.body_text = ""
            if e.code == 429 and QUOTA_RE.search(e.body_text):
                log(f"[http] 429 quota/budget exhausted on {url[:90]}… (not retrying)")
                raise
            if e.code in (429, 500, 502, 503, 504) and i < retries:
                ra = e.headers.get("Retry-After")
                wait = float(ra) if ra and ra.isdigit() else backoff * (2 ** i)
                log(f"[http] {e.code} on {url[:90]}… retry in {min(wait, max_wait):.0f}s ({i + 1}/{retries})")
                if _sleep_or_give_up(wait):
                    continue
                log("[http] deadline reached, giving up")
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            if i < retries and _sleep_or_give_up(backoff * (2 ** i)):
                continue
            raise
    raise last


def get_json(url, **kw):
    return json.loads(http_get(url, **kw))


ARXIV_RE = re.compile(r"(?:arxiv[:/ ]|abs/|pdf/)?(\d{4}\.\d{4,5})(v\d+)?", re.I)
DOI_RE = re.compile(r"(10\.\d{4,9}/[^\s\"<>]+)", re.I)
# Preprint DOIs. bioRxiv/medRxiv: 10.1101/YYYY.MM.DD.NNNNNN (or old 6-digit 10.1101/NNNNNN) until
# 2025-11, openRxiv prefix 10.64898/YYYY.MM.DD.NNNNNN from 2025-12-01. NB: plain 10.1101/ is also
# used by CSHL journals (Genome Res "10.1101/gr.…", Genes Dev "10.1101/gad.…"), so only the
# numeric/date-shaped suffix counts. Others: Research Square, Preprints.org, ChemRxiv, SSRN, OSF.
PREPRINT_DOI_RE = re.compile(
    r"^(10\.1101/(\d{4}\.\d{2}\.\d{2}\.)?\d{6,}"
    r"|10\.64898/"
    r"|10\.21203/rs\.|10\.20944/preprints|10\.26434/chemrxiv|10\.2139/ssrn|10\.31219/osf\.io|10\.48550/arxiv\.)", re.I)
RXIV_DOI_RE = re.compile(r"^(10\.1101/(\d{4}\.\d{2}\.\d{2}\.)?\d{6,}|10\.64898/)", re.I)


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


def is_preprint_doi(doi):
    """True for bioRxiv/medRxiv (10.1101 date-shaped, 10.64898) and other preprint-server DOIs."""
    return bool(PREPRINT_DOI_RE.match(norm_doi(doi)))


def is_rxiv_doi(doi):
    """True for bioRxiv/medRxiv DOIs (old 10.1101 and new openRxiv 10.64898 prefix)."""
    return bool(RXIV_DOI_RE.match(norm_doi(doi)))


def preprint_server(doi="", venue="", url=""):
    """Best-effort preprint server name from DOI / venue / URL ('' when not a preprint)."""
    d, t = norm_doi(doi), f"{venue} {url}".lower()
    for name in ("medRxiv", "bioRxiv", "ChemRxiv", "SSRN", "Research Square", "Preprints.org", "arXiv", "OSF"):
        if name.lower() in t:
            return name
    if is_rxiv_doi(d):
        return "medRxiv" if "medrxiv" in t else "bioRxiv"
    if d.startswith("10.48550/arxiv.") or norm_arxiv(url) and "arxiv" in t:
        return "arXiv"
    if d.startswith("10.21203/rs."):
        return "Research Square"
    if d.startswith("10.20944/preprints"):
        return "Preprints.org"
    if d.startswith("10.26434/chemrxiv"):
        return "ChemRxiv"
    if d.startswith("10.2139/ssrn"):
        return "SSRN"
    if d.startswith("10.31219/osf.io"):
        return "OSF"
    return ""


def clean_title(s):
    """Strip HTML tags, collapse whitespace and drop one trailing period (PubMed/Europe PMC style)."""
    s = re.sub(r"<[^>]+>", "", s or "")
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:-1] if s.endswith(".") and not s.endswith("..") else s


# ---------------------------------------------------------------- author names
# Group / corporate authors ("GTEx Consortium", "eQTLGen Consortium", "FarmGTEx Consortium",
# "Human Cell Atlas Network") must stay ONE author; BibTeX needs them wrapped in braces.
CORP_RE = re.compile(
    r"\b(consortium|consortia|collaborat\w*|group|project|network|committee|initiative|investigators|"
    r"alliance|society|association|program(me)?|biobank|atlas|institute|laboratory|centre|center|"
    r"foundation|council|organi[sz]ation|study|team|working party|taskforce|task force|inc|ltd|llc|gmbh)\b", re.I)
ETAL_RE = re.compile(r"^(et\.? ?al\.?|others|等)$", re.I)
_SUFFIX = re.compile(r"^(jr|sr|ii|iii|iv|\d+(st|nd|rd|th))\.?$", re.I)
_PARTICLES = {"van", "von", "der", "den", "de", "del", "della", "da", "di", "du", "dos", "das", "le", "la", "ter", "ten", "bin", "al", "el"}


def parse_author(name):
    """Split an author string into {kind, last, first, suffix}.

    kind: "person" | "corporate" | "etal". Understands
      "Smith AB" / "van der Berg JH 2nd"   (PubMed / Europe PMC "Surname Initials")
      "Smith, Anna B."                     (already "Last, First")
      "Anna B. Smith" / "AB Smith"         (natural order)
      "GTEx Consortium", "{GTEx Consortium}" (group author -> corporate)
      "et al." / "others"                  (-> etal; exported as BibTeX "and others")
    """
    n = re.sub(r"\s*\((?:[^()]*)\)", "", str(name or "")).strip().strip(";")
    if not n:
        return None
    if ETAL_RE.match(n.strip()):
        return dict(kind="etal", last="", first="", suffix="", raw=n)
    if n.startswith("{") and n.endswith("}"):
        return dict(kind="corporate", last=n[1:-1].strip(), first="", suffix="", raw=n)
    if CORP_RE.search(n) or re.search(r"\d{3,}", n):
        return dict(kind="corporate", last=n, first="", suffix="", raw=n)
    if "," in n:
        last, first = [x.strip() for x in n.split(",", 1)]
        suffix = ""
        if "," in first and _SUFFIX.match(first.split(",")[0].strip()):
            suffix, first = [x.strip() for x in first.split(",", 1)]
        return dict(kind="person", last=last, first=first, suffix=suffix, raw=n)
    toks = n.split()
    suffix = ""
    if len(toks) > 2 and _SUFFIX.match(toks[-1]):
        suffix = toks.pop()
    if len(toks) == 1:
        return dict(kind="person", last=toks[0], first="", suffix=suffix, raw=n)
    # PubMed style: last token is 1-3 capital letters (initials), the rest is the surname
    if re.fullmatch(r"[A-Z\u00C0-\u00DE]{1,3}(-[A-Z])?", toks[-1]) and re.search(r"[a-z\u00DF-\u00FF]", " ".join(toks[:-1])):
        ini = toks[-1].replace("-", "")
        return dict(kind="person", last=" ".join(toks[:-1]), first=" ".join(c + "." for c in ini), suffix=suffix, raw=n)
    # natural order; keep lowercase particles (van der, de, von) with the surname
    i = len(toks) - 1
    while i > 1 and toks[i - 1].lower() in _PARTICLES:
        i -= 1
    return dict(kind="person", last=" ".join(toks[i:]), first=" ".join(toks[:i]), suffix=suffix, raw=n)


def author_surname(name):
    """Surname for citation keys ("Smith AB" -> "Smith", "GTEx Consortium" -> "GTEx")."""
    a = parse_author(name)
    if not a or a["kind"] == "etal":
        return ""
    if a["kind"] == "corporate":
        words = [w for w in re.split(r"[\s/]+", a["last"]) if w.lower() not in ("the", "of", "and")]
        return words[0] if words else a["last"]
    return a["last"].split()[-1] if a["last"] else ""


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


def log_query(path, source, query, hits=None, retrieved=None, out=None, **extra):
    """Append one line per executed query to a TSV search log (for the report's 'scope & method').

    path: explicit --log value, else $SURVEY_QUERY_LOG, else nothing is written.
    Columns: time (local, with UTC offset), source, query (verbatim), total hits, retrieved,
    output file, extra key=value pairs (filters etc.)."""
    path = path or os.environ.get("SURVEY_QUERY_LOG")
    if not path:
        return
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if new:
            f.write("time\tsource\tquery\thits\tretrieved\tout\textra\n")
        ex = " ".join(f"{k}={v}" for k, v in extra.items() if v not in (None, ""))
        f.write("\t".join(str(x if x is not None else "") for x in (
            time.strftime("%Y-%m-%d %H:%M:%S%z"), source, query.replace("\t", " ").replace("\n", " "),
            hits, retrieved, out or "-", ex)) + "\n")
    log(f"[log] query appended to {path}")
