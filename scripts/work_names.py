# -*- coding: utf-8 -*-
"""`title` is the full title the report shows. `name` is the required short label."""


def _cjk(ch):
    o = ord(ch)
    return 0x2E80 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF or 0xFF00 <= o <= 0xFFEF


def _inside_latin_word(prev, nxt):
    if not prev or not nxt or _cjk(prev) or _cjk(nxt):
        return False
    return prev.isalnum() and nxt.isalnum()


def _head_word(text):
    """First word and the unconsumed tail. A CJK character is its own word."""
    s = text.lstrip()
    if not s:
        return "", ""
    if _cjk(s[0]):
        return s[0], s[1:]
    j = 0
    while j < len(s) and not _cjk(s[j]) and s[j].isalnum():
        j += 1
    if j == 0:
        return "", s
    return s[:j], s[j:]


def truncate_words(text, limit):
    """Shorten `text` to at most `limit` characters without cutting a Latin word.

    The result ends with … when characters were dropped. A word longer than `limit`
    is kept whole, so the result can be longer than `limit` rather than sliced.
    Spaces and hyphens are boundaries. Each CJK character is its own word.
    """
    text = str(text or "")
    limit = int(limit)
    if limit < 1 or len(text) <= limit:
        return text
    word, rest = _head_word(text)
    if limit < 2 or not word:
        if word and rest.strip():
            return word + "…"
        return text
    cut = limit - 1
    while cut > 0 and _inside_latin_word(text[cut - 1], text[cut]):
        cut -= 1
    body = text[:cut].rstrip(" \t-/·")
    if not body:
        if rest.strip():
            return word + "…"
        return text
    if body == text:
        return text
    return body + "…"


def is_hard_truncated_name(name, title):
    """True when `name` is a sliced prefix of `title`, not a real short name.

    A real short name is either not a prefix, or the clause before ':' / '—'
    (SciMON, The Virtual Lab). A prefix that ends inside a Latin word, splits a
    hyphenated word ("Toward self" + "-driving"), or is a long unlabeled slice
    (40 characters or more, the 60-character `title[:60]` case) is a hard cut.
    """
    name = str(name or "").strip()
    title = str(title or "").strip()
    if not name or not title or name == title:
        return False
    if name.endswith("…") or name.endswith("..."):
        return False
    if not title.startswith(name):
        return False
    rest = title[len(name):]
    if not rest:
        return False
    if rest[0] in ":：—" or rest.startswith(" - "):
        return False
    if _inside_latin_word(name[-1], rest[0]):
        return True
    if name[-1].isalnum() and not _cjk(name[-1]) and rest[0] == "-":
        return True
    return len(name) >= 40


def work_display_title(work):
    work = work or {}
    title = str(work.get("title") or "").strip()
    if title:
        return title
    return str(work.get("name") or "").strip()


def repair_works(works):
    """Copy `title` back into `name` where `name` is a hard-cut prefix.

    Returns (new_list, count). The input list and its dicts are not mutated.
    Real short names are left as they are. The table shows `title` either way.
    """
    out = []
    n = 0
    for w in works or []:
        if isinstance(w, dict) and is_hard_truncated_name(w.get("name"), w.get("title")):
            w = dict(w)
            w["name"] = str(w.get("title") or "").strip()
            n += 1
        out.append(w)
    return out, n
